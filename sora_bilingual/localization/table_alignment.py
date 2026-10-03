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
from sora_bilingual.localization.resources import FormatError


def supports_record_alignment(path, kind):
    return (path, kind) in {
        ("table/t_achievement.tbl", "PlayRecordData"),
        ("table/t_active_voice.tbl", "ActiveVoiceTableData"),
        ("table/t_name.tbl", "NameTableData"),
        ("table/t_quest_fc.tbl", "NoteMainHistory"),
        ("table/t_help.tbl", "HelpIconList"),
        ("table/t_help.tbl", "HelpPage"),
        ("table/t_books.tbl", "BooksText"),
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


def _help_page_records(data, section, schema, floor):
    """Continuation pages repeat a heading; page count is locale-dependent.

    Keep the complete ordered heading sequence within a topic, collapsing
    only adjacent identical headings with identical non-page metadata. Every
    physical repeat retains a pointer alias; distinct headings are not merged.
    """
    _, start, size, count = section
    raw = read_section(data, section, schema, floor, stable_row_identity=True)
    topics = defaultdict(list)
    for i in range(count):
        at = start + size * i
        topic = struct.unpack_from("<H", data, at)[0]
        # +2 is page type and +3 page number. +8 is an image resource name.
        resource = struct.unpack_from("<Q", data, at + 8)[0]
        end = data.find(b"\0", resource)
        if not floor <= resource <= end < len(data):
            raise FormatError("HelpPage image resource outside string pool")
        identity = (data[at + 2 : at + 3] + data[at + 4 : at + 8] + data[resource:end]).hex()
        fields = raw[f"row:{i}"][0]
        runs = topics[topic]
        if runs and runs[-1][0] == identity and runs[-1][1] == fields:
            runs[-1][2].append(i)
        else:
            runs.append((identity, fields, [i]))
    for topic, runs in topics.items():
        signature = _signature([identity for identity, _, _ in runs])
        for ordinal, (_, fields, rows) in enumerate(runs):
            yield (
                f"topic:{topic}/sequence:{signature}/heading:{ordinal}",
                {name: [(row, text) for row in rows] for name, text in fields.items()},
            )


def align_record_sections(files, descriptors, schema, *, path, prefix, kind, occurrence, audit):
    """Emit full fields and equal-segment-count aliases; never zip unequal rows."""
    if kind == "BooksText":
        return _align_books(files, descriptors, schema, prefix, occurrence, audit)
    records = defaultdict(dict)
    for language, data in files.items():
        matching = [s for s in descriptors.get(language, []) if s[0] == kind]
        if occurrence >= len(matching):
            continue
        floor = max(s + z * n for _, s, z, n in descriptors[language])
        reader = {"HelpIconList": _help_records, "HelpPage": _help_page_records}.get(
            kind, _ordered_records
        )
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
            if kind == "HelpPage":
                # Repeat aliases keep each native source pointer, without
                # joining the repeated header or mapping page 2 to page 2.
                for copy in range(max(map(len, pieces.values()))):
                    emit(
                        f"{key}/copy:{copy}",
                        field,
                        {l: [rows[min(copy, len(rows) - 1)]] for l, rows in pieces.items()},
                    )
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


def _align_books(files, descriptors, schema, prefix, occurrence, audit):
    """A chapter ID owns a whole document; a locale's page is not a text ID.

    The reader consumes book/page at +0/+2, body at +8 and illustration at
    +16. Retain native pages for disabled/single-language mode and build the
    bilingual pagination separately, without changing any on-disk table.
    """
    documents = defaultdict(dict)
    for language, data in files.items():
        matching = [s for s in descriptors[language] if s[0] == "BooksText"]
        if occurrence >= len(matching):
            continue
        _, start, size, count = matching[occurrence]
        floor = max(s + z * n for _, s, z, n in descriptors[language])
        raw = read_section(
            data, ("BooksText", start, size, count), schema, floor, stable_row_identity=True
        )
        grouped = defaultdict(list)
        for row in range(count):
            at = start + row * size
            book, page, reserved = struct.unpack_from("<HHI", data, at)
            pointer = struct.unpack_from("<Q", data, at + 16)[0]
            end = data.find(b"\0", pointer)
            if reserved or not floor <= pointer <= end < len(data):
                raise FormatError("BooksText has unknown metadata or illustration pointer")
            image = data[pointer:end].decode("utf-8")
            grouped[book].append((row, page, image, raw[f"row:{row}"][0].get("body", "")))
        for book, pages in grouped.items():
            if [p[1] for p in pages] != list(range(1, len(pages) + 1)):
                raise FormatError(f"BooksText {book} has duplicate or non-contiguous pages")
            documents[book][language] = pages
    entries = []
    for book, localized in sorted(documents.items()):
        sequences = {}
        for language, pages in localized.items():
            sequence = []
            for _, _, image, _ in pages:
                if not sequence or sequence[-1] != image:
                    sequence.append(image)
            sequences[language] = tuple(sequence)
        if len(localized) < 2 or len(set(sequences.values())) != 1:
            audit["diagnostics"].append(
                {
                    "class": "BooksText",
                    "book": book,
                    "reason": "book_illustration_sequence_mismatch",
                }
            )
            continue
        entries.append(
            {
                "key": f"{prefix}/group:{book}/body",
                "texts": {l: "\n".join(p[3] for p in pages) for l, pages in localized.items()},
                "table_rows": {l: [p[0] for p in pages] for l, pages in localized.items()},
                "book_id": book,
                "book_pages": {l: [[p[2], p[3]] for p in pages] for l, pages in localized.items()},
            }
        )
    audit["counters"]["entries_emitted"] += len(entries)
    audit["counters"]["book_documents_emitted"] += len(entries)
    return entries
