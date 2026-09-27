"""Audit the full-screen command-8 family against a rebuilt local catalog.

Reads all installed language archives. Never attaches to the game. This checks
resource extraction and exact language pairing, not visible-control coverage.
"""

import argparse
from collections import Counter
import json
from pathlib import Path

from sora_bilingual.localization.resources import (
    FpacArchive,
    LANGUAGES,
    _ARCHIVES,
    _logical_script_entries,
    assembled_dialogue,
    parse_scp,
)


def is_command8(call):
    return (
        call.kind == 3
        and len(call.args) >= 2
        and call.args[0] == ("int", 5)
        and call.args[1] == ("int", 8)
    )


def literal_tail(call):
    """Return whether command 8 has a static display payload.

    Only the observed window/single-style prefixes are admitted. Integer
    sequences can themselves generate text (17,itemId); an all-integer
    prefix is not proof of a static payload.
    """
    if not is_command8(call):
        return False
    first = next((i for i, (kind, _) in enumerate(call.args) if kind == "string"), None)
    return (
        first in (3, 4)
        and call.args[2][0] == "int"
        and (first == 3 or call.args[3] in (("int", 13), ("int", 16), ("int", 26), ("int", 28)))
        and all(
            kind == "string" or (kind == "int" and value == 10) for kind, value in call.args[first:]
        )
    )


def first_string_index(call):
    return next((i for i, (kind, _) in enumerate(call.args) if kind == "string"), None)


def literal_failure_reason(call):
    first = first_string_index(call)
    if first is None:
        return "no_string"
    if first < 3:
        return "first_string_before_arg3"
    if any(kind != "int" for kind, _ in call.args[2:first]):
        return "noninteger_prefix"
    if first > 4 or (
        first == 4 and call.args[3] not in (("int", 13), ("int", 16), ("int", 26), ("int", 28))
    ):
        return "unverified_integer_prefix"
    return "nonliteral_after_first_string"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))["entries"]
    catalog_by_key = {entry["key"]: entry for entry in catalog}
    catalog_groups = {}
    for entry in catalog:
        if "/assembled_dialogue/alignment/" in entry["key"]:
            base = entry["key"].split("/alignment/", 1)[0]
            catalog_groups.setdefault(base, []).append(entry)
    archives = {
        language: FpacArchive(args.game / "pac/steam" / _ARCHIVES[language])
        for language in LANGUAGES
    }
    try:
        paths = {
            language: _logical_script_entries(archive) for language, archive in archives.items()
        }
        counters, examples, peer_examples, source_examples = Counter(), [], {}, {}

        def note(reason, key, language):
            counters[reason] += 1
            rows = peer_examples.setdefault(reason, [])
            if len(rows) < 3:
                rows.append({"key": key, "language": language})

        def note_source(reason, key, call):
            rows = source_examples.setdefault(reason, [])
            if len(rows) < 3:
                rows.append(
                    {
                        "key": key,
                        "first_string_arg": first_string_index(call),
                        "args": call.args,
                    }
                )

        for path, actual in paths["zh-Hans"].items():
            source = parse_scp(archives["zh-Hans"].read(actual))
            peers = {
                language: parse_scp(archives[language].read(paths[language][path]))
                for language in LANGUAGES
                if path in paths[language]
            }
            for function_name, function in source.functions.items():
                for call_index, call in enumerate(function.called):
                    if not is_command8(call):
                        continue
                    counters["source_command8"] += 1
                    key = f"{path}/{function_name}/called/{call_index}/assembled_dialogue"
                    first = first_string_index(call)
                    if first is None:
                        counters["source_no_string"] += 1
                        note_source("source_no_string", key, call)
                        continue
                    if first < 3:
                        counters["source_first_string_before_arg3"] += 1
                        note_source("source_first_string_before_arg3", key, call)
                        continue
                    counters[f"source_first_string_arg_{first}"] += 1
                    if any(kind != "int" for kind, _ in call.args[2:first]):
                        counters["source_noninteger_prefix"] += 1
                        note_source("source_noninteger_prefix", key, call)
                        continue
                    if not literal_tail(call):
                        reason = "source_" + literal_failure_reason(call)
                        counters[reason] += 1
                        note_source(reason, key, call)
                        continue
                    counters["source_literal_payload"] += 1
                    values, missing = {}, []
                    for language in LANGUAGES:
                        if path not in paths[language]:
                            missing.append(language)
                            note("peer_path_missing", key, language)
                            continue
                        peer = peers.get(language, None)
                        if peer is None or function_name not in peer.functions:
                            missing.append(language)
                            note("peer_function_missing", key, language)
                            continue
                        calls = peer.functions[function_name].called
                        if call_index >= len(calls):
                            missing.append(language)
                            note("peer_call_index_missing", key, language)
                            continue
                        if not is_command8(calls[call_index]):
                            missing.append(language)
                            note("peer_not_command8", key, language)
                            continue
                        value = assembled_dialogue(calls[call_index])
                        if value is None:
                            missing.append(language)
                            note(
                                "peer_command8_" + literal_failure_reason(calls[call_index]),
                                key,
                                language,
                            )
                        else:
                            values[language] = value
                    if missing:
                        counters["literal_payload_missing_or_dynamic_peer"] += 1
                        continue
                    counters["literal_payload_all8"] += 1
                    entry = catalog_by_key.get(key)
                    if entry is None:
                        aligned = catalog_groups.get(key, [])
                        if aligned:
                            counters["catalog_alignment_split"] += 1
                            present_languages = set().union(*(e["texts"] for e in aligned))
                            if len(examples) < 50:
                                examples.append(
                                    {
                                        "key": key,
                                        "kind": "alignment_split",
                                        "missing_languages": sorted(
                                            set(LANGUAGES) - present_languages
                                        ),
                                        "groups": [sorted(e["texts"]) for e in aligned],
                                    }
                                )
                            continue
                        counters["all8_literal_missing_catalog"] += 1
                        if len(examples) < 50:
                            examples.append({"key": key, "kind": "missing_catalog"})
                        continue
                    present = entry.get("texts", {})
                    absent = [language for language in LANGUAGES if language not in present]
                    if absent:
                        counters["catalog_partial_languages"] += 1
                        if len(examples) < 50:
                            examples.append(
                                {"key": key, "kind": "catalog_partial", "missing": absent}
                            )
                        continue
                    if any(present[language] != values[language] for language in LANGUAGES):
                        counters["catalog_text_conflict"] += 1
                        if len(examples) < 50:
                            examples.append({"key": key, "kind": "catalog_text_conflict"})
                        continue
                    counters["catalog_all8_exact"] += 1
        report = {
            "scope": "read-only real eight-language script PAC mapping to current catalog",
            "source_language": "zh-Hans",
            "candidate_definition": "group 5 command 8; first string at arg3 or arg4 with a verified single style; subsequent arguments are strings or int10 newline",
            "prefix_definition": "integer window argument, optionally one of 13/16/26/28; longer integer sequences, variables and calls are unverified",
            "counters": dict(sorted(counters.items())),
            "examples": examples,
            "peer_reason_examples": peer_examples,
            "source_reason_examples": source_examples,
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["counters"], ensure_ascii=False))
    finally:
        for archive in archives.values():
            archive.close()


if __name__ == "__main__":
    main()
