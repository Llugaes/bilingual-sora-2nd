"""Fail-closed grammar for native item/skill help composition.

The raw tables contain metadata omitted from the display catalogue: effect
parameter types and three fixed effect slots for every item and skill.  This
module proves constructor families from those actual groups before emitting a
bounded grammar.  It never crosses arbitrary ``%s`` records.
"""

from __future__ import annotations

import hashlib
from itertools import permutations
import json
from pathlib import Path
import struct

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.menu_tables import record_identity, schema_for, sections
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables


class ItemHelpContractError(ValueError):
    """Installed resources no longer satisfy the audited builder contract."""


EFFECT_LAYOUTS = {
    "table/t_skill.tbl": ("SkillParam", 0x40, 3),
    "table/t_item.tbl": ("ItemTableData", 0x6C, 3),
}


def _normalise_metadata(metadata):
    result = {}
    for kind in ("SkillItemStatusData", "SkillEffectHelpData"):
        records = metadata.get(kind)
        if not records:
            raise ItemHelpContractError("missing metadata section: " + kind)
        result[kind] = {
            identity: {
                "id": int(value["id"]),
                "parameter_types": tuple(value.get("parameter_types", ())),
            }
            for identity, value in records.items()
        }
        ids = [value["id"] for value in result[kind].values()]
        if len(ids) != len(set(ids)):
            raise ItemHelpContractError(kind + " has duplicate record IDs")
    return result


def _entry_map(entries):
    result = {}
    for entry in entries:
        key = entry.get("key")
        if key in result:
            raise ItemHelpContractError("duplicate catalogue key: " + str(key))
        if key:
            result[key] = entry.get("texts", {})
    return result


def _field(catalogue, kind, identity, field, languages, *, required=True):
    key = f"table/t_itemhelp.tbl/{kind}/{identity}/{field}"
    texts = catalogue.get(key)
    if not texts:
        if not required:
            return None
        raise ItemHelpContractError("missing catalogue field: " + key)
    missing = [language for language in languages if not texts.get(language, "")]
    if missing:
        raise ItemHelpContractError(f"{key} missing locales: {missing}")
    return texts


def _constant(catalogue, name, languages):
    key = "table/t_text.tbl/TXT_ITEM_HELP_" + name
    texts = catalogue.get(key)
    if not texts or any(not texts.get(language, "") for language in languages):
        raise ItemHelpContractError("incomplete constructor constant: " + key)
    return texts


def _record_fields(catalogue, identity, languages):
    return {
        field: _field(
            catalogue, "SkillEffectHelpData", identity, field, languages, required=field == "name"
        )
        for field in ("name", "stat", "format", "turns")
    }


def _one_field(value, kind):
    other = "s" if kind == "d" else "d"
    return value.count("%" + kind) == 1 and "%" + other not in value


def _is_chance(fields, languages):
    if not fields["stat"] or not fields["format"]:
        return False
    for language in languages:
        name, stat, form = (
            fields["name"][language],
            fields["stat"][language],
            fields["format"][language],
        )
        if name.count(stat) != 1 or not _one_field(name, "d") or not _one_field(form, "d"):
            return False
    return True


def _is_turn_stat(fields, languages):
    if not fields["stat"] or not fields["format"] or not fields["turns"]:
        return False
    for language in languages:
        name, stat, form, turns = (
            fields["name"][language],
            fields["stat"][language],
            fields["format"][language],
            fields["turns"][language],
        )
        if (
            name.count(stat) != 1
            or name.count("%d") != 1
            or name.count("%s") != 1
            or form != "%s"
            or not _one_field(turns, "d")
        ):
            return False
    return True


def _literal_cluster_key(fields, languages):
    if not fields["stat"] or not fields["format"]:
        return None
    result = []
    for language in languages:
        name, stat, form = (
            fields["name"][language],
            fields["stat"][language],
            fields["format"][language],
        )
        if "%" in name + stat + form or name.count(stat) != 1 or not form.strip():
            return None
        result.append(form)
    return tuple(result)


