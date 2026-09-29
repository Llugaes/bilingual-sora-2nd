"""Inventory installed PAC resources without opening or attaching to the game.

The detailed JSON retains every omitted string slot and unassembled text call.
Raw strings include identifiers, developer labels, and unused content: none of
these counts is an on-screen untranslated count. A separate summary is printed
and written beside the detailed report. Extraction, pairing, and runtime
observation are deliberately separate denominators.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct

from sora_bilingual.localization import resources
from sora_bilingual.localization.menu_tables import (
    SCHEMAS,
    read_section,
    record_identity,
    schema_for,
    sections,
)
from sora_bilingual.localization.resources import (
    FpacArchive,
    FormatError,
    LANGUAGES,
    _ARCHIVES,
    _logical_script_entries,
    _script_paths,
    assembled_dialogue,
    parse_scp,
)
from sora_bilingual.localization.tables import (
    _TABLE_ARCHIVES,
    _logical_tables,
    _text_rows,
    build_table_entries,
)


def record_family(key):
    if key.startswith("table/"):
        return "table"
    for family in ("assembled_display", "assembled_dialogue", "arg", "code"):
        if "/" + family + "/" in key or key.endswith("/" + family):
            return family
    return "other"


def command_family(call):
    if call.kind == 3:
        return "/".join(f"{kind}:{value}" for kind, value in call.args[:2])
    return f"kind:{call.kind}/target:{call.target}"


def text_call_reason(call):
    body = call.args[3:]
    if any(kind in ("call", "var", "expr") for kind, _ in body):
        return "dynamic_operand"
    position = 0
    while position < len(body):
        kind, value = body[position]
        if kind == "int" and value in (11, 12):
            position += 1  # A voice ID is an operand, not a text opcode.
        elif kind == "int" and value in (17, 18, 21, 23):
            return "possible_text_interpolation_opcode"
        position += 1
    if not any(kind == "string" and value for kind, value in body):
        return "no_nonempty_literal"
    return "unrecognized_static_control_grammar"


def catalog_inventory(entries):
    index = defaultdict(lambda: defaultdict(set))
    categories = defaultdict(Counter)
    gaps = []
    for entry in entries:
        key = entry["key"]
        base = key.split("/alignment/", 1)[0]
        texts = entry["texts"]
        for language, value in texts.items():
            index[base][language].add(value)
            called_ids = entry.get("called_ids")
            called = called_ids.get(language) if called_ids else None
            if isinstance(called, int) and "/called/" in base:
                prefix, rest = base.rsplit("/called/", 1)
                _canonical, separator, suffix = rest.partition("/")
                if separator:
                    localized = f"{prefix}/called/{called}/{suffix}"
                    index[localized][language].add(value)
        missing = [language for language in LANGUAGES if language not in texts]
        blank = [
            language for language in LANGUAGES if language in texts and not texts[language].strip()
        ]
        family = record_family(base)
        categories[family]["records"] += 1
        categories[family]["missing_locale_records"] += bool(missing)
        categories[family]["blank_locale_records"] += bool(blank)
        categories[family]["complete_nonblank_all8"] += not missing and not blank
        if missing or blank:
            gaps.append([key, missing, blank])
    return index, dict(categories), gaps


def indexed_text(index, key, language, text):
    return text in index.get(key, {}).get(language, ())


def audit_scripts(game, sources, index):
    counts = {language: Counter() for language in sources}
    families = {language: defaultdict(Counter) for language in sources}
    omitted, unassembled, prefix_risks, failures, absent = [], [], [], [], []
    archives = {}
    try:
        for language, name in _ARCHIVES.items():
            path = game / "pac/steam" / name
            if path.is_file():
                try:
                    archives[language] = FpacArchive(path)
                except (OSError, FormatError) as exc:
                    failures.append({"language": language, "archive": name, "reason": str(exc)})
            else:
                failures.append(
                    {"language": language, "archive": name, "reason": "missing_archive"}
                )
        paths = {
            language: _logical_script_entries(archive) for language, archive in archives.items()
        }
        all_paths = _script_paths(paths.values())
        for path in all_paths:
            parsed, unique = {}, {}
            for language, archive in archives.items():
                if path not in paths[language]:
                    absent.append([language, path])
                    continue
                data = archive.read(paths[language][path])
                if data not in unique:
                    try:
                        unique[data] = parse_scp(data)
                    except FormatError as exc:
                        unique[data] = str(exc)
                result = unique[data]
                if isinstance(result, str):
                    failures.append({"language": language, "path": path, "reason": result})
                else:
                    parsed[language] = result
            shapes = {}

            def signatures(language, name):
                identity = (language, name)
                if identity not in shapes:
                    function = parsed[language].functions[name]
                    shapes[identity] = (function.shape(), function.called_sequence_shape())
                return shapes[identity]

            for language in sources:
                if language not in parsed:
                    continue
                count = counts[language]
                count["parsed_files"] += 1
                script = parsed[language]
                count["functions"] += len(script.functions)
                for name, function in script.functions.items():
                    prefix = f"{path}/{name}"
                    peers = {l: s.functions[name] for l, s in parsed.items() if name in s.functions}
                    # These are exactly the production equivalence contracts.
                    code_shape, call_shape = signatures(language, name)
                    code_peers = [l for l in peers if signatures(l, name)[0] == code_shape]
                    call_peers = [l for l in peers if signatures(l, name)[1] == call_shape]
                    for ordinal, value in enumerate(function.code_strings):
                        count["code_string_slots"] += 1
                        key = f"{prefix}/code/{ordinal}"
                        if indexed_text(index, key, language, value):
                            count["code_slots_catalogued"] += 1
                        else:
                            count["code_slots_not_catalogued"] += 1
                            reason = (
                                "singleton_full_function_alignment"
                                if len(code_peers) < 2
                                else "catalog_missing_eligible_code_slot"
                            )
                            omitted.append([language, key, reason, value])
                    for ordinal, call in enumerate(function.called):
                        count["calls"] += 1
                        key = f"{prefix}/called/{ordinal}"
                        slots = list(call.display_text_slots())
                        family = families[language][command_family(call)]
                        family["calls"] += 1
                        family["calls_with_literal"] += bool(slots)
                        text = assembled_dialogue(call)
                        represented = text is not None and indexed_text(
                            index, key + "/assembled_dialogue", language, text
                        )
                        if text is not None:
                            count["assembled_literal_calls"] += 1
                            count[
                                "assembled_catalogued"
                                if represented
                                else "assembled_not_catalogued"
                            ] += 1
                            if not represented:
                                omitted.append(
                                    [
                                        language,
                                        key + "/assembled_dialogue",
                                        "assembled_text_not_in_catalog",
                                        text,
                                    ]
                                )
                        text_command = (
                            call.kind == 3
                            and len(call.args) >= 2
                            and call.args[0] == ("int", 5)
                            and call.args[1] in tuple(("int", n) for n in (0, 6, 7, 8, 19))
                        )
                        if text_command and text is None:
                            reason = text_call_reason(call)
                            family["unassembled_" + reason] += 1
                            unassembled.append(
                                {
                                    "language": language,
                                    "key": key,
                                    "reason": reason,
                                    "args": call.args,
                                }
                            )
                        elif text_command and text is not None:
                            reason = text_call_reason(call)
                            if reason in ("dynamic_operand", "possible_text_interpolation_opcode"):
                                family["assembled_despite_dynamic_prefix"] += 1
                                prefix_risks.append(
                                    {
                                        "language": language,
                                        "key": key,
                                        "reason": reason,
                                        "assembled_text": text,
                                        "args": call.args,
                                    }
                                )
                        for slot, value in slots:
                            count["call_string_slots"] += 1
                            slot_key = key + f"/arg/{slot}"
                            if indexed_text(index, slot_key, language, value):
                                count["call_slots_catalogued"] += 1
                            elif represented:
                                count["call_slots_represented_by_assembled_text"] += 1
                            else:
                                count["call_slots_not_catalogued"] += 1
                                family["slots_not_catalogued"] += 1
                                reason = (
                                    "singleton_called_sequence_alignment"
                                    if len(call_peers) < 2
                                    else "call_slot_shape_mismatch"
                                    if any(
                                        peers[l].called[ordinal].shape() != call.shape()
                                        for l in call_peers
                                    )
                                    else "catalog_missing_eligible_call_slot"
                                )
                                omitted.append([language, slot_key, reason, value])
        return {
            "logical_path_union": len(all_paths),
            "path_counts": {l: len(p) for l, p in paths.items()},
            "counts": counts,
            "command_families": {l: dict(f) for l, f in families.items()},
            "missing_paths_columns": ["language", "logical_path"],
            "missing_paths": absent,
            "parse_failures": failures,
            "omitted_slots_columns": [
                "language",
                "key",
                "reason",
                "raw_text_not_proven_display_text",
            ],
            "omitted_slots": omitted,
            "unassembled_text_calls": unassembled,
            "assembled_dynamic_prefix_risks": prefix_risks,
        }
    finally:
        for archive in archives.values():
            archive.close()


def audit_tables(game, sources, index):
    try:
        entries, build_audit = build_table_entries(game)
    except (OSError, FormatError) as exc:
        entries, build_audit = [], {"failed": True, "reason": str(exc)}
    mismatches = [
        e["key"]
        for e in entries
        if any(not indexed_text(index, e["key"], l, t) for l, t in e["texts"].items())
    ]
    # Check declared physical provenance against raw bytes, not against the
    # alignment algorithm. Aggregate membership is reported separately from
    # a directly addressable field so wrapped text does not inflate coverage.
    physical = defaultdict(list)
    for entry in entries:
        if "table_rows" not in entry:
            continue
        path_prefix = entry["key"].split("/group:")[0].split("/topic:")[0]
        field = entry["key"].rsplit("/", 1)[-1]
        for language, rows in entry["table_rows"].items():
            if indexed_text(index, entry["key"], language, entry["texts"][language]):
                physical[(language, path_prefix, field)].append((rows, entry["texts"][language]))
    counts, unknown, candidates, failures, omitted_fields = {}, [], [], [], []
    for language in sources:
        count = Counter()
        counts[language] = count
        filename = game / "pac/steam" / _TABLE_ARCHIVES[language]
        if not filename.is_file():
            failures.append({"language": language, "reason": "missing_archive"})
            continue
        try:
            archive = FpacArchive(filename)
        except (OSError, FormatError) as exc:
            failures.append({"language": language, "reason": str(exc)})
            continue
        with archive:
            for path, actual in _logical_tables(archive).items():
                data = archive.read(actual)
                try:
                    descriptors = sections(data)
                except FormatError as exc:
                    failures.append({"language": language, "path": path, "reason": str(exc)})
                    continue
                count["files"] += 1
                floor = max(start + size * rows for _, start, size, rows in descriptors)
                occurrences = Counter()
                for section_index, (kind, start, size, rows) in enumerate(descriptors):
                    occurrence = occurrences[kind]
                    occurrences[kind] += 1
                    known = kind == "TextTableData" or kind in SCHEMAS
                    category = "recognized" if known else "unrecognized"
                    count[category + "_sections"] += 1
                    count[category + "_rows"] += rows
                    if not known:
                        unknown.append([language, path, kind, occurrence, size, rows])
                    else:
                        key_path = (
                            path
                            if section_index == 0
                            else path + "/" + kind + (f"/{occurrence}" if occurrence else "")
                        )
                        try:
                            proven = {}
                            if kind in SCHEMAS:
                                for field, offset in schema_for(path, kind).fields:
                                    for physical_rows, text in physical.get(
                                        (language, key_path, field), []
                                    ):
                                        parts = []
                                        for number in physical_rows:
                                            if not 0 <= number < rows:
                                                break
                                            pointer = struct.unpack_from(
                                                "<Q", data, start + number * size + offset
                                            )[0]
                                            if not floor <= pointer < len(data):
                                                break
                                            end = data.find(b"\0", pointer)
                                            parts.append(data[pointer:end].decode("utf-8"))
                                        if (
                                            len(parts) == len(physical_rows)
                                            and "\n".join(parts) == text
                                        ):
                                            for number, part in zip(physical_rows, parts):
                                                token = (number, field, part)
                                                direct = len(parts) == 1
                                                proven[token] = proven.get(token, False) or direct
                            if kind == "TextTableData":
                                raw_fields = [
                                    (
                                        key_path + "/" + identity,
                                        text,
                                        "table_key_not_in_catalog",
                                        None,
                                    )
                                    for identity, text in _text_rows(data).items()
                                ]
                            else:
                                groups = read_section(
                                    data,
                                    (kind, start, size, rows),
                                    schema_for(path, kind),
                                    floor,
                                    stable_row_identity=path == "table/t_notemenu.tbl"
                                    and kind == "NoteMainHistory",
                                )
                                numbers = defaultdict(list)
                                for number in range(rows):
                                    identity = (
                                        f"row:{number}"
                                        if path == "table/t_notemenu.tbl"
                                        and kind == "NoteMainHistory"
                                        else record_identity(
                                            data,
                                            start + number * size,
                                            kind,
                                            schema_for(path, kind),
                                            floor,
                                        )
                                    )
                                    numbers[identity].append(number)
                                raw_fields = []
                                for identity, records in groups.items():
                                    conflicting = len(records) > 1 and any(
                                        record != records[0] for record in records
                                    )
                                    reason = (
                                        "ambiguous_duplicate_identity"
                                        if conflicting
                                        else "table_field_not_in_catalog"
                                    )
                                    for number, record in zip(numbers[identity], records):
                                        raw_fields.extend(
                                            (
                                                f"{key_path}/{identity}/{field}",
                                                value,
                                                reason,
                                                number,
                                            )
                                            for field, value in record.items()
                                        )
                            for field_key, value, reason, number in raw_fields:
                                count["schema_field_occurrences"] += 1
                                if indexed_text(index, field_key, language, value):
                                    count["schema_fields_catalogued"] += 1
                                elif (number, field_key.rsplit("/", 1)[-1], value) in proven:
                                    count["schema_fields_catalogued"] += 1
                                    direct = proven[(number, field_key.rsplit("/", 1)[-1], value)]
                                    count[
                                        "ordered_fields_direct"
                                        if direct
                                        else "ordered_fields_aggregate_only"
                                    ] += 1
                                else:
                                    count["schema_fields_not_catalogued"] += 1
                                    omitted_fields.append([language, field_key, reason, value])
                        except FormatError as exc:
                            failures.append(
                                {
                                    "language": language,
                                    "path": path,
                                    "class": kind,
                                    "reason": str(exc),
                                }
                            )
                    allowed = (
                        {0, 8}
                        if kind == "TextTableData"
                        else {o for _, o in schema_for(path, kind).fields}
                        if known
                        else set()
                    )
                    # Heuristic leads only. An integer can resemble a pointer;
                    # arrays/debug strings are not translatable field contracts.
                    for row in range(rows):
                        for offset in range(0, size - 7, 8):
                            if offset in allowed:
                                continue
                            pointer = struct.unpack_from("<Q", data, start + row * size + offset)[0]
                            if not floor <= pointer < len(data) or (
                                pointer > floor and data[pointer - 1] != 0
                            ):
                                continue
                            end = data.find(b"\0", pointer)
                            if not pointer < end <= pointer + 10000:
                                continue
                            try:
                                value = data[pointer:end].decode("utf-8")
                            except UnicodeDecodeError:
                                continue
                            if not re.search(
                                r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]|[A-Za-z].*\s[A-Za-z]",
                                value,
                            ) or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
                                continue
                            count["unclassified_pointer_candidates"] += 1
                            candidates.append(
                                [language, path, kind, occurrence, row, offset, value]
                            )
    return {
        "counts": counts,
        "build_audit": build_audit,
        "fresh_build_catalog_mismatches": mismatches,
        "parse_failures": failures,
        "omitted_fields_columns": ["language", "key", "reason", "text"],
        "omitted_fields": omitted_fields,
        "unrecognized_sections_columns": [
            "language",
            "path",
            "class",
            "occurrence",
            "stride",
            "rows",
        ],
        "unrecognized_sections": unknown,
        "pointer_candidate_warning": "Unclassified heuristic leads, not proof of display text or locale alignment; includes unused/debug strings and arrays.",
        "pointer_candidates_columns": [
            "language",
            "path",
            "class",
            "occurrence",
            "row",
            "offset",
            "text",
        ],
        "pointer_candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("generated/catalog.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source", "--source-language", choices=("all", *LANGUAGES), nargs="+", default=["all"]
    )
    args = parser.parse_args()
    game = args.game.resolve()
    if args.output.resolve().is_relative_to(game):
        parser.error("Audit output must be outside the game directory")
    sources = list(LANGUAGES) if "all" in args.source else list(dict.fromkeys(args.source))
    raw = args.catalog.read_bytes()
    entries = json.loads(raw)["entries"]
    stamp = {
        "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "extractor_sha256": hashlib.sha256(Path(resources.__file__).read_bytes()).hexdigest(),
        "code_sha256": {
            name: hashlib.sha256((Path(resources.__file__).parent / name).read_bytes()).hexdigest()
            for name in ("resources.py", "tables.py", "menu_tables.py")
        },
        "audit_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    stamp["resource_files"] = [
        {"name": path.name, "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}
        for name in (*_ARCHIVES.values(), *_TABLE_ARCHIVES.values())
        if (path := game / "pac/steam" / name).is_file()
    ]
    del raw
    index, categories, gaps = catalog_inventory(entries)
    total = len(entries)
    del entries
    scripts = audit_scripts(game, sources, index)
    tables = audit_tables(game, sources, index)
    summary = {
        "catalog_entries": total,
        "catalog_categories": categories,
        "script_logical_path_union": scripts["logical_path_union"],
        "script_counts": scripts["counts"],
        "script_parse_failures": len(scripts["parse_failures"]),
        "script_omitted_slots": len(scripts["omitted_slots"]),
        "unassembled_text_calls_by_reason": dict(
            Counter(e["reason"] for e in scripts["unassembled_text_calls"])
        ),
        "assembled_dynamic_prefix_risks": len(scripts["assembled_dynamic_prefix_risks"]),
        "table_counts": tables["counts"],
        "table_build_catalog_mismatches": len(tables["fresh_build_catalog_mismatches"]),
        "table_parse_failures": len(tables["parse_failures"]),
        "runtime_observation": "not_measured; no attachment, control, or process reads",
    }
    report = {
        "scope": "all requested source-locale PAC string slots and table sections; raw strings are not a screen-untranslated denominator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_languages": sources,
        "game_started": False,
        "game_attached": False,
        **stamp,
        "summary": summary,
        "catalog_locale_gaps_columns": ["key", "absent_locales", "present_but_blank_locales"],
        "catalog_locale_gaps": gaps,
        "scripts": scripts,
        "tables": tables,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, separators=(",", ":"))
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps({**stamp, **summary}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
