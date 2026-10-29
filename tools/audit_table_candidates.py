"""Classify raw table string leads without calling them screen coverage.

Input is the independent PAC inventory. Every lead must retain a reason:
typed array/scalar, identical official content in every locale, or a reviewed
native-only label. New fields and changed native evidence remain unresolved.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

import pefile

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


ARRAYS = {
    ("ActiveVoiceTableData", 48): 2,
    ("ActiveVoiceTableData", 64): 2,
    ("ActiveVoiceTableData", 80): 2,
    ("ActiveVoiceTableData", 96): 4,
    ("NaviText", 24): 2,
    ("SkillEffectHelpData", 16): 2,
    ("TalkTableData", 24): 2,
    ("TalkTableData", 40): 2,
    ("NPCParam", 16): 2,
}
SCALARS = {("QuestTitle", 0), ("QuestText", 0), ("BooksText", 0)}
IDENTICAL = {
    ("VoiceTableData", 32),
    ("StatusParam", 416),
    ("SceneSkySetting", 8),
    ("CardBattlerMessage", 8),
    ("CardData", 8),
    ("CardEffectText", 8),
    ("CardEffectText", 16),
    ("LogText", 8),
    *(
        (kind + "PatternNameData", 8)
        for kind in (
            "Mouth",
            "EyeLids",
            "EyeDir",
            "EyeBrows",
            "FaceTexture",
            "EyeModify",
            "EyeBallSize",
        )
    ),
}


def native_contract(executable):
    contract = json.loads(
        Path(__file__).with_name("table_candidate_contracts.json").read_text("utf-8")
    )
    if executable is None:
        return {"passed": False, "reason": "native_evidence_not_supplied"}
    # A new consumer could be introduced outside the reviewed functions.
    # This is audit-evidence freshness, never the application's EXE gate.
    with Path(executable).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != contract["audited_executable_sha256"]:
        return {"passed": False, "reason": "executable_changed_requires_consumer_search"}
    with pefile.PE(str(executable), fast_load=True) as image:
        changed = [
            row["start"]
            for row in contract["regions"]
            if hashlib.sha256(image.get_data(row["start"], row["end"] - row["start"])).hexdigest()
            != row["sha256"]
        ]
    return {
        "passed": not changed,
        "regions": len(contract["regions"]),
        "changed": changed,
        "contract_sha256": hashlib.sha256(
            Path(__file__).with_name("table_candidate_contracts.json").read_bytes()
        ).hexdigest(),
    }


def audit(game, inventory, executable=None):
    groups = defaultdict(list)
    for row in inventory["tables"]["pointer_candidates"]:
        groups[row[1], row[2], row[5]].append(row)
    paths = {key[0] for key in groups}
    raw, values, failures = {}, defaultdict(dict), []
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_tables(archive)
            for path in sorted(paths):
                data = archive.read(logical[path])
                table_sections = sections(data)
                floor = max(
                    [8 + 80 * len(table_sections)]
                    + [at + size * n for _, at, size, n in table_sections]
                )
                occurrence = Counter()
                for kind, at, size, count in table_sections:
                    number = occurrence[kind]
                    occurrence[kind] += 1
                    for key in (k for k in groups if k[:2] == (path, kind)):
                        field = key[2]
                        decoded = []
                        for row in range(count):
                            record = at + row * size
                            pointer = struct.unpack_from("<Q", data, record + field)[0]
                            text = None
                            if floor <= pointer < len(data):
                                end = data.find(b"\0", pointer)
                                if end >= pointer:
                                    try:
                                        text = data[pointer:end].decode("utf-8")
                                    except UnicodeDecodeError:
                                        pass
                            decoded.append(text)
                            raw[locale, path, kind, number, row, field] = (
                                data,
                                record,
                                size,
                                floor,
                                text,
                            )
                        values[key].setdefault(locale, []).append(decoded)
    native = native_contract(executable)
    classified, unresolved = [], []
    for key, leads in sorted(groups.items()):
        path, kind, field = key
        reason = None
        evidence = {}
        if any(
            raw[locale, p, k, occurrence, row, offset][4] != text
            for locale, p, k, occurrence, row, offset, text in leads
        ):
            failures.append(
                {
                    "path": path,
                    "kind": kind,
                    "offset": field,
                    "reason": "inventory_resource_changed",
                }
            )
            continue
        if (kind, field) in ARRAYS:
            width = ARRAYS[kind, field]
            valid = True
            for locale, p, k, occurrence, row, offset, text in leads:
                data, at, size, floor, decoded = raw[locale, p, k, occurrence, row, offset]
                pointer, count = struct.unpack_from("<QQ", data, at + offset)
                if (
                    offset + 16 > size
                    or count > 4096
                    or not floor <= pointer <= len(data) - count * width
                    or decoded != text
                ):
                    valid = False
                    break
            if valid:
                reason = "typed_array_not_text"
                evidence = {"element_bytes": width, "count_offset": field + 8}
        elif (kind, field) in SCALARS:
            reason = "packed_record_identity_not_pointer"
        elif (kind, field) in IDENTICAL:
            localized = values[key]
            if len(localized) == 8 and all(v == localized["ja"] for v in localized.values()):
                reason = "official_content_identical_in_all_eight_locales"
                evidence = {"distinct_localized_versions": 1}
        elif (kind, field) == ("EventTableData", 32) and native["passed"]:
            reason = "event_label_without_display_read_in_reviewed_native_consumers"
            evidence = {"native_contract_sha256": native["contract_sha256"]}
        result = {
            "path": path,
            "kind": kind,
            "offset": field,
            "leads": len(leads),
            "per_locale": dict(Counter(r[0] for r in leads)),
            "reason": reason,
            "evidence": evidence,
        }
        (classified if reason else unresolved).append(result)
    return {
        "scope": "raw table pointer leads; classification is not an all-screen runtime guarantee",
        "game_started": False,
        "game_attached": False,
        "catalog_sha256": inventory["catalog_sha256"],
        "native": native,
        "candidate_count": sum(map(len, groups.values())),
        "candidate_groups": len(groups),
        "classified": classified,
        "unresolved": unresolved,
        "failures": failures,
        "all_classified": not unresolved and not failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes())
    result = audit(args.game, inventory, args.exe)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("classified", "unresolved")},
            ensure_ascii=False,
        )
    )
    print(json.dumps(result["unresolved"], ensure_ascii=False))
    return 0 if result["all_classified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