def _status_fragments(catalogue, records, languages):
    result = []
    for identity, metadata in sorted(records.items(), key=lambda row: row[1]["id"]):
        formats = _field(catalogue, "SkillItemStatusData", identity, "format", languages)
        texts = {}
        for language, value in formats.items():
            if value.count("%d") != 1 or "%" in value.replace("%d", ""):
                break
            texts[language] = value.replace("%d", "")
        else:
            result.append(
                {
                    "key": f"table/t_itemhelp.tbl/generated/status_fragment/{metadata['id']}",
                    "texts": texts,
                    "item_help_scope": "status",
                }
            )
    return result


def _aggregate_name(catalogue, identities, languages, *, literal_s=None):
    link = _constant(catalogue, "LINK", languages)
    fields = [_record_fields(catalogue, identity, languages) for identity in identities]
    result = {}
    for language in languages:
        template = fields[0]["name"][language]
        first_stat = fields[0]["stat"][language]
        joined = link[language].join(row["stat"][language] for row in fields)
        if template.count(first_stat) != 1:
            raise ItemHelpContractError("aggregate stat is no longer unique")
        value = template.replace(first_stat, joined, 1)
        if literal_s is not None:
            if value.count("%s") != 1:
                raise ItemHelpContractError("turn aggregate lost its strength slot")
            value = value.replace("%s", literal_s)
        result[language] = value.rstrip()
    return result


def _literal_group(catalogue, identities, languages):
    link = _constant(catalogue, "LINK", languages)
    fields = [_record_fields(catalogue, identity, languages) for identity in identities]
    result = {}
    for language in languages:
        forms = {row["format"][language] for row in fields}
        if len(forms) != 1:
            raise ItemHelpContractError("literal group formats diverged")
        result[language] = (
            link[language].join(row["stat"][language] for row in fields) + next(iter(forms))
        ).rstrip()
    return result


