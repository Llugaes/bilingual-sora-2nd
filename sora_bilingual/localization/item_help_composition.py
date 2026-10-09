"""Fail-closed grammar for native item/skill help composition.

The raw tables contain metadata omitted from the display catalogue: effect
parameter types and native effect slots for every item and skill.  Skills
have five slots, as do item effect records; typed aggregate families remain
bounded separately from that raw storage capacity.  This module proves
constructor families from those actual groups before emitting a bounded
grammar.  It never crosses arbitrary ``%s`` records.
"""

from __future__ import annotations

import hashlib
from itertools import permutations
import json
from pathlib import Path
import re
import struct

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.menu_tables import record_identity, schema_for, sections
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables


class ItemHelpContractError(ValueError):
    """Installed resources no longer satisfy the audited builder contract."""


EFFECT_LAYOUTS = {
    "table/t_skill.tbl": ("SkillParam", 0x30, 5),
    "table/t_item.tbl": ("ItemTableData", 0x3C, 5),
}

# The raw SkillParam row exposes five 16-byte effect blocks at +0x30.
# The item normalizer at 0x23f010 reads the loaded ItemTableData row returned
# by 0x23ef20, copying +0x3c..+0x7c into the normalized five-slot record.
# Live ID 4050 and the raw PAC agree on the first two effects (1092, 1033).
# Keep speculative permutations bounded; actual native groups may use all five
# slots. The native grouping loop at 0x34b9ea..0x34bb26 accepts matching kinds
# and parameters across the remaining slots, including non-adjacent members.
MAX_RAW_GROUP_SLOTS = 5
MAX_TYPED_GROUP_SLOTS = 3


def _aggregate_sequences(members, groups, *, minimum=2, shared_values=True):
    """Bound permutations, then include wider groups proven by installed slots."""
    members = tuple(members)
    for length in range(minimum, min(MAX_TYPED_GROUP_SLOTS, len(members)) + 1):
        yield from permutations(members, length)
    wide = set()
    for group in groups:
        buckets = {}
        for slot in group:
            if slot[0] in members:
                key = slot[1:] if shared_values else ()
                buckets.setdefault(key, []).append(slot[0])
        for ids in buckets.values():
            if MAX_TYPED_GROUP_SLOTS < len(ids) <= MAX_RAW_GROUP_SLOTS:
                wide.add(tuple(ids))
    yield from sorted(wide)


# In ItemKindHelpData, the high word of the first scalar selects the item
# category. The seven elemental quartz label templates use categories 20..26.
# Their dynamic icon/count arguments remain owned by the native formatter.
ELEMENT_TITLE_KIND_BASE = 19
ELEMENT_TITLE_SELECTOR_MODE = 0x12
ELEMENT_TITLE_FLAGS = 8


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


def _status_fragments(catalogue, records, languages, help_titles=None):
    result = []
    for identity, metadata in sorted(records.items(), key=lambda row: row[1]["id"]):
        formats = _field(catalogue, "SkillItemStatusData", identity, "format", languages)
        texts = {}
        for language, value in formats.items():
            if value.count("%d") != 1 or "%" in value.replace("%d", ""):
                break
            texts[language] = value.replace("%d", "")
        else:
            # HelpIconList has layout scalars, not a stable cross-locale ID.
            # Admit only its actual titles equivalent to this identified stat
            # formatter: one terminal plus, with locale-specific glyph/spacing.
            # This never aligns help rows by ordinal or by translated wording.
            variants, provenance, display_texts = {}, {}, dict(texts)
            for language, fragment in texts.items():
                if not fragment.endswith("+"):
                    continue
                pattern = re.compile(
                    re.escape(fragment[:-1].rstrip(" \t\u3000")) + r"[ \t\u3000]*[+＋]"
                )
                matched = [
                    row
                    for row in (help_titles or {}).get(language, ())
                    if pattern.fullmatch(row["title"])
                ]
                if matched:
                    titles = sorted({row["title"] for row in matched})
                    # The status record identifies the stat; HelpIconList owns
                    # the displayed glyph. Its rows are locale-specific, so
                    # only a unique per-locale match may replace the output.
                    variants[language] = sorted({fragment, *titles})
                    provenance[language] = [row["row"] for row in matched]
                    if len(titles) == 1:
                        display_texts[language] = titles[0]
            result.append(
                {
                    "key": f"table/t_itemhelp.tbl/generated/status_fragment/{metadata['id']}",
                    "texts": display_texts,
                    "item_help_scope": "status",
                    "source_variants": variants,
                    "status_label_rows": provenance,
                }
            )
    return result


def _condition_list_entries(entries, catalogue, records, languages):
    """Effect 98 owns a condition-mask list, not an arbitrary printf string.

    Validate its raw ID/type and all three formatter fields. Names come only
    from ConditionInfoTableData; homographs in inventory are separate roles.
    """
    matches = [(identity, row) for identity, row in records.items() if row["id"] == 98]
    if not matches:
        return []
    identity, row = matches[0]
    fields = _record_fields(catalogue, identity, languages)
    if tuple(row["parameter_types"]) != (10,) or any(
        fields["format"][l] != "%s"
        or fields["name"][l].count("%s") != 1
        or not fields["name"][l].endswith("%s")
        or fields["name"][l][:-2].rstrip() != fields["stat"][l].rstrip()
        for l in languages
    ):
        raise ItemHelpContractError("condition-list formatter contract changed")
    names = [
        e["texts"]
        for e in entries
        if re.fullmatch(r"table/t_condition_info\.tbl/sha256:[^/]+/name", e.get("key", ""))
    ]
    if not names or any(not names_row.get(l) for names_row in names for l in languages):
        raise ItemHelpContractError("condition-list names incomplete")
    return [
        {
            "key": f"table/t_itemhelp.tbl/generated/condition_list/{row['id']}",
            "texts": fields["name"],
            "detail_only": True,
            "condition_list_contract": {
                "id": row["id"],
                "parameter_types": [10],
                "templates": fields["name"],
                "names": names,
                "links": _constant(catalogue, "LINK", languages),
                "percent": _constant(catalogue, "PERSENT", languages),
            },
        }
    ]


def _condition_parameter_entries(entries, fields, records, languages):
    """Bind native type 17's condition argument inside its complete formatter.

    0x34febb..0x34ff65 obtains ConditionHelpData with 0x256100 and passes
    its +0x10 condition field, then the numeric slot, to the name formatter.
    These enum values must never become global aliases for item homographs.
    """
    names = [
        e
        for e in entries
        if re.fullmatch(r"table/t_itemhelp\.tbl/sha256:[^/]+/condition", e.get("key", ""))
    ]
    generated = {}
    # Item panes may put a category's complete coloured hint in a separate
    # label. Bind that entire raw span in every locale, never individual words
    # or the surrounding category name. Conflicting complete hints stay denied.
    for entry in entries:
        key = entry.get("key", "")
        if not key.startswith("table/t_itemhelp.tbl/ItemKindHelpData/") or not key.endswith(
            "/description"
        ):
            continue
        hints = {}
        for language in languages:
            spans = re.findall(
                r"<[Cc][0-9a-fA-F]+>([^<>]+)</[Cc]>", entry.get("texts", {}).get(language, "")
            )
            if len(spans) != 1 or "%" in spans[0]:
                break
            hints[language] = spans[0]
        if len(hints) == len(languages):
            _add_unique(
                generated,
                hints,
                "item_category_hint",
                [],
                languages,
                resource_key=key,
                resource_field="description.coloured_hint",
            )
    for identity, row in records.items():
        if row["parameter_types"] != (17,) or identity not in fields:
            continue
        templates = fields[identity]["name"]
        if any(
            re.findall(r"%[sdiu]", templates[l]) != ["%s", "%d"]
            or "%" in templates[l].replace("%s", "").replace("%d", "").replace("%%", "")
            for l in languages
        ):
            raise ItemHelpContractError("condition-parameter formatter changed")
        if not names:
            raise ItemHelpContractError("condition-parameter names missing")
        for name in names:
            texts = name["texts"]
            if any(not texts.get(l) or re.search(r"[%<>\r\n]", texts[l]) for l in languages):
                raise ItemHelpContractError("condition-parameter name incomplete")
            _add_unique(
                generated,
                {l: templates[l].replace("%s", texts[l]) for l in languages},
                "condition_parameter",
                [row["id"]],
                languages,
                parameter_types=[17],
                condition_key=name["key"],
            )
    # Existing complete-constructor promotion exposes these as ordinary
    # candidates too. Only the bound sentence enters that model, never a name.
    return list(generated.values())


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


def _recovery_group(catalogue, fields, identities, languages, *, magnitude=None):
    """Build the native connection-13 stat/format phrase from ordered slots."""
    link = _constant(catalogue, "LINK", languages)
    percent = magnitude if magnitude is not None else _constant(catalogue, "PERSENT", languages)
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


