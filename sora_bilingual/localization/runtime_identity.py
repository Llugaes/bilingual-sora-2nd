"""Compile SCP call identities without changing any game resource.

The VM keeps encoded arguments (including string-pool offsets), not just the
displayed string. Equal Chinese text in different calls can therefore retain
its own localisation key. Every candidate is still checked against the exact
source before use; duplicate identities with different translations are denied.
"""

import struct
import hashlib
from collections import defaultdict
from pathlib import Path

from sora_bilingual.localization.resources import (
    FpacArchive,
    _ARCHIVES,
    _logical_script_entries,
    _utf8z,
    _parse_code,
)
from sora_bilingual.localization.menu_text import MenuTranslator, complete_pair, needs_annotation


def script_signature(data):
    if data[:4] != b"#scp" or len(data) < 24:
        raise ValueError("Invalid script identity header")
    start, count = struct.unpack_from("<II", data, 4)
    if not 0 < count <= 65536 or start < 24 or start + count * 32 > len(data):
        raise ValueError("Invalid script function range")
    return (
        data[:24] + data[start : start + 32] + data[start + (count - 1) * 32 : start + count * 32]
    ).hex()


def compile_script_identities(game, entries, primary, secondary, language, *, resolved_pairs=None):
    """Index only functions needed to disambiguate the global source model."""
    if resolved_pairs is None:
        resolved_pairs = MenuTranslator(entries, primary, secondary, language).pairs
    # Use the same admission result as rendering. Comparing only raw duplicate
    # strings misses conflicts introduced by colour/size normalization.
    candidates = defaultdict(set)
    for e in entries:
        t = e["texts"]
        if t.get(language, "").strip():
            pair = complete_pair(t, primary, secondary)
            candidates[t[language]].add(pair)
    ambiguous = {
        s
        for s, pairs in candidates.items()
        if any(
            pair and needs_annotation(*pair) and tuple(resolved_pairs.get(s, ())) != pair
            for pair in pairs
        )
    }
    functions = defaultdict(list)
    needed = set()
    for e in entries:
        key = e.get("key", "")
        if not key.startswith("script/") or ".dat/" not in key:
            continue
        path, rest = key.split(".dat/", 1)
        fn = rest.split("/", 1)[0]
        identity = (path + ".dat", fn)
        functions[identity].append(e)
        if e["texts"].get(language) in ambiguous:
            needed.add(identity)
    paths = {path for path, _ in needed}
    result = {}
    stats = defaultdict(int)
    pointers = defaultdict(list)
    pointer_models = {}
    blocked_functions = set()
    archive = FpacArchive(Path(game) / "pac/steam" / _ARCHIVES[language])
    try:
        logical = _logical_script_entries(archive)
        for path in sorted(paths):
            data = archive.read(logical[path])
            signature = script_signature(data)
            digest = hashlib.sha256(data).hexdigest()
            start, count = struct.unpack_from("<II", data, 4)
            names = tuple(
                _utf8z(data, struct.unpack_from("<I", data, start + n * 32 + 28)[0] & 0x3FFFFFFF)
                for n in range(count)
            )
            global_at, global_count = struct.unpack_from("<II", data, 12)
            globals_ = tuple(
                _utf8z(data, struct.unpack_from("<I", data, global_at + n * 8)[0] & 0x3FFFFFFF)
                for n in range(global_count)
            )
            code_starts = sorted(
                struct.unpack_from("<I", data, start + n * 32)[0] for n in range(count)
            )
            bucket = result.setdefault(signature, [])
            script = next((v for v in bucket if v["sha256"] == digest), None)
            if script is None:
                script = {"size": len(data), "sha256": digest, "paths": [], "functions": {}}
                bucket.append(script)
            script["paths"].append(path)
            for number in range(count):
                at = start + number * 32
                name = _utf8z(data, struct.unpack_from("<I", data, at + 28)[0] & 0x3FFFFFFF)
                if (path, name) not in needed:
                    continue
                selected = functions[path, name]
                code_offsets = None
                for entry in selected:
                    source = entry["texts"].get(language)
                    if source not in ambiguous or not complete_pair(
                        entry["texts"], primary, secondary
                    ):
                        continue
                    suffix = (
                        entry["key"].split("/alignment/", 1)[0].split(".dat/", 1)[1].split("/")[1:]
                    )
                    offset = None
                    if len(suffix) == 4 and suffix[0] == "called" and suffix[2] == "arg":
                        call_at = struct.unpack_from("<I", data, at + 20)[0] + int(suffix[1]) * 12
                        argc, args_at = struct.unpack_from("<HI", data, call_at + 6)
                        slot = int(suffix[3])
                        if slot < argc:
                            v, k = struct.unpack_from("<II", data, args_at + slot * 8)
                            if k == 0 and v >> 30 == 3:
                                offset = v & 0x3FFFFFFF
                    elif len(suffix) == 2 and suffix[0] == "code":
                        if code_offsets is None:
                            code_offsets = []
                            code_at = struct.unpack_from("<I", data, at)[0]
                            next_at = next((v for v in code_starts if v > code_at), None)
                            _parse_code(
                                data, code_at, next_at, number, names, globals_, code_offsets
                            )
                        offset = code_offsets[int(suffix[1])]
                    if offset is not None:
                        if _utf8z(data, offset) != source:
                            raise ValueError("Script pointer/catalog disagreement")
                        pointer_models[entry["key"]] = {
                            "source": source,
                            "model": MenuTranslator(
                                [entry], primary, secondary, language, True
                            ).runtime_model(),
                        }
                        pointers[source].append(
                            {
                                "key": entry["key"],
                                "offset": offset,
                                "size": len(data),
                                "sha256": digest,
                                "header": data[:24].hex(),
                            }
                        )
                local = MenuTranslator(selected, primary, secondary, language, True)
                call_count, call_start = struct.unpack_from("<II", data, at + 16)
                by_call = defaultdict(list)
                for entry in selected:
                    if language not in entry["texts"]:
                        continue
                    suffix = entry["key"].split(".dat/", 1)[1].split("/")[1:]
                    if len(suffix) >= 2 and suffix[0] == "called":
                        by_call[int(suffix[1])].append(entry)
                groups = defaultdict(list)
                call_numbers = defaultdict(list)
                for call, values in by_call.items():
                    if not any(e["texts"].get(language) in ambiguous for e in values):
                        continue
                    if call >= call_count:
                        raise ValueError("Catalog call outside script")
                    _, kind, argc, args_at = struct.unpack_from(
                        "<IHHI", data, call_start + call * 12
                    )
                    if kind != 3 or argc < 3 or args_at + argc * 8 > len(data):
                        continue
                    args = [struct.unpack_from("<II", data, args_at + i * 8) for i in range(argc)]
                    if any(k != 0 for _, k in args):
                        stats["dynamic_calls"] += 1
                    if args[0][0] != 0x40000005 or args[1][0] not in (
                        0x40000000,
                        0x40000006,
                        0x40000007,
                        0x40000013,
                    ):
                        continue
                    token = ",".join(str(v) if k == 0 else "?" for v, k in args[2:])
                    groups[token].extend(values)
                    call_numbers[token].append(call)
                calls = {}
                for token, values in groups.items():
                    tr = MenuTranslator(values, primary, secondary, language, True)
                    calls[token] = {"records": call_numbers[token], "model": tr.runtime_model()}
                    stats["call_identities"] += 1
                    for entry in values:
                        t = entry["texts"]
                        s = t.get(language)
                        if s in ambiguous and primary in t and secondary in t:
                            if tr.pairs.get(s) == (t[primary], t[secondary]):
                                stats["ambiguous_records_resolved_by_call"] += 1
                            else:
                                stats["ambiguous_records_still_conflicting"] += 1
                item = {"model": local.runtime_model(), "calls": calls}
                function_identity = (digest, name)
                if function_identity in blocked_functions:
                    continue
                previous = script["functions"].get(name)
                if previous is not None and previous != item:
                    # Byte-identical files can have different localized owners.
                    # The native identity cannot distinguish those owners, so
                    # quarantine this function rather than abort the language.
                    blocked_functions.add(function_identity)
                    del script["functions"][name]
                    stats["conflicting_function_identities"] += 1
                    continue
                script["functions"][name] = item
                stats["functions"] += 1
        stats["scripts"] = len(result)
        address_pairs = defaultdict(set)
        for source, items in pointers.items():
            for item in items:
                address_pairs[item["sha256"], item["offset"]].add(
                    tuple(pointer_models[item["key"]]["model"]["pairs"][source])
                )
        blocked = {address for address, pairs in address_pairs.items() if len(pairs) > 1}
        stats["shared_script_pointer_conflicts"] = len(blocked)
        pointers = {
            source: [item for item in items if (item["sha256"], item["offset"]) not in blocked]
            for source, items in pointers.items()
        }
        used = {item["key"] for items in pointers.values() for item in items}
        pointer_models = {key: value for key, value in pointer_models.items() if key in used}
        return {
            "scripts": result,
            "stats": dict(stats),
            "pointers": dict(pointers),
            "pointer_models": pointer_models,
        }
    finally:
        archive.close()


