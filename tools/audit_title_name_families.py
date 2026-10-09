"""Bounded disk-only title/name inventory and independent Tips record oracle."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables

# Explicit physical contracts; not enumerated from catalog admission or model output.
FIELDS = {
    "TipsTableData": (56, {"title": 40, "body": 48}),
    "HelpTitle": (24, {"title": 8}),
    "HelpPage": (32, {"title": 16}),
    "HelpIconList": (56, {"title": 8}),
    "NoteMainCategory": (24, {"title": 8}),
    "NoteBattleCategory": (24, {"title": 8}),
    "NoteHelpCategory": (32, {"title": 8}),
    "NoteCookCategory": (32, {"title": 8}),
    "NoteFishingCategory": (32, {"title": 8}),
    "BooksTitle": (24, {"title": 8}),
    "BooksCategory": (24, {"title": 8}),
    "MapJumpAreaData": (56, {"name": 8}),
    "MapJumpSpotData": (152, {"name": 16}),
    "PlaceTableData": (168, {"name": 96}),
    "NameTableData": (104, {"name": 8}),
    "StatusParam": (424, {"name": 408}),
    "ViewerMapData": (80, {"name": 16}),
    "ItemTableData": (256, {"name": 224}),
    "SkillParam": (176, {"name": 152}),
    "SupportAbilityParam": (64, {"name": 48}),
}


def raw_sections(data):
    if data[:4] != b"#TBL" or len(data) < 88:
        raise FormatError("missing disk table header")
    count = struct.unpack_from("<I", data, 4)[0]
    if not 0 < count <= 1024 or 8 + count * 80 > len(data):
        raise FormatError("invalid disk descriptor count")
    result = []
    for i in range(count):
        at = 8 + i * 80
        kind = data[at : at + 64].split(b"\0", 1)[0].decode("ascii")
        start, stride, rows = struct.unpack_from("<III", data, at + 68)
        if not kind or not stride or start < 8 + count * 80 or start + rows * stride > len(data):
            raise FormatError("disk records outside table")
        result.append((kind, start, stride, rows))
    occupied = sorted((s, s + z * n) for _, s, z, n in result if n)
    if any(a[1] > b[0] for a, b in zip(occupied, occupied[1:])):
        raise FormatError("overlapping disk records")
    return result


def raw_text(data, pointer, floor):
    if not floor <= pointer < len(data):
        raise FormatError("disk text outside pool")
    end = data.find(b"\0", pointer)
    if end < 0:
        raise FormatError("unterminated disk text")
    return data[pointer:end].decode("utf-8")


def raw_tips(data):
    """Oracle preserves scalar metadata, resource selector and uint16 conditions.

    Uses a structured tuple instead of production SHA identities. IDs +0/+2
    alone repeat in the installed table; never align rows just by those IDs.
    """
    headers = raw_sections(data)
    if len(headers) != 1 or headers[0][0:1] != ("TipsTableData",):
        raise FormatError("unexpected Tips family")
    _, start, stride, count = headers[0]
    if stride != 56:
        raise FormatError("unexpected Tips stride")
    floor = start + stride * count
    rows = {}
    for number in range(count):
        at = start + number * stride
        (array,) = struct.unpack_from("<Q", data, at + 8)
        (size,) = struct.unpack_from("<I", data, at + 16)
        if size > 4096 or size and not floor <= array <= len(data) - size * 2:
            raise FormatError("Tips conditions outside pool")
        selector, title, body = [
            raw_text(data, struct.unpack_from("<Q", data, at + p)[0], floor) for p in (24, 40, 48)
        ]
        identity = (
            data[at : at + 8].hex(),
            data[at + 16 : at + 24].hex(),
            data[at + 32 : at + 40].hex(),
            selector,
            tuple(struct.unpack_from(f"<{size}H", data, array)),
        )
        if identity in rows:
            raise FormatError("duplicate full Tips record identity")
        rows[identity] = {
            "row": number,
            "ids": struct.unpack_from("<HH", data, at),
            "title": title,
            "body": body,
        }
    return rows


def audit(game, catalog, model):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    cached = json.loads(model.read_text("utf-8"))
    by_field = defaultdict(list)
    for e in entries:
        key = e["key"].split("/")
        if key[0] == "table" and key[-1] in ("title", "name", "body"):
            by_field[("/".join(key[:2]), key[-1])].append(e)
    inventory, gaps, tips = [], [], {}
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            for path, member in _logical_tables(archive).items():
                data = archive.read(member)
                if data[:4] != b"#TBL":
                    continue
                headers = raw_sections(data)
                floor = max(s + z * n for _, s, z, n in headers)
                for kind, start, stride, count in headers:
                    if kind not in FIELDS:
                        continue
                    expected, fields = FIELDS[kind]
                    # Known alternate FC schemas are outside this bounded audit.
                    if stride != expected:
                        inventory.append(
                            {
                                "language": language,
                                "path": path,
                                "kind": kind,
                                "excluded_stride": stride,
                            }
                        )
                        continue
                    if kind == "TipsTableData":
                        tips[language] = raw_tips(data)
                    counts = Counter(records=count, fields=count * len(fields))
                    for field, offset in fields.items():
                        admitted = {e["texts"].get(language) for e in by_field[(path, field)]}
                        for row in range(count):
                            (pointer,) = struct.unpack_from(
                                "<Q", data, start + row * stride + offset
                            )
                            text = raw_text(data, pointer, floor) if pointer else ""
                            if not text.strip():
                                counts["empty"] += 1
                                continue
                            counts["nonempty"] += 1
                            if text not in admitted:
                                counts["catalog_value_missing"] += 1
                                gaps.append(
                                    {
                                        "language": language,
                                        "path": path,
                                        "kind": kind,
                                        "row": row,
                                        "field": field,
                                        "source": text,
                                    }
                                )
                            elif language == "en":
                                counts[
                                    "global_denied"
                                    if text not in cached["pairs"]
                                    and text not in cached.get("plain_pairs", {})
                                    else "global_admitted"
                                ] += 1
                    inventory.append(
                        {
                            "language": language,
                            "path": path,
                            "kind": kind,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            **counts,
                        }
                    )
    identities = set(tips["en"])
    assert all(set(rows) == identities for rows in tips.values()), (
        "cross-locale Tips identity mismatch"
    )
    title_entries = by_field[("table/t_tips.tbl", "title")]
    body_entries = by_field[("table/t_tips.tbl", "body")]
    oracle_failures, title_paths = [], []
    for field, family in (("title", title_entries), ("body", body_entries)):
        raw_payloads = Counter(
            tuple(tips[l][identity][field] for l in tips) for identity in identities
        )
        catalog_payloads = Counter(tuple(e["texts"].get(l) for l in tips) for e in family)
        if raw_payloads != catalog_payloads:
            oracle_failures.append({"field": field, "stage": "eight_locale_payload_multiplicity"})
    for identity, row in tips["en"].items():
        for field, family in (("title", title_entries), ("body", body_entries)):
            expected = {l: values[identity][field] for l, values in tips.items()}
            exact = [e for e in family if e["texts"] == expected]
            if not exact:
                oracle_failures.append(
                    {
                        "ids": row["ids"],
                        "row": row["row"],
                        "field": field,
                        "exact_catalog_owners": len(exact),
                    }
                )
            if field == "title":
                source = row[field]
                title_paths.append(
                    {
                        "row": row["row"],
                        "ids": row["ids"],
                        "source": source,
                        "catalog_keys": [e["key"] for e in exact],
                        "pair": [expected["zh-Hans"], expected["ja"]],
                        "global_pair": cached["pairs"].get(source),
                        "plain_pair": cached.get("plain_pairs", {}).get(source),
                        "compiled_table_keys": [
                            c["key"]
                            for c in cached.get("table_identities", {})
                            .get("sources", {})
                            .get(source, [])
                        ],
                    }
                )
    return {
        "method": "independent raw offsets -> full Tips scalar/resource/condition tuples -> exact eight-language catalog payload",
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "inventory": inventory,
        "catalog_value_gaps": gaps,
        "tips_physical_records": {l: len(rows) for l, rows in tips.items()},
        "tips_oracle_failures": oracle_failures,
        "tips_title_paths": title_paths,
        "limits": [
            "Broader inventory proves literal field coverage, not cross-locale record association or UI reachability.",
            "Tips uses an independent complete metadata tuple and compares entire eight-language payloads, not model output.",
            "Cached model is exact accepted r14; no live label/process/configuration was read.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "model", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.game, args.catalog, args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "raw_fields": sum(r.get("nonempty", 0) for r in report["inventory"]),
                "value_gaps": len(report["catalog_value_gaps"]),
                "tips_oracle_failures": len(report["tips_oracle_failures"]),
                "tips_global_denied": sum(
                    not r["global_pair"] and not r["plain_pair"] for r in report["tips_title_paths"]
                ),
            }
        )
    )
    assert not report["tips_oracle_failures"]
