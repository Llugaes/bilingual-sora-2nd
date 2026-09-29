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
    _value,
    Called,
    assembled_dialogue,
    parse_scp,
)
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator, complete_pair, needs_annotation


_DIALOGUE_COMMANDS = (0, 6, 7, 8, 19)


def _source_called_id(entry, language, canonical):
    """Resolve a catalog call key to the selected source archive's record ID."""
    called_ids = entry.get("called_ids")
    if called_ids is None:
        return canonical
    called = called_ids.get(language)
    return called if isinstance(called, int) and called >= 0 else None


def _call_entry_family(entry):
    key = entry.get("key", "").split("/alignment/", 1)[0]
    if "/called/" not in key:
        return None
    tail = key.split("/called/", 1)[1].split("/", 1)
    return tail[1].split("/", 1)[0] if len(tail) == 2 else None


def _dedupe_call_entries(entries, primary, secondary, language):
    """Drop only same-record rows dominated by an exact complete row."""
    entries = list(entries)
    complete = [
        entry
        for entry in entries
        if language in entry["texts"] and complete_pair(entry["texts"], primary, secondary)
    ]
    result = []
    seen_complete = set()
    for entry in entries:
        texts = entry["texts"]
        family = _call_entry_family(entry)
        dominators = [
            candidate
            for candidate in complete
            if _call_entry_family(candidate) == family
            and all(candidate["texts"].get(locale) == text for locale, text in texts.items())
        ]
        if dominators:
            best = max(
                dominators,
                key=lambda candidate: (len(candidate["texts"]), candidate.get("key", "")),
            )
            identity = (family, tuple(sorted(best["texts"].items())))
            if complete_pair(texts, primary, secondary) is None:
                continue
            if identity in seen_complete:
                continue
            seen_complete.add(identity)
            result.append(best)
        else:
            result.append(entry)
    return result


def _stable_dialogue_record(entry):
    """Return the locale-independent identity of one physical dialogue call."""
    key = entry.get("key", "").split("/alignment/", 1)[0]
    if not key.endswith("/assembled_dialogue") or "/called/" not in key:
        return None
    called = key.rsplit("/called/", 1)[1].split("/", 1)
    if len(called) != 2 or not called[0].isdigit():
        return None
    return key


def _record_candidate(entries, language):
    """Select one exact source for a canonical dialogue record."""
    candidates = set()
    for entry in entries:
        key = _stable_dialogue_record(entry)
        source = entry["texts"].get(language)
        if key is not None and source is not None:
            candidates.add((key, source))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _history_marker(call):
    """Return the last static marker written by the common dialogue builder.

    Native 0x4ad844 sends operators 11 and 12 through the same operand branch;
    0x4add28 writes the following integer through the handler's marker output.
    The three handlers that later call log_write consume group, command and
    speaker before the builder sees args[3:].  Builder operations 11/12 and
    17/18/21/23 consume one following operand; every other integer operation
    is one slot wide.  Zero and 0xffff are native sentinel values, not
    recoverable identities.  The writer persists the result as an unsigned
    dword, so no narrower upper bound is imposed here.
    """
    if (
        call.kind != 3
        or len(call.args) < 3
        or call.args[0] != ("int", 5)
        or call.args[1] not in (("int", 0), ("int", 6), ("int", 19))
        or call.args[2][0] == "string"
    ):
        return None
    marker = None
    index = 3
    while index < len(call.args):
        kind, value = call.args[index]
        if kind == "string":
            index += 1
            continue
        if kind != "int":
            return None
        if value in (11, 12):
            if index + 1 >= len(call.args) or call.args[index + 1][0] != "int":
                return None
            marker = int(call.args[index + 1][1])
            index += 2
            continue
        if value in (17, 18, 21, 23):
            # These width-two operations interpolate runtime data.  A static
            # resource suffix is not the complete string written to history.
            return None
        index += 1
    if marker is None:
        return None
    marker &= 0xFFFFFFFF
    return marker if marker not in (0, 0xFFFF) else None


def _history_marker_catalog_records(entries):
    candidates = defaultdict(set)
    for entry in entries:
        record_key = _stable_dialogue_record(entry)
        if record_key is None or entry.get("display_role") != "dialogue":
            continue
        prefix, tail = record_key.rsplit("/called/", 1)
        canonical = int(tail.split("/", 1)[0])
        path, function = prefix.split(".dat/", 1)
        path += ".dat"
        for locale, source in entry.get("texts", {}).items():
            called = _source_called_id(entry, locale, canonical)
            if called is not None:
                candidates[locale, path, function, called].add((record_key, source))
    # Conflicting catalog rows cannot acquire authority merely because a log
    # marker happens to match one of them.
    return {
        physical: next(iter(values)) for physical, values in candidates.items() if len(values) == 1
    }


