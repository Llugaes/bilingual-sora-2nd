"""Offline raw-field inventory and model-path audit; never reads a live process."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import sections, schema_for, record_identity
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables

# Disk offsets are explicit so the field denominator does not come from accepted catalog entries.
FIELDS = {
    "table/t_mapjump.tbl": {
        "MapJumpAreaData": (56, {"name": 8}),
        "MapJumpSpotData": (152, {"name": 16}),
    },
    "table/t_item.tbl": {"ItemTableData": (256, {"name": 224, "description": 232})},
    "table/t_itemhelp.tbl": {"ItemKindHelpData": (32, {"description": 8, "label": 24})},
}


def audit(game, catalog, model_path, evidence_path):
    catalog_data = json.loads(catalog.read_text("utf-8"))
    entries = {e["key"]: e for e in catalog_data["entries"]}
    model = json.loads(model_path.read_text("utf-8"))
    evidence = json.loads(evidence_path.read_text("utf-8"))
    inventory, gaps = [], []
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_tables(archive)
            for path, kinds in FIELDS.items():
                data = archive.read(logical[path])
                headers = sections(data)
                floor = max(start + stride * count for _, start, stride, count in headers)
                for index, (kind, start, stride, count) in enumerate(headers):
                    if kind not in kinds:
                        continue
                    expected_stride, fields = kinds[kind]
                    assert stride == expected_stride
                    occurrence = sum(s[0] == kind for s in headers[:index])
                    prefix = (
                        path
                        if index == 0
                        else path + "/" + kind + (f"/{occurrence}" if occurrence else "")
                    )
                    counters = Counter(records=count, fields=count * len(fields))
                    for row in range(count):
                        at = start + row * stride
                        identity = record_identity(data, at, kind, schema_for(path, kind), floor)
                        for field, offset in fields.items():
                            pointer = struct.unpack_from("<Q", data, at + offset)[0]
                            source = (
                                data[pointer : data.index(b"\0", pointer)].decode("utf-8")
                                if pointer
                                else ""
                            )
                            if not source.strip():
                                counters["empty"] += 1
                                continue
                            counters["nonempty"] += 1
                            key = f"{prefix}/{identity}/{field}"
                            entry = entries.get(key)
                            stage = (
                                "catalog_missing"
                                if entry is None
                                else (
                                    "association_mismatch"
                                    if entry["texts"].get(language) != source
                                    else "associated"
                                )
                            )
                            counters[stage] += 1
                            if stage != "associated":
                                gaps.append(
                                    {
                                        "language": language,
                                        "path": path,
                                        "kind": kind,
                                        "row": row,
                                        "field": field,
                                        "key": key,
                                        "source": source,
                                        "stage": stage,
                                    }
                                )
                    inventory.append(
                        {
                            "language": language,
                            "path": path,
                            "kind": kind,
                            "occurrence": occurrence,
                            "resource_sha256": hashlib.sha256(data).hexdigest(),
                            **counters,
                        }
                    )
    cases = []
    for observed in evidence["cases"]:
        source = observed["source"]
        candidates = [e for e in entries.values() if e["texts"].get("en") == source]
        table = model.get("table_identities", {})
        cases.append(
            {
                "source": source,
                "global_pair": model["pairs"].get(source),
                "map_pair": model.get("scoped", {})
                .get("map_spot", {})
                .get("pairs", {})
                .get(source),
                "catalog_owners": [
                    {
                        "key": e["key"],
                        "languages": sorted(e["texts"]),
                        "pair": [e["texts"].get("zh-Hans"), e["texts"].get("ja")],
                    }
                    for e in candidates
                ],
                "compiled_table_owners": [
                    c["key"] for c in table.get("sources", {}).get(source, [])
                ],
                "full_owner_pairs": [
                    {"source": s, "pair": p}
                    for s, p in model["pairs"].items()
                    if source in s and s != source
                ][:4],
            }
        )
    return {
        "method": "raw eight-language PAC fields -> existing catalog associations -> exact model paths",
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "inventory": inventory,
        "gaps": gaps,
        "observed_cases": cases,
        "limits": [
            "Resource inventory is not actual UI coverage.",
            "No raw setter segmentation or copied item-owner identity was captured.",
            "Keys reuse production resource identity; text and physical field denominators come from raw bytes.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "model", "evidence", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game, args.catalog, args.model, args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "raw_nonempty_fields": sum(r["nonempty"] for r in report["inventory"]),
                "gaps": len(report["gaps"]),
                "association_mismatches": sum(
                    r["stage"] == "association_mismatch" for r in report["gaps"]
                ),
            }
        )
    )
