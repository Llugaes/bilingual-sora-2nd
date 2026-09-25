"""Shared multilingual table alignment helpers; section layouts live in menu_tables."""

from __future__ import annotations
from pathlib import Path
import struct
from typing import Any
from sora_bilingual.localization.resources import FpacArchive, FormatError, LANGUAGES

from sora_bilingual.config.locales import archive_names

_TABLE_ARCHIVES = archive_names("table")


_HEADER = 88


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FormatError(f"TBL u32 outside input at {offset:#x}")
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 8 > len(data):
        raise FormatError(f"TBL u64 outside input at {offset:#x}")
    return struct.unpack_from("<Q", data, offset)[0]


def _zutf8(data: bytes, offset: int) -> tuple[str, int]:
    if offset < 0 or offset >= len(data):
        raise FormatError(f"TBL string outside input at {offset:#x}")
    end = data.find(b"\0", offset)
    if end < 0:
        raise FormatError(f"TBL unterminated string at {offset:#x}")
    try:
        return data[offset:end].decode("utf-8"), end + 1
    except UnicodeDecodeError as exc:
        raise FormatError(f"TBL non-UTF-8 string at {offset:#x}") from exc


def _header(data: bytes) -> tuple[int, str, int, int, int]:
    if len(data) < _HEADER or data[:4] != b"#TBL":
        raise FormatError("missing #TBL header")
    version = _u32(data, 4)
    try:
        kind = data[8:72].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise FormatError("TBL class name is not ASCII") from exc
    metadata_size, row_size, row_count = (_u32(data, 76), _u32(data, 80), _u32(data, 84))
    if not kind or row_size == 0 or row_count > (len(data) - _HEADER) // min(row_size, 8):
        raise FormatError("invalid TBL row metadata")
    return version, kind, metadata_size, row_size, row_count


def _text_rows(data: bytes) -> dict[str, str]:
    version, kind, _metadata, row_size, count = _header(data)
    if (version, kind, row_size) != (1, "TextTableData", 16):
        raise FormatError("not the validated TextTableData layout")
    end = _HEADER + count * row_size
    if end > len(data):
        raise FormatError("TextTableData rows outside input")
    result: dict[str, str] = {}
    for number in range(count):
        row = _HEADER + number * row_size
        key, _ = _zutf8(data, _u64(data, row))
        text, _ = _zutf8(data, _u64(data, row + 8))
        if not key or key in result:
            raise FormatError(f"invalid duplicate/empty TextTableData key at row {number}")
        result[key] = text
    return result


def _coalesce_duplicate_groups(
    per_language: dict[str, dict[str, list[dict[str, str]]]],
    audit: dict[str, Any],
    *,
    path: str,
    kind: str,
) -> dict[str, dict[str, dict[str, str]]]:
    """Accept only provably identical duplicate record groups across locales."""
    result: dict[str, dict[str, dict[str, str]]] = {language: {} for language in per_language}
    all_ids = set().union(*(rows.keys() for rows in per_language.values()))
    for stable_id in all_ids:
        groups = {language: rows.get(stable_id, []) for language, rows in per_language.items()}
        sizes = {language: len(group) for language, group in groups.items()}
        for language, group in groups.items():
            if len(group) > 1 and any(value != group[0] for value in group):
                audit["ambiguous_duplicate_groups"].append(
                    {
                        "path": path,
                        "class": kind,
                        "fingerprint": stable_id,
                        "language": language,
                        "records_by_language": sizes,
                    }
                )
                audit["counters"]["duplicate_groups_rejected"] += 1
                continue
            if len(group) > 1:
                audit["counters"]["duplicate_groups_coalesced"] += 1
            if group:
                result[language][stable_id] = group[0]
    return result


def _logical_tables(archive: FpacArchive) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in archive.entries:
        root, separator, rest = path.partition("/")
        if not separator or (root != "table" and not root.startswith("table_")):
            continue
        logical = "table/" + rest
        if logical in result:
            raise FormatError(f"{archive.path.name}: duplicate logical table path {logical}")
        result[logical] = path
    return result


def _emit_aligned(
    entries: list[dict[str, Any]],
    per_language: dict[str, dict[Any, Any]],
    *,
    path: str,
    field: str | None,
    audit: dict[str, Any],
) -> None:
    identities = set().union(*(rows.keys() for rows in per_language.values()))
    for stable_id in sorted(identities, key=str):
        texts: dict[str, str] = {}
        for language in LANGUAGES:
            value = per_language.get(language, {}).get(stable_id)
            if value is None:
                audit["counters"][f"missing_{language}"] += 1
                continue
            text = value if field is None else value.get(field)
            if not isinstance(text, str):
                audit["counters"][f"missing_field_{field}_{language}"] += 1
                continue
            texts[language] = text
        if len(texts) < 2:
            audit["counters"]["without_secondary_language"] += 1
            continue
        suffix = str(stable_id) if field is None else f"{stable_id}/{field}"
        entries.append({"key": f"{path}/{suffix}", "texts": texts})
        audit["counters"]["entries_emitted"] += 1


def build_table_entries(game_dir):
    from sora_bilingual.localization.menu_tables import build_menu_entries

    return build_menu_entries(game_dir)
