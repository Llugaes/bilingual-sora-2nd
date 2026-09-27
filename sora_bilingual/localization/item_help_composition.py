"""Fail-closed grammar for native item/skill help composition.

The raw tables contain metadata omitted from the display catalogue: effect
parameter types and native effect slots for every item and skill.  Skills
have five slots while items have three; typed aggregate families remain
bounded separately from that raw storage capacity.  This module proves
constructor families from those actual groups before emitting a bounded
grammar.  It never crosses arbitrary ``%s`` records.
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
    "table/t_skill.tbl": ("SkillParam", 0x30, 5),
    "table/t_item.tbl": ("ItemTableData", 0x6C, 3),
}

# The raw SkillParam row exposes five 16-byte effect blocks at +0x30.
# The native normalizer uses an object-relative +0x3c address; its object
# base is not the #TBL record base, so this PAC reader stays on the verified
# row-relative offsets. Existing typed families are only proven for
# combinations of at most three effects; raw capacity must never widen their
# permutations.
MAX_RAW_GROUP_SLOTS = 5
MAX_TYPED_GROUP_SLOTS = 3

# In ItemKindHelpData, the high word of the first scalar selects the item
# category.  The seven elemental quartz rows use categories 20..26 and the
# same ordinal is stored as AttrData ID 1..7.  The bounded relation is admitted
# only with the complete raw templates and the captured native title shape;
# AttrData +4 supplies the icon retained in that shape.
ELEMENT_TITLE_KIND_BASE = 19
ELEMENT_TITLE_SELECTOR_MODE = 0x12
ELEMENT_TITLE_FLAGS = 8
ELEMENT_TITLE_NUMBER_KEY = "table/t_text.tbl/TXT_HUD_ITEM_NUM"


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


def _is_timed_label(fields, languages):
    """A literal label whose native format owns one duration parameter."""
    if not fields["format"]:
        return False
    for language in languages:
        name, form = fields["name"][language], fields["format"][language]
        if "%" in name or not _one_field(form, "d"):
            return False
    return True


def _is_duration_value(fields, languages):
    """The companion record carries the duration consumed by a timed label."""
    if not fields["format"]:
        return False
    for language in languages:
        name, form = fields["name"][language], fields["format"][language]
        if not _one_field(name, "d") or form != name:
            return False
    return True


def _is_percent_recovery(fields, percent, languages):
    """A type-4 effect whose native builder substitutes PERSENT into format."""
    if not fields["stat"] or not fields["format"]:
        return False
    for language in languages:
        stat, form, value = (
            fields["stat"][language],
            fields["format"][language],
            percent[language],
        )
        if (
            not stat.strip()
            or "%" in stat
            or form.count("%s") != 1
            or "%" in form.replace("%s", "")
            or not _one_field(value, "d")
        ):
            return False
    return True


def _recovery_group(catalogue, fields, identities, languages):
    """Build one native LINK + PERSENT recovery phrase from ordered slots."""
    link = _constant(catalogue, "LINK", languages)
    percent = _constant(catalogue, "PERSENT", languages)
    result = {}
    for language in languages:
        formats = {fields[identity]["format"][language] for identity in identities}
        if len(formats) != 1:
            return None
        form = next(iter(formats))
        stat = link[language].join(fields[identity]["stat"][language] for identity in identities)
        phrase = form.replace("%s", percent[language])
        result[language] = (
            stat + (" " if language == "ko" else "") + phrase
            if language in ("ja", "zh-Hans", "zh-Hant", "ko")
            else phrase + stat
        )
    return result


def _literal_tail(fields, languages):
    """Return a parameter-free display name that can follow a native recovery group."""
    names = fields["name"]
    if any(not names[language].strip() or "%" in names[language] for language in languages):
        return None
    return names


def _recovery_header(catalogue, recovery_texts, tails, languages):
    """Preserve a native whole header before slash/comma component splitting."""
    separator = _constant(catalogue, "FORMAT8", languages)
    return {
        language: separator[language].join(
            [recovery_texts[language], *(tail[language] for tail in tails)]
        )
        for language in languages
    }


# The live type-16 skill page proves `<I270>` after a stat. Keep that literal
# control token: target locales own the surrounding name/turn order, while the
# native icon is never translated or replaced with a Unicode lookalike. The
# separate `<I267>` observation is type10 with no turn contract, so it is not
# inferred into this family.
INLINE_TURN_ICONS = ("<I270>",)


def _inline_icon_turn_texts(catalogue, identity, icon, languages):
    """Return one complete coloured type-16 effect segment with its native icon."""
    values = _aggregate_name(catalogue, (identity,), languages, literal_s=icon)
    return {language: f"<c698>{value}</C>" for language, value in values.items()}


def _add_unique(target, texts, family, ids, languages, **contract):
    identity = tuple(texts[language] for language in languages)
    if identity in target:
        return
    detail_inline_icon = bool(contract.pop("detail_inline_icon", False))
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
        **({"detail_inline_icon": True} if detail_inline_icon else {}),
    }


def _element_title_entries(catalogue, element_titles, languages):
    """Compile the seven audited element-header formatters without free `%s`."""
    if not element_titles:
        return []
    number = catalogue.get(ELEMENT_TITLE_NUMBER_KEY)
    if not number or any(
        not (value := number.get(language))
        or value.count("%d") != 1
        or "%" in value.replace("%d", "")
        for language in languages
    ):
        raise ItemHelpContractError("element title count formatter changed")
    result = []
    for row in element_titles:
        if not isinstance(row, dict):
            raise ItemHelpContractError("invalid element title contract")
        key, category, attribute, icon = (
            row.get("description_key"),
            row.get("category"),
            row.get("attribute"),
            row.get("icon"),
        )
        if (
            not isinstance(key, str)
            or not all(
                isinstance(value, int) and value > 0 for value in (category, attribute, icon)
            )
            or category != ELEMENT_TITLE_KIND_BASE + attribute
        ):
            raise ItemHelpContractError("invalid element title selector")
        template = catalogue.get(key)
        if not template or any(
            not (value := template.get(language))
            or value.count("%s") != 1
            or "%" in value.replace("%s", "")
            for language in languages
        ):
            raise ItemHelpContractError("element title template changed: " + str(key))
        texts = {
            language: template[language].replace("%s", f"<I{icon}>" + number[language])
            for language in languages
        }
        result.append(
            {
                "key": key + "/generated/element-title",
                "texts": texts,
                "producer_origin": {
                    "family": "item_help_element_title",
                    "category": category,
                    "attribute": attribute,
                    "icon": icon,
                },
                "dynamic_producer": {
                    "family": "item_help_element_title",
                    "numbers": {language: ["ascii"] for language in languages},
                    "slots": [{"source": ELEMENT_TITLE_NUMBER_KEY, "kind": "int32"}],
                },
            }
        )
    return result


def compile_item_help_grammar(
    entries,
    source_language,
    metadata,
    actual_groups=(),
    *,
    actual_contexts=(),
    element_titles=(),
    max_group_slots=3,
    languages=None,
):
    """Compile every proven typed family, rejecting unproved constructors."""
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    if source_language not in languages or any(language not in LANGUAGES for language in languages):
        raise ItemHelpContractError("unknown source language: " + str(source_language))
    if max_group_slots != MAX_TYPED_GROUP_SLOTS:
        raise ItemHelpContractError("typed aggregate families require the audited three-slot bound")
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
        len(group) > MAX_RAW_GROUP_SLOTS or any(len(slot) != 4 for slot in group)
        for group in raw_groups
    ):
        raise ItemHelpContractError("effect group exceeds the audited native 16-byte slots")
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
    turn_slots = [
        slot for group in groups for slot in group if slot[0] in turn and 1 <= slot[3] <= 3
    ]
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
    timed_labels = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and not value["parameter_types"]
        and _is_timed_label(fields[identity], languages)
    }
    duration_values = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and value["parameter_types"] == (1,)
        and _is_duration_value(fields[identity], languages)
    }
    percent = _constant(catalogue, "PERSENT", languages)
    recovery = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and value["parameter_types"] == (4,)
        and _is_percent_recovery(fields[identity], percent, languages)
    }

    generated = {}
    context_entries = []
    context_seen = set()
    for context in actual_contexts:
        if not isinstance(context, dict):
            raise ItemHelpContractError("invalid raw effect context")
        description_key = context.get("description_key")
        group = tuple(tuple(map(int, slot)) for slot in context.get("group", ()))
        if (
            not isinstance(description_key, str)
            or any(len(slot) != 4 for slot in group)
            or 131 not in {slot[0] for slot in group}
        ):
            continue
        descriptions = catalogue.get(description_key)
        identity_and_value = by_id.get(131)
        if (
            not descriptions
            or any(not descriptions.get(language) for language in languages)
            or not identity_and_value
            or identity_and_value[1]["parameter_types"]
        ):
            continue
        identity, _value = identity_and_value
        names = _literal_tail(fields.get(identity, {}), languages)
        if names is None:
            continue
        signature = (description_key, tuple(names[language] for language in languages))
        if signature in context_seen:
            continue
        context_seen.add(signature)
        digest = hashlib.sha256(
            json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        context_entries.append(
            {
                "key": "table/t_itemhelp.tbl/generated/context/131/" + digest,
                "texts": {language: f"<c698>{names[language]}</C>" for language in languages},
                "detail_only": True,
                "detail_context_only": True,
                "detail_context_descriptions": descriptions,
                "item_help_contract": {
                    "family": "raw_description_context",
                    "record_ids": [131],
                    "description_key": description_key,
                    "raw_slots": [list(slot) for slot in group],
                },
            }
        )

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
    for record_id, level in sorted({(slot[0], slot[3]) for slot in turn_slots}):
        _add_unique(
            generated,
            _aggregate_name(catalogue, (turn[record_id],), languages, literal_s="↑" * level),
            "turn_stat_single",
            (record_id,),
            languages,
            parameter_types=[16],
            turn_argument="slot2",
            strength_argument="slot3",
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
    for group in groups:
        if len(group) != 2 or group[0][0] not in timed_labels or group[1][0] not in duration_values:
            continue
        label, _duration = timed_labels[group[0][0]], duration_values[group[1][0]]
        # The label's format owns locale punctuation/spacing.  The companion
        # record proves the duration argument, but German deliberately omits
        # this leading separator from its own display field.
        _add_unique(
            generated,
            {
                language: fields[label]["name"][language] + fields[label]["format"][language]
                for language in languages
            },
            "timed_literal",
            (group[0][0], group[1][0]),
            languages,
            parameter_types=[[], [1]],
            duration_argument="slot1",
        )
    recovery_groups = []
    recovery_header_groups = []
    for group in groups:
        selected = tuple(slot for slot in group if slot[0] in recovery)
        if len(selected) < 2 or len({slot[1] for slot in selected}) != 1:
            continue
        positions = [index for index, slot in enumerate(group) if slot[0] in recovery]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            continue
        ids = tuple(slot[0] for slot in selected)
        texts = _recovery_group(
            catalogue, fields, tuple(recovery[record_id] for record_id in ids), languages
        )
        if texts is None:
            continue
        _add_unique(
            generated,
            texts,
            "percent_recovery_group",
            ids,
            languages,
            parameter_types=[4] * len(ids),
            amount_argument="slot1",
            same_amount=True,
        )
        recovery_groups.append(ids)
        if positions != list(range(len(selected))):
            continue
        tails = []
        for slot in group[len(selected) :]:
            identity_and_value = by_id.get(slot[0])
            if not identity_and_value or identity_and_value[1]["parameter_types"]:
                break
            tail = fields.get(identity_and_value[0])
            if tail is None or (name := _literal_tail(tail, languages)) is None:
                break
            tails.append(name)
        else:
            if not tails:
                continue
            header_ids = tuple(slot[0] for slot in group)
            _add_unique(
                generated,
                _recovery_header(catalogue, texts, tails, languages),
                "percent_recovery_header",
                header_ids,
                languages,
                parameter_types=[4] * len(ids) + [[]] * len(tails),
                amount_argument="slot1",
                same_amount=True,
            )
            recovery_header_groups.append(header_ids)

    # The native details builder emits the type-16 arrow as an `<I270>` token,
    # splitting it from surrounding text before the ordinary component resolver
    # runs. Only records that occur in raw type-16 slots receive this bounded,
    # details-only inline template. The template captures the duration; an
    # input still has to contain this exact icon and coloured effect segment.
    inline_turn_icon_records = sorted({slot[0] for slot in turn_slots})
    for record_id in inline_turn_icon_records:
        for icon in INLINE_TURN_ICONS:
            _add_unique(
                generated,
                _inline_icon_turn_texts(catalogue, turn[record_id], icon, languages),
                "turn_stat_inline_icon",
                (record_id,),
                languages,
                parameter_types=[16],
                turn_argument="slot2",
                inline_icons=[icon],
                detail_inline_icon=True,
            )

    status_entries = _status_fragments(catalogue, metadata["SkillItemStatusData"], languages)
    element_entries = _element_title_entries(catalogue, element_titles, languages)
    # These are menu headers, not effect-detail aliases.  They share this
    # return collection only so existing callers include all generated rows.
    detail_entries = [*generated.values(), *context_entries, *element_entries]
    literal_group_candidates = {
        tuple(slot[0] for slot in group)
        for group in groups
        if len(group) > 1
        and all(
            (identity_and_value := by_id.get(slot[0]))
            and not identity_and_value[1]["parameter_types"]
            and (fields_for_id := fields.get(identity_and_value[0])) is not None
            and _literal_tail(fields_for_id, languages) is not None
            for slot in group
        )
    }
    unsupported_groups = set()
    known = (
        set(chance)
        | set(turn)
        | set(prefixes)
        | set(timed_labels)
        | set(duration_values)
        | set(recovery)
    )
    for group in recovery_header_groups:
        known.update(group)
    for cluster in proven_literal_clusters:
        known.update(cluster)
    # Keep this audit on the pre-existing unsupported denominator.  Literal groups
    # whose records are already covered by a typed family are not new findings.
    independent_literal_groups = {
        ids for ids in literal_group_candidates if any(record_id not in known for record_id in ids)
    }
    for group in groups:
        ids = [slot[0] for slot in group]
        if tuple(ids) in independent_literal_groups:
            continue
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
            "turn_single_slot_records": len({slot[0] for slot in turn_slots}),
            "timed_label_records": len(timed_labels),
            "percent_recovery_records": len(recovery),
            "percent_recovery_groups_proven": len(set(recovery_groups)),
            "percent_recovery_headers_proven": len(set(recovery_header_groups)),
            "literal_clusters_proven": len(proven_literal_clusters),
            "prefix_records_proven": len(prefixes),
            "turn_stat_inline_icon_records": len(inline_turn_icon_records),
            "turn_stat_inline_icon_templates": len(inline_turn_icon_records)
            * len(INLINE_TURN_ICONS),
            "raw_description_contexts": len(context_entries),
            "element_title_templates": len(element_entries),
            "detail_templates": len(detail_entries),
            "raw_slot_groups": len(raw_groups),
            "actual_groups": len(groups),
            "non_effect_union_rows": len(raw_groups) - len(groups),
            "independent_literal_groups": [list(ids) for ids in sorted(independent_literal_groups)],
            "unsupported_multi_record_groups": [list(ids) for ids in sorted(unsupported_groups)],
            "max_group_slots": max_group_slots,
            "max_raw_group_slots": MAX_RAW_GROUP_SLOTS,
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


def _read_effect_contexts(data, path, kind, offset, count):
    """Keep a raw effect group attached to its stable description resource ID."""
    section = next(row for row in sections(data) if row[0] == kind)
    _, start, size, rows = section
    schema = schema_for(path, kind)
    if size != schema.size or offset + count * 16 > size:
        raise ItemHelpContractError(f"{kind} effect slot layout changed")
    text_floor = max(at + stride * total for _, at, stride, total in sections(data))
    result = []
    for index in range(rows):
        at = start + index * size
        group = []
        for slot in range(count):
            values = struct.unpack_from("<4I", data, at + offset + slot * 16)
            if values[0]:
                group.append(values)
        if group:
            identity = record_identity(data, at, kind, schema, text_floor)
            result.append(
                {
                    "description_key": f"{path}/{identity}/description",
                    "group": [list(values) for values in group],
                }
            )
    return tuple(result)


def _read_element_title_contract(item_help, item_table, orbment):
    """Join the raw seven-category selector to AttrData's native icon ID."""
    help_sections = sections(item_help)
    item_sections = sections(item_table)
    orbment_sections = sections(orbment)
    help_floor = max(start + size * count for _, start, size, count in help_sections)
    orbment_floor = max(start + size * count for _, start, size, count in orbment_sections)
    _kind, attr_start, attr_size, attr_count = next(
        row for row in orbment_sections if row[0] == "AttrData"
    )
    attr_schema = schema_for("table/t_orbment.tbl", "AttrData")
    if attr_size != attr_schema.size:
        raise ItemHelpContractError("AttrData stride changed")
    attributes = {}
    for index in range(attr_count):
        at = attr_start + index * attr_size
        attribute, icon = struct.unpack_from("<II", orbment, at)
        identity = record_identity(orbment, at, "AttrData", attr_schema, orbment_floor)
        if attribute in attributes or not attribute or not icon:
            raise ItemHelpContractError("invalid AttrData element row")
        attributes[attribute] = {"icon": icon, "identity": identity}
    expected_categories = {ELEMENT_TITLE_KIND_BASE + attribute for attribute in attributes}
    if set(attributes) != set(range(1, 8)) or expected_categories != set(range(20, 27)):
        raise ItemHelpContractError("element AttrData domain changed")

    _kind, category_start, category_size, category_count = next(
        row for row in item_sections if row[0] == "ItemKindParam2"
    )
    category_schema = schema_for("table/t_item.tbl", "ItemKindParam2")
    if category_size != category_schema.size:
        raise ItemHelpContractError("ItemKindParam2 stride changed")
    category_ids = {
        struct.unpack_from("<I", item_table, category_start + index * category_size)[0]
        for index in range(category_count)
    }
    if not expected_categories <= category_ids:
        raise ItemHelpContractError("element item kinds changed")

    _kind, help_start, help_size, help_count = next(
        row for row in help_sections if row[0] == "ItemKindHelpData"
    )
    help_schema = schema_for("table/t_itemhelp.tbl", "ItemKindHelpData")
    if help_size != help_schema.size:
        raise ItemHelpContractError("ItemKindHelpData stride changed")
    result = {}
    for index in range(help_count):
        at = help_start + index * help_size
        selector = struct.unpack_from("<I", item_help, at)[0]
        category, mode = selector >> 16, selector & 0xFFFF
        flags = struct.unpack_from("<I", item_help, at + 16)[0]
        if category not in expected_categories:
            continue
        if mode != ELEMENT_TITLE_SELECTOR_MODE or flags != ELEMENT_TITLE_FLAGS:
            raise ItemHelpContractError("element title selector changed")
        identity = record_identity(item_help, at, "ItemKindHelpData", help_schema, help_floor)
        attribute = category - ELEMENT_TITLE_KIND_BASE
        if category in result:
            raise ItemHelpContractError("duplicate element title selector")
        result[category] = {
            "description_key": f"table/t_itemhelp.tbl/ItemKindHelpData/{identity}/description",
            "category": category,
            "attribute": attribute,
            "icon": attributes[attribute]["icon"],
            "attribute_key": f"table/t_orbment.tbl/AttrData/{attributes[attribute]['identity']}/name",
        }
    if set(result) != expected_categories:
        raise ItemHelpContractError("incomplete element title selectors")
    return tuple(result[category] for category in sorted(result))