def _speaker_setter_catalog_records(entries, primary, secondary):
    """Return one complete label pair for each physical display-name setter."""

    def identity(entry):
        key = entry.get("key", "").split("/alignment/", 1)[0]
        prefix, separator, suffix = key.partition("/called/")
        if not prefix or not separator:
            return None
        parts = suffix.split("/")
        if len(parts) != 3 or not parts[0].isdigit() or parts[1:] != ["arg", "1"]:
            return None
        path, separator, function = prefix.partition(".dat/")
        if not path or not separator or not function:
            return None
        return path + ".dat", function, int(parts[0])

    claims = defaultdict(set)
    for entry in entries:
        if entry.get("display_role") != "speaker":
            continue
        record = identity(entry)
        if record is None:
            continue
        pair = complete_pair(entry["texts"], primary, secondary)
        for locale, source in entry["texts"].items():
            if not source or not source.strip():
                continue
            called = _source_called_id(entry, locale, record[2])
            if called is not None:
                claims[locale, record[0], record[1], called].add((source, pair))

    result = {}
    for physical, values in claims.items():
        # A complete direct setter dominates its incomplete alignment fragment.
        complete = {(source, pair) for source, pair in values if pair is not None}
        if len(complete) == 1:
            result[physical] = next(iter(complete))
    return result


def _active_speaker_setter_records(function, setters, dialogues):
    """Map marker-qualified calls to their active, static name setter.

    Only a branch-free function with ``wait_prompt`` between known operations
    is admitted.  Any other call after a setter can change VM state outside
    this compiler's contract, so it clears every active label.
    """
    if any(instruction[0] == "branch" for instruction in function.code_shape):
        return {}
    active, result = {}, defaultdict(set)
    for called, call in enumerate(function.called):
        if call.target == "chr_set_display_name":
            if len(call.args) == 2 and call.args[0][0] == "int" and call.args[1][0] == "string":
                actor = int(call.args[0][1])
                setter = setters.get(called)
                if setter is not None and setter[0] == call.args[1][1]:
                    active[actor] = setter
                else:
                    active.pop(actor, None)
            else:
                active.clear()
            continue
        source = assembled_dialogue(call)
        if source is not None:
            record = dialogues.get(called)
            actor = call.args[2][1] if len(call.args) >= 3 and call.args[2][0] == "int" else None
            if record is not None and actor in active:
                result[record].add(active[actor])
            continue
        if active and not (call.target == "wait_prompt" and not call.args):
            active.clear()
    return dict(result)


def _compile_history_speaker_setters(game, entries, primary, secondary):
    """Compile record-keyed generic name pairs without changing marker identity."""
    return _compile_history_provenance(game, entries, primary, secondary)[1]


def _compile_history_provenance(game, entries, primary=None, secondary=None):
    """Read each source script once for marker and optional name provenance."""
    from sora_bilingual.localization.speaker_context import read_speaker_names

    catalog = _history_marker_catalog_records(entries)
    setters_by_function = defaultdict(dict)
    if primary is not None and secondary is not None:
        for (locale, path, function, called), setter in _speaker_setter_catalog_records(
            entries, primary, secondary
        ).items():
            setters_by_function[locale, path, function][called] = setter
    # A marker only becomes usable when an exact catalog record already maps
    # this locale, script function and called-record ordinal.  Parsing every
    # installed script cannot add a candidate: those records would be rejected
    # below.  Keep the physical call set so source checks and conflicts remain
    # exactly as strict after skipping unrelated files and functions.
    wanted = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for locale, path, function, called in catalog:
        wanted[locale][path][function].add(called)
    buckets = defaultdict(set)
    speaker_rows = defaultdict(set)
    names = {}
    for locale in LANGUAGES:
        archive = FpacArchive(Path(game) / "pac/steam" / _ARCHIVES[locale])
        try:
            logical = _logical_script_entries(archive)
            for path in sorted(wanted[locale]):
                archive_path = logical.get(path)
                if archive_path is None:
                    continue
                script = parse_scp(archive.read(archive_path))
                for function_name, function in script.functions.items():
                    calls = wanted[locale][path].get(function_name)
                    if not calls:
                        continue
                    dialogues = {}
                    for called, call in enumerate(function.called):
                        if called not in calls:
                            continue
                        source = assembled_dialogue(call)
                        if source is None:
                            continue
                        marker = _history_marker(call)
                        if marker is None:
                            continue
                        candidate = catalog.get((locale, path, function_name, called))
                        if candidate is None or candidate[1] != source:
                            continue
                        speaker_id = None
                        if (
                            len(call.args) >= 3
                            and call.args[0] == ("int", 5)
                            and call.args[1] in (("int", 0), ("int", 6), ("int", 19))
                            and call.args[2][0] == "int"
                        ):
                            speaker_id = int(call.args[2][1])
                        if speaker_id is not None and locale not in names:
                            names[locale] = read_speaker_names(game, locale)
                        speaker = names.get(locale, {}).get(speaker_id)
                        record_key = candidate[0]
                        buckets[str(marker)].add((locale, source, speaker, record_key, called))
                        dialogues[called] = record_key
                    if primary is not None and secondary is not None:
                        local_setters = setters_by_function[locale, path, function_name]
                        for record_key, candidates in _active_speaker_setter_records(
                            function, local_setters, dialogues
                        ).items():
                            for source, pair in candidates:
                                speaker_rows[record_key].add((locale, source, *pair))
        finally:
            archive.close()
    markers = {
        marker: [list(row) for row in sorted(rows, key=repr)]
        for marker, rows in sorted(buckets.items(), key=lambda item: int(item[0]))
    }
    speakers = {
        record_key: [list(row) for row in sorted(rows, key=repr)]
        for record_key, rows in sorted(speaker_rows.items())
    }
    return markers, speakers


