"""Read-only audit denominators. Raw fields, proven producers and projections stay separate."""

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_resource_inventory import catalog_inventory, indexed_text, text_call_reason
from sora_bilingual.localization.resources import (
    FpacArchive,
    _ARCHIVES,
    _logical_script_entries,
    parse_scp,
    assembled_dialogue,
)
from tools.audit_locale_coverage import scoped_records

LANGUAGES = ["en", "ja", "zh-Hans", "zh-Hant", "ko", "fr", "de", "es"]
OUT = ROOT / "generated/r27-association-audit"
HISTORICAL = ROOT / "generated/dev5-system-audit-20261005/resource-inventory-dev5-r12.json"


def read(path):
    return json.loads(Path(path).read_text("utf8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(name, data):
    path = OUT / name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf8")


def main():
    OUT.mkdir(exist_ok=True)
    raw_path = ROOT / "generated/r25-raw-entity-denominator.json"
    raw = read(raw_path)
    receipts = read(OUT / "builds/build001/receipts.json")
    signature = read(ROOT / "generated/r26-p0-local-production-receipt.json")["signature"]
    hashes = {row[0]: row[3] for row in signature["resources"]}
    for resource in raw["resources"]:
        assert hashes[Path(resource["file"]).name] == resource["sha256"]
    catalog_path = ROOT / "generated/r26-p0-local-production/catalog.json"
    catalog = read(catalog_path)
    entries = catalog["entries"]
    index, categories, _ = catalog_inventory(entries)
    entry_map = {entry["key"]: entry for entry in entries}
    old = read(ROOT / "generated/r25-producer-denominator.json")
    entities = {
        (case["entity"]["kind"], case["entity"]["physical_row"]): case["entity"]
        for case in old["cases"]
        if "entity" in case
    }
    records, raw_keys = [], set()
    for row in raw["rows"]:
        raw_keys.add(row["key"])
        entity = entities.get((row["kind"], row["row"]), {})
        records.append(
            {
                "id": f"raw/{row['kind']}/{row['section']}/{row['row']}/{row['field']}",
                "layer": "physical_item_skill_help_field",
                "resource_key": row["key"],
                "texts": row["texts"],
                "physical": {
                    key: row.get(key)
                    for key in (
                        "path",
                        "kind",
                        "section",
                        "row",
                        "entity_id",
                        "field",
                        "identity",
                        "raw_record_sha256",
                        "effect_slots",
                        "native_scalars",
                    )
                },
                "category": entity.get("category", "help_resource"),
                "ambiguous_locales": row.get("ambiguous_locales", {}),
                "entry_proof": "SHA-bound raw PAC field; replayed through product render with empty key/scope/owner. This field alone does not prove its complete SetText composition.",
                "input_class": "template_resource"
                if any(
                    re.search(r"%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdiufoxX]", value)
                    for value in row["texts"].values()
                )
                else "static_literal",
            }
        )
    raw_membership = [
        {
            "key": row["key"],
            "physical_id": f"{row['kind']}/{row['row']}/{row['field']}",
            "missing_locales": [
                language
                for language, value in row["texts"].items()
                if not indexed_text(index, row["key"], language, value)
            ],
        }
        for row in raw["rows"]
    ]
    # Complete final strings reconstructed from the audited native branch and the actual eight-language resources.
    p0 = read(ROOT / "generated/r26-p0-producers-after.json")
    for row in [r for r in p0["cases"] if r["locale"] == "en"]:
        name = row["name"]
        records.append(
            {
                "id": "producer/" + name,
                "layer": "proven_complete_p0_producer",
                "resource_key": "native-p0/" + name,
                "texts": row["texts"],
                "input_class": "static_native_composition",
                "category": "Tools" if not name.startswith("junior/") else "key_items",
                "physical": {
                    "item_id": 252 if name.startswith("junior/") else None,
                    "effect_id": 125
                    if name == "all_ep"
                    else 151
                    if name.startswith("permanent")
                    else None,
                },
                "entry_proof": "r26-p0-target-producer-report + native branch trace + eight-locale resource/parameter reconstruction; actual dynamic colour controls and live Rank remain uncaptured.",
                "proof_paths": [
                    "generated/r26-p0-target-producer-report.json",
                    "generated/r26-p0-producer-resources.json",
                    "generated/r26-p0-producers-after.json",
                ],
            }
        )
    # Catalogue projections are useful coverage, but are not a full raw-PAC denominator.
    scope = scoped_records(entries)
    scoped = (
        scope["complete_dialogue"]
        + scope["table_entries"]
        + [e for e in entries if e.get("display_role") in ("script_menu", "speaker", "popup_line")]
    )
    for entry in scoped:
        if entry["key"] in raw_keys:
            continue
        key = entry["key"]
        role = entry.get("display_role", "table")
        records.append(
            {
                "id": "projection/" + key,
                "resource_key": key,
                "texts": entry["texts"],
                "layer": "current_catalog_static_projection",
                "category": role,
                "input_class": "template_resource"
                if key.startswith("table/")
                and any(
                    re.search(r"%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdiufoxX]", value)
                    for value in entry["texts"].values()
                )
                else "static_literal",
                "physical": {
                    key: entry[key]
                    for key in (
                        "called_ids",
                        "table_rows",
                        "table_record_identities",
                        "book_id",
                        "book_pages",
                        "speaker_ids",
                    )
                    if key in entry
                },
                "entry_proof": "Current SHA-bound production catalog extractor projection, with argument fragments excluded and assembled_display preferred. Reachability/native context is not observed; projection counts do not equal physical calls or whole-game texts.",
            }
        )
    # Quarantine existing synthetic compositions without replacing their strings or expectations.
    invalid = []
    for row in old["cases"]:
        reasons = []
        if row["surface"] in ("item_category_header", "item_category_detail"):
            reasons.append(
                "legacy selector/category composition not proved to be the complete native input"
            )
        if row["surface"] == "effect_detail":
            reasons.append(
                "legacy outer colour/newline wrapper is a probe; native icon and branch reconstruction is incomplete"
            )
            for effect, *_ in row.get("entity", {}).get("effect_slots", []):
                if effect in (123, 125):
                    reasons.append(
                        "legacy type4 oracle emits percent unconditionally and omits actual icon/ALL branch"
                    )
                if effect in (150, 151, 152, 153, 154):
                    reasons.append(
                        "legacy metadata reads u16 rather than the evidenced u32 [0,1] array"
                    )
        if row["surface"] == "item_hint_node":
            reasons.append("constructed hint formatting lacks a captured complete native caller")
        if reasons:
            invalid.append(
                {
                    **row,
                    "oracle_status": "not_admitted_to_real_input_miss_denominator",
                    "reasons": sorted(set(reasons)),
                }
            )
    write(
        "quarantined-legacy-oracles.json",
        {
            "unchanged_original_cases": invalid,
            "counts": dict(Counter(row["surface"] for row in invalid)),
            "old_cases": len(old["cases"]),
            "old_plan_preservation_receipt": "generated/r26-p0-local-product-replay.json",
        },
    )
    # Targeted refresh of the old dynamic-call and eligible-slot findings; never rerun a full PAC scan.
    historical = read(HISTORICAL)
    old_unknown = historical["scripts"]["unassembled_text_calls"]
    eligible = [
        row
        for row in historical["scripts"]["omitted_slots"]
        if row[2] == "catalog_missing_eligible_call_slot"
    ]
    targets = defaultdict(list)
    for row in old_unknown:
        targets[(row["language"], "/".join(row["key"].split("/")[:3]))].append(("unassembled", row))
    for row in eligible:
        targets[(row[0], "/".join(row[1].split("/")[:3]))].append(("eligible_slot", row))
    archives, parsed, refreshed, eligible_results, failures = {}, {}, [], [], []
    game = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    try:
        for (language, logical), rows in targets.items():
            if language not in archives:
                archive = FpacArchive(game / "pac/steam" / _ARCHIVES[language])
                archives[language] = (archive, _logical_script_entries(archive))
            archive, paths = archives[language]
            data = archive.read(paths[logical])
            # Deduplicate byte-identical script parses; only targeted paths are read.
            data_hash = hashlib.sha256(data).hexdigest()
            if data_hash not in parsed:
                parsed[data_hash] = parse_scp(data)
            script = parsed[data_hash]
            for family, old_row in rows:
                key = old_row["key"] if family == "unassembled" else old_row[1]
                parts = key.split("/")
                function, ordinal = parts[3], int(parts[5])
                try:
                    call = script.functions[function].called[ordinal]
                    if family == "unassembled":
                        value = assembled_dialogue(call)
                        refreshed.append(
                            {
                                "language": language,
                                "key": key,
                                "reason": text_call_reason(call),
                                "args": call.args,
                                "historical_args_match": json.loads(json.dumps(call.args))
                                == old_row["args"],
                                "assembled_now": value,
                                "raw_script_sha256": data_hash,
                                "pac_sha256": hashes[_ARCHIVES[language]],
                                "status": "dynamic_producer_full_input_unknown"
                                if value is None
                                else "now_static_assembled",
                                "catalog_member": bool(
                                    value is not None
                                    and indexed_text(
                                        index, key + "/assembled_dialogue", language, value
                                    )
                                ),
                                "missing_evidence": "runtime variable/substitution operands and complete setter bytes; literal fragments are not final input"
                                if value is None
                                else None,
                            }
                        )
                    else:
                        slot = int(parts[7])
                        slots = dict(call.display_text_slots())
                        value = slots.get(slot)
                        eligible_results.append(
                            {
                                "language": language,
                                "key": key,
                                "historical_reason": old_row[2],
                                "historical_text": old_row[3],
                                "current_text": value,
                                "raw_current_match": value == old_row[3],
                                "current_catalog_member": indexed_text(index, key, language, value)
                                if value is not None
                                else False,
                                "raw_script_sha256": data_hash,
                                "call_kind": call.kind,
                                "call_target": call.target,
                                "call_args": call.args,
                                "display_status": "call string slot; display role/reachability not implied by parser slot",
                            }
                        )
                except (KeyError, IndexError, ValueError) as exc:
                    failures.append({"language": language, "key": key, "reason": str(exc)})
    finally:
        for archive, _ in archives.values():
            archive.close()
    write(
        "dynamic-script-producers.json",
        {
            "refresh_scope": "Only old 912 unassembled calls and 237 eligible omitted slots; targeted current PAC parses, not a full scan",
            "targeted_locale_files": len(targets),
            "unique_script_payloads": len(parsed),
            "calls": refreshed,
            "failures": failures,
            "counts": dict(Counter(row["status"] for row in refreshed)),
            "reason_counts": dict(Counter(row["reason"] for row in refreshed)),
        },
    )
    # Reevaluate the historical omitted-slot membership using current catalogue keys.
    historical_membership = Counter()
    for language, key, reason, text in historical["scripts"]["omitted_slots"]:
        historical_membership[
            (reason, "now_member" if indexed_text(index, key, language, text) else "still_absent")
        ] += 1
    inventory = {
        "catalog_sha256": digest(catalog_path),
        "catalog_entries": len(entries),
        "catalog_family_counts": categories,
        "raw_packet_sha256": digest(raw_path),
        "raw_resources_sha_match_sealed_build": True,
        "raw_field_membership": raw_membership,
        "raw_field_missing_membership_count": sum(
            bool(row["missing_locales"]) for row in raw_membership
        ),
        "historical_inventory": {
            "path": str(HISTORICAL),
            "sha256": digest(HISTORICAL),
            "catalog_and_extractor_stale": True,
            "resource_size_mtime_match": all(
                any(
                    r[0] == f["name"] and r[1] == f["bytes"] and r[2] == f["mtime_ns"]
                    for r in signature["resources"]
                )
                for f in historical["resource_files"]
            ),
            "historical_omitted_slots_current_catalog_membership": [
                {"old_reason": reason, "status": status, "count": count}
                for (reason, status), count in historical_membership.items()
            ],
            "limits": "Old omitted raw values retained; only selected calls reread. Code/argument identifiers, alignment singles and unrecognized pointer candidates cannot be counted as displayed untranslated texts.",
            "unrecognized_table_sections": historical["tables"].get("unrecognized_sections", []),
            "unknown_item_skill_sections": raw["unknown_sections_retained"],
        },
        "eligible_call_slot_refresh": eligible_results,
        "refresh_failures": failures,
    }
    write("inventory-extraction-diff.json", inventory)
    # Tools fixtures remain a separate probe layer until each inner effect is independently reconstructed.
    tools = read(ROOT / "generated/r26-tools-real-producer-fixtures.json")
    for row in [r for r in tools["rows"] if r["locale"] == "en"]:
        records.append(
            {
                "id": "probe/Tools/" + str(row["physical"]),
                "resource_key": row.get("body_key", "Tools/" + str(row["physical"])),
                "texts": row["texts"],
                "physical": {
                    k: row[k]
                    for k in (
                        "physical",
                        "mode",
                        "category",
                        "help_row",
                        "reason",
                        "range",
                        "flags",
                        "target",
                        "icon",
                    )
                    if k in row
                },
                "layer": "unqualified_tools_inner_effect_probe",
                "category": "Tools",
                "input_class": "composition_probe",
                "entry_proof": "Outer FORMAT1/FORMAT7 is traced. Inner effects derive from the legacy corpus; not a certified complete producer or real miss denominator.",
            }
        )
    counts = Counter(row["layer"] for row in records)
    packet = {
        "build_id": "build001",
        "source_languages": LANGUAGES,
        "primary": "ja",
        "secondary": "zh-Hans",
        "modes": ["primary", "secondary", "annotation"],
        "game_attached": False,
        "actual_setter_captured": False,
        "positive_identity_supplied": False,
        "denominator_layers": dict(counts),
        "records": records,
        "provenance": {
            "catalog_sha256": digest(catalog_path),
            "raw_packet_sha256": digest(raw_path),
            "p0_input_sha256": digest(ROOT / "generated/r26-p0-producers-after.json"),
            "signature": signature,
            "source_snapshot_sha256": receipts[0]["source_snapshot_sha256"],
        },
    }
    write("inputs.json", packet)
    print(
        json.dumps(
            {
                "layers": dict(counts),
                "raw_catalog_absences": inventory["raw_field_missing_membership_count"],
                "dynamic_calls": len(refreshed),
                "targeted_locale_files": len(targets),
                "refresh_failures": len(failures),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
