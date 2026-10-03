"""Compile verified dynamic item-notification call identities.

A dynamic notification may have equal displayed source bytes at distinct SCP
call sites.  This compiler follows the actual helper stack program and keeps
the resolved command-8 raw tokens as the identity.  It deliberately admits no
helper whose forwarding bytecode or outer local-call frame differs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import struct
from typing import Any, Iterable

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.dynamic_producers import _ITEM_CALLEES
from sora_bilingual.localization.resources import (
    FpacArchive,
    FormatError,
    _FUNCTION,
    _SCP_HEADER,
    _logical_script_entries,
    _parse_code,
    _string_value,
    parse_scp,
)


_HELPER_SHAPE = (
    ("slot", 2, 3),
    ("slot", 2, 2),
    ("push", "int", 17),
    ("slot", 2, 5),
    ("push", "int", 16),
    ("push", "int", 65535),
    ("system-call", 5, 8, 6),
)
_SUFFIX_HELPER_SHAPE = (
    ("slot", 2, 2),
    ("slot", 2, 2),
    ("push", "int", 17),
    ("push", "int", 16),
    ("push", "int", 65535),
    ("system-call", 5, 8, 5),
)


def _function_code(data: bytes, function_name: str) -> tuple[list[int], list[tuple[Any, ...]]]:
    """Return raw instruction positions alongside one function's parsed code."""
    _magic, start, count, global_start, global_count, _reserved = _SCP_HEADER.unpack_from(data)
    names = tuple(_string_value(data, start + number * 32 + 28) for number in range(count))
    globals_ = tuple(
        _string_value(data, global_start + number * 8) for number in range(global_count)
    )
    number = names.index(function_name)
    code_at = _FUNCTION.unpack_from(data, start + number * 32)[0]
    starts = sorted(_FUNCTION.unpack_from(data, start + index * 32)[0] for index in range(count))
    end = next((value for value in starts if value > code_at), None)
    positions: list[int] = []
    code, _strings = _parse_code(data, code_at, end, number, names, globals_, None, positions)
    return positions, list(code)


def _push_raw(data: bytes, position: int) -> int:
    if data[position : position + 2] != b"\0\4":
        raise ValueError(f"SCP instruction at {position:#x} is not a push")
    return struct.unpack_from("<I", data, position + 2)[0]


def _called_index(code: list[tuple[Any, ...]], position: int) -> int:
    """Map an executable call instruction to its SCP called-record ordinal."""
    if code[position][0] not in ("local-call", "external-call", "system-call"):
        raise ValueError("candidate is not an executable call")
    return (
        sum(
            item[0] in ("local-call", "external-call", "system-call")
            for item in code[: position + 1]
        )
        - 1
    )


def _helper_site(data: bytes, helper: str) -> tuple[int, tuple[tuple[Any, ...], ...]]:
    positions, code = _function_code(data, helper)
    sites = [i for i, op in enumerate(code) if op[:3] == ("system-call", 5, 8)]
    if len(sites) != 1:
        raise ValueError("helper must have exactly one command-8 forwarding site")
    system = sites[0]
    program = tuple(code[system - code[system][3] : system + 1])
    if program not in (_HELPER_SHAPE, _SUFFIX_HELPER_SHAPE):
        raise ValueError("helper command-8 forwarding shape differs")
    # opcode 36 is one byte plus group, command and argc bytes.  The VM PC is
    # advanced past these operands before the native system handler is called.
    return positions[system] + 4, program


