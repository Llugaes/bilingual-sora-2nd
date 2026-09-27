"""Audit the persisted message-log marker against every raw dialogue call.

This is an offline installed-resource check.  It never starts or attaches to
the game.  A marker is useful only when the exact locale, stored source and
stored speaker still select one physical dialogue record; the marker is never
treated as a replacement for the call ID.
"""

from __future__ import annotations

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

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries
from sora_bilingual.localization.resources import (
    FpacArchive,
    _ARCHIVES,
    _logical_script_entries,
    assembled_dialogue,
    parse_scp,
)
from sora_bilingual.localization.runtime_identity import _stable_dialogue_record
from sora_bilingual.localization.speaker_context import read_speaker_names


EXE_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"

# Exact instructions joining the SCP builder's operator-11 operand to the
# fourth log-writer argument, then to record +0.  The readable instruction
# sequence is also emitted in the generated diagnostic report.
NATIVE_PROOF = {
    # op 11/12 consumes the following integer, decodes it and stores it through
    # the fifth stack argument passed by each dialogue handler.
    0x4AD844: "8d47f583f8010f8685040000",
    0x4ADD1E: "8d149500000000",
    0x4ADD25: "c1fa02",
    0x4ADD28: "488b4424708910",
    # dialogue_popup: &local -> builder, local -> r9d -> log_write.
    0x4AE4C0: "488d4424304889442428",
    0x4AE4DB: "e890f1ffff",
    0x4AE524: "8b742430",
    0x4AE5BD: "448bce488d55a0",
    0x4AE5C4: "e8e7f9f8ff",
    # dialogue_message.
    0x4AEC10: "488d4424304889442428",
    0x4AEC2A: "e841eaffff",
    0x4AEC49: "448b7c2430",
    0x4AECFA: "458bcf488d55e0",
    0x4AED01: "e8aaf2f8ff",
    # dialogue_bubble.
    0x4AEF6E: "488d4424304889442428",
    0x4AEF89: "e8e2e6ffff",
    0x4AEFA9: "448b742430",
    0x4AF03D: "458bce488d55a0",
    0x4AF044: "e867eff8ff",
    # log_write saves r9d, builds a record at rsp+0x30 and copies that complete
    # record to owner+0x1604ec+slot*0x18c.  Therefore its first dword is r9d.
    0x43DFD7: "44894c2420458be1",
    0x43E0CF: "448b642420",
    0x43E118: "4489642430",
    0x43E197: "498d88ec041600",
    0x43E1B7: "0f10020f104a10488d9280000000",
}

NATIVE_CHAIN = [
    {
        "handler": "dialogue_popup",
        "handler_rva": "0x4ae2a0",
        "builder_call": "0x4ae4db",
        "marker_load": "0x4ae524",
        "writer_call": "0x4ae5c4",
    },
    {
        "handler": "dialogue_message",
        "handler_rva": "0x4ae990",
        "builder_call": "0x4aec2a",
        "marker_load": "0x4aec49",
        "writer_call": "0x4aed01",
    },
    {
        "handler": "dialogue_bubble",
        "handler_rva": "0x4aee20",
        "builder_call": "0x4aef89",
        "marker_load": "0x4aefa9",
        "writer_call": "0x4af044",
    },
]

KNOWN = {
    (
        "zh-Hans",
        33620,
        "<#E[#60s111EEE[autoEE]]#M_2#B_0>咦……！？",
        "艾丝蒂尔",
    ): "script/scena/mp3070.dat/EV_02_31_00/called/522/assembled_dialogue",
    (
        "zh-Hans",
        33511,
        "<#E_E#M_2#B_0>啊……",
        "艾丝蒂尔",
    ): "script/scena/mp3010_01.dat/EV_02_27_03/called/450/assembled_dialogue",
}
KNOWN_DYNAMIC = {
    (
        34132,
        "尤莉亚上尉",
        "……是！",
    ): "script/scena/mp3000_ev.dat/MayaEvent03_00_01/called/564/assembled_dialogue",
    (
        34139,
        "尤莉亚上尉",
        "喝啊──！",
    ): "script/scena/mp3000_ev.dat/MayaEvent03_00_01/called/908/assembled_dialogue",
}


def expression_body(value: str) -> str:
    return re.sub(r"^(?:<#[^<>]*>)+", "", value)