def _revive_recovery(catalogue, fields, first_identity, magnitude, languages):
    """Build connection-kind 16's name + FORMAT8 + formatted recovery."""
    separator = _constant(catalogue, "FORMAT8", languages)
    first = fields[first_identity]
    result = {}
    for language in languages:
        name = first["name"][language]
        form = first["format"][language]
        value = magnitude[language]
        if (
            not name.strip()
            or "%" in name
            or form.count("%s") != 1
            or "%" in form.replace("%s", "")
            or not value.strip()
        ):
            raise ItemHelpContractError("revive recovery constructor fields changed")
        result[language] = name + separator[language] + form.replace("%s", value)
    return result


def _actual_connection_sequences(groups, members):
    """Mirror the native forward scan for a connection kind with equal arguments."""
    members = set(members)
    result = set()
    for group in groups:
        consumed = set()
        for index, slot in enumerate(group):
            if index in consumed or slot[0] not in members:
                continue
            selected = [slot]
            consumed.add(index)
            for following in range(index + 1, len(group)):
                candidate = group[following]
                if (
                    following not in consumed
                    and candidate[0] in members
                    and candidate[1:] == slot[1:]
                ):
                    selected.append(candidate)
                    consumed.add(following)
            result.add(tuple(selected))
    return result


# The live type-16 skill page proves `<I270>` after a stat. Keep that literal
# control token: target locales own the surrounding name/turn order, while the
# native icon is never translated or replaced with a Unicode lookalike. The
# separate `<I267>` observation is type10 with no turn contract, so it is not
# inferred into this family.
# Native connection kind 4 selects 0x10e/0x10f/0x110 for strength
# 1/2/3 (0x34c791..0x34c94d in the verified d8b2911d sample).
INLINE_TURN_ICONS = ("<I270>", "<I271>", "<I272>")


def _inline_icon_turn_texts(catalogue, identity, icon, languages):
    """Return one complete coloured type-16 effect segment with its native icon."""
    values = _aggregate_name(catalogue, (identity,), languages, literal_s=icon)
    return {language: f"<c698>{value}</C>" for language, value in values.items()}


def _add_unique(target, texts, family, ids, languages, **contract):
    identity = tuple(texts[language] for language in languages)
    if identity in target:
        return
    detail_inline_icon = bool(contract.pop("detail_inline_icon", False))
    source_variants = contract.pop("source_variants", None)
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
        **({"source_variants": source_variants} if source_variants else {}),
    }