def _compile_history_markers(game, entries):
    """Compile exact old-log provenance across every installed source locale."""
    return _compile_history_provenance(game, entries)[0]


def _script_call_sites(data, start, names):
    """Map the VM's next PC to the compiler's independent called-record ID.

    VM 0x5e7749..0x5e7790 stores the PC after opcode 36's three operands
    before dispatch. Match the complete call sequence, never a filtered text
    sequence, and validate each system operation and argument count.
    """
    starts = sorted(struct.unpack_from("<I", data, start + i * 32)[0] for i in range(len(names)))
    global_at, global_count = struct.unpack_from("<II", data, 12)
    globals_ = tuple(
        _utf8z(data, struct.unpack_from("<I", data, global_at + i * 8)[0] & 0x3FFFFFFF)
        for i in range(global_count)
    )
    result, records = {}, {}
    for number, name in enumerate(names):
        at = start + number * 32
        count, called_at = struct.unpack_from("<II", data, at + 16)
        calls, wanted = [], set()
        for call in range(count):
            target, kind, argc, args_at = struct.unpack_from("<IHHI", data, called_at + call * 12)
            args = [struct.unpack_from("<II", data, args_at + i * 8) for i in range(argc)]
            calls.append((target, kind, args))
            if (
                kind == 3
                and argc >= 3
                and args[0] == (0x40000005, 0)
                and args[1] in ((0x40000000 + command, 0) for command in _DIALOGUE_COMMANDS)
            ):
                decoded = tuple(
                    _value(data, args_at + i * 8) if tag == 0 else ("dynamic", None)
                    for i, (_, tag) in enumerate(args)
                )
                if assembled_dialogue(Called(None, kind, decoded)) is not None:
                    wanted.add(call)
        if not wanted:
            continue
        index = defaultdict(list)
        for call in sorted(wanted):
            args = calls[call][2]
            token = ",".join(str(value) if tag == 0 else "?" for value, tag in args[2:])
            index[f"5:{args[1][0] - 0x40000000}:{token}"].append(call)
        records[name] = dict(index)
        code_at = struct.unpack_from("<I", data, at)[0]
        end = next((v for v in starts if v > code_at), None)
        positions = []
        code, _ = _parse_code(data, code_at, end, number, tuple(names), globals_, None, positions)
        sequence = [
            (pos, op)
            for pos, op in zip(positions, code, strict=True)
            if op[0] in ("local-call", "external-call", "system-call")
        ]
        if len(sequence) != len(calls):
            continue
        sites = {}
        for call, ((pc, op), (target, kind, args)) in enumerate(zip(sequence, calls, strict=True)):
            valid = (
                kind == 0
                and op[0] == "local-call"
                and target < len(names)
                and op[1] == names[target]
                or kind in (1, 2)
                and op[:2] == ("external-call", 33 + kind)
                and bool(args)
                and args[0][1] == 0
                and args[0][0] >> 30 == 3
                and _utf8z(data, args[0][0] & 0x3FFFFFFF) == f"{op[2]}.{op[3]}"
                and len(args) == op[4] + 1
                or kind == 3
                and op[0] == "system-call"
                and len(args) >= 2
                and args[:2] == [(0x40000000 + op[1], 0), (0x40000000 + op[2], 0)]
                and len(args) == op[3] + 2
            )
            if not valid:
                sites = {}
                break
            if call in wanted:
                sites[str(pc + 4)] = {
                    "record": call,
                    "group": op[1],
                    "command": op[2],
                    "token": ",".join(str(value) if tag == 0 else "?" for value, tag in args[2:]),
                }
        result[name] = sites
    return result, records


