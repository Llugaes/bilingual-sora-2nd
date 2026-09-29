"""Ordered table documents and grouped help entries, with physical provenance.

These sections are not dictionaries of scalar IDs. Keep their ordered resource
locations, guarded by the non-text sequence, rather than coalescing equal rows.
Help pages contain locale-specific continuation/padding rows, so only headings
advance the entry number; fields are aligned as complete paragraphs first.
"""

from collections import defaultdict
import hashlib
import struct

from sora_bilingual.localization.menu_tables import read_section, record_identity


def supports_record_alignment(path, kind):
    return (path, kind) in {
        ("table/t_achievement.tbl", "PlayRecordData"),
        ("table/t_active_voice.tbl", "ActiveVoiceTableData"),
        ("table/t_name.tbl", "NameTableData"),
        ("table/t_quest_fc.tbl", "NoteMainHistory"),
        ("table/t_help.tbl", "HelpIconList"),
    }


def _signature(values):
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def _ordered_records(data, section, schema, floor):
    kind, start, size, count = section
    raw = read_section(data, section, schema, floor, stable_row_identity=True)
    groups = defaultdict(list)
    for i in range(count):
        at = start + size * i
        # ActiveVoice's scalar selects a conversation, not one of its lines.
        group = struct.unpack_from("<I", data, at)[0] if kind == "ActiveVoiceTableData" else 0
        groups[group].append(
            (i, record_identity(data, at, kind, schema, floor), raw[f"row:{i}"][0])
        )
    for group, rows in groups.items():
        signature = _signature([identity for _, identity, _ in rows])
        for ordinal, (i, _, fields) in enumerate(rows):
            yield (
                f"group:{group}/sequence:{signature}/record:{ordinal}",
                {name: [(i, text)] for name, text in fields.items()},
            )


def _help_records(data, section, schema, floor):
    _, start, size, count = section
    raw = read_section(data, section, schema, floor, stable_row_identity=True)
    topics = defaultdict(list)
    for i in range(count):
        fields = raw[f"row:{i}"][0]
        topic = struct.unpack_from("<H", data, start + size * i)[0]
        icon = struct.unpack_from("<I", data, start + size * i + 4)[0]
        # +2 is the locale's page, +16/+32 are column widths. None identifies
        # an entry. A title/icon starts an entry; untitled rows continue it.
        if fields.get("title", "").strip() or icon:
            topics[topic].append((icon, defaultdict(list)))
        if not any(text.strip() for text in fields.values()):
            continue
        if not topics[topic]:
            # Retain an untitled leading block as its own explicit entry.
            topics[topic].append((0, defaultdict(list)))
        target = topics[topic][-1][1]
        for name, text in fields.items():
            if text.strip():
                target[name].append((i, text))
    for topic, blocks in topics.items():
        signature = _signature([str(icon) for icon, _ in blocks])
        for ordinal, (_, fields) in enumerate(blocks):
            yield f"topic:{topic}/sequence:{signature}/entry:{ordinal}", dict(fields)


def align_record_sections(files, descriptors, schema, *, path, prefix, kind, occurrence, audit):
    """Emit full fields and equal-segment-count aliases; never zip unequal rows."""
    records = defaultdict(dict)
    for language, data in files.items():
        matching = [s for s in descriptors.get(language, []) if s[0] == kind]
        if occurrence >= len(matching):
            continue
        floor = max(s + z * n for _, s, z, n in descriptors[language])
        reader = _help_records if kind == "HelpIconList" else _ordered_records
        for key, fields in reader(data, matching[occurrence], schema, floor):
            records[key][language] = fields
    entries = []

    def emit(key, field, pieces):
        texts = {language: "\n".join(text for _, text in rows) for language, rows in pieces.items()}
        if len(texts) < 2:
            audit["diagnostics"].append(
                {
                    "path": path,
                    "class": kind,
                    "key": key,
                    "field": field,
                    "reason": "ordered_record_missing_peer",
                    "languages": list(texts),
                }
            )
            return
        entries.append(
            {
                "key": f"{prefix}/{key}/{field}",
                "texts": texts,
                "table_rows": {language: [i for i, _ in rows] for language, rows in pieces.items()},
            }
        )
        audit["counters"]["entries_emitted"] += 1

    for key, localized in records.items():
        for field, _ in schema.fields:
            pieces = {l: fields[field] for l, fields in localized.items() if field in fields}
            if not pieces:
                continue
            emit(key, field, pieces)
            # A locale can wrap one field over several physical controls. Only
            # equally segmented locales share individual line identities.
            for count in sorted({len(rows) for rows in pieces.values()} - {1}):
                same = {l: rows for l, rows in pieces.items() if len(rows) == count}
                for line in range(count):
                    emit(
                        f"{key}/segments:{count}/line:{line}",
                        field,
                        {l: [rows[line]] for l, rows in same.items()},
                    )
    audit["counters"]["ordered_fields_emitted"] += len(entries)
    return entries