def _add_unique(target, texts, family, ids, languages, **contract):
    identity = tuple(texts[language] for language in languages)
    if identity in target:
        return
    identity_contract = {"family": family, "record_ids": list(ids), **contract}
    digest = hashlib.sha256(
        json.dumps(identity_contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    target[identity] = {
        "key": (
            "table/t_itemhelp.tbl/generated/typed/"
            + family
            + "/"
            + "-".join(map(str, ids))
            + "/"
            + digest
        ),
        "texts": texts,
        "detail_authority": True,
        "detail_only": True,
        "item_help_contract": identity_contract,
    }


def compile_item_help_grammar(
    entries, source_language, metadata, actual_groups=(), *, max_group_slots=3, languages=None
):
    """Compile every proven typed family, rejecting unproved constructors."""
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    if source_language not in languages or any(language not in LANGUAGES for language in languages):
        raise ItemHelpContractError("unknown source language: " + str(source_language))
    if max_group_slots != 3:
        raise ItemHelpContractError("only the audited three-slot layouts are supported")
    metadata = _normalise_metadata(metadata)
    catalogue = _entry_map(entries)
    by_id = {
        value["id"]: (identity, value)
        for identity, value in metadata["SkillEffectHelpData"].items()
    }
    fields = {
        identity: _record_fields(catalogue, identity, languages)
        for identity in metadata["SkillEffectHelpData"]
        if f"table/t_itemhelp.tbl/SkillEffectHelpData/{identity}/name" in catalogue
    }
    chance = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and value["parameter_types"] == (1,)
        and _is_chance(fields[identity], languages)
    }
    turn = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and value["parameter_types"] == (16,)
        and _is_turn_stat(fields[identity], languages)
    }
    literal_clusters = {}
    for identity, value in metadata["SkillEffectHelpData"].items():
        if identity not in fields or value["parameter_types"]:
            continue
        key = _literal_cluster_key(fields[identity], languages)
        if key is not None:
            literal_clusters.setdefault(key, {})[value["id"]] = identity

    raw_groups = [tuple(tuple(map(int, slot)) for slot in group) for group in actual_groups]
    if any(
        len(group) > max_group_slots or any(len(slot) != 4 for slot in group)
        for group in raw_groups
    ):
        raise ItemHelpContractError("effect group exceeds the audited three 16-byte slots")
    groups = [group for group in raw_groups if all(slot[0] in by_id for slot in group)]
    chance_proven = any(sum(slot[0] in chance for slot in group) >= 2 for group in groups)
    turn_groups = [group for group in groups if sum(slot[0] in turn for slot in group) >= 2]
    levels = sorted(
        {
            slot[3]
            for group in turn_groups
            for slot in group
            if slot[0] in turn and 1 <= slot[3] <= 3
        }
    )
    prefixes = {}
    for group in groups:
        if (
            len(group) >= 3
            and group[0][0] not in turn
            and all(slot[0] in turn for slot in group[1:])
        ):
            prefix = by_id.get(group[0][0])
            if prefix and prefix[0] in fields and not prefix[1]["parameter_types"]:
                prefix_fields = fields[prefix[0]]
                if all(
                    prefix_fields["name"].get(language)
                    and not any(x in prefix_fields["name"][language] for x in ("%d", "%s"))
                    for language in languages
                ):
                    prefixes[group[0][0]] = prefix[0]
    proven_literal_clusters = [
        cluster
        for cluster in literal_clusters.values()
        if len(cluster) >= 2
        and any(sum(slot[0] in cluster for slot in group) >= 2 for group in groups)
    ]

    generated = {}
    if chance_proven:
        for length in range(2, max_group_slots + 1):
            for ids in permutations(chance, length):
                _add_unique(
                    generated,
                    _aggregate_name(catalogue, tuple(chance[i] for i in ids), languages),
                    "chance_group",
                    ids,
                    languages,
                    parameter_types=[1],
                )
    if turn_groups:
        for length in range(2, max_group_slots + 1):
            for ids in permutations(turn, length):
                for level in levels:
                    _add_unique(
                        generated,
                        _aggregate_name(
                            catalogue, tuple(turn[i] for i in ids), languages, literal_s="↑" * level
                        ),
                        "turn_stat_group",
                        ids,
                        languages,
                        parameter_types=[16],
                        strength_level=level,
                    )
    separator = _constant(catalogue, "FORMAT8", languages)
    for prefix_id, prefix_identity in prefixes.items():
        prefix_names = fields[prefix_identity]["name"]
        for ids in permutations(turn, max_group_slots - 1):
            for level in levels:
                tail = _aggregate_name(
                    catalogue, tuple(turn[i] for i in ids), languages, literal_s="↑" * level
                )
                _add_unique(
                    generated,
                    {
                        language: prefix_names[language] + separator[language] + tail[language]
                        for language in languages
                    },
                    "literal_plus_turn_group",
                    (prefix_id, *ids),
                    languages,
                    parameter_types=[[], [16], [16]],
                    strength_level=level,
                )
    for cluster in proven_literal_clusters:
        unique = {}
        for record_id, identity in cluster.items():
            # Some records reserve padding at the outer edge of the stat
            # field. LINK owns the following boundary, so this padding is not
            # semantic. Deduplicate by the boundary-normalized signature but
            # keep the first record's original text as the emitted target.
            stat_identity = tuple(
                fields[identity]["stat"][language].rstrip() for language in languages
            )
            unique.setdefault(stat_identity, (record_id, identity))
        records = list(unique.values())
        for length in range(2, min(max_group_slots, len(records)) + 1):
            for selected in permutations(records, length):
                ids = tuple(row[0] for row in selected)
                _add_unique(
                    generated,
                    _literal_group(catalogue, tuple(row[1] for row in selected), languages),
                    "literal_stat_group",
                    ids,
                    languages,
                    parameter_types=[],
                )

    status_entries = _status_fragments(catalogue, metadata["SkillItemStatusData"], languages)
    detail_entries = list(generated.values())
    unsupported_groups = set()
    known = set(chance) | set(turn) | set(prefixes)
    for cluster in proven_literal_clusters:
        known.update(cluster)
    for group in groups:
        ids = [slot[0] for slot in group]
        if len(ids) > 1 and any(record_id not in known for record_id in ids):
            unsupported_groups.add(tuple(ids))
    return {
        "status_entries": status_entries,
        "detail_entries": detail_entries,
        "audit": {
            "source_language": source_language,
            "raw_status_records": len(metadata["SkillItemStatusData"]),
            "raw_effect_records": len(metadata["SkillEffectHelpData"]),
            "status_families": len(status_entries),
            "chance_records": len(chance),
            "turn_stat_records": len(turn),
            "literal_clusters_proven": len(proven_literal_clusters),
            "prefix_records_proven": len(prefixes),
            "detail_templates": len(detail_entries),
            "raw_slot_groups": len(raw_groups),
            "actual_groups": len(groups),
            "non_effect_union_rows": len(raw_groups) - len(groups),
            "unsupported_multi_record_groups": [list(ids) for ids in sorted(unsupported_groups)],
            "max_group_slots": max_group_slots,
            "arbitrary_printf_products": 0,
            "typed_products_only": True,
        },
    }