def verify_native_contract(executable: Path) -> dict:
    import pefile

    data = executable.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXE_SHA256:
        raise AssertionError(f"unexpected executable sha256: {digest}")
    pe = pefile.PE(data=data, fast_load=True)
    actual = {}
    for rva, expected in NATIVE_PROOF.items():
        raw = bytes.fromhex(expected)
        offset = pe.get_offset_from_rva(rva)
        value = data[offset : offset + len(raw)].hex()
        actual[hex(rva)] = value
        if value != expected:
            raise AssertionError(f"native marker contract changed at {rva:#x}")
    return {
        "exe": str(executable),
        "sha256": digest,
        "proof_bytes": actual,
        "handlers": NATIVE_CHAIN,
        "contract": (
            "The common text builder consumes the integer immediately after operator 11 "
            "or 12 and stores it through its fifth argument. Each of the three logged "
            "dialogue handlers passes one local dword there, then forwards the dword in "
            "r9d to log_write. log_write copies that dword to ring record +0."
        ),
    }


def _called_from_key(entry: dict, locale: str, canonical: int) -> int | None:
    called = entry.get("called_ids")
    if called is None:
        return canonical
    value = called.get(locale)
    return value if isinstance(value, int) and value >= 0 else None


def catalog_physical_records(entries: list[dict]) -> tuple[dict, dict]:
    """Return only catalog mappings that identify one stable physical call."""
    candidates = defaultdict(set)
    physicals_by_key = defaultdict(set)
    for entry in entries:
        record_key = _stable_dialogue_record(entry)
        if record_key is None or entry.get("display_role") != "dialogue":
            continue
        prefix, tail = record_key.rsplit("/called/", 1)
        canonical = int(tail.split("/", 1)[0])
        for locale, source in entry.get("texts", {}).items():
            called = _called_from_key(entry, locale, canonical)
            if called is None:
                continue
            path, function = prefix.split(".dat/", 1)
            physical = (locale, path + ".dat", function, called)
            candidates[physical].add((record_key, source))
            physicals_by_key[locale, record_key].add(physical)
    selected = {
        physical: next(iter(values)) for physical, values in candidates.items() if len(values) == 1
    }
    conflicts = {
        ":".join(map(str, physical)): sorted(values)
        for physical, values in candidates.items()
        if len(values) != 1
    }
    merged = {
        f"{locale}:{key}": sorted(values)
        for (locale, key), values in physicals_by_key.items()
        if len(values) > 1
    }
    return selected, {
        "catalog_physical_candidates": len(candidates),
        "catalog_physical_selected": len(selected),
        "catalog_physical_conflicts": conflicts,
        "record_keys_merging_independent_calls": merged,
    }


def builder_marker(call) -> tuple[int, int] | None:
    """Decode the raw pre-text builder stream independently of production.

    The logged handlers consume group, command and a numeric/dynamic speaker
    slot first.  A literal in slot 2 means command 0 omitted its speaker, so
    there cannot be a marker before the first displayed string.  The native
    builder consumes one operand after 11/12 and after the four interpolation
    operations; an operand equal to 11 or 12 is data, never another opcode.
    """
    args = call.args
    if (
        call.kind != 3
        or len(args) < 3
        or args[0] != ("int", 5)
        or args[1] not in (("int", 0), ("int", 6), ("int", 19))
        or args[2][0] == "string"
    ):
        return None
    first = next((index for index, (kind, _) in enumerate(args) if kind == "string"), None)
    if first is None:
        return None
    seen = []
    index = 3
    while index < first:
        kind, value = args[index]
        if kind != "int":
            return None
        operator = int(value)
        if operator in (11, 12, 17, 18, 21, 23):
            if index + 1 >= first or args[index + 1][0] != "int":
                return None
            if operator in (17, 18, 21, 23):
                return None
            seen.append((operator, int(args[index + 1][1])))
            index += 2
            continue
        index += 1
    return seen[-1] if seen else None