def compile_table_identities(game, entries, primary, secondary, language, *, resolved_pairs=None):
    """Recover the record key from direct native table-string pointers.

    The immutable descriptor and full string pool identify the actual file;
    masked scalar record bytes and the live field pointer identify its record.
    A shared string-pool pointer is retained as multiple candidates, never
    arbitrarily assigned to the first record that happens to use it.
    """
    from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables
    from sora_bilingual.localization.menu_tables import sections, schema_for, SCHEMAS

    if resolved_pairs is None:
        resolved_pairs = MenuTranslator(entries, primary, secondary, language).pairs
    needed = {
        e["key"]: e
        for e in entries
        if e.get("key", "").startswith("table/")
        and e["texts"].get(language, "").strip()
        and complete_pair(e["texts"], primary, secondary)
        and e["texts"][language] not in resolved_pairs
    }
    sources = defaultdict(list)
    models = {}
    files = {}
    archive = FpacArchive(Path(game) / "pac/steam" / _TABLE_ARCHIVES[language])
    try:
        logical = _logical_tables(archive)
        for path, actual in logical.items():
            if not any(k.startswith(path + "/") for k in needed):
                continue
            data = archive.read(actual)
            headers = sections(data)
            floor = max(start + stride * count for _, start, stride, count in headers)
            file_id = hashlib.sha256(data).hexdigest()
            files[file_id] = {
                "header": data[: 8 + 80 * len(headers)].hex(),
                "floor": floor,
                "size": len(data),
                "pool_sha256": hashlib.sha256(data[floor:]).hexdigest(),
            }
            for index, (kind, start, stride, count) in enumerate(headers):
                if kind not in SCHEMAS:
                    continue  # t_text already has native hash keys
                schema = schema_for(path, kind)
                if stride != schema.size:
                    continue
                occurrence = sum(s[0] == kind for s in headers[:index])
                prefix = (
                    path
                    if index == 0
                    else path + "/" + kind + (f"/{occurrence}" if occurrence else "")
                )
                for number in range(count):
                    at = start + number * stride
                    record = bytearray(data[at : at + stride])
                    for offset in schema.pointers:
                        record[offset : offset + 8] = b"\0" * 8
                    from sora_bilingual.localization.menu_tables import record_identity

                    stable = record_identity(data, at, kind, schema, floor)
                    for field, offset in schema.fields:
                        key = f"{prefix}/{stable}/{field}"
                        if key not in needed:
                            continue
                        entry = needed[key]
                        source = entry["texts"][language]
                        pointer = struct.unpack_from("<Q", data, at + offset)[0]
                        if not floor <= pointer < len(data) or _utf8z(data, pointer) != source:
                            continue
                        one = MenuTranslator(
                            [entry], primary, secondary, language, True
                        ).runtime_model()
                        models[key] = {"source": source, "model": one}
                        sources[source].append(
                            {
                                "key": key,
                                "file": file_id,
                                "offset": pointer,
                                "record_at": at,
                                "field_at": offset,
                                "record": record.hex(),
                                "pointers": schema.pointers,
                            }
                        )
        return {"sources": dict(sources), "models": models, "files": files}
    finally:
        archive.close()
