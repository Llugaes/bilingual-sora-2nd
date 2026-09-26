#!/usr/bin/env python3
"""Compare fixed native-layout JSON snapshots without touching a live process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TARGET = "list_root/items/"
TARGET_SUFFIX = "/item_template/text"
STATE_BASE = 0x330


def load_labels(
    path: Path, layout_id: int = 55, path_contains: str = TARGET, path_suffix: str = TARGET_SUFFIX
) -> dict[str, dict[str, Any]]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    layout = next(item for item in snapshot["layouts"] if item["layout_id"]["value"] == layout_id)
    return {
        label["ptr"]: label
        for label in layout["labels"]
        if path_contains in label["path"] and label["path"].endswith(path_suffix)
    }


def raw_words(label: dict[str, Any], field: str) -> list[int]:
    return label["label"][field]["value"]["u32_le"]


def field_differences(left: list[int], right: list[int], base: int) -> list[dict[str, Any]]:
    return [
        {"offset": f"0x{base + index * 4:X}", "left": a, "right": b, "delta": b - a}
        for index, (a, b) in enumerate(zip(left, right, strict=True))
        if a != b
    ]


def glyph_geometry(label: dict[str, Any]) -> list[tuple[float | None, ...]]:
    return [
        tuple(record["geometry"][key] for key in ("x_0x38", "y_0x3c", "w_0x08", "h_0x1c"))
        for record in label["label"]["glyphs"]["records"]
        if record.get("ptr")
    ]


def parent_transforms(label: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "ptr": entry["ptr"],
            "name": entry.get("name"),
            "translation": entry.get("transform", {})
            .get("translation_row_0x38_0x47", {})
            .get("value", {})
            .get("f32_le"),
        }
        for entry in label["node"]["parent_chain"]
    ]


def line_info_parts(label: dict[str, Any]) -> dict[str, Any]:
    line_info = label["label"]["line_info"]
    records = [
        bytes.fromhex(record["raw"]["value"]["bytes_le_hex"]) for record in line_info["records"]
    ]
    return {
        "data": line_info["data"]["value"],
        "count": line_info["count"]["value"],
        # RVA 0x588570 reads a byte at record+0x08.  Do not assign a semantic
        # type to it here; preserve it separately from the first two floats.
        "prefix_0x00_0x07": [record[:8].hex() for record in records],
        "byte_0x08": [record[8] for record in records],
        "tail_0x09_0x0b": [record[9:].hex() for record in records],
    }


def summarize_pair(
    left_name: str,
    left: dict[str, dict[str, Any]],
    right_name: str,
    right: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    common = sorted(set(left) & set(right))
    entries: list[dict[str, Any]] = []
    control_equal = 0
    parent_equal = 0
    line_data_count_equal = 0
    line_prefix_equal = 0
    glyph_xwh_equal = 0
    glyph_y_deltas: list[float] = []
    state_diffs: dict[str, list[dict[str, Any]]] = {}

    for ptr in common:
        a, b = left[ptr], right[ptr]
        a_label, b_label = a["label"], b["label"]
        a_control = raw_words(a, "measurement_control_raw_0x2d8_0x317")
        b_control = raw_words(b, "measurement_control_raw_0x2d8_0x317")
        a_state = raw_words(a, "measurement_state_raw_0x330_0x3bf")
        b_state = raw_words(b, "measurement_state_raw_0x330_0x3bf")
        state = field_differences(a_state, b_state, STATE_BASE)
        for item in state:
            state_diffs.setdefault(item["offset"], []).append(item)
        a_glyphs, b_glyphs = glyph_geometry(a), glyph_geometry(b)
        same_xwh = len(a_glyphs) == len(b_glyphs) and all(
            a_item[0] == b_item[0] and a_item[2:] == b_item[2:]
            for a_item, b_item in zip(a_glyphs, b_glyphs, strict=True)
        )
        if same_xwh:
            glyph_xwh_equal += 1
            glyph_y_deltas.extend(
                b_item[1] - a_item[1] for a_item, b_item in zip(a_glyphs, b_glyphs)
            )
        control_equal += a_control == b_control
        parent_equal += parent_transforms(a) == parent_transforms(b)
        a_line, b_line = line_info_parts(a), line_info_parts(b)
        same_line_data_count = (
            a_line["data"] == b_line["data"] and a_line["count"] == b_line["count"]
        )
        same_line_prefix = a_line["prefix_0x00_0x07"] == b_line["prefix_0x00_0x07"]
        line_data_count_equal += same_line_data_count
        line_prefix_equal += same_line_prefix
        entries.append(
            {
                "ptr": ptr,
                "path": a["path"],
                "same_path": a["path"] == b["path"],
                "same_text": a_label["text"] == b_label["text"],
                "glyph_count": {
                    left_name: len(a_glyphs),
                    right_name: len(b_glyphs),
                },
                "flags": {
                    left_name: a_label["flags"]["value"],
                    right_name: b_label["flags"]["value"],
                },
                "measurement_control_equal": a_control == b_control,
                "parent_transforms_equal": parent_transforms(a) == parent_transforms(b),
                "line_info": {
                    "same_data_and_count": same_line_data_count,
                    "same_record_prefix_0x00_0x07": same_line_prefix,
                    "byte_0x08": {left_name: a_line["byte_0x08"], right_name: b_line["byte_0x08"]},
                },
                "glyph_xwh_equal": same_xwh,
                "glyph_y_delta": (
                    sorted(set(glyph_y_deltas[-len(a_glyphs) :])) if same_xwh and a_glyphs else []
                ),
                "measurement_state_differences": state,
            }
        )

    return {
        "left": left_name,
        "right": right_name,
        "common_ptr_count": len(common),
        "only_left": sorted(set(left) - set(right)),
        "only_right": sorted(set(right) - set(left)),
        "consistent_fields": {
            "measurement_control_equal_count": control_equal,
            "parent_transforms_equal_count": parent_equal,
            "line_info_same_data_and_count": line_data_count_equal,
            "line_info_same_record_prefix_0x00_0x07": line_prefix_equal,
            "glyph_xwh_equal_count": glyph_xwh_equal,
            "glyph_y_deltas_when_xwh_equal": sorted(set(glyph_y_deltas)),
        },
        "measurement_state_differences_by_offset": {
            offset: {
                "affected_count": len(items),
                "values": sorted({(item["left"], item["right"], item["delta"]) for item in items}),
            }
            for offset, items in state_diffs.items()
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cold", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--hot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--layout-id", type=int, default=55)
    parser.add_argument("--path-contains", default=TARGET)
    parser.add_argument("--path-suffix", default=TARGET_SUFFIX)
    args = parser.parse_args()
    snapshots = {
        name: load_labels(getattr(args, name), args.layout_id, args.path_contains, args.path_suffix)
        for name in ("cold", "primary", "hot")
    }
    comparisons = [
        summarize_pair("cold", snapshots["cold"], "primary", snapshots["primary"]),
        summarize_pair("primary", snapshots["primary"], "hot", snapshots["hot"]),
        summarize_pair("cold", snapshots["cold"], "hot", snapshots["hot"]),
    ]
    cold_hot = comparisons[2]
    result = {
        "scope": {
            "layout_id": args.layout_id,
            "path_contains": args.path_contains,
            "path_suffix": args.path_suffix,
        },
        "inputs": {name: str(getattr(args, name)) for name in snapshots},
        "label_counts": {name: len(labels) for name, labels in snapshots.items()},
        "comparisons": comparisons,
        "observed_cold_hot_delta_locus": {
            "common_items": cold_hot["common_ptr_count"],
            "unchanged_across_all_common_items": {
                "measurement_control_0x2d8_0x317": cold_hot["consistent_fields"][
                    "measurement_control_equal_count"
                ],
                "parent_transforms": cold_hot["consistent_fields"]["parent_transforms_equal_count"],
                "glyph_x_w_h": cold_hot["consistent_fields"]["glyph_xwh_equal_count"],
                "line_info_data_count": cold_hot["consistent_fields"][
                    "line_info_same_data_and_count"
                ],
                "line_info_record_prefix_0x00_0x07": cold_hot["consistent_fields"][
                    "line_info_same_record_prefix_0x00_0x07"
                ],
            },
            "glyph_y_delta": cold_hot["consistent_fields"]["glyph_y_deltas_when_xwh_equal"],
            "measurement_state_word_differences": cold_hot[
                "measurement_state_differences_by_offset"
            ],
        },
        "interpretation_limit": (
            "This compares captured state only. Equal or different fields do not establish a causal "
            "write path or a root cause without paired runtime evidence."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