def script_signature(data):
    if data[:4] != b"#scp" or len(data) < 24:
        raise ValueError("Invalid script identity header")
    start, count = struct.unpack_from("<II", data, 4)
    if not 0 < count <= 65536 or start < 24 or start + count * 32 > len(data):
        raise ValueError("Invalid script function range")
    return (
        data[:24] + data[start : start + 32] + data[start + (count - 1) * 32 : start + count * 32]
    ).hex()


def _script_manifest_entry(data):
    """Return the bounded provenance needed before any language resolver exists."""
    if not 24 <= len(data) <= 16 * 1024 * 1024:
        raise ValueError("Script identity data outside capture bounds")
    signature = script_signature(data)
    start, count = struct.unpack_from("<II", data, 4)
    names = [
        _utf8z(data, struct.unpack_from("<I", data, start + number * 32 + 28)[0] & 0x3FFFFFFF)
        for number in range(count)
    ]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("Invalid script function names")
    sites, records = _script_call_sites(data, start, names)
    return signature, {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "functions": names,
        "callSites": sites,
        "callRecords": records,
    }


def compile_script_identities(game, entries, primary, secondary, language, *, resolved_pairs=None):
    """Compile source provenance and per-ID resolvers for all static dialogue."""
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
    paths = {path for path, _ in functions}
    result = {}
    stats = defaultdict(int)
    pointers = defaultdict(list)
    pointer_models = {}
    blocked_functions = set()
    record_pair_candidates = defaultdict(set)
    for entry in entries:
        record_key = _stable_dialogue_record(entry)
        pair = complete_pair(entry["texts"], primary, secondary)
        if record_key is not None and pair is not None:
            record_pair_candidates[record_key].add(pair)
    manifest_record_conflicts = set()
    archive = FpacArchive(Path(game) / "pac/steam" / _ARCHIVES[language])
    try:
        logical = _logical_script_entries(archive)
        manifest = defaultdict(list)
        for path in sorted(logical):
            if not path.endswith(".dat"):
                continue
            try:
                signature, item = _script_manifest_entry(archive.read(logical[path]))
            except ValueError, struct.error:
                stats["manifest_invalid_scripts"] += 1
                continue
            bucket = manifest[signature]
            if not any(candidate["sha256"] == item["sha256"] for candidate in bucket):
                bucket.append(item)
                stats["manifest_scripts"] += 1
                stats["manifest_functions"] += len(item["functions"])
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
                source_identity = next(v for v in manifest[signature] if v["sha256"] == digest)
                record_index = source_identity["callRecords"].get(name, {})
                if (path, name) not in needed and not record_index:
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
                        called = _source_called_id(entry, language, int(suffix[1]))
                        if called is None:
                            continue
                        pointer_call_count, pointer_calls_at = struct.unpack_from(
                            "<II", data, at + 16
                        )
                        if called >= pointer_call_count:
                            continue
                        call_at = pointer_calls_at + called * 12
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
                call_count, call_start = struct.unpack_from("<II", data, at + 16)
                by_call = defaultdict(list)
                non_call_entries = []
                for entry in selected:
                    if language not in entry["texts"]:
                        continue
                    suffix = entry["key"].split(".dat/", 1)[1].split("/")[1:]
                    if len(suffix) >= 2 and suffix[0] == "called":
                        called = _source_called_id(entry, language, int(suffix[1]))
                        if called is not None:
                            by_call[called].append(entry)
                    else:
                        non_call_entries.append(entry)
                raw_record_candidates = {
                    call: candidate
                    for call, values in by_call.items()
                    if (candidate := _record_candidate(values, language)) is not None
                }
                calls_by_record = defaultdict(set)
                for call, (record_key, _source) in raw_record_candidates.items():
                    calls_by_record[record_key].add(call)
                record_candidates = {
                    call: candidate
                    for call, candidate in raw_record_candidates.items()
                    if len(calls_by_record[candidate[0]]) == 1
                }
                for call, (record_key, source) in record_candidates.items():
                    records_by_function = source_identity.setdefault("recordKeys", {}).setdefault(
                        name, {}
                    )
                    slot = str(call)
                    identity = (id(source_identity), name, slot)
                    value = {"key": record_key, "source": source}
                    previous = records_by_function.get(slot)
                    if identity in manifest_record_conflicts:
                        continue
                    if previous is not None and previous != value:
                        del records_by_function[slot]
                        manifest_record_conflicts.add(identity)
                        stats["conflicting_canonical_record_keys"] += 1
                    else:
                        records_by_function[slot] = value
                for call, values in tuple(by_call.items()):
                    by_call[call] = _dedupe_call_entries(values, primary, secondary, language)
                local_entries = non_call_entries + [
                    entry for values in by_call.values() for entry in values
                ]
                local = MenuTranslator(
                    local_entries if (path, name) in needed else [],
                    primary,
                    secondary,
                    language,
                    True,
                )
                groups = defaultdict(list)
                call_numbers = defaultdict(list)
                records = {}
                identified_calls = {call for calls in record_index.values() for call in calls}
                for call, values in by_call.items():
                    if call in identified_calls:
                        candidate = record_candidates.get(call)
                        records[str(call)] = (
                            {"key": candidate[0]}
                            if candidate is not None
                            else {
                                "model": MenuTranslator(
                                    values, primary, secondary, language, True
                                ).runtime_model()
                            }
                        )
                        stats["dialogue_records"] += 1
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
                        0x40000008,
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
                item = {"model": local.runtime_model(), "calls": calls, "records": records}
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
        resolved_record_pairs = {
            key: next(iter(pairs))
            for key, pairs in record_pair_candidates.items()
            if len(pairs) == 1
        }
        stats["canonical_record_pairs"] = len(resolved_record_pairs)
        stats["conflicting_canonical_record_pairs"] = sum(
            len(pairs) > 1 for pairs in record_pair_candidates.values()
        )
        record_pair_values = sorted(set(resolved_record_pairs.values()))
        record_pair_indexes = {pair: index for index, pair in enumerate(record_pair_values)}
        history_markers, history_speaker_setters = _compile_history_provenance(
            game, entries, primary, secondary
        )
        from sora_bilingual.localization.dynamic_identity import compile_dynamic_identities

        dynamic_producers = compile_dynamic_identities(game, entries, primary, secondary, language)
        return {
            "scripts": result,
            "manifest": dict(manifest),
            "source_language": language,
            "history_markers": history_markers,
            "history_speaker_setters": history_speaker_setters,
            "dynamic_producers": dynamic_producers,
            "record_pairs": {
                key: record_pair_indexes[pair] for key, pair in resolved_record_pairs.items()
            },
            "record_pair_values": record_pair_values,
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
    from sora_bilingual.localization.menu_tables import (
        sections,
        schema_for,
        record_identity,
        spec,
        SCHEMAS,
    )

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
                occurrence = sum(s[0] == kind for s in headers[:index])
                prefix = (
                    path
                    if index == 0
                    else path + "/" + kind + (f"/{occurrence}" if occurrence else "")
                )
                keyed_text = kind == "TextTableData"
                if not keyed_text and kind not in SCHEMAS:
                    continue
                # t_text has an explicit string key and a text pointer, rather
                # than scalar ID fields. Both use the same pointer validation,
                # conflict handling and native resolver as every other table.
                schema = spec(16, [("", 8)], [0]) if keyed_text else schema_for(path, kind)
                if stride != schema.size:
                    continue
                physical_keys = defaultdict(list)
                for key, entry in needed.items():
                    owner = key.split("/group:", 1)[0].split("/topic:", 1)[0]
                    if owner != prefix or "table_rows" not in entry:
                        continue
                    rows = entry["table_rows"].get(language, [])
                    # A paragraph spanning several native controls cannot be
                    # mistaken for a single field pointer. Its equal-segment
                    # aliases have their own physical row provenance.
                    if len(rows) == 1:
                        physical_keys[(rows[0], key.rsplit("/", 1)[-1])].append(key)
                for number in range(count):
                    at = start + number * stride
                    record = bytearray(data[at : at + stride])
                    for offset in schema.pointers:
                        record[offset : offset + 8] = b"\0" * 8
                    if keyed_text:
                        key_pointer = struct.unpack_from("<Q", data, at)[0]
                        if not floor <= key_pointer < len(data):
                            continue
                        stable = _utf8z(data, key_pointer)
                    else:
                        stable = record_identity(data, at, kind, schema, floor)
                    for field, offset in schema.fields:
                        key = f"{prefix}/{stable}" + (f"/{field}" if field else "")
                        keys = physical_keys.get((number, field), []) or [key]
                        for key in keys:
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