def audit_resources(game: Path, entries: list[dict]) -> dict:
    physical_records, catalog_audit = catalog_physical_records(entries)
    names = {locale: read_speaker_names(game, locale) for locale in LANGUAGES}
    counters = Counter()
    locale_counters = {locale: Counter() for locale in LANGUAGES}
    tuples = defaultdict(set)
    tuple_calls = defaultdict(set)
    locale_free = defaultdict(set)
    runtime_rows = defaultdict(set)
    raw_marker_values = []
    stored_marker_values = []
    for locale in LANGUAGES:
        archive = FpacArchive(game / "pac/steam" / _ARCHIVES[locale])
        try:
            for path, archive_path in sorted(_logical_script_entries(archive).items()):
                if not path.endswith(".dat"):
                    continue
                script = parse_scp(archive.read(archive_path))
                for function_name, function in script.functions.items():
                    for called, call in enumerate(function.called):
                        source = assembled_dialogue(call)
                        if source is None:
                            continue
                        counters["raw_dialogue"] += 1
                        locale_counters[locale]["raw_dialogue"] += 1
                        marker = builder_marker(call)
                        if marker is None:
                            counters["without_static_marker"] += 1
                            locale_counters[locale]["without_static_marker"] += 1
                            continue
                        operator, value = marker
                        stored_value = value & 0xFFFFFFFF
                        raw_marker_values.append(value)
                        stored_marker_values.append(stored_value)
                        counters[f"operator_{operator}"] += 1
                        locale_counters[locale][f"operator_{operator}"] += 1
                        if value == 0:
                            value_kind = "marker_zero"
                        elif value == 0xFFFF:
                            value_kind = "marker_ffff_sentinel"
                        elif value < 0:
                            value_kind = "marker_negative"
                        elif value > 0xFFFF:
                            value_kind = "marker_above_ffff"
                        else:
                            value_kind = "marker_positive"
                        counters[value_kind] += 1
                        locale_counters[locale][value_kind] += 1
                        if operator not in (11, 12) or stored_value in (0, 0xFFFF):
                            counters["unsupported_marker_shape"] += 1
                            locale_counters[locale]["unsupported_marker_shape"] += 1
                            continue
                        physical = (locale, path, function_name, called)
                        mapped = physical_records.get(physical)
                        if mapped is None:
                            counters["marker_without_stable_record"] += 1
                            locale_counters[locale]["marker_without_stable_record"] += 1
                            continue
                        record_key, catalog_source = mapped
                        if catalog_source != source:
                            counters["catalog_source_mismatch"] += 1
                            locale_counters[locale]["catalog_source_mismatch"] += 1
                            continue
                        speaker_id = None
                        if (
                            len(call.args) >= 3
                            and call.args[0] == ("int", 5)
                            and call.args[1] in (("int", 0), ("int", 6), ("int", 19))
                            and call.args[2][0] == "int"
                        ):
                            speaker_id = int(call.args[2][1])
                        speaker = names[locale].get(speaker_id)
                        if speaker:
                            counters["marker_with_static_unique_speaker"] += 1
                            locale_counters[locale]["marker_with_static_unique_speaker"] += 1
                        else:
                            counters["marker_without_static_unique_speaker"] += 1
                            locale_counters[locale]["marker_without_static_unique_speaker"] += 1
                            reason = (
                                "no_static_speaker_argument"
                                if speaker_id is None
                                else "speaker_id_missing_or_nonunique_in_name_table"
                            )
                            counters[reason] += 1
                            locale_counters[locale][reason] += 1
                        source_body = expression_body(source)
                        key = (locale, stored_value, source_body, speaker)
                        tuples[key].add(record_key)
                        tuple_calls[key].add(physical)
                        locale_free[stored_value, source_body, speaker].add(
                            (locale, record_key, path, function_name, called)
                        )
                        runtime_rows[stored_value].add(
                            (locale, source_body, speaker, record_key, called)
                        )
                        counters["fully_indexable_input"] += 1
                        locale_counters[locale]["fully_indexable_input"] += 1
                        if operator == 11:
                            counters["operator_11_fully_indexable_input"] += 1
                            locale_counters[locale]["operator_11_fully_indexable_input"] += 1
        finally:
            archive.close()
    conflicts = {
        json.dumps(key, ensure_ascii=False): {
            "record_keys": sorted(values),
            "physical_calls": sorted(tuple_calls[key]),
        }
        for key, values in tuples.items()
        if len(values) != 1 or len(tuple_calls[key]) != 1
    }
    admitted = {
        key: next(iter(values))
        for key, values in tuples.items()
        if len(values) == 1 and len(tuple_calls[key]) == 1
    }
    locale_free_admitted = {
        key: next(iter(values)) for key, values in locale_free.items() if len(values) == 1
    }
    locale_free_conflicts = {
        json.dumps(key, ensure_ascii=False): sorted(values)
        for key, values in locale_free.items()
        if len(values) != 1
    }
    locale_free_record_key_unique = sum(
        len({row[1] for row in values}) == 1 for values in locale_free.values()
    )

    def runtime_resolve(marker, speaker, source):
        matches = {
            (locale, record_key, called)
            for locale, candidate_source, candidate_speaker, record_key, called in runtime_rows[
                marker
            ]
            if candidate_source == expression_body(source)
            and (candidate_speaker is None or candidate_speaker == speaker)
        }
        keys = {record_key for _, record_key, _ in matches}
        return (next(iter(keys)) if len(keys) == 1 else None), sorted(matches)

    known_dynamic = []
    for (marker, speaker, source), expected in KNOWN_DYNAMIC.items():
        actual, matches = runtime_resolve(marker, speaker, source)
        known_dynamic.append(
            {
                "marker": marker,
                "speaker": speaker,
                "source": source,
                "expected": expected,
                "actual": actual,
                "matches": matches,
                "pass": actual == expected,
            }
        )
    if any(not item["pass"] for item in known_dynamic):
        raise AssertionError("known dynamic-speaker rows do not resolve uniquely")
    known = []
    for key, expected in KNOWN.items():
        normalized = (key[0], key[1], expression_body(key[2]), key[3])
        actual = admitted.get(normalized)
        known.append(
            {
                "tuple": list(key),
                "normalized_source_body": normalized[2],
                "expected": expected,
                "actual": actual,
                "pass": actual == expected,
            }
        )
    if any(not item["pass"] for item in known):
        raise AssertionError("known retained ring rows do not resolve uniquely")
    for key in (
        "operator_11",
        "operator_12",
        "marker_zero",
        "marker_ffff_sentinel",
        "marker_negative",
        "marker_above_ffff",
        "unsupported_marker_shape",
    ):
        counters.setdefault(key, 0)
        for values in locale_counters.values():
            values.setdefault(key, 0)
    if catalog_audit["catalog_physical_conflicts"]:
        raise AssertionError("a physical call has multiple stable catalog identities")
    if catalog_audit["record_keys_merging_independent_calls"]:
        raise AssertionError("one stable record key merges independent calls")
    if counters["catalog_source_mismatch"]:
        raise AssertionError("raw dialogue and catalog source disagree")
    if set(locale_counters) != set(LANGUAGES):
        raise AssertionError("not all installed source locales were audited")
    return {
        "all_locales": list(LANGUAGES),
        "marker_value_range": {
            "raw_signed_min": min(raw_marker_values) if raw_marker_values else None,
            "raw_signed_max": max(raw_marker_values) if raw_marker_values else None,
            "stored_u32_min": min(stored_marker_values) if stored_marker_values else None,
            "stored_u32_max": max(stored_marker_values) if stored_marker_values else None,
            "raw_negative_count": sum(value < 0 for value in raw_marker_values),
            "raw_above_ffff_count": sum(value > 0xFFFF for value in raw_marker_values),
            "stored_above_ffff_count": sum(value > 0xFFFF for value in stored_marker_values),
        },
        "counts": dict(sorted(counters.items())),
        "counts_by_locale": {
            locale: dict(sorted(values.items())) for locale, values in locale_counters.items()
        },
        "catalog": catalog_audit,
        "complete_tuple_count": len(tuples),
        "admitted_unique_physical_tuple_count": len(admitted),
        "ambiguous_or_merged_tuple_count": len(conflicts),
        "ambiguous_or_merged_tuples": conflicts,
        "locale_free_tuple_count": len(locale_free),
        "locale_free_unique_physical_count": len(locale_free_admitted),
        "locale_free_ambiguous_count": len(locale_free_conflicts),
        "locale_free_unique_record_key_count": locale_free_record_key_unique,
        "locale_free_multiple_record_key_count": len(locale_free) - locale_free_record_key_unique,
        "locale_free_ambiguous_samples": dict(list(locale_free_conflicts.items())[:50]),
        "known_ring_rows": known,
        "known_dynamic_speaker_rows": known_dynamic,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "generated/diagnostic-131-history-marker.json",
    )
    args = parser.parse_args()
    entries, _ = load_entries(args.game_dir)
    report = {
        "game_attached": False,
        "native": verify_native_contract(args.game_dir / "sora_2nd.exe"),
        "resources": audit_resources(args.game_dir, entries),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "locales": report["resources"]["all_locales"],
        "counts": report["resources"]["counts"],
        "complete_tuple_count": report["resources"]["complete_tuple_count"],
        "admitted_unique_physical_tuple_count": report["resources"][
            "admitted_unique_physical_tuple_count"
        ],
        "ambiguous_or_merged_tuple_count": report["resources"]["ambiguous_or_merged_tuple_count"],
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
