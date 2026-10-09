"""Independent physical-row oracle for the finite CAB62 Bracer History scope.

Only the two new component receipts are written. No production model compiler,
native attach, game process, or old failure expectation is changed.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.notebook_composition import compile_bracer_history
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

LANGUAGES = ("en", "ja", "zh-Hans", "zh-Hant")
CONFIGS = (
    ("en", "en", "en", "zh-Hans"),
    ("ja", "ja", "ja", "zh-Hans"),
    ("zh-Hans", "zh-Hans", "zh-Hans", "ja"),
    ("zh-Hant", "zh-Hant", "zh-Hant", "ja"),
    ("en-manual", "en", "ja", "zh-Hans"),
)
CODE = (
    "sora_bilingual/localization/notebook_composition.py",
    "sora_bilingual/localization/menu_text.py",
    "sora_bilingual/localization/native_catalog.py",
    "sora_bilingual/game/scripts/runtime_text.js",
    "sora_bilingual/game/scripts/native_agent.js",
    "sora_bilingual/game/scripts/runtime_paragraph.js",
    "sora_bilingual/game/scripts/runtime_identity.js",
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def catalog_rows(path, wanted):
    """Stream each catalog entry, retaining only the actual eleven identities."""
    decoder = json.JSONDecoder()
    selected = defaultdict(list)
    with Path(path).open(encoding="utf8") as stream:
        buffer = stream.read(65536)
        marker = re.search(r'"entries"\s*:\s*\[', buffer)
        if marker is None:
            raise ValueError("catalog entries array missing from initial header")
        buffer = buffer[marker.end() :]
        while True:
            buffer = buffer.lstrip()
            if not buffer:
                buffer = stream.read(65536)
                if not buffer:
                    raise ValueError("truncated catalog entries")
                continue
            if buffer[0] == "]":
                break
            if buffer[0] == ",":
                buffer = buffer[1:]
                continue
            while True:
                try:
                    entry, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    chunk = stream.read(65536)
                    if not chunk:
                        raise
                    buffer += chunk
            if entry.get("key") in wanted:
                selected[entry["key"]].append(entry)
            buffer = buffer[end:]
    return selected


def official_frame(rows, ordinal, source_locale, target_locale):
    """Reviewed native slots; this oracle does not call _history_frame."""
    source, target = rows[ordinal]["texts"][source_locale], rows[ordinal]["texts"][target_locale]
    if source_locale == target_locale:
        return source
    source_slots = source.split("\n")
    target_slots = target.split("\n")
    if ordinal == 0:
        source_starts = [0, 2] if source_locale == "en" else [0, 1]
        target_starts = [0, 2] if target_locale == "en" else [0, 1]
        assert len(source_slots) == (4 if source_locale == "en" else 2)
        assert len(target_slots) == (4 if target_locale == "en" else 2)
        ends = target_starts[1:] + [len(target_slots)]
        captions = [" ".join(target_slots[a:b]).strip() for a, b in zip(target_starts, ends)]
        framed = [""] * len(source_slots)
        for slot, caption in zip(source_starts, captions):
            framed[slot] = caption
        return "\n".join(framed)
    assert 1 <= len(source_slots) <= 2 and 1 <= len(target_slots) <= 2
    complete = " ".join(line for line in target_slots if line).strip()
    return complete + "\n" * (len(source_slots) - 1)


def selected_ordinals(rows, flags, mask):
    selected = {flag for bit, flag in enumerate(flags) if mask & (1 << bit)}
    return [row["ordinal"] for row in rows if row["condition_u16"] in selected]


def constructor(rows, ordinals, source_locale, target_locale):
    return "".join(official_frame(rows, i, source_locale, target_locale) + "\n" for i in ordinals)


def expected_plan(primary, secondary, mode):
    if mode != "annotation":
        return {"text": primary if mode == "primary" else secondary, "layers": [], "kind": "plain"}
    left, right = primary.split("\n"), secondary.split("\n")
    assert len(left) == len(right)
    output, layers = "", []
    for index, (a, b) in enumerate(zip(left, right)):
        if index:
            output += "\n"
        if a and b and a != b:
            layers.append(
                {
                    "offset": len(output.encode("utf8")) + 6,
                    "text": b,
                    "primary": a,
                    "protected": False,
                }
            )
            output += "<R></R_>"
        output += a
    return {"text": output, "layers": layers, "kind": "layered"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game", type=Path, default=Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    )
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "generated/r32-coverage-production/catalog.json"
    )
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "generated/r32-coverage-source-freeze.json"
    )
    parser.add_argument(
        "--input", type=Path, default=ROOT / "generated/r32-bracer-history-component-input.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r32-bracer-history-component-python.json"
    )
    args = parser.parse_args()
    assert not args.input.exists() and not args.output.exists(), (
        "never overwrite previous component evidence"
    )
    frozen = json.loads(args.freeze.read_text("utf8"))
    hashes = {name: digest(ROOT / name) for name in CODE}
    assert all(frozen["files"][name] == value for name, value in hashes.items()), (
        "source differs from current freeze"
    )
    static_path = ROOT / "generated/r32-bracer-history-static-builder-readonly.json"
    red_path = ROOT / "generated/r32-bracer-history-readonly.json"
    capture_path = ROOT / "generated/r32-live003-en-bracer-history-inputs.json"
    static = json.loads(static_path.read_text("utf8"))
    red = json.loads(red_path.read_text("utf8"))
    capture = json.loads(capture_path.read_text("utf8"))
    (observed,) = [row for row in capture["rows"] if len(row.get("original", "")) == 627]
    assert not observed["original_truncated"] and observed["source_matches_diagnostic"]
    diagnostic = observed["input_identity_diagnostic"]
    assert diagnostic["phase"] == "owned_update" and diagnostic["layout_id"] == 61
    assert diagnostic["node_path"] == ["history", "top_page_contents", "note_base", "root"]
    rows = [dict(row, texts={}) for row in static["physical_rows"]]
    assert [row["ordinal"] for row in rows] == list(range(11))
    selected_catalog = catalog_rows(
        args.catalog, {row["current_aligned_catalog_key"] for row in rows}
    )
    entries, table_evidence = [], []
    for language in LANGUAGES:
        archive_path = args.game / "pac/steam" / _TABLE_ARCHIVES[language]
        with FpacArchive(archive_path) as archive:
            data = archive.read(_logical_tables(archive)["table/t_quest_fc.tbl"])
        (descriptor,) = [row for row in sections(data) if row[0] == "NoteMainHistory"]
        _, start, stride, count = descriptor
        assert (stride, count) == (16, 11)
        for ordinal, row in enumerate(rows):
            at = start + ordinal * stride
            pointer, flag = struct.unpack_from("<QH", data, at)
            end = data.index(b"\0", pointer)
            raw = data[pointer:end].decode("utf8", "strict")
            key = row["current_aligned_catalog_key"]
            candidates = selected_catalog[key]
            assert len(candidates) == 1 and candidates[0]["texts"][language] == raw
            assert (
                flag == row["condition_u16"]
                and raw == static["physical_rows"][ordinal]["texts"][language]
            )
            assert raw and "<" not in raw and ">" not in raw
            row["texts"][language] = raw
        table_evidence.append(
            {
                "language": language,
                "archive_path": str(archive_path),
                "logical_table": "table/t_quest_fc.tbl",
                "table_sha256": hashlib.sha256(data).hexdigest(),
                "section_start": start,
                "physical_stride": stride,
                "physical_count": count,
            }
        )
    for row in rows:
        entries.append(selected_catalog[row["current_aligned_catalog_key"]][0])
    flags = list(dict.fromkeys(row["condition_u16"] for row in rows))
    assert len(flags) == 10 and rows[-2]["condition_u16"] == rows[-1]["condition_u16"] == 14187
    full_source = constructor(rows, list(range(11)), "en", "en")
    assert full_source == observed["original"]
    assert (
        hashlib.sha256(full_source.encode("utf8")).hexdigest()
        == static["known_live_constructor"]["source_en_utf8_sha256"]
    )
    failures, counts, samples, models = [], Counter(), [], []

    def check(ok, name, actual=None, expected=None):
        counts[name.split("/")[0]] += 1
        if not ok:
            failures.append({"name": name, "actual": actual, "expected": expected})

    compiled_by_source = {}
    for source_locale in LANGUAGES:
        compiled = compile_bracer_history(args.game, entries, LANGUAGES, source_locale)
        compiled_by_source[source_locale] = compiled
        check(
            len(compiled) == 1023, "physical/compiler_count/" + source_locale, len(compiled), 1023
        )
        for mask, entry in enumerate(compiled, 1):
            indices = selected_ordinals(rows, flags, mask)
            check(
                entry["key"] == f"table/t_bracer_history_generated/flags:{mask}/body",
                "physical/key/" + source_locale + "/" + str(mask),
                entry["key"],
                mask,
            )
            for language in LANGUAGES:
                expected = constructor(rows, indices, source_locale, language)
                check(
                    entry["texts"][language] == expected,
                    f"physical/{source_locale}/{mask}/{language}",
                    entry["texts"][language],
                    expected,
                )
    for label, source_locale, primary_locale, secondary_locale in CONFIGS:
        translator = MenuTranslator(
            entries + compiled_by_source[source_locale],
            primary_locale,
            secondary_locale,
            source_locale,
        )
        scoped = translator.scoped["bracer_history"]
        model = translator.runtime_model()
        check(
            model["scoped"]["bracer_history"].get("bracer_history_frame") is True,
            "scope/strict_frame/" + label,
        )
        for mask in range(1, 1024):
            indices = selected_ordinals(rows, flags, mask)
            source = constructor(rows, indices, source_locale, source_locale)
            primary = constructor(rows, indices, source_locale, primary_locale)
            secondary = constructor(rows, indices, source_locale, secondary_locale)
            check(
                source not in model["pairs"],
                f"scope/no_generated_global/{label}/{mask}",
                source in model["pairs"],
                False,
            )
            for mode in ("primary", "secondary", "annotation"):
                expected = expected_plan(primary, secondary, mode)
                actual = scoped.render(source, mode)
                check(actual == expected, f"python/{label}/{mask}/{mode}", actual, expected)
                if mask in (1, 512, 1023):
                    samples.append(
                        {
                            "label": label,
                            "mask": mask,
                            "ordinals": indices,
                            "source": source,
                            "mode": mode,
                            "expected": expected,
                            "actual": actual,
                        }
                    )
        models.append(
            {
                "label": label,
                "game_language": source_locale,
                "primary": primary_locale,
                "secondary": secondary_locale,
                "model": model,
            }
        )
    check(all(digest(ROOT / name) == value for name, value in hashes.items()), "source/unchanged")
    input_document = {
        "schema": 1,
        "source_snapshot_sha256": frozen["snapshot_sha256"],
        "production_source_sha256": hashes,
        "physical_rows": rows,
        "flags": flags,
        "models": models,
        "observed_source": observed["original"],
        "observed_displayed_before": observed["displayed"],
        "observed_diagnostic": {
            key: diagnostic.get(key)
            for key in ("phase", "node_path", "layout_id", "caller_rva", "scope")
        },
        "prior_failure_receipt": str(red_path),
        "prior_failure_receipt_sha256": digest(red_path),
        "capture_path": str(capture_path),
        "capture_sha256": digest(capture_path),
        "static_builder_path": str(static_path),
        "static_builder_sha256": digest(static_path),
        "oracle_rules": {
            "append": "selected complete physical body plus one LF, in ascending ordinal order",
            "initial_source_slots": {
                "en": [0, 2],
                "ja": [0, 1],
                "zh-Hans": [0, 1],
                "zh-Hant": [0, 1],
            },
            "recommendation_ordinals": [1, 3, 5, 7, 9],
            "same_flag_ordinals": [9, 10],
            "whole_target_event": "complete official event on first corresponding source slot; remaining native hard slots empty",
        },
    }
    args.input.write_text(
        json.dumps(input_document, ensure_ascii=False, separators=(",", ":")), encoding="utf8"
    )
    output = {
        "schema": 1,
        "kind": "bracer_history_physical_component_python",
        "source_snapshot_sha256": frozen["snapshot_sha256"],
        "production_source_sha256": hashes,
        "catalog_path": str(args.catalog),
        "catalog_sha256": digest(args.catalog),
        "catalog_streamed": True,
        "selected_catalog_entries": len(entries),
        "tables": table_evidence,
        "physical_rows": rows,
        "independent_flags": flags,
        "physical_constructor_count": 1023,
        "source_language_count": 4,
        "configuration_count": 5,
        "three_mode_plan_count": 15345,
        "original_627_source_exact": True,
        "original_capture_sha256": digest(capture_path),
        "prior_failure_receipt": str(red_path),
        "prior_failure_receipt_sha256": digest(red_path),
        "prior_failure_findings_unchanged": red["findings"],
        "static_builder_sha256": digest(static_path),
        "input_path": str(args.input),
        "input_sha256": digest(args.input),
        "counts": dict(counts),
        "failure_count": len(failures),
        "failures": failures,
        "complete_samples": samples,
        "component_model_only": True,
        "production_model_compiled": False,
        "game_attached": False,
        "limitations": [
            "Native-builder flag combinations are covered; normal story reachability is not asserted.",
            "Only EN all-eleven has a real captured full input; other inputs derive from verified physical native builder.",
            "Component proof does not endorse a subsequently built full wire or game glyph layout.",
        ],
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    "source_snapshot_sha256",
                    "physical_constructor_count",
                    "configuration_count",
                    "three_mode_plan_count",
                    "counts",
                    "failure_count",
                )
            }
        )
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