def _resolved_tokens(
    data: bytes,
    positions: list[int],
    code: list[tuple[Any, ...]],
    call_at: int,
    argument_types: tuple[int, ...],
    program: tuple[tuple[Any, ...], ...] = _HELPER_SHAPE,
) -> list[int]:
    """Execute the helper's verified slot copies on its declared local frame."""
    if program not in (_HELPER_SHAPE, _SUFFIX_HELPER_SHAPE):
        raise ValueError("helper command-8 forwarding shape differs")
    # The declaration is in argument order; executable pushes are reversed.
    # Bit 3 marks a defaultable argument, not a different value type. Require
    # every declared argument here: omitted defaults need separate VM proof.
    kinds = {1: "int", 2: "string"}
    expected = tuple(kinds.get(kind & ~8) for kind in reversed(argument_types))
    start = call_at - len(expected) - 1
    frame = code[start : call_at + 1] if start >= 0 else []
    if (
        not expected
        or None in expected
        or len(frame) != len(expected) + 2
        or frame[0][0] != "prepare-local"
        or frame[-1][0] != "local-call"
        or tuple(item[:2] for item in frame[1:-1]) != tuple(("push", kind) for kind in expected)
    ):
        raise ValueError("outer local-call frame differs")
    # Both the three-argument TK and four-argument EV frames end in the same
    # suffix, prefix, item sequence. The unused EV style precedes it. Opcode 2 reads
    # stack[top - N*4], then increments top.  Therefore its N operand is a
    # dynamic stack offset, never a hard-coded function-argument index.
    stack = [_push_raw(data, positions[index]) for index in range(start + 1, call_at)]
    for op in program[:-1]:
        if op[0] == "slot":
            source = len(stack) - op[2]
            if source < 0 or source >= len(stack):
                raise ValueError("slot copy escapes the local call frame")
            stack.append(stack[source])
        else:
            stack.append(0x40000000 | op[2])
    return list(reversed(stack[-program[-1][3] :]))


def _record_key(entry: dict[str, Any]) -> tuple[str, str, int] | None:
    origin = entry.get("producer_origin", {})
    if origin.get("family") != "item_add_message":
        return None
    signature = origin.get("signature", {})
    path, function, called = (
        signature.get("path"),
        signature.get("function"),
        signature.get("called"),
    )
    if not isinstance(path, str) or not isinstance(function, str) or not isinstance(called, int):
        return None
    return path, function, called


def _source_called(entry: dict[str, Any], language: str, canonical: int) -> int | None:
    values = entry.get("called_ids")
    if values is None:
        return canonical
    value = values.get(language)
    return value if isinstance(value, int) and value >= 0 else None


def _producer_models(
    entry: dict[str, Any], primary: str, secondary: str
) -> dict[str, dict[str, Any]]:
    """Build one exact numeric model for each catalog source locale."""
    result: dict[str, dict[str, Any]] = {}
    for locale, source in entry.get("texts", {}).items():
        if not isinstance(source, str) or not source:
            continue
        translator = MenuTranslator([entry], primary, secondary, locale, True)
        # Catalog strings retain ``%d``; the builder emits an actual signed
        # icon value.  Zero is inside the producer's documented int32 domain
        # and is used only to prove the compiled pattern can render a full row.
        probe = source.replace("%d", "0")
        if translator.producer_pair(probe) is None or len(translator.producer_numeric) != 1:
            continue
        pattern = translator.producer_numeric[0][0].pattern
        result[locale] = {
            "model": translator.runtime_model(),
            "sourcePattern": "^(?:" + pattern + ")$",
        }
    return result