def read_item_help_contract(game, languages=None):
    """Read all typed records and raw PAC effect groups across installed locales."""
    game = Path(game)
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    if not languages or any(language not in LANGUAGES for language in languages):
        raise ItemHelpContractError("invalid item-help language set")
    per_language, groups_by_language, contexts_by_language, titles_by_language = {}, {}, {}, {}
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
                item_table = archive.read(logical["table/t_item.tbl"])
                orbment = archive.read(logical["table/t_orbment.tbl"])
                element_titles = _read_element_title_contract(item_help, item_table, orbment)
                effect_groups, effect_contexts = [], []
                for table_path, (kind, offset, count) in EFFECT_LAYOUTS.items():
                    table = archive.read(logical[table_path])
                    effect_groups.extend(
                        _read_effect_groups(table, table_path, kind, offset, count)
                    )
                    effect_contexts.extend(
                        _read_effect_contexts(table, table_path, kind, offset, count)
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
            contexts_by_language[language] = tuple(effect_contexts)
            titles_by_language[language] = element_titles
        except (FormatError, KeyError, StopIteration, struct.error) as exc:
            raise ItemHelpContractError(f"cannot audit {language} item-help tables: {exc}") from exc
    first_metadata, first_groups = per_language[languages[0]], groups_by_language[languages[0]]
    first_contexts = contexts_by_language[languages[0]]
    first_titles = titles_by_language[languages[0]]
    for language in languages[1:]:
        if per_language[language] != first_metadata:
            raise ItemHelpContractError("item-help metadata differs in " + language)
        if groups_by_language[language] != first_groups:
            raise ItemHelpContractError("item/skill effect groups differ in " + language)
        if contexts_by_language[language] != first_contexts:
            raise ItemHelpContractError("item/skill effect contexts differ in " + language)
        if titles_by_language[language] != first_titles:
            raise ItemHelpContractError("element title contract differs in " + language)
    return (
        first_metadata,
        first_groups,
        {
            "metadata_languages": list(per_language),
            "metadata_equal": True,
            "effect_groups_equal": True,
            "effect_contexts_equal": True,
            "element_title_contract_equal": True,
            "raw_effect_groups": len(first_groups),
            "_effect_contexts": first_contexts,
            "_element_titles": first_titles,
        },
    )


def read_item_help_metadata(game, languages=None):
    metadata, _groups, audit = read_item_help_contract(game, languages)
    audit.pop("_effect_contexts", None)
    audit.pop("_element_titles", None)
    return metadata, audit


def build_item_help_grammar(game, entries, source_language, languages=None):
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    metadata, groups, audit = read_item_help_contract(game, languages)
    contexts = audit.pop("_effect_contexts", ())
    element_titles = audit.pop("_element_titles", ())
    result = compile_item_help_grammar(
        entries,
        source_language,
        metadata,
        groups,
        actual_contexts=contexts,
        element_titles=element_titles,
        languages=languages,
    )
    result["audit"].update(audit)
    return result
