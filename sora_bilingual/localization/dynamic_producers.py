"""Compile the narrowly verified dynamic script producers into catalog entries.

The PAC parser intentionally leaves dynamic display operations out of the
ordinary literal catalog. This module adds separately audited
families.  It never infers a producer from a phrase, a screenshot, or a
generic printf field: every entry comes from a named function, a fixed called
record, and the corresponding raw table row.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Iterable

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.resources import (
    FpacArchive,
    FormatError,
    Script,
    PANEL_FLAGS,
    _logical_script_entries,
    parse_scp,
)
from sora_bilingual.localization.tables import _logical_tables


_SYSTEM_PATH = "script/scena/system.dat"
_RECIPE_MIN_ID = 2100
_RECIPE_MAX_ID = 2316
# The five raw item classes occupying the complete recipe block in t_item.tbl.
# They cover normal, bad, special, and alternate cooking results.  The regular
# medicine/ingredient classes are deliberately outside this finite domain.
_RECIPE_ITEM_CLASSES = frozenset((656129, 721665, 787457, 852993, 1253377))
# The native item/recipe builders choose the display icon from the runtime item
# record.  Keep the icon number as a typed producer slot: it is not a fixed
# resource constant (for example, food and fishing-rod notifications use
# different icon IDs).
_ITEM_RENDER = "<C0><I%d></C><C5>{name}</C>"
_ITEM_SINGLE_CALLEES = frozenset(("ITEM_ADD_MESSAGE_EV", "ITEM_ADD_MESSAGE_TK"))
_ITEM_SPLIT_CALLEES = frozenset(("ITEM_ADD_MESSAGE2_EV", "ITEM_ADD_MESSAGE2_TK"))
_ITEM_CALLEES = _ITEM_SINGLE_CALLEES | _ITEM_SPLIT_CALLEES


def _popup_lines(call):
    """Preserve complete literal lines around typed item insertions.

    A color literal split across arguments is still one line. An item opcode
    consumes its operand and invalidates only its own line, never the preceding
    complete line. Unknown opcodes reject the contract rather than guessing an
    operand width. The normalized shape keeps every non-text argument.
    """
    if (
        call.kind != 3
        or call.args[:2] != (("int", 5), ("int", 8))
        or len(call.args) < 4
        or call.args[2][0] != "int"
    ):
        return None
    shape, lines, text, dynamic, has_item = list(call.args[:3]), [], [], False, False
    i = 3
    while i < len(call.args):
        kind, value = call.args[i]
        if kind == "string":
            if not shape or shape[-1] != ("string", None):
                shape.append(("string", None))
            text.append(str(value))
        elif kind == "int" and value == 10:
            shape.append((kind, value))
            lines.append(None if dynamic else "".join(text))
            text, dynamic = [], False
        elif kind == "int" and value in PANEL_FLAGS:
            shape.append((kind, value))
        elif kind == "int" and value in (11, 12, 17):
            if i + 1 >= len(call.args) or call.args[i + 1][0] != "int":
                return None
            shape.extend(call.args[i : i + 2])
            i += 1
            if value == 17:
                dynamic = True
                has_item = True
        else:
            return None
        i += 1
    lines.append(None if dynamic else "".join(text))
    return (tuple(shape), tuple(lines)) if has_item else None


def _popup_line_entries(scripts, audit):
    buckets = defaultdict(dict)
    origins = defaultdict(dict)
    for language, paths in scripts.items():
        for path, script in paths.items():
            for function, body in script.functions.items():
                decoded = [_popup_lines(call) for call in body.called]
                if not any(decoded):
                    continue
                shape = tuple(
                    (call.target, call.kind, value[0]) if value else call.shape()
                    for call, value in zip(body.called, decoded)
                )
                signature = hashlib.sha256(repr(shape).encode()).hexdigest()
                call_shapes = [
                    (call.target, call.kind, value[0]) if value else None
                    for call, value in zip(body.called, decoded)
                ]
                counts = Counter(s for s in call_shapes if s is not None)
                for called, value in enumerate(decoded):
                    if value is None:
                        continue
                    audit["counters"]["popup_item_calls"] += 1
                    # A unique item/control stream identifies this popup even
                    # if unrelated calls differ between localized functions.
                    # Repeated streams still require the full function shape
                    # and physical call index; never align by translated text.
                    call_shape = call_shapes[called]
                    identity = (
                        "unique/" + hashlib.sha256(repr(call_shape).encode()).hexdigest()
                        if counts[call_shape] == 1
                        else f"called/{called}/{signature}"
                    )
                    # A visual newline is not a translation boundary. Keep
                    # consecutive static lines together: localized sentences
                    # may distribute their words differently across those lines.
                    start, block = 0, []
                    for line, text in enumerate((*value[1], None)):
                        if text is not None:
                            if not block:
                                start = line
                            block.append(text)
                            continue
                        if block and any(t.strip() for t in block):
                            key = (path, function, identity, start)
                            buckets[key][language] = "\n".join(block)
                            origins[key][language] = called
                        block = []
                        if line < len(value[1]):
                            audit["counters"]["popup_dynamic_lines"] += 1
    result = []
    for key, texts in sorted(buckets.items()):
        path, function, identity, line = key
        audit["counters"]["popup_literal_lines"] += 1
        result.append(
            {
                "key": f"popup/{path}/{function}/{identity}/line/{line}",
                "texts": texts,
                "display_role": "popup_line",
                "popup_origin": {
                    "path": path,
                    "function": function,
                    "calls_by_language": origins[key],
                    "line": line,
                },
            }
        )
    return result


def _audit(reason: str, **detail: object) -> dict[str, object]:
    return {"reason": reason, **detail}


def _read_scripts(game: Path, audit: dict[str, object]) -> dict[str, dict[str, Script]]:
    """Return parsed logical scripts by locale and record every unavailable input."""
    result: dict[str, dict[str, Script]] = {}
    diagnostics = audit["diagnostics"]
    assert isinstance(diagnostics, list)
    for language, archive_name in archive_names("script").items():
        path = game / "pac" / "steam" / archive_name
        if not path.is_file():
            diagnostics.append(_audit("missing_script_archive", language=language))
            continue
        try:
            with FpacArchive(path) as archive:
                scripts: dict[str, Script] = {}
                for logical, actual in _logical_script_entries(archive).items():
                    if not logical.endswith(".dat"):
                        continue
                    try:
                        scripts[logical] = parse_scp(archive.read(actual))
                    except FormatError as exc:
                        diagnostics.append(
                            _audit(
                                "invalid_script", language=language, path=logical, detail=str(exc)
                            )
                        )
                result[language] = scripts
        except FormatError as exc:
            diagnostics.append(_audit("invalid_script_archive", language=language, detail=str(exc)))
    return result


def _read_item_rows(game: Path, audit: dict[str, object]) -> dict[str, dict[int, tuple[str, int]]]:
    """Read the stable item ID, display name and raw class directly from t_item."""
    result: dict[str, dict[int, tuple[str, int]]] = {}
    diagnostics = audit["diagnostics"]
    assert isinstance(diagnostics, list)
    for language, archive_name in archive_names("table").items():
        archive_path = game / "pac" / "steam" / archive_name
        if not archive_path.is_file():
            diagnostics.append(_audit("missing_table_archive", language=language))
            continue
        try:
            with FpacArchive(archive_path) as archive:
                logical = _logical_tables(archive)
                actual = logical.get("table/t_item.tbl")
                if actual is None:
                    diagnostics.append(_audit("missing_item_table", language=language))
                    continue
                data = archive.read(actual)
                candidates = [
                    section for section in sections(data) if section[0] == "ItemTableData"
                ]
                if len(candidates) != 1:
                    diagnostics.append(
                        _audit("item_table_schema", language=language, sections=len(candidates))
                    )
                    continue
                _kind, start, size, count = candidates[0]
                if size != 256 or count > 8192 or start + size * count > len(data):
                    diagnostics.append(
                        _audit("item_table_schema", language=language, size=size, count=count)
                    )
                    continue
                rows: dict[int, tuple[str, int]] = {}
                for index in range(count):
                    at = start + index * size
                    item_id = struct.unpack_from("<I", data, at)[0]
                    item_class = struct.unpack_from("<I", data, at + 40)[0]
                    name_at = struct.unpack_from("<Q", data, at + 224)[0]
                    if not item_id or name_at >= len(data):
                        raise FormatError("invalid item ID or name pointer")
                    end = data.find(b"\0", name_at)
                    if end < 0:
                        raise FormatError("unterminated item name")
                    try:
                        name = data[name_at:end].decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise FormatError("invalid item name") from exc
                    if not name or item_id in rows:
                        raise FormatError("empty or duplicate item name")
                    rows[item_id] = (name, item_class)
                result[language] = rows
        except FormatError as exc:
            diagnostics.append(_audit("invalid_item_table", language=language, detail=str(exc)))
    return result


def _panel_template(call: object, *, allowed_opcodes: frozenset[int]) -> tuple[str, int] | None:
    """Decode one command-8 producer with exactly one typed runtime slot."""
    args = getattr(call, "args", ())
    if getattr(call, "kind", None) != 3 or len(args) < 7:
        return None
    if args[:4] != (("int", 5), ("int", 8), ("int", 65535), ("int", 16)):
        return None
    slot_positions = [
        index
        for index in range(4, len(args) - 1)
        if args[index][0] == "int" and args[index][1] in allowed_opcodes
    ]
    if len(slot_positions) != 1:
        return None
    slot = slot_positions[0]
    if args[slot + 1] != ("var", None):
        return None
    pieces: list[str] = []
    for index, (kind, value) in enumerate(args[4:]):
        actual = index + 4
        if actual == slot:
            pieces.append("%d")
        elif actual == slot + 1:
            continue
        elif kind == "string" and isinstance(value, str):
            if "%" in value:
                return None
            pieces.append(value)
        else:
            return None
    return "".join(pieces), int(args[slot][1])


def _emit_numeric(
    scripts: dict[str, dict[str, Script]],
    audit: dict[str, object],
    *,
    family: str,
    function: str,
    called: int,
    allowed_opcodes: frozenset[int],
) -> list[dict[str, object]]:
    templates: dict[str, str] = {}
    opcodes: dict[str, int] = {}
    for language in LANGUAGES:
        call = scripts.get(language, {}).get(_SYSTEM_PATH, Script({})).functions.get(function)
        candidate = call.called[called] if call is not None and len(call.called) > called else None
        decoded = _panel_template(candidate, allowed_opcodes=allowed_opcodes) if candidate else None
        if decoded is None:
            audit["diagnostics"].append(
                _audit(
                    "producer_rejected",
                    family=family,
                    language=language,
                    path=_SYSTEM_PATH,
                    function=function,
                    called=called,
                )
            )
            continue
        templates[language], opcodes[language] = decoded
    missing = sorted(set(LANGUAGES) - set(templates))
    if missing:
        audit["diagnostics"].append(
            _audit("producer_missing_locales", family=family, missing=missing)
        )
    if len(templates) < 2:
        audit["counters"]["numeric_incomplete"] += 1
        return []
    numbers = {
        language: ["fullwidth" if opcode == 23 else "ascii"] for language, opcode in opcodes.items()
    }
    return [
        {
            "key": f"dynamic/{_SYSTEM_PATH}/{function}/called/{called}",
            "texts": templates,
            "dynamic_producer": {
                "family": family,
                "numbers": numbers,
                "slots": [{"kind": "integer", "opcodes": opcodes}],
                "signature": {
                    "path": _SYSTEM_PATH,
                    "function": function,
                    "called": called,
                    "kind": 3,
                    "command": 8,
                },
            },
        }
    ]


def _read_book_ids(game: Path, audit: dict[str, object]) -> dict[str, set[int]]:
    """BooksTitle+0x10 is the item ID sent to OnBooksNoteClose argument 3.

    The native sender at 0x428e46 reads a uint16, then 0x428ef7..0x428f02
    tags it as an integer. RegisterBook forwards that argument to opcode 17.
    Zero means no associated inventory item (e.g. encyclopedia entries).
    """
    result = {}
    for language, archive_name in archive_names("table").items():
        try:
            with FpacArchive(game / "pac" / "steam" / archive_name) as archive:
                data = archive.read(_logical_tables(archive)["table/t_books.tbl"])
            section = [row for row in sections(data) if row[0] == "BooksTitle"]
            if len(section) != 1 or section[0][2] != 24:
                raise FormatError("unexpected BooksTitle layout")
            _, start, size, count = section[0]
            if start + size * count > len(data):
                raise FormatError("BooksTitle outside table")
            result[language] = {
                item_id
                for i in range(count)
                if (item_id := struct.unpack_from("<H", data, start + size * i + 16)[0])
            }
        except (OSError, KeyError, FormatError) as exc:
            audit["diagnostics"].append(
                _audit("book_domain_unavailable", language=language, detail=str(exc))
            )
    return result


def _item_template_entries(
    scripts: dict[str, dict[str, Script]],
    item_rows: dict[str, dict[int, tuple[str, int]]],
    audit: dict[str, object],
    *,
    family: str,
    function_name: str,
    item_ids_by_locale: dict[str, set[int]],
) -> list[dict[str, object]]:
    templates: dict[str, str] = {}
    for language in LANGUAGES:
        function = (
            scripts.get(language, {}).get(_SYSTEM_PATH, Script({})).functions.get(function_name)
        )
        call = function.called[2] if function is not None and len(function.called) > 2 else None
        decoded = _panel_template(call, allowed_opcodes=frozenset((17,))) if call else None
        if decoded is None or decoded[1] != 17:
            audit["diagnostics"].append(
                _audit("producer_rejected", family=family, language=language)
            )
            continue
        templates[language] = decoded[0]
    template_missing = sorted(set(LANGUAGES) - set(templates))
    if template_missing:
        audit["diagnostics"].append(
            _audit("producer_missing_locales", family=family, missing=template_missing)
        )
    if len(templates) < 2:
        audit["counters"][family + "_incomplete"] += 1
        return []
    item_ids = set().union(*item_ids_by_locale.values()) if item_ids_by_locale else set()
    result = []
    for item_id in sorted(item_ids):
        rows = {
            language: item_rows[language][item_id]
            for language in templates
            if item_id in item_rows.get(language, {})
            and item_id in item_ids_by_locale.get(language, ())
        }
        if len(rows) < 2:
            audit["counters"][family + "_items_without_pair"] += 1
            audit["diagnostics"].append(
                _audit(
                    "producer_item_without_pair",
                    family=family,
                    item_id=item_id,
                    missing=sorted(set(templates) - set(rows)),
                )
            )
            continue
        texts = {
            language: templates[language].replace("%d", _ITEM_RENDER.format(name=rows[language][0]))
            for language in rows
        }
        missing = sorted(set(LANGUAGES) - set(texts))
        if missing:
            audit["diagnostics"].append(
                _audit(
                    "producer_item_missing_locales", family=family, item_id=item_id, missing=missing
                )
            )
        result.append(
            {
                "key": f"dynamic/{_SYSTEM_PATH}/{function_name}/item/{item_id}",
                "texts": texts,
                "producer_origin": {
                    "family": family,
                    "item_id": item_id,
                    "signature": {
                        "path": _SYSTEM_PATH,
                        "function": function_name,
                        "called": 2,
                        "kind": 3,
                        "command": 8,
                        "opcode": 17,
                    },
                },
                "dynamic_producer": {
                    "family": family,
                    "dynamic_icon": True,
                    "numbers": {language: ["ascii"] for language in texts},
                    "slots": [{"kind": "icon", "opcode": 17}],
                },
            }
        )
    audit["counters"][family + "_items_emitted"] += len(result)
    return result


def _item_call_parts(call: object) -> tuple[int, str, str, tuple[int, ...]] | None:
    """Accept only the two documented item-message arities and static tail modes."""
    if getattr(call, "kind", None) != 0 or getattr(call, "target", None) not in _ITEM_CALLEES:
        return None
    args = getattr(call, "args", ())
    if not args or args[0][0] != "int" or not isinstance(args[0][1], int) or args[0][1] <= 0:
        return None
    if call.target in _ITEM_SINGLE_CALLEES:
        if len(args) not in (2, 3) or args[1][0] != "string":
            return None
        if len(args) == 3 and (
            args[2][0] != "int" or not isinstance(args[2][1], int) or not 0 <= args[2][1] <= 3
        ):
            return None
        return int(args[0][1]), "", str(args[1][1]), (() if len(args) == 2 else (int(args[2][1]),))
    if len(args) not in (3, 4) or args[1][0] != "string" or args[2][0] != "string":
        return None
    if len(args) == 4 and (
        args[3][0] != "int" or not isinstance(args[3][1], int) or not 0 <= args[3][1] <= 3
    ):
        return None
    return (
        int(args[0][1]),
        str(args[1][1]),
        str(args[2][1]),
        (() if len(args) == 3 else (int(args[3][1]),)),
    )


def _item_entries(
    scripts: dict[str, dict[str, Script]],
    item_rows: dict[str, dict[int, tuple[str, int]]],
    audit: dict[str, object],
) -> list[dict[str, object]]:
    identities = set().union(*(paths.keys() for paths in scripts.values()))
    emitted: list[dict[str, object]] = []
    for path in sorted(identities):
        names = set().union(
            *(script.get(path, Script({})).functions.keys() for script in scripts.values())
        )
        for function_name in sorted(names):
            functions = [
                script.get(path, Script({})).functions.get(function_name)
                for script in scripts.values()
            ]
            max_called = max(
                (len(function.called) if function is not None else 0 for function in functions),
                default=0,
            )
            for called in range(max_called):
                parts: dict[str, tuple[int, str, str, tuple[int, ...]]] = {}
                saw_item_callee = False
                rejected_languages = []
                for language in LANGUAGES:
                    function = (
                        scripts.get(language, {}).get(path, Script({})).functions.get(function_name)
                    )
                    call = (
                        function.called[called]
                        if function is not None and len(function.called) > called
                        else None
                    )
                    saw_item_callee = (
                        saw_item_callee or getattr(call, "target", None) in _ITEM_CALLEES
                    )
                    candidate = _item_call_parts(call) if call is not None else None
                    if candidate is None:
                        rejected_languages.append(language)
                        continue
                    parts[language] = candidate
                if saw_item_callee and rejected_languages:
                    audit["diagnostics"].append(
                        _audit(
                            "item_message_rejected",
                            path=path,
                            function=function_name,
                            called=called,
                            languages=rejected_languages,
                        )
                    )
                if len(parts) < 2:
                    if saw_item_callee:
                        audit["counters"]["item_message_without_pair"] += 1
                    continue
                item_ids = {value[0] for value in parts.values()}
                if len(item_ids) != 1:
                    audit["diagnostics"].append(
                        _audit(
                            "item_message_item_id_conflict",
                            path=path,
                            function=function_name,
                            called=called,
                            item_ids=sorted(item_ids),
                        )
                    )
                    continue
                item_id = next(iter(item_ids))
                parts = {
                    language: value
                    for language, value in parts.items()
                    if item_id in item_rows.get(language, {})
                }
                if len(parts) < 2:
                    audit["counters"]["item_message_without_pair"] += 1
                    audit["diagnostics"].append(
                        _audit(
                            "item_message_without_pair",
                            path=path,
                            function=function_name,
                            called=called,
                            item_id=item_id,
                        )
                    )
                    continue
                texts = {
                    language: prefix
                    + _ITEM_RENDER.format(name=item_rows[language][item_id][0])
                    + suffix
                    for language, (_id, prefix, suffix, _mode) in parts.items()
                }
                missing = sorted(set(LANGUAGES) - set(texts))
                if missing:
                    audit["diagnostics"].append(
                        _audit(
                            "item_message_missing_locales",
                            path=path,
                            function=function_name,
                            called=called,
                            missing=missing,
                        )
                    )
                emitted.append(
                    {
                        "key": f"dynamic/{path}/{function_name}/called/{called}/item/{item_id}",
                        "texts": texts,
                        "producer_origin": {
                            "family": "item_add_message",
                            "item_id": item_id,
                            "signature": {
                                "path": path,
                                "function": function_name,
                                "called": called,
                            },
                        },
                        "dynamic_producer": {
                            "family": "item_add_message",
                            "dynamic_icon": True,
                            "numbers": {language: ["ascii"] for language in texts},
                            "slots": [{"kind": "icon", "markup": "<I%d>"}],
                        },
                    }
                )
    audit["counters"]["item_message_calls_emitted"] += len(emitted)
    return emitted


def _audit_source_conflicts(
    entries: Iterable[dict[str, object]], audit: dict[str, object]
) -> list[dict[str, object]]:
    """Record source-locale conflicts without erasing other exact language pairs.

    A source string can be ambiguous in one locale while a different source
    locale on the same resource record remains exact.  Pair admission belongs
    to the resolver, which knows the selected source/primary/secondary tuple;
    removing an eight-language record here would incorrectly weaken that pair.
    """
    claims: dict[tuple[str, str], set[tuple[tuple[str, str], ...]]] = defaultdict(set)
    records = list(entries)
    for entry in records:
        texts = entry["texts"]
        assert isinstance(texts, dict)
        identity = tuple(sorted((str(language), str(text)) for language, text in texts.items()))
        for language, source in texts.items():
            claims[(str(language), str(source))].add(identity)
    conflicts = {key for key, values in claims.items() if len(values) > 1}
    if not conflicts:
        return records
    audit["counters"]["dynamic_source_conflicts"] += len(conflicts)
    audit["diagnostics"].extend(
        _audit("dynamic_source_conflict", language=language, source=source)
        for language, source in sorted(conflicts)
    )
    return records


def build_dynamic_entries(
    game: str | Path, entries: Iterable[dict[str, object]]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build dynamic entries from raw PAC/table contracts without writing the game.

    ``entries`` is accepted for the catalog-builder API symmetry.  Dynamic
    resource evidence is deliberately read from PAC/table inputs, never from
    already accepted catalog entries.
    """
    del entries
    audit: dict[str, object] = {
        "version": 1,
        "languages": list(LANGUAGES),
        "counters": Counter(),
        "diagnostics": [],
    }
    scripts = _read_scripts(Path(game), audit)
    items = _read_item_rows(Path(game), audit)
    result: list[dict[str, object]] = []
    result += _emit_numeric(
        scripts,
        audit,
        family="on_quest_add_bp",
        function="OnQuestAddBP",
        called=3,
        allowed_opcodes=frozenset((18,)),
    )
    result += _emit_numeric(
        scripts,
        audit,
        family="rest_shop_process",
        function="RestShopProcess",
        called=3,
        allowed_opcodes=frozenset((18, 23)),
    )
    result += _item_template_entries(
        scripts,
        items,
        audit,
        family="unlock_recipe",
        function_name="UnLockRecipe",
        item_ids_by_locale={
            language: {
                item_id
                for item_id, (_, item_class) in rows.items()
                if _RECIPE_MIN_ID <= item_id <= _RECIPE_MAX_ID
                and item_class in _RECIPE_ITEM_CLASSES
            }
            for language, rows in items.items()
        },
    )
    result += _item_template_entries(
        scripts,
        items,
        audit,
        family="register_book",
        function_name="RegisterBook",
        item_ids_by_locale=_read_book_ids(Path(game), audit),
    )
    result += _item_entries(scripts, items, audit)
    result += _popup_line_entries(scripts, audit)
    result = _audit_source_conflicts(result, audit)
    audit["counters"] = dict(sorted(audit["counters"].items()))
    return result, audit