def _element_title_entries(catalogue, element_titles, languages):
    """Extract the two literal labels; the native formatter owns its arguments.

    Labels are taken from aligned resource fields, not invented translations.
    Delimiter structure is checked for every locale before any row is emitted.
    Icon IDs, their count and ordering are irrelevant to translating these labels.
    """
    result = []
    template_shape = re.compile(
        r"(?P<element>[^【\[(:：<>%]+?)[ \t\u3000]*"
        r"(?P<opening>[【\[(])[ \t\u3000]*"
        r"(?P<value>[^:：<>%]+?)[ \t\u3000]*[:：][ \t\u3000]*"
        r"%s[ \t\u3000]*(?P<closing>[】\])])"
    )
    closing = {"【": "】", "[": "]", "(": ")"}
    for row in element_titles:
        key = row["description_key"]
        labels = {}
        for language in languages:
            template = catalogue.get(key, {}).get(language, "")
            match = template_shape.fullmatch(template)
            if match is None or closing[match["opening"]] != match["closing"]:
                raise ItemHelpContractError("element label template changed: " + key)
            labels[language] = (match["element"].strip(), match["value"].strip())
        for index, field in enumerate(("element", "value")):
            result.append(
                {
                    "key": key + "/label/" + field,
                    "texts": {language: labels[language][index] for language in languages},
                    "detail_only": True,
                    "detail_authority": True,
                    "detail_header_templates": catalogue[key],
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
    help_titles=None,
    connect_groups=None,
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
    # Native grouping is selected by SkillConnectListData, not by a shared
    # integer parameter or a coincidentally similar translated format.
    # The public low-level compiler also accepts metadata-only fixtures;
    # production always supplies the validated connection table.
    connection_kinds = None
    if connect_groups is not None:
        connection_kinds = {}
        # Native 345980 returns the first physical connection row. In
        # particular 95/96 occur in both kind10 and a later kind14 row.
        for row in connect_groups:
            for record_id in row["ids"]:
                connection_kinds.setdefault(record_id, row["kind"])
    chance = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and (connection_kinds is None or connection_kinds.get(value["id"]) == 7)
        and value["parameter_types"] == (1,)
        and _is_chance(fields[identity], languages)
    }
    turn = {
        value["id"]: identity
        for identity, value in metadata["SkillEffectHelpData"].items()
        if identity in fields
        and (connection_kinds is None or connection_kinds.get(value["id"]) == 4)
        and value["parameter_types"] == (16,)
        and _is_turn_stat(fields[identity], languages)
    }
    literal_clusters = {}
    for identity, value in metadata["SkillEffectHelpData"].items():
        if identity not in fields or value["parameter_types"]:
            continue
        key = _literal_cluster_key(fields[identity], languages)
        if connection_kinds is not None:
            kind = connection_kinds.get(value["id"])
            if kind not in (11, 12):
                continue
            key = (kind, key) if key is not None else None
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
            # Recognise the bounded leading group, not the entire raw tail.
            # A fourth/fifth effect does not undo prefix + two adjacent stats.
            and all(slot[0] in turn for slot in group[1:MAX_TYPED_GROUP_SLOTS])
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
        if any(any(slot[0] in cluster for slot in group) for group in groups)
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
    # The single-effect parameter dispatcher passes type 1's integer directly
    # to the complete name (0x34f259..0x34f292 in the current EXE). This owns
    # stat-less names such as reflect counts too; they are not role conflicts.
    # Type6's dispatcher (CAB62 0x34fa91) passes two integers. The second
    # getter explicitly selects slot3 for effect1046 (0x3531b9), proving
    # independent HP/EP percent and CP amount, including the gold doll.
    for identity, row in metadata["SkillEffectHelpData"].items():
        if row["id"] != 1046 or row["parameter_types"] != (6,) or identity not in fields:
            continue
        names = fields[identity]["name"]
        if all(
            names[l].count("%d") == 2 and "%" not in names[l].replace("%d", "").replace("%%", "")
            for l in languages
        ):
            _add_unique(
                generated,
                names,
                "before_ko_recovery",
                [row["id"]],
                languages,
                parameter_types=[6],
                arguments=["slot1", "slot3"],
            )
    for identity, row in metadata["SkillEffectHelpData"].items():
        if identity not in fields or row["parameter_types"] != (1,) or row["id"] in chance:
            continue
        names = fields[identity]["name"]
        if all(
            _one_field(names[l], "d") and "%" not in names[l].replace("%d", "").replace("%%", "")
            for l in languages
        ):
            _add_unique(
                generated,
                names,
                "numeric_single",
                [row["id"]],
                languages,
                parameter_types=[1],
                amount_argument="slot1",
            )
            # Screenshot-observed event display uses LINK in place of the
            # resource's FORMAT8. Bind the entire effect1016 template; never
            # split arbitrary comma phrases or admit the event prefix alone.
            if row["id"] == 1016 and source_language == "en":
                separator = _constant(catalogue, "FORMAT8", languages)
                link = _constant(catalogue, "LINK", languages)
                if names["en"].count(separator["en"]) == 1:
                    values = dict(names)
                    values["en"] = names["en"].replace(separator["en"], " " + link["en"] + " ")
                    _add_unique(
                        generated,
                        values,
                        "event_link_display",
                        [row["id"]],
                        languages,
                        parameter_types=[1],
                        amount_argument="slot1",
                        evidence="screenshot_display_variant_not_setter_capture",
                    )
    # Type12 substitutes the HP recovery magnitude into the complete name,
    # even when its stat field is empty. Current 0x34fb81..0x34fc2f selects
    # SMALL below 3000, MIDDLE below 4500, otherwise LARGE. This is a typed
    # constructor, not a grade word borrowed from another effect's stat.
    for identity, row in metadata["SkillEffectHelpData"].items():
        if identity not in fields or row["parameter_types"] != (12,):
            continue
        names = fields[identity]["name"]
        if not all(_one_field(names[l], "s") for l in languages):
            raise ItemHelpContractError("type12 recovery name changed")
        for constant, selector in (
            ("SMALL", "slot1 < 3000"),
            ("MIDDLE", "3000 <= slot1 < 4500"),
            ("LARGE", "slot1 >= 4500"),
        ):
            magnitude = _constant(catalogue, constant, languages)
            _add_unique(
                generated,
                {l: names[l].replace("%s", magnitude[l]) for l in languages},
                "recovery_magnitude_single",
                [row["id"]],
                languages,
                parameter_types=[12],
                magnitude_constant=constant,
                amount_argument="slot1",
                selector=selector,
            )

    # Type9 binds its complete name's one string slot to the upward direction
    # selected from slot1. CAB62 0x34ff95..0x3500b1 maps 0/1,2,3 to strength
    # 1,2,3; display kinds5/6 use Unicode arrows, others use I270/271/272.
    for identity, row in metadata["SkillEffectHelpData"].items():
        if identity not in fields or row["parameter_types"] != (9,):
            continue
        names = fields[identity]["name"]
        if not all(_one_field(names[l], "s") for l in languages):
            raise ItemHelpContractError("type9 direction name changed")
        for level in range(1, 4):
            for arrow in (f"<I{269 + level}>", "↑" * level):
                _add_unique(
                    generated,
                    {l: names[l].replace("%s", arrow) for l in languages},
                    "direction_single_up",
                    [row["id"]],
                    languages,
                    parameter_types=[9],
                    amount_argument="slot1",
                    strength_level=level,
                    selector="slot1 in (0,1)" if level == 1 else f"slot1 == {level}",
                    inline_icons=[arrow] if arrow.startswith("<I") else [],
                    detail_inline_icon=arrow.startswith("<I"),
                )

    # Types 11 (Delay's slot2 magnitude) and 13 use finite magnitude labels.
    # Reuse the exact admitted constants, never an arbitrary string parameter.
    for identity, row in metadata["SkillEffectHelpData"].items():
        if identity not in fields or row["parameter_types"] not in ((11,), (13,)):
            continue
        names = fields[identity]["name"]
        if (row["parameter_types"] == (13,) and not fields[identity]["stat"]) or not all(
            _one_field(names[l], "s") for l in languages
        ):
            continue
        for constant in ("MOSTSMALL", "SMALL", "MIDDLE", "LARGE", "MOSTLARGE"):
            magnitude = _constant(catalogue, constant, languages)
            _add_unique(
                generated,
                {l: names[l].replace("%s", magnitude[l]) for l in languages},
                "magnitude_single",
                [row["id"]],
                languages,
                parameter_types=list(row["parameter_types"]),
                magnitude_constant=constant,
                amount_argument="slot2" if row["parameter_types"] == (11,) else "slot1",
            )
    # Kind 1 joins SkillEffectHelpData.stat from the equal-argument forward
    # group, then its format and numeric slot. Unlike effect98, its argument
    # is not a ConditionInfo mask. Exact EXE formats at 0x34bc92/0x34bd06 are
    # %s「%s」%s and %s%s %s %d%%; the CJK format itself owns the number.
    for connection in connect_groups or ():
        if connection["kind"] != 1:
            continue
        members = connection["ids"]
        if any(i not in by_id or by_id[i][1]["parameter_types"] != (1,) for i in members):
            raise ItemHelpContractError("resist connection parameters changed")
        sequences = {(i,) for i in members}
        sequences.update(
            tuple(slot[0] for slot in group)
            for group in _actual_connection_sequences(raw_groups, members)
        )
        for ids in sorted(sequences):
            records = [fields[by_id[i][0]] for i in ids]
            if any(not record["stat"] or not record["format"] for record in records):
                raise ItemHelpContractError("resist connection fields missing")
            link = _constant(catalogue, "LINK", languages)
            texts = {}
            for l in languages:
                if len({record["format"][l] for record in records}) != 1:
                    raise ItemHelpContractError("resist connection formats differ")
                stat = link[l].join(record["stat"][l] for record in records)
                form = records[0]["format"][l]
                if l in ("ja", "zh-Hans", "zh-Hant", "ko"):
                    if not _one_field(form, "d"):
                        raise ItemHelpContractError("resist numeric format changed")
                    texts[l] = "「" + stat + "」" + form
                else:
                    if "%" in form:
                        raise ItemHelpContractError("resist literal format changed")
                    texts[l] = form + " " + stat + " %d%%"
            _add_unique(
                generated,
                texts,
                "resist_connection",
                ids,
                languages,
                parameter_types=[1],
                connect_kind=1,
                amount_argument="slot1",
                same_amount=True,
            )
    # A single type4 percentage uses format + stat too; its raw name can say
    # Heal while the actual builder says Recover. Cover the complete constructor.
    for record_id, identity in sorted(recovery.items()):
        _add_unique(
            generated,
            _recovery_group(catalogue, fields, (identity,), languages),
            "percent_recovery_single",
            [record_id],
            languages,
            parameter_types=[4],
            amount_argument="slot1",
        )
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

    # The single-effect path uses the same name/format and integer argument as
    # connection kind 7. Previously only aggregates carried the typed contract,
    # so an otherwise complete battle help constructor rejected its single
    # chance member (e.g. a numeric status probability). Admit the entire
    # resource family, with the same locale and native-type checks as groups.
    for record_id, identity in sorted(chance.items()):
        _add_unique(
            generated,
            _aggregate_name(catalogue, (identity,), languages),
            "chance_single",
            (record_id,),
            languages,
            parameter_types=[1],
            connect_kind=7,
        )
    if chance_proven:
        for ids in _aggregate_sequences(chance, raw_groups):
            _add_unique(
                generated,
                _aggregate_name(catalogue, tuple(chance[i] for i in ids), languages),
                "chance_group",
                ids,
                languages,
                parameter_types=[1],
            )
    # SkillConnectListData selects the native constructor independently from
    # each effect's parameter type. Branch 17 (0x34de3f) formats the first
    # effect's name, then each following stat + format, with separate numbers.
    # Read its members from the table; never enumerate translated effect names.
    independent_numeric_groups = set()
    for connection in connect_groups or ():
        if connection["kind"] != 17:
            continue
        members = tuple(connection["ids"])
        if not any(sum(slot[0] in members for slot in group) > 1 for group in groups):
            continue
        for ids in _aggregate_sequences(members, raw_groups, shared_values=False):
            records = [fields[by_id[record_id][0]] for record_id in ids]
            if any(not row["stat"] or not row["format"] for row in records):
                raise ItemHelpContractError("independent numeric constructor fields missing")
            if any(by_id[record_id][1]["parameter_types"] != (1,) for record_id in ids):
                raise ItemHelpContractError("independent numeric constructor parameters changed")
            texts = {}
            link = _constant(catalogue, "LINK", languages)
            for language in languages:
                parts = [records[0]["name"][language]] + [
                    row["stat"][language] + row["format"][language] for row in records[1:]
                ]
                if any(not _one_field(part, "d") for part in parts):
                    raise ItemHelpContractError("independent numeric constructor fields changed")
                texts[language] = link[language].join(parts)
            _add_unique(
                generated,
                texts,
                "independent_numeric_group",
                ids,
                languages,
                parameter_types=[1] * len(ids),
                connect_kind=17,
            )
            independent_numeric_groups.add(ids)

    # Connection kind 16 is the native revive/recovery constructor at
    # 0x34d933..0x34de3a. It writes the first record's name, FORMAT8 and the
    # first record's format. ID 121 selects one of exactly three magnitude
    # constants from slot1 (<3000 SMALL, <4500 MIDDLE, otherwise LARGE).
    # Other members substitute PERSENT; value 100 can instead select ALL at
    # runtime. Emit both proven 100 spellings and let the exact source choose.
    revive_members = set()
    for connection in connect_groups or ():
        if connection["kind"] != 16:
            continue
        members = tuple(connection["ids"])
        revive_members.update(members)
        for record_id in members:
            identity_and_value = by_id.get(record_id)
            if (
                not identity_and_value
                or identity_and_value[0] not in fields
                or identity_and_value[1]["parameter_types"] != (0, 0)
            ):
                raise ItemHelpContractError("revive recovery constructor parameters changed")
        for sequence in sorted(_actual_connection_sequences(raw_groups, members)):
            ids = tuple(slot[0] for slot in sequence)
            first_identity = by_id[ids[0]][0]
            if ids[0] == 121:
                for variant, constant, bounds in (
                    ("small", "SMALL", "slot1 < 3000"),
                    ("middle", "MIDDLE", "3000 <= slot1 < 4500"),
                    ("large", "LARGE", "slot1 >= 4500"),
                ):
                    _add_unique(
                        generated,
                        _revive_recovery(
                            catalogue,
                            fields,
                            first_identity,
                            _constant(catalogue, constant, languages),
                            languages,
                        ),
                        "revive_recovery",
                        ids,
                        languages,
                        connect_kind=16,
                        parameter_types=[[0, 0]] * len(ids),
                        amount_argument="slot1",
                        variant=variant,
                        selector=bounds,
                    )
            else:
                _add_unique(
                    generated,
                    _revive_recovery(
                        catalogue,
                        fields,
                        first_identity,
                        _constant(catalogue, "PERSENT", languages),
                        languages,
                    ),
                    "revive_recovery",
                    ids,
                    languages,
                    connect_kind=16,
                    parameter_types=[[0, 0]] * len(ids),
                    amount_argument="slot1",
                    variant="percent",
                )
                if sequence[0][1] == 100:
                    _add_unique(
                        generated,
                        _revive_recovery(
                            catalogue,
                            fields,
                            first_identity,
                            _constant(catalogue, "ALL", languages),
                            languages,
                        ),
                        "revive_recovery",
                        ids,
                        languages,
                        connect_kind=16,
                        parameter_types=[[0, 0]] * len(ids),
                        amount_argument="slot1",
                        variant="all",
                        selector="runtime flag false and slot1 == 100",
                    )
    if turn_groups:
        for ids in _aggregate_sequences(turn, raw_groups):
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
                    turn_argument="slot2",
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
        # The native connection formatter also handles one member. Its display
        # is stat + format, which need not equal the record's name (HP absorb).
        for length in range(1, min(max_group_slots, len(records)) + 1):
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
        for ids in _aggregate_sequences(cluster, raw_groups, shared_values=False):
            if len(ids) <= MAX_TYPED_GROUP_SLOTS:
                continue
            _add_unique(
                generated,
                _literal_group(catalogue, tuple(cluster[i] for i in ids), languages),
                "literal_stat_group",
                ids,
                languages,
                parameter_types=[],
            )
    timed_sequences = set()
    for group in groups:
        for slot in group:
            if slot[0] not in timed_labels:
                continue
            if connection_kinds is not None and connection_kinds.get(slot[0]) != 18:
                continue
            for companion in group:
                if companion[0] in duration_values:
                    timed_sequences.add((slot[0], companion[0]))
    for label_id, duration_id in sorted(timed_sequences):
        label, _duration = timed_labels[label_id], duration_values[duration_id]
        # The label's format owns locale punctuation/spacing.  The companion
        # record proves the duration argument, but German deliberately omits
        # this leading separator from its own display field.
        _add_unique(
            generated,
            {
                language: (
                    fields[label]["stat"][language]
                    if connection_kinds is not None
                    else fields[label]["name"][language]
                )
                + fields[label]["format"][language]
                for language in languages
            },
            "timed_literal",
            (label_id, duration_id),
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
            # Kind4's Western path concatenates stat, selected icon and the
            # raw turns field (0x34c6..0x34ca), rather than printf-ing name.
            # Admit that exact complete source too; no optional-whitespace rule
            # or unproved icon is introduced by the runtime matcher.
            if source_language == "en":
                values = _inline_icon_turn_texts(catalogue, turn[record_id], icon, languages)
                raw = fields[turn[record_id]]
                values[source_language] = (
                    "<c698>"
                    + raw["stat"][source_language]
                    + icon
                    + raw["turns"][source_language]
                    + "</C>"
                )
                _add_unique(
                    generated,
                    values,
                    "turn_stat_native_parts",
                    [record_id],
                    languages,
                    parameter_types=[16],
                    connect_kind=4,
                    turn_argument="slot2",
                    strength_argument="slot3",
                    inline_icons=[icon],
                    detail_inline_icon=True,
                )

    # Kind4/6 join the raw stat fields before the direction token. Kind4
    # then appends the raw turns field, without the name template's space
    # (CAB62 0x34d263..0x34d2f5). Prove aggregate membership with the actual
    # equal-argument forward scan, including single-member constructors.
    for connection in connect_groups or ():
        kind = connection["kind"]
        if kind not in (4, 6):
            continue
        members = connection["ids"]
        expected = (16,) if kind == 4 else (10,)
        if any(by_id[i][1]["parameter_types"] != expected for i in members):
            raise ItemHelpContractError("direction connection parameter changed")
        sequences = _actual_connection_sequences(raw_groups, members)
        for group in sorted(sequences):
            ids = tuple(slot[0] for slot in group)
            records = [fields[by_id[i][0]] for i in ids]
            if any(not r["stat"] for r in records):
                continue
            for level in range(1, 4):
                # Current EXE chooses I267/268/269 for downward strengths
                # 1/2/3 and I270/271/272 for upward strengths 1/2/3.
                for direction in (("up", 269, "↑"), ("down", 266, "↓")):
                    # Current native kind4 selects upward icons and kind6
                    # downward icons; these are distinct resource families.
                    is_down = kind == 6
                    if (direction[0] == "down") != is_down:
                        continue
                    for arrow in (f"<I{direction[1] + level}>", direction[2] * level):
                        values = _aggregate_name(
                            catalogue, tuple(by_id[i][0] for i in ids), languages, literal_s=arrow
                        )
                        if "en" in languages:
                            joined = _constant(catalogue, "LINK", languages)["en"].join(
                                r["stat"]["en"] for r in records
                            )
                            values["en"] = (
                                joined + arrow + (records[0]["turns"]["en"] if kind == 4 else "")
                            )
                        _add_unique(
                            generated,
                            {l: "<c698>" + v + "</C>" for l, v in values.items()},
                            "direction_native_group",
                            ids,
                            languages,
                            parameter_types=list(expected),
                            connect_kind=kind,
                            strength_level=level,
                            inline_icons=[arrow] if arrow.startswith("<I") else [],
                            detail_inline_icon=arrow.startswith("<I"),
                        )

    # Connection kind 2 joins each record's format (the stat name), then uses
    # the first record's stat template. Native 0x34bd71..0x34c20e passes turns,
    # joined names and the arrow in locale-dependent order. Bind string slots
    # now so the runtime only substitutes the numeric duration.
    for connection in connect_groups or ():
        if connection["kind"] != 2:
            continue
        members = set(connection["ids"])
        sequences = {
            tuple(slot[0] for slot in group if slot[0] in members) for group in raw_groups
        } - {()}
        for ids in sorted(sequences):
            rows = [fields[by_id[i][0]] for i in ids]
            if any(by_id[i][1]["parameter_types"] != (9,) for i in ids):
                raise ItemHelpContractError("critical connection parameter changed")
            for level in range(1, 4):
                for arrow in ("↑" * level, f"<I{269 + level}>"):
                    values = {}
                    for language in languages:
                        template = rows[0]["stat"][language]
                        if template.count("%d") != 1 or template.count("%s") != 2:
                            raise ItemHelpContractError("critical connection template changed")
                        joined = _constant(catalogue, "LINK", languages)[language].join(
                            row["format"][language] for row in rows
                        )
                        values[language] = (
                            template.replace("%s", joined, 1).replace("%s", arrow, 1).rstrip()
                        )
                    icon = arrow.startswith("<I")
                    _add_unique(
                        generated,
                        {l: f"<c698>{v}</C>" for l, v in values.items()} if icon else values,
                        "critical_turn_group",
                        ids,
                        languages,
                        turn_argument="slot2",
                        strength_level=level,
                        detail_inline_icon=icon,
                        **({"inline_icons": [arrow]} if icon else {}),
                    )

    # Status-panel/detail values use name + value, whereas the format field
    # omits the percentage suffix. Compile every numeric status row, not a
    # list of four labels from a screenshot.
    for identity, row in metadata["SkillItemStatusData"].items():
        names = _field(
            catalogue, "SkillItemStatusData", identity, "name", languages, required=False
        )
        values = _field(
            catalogue, "SkillItemStatusData", identity, "value", languages, required=False
        )
        if names and values and all(_one_field(values[l], "d") for l in languages):
            _add_unique(
                generated,
                {l: names[l] + values[l] for l in languages},
                "status_value",
                [row["id"]],
                languages,
                resource_kind="SkillItemStatusData",
                # Percentage glyph width does not change the status or its
                # value. Keep the official target glyph and admit the narrow
                # spelling only for this numeric percentage constructor.
                source_variants={
                    l: [(names[l] + values[l]).replace("％", "%%")]
                    for l in languages
                    if "％" in values[l]
                },
            )

    # The engine's explicit effect-97 branch appends its format to the shared
    # cure-debuff label with LINK (0x34e638..0x34e693). Keep the resource ID and
    # locale-owned strings; no translated-word exception belongs in the resolver.
    immune = by_id.get(97)
    cancel = catalogue.get("table/t_text.tbl/TXT_ITEM_HELP_DEBUFF_CANCEL")
    if (
        immune
        and cancel
        and all(l in cancel for l in languages)
        and any({96, 97}.issubset({s[0] for s in group}) for group in raw_groups)
    ):
        formats = fields[immune[0]]["format"]
        link = _constant(catalogue, "LINK", languages)
        _add_unique(
            generated,
            {l: cancel[l] + link[l] + formats[l] for l in languages},
            "debuff_cancel_immunity",
            [96, 97],
            languages,
        )
        _add_unique(
            generated,
            formats,
            "debuff_immunity_modifier",
            [97],
            languages,
            resource_field="format",
            native_effect_branch=97,
        )

    # Actual independent numeric + literal slot sequences own a complete
    # FORMAT8 header even when the resource description is blank. A turns
    # parameter homograph (CP/EP Regen) cannot veto that whole constructor.
    # Reuse proved type1/type4 displays and ordinary literal-name dispatch;
    # connection members never enter this independent-member composition.
    single_displays = {
        entry["item_help_contract"]["record_ids"][0]: entry["texts"]
        for entry in generated.values()
        if entry["item_help_contract"]["family"] in {"numeric_single", "percent_recovery_single"}
        and len(entry["item_help_contract"]["record_ids"]) == 1
    }
    separator = _constant(catalogue, "FORMAT8", languages)
    for group in groups:
        if not 2 <= len(group) <= MAX_TYPED_GROUP_SLOTS:
            continue
        members, arguments, has_numeric, has_literal = [], [], False, False
        for index, slot in enumerate(group):
            identity, row = by_id[slot[0]]
            kind = connection_kinds.get(slot[0]) if connection_kinds is not None else None
            parameters = tuple(row["parameter_types"])
            if parameters in {(1,), (4,)} and slot[0] in single_displays:
                if kind is not None and not (
                    kind == 13
                    and parameters == (4,)
                    and sum(connection_kinds.get(other[0]) == kind for other in group) == 1
                ):
                    break
                members.append(single_displays[slot[0]])
                arguments.append({"member_slot": index, "argument": "slot1"})
                has_numeric = True
            elif not parameters and kind is None:
                names = _literal_tail(fields.get(identity, {}), languages)
                if names is None:
                    break
                members.append(names)
                has_literal = True
            else:
                break
        else:
            if not has_numeric or not has_literal:
                continue
            texts = {l: separator[l].join(member[l] for member in members) for l in languages}
            if any(
                len(list(re.finditer(r"%[diug]", texts[l].replace("%%", "")))) != len(arguments)
                for l in languages
            ):
                continue
            _add_unique(
                generated,
                texts,
                "native_mixed_effect_sequence",
                [slot[0] for slot in group],
                languages,
                parameter_types=[list(by_id[slot[0]][1]["parameter_types"]) for slot in group],
                arguments=arguments,
                source="actual raw independent slot group + FORMAT8",
            )

    # Qualification prefixes are constructor roles, including their native
    # trailing padding. They enter only the detail translator/effect grammar.
    for key in ("MAIL_ONLY", "FEMAIL_ONLY"):
        values = catalogue.get("table/t_text.tbl/TXT_ITEM_HELP_" + key)
        if values and all(values.get(l) for l in languages):
            _add_unique(
                generated,
                values,
                "equipment_qualification",
                [],
                languages,
                resource_field="TXT_ITEM_HELP_" + key,
            )

    # Native target0x101 selects the entire SELF constant before a direction
    # field (CAB62 0x34cbd8/0x34ccb5/0x34d811/0x34dccd/0x34ed15). Bind it
    # to already-proved complete constructors, never to a word/prefix resolver.
    # Partial legacy catalogues may omit this optional constructor entirely.
    # A present constant still requires every locale; never invent a prefix.
    self_key = "table/t_text.tbl/TXT_ITEM_HELP_SELF"
    self_prefix = _constant(catalogue, "SELF", languages) if self_key in catalogue else None
    for entry in list(generated.values()) if self_prefix is not None else ():
        contract = entry["item_help_contract"]
        if contract["family"] not in {"direction_native_group", "direction_single_up"}:
            continue
        for framed in (False, True) if contract["family"] == "direction_single_up" else (False,):
            texts = {
                l: self_prefix[l]
                + (f"<c698>{entry['texts'][l]}</C>" if framed else entry["texts"][l])
                for l in languages
            }
            for display_space in (False, True) if source_language == "en" else (False,):
                values = dict(texts)
                if display_space:
                    values["en"] = self_prefix["en"] + " " + texts["en"][len(self_prefix["en"]) :]
                _add_unique(
                    generated,
                    values,
                    "self_direction_constructor",
                    contract["record_ids"],
                    languages,
                    parameter_types=contract["parameter_types"],
                    prefix_constant="SELF",
                    native_target_code=0x101,
                    base_family=contract["family"],
                    strength_level=contract["strength_level"],
                    display_space_evidence="user_visible_text_not_setter_capture"
                    if display_space
                    else "native_concatenation",
                    inline_icons=contract.get("inline_icons", []),
                    detail_inline_icon=bool(contract.get("inline_icons")),
                )

    status_entries = _status_fragments(
        catalogue, metadata["SkillItemStatusData"], languages, help_titles
    )
    element_entries = _element_title_entries(catalogue, element_titles, languages)
    # These are menu headers, not effect-detail aliases.  They share this
    # return collection only so existing callers include all generated rows.
    condition_entries = _condition_list_entries(
        entries, catalogue, metadata["SkillEffectHelpData"], languages
    )
    condition_parameters = _condition_parameter_entries(
        entries, fields, metadata["SkillEffectHelpData"], languages
    )
    detail_entries = [
        *generated.values(),
        *context_entries,
        *element_entries,
        *condition_entries,
        *condition_parameters,
    ]
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
        | revive_members
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
        if tuple(ids) in independent_literal_groups or tuple(ids) in independent_numeric_groups:
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
            "status_label_aliases": [
                {
                    "key": entry["key"],
                    "sources": entry["source_variants"],
                    "help_rows": entry["status_label_rows"],
                }
                for entry in status_entries
                if entry["source_variants"]
            ],
            "chance_records": len(chance),
            "turn_stat_records": len(turn),
            "turn_single_slot_records": len({slot[0] for slot in turn_slots}),
            "timed_label_records": len(timed_labels),
            "percent_recovery_records": len(recovery),
            "percent_recovery_groups_proven": len(set(recovery_groups)),
            "percent_recovery_headers_proven": len(set(recovery_header_groups)),
            "independent_numeric_groups_proven": len(independent_numeric_groups),
            "revive_recovery_records": len(revive_members),
            "revive_recovery_templates": sum(
                row["item_help_contract"]["family"] == "revive_recovery"
                for row in generated.values()
            ),
            "literal_clusters_proven": len(proven_literal_clusters),
            "prefix_records_proven": len(prefixes),
            "turn_stat_inline_icon_records": len(inline_turn_icon_records),
            "turn_stat_inline_icon_templates": len(inline_turn_icon_records)
            * len(INLINE_TURN_ICONS),
            "raw_description_contexts": len(context_entries),
            "element_title_templates": len(element_titles),
            "element_title_labels": len(element_entries),
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


def _iter_effect_groups(data, path, kind, offset, count):
    section = next(row for row in sections(data) if row[0] == kind)
    _, start, size, rows = section
    if size != schema_for(path, kind).size or offset + count * 16 > size:
        raise ItemHelpContractError(f"{kind} effect slot layout changed")
    for index in range(rows):
        group = []
        for slot in range(count):
            values = struct.unpack_from("<4I", data, start + index * size + offset + slot * 16)
            if values[0] == 0:
                continue
            group.append(values)
        if group:
            yield start + index * size, tuple(group)


def _read_effect_contexts(data, path, kind, offset, count):
    """Keep a raw effect group attached to its stable description resource ID."""
    schema = schema_for(path, kind)
    text_floor = max(at + stride * total for _, at, stride, total in sections(data))
    return tuple(
        {
            "description_key": f"{path}/{record_identity(data, at, kind, schema, text_floor)}/description",
            "group": [list(values) for values in group],
        }
        for at, group in _iter_effect_groups(data, path, kind, offset, count)
    )


def _read_element_title_contract(item_help, item_table):
    """Identify label templates by the item category, independent of icon data."""
    help_sections = sections(item_help)
    item_sections = sections(item_table)
    help_floor = max(start + size * count for _, start, size, count in help_sections)
    expected_categories = set(range(20, 27))

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
        }
    if set(result) != expected_categories:
        raise ItemHelpContractError("incomplete element title selectors")
    return tuple(result[category] for category in sorted(result))


def _read_help_titles(data):
    layout = sections(data)
    floor = max(start + size * count for _, start, size, count in layout)
    _, start, size, count = next(row for row in layout if row[0] == "HelpIconList")
    if size != 56:
        raise ItemHelpContractError("help title stride changed")
    result = []
    for index in range(count):
        pointer = struct.unpack_from("<Q", data, start + index * size + 8)[0]
        if not floor <= pointer < len(data):
            raise ItemHelpContractError("help title outside pool")
        end = data.find(b"\0", pointer)
        if end < 0:
            raise ItemHelpContractError("unterminated help title")
        result.append({"row": index, "title": data[pointer:end].decode("utf-8")})
    return result


def _read_connect_groups(data):
    layout = sections(data)
    floor = max(start + size * count for _, start, size, count in layout)
    _, start, size, count = next(row for row in layout if row[0] == "SkillConnectListData")
    if size != 24:
        raise ItemHelpContractError("effect connection stride changed")
    result = []
    for index in range(count):
        at = start + index * size
        kind = struct.unpack_from("<I", data, at)[0]
        pointer, total = struct.unpack_from("<QI", data, at + 8)
        if total > 204 or not floor <= pointer <= len(data) - total * 2:
            raise ItemHelpContractError("effect connection list outside pool")
        result.append({"kind": kind, "ids": list(struct.unpack_from(f"<{total}H", data, pointer))})
    return result


def _read_item_description_formats(data):
    """ItemTableData +232 is the format consumed by 0x347320's printf paths.

    Keep whole physical resource IDs; this does not authorize formatting a
    script, book, arbitrary label, or dynamically supplied format string.
    """
    path, kind = "table/t_item.tbl", "ItemTableData"
    layout = sections(data)
    _, start, size, count = next(row for row in layout if row[0] == kind)
    schema = schema_for(path, kind)
    if size != 256 or size != schema.size:
        raise ItemHelpContractError("item description format layout changed")
    floor = max(at + stride * total for _, at, stride, total in layout)
    return [
        {
            "key": f"{path}/{record_identity(data, start + i * size, kind, schema, floor)}/description",
            "id": struct.unpack_from("<I", data, start + i * size)[0],
            "formatter": "item_description_printf",
        }
        for i in range(count)
    ]


def compile_item_description_printf(entries, contracts, languages):
    """Zero-argument printf outputs; never discard actual dynamic parameters."""
    catalogue = _entry_map(entries)
    result, refusals = [], []
    for contract in contracts:
        key = contract.get("key", "")
        if contract.get("formatter") != "item_description_printf" or not re.fullmatch(
            r"table/t_item\.tbl/sha256:[^/]+/description", key
        ):
            continue
        values = catalogue.get(key, {})
        if not any("%%" in values.get(language, "") for language in languages):
            continue
        if any(not values.get(language) for language in languages):
            refusals.append({"key": key, "reason": "missing_description_locale"})
            continue
        if any("%" in values[language].replace("%%", "") for language in languages):
            refusals.append({"key": key, "reason": "dynamic_or_unsupported_description_printf"})
            continue
        raw = {language: values[language] for language in languages}
        result.append(
            {
                "key": key,
                "texts": {l: t.replace("%%", "%") for l, t in raw.items()},
                "printf_description_contract": {**contract, "raw_texts": raw, "slots": 0},
            }
        )
    return result, refusals


def _read_p0_producer_resources(item_help, item, quest):
    """Read only the audited mode0/type4, mode1/[0,1] and kind9 paths.

    The legacy metadata reader stays unchanged. CAB62 0x35041a reads mode1's
    parameter array with a four-byte stride; that proof does not apply globally.
    """

    def records(data, path, kind):
        layout = sections(data)
        _, start, size, count = next(row for row in layout if row[0] == kind)
        schema = schema_for(path, kind)
        if size != schema.size:
            raise ItemHelpContractError("P0 producer stride changed: " + kind)
        floor = max(at + stride * n for _, at, stride, n in layout)
        result = {}
        for physical in range(count):
            at = start + physical * size
            identifier = struct.unpack_from("<I", data, at)[0]
            result[identifier] = (at, record_identity(data, at, kind, schema, floor))
        return result, floor

    def string(data, at, floor):
        pointer = struct.unpack_from("<Q", data, at)[0]
        if not floor <= pointer < len(data):
            raise ItemHelpContractError("P0 producer string outside pool")
        end = data.find(b"\0", pointer, min(pointer + 2048, len(data)))
        if end < 0:
            raise ItemHelpContractError("P0 producer string exceeds budget")
        return data[pointer:end].decode("utf8", "strict")

    effects, effect_floor = records(item_help, "table/t_itemhelp.tbl", "SkillEffectHelpData")
    items, item_floor = records(item, "table/t_item.tbl", "ItemTableData")
    # Mode0 emits this record's icon before its complete name. Keep the
    # scalar contract separate from the legacy parameter decoder.
    effect_icons = {
        identifier: {
            "identity": identity,
            "format_mode": struct.unpack_from("<I", item_help, at + 28)[0],
            "icon": struct.unpack_from("<I", item_help, at + 64)[0],
        }
        for identifier, (at, identity) in effects.items()
    }
    effect_colours = {
        identifier: string(item_help, at + 48, effect_floor)
        for identifier, (at, _identity) in effects.items()
    }
    effects_out = {}
    expected_effects = [
        (120, (1, (0, 4), 347, 351)),
        (123, (0, (4,), 351, 0)),
        (125, (0, (4,), 352, 0)),
        (127, (1, (0, 1), 347, 351)),
    ]
    expected_effects.extend((i, (1, (0, 1), 0, 378 + i - 150)) for i in range(150, 155))
    for identifier, expected in expected_effects:
        at, identity = effects[identifier]
        pointer = struct.unpack_from("<Q", item_help, at + 16)[0]
        count, mode = struct.unpack_from("<II", item_help, at + 24)
        if count > 2 or not effect_floor <= pointer <= len(item_help) - count * 4:
            raise ItemHelpContractError("P0 producer parameter array outside pool")
        types = struct.unpack_from(f"<{count}I", item_help, pointer)
        icon, parameter_icon = struct.unpack_from("<II", item_help, at + 64)
        if (mode, types, icon, parameter_icon) != expected:
            raise ItemHelpContractError("P0 producer dispatch changed: " + str(identifier))
        effects_out[identifier] = {
            "identity": identity,
            "parameter_types_u32": types,
            "format_mode": mode,
            "icon": icon,
            "parameter_icon": parameter_icon,
            "fields": {
                field: string(item_help, at + offset, effect_floor)
                for field, offset in (("name", 8), ("stat", 32), ("format", 40))
            },
        }
    slots = set()
    for at, _ in items.values():
        for index in range(5):
            slot = struct.unpack_from("<4I", item, at + 0x3C + index * 16)
            if slot[0] in effects_out:
                slots.add(slot)
    junior_at, junior_identity = items[252]
    mode, category, third = struct.unpack_from("<BBH", item, junior_at + 40)
    _, start, size, count = next(row for row in sections(item_help) if row[0] == "ItemKindHelpData")
    selected = next(
        (
            start + i * size
            for i in range(count)
            if (selector := struct.unpack_from("<HHI", item_help, start + i * size))[:2]
            == (mode, category)
            and selector[2] in (0, third)
        ),
        None,
    )
    if selected is None or struct.unpack_from("<I", item_help, selected + 16)[0] != 9:
        raise ItemHelpContractError("Junior notebook no longer selects help kind9")
    rank_rows, rank_floor = records(quest, "table/t_quest.tbl", "QuestRankBefore")
    return {
        "effects": effects_out,
        "effect_icons": effect_icons,
        "effect_colours": effect_colours,
        "slots": sorted(slots),
        "junior": {
            "key": "table/t_item.tbl/" + junior_identity + "/description",
            "body": string(item, junior_at + 232, item_floor),
            "ranks": {
                identifier: {
                    "key": "table/t_quest.tbl/QuestRankBefore/" + identity + "/rank",
                    "text": string(quest, at + 8, rank_floor),
                }
                for identifier, (at, identity) in rank_rows.items()
            },
        },
    }


def _compile_p0_producers(entries, resources, languages):
    """Compile complete phrases and all installed imported ranks, without owners."""
    catalogue = _entry_map(entries)
    generated = {}
    first = resources[languages[0]]

    def aligned(key, raw):
        values = catalogue.get(key)
        if not values or any(values.get(l) != raw[l] for l in languages):
            raise ItemHelpContractError("P0 producer resource alignment changed: " + key)
        return {l: values[l] for l in languages}

    for identifier in (120, 123, 125, 127, *range(150, 155)):
        record = first["effects"][identifier]
        if any(
            resources[l]["effects"][identifier]["identity"] != record["identity"] for l in languages
        ):
            raise ItemHelpContractError("P0 effect identity differs across locales")
        fields = {
            field: aligned(
                "table/t_itemhelp.tbl/SkillEffectHelpData/" + record["identity"] + "/" + field,
                {l: resources[l]["effects"][identifier]["fields"][field] for l in languages},
            )
            for field in ("name", "stat", "format")
        }
        if identifier in (123, 125):
            if (identifier, 100, 0, 0) not in first["slots"] or any(
                not _one_field(fields["name"][l], "s") for l in languages
            ):
                raise ItemHelpContractError("Type4 recovery actual slot/name changed")
            magnitude = _constant(catalogue, "ALL", languages)
            icon = f"<I{record['icon']}>"
            # CAB62 connection-kind 13 reads format+0x28 and stat+0x20 for
            # ALL too (0x34db97..0x34dd05). The generic name+0x08 fallback
            # produces different EN/SC/TC wording and is not this producer.
            all_texts = _recovery_group(
                catalogue,
                {record["identity"]: fields},
                (record["identity"],),
                languages,
                magnitude=magnitude,
            )
            if all_texts is None:
                raise ItemHelpContractError("connection-13 ALL format changed")
            _add_unique(
                generated,
                {l: icon + all_texts[l] for l in languages},
                "p0_all_ep" if identifier == 125 else "native_all_hp",
                [identifier],
                languages,
                format_mode=0,
                parameter_types=[4],
                selector="slot1 == 100 and runtime flag false",
                inline_icons=[icon],
            )
            percent = _constant(catalogue, "PERSENT", languages)
            if not _is_percent_recovery(fields, percent, languages):
                raise ItemHelpContractError("Type4 recovery actual stat/format changed")
            # Both percentage and ALL select the same proven stat/format
            # branch; only the magnitude constant changes.
            percentage_texts = _recovery_group(
                catalogue, {record["identity"]: fields}, (record["identity"],), languages
            )
            _add_unique(
                generated,
                {l: icon + percentage_texts[l] for l in languages},
                "native_mode0_percent_recovery",
                [identifier],
                languages,
                format_mode=0,
                parameter_types=[4],
                amount_argument="slot1",
                inline_icons=[icon],
                detail_inline_icon=True,
            )
        elif identifier == 120:
            # Same mode1 stat/parameter fields as numeric revival, but its
            # second u32 enum is type4. The existing type4 branch supplies
            # PERSENT, or ALL for 100 with the runtime flag false.
            if any(
                "%" in fields["stat"][l] or not _one_field(fields["format"][l], "s")
                for l in languages
            ):
                raise ItemHelpContractError("Percent revival actual fields changed")
            icons = [f"<I{record['icon']}>", f"<I{record['parameter_icon']}>"]
            for variant, magnitude in (("percent", "PERSENT"), ("all", "ALL")):
                values = _constant(catalogue, magnitude, languages)
                for separator in (" ", " - "):
                    _add_unique(
                        generated,
                        {
                            l: icons[0]
                            + fields["stat"][l]
                            + separator
                            + icons[1]
                            + fields["format"][l].replace("%s", values[l])
                            for l in languages
                        },
                        "native_percent_revival",
                        [identifier],
                        languages,
                        format_mode=1,
                        parameter_types=[0, 4],
                        amount_argument="slot1",
                        variant=variant,
                        separator=separator,
                        inline_icons=icons,
                        detail_inline_icon=True,
                    )
        else:
            # 0x350195 emits stat first, then slot1 formatted by the second
            # uint32 parameter. +0x239 selects these two literal separators.
            if any(
                "%" in fields["stat"][l] or not _one_field(fields["format"][l], "d")
                for l in languages
            ):
                raise ItemHelpContractError("Permanent stat actual stat/format changed")
            icon = f"<I{record['parameter_icon']}>"
            leading_icon = f"<I{record['icon']}>" if record["icon"] else ""
            for separator in (" ", " - "):
                _add_unique(
                    generated,
                    {
                        l: leading_icon + fields["stat"][l] + separator + icon + fields["format"][l]
                        for l in languages
                    },
                    (
                        "p0_permanent_str"
                        if identifier == 151
                        else "native_numeric_revival"
                        if identifier == 127
                        else "native_permanent_stat"
                    ),
                    [identifier],
                    languages,
                    format_mode=1,
                    parameter_types=[0, 1],
                    amount_argument="slot1",
                    separator=separator,
                    inline_icons=[leading_icon, icon] if leading_icon else [icon],
                    detail_inline_icon=True,
                )
    junior = first["junior"]
    body = aligned(junior["key"], {l: resources[l]["junior"]["body"] for l in languages})
    if any(not _one_field(body[l], "s") for l in languages):
        raise ItemHelpContractError("Junior complete body printf changed")
    descriptions = []
    for identifier, rank in junior["ranks"].items():
        if any(set(resources[l]["junior"]["ranks"]) != set(junior["ranks"]) for l in languages):
            raise ItemHelpContractError("Imported Junior rank domain differs across locales")
        values = aligned(
            rank["key"], {l: resources[l]["junior"]["ranks"][identifier]["text"] for l in languages}
        )
        descriptions.append(
            {
                "key": junior["key"].removesuffix("/description")
                + "/imported_rank/"
                + str(identifier)
                + "/description",
                "texts": {l: body[l].replace("%s", values[l]) for l in languages},
                "junior_rank_contract": {
                    "item_id": 252,
                    "help_kind": 9,
                    "event_return": 2,
                    "body_key": junior["key"],
                    "rank_key": rank["key"],
                    "rank_id": identifier,
                },
            }
        )
    return [*generated.values(), *descriptions]


def _compile_native_effect_icons(entries, detail_entries, metadata, resources, languages):
    """Decorate already-proved complete mode0 constructors with their own icon.

    No arbitrary icon or parameter fragment gains an effect role. Multi-record
    joins keep the native per-member grammar instead of receiving a guessed
    outer icon. The unadorned entries remain available for existing inputs.
    """
    first = resources[languages[0]]["effect_icons"]
    if any(resources[l]["effect_icons"] != first for l in languages):
        raise ItemHelpContractError("native effect icon metadata differs across locales")
    catalogue = _entry_map(entries)
    generated = {}
    candidates = list(detail_entries)
    for identity, row in metadata["SkillEffectHelpData"].items():
        # A parameter-free complete name is already a constructor role.
        if row["parameter_types"]:
            continue
        key = "table/t_itemhelp.tbl/SkillEffectHelpData/" + identity + "/name"
        texts = catalogue.get(key)
        if texts and all(texts.get(l) and "%" not in texts[l] for l in languages):
            candidates.append(
                {"key": key, "texts": texts, "item_help_contract": {"record_ids": [row["id"]]}}
            )
    for entry in candidates:
        contract = entry.get("item_help_contract", {})
        ids = contract.get("record_ids", ())
        timed = contract.get("family") == "timed_literal" and len(ids) == 2
        if (len(ids) != 1 and not timed) or entry.get("detail_context_only"):
            continue
        record = first.get(ids[0])
        if not record or record["format_mode"] != 0 or not record["icon"]:
            continue
        # Type4 percentage uses stat/format, while ALL uses the complete name.
        # Both icon roles are compiled directly above from their raw fields.
        # Re-wrapping a generated percent template would normalize its printf
        # escapes twice and create a competing numeric target.
        if contract.get("family") == "percent_recovery_single" and ids[0] in (123, 125):
            continue
        if timed and (first[ids[1]]["format_mode"] != 0 or first[ids[1]]["icon"]):
            raise ItemHelpContractError("timed companion now emits an independent icon")
        icon = f"<I{record['icon']}>"
        # These constructors prepend something before the name, or already
        # contain the exact icon. Neither is a bare mode0 name constructor.
        if contract.get("family") in {"self_direction_constructor", "event_link_display"}:
            continue
        if any(icon in entry["texts"][l] for l in languages):
            continue
        _add_unique(
            generated,
            {l: icon + entry["texts"][l] for l in languages},
            "native_effect_icon",
            ids,
            languages,
            format_mode=0,
            base_constructor=entry["key"],
            inline_icons=[icon],
            detail_inline_icon=True,
        )
    return list(generated.values())


def _compile_deferred_cure_icons(entries, metadata, groups, connections, resources, languages):
    """Kind10 is a single, icon-bearing phrase appended after ordinary effects."""
    catalogue = _entry_map(entries)
    by_id = {value["id"]: identity for identity, value in metadata["SkillEffectHelpData"].items()}
    kinds = {}
    for row in connections:
        for identifier in row["ids"]:
            kinds.setdefault(identifier, row["kind"])
    members = {identifier for identifier, kind in kinds.items() if kind == 10}
    sequences = {tuple(slot[0] for slot in group if slot[0] in members) for group in groups}
    immune_sequences = {
        tuple(slot[0] for slot in group if slot[0] in members)
        for group in groups
        if any(slot[0] == 97 for slot in group)
    }
    sequences.discard(())
    generated = {}
    first = resources[languages[0]]["effect_icons"]
    colours = resources[languages[0]]["effect_colours"]
    cancel = _constant(catalogue, "DEBUFF_CANCEL", languages)
    for sequence in sorted(sequences):
        if len(sequence) > 2:
            raise ItemHelpContractError("kind10 cure group exceeds native two members")
        identifier = sequence[0]
        record = first[identifier]
        if record["format_mode"] != 0 or not record["icon"]:
            raise ItemHelpContractError("kind10 icon formatter changed")
        texts = (
            cancel
            if len(sequence) == 2
            else _field(catalogue, "SkillEffectHelpData", by_id[identifier], "name", languages)
        )
        colour = colours[identifier]
        if not re.fullmatch(r"<[Cc][0-9a-fA-F]+>", colour) or any(
            resources[l]["effect_colours"][identifier] != colour for l in languages
        ):
            raise ItemHelpContractError("kind10 native colour contract changed")
        icon = f"<I{record['icon']}>"
        for compact in (False, True):
            native_icon = f"<C9>{icon}</C>" if compact else icon
            for styled in (False, True):
                values = {
                    l: native_icon + (colour + texts[l] + "</C>" if styled else texts[l])
                    for l in languages
                }
                _add_unique(
                    generated,
                    values,
                    "native_deferred_cure",
                    sequence,
                    languages,
                    connect_kind=10,
                    physical_first_match=True,
                    deferred=True,
                    compact=compact,
                    styled=styled,
                    inline_icons=[icon],
                    detail_inline_icon=True,
                )
        if sequence in immune_sequences:
            # CAB62 34edc1..34ef30 appends 97 after the closed cure phrase.
            # r9=1 suppresses 97's own icon; ordinary r9=0 keeps that icon
            # before its independent colour, including the connection inside.
            immunity = _field(
                catalogue,
                "SkillEffectHelpData",
                by_id[97],
                "format" if len(sequence) == 2 else "name",
                languages,
            )
            link = _constant(catalogue, "LINK" if len(sequence) == 2 else "FORMAT8", languages)
            modifier = first[97]
            modifier_colour = colours[97]
            if any(
                resources[l]["effect_icons"][97] != modifier
                or resources[l]["effect_colours"][97] != modifier_colour
                for l in languages
            ):
                raise ItemHelpContractError("deferred immunity icon/colour differs across locales")
            modifier_icon = f"<I{modifier['icon']}>" if modifier["icon"] else ""
            for compact, styled in ((True, False), (False, False), (False, True)):
                native_icon = f"<C9>{icon}</C>" if compact else icon
                values = {
                    l: native_icon
                    + (colour + texts[l] + "</C>" if styled else texts[l])
                    + ("" if compact else modifier_icon)
                    + (modifier_colour if styled else "")
                    + link[l]
                    + immunity[l]
                    + ("</C>" if styled else "")
                    for l in languages
                }
                _add_unique(
                    generated,
                    values,
                    "native_deferred_cure_immunity",
                    (*sequence, 97),
                    languages,
                    connect_kind=10,
                    physical_first_match=True,
                    deferred=True,
                    compact=compact,
                    styled=styled,
                    inline_icons=[icon] + ([] if compact or not modifier_icon else [modifier_icon]),
                    detail_inline_icon=True,
                )
    return list(generated.values())


def read_item_help_contract(game, languages=None):
    """Read all typed records and raw PAC effect groups across installed locales."""
    game = Path(game)
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    if not languages or any(language not in LANGUAGES for language in languages):
        raise ItemHelpContractError("invalid item-help language set")
    per_language, groups_by_language, contexts_by_language, titles_by_language = {}, {}, {}, {}
    help_titles = {}
    connections_by_language = {}
    descriptions_by_language = {}
    p0_resources = {}
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
                connections_by_language[language] = _read_connect_groups(item_help)
                item_table = archive.read(logical["table/t_item.tbl"])
                p0_resources[language] = _read_p0_producer_resources(
                    item_help, item_table, archive.read(logical["table/t_quest.tbl"])
                )
                descriptions_by_language[language] = _read_item_description_formats(item_table)
                help_titles[language] = _read_help_titles(archive.read(logical["table/t_help.tbl"]))
                element_titles = _read_element_title_contract(item_help, item_table)
                effect_groups, effect_contexts = [], []
                for table_path, (kind, offset, count) in EFFECT_LAYOUTS.items():
                    table = archive.read(logical[table_path])
                    contexts = _read_effect_contexts(table, table_path, kind, offset, count)
                    effect_contexts.extend(contexts)
                    effect_groups.extend(
                        tuple(tuple(slot) for slot in context["group"]) for context in contexts
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
        if connections_by_language[language] != connections_by_language[languages[0]]:
            raise ItemHelpContractError("effect connection groups differ in " + language)
        if per_language[language] != first_metadata:
            raise ItemHelpContractError("item-help metadata differs in " + language)
        if groups_by_language[language] != first_groups:
            raise ItemHelpContractError("item/skill effect groups differ in " + language)
        if contexts_by_language[language] != first_contexts:
            raise ItemHelpContractError("item/skill effect contexts differ in " + language)
        if titles_by_language[language] != first_titles:
            raise ItemHelpContractError("element title contract differs in " + language)
        if descriptions_by_language[language] != descriptions_by_language[languages[0]]:
            raise ItemHelpContractError("item description identities differ in " + language)
    return (
        first_metadata,
        first_groups,
        {
            "metadata_languages": list(per_language),
            "_p0_producer_resources": p0_resources,
            "metadata_equal": True,
            "effect_groups_equal": True,
            "effect_contexts_equal": True,
            "element_title_contract_equal": True,
            "raw_effect_groups": len(first_groups),
            "_effect_contexts": first_contexts,
            "_element_titles": first_titles,
            "_help_titles": help_titles,
            "_connect_groups": connections_by_language[languages[0]],
            "_item_description_formats": descriptions_by_language[languages[0]],
        },
    )


def read_item_help_metadata(game, languages=None):
    metadata, _groups, audit = read_item_help_contract(game, languages)
    audit.pop("_effect_contexts", None)
    audit.pop("_element_titles", None)
    audit.pop("_help_titles", None)
    audit.pop("_connect_groups", None)
    audit.pop("_item_description_formats", None)
    return metadata, audit


def build_item_help_grammar(game, entries, source_language, languages=None):
    languages = tuple(dict.fromkeys(languages or LANGUAGES))
    metadata, groups, audit = read_item_help_contract(game, languages)
    contexts = audit.pop("_effect_contexts", ())
    element_titles = audit.pop("_element_titles", ())
    help_titles = audit.pop("_help_titles", {})
    connect_groups = audit.pop("_connect_groups", ())
    formats = audit.pop("_item_description_formats", ())
    p0_resources = audit.pop("_p0_producer_resources", {})
    result = compile_item_help_grammar(
        entries,
        source_language,
        metadata,
        groups,
        actual_contexts=contexts,
        element_titles=element_titles,
        help_titles=help_titles,
        connect_groups=connect_groups,
        languages=languages,
    )
    descriptions, refusals = compile_item_description_printf(entries, formats, languages)
    result["detail_entries"].extend(descriptions)
    # EventItemCheck's exact finite branch is already proved in all eight
    # shipped scripts. Revalidate only that function, never scan all scripts.
    from sora_bilingual.localization.resources import _logical_script_entries, parse_scp

    shape = (
        ("slot", 2, 1),
        ("push", "int", 90),
        ("op", 21),
        ("branch", 15, 10),
        ("push", "int", 1),
        ("byte", 10, 0),
        ("pop", 1),
        ("return",),
        ("slot", 2, 1),
        ("push", "int", 252),
        ("op", 21),
        ("branch", 15, 20),
        ("push", "int", 2),
        ("byte", 10, 0),
        ("pop", 1),
        ("return",),
        ("push", "int", -1),
        ("byte", 10, 0),
        ("pop", 1),
        ("return",),
    )
    for language in languages:
        with FpacArchive(Path(game) / "pac/steam" / archive_names("script")[language]) as archive:
            function = parse_scp(
                archive.read(_logical_script_entries(archive)["script/scena/system.dat"])
            ).functions["EventItemCheck"]
        if (
            function.flags != 0
            or tuple(function.arg_types) != (1,)
            or function.called
            or tuple(op for op in function.code_shape if op != ("line",)) != shape
        ):
            raise ItemHelpContractError("Junior EventItemCheck branch changed in " + language)
    p0_entries = _compile_p0_producers(entries, p0_resources, languages)
    result["detail_entries"].extend(p0_entries)
    result["detail_entries"].extend(
        _compile_deferred_cure_icons(
            entries, metadata, groups, connect_groups, p0_resources, languages
        )
    )
    icon_entries = _compile_native_effect_icons(
        entries, result["detail_entries"], metadata, p0_resources, languages
    )
    result["detail_entries"].extend(icon_entries)
    result["audit"]["native_effect_icons"] = {
        "compiled": len(icon_entries),
        "new_native_reads": 0,
        "source": "mode0 record icon + already-proved complete constructor",
    }
    result["audit"]["p0_producers"] = {
        "compiled": len(p0_entries),
        "locales": list(languages),
        "legacy_metadata_unchanged": True,
        "new_native_reads": 0,
    }
    result["audit"]["item_description_printf"] = {
        "physical_records": len(formats),
        "compiled": len(descriptions),
        "refusals": refusals,
        "literal_copy_entrance": "pending; raw escaped input is not normalized",
    }
    result["audit"].update(audit)
    return result
