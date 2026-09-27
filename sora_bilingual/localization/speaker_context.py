"""Resolve copied history by its retained speaker and complete dialogue text.

No neighbouring dialogue or current scene is used. A name narrows the resource
set only; same-speaker wording conflicts still use the normal admission gate.
"""

from collections import defaultdict
from pathlib import Path
import struct

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables, _zutf8


def speaker_names(data):
    layout = sections(data)
    floor = max(start + size * count for _, start, size, count in layout)
    names = defaultdict(list)
    for kind, start, size, count in layout:
        if kind != "NameTableData":
            continue
        if size != 104:
            raise FormatError("Unexpected speaker name record stride")
        for number in range(count):
            at = start + number * size
            identity = struct.unpack_from("<I", data, at)[0]
            pointer = struct.unpack_from("<Q", data, at + 8)[0]
            if not floor <= pointer < len(data):
                raise FormatError("Speaker name outside pool")
            name, _ = _zutf8(data, pointer)
            if identity != 0xFFFF:
                names[identity].append(name)
    # Costume/entity variants may share an ID. Do not infer their actor state.
    return {
        identity: values[0] for identity, values in names.items() if len(values) == 1 and values[0]
    }


def read_speaker_names(game, language):
    with FpacArchive(Path(game) / "pac/steam" / archive_names("table")[language]) as archive:
        return speaker_names(archive.read(_logical_tables(archive)["table/t_name.tbl"]))


def compile_speaker_contexts(entries, names, primary, secondary, language, resolved_pairs=None):
    groups = defaultdict(list)
    for entry in entries:
        if entry.get("display_role") != "dialogue":
            continue
        ids = entry.get("speaker_ids", {})
        actor = ids.get(language)
        if actor not in names or any(ids.get(locale) != actor for locale in (primary, secondary)):
            continue
        source = entry["texts"].get(language)
        if not source or (resolved_pairs is not None and source in resolved_pairs):
            continue
        groups[names[actor]].append(entry)
    result = {}
    for name, records in groups.items():
        tr = MenuTranslator(records, primary, secondary, language, True)
        if tr.pairs:
            result[name] = {
                "pairs": tr.pairs,
                "plain_pairs": tr.plain_pairs,
                "ambiguous_display": sorted(tr.ambiguous_display),
                "same_language": tr.same_language,
            }
    return result