def compile_dynamic_identities(
    game: str | Path,
    entries: Iterable[dict[str, Any]],
    primary: str,
    secondary: str,
    language: str,
) -> dict[str, Any]:
    """Return source-SHA/helper/raw-token identity rows for proven item helpers.

    Rows conflict when the same executable identity claims different physical
    outer records.  Conflicts are counted and omitted; selecting an arbitrary
    same-string candidate would defeat the purpose of this index.
    """
    entries = list(entries)
    stats: Counter[str] = Counter()
    record_specs: dict[str, dict[str, dict[str, Any]]] = {}
    records: dict[str, dict[str, dict[str, Any]]] = {}
    candidates: dict[tuple[str, str, str], dict[tuple[str, int], dict[str, Any]]] = defaultdict(
        dict
    )
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        record = _record_key(entry)
        if record is None:
            continue
        models = _producer_models(entry, primary, secondary)
        if not models:
            stats["rejected_models"] += 1
            continue
        record_key = str(entry["key"])
        record_specs[record_key] = models
        records[record_key] = {locale: value["model"] for locale, value in models.items()}
        by_path[record[0]].append(entry)
        stats["catalog_records"] += 1

    archive_path = Path(game) / "pac" / "steam" / archive_names("script")[language]
    try:
        with FpacArchive(archive_path) as archive:
            logical = _logical_script_entries(archive)
            for path, selected in by_path.items():
                actual = logical.get(path)
                if actual is None:
                    stats["missing_scripts"] += len(selected)
                    continue
                data = archive.read(actual)
                digest = hashlib.sha256(data).hexdigest()
                script = parse_scp(data)
                helper_cache = {}
                code_cache: dict[str, tuple[list[int], list[tuple[Any, ...]]]] = {}
                for entry in selected:
                    path, function, canonical = _record_key(entry)  # type: ignore[misc]
                    call_id = _source_called(entry, language, canonical)
                    if call_id is None or function not in script.functions:
                        stats["missing_outer_calls"] += 1
                        continue
                    outer = script.functions[function]
                    if call_id >= len(outer.called):
                        stats["missing_outer_calls"] += 1
                        continue
                    helper = outer.called[call_id].target
                    if helper not in _ITEM_CALLEES:
                        stats["unsupported_helpers"] += 1
                        continue
                    try:
                        if helper not in helper_cache:
                            helper_cache[helper] = _helper_site(data, helper)
                        helper_pc, program = helper_cache[helper]
                        if function not in code_cache:
                            code_cache[function] = _function_code(data, function)
                        positions, code = code_cache[function]
                        call_positions = [
                            index
                            for index, instruction in enumerate(code)
                            if instruction[0] in ("local-call", "external-call", "system-call")
                        ]
                        call_at = call_positions[call_id]
                        if (
                            code[call_at] != ("local-call", helper)
                            or _called_index(code, call_at) != call_id
                        ):
                            raise ValueError("called metadata/code position mismatch")
                        tokens = _resolved_tokens(
                            data,
                            positions,
                            code,
                            call_at,
                            script.functions[helper].arg_types,
                            program,
                        )
                    except (IndexError, ValueError, FormatError) as exc:
                        stats["rejected_bytecode"] += 1
                        detail = str(exc)
                        if detail.startswith("helper"):
                            stats["rejected_helper_shape"] += 1
                        elif detail.startswith("outer") or detail.startswith("slot"):
                            stats["rejected_outer_frame"] += 1
                        elif detail.startswith("called"):
                            stats["rejected_call_alignment"] += 1
                        else:
                            stats["rejected_other_bytecode"] += 1
                        continue
                    models = record_specs[str(entry["key"])]
                    source_row = models.get(language)
                    if source_row is None:
                        stats["missing_source_model"] += 1
                        continue
                    token = ",".join(str(value) for value in tokens)
                    row = {
                        "recordKey": str(entry["key"]),
                        "callId": call_id,
                        "model": source_row["model"],
                        "sourcePattern": source_row["sourcePattern"],
                        "pc": helper_pc,
                        "sha256": digest,
                    }
                    candidates[digest, helper, token][str(entry["key"]), call_id] = row
                    stats["resolved_candidates"] += 1
    except OSError, FormatError, KeyError, ValueError:
        stats["invalid_archive"] += 1

    scripts: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    emitted_records = set()
    for (digest, helper, token), claims in candidates.items():
        if len(claims) != 1:
            stats["conflicting_tokens"] += 1
            continue
        row = next(iter(claims.values()))
        scripts.setdefault(digest, {}).setdefault(helper, {})[token] = row
        emitted_records.add(row["recordKey"])
        stats["emitted"] += 1
    records = {key: value for key, value in records.items() if key in emitted_records}
    stats["records"] = len(records)
    for key in (
        "conflicting_tokens",
        "missing_scripts",
        "missing_outer_calls",
        "unsupported_helpers",
        "rejected_bytecode",
        "rejected_helper_shape",
        "rejected_outer_frame",
        "rejected_call_alignment",
        "rejected_other_bytecode",
    ):
        stats.setdefault(key, 0)
    return {"scripts": scripts, "records": records, "stats": dict(stats)}
