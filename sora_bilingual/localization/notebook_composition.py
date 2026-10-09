"""Finite notebook text producers, derived from their physical resource rows.

Fishing's rod page copies item names in slot order and joins them with
TXT_NOTE_FISHING_CONNECT. This is not a general comma-list translator: only
complete lists produced by an actual rod row enter the normal conflict set.
"""

from collections import defaultdict
from pathlib import Path
import struct

from sora_bilingual.localization.menu_tables import sections, schema_for, record_identity
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables


def _history_frame(source, target, ordinal):
    """Keep each complete event on its original native hard-line slots."""
    if source == target:
        return source
    left, right = source.split("\n"), target.split("\n")
    if ordinal == 0:

        def events(lines):
            starts = [i for i, line in enumerate(lines) if line.startswith("- ")]
            if not starts:
                starts = list(range(len(lines)))
            if len(starts) != 2 or starts[0] != 0:
                raise FormatError("unverified initial bracer history event grouping")
            ends = starts[1:] + [len(lines)]
            return starts, [" ".join(lines[a:b]).strip() for a, b in zip(starts, ends)]

        starts, _ = events(left)
        _, captions = events(right)
        framed = [""] * len(left)
        for start, caption in zip(starts, captions):
            framed[start] = caption
        return "\n".join(framed)
    # Every subsequent physical row contains one complete event. The five
    # recommendations include their locale's native trailing empty slot.
    if not source.strip() or not target.strip() or len(left) > 2 or len(right) > 2:
        raise FormatError("unverified bracer history event frame")
    return " ".join(line for line in right if line).strip() + "\n" * (len(left) - 1)


def compile_bracer_history(game, entries, languages, source_language):
    """CAB62 3FAA0E: ordered flag-selected bodies, each followed by LF.

    This copied label has no resource pointer. Only its dedicated native
    history scope consumes these whole constructors; none enter global pairs.
    """
    from sora_bilingual.localization.table_alignment import _ordered_records

    languages = tuple(dict.fromkeys(languages))
    catalog = defaultdict(list)
    for entry in entries:
        catalog[entry["key"]].append(entry.get("texts", {}))
    bodies, reference = {}, None
    for language in languages:
        with FpacArchive(Path(game) / "pac/steam" / _TABLE_ARCHIVES[language]) as archive:
            logical = _logical_tables(archive)
            data = archive.read(logical["table/t_quest_fc.tbl"])
        descriptors = sections(data)
        matches = [row for row in descriptors if row[0] == "NoteMainHistory"]
        schema = schema_for("table/t_quest_fc.tbl", "NoteMainHistory")
        if len(matches) != 1 or matches[0][2:] != (16, 11) or schema.size != 16:
            raise FormatError("bracer history physical layout changed")
        _, start, stride, count = matches[0]
        flags = [struct.unpack_from("<H", data, start + stride * i + 8)[0] for i in range(count)]
        if any(not 0 < flag < 0x8000 for flag in flags):
            raise FormatError("bracer history flag outside native builder domain")
        if reference is None:
            reference = flags
        elif flags != reference:
            raise FormatError("localized bracer history ordered flags differ")
        floor = max(at + size * n for _, at, size, n in descriptors)
        rows = []
        for identity, fields in _ordered_records(data, matches[0], schema, floor):
            pieces = fields.get("body", [])
            if len(pieces) != 1:
                raise FormatError("bracer history body is not one physical field")
            raw = pieces[0][1]
            key = "table/t_quest_fc.tbl/NoteMainHistory/" + identity + "/body"
            values = {row.get(language) for row in catalog.get(key, ())}
            if values != {raw} or not raw or "<" in raw or ">" in raw:
                raise FormatError("missing or changed complete bracer history resource: " + key)
            rows.append(raw)
        bodies[language] = rows
    unique_flags = list(dict.fromkeys(reference))
    if len(unique_flags) != 10 or reference[-2:] != [14187, 14187]:
        raise FormatError("bracer history independent flag contract changed")
    result = []
    for mask in range(1, 1 << len(unique_flags)):
        selected = {flag for bit, flag in enumerate(unique_flags) if mask & (1 << bit)}
        indices = [i for i, flag in enumerate(reference) if flag in selected]
        source_rows = bodies[source_language]
        texts = {
            language: "".join(
                _history_frame(source_rows[i], bodies[language][i], i) + "\n" for i in indices
            )
            for language in languages
        }
        if any(len(text.encode("utf8")) >= 2048 for text in texts.values()):
            raise FormatError("bracer history exceeds native formatter budget")
        result.append(
            {
                "key": f"table/t_bracer_history_generated/flags:{mask}/body",
                "texts": texts,
                "bracer_history_frame": True,
            }
        )
    return result