def _read_effect_groups(data, path, kind, offset, count):
    section = next(row for row in sections(data) if row[0] == kind)
    _, start, size, rows = section
    if size != schema_for(path, kind).size or offset + count * 16 > size:
        raise ItemHelpContractError(f"{kind} effect slot layout changed")
    result = []
    for index in range(rows):
        group = []
        for slot in range(count):
            values = struct.unpack_from("<4I", data, start + index * size + offset + slot * 16)
            if values[0] == 0:
                continue
            group.append(values)
        if group:
            result.append(tuple(group))
    return tuple(result)


def read_item_help_contract(game, languages=None):
    """Read all typed records and actual three-slot groups across eight locales."""
    game = Path(game)
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    if not languages or any(language not in LANGUAGES for language in languages):
        raise ItemHelpContractError("invalid item-help language set")
    per_language, groups_by_language = {}, {}
    names = archive_names("table")
    for language in languages:
        filename = names[language]
        path = game / "pac/steam" / filename
        if not path.is_file():
            raise ItemHelpContractError("missing table archive: " + str(path))
        try:
            with FpacArchive(path) as archive:
                logical = _logical_tables(archive)
                item_help = archive.read(logical["table/t_itemhelp.tbl"])
                effect_groups = []
                for table_path, (kind, offset, count) in EFFECT_LAYOUTS.items():
                    table = archive.read(logical[table_path])
                    effect_groups.extend(
                        _read_effect_groups(table, table_path, kind, offset, count)
                    )
            table_sections = sections(item_help)
            text_floor = max(start + size * count for _, start, size, count in table_sections)
            found = {"SkillItemStatusData": {}, "SkillEffectHelpData": {}}
            for kind in found:
                _, start, size, count = next(row for row in table_sections if row[0] == kind)
                schema = schema_for("table/t_itemhelp.tbl", kind)
                if size != schema.size:
                    raise ItemHelpContractError(kind + " stride changed")
                for index in range(count):
                    at = start + index * size
                    identity = record_identity(item_help, at, kind, schema, text_floor)
                    record_id = struct.unpack_from("<I", item_help, at)[0]
                    parameter_types = ()
                    if kind == "SkillEffectHelpData":
                        pointer = struct.unpack_from("<Q", item_help, at + 16)[0]
                        parameter_count = struct.unpack_from("<I", item_help, at + 24)[0]
                        if parameter_count > 16 or (
                            parameter_count
                            and not text_floor <= pointer <= len(item_help) - parameter_count * 2
                        ):
                            raise ItemHelpContractError("effect parameter array outside table")
                        parameter_types = (
                            tuple(struct.unpack_from(f"<{parameter_count}H", item_help, pointer))
                            if parameter_count
                            else ()
                        )
                    found[kind][identity] = {"id": record_id, "parameter_types": parameter_types}
            per_language[language] = _normalise_metadata(found)
            groups_by_language[language] = tuple(effect_groups)
        except (FormatError, KeyError, StopIteration, struct.error) as exc:
            raise ItemHelpContractError(f"cannot audit {language} item-help tables: {exc}") from exc
    first_metadata, first_groups = per_language[languages[0]], groups_by_language[languages[0]]
    for language in languages[1:]:
        if per_language[language] != first_metadata:
            raise ItemHelpContractError("item-help metadata differs in " + language)
        if groups_by_language[language] != first_groups:
            raise ItemHelpContractError("item/skill effect groups differ in " + language)
    return (
        first_metadata,
        first_groups,
        {
            "metadata_languages": list(per_language),
            "metadata_equal": True,
            "effect_groups_equal": True,
            "raw_effect_groups": len(first_groups),
        },
    )


def read_item_help_metadata(game, languages=None):
    metadata, _groups, audit = read_item_help_contract(game, languages)
    return metadata, audit


def build_item_help_grammar(game, entries, source_language, languages=None):
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    metadata, groups, audit = read_item_help_contract(game, languages)
    result = compile_item_help_grammar(
        entries, source_language, metadata, groups, languages=languages
    )
    result["audit"].update(audit)
    return result