def compile_fishing_lists(game, entries, languages):
    languages = tuple(dict.fromkeys(languages))
    catalog = defaultdict(list)
    for entry in entries:
        catalog[entry["key"]].append(entry.get("texts", {}))

    def field(key, language, raw=None):
        values = {row.get(language) for row in catalog.get(key, ())}
        if len(values) != 1 or None in values:
            raise FormatError("missing or ambiguous notebook field: " + key)
        value = next(iter(values))
        if raw is not None and value != raw:
            raise FormatError("notebook physical source differs: " + key)
        return value

    by_language = {}
    reference = None
    for language in languages:
        with FpacArchive(Path(game) / "pac/steam" / _TABLE_ARCHIVES[language]) as archive:
            logical = _logical_tables(archive)
            fishing = archive.read(logical["table/t_minigame_fishing.tbl"])
            item = archive.read(logical["table/t_item.tbl"])
        fish_sections = sections(fishing)
        rods = [row for row in fish_sections if row[0] == "FishingRodInfo"]
        if len(rods) != 1 or rods[0][2] != 96:
            raise FormatError("FishingRodInfo physical layout changed")
        _, start, stride, count = rods[0]
        physical = [struct.unpack_from("<17I", fishing, start + i * stride) for i in range(count)]
        if len({row[0] for row in physical}) != len(physical):
            raise FormatError("duplicate physical rod ID")
        if reference is None:
            reference = physical
        elif physical != reference:
            raise FormatError("localized rod IDs or ordered bait slots differ")

        item_sections = sections(item)
        selected = [row for row in item_sections if row[0] == "ItemTableData"]
        schema = schema_for("table/t_item.tbl", "ItemTableData")
        if len(selected) != 1 or selected[0][2] != schema.size:
            raise FormatError("notebook item physical layout changed")
        _, item_start, item_stride, item_count = selected[0]
        pool = max(a + z * n for _, a, z, n in item_sections)
        names = defaultdict(set)
        needed = {item_id for row in physical for item_id in row[1:16] if item_id}
        for i in range(item_count):
            at = item_start + i * item_stride
            item_id = struct.unpack_from("<I", item, at)[0]
            if item_id not in needed:
                continue
            pointer = struct.unpack_from("<Q", item, at + 224)[0]
            if not pool <= pointer < len(item):
                raise FormatError("notebook name pointer outside item pool")
            end = item.find(b"\0", pointer, min(pointer + 4096, len(item)))
            if end < 0:
                raise FormatError("notebook item name exceeds budget")
            raw = item[pointer:end].decode("utf-8", "strict")
            identity = record_identity(item, at, "ItemTableData", schema, pool)
            key = "table/t_item.tbl/" + identity + "/name"
            names[item_id].add(field(key, language, raw))

        join = field("table/t_text.tbl/TXT_NOTE_FISHING_CONNECT", language)
        all_bait = field("table/t_text.tbl/TXT_NOTE_FISHING_USE_ALL_BAIT", language)
        values = {}
        for row in physical:
            rod_id, *slots = row
            members = []
            for slot, item_id in enumerate(slots):
                if not item_id:
                    break
                # CAB62 41B1B9/41B2BD: a nonzero sixteenth slot selects the
                # complete all-bait resource, rather than listing more names.
                if slot == 15:
                    members = None
                    break
                candidates = names.get(item_id, set())
                if len(candidates) != 1 or not next(iter(candidates), "").strip():
                    raise FormatError("missing or ambiguous physical bait name")
                members.append(next(iter(candidates)))
            text = all_bait if members is None else join.join(members)
            if len(text.encode("utf-8")) >= 1024:
                raise FormatError("rod bait list exceeds native buffer")
            if text:
                values[rod_id] = text
        by_language[language] = values

    return [
        {
            "key": f"table/t_minigame_fishing.tbl/FishingRodInfo/{rod_id}/bait_list",
            "texts": {language: by_language[language][rod_id] for language in languages},
            "notebook_producer": {
                "family": "rod_bait_list",
                "rod_id": rod_id,
                "ordered_slots": list(slots),
                "native_max_slots": 16,
            },
        }
        for rod_id, *slots in (reference or ())
        if all(rod_id in by_language[language] for language in languages)
    ]
