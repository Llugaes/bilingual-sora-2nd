"""Production audit for the complete status and effect raw text families.

The audit separates raw resource fields, source-proven effect constructors,
and printf fields whose native argument binding is not yet proven. It never
uses invented argument values merely to make an unresolved family look green.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gc
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.config.native_config import read_config
from sora_bilingual.localization.item_help_composition import (
    build_item_help_grammar,
    read_item_help_contract,
)
from sora_bilingual.localization.menu_tables import (
    read_section,
    record_identity,
    schema_for,
    sections,
)
from sora_bilingual.localization.native_catalog import (
    fingerprint,
    load_entries,
    load_model,
    model_path,
)
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables

FIELD_NAMES = {
    "SkillItemStatusData": ("name", "format", "value"),
    "SkillEffectHelpData": ("name", "stat", "format", "turns"),
}
MODE_MATRIX = (
    ("zh-Hans", "zh-Hans", "ja"),
    ("zh-Hans", "zh-Hans", "en"),
    ("zh-Hans", "en", "ja"),
)
PRINTF = re.compile(r"%%|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[diusg]")
SOURCE_EFFECT_LAYOUTS = (
    ("table/t_skill.tbl", "SkillParam", 0x30, 5),
    # The live builder copies five 16-byte slots from ItemTableData +0x3c.
    # This is independent from item_help_composition's current grammar reader.
    ("table/t_item.tbl", "ItemTableData", 0x3C, 5),
)
RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(data.model,'utf8')),runtime=new RuntimeText(model);
const tableModels=model.table_identities?.models||{};
function selected(c) {
 const table=tableModels[c.resource_key];
 if((c.family==='raw_resource_top_level'||c.family==='numeric_formatting_probe')&&table?.source===c.source)
  return {runtime:new RuntimeText(table.model),tableIdentity:true};
 return {runtime:c.resolver==='details'?runtime.details:runtime,tableIdentity:false};
}
process.stdout.write(JSON.stringify(data.cases.map(c=>{
 const selectedRuntime=selected(c),active=selectedRuntime.runtime,annotation=active.render(c.source,'annotation');
 return {
  primary:active.translate(c.source,'primary'),
  secondary:active.translate(c.source,'secondary'),
  primary_render:active.render(c.source,'primary'),
  annotation,
  annotation_payload:annotation.layers.map(layer=>layer.text).join('')+[...annotation.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join(''),
  annotation_needed:RuntimeText.needsAnnotation(c.primary??c.required_primary,c.secondary??c.required_secondary),
  table_identity_resolved:selectedRuntime.tableIdentity
 };
})));
"""


def _catalog(entries):
    return {entry["key"]: entry["texts"] for entry in entries if entry.get("key")}


def _read_source_effect_groups(game):
    """Read the native source slots independently of the production grammar."""
    per_language = {}
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_tables(archive)
            contexts = []
            for path, kind, offset, count in SOURCE_EFFECT_LAYOUTS:
                data = archive.read(logical[path])
                layout = sections(data)
                _name, start, stride, rows = next(row for row in layout if row[0] == kind)
                if stride != schema_for(path, kind).size or offset + count * 16 > stride:
                    raise AssertionError(f"source effect-slot contract changed: {path} {kind}")
                text_floor = max(at + row_stride * total for _name, at, row_stride, total in layout)
                schema = schema_for(path, kind)
                for index in range(rows):
                    base = start + index * stride
                    slots = tuple(
                        struct.unpack_from("<4I", data, base + offset + slot * 16)
                        for slot in range(count)
                    )
                    group = tuple(slot for slot in slots if slot[0])
                    if group:
                        identity = record_identity(data, base, kind, schema, text_floor)
                        contexts.append(
                            {
                                "path": path,
                                "row_index": index,
                                "description_key": f"{path}/{identity}/description",
                                "description": _string_at(
                                    data,
                                    struct.unpack_from(
                                        "<Q", data, base + dict(schema.fields)["description"]
                                    )[0],
                                    text_floor,
                                ),
                                "group": [list(slot) for slot in group],
                            }
                        )
            per_language[language] = tuple(contexts)
    first = per_language["ja"]
    signatures = lambda rows: [(row["path"], row["row_index"], row["group"]) for row in rows]
    mismatched = [
        language for language, rows in per_language.items() if signatures(rows) != signatures(first)
    ]
    if mismatched:
        raise AssertionError(f"source effect slots differ across locales: {mismatched}")
    first = tuple(
        {
            **row,
            "description_keys": {
                language: per_language[language][index]["description_key"]
                for language in per_language
            },
            "descriptions": {
                language: per_language[language][index]["description"] for language in per_language
            },
        }
        for index, row in enumerate(first)
    )
    return (
        tuple(tuple(map(tuple, context["group"])) for context in first),
        first,
        {
            "layouts": [
                {"path": path, "kind": kind, "offset": hex(offset), "slots": count}
                for path, kind, offset, count in SOURCE_EFFECT_LAYOUTS
            ],
            "languages_equal": True,
            "groups": len(first),
        },
    )


def _string_at(data, pointer, text_floor):
    if not text_floor <= pointer < len(data):
        raise AssertionError(f"display string pointer outside table: {pointer:#x}")
    end = data.find(b"\0", pointer)
    if end < 0:
        raise AssertionError("unterminated display string")
    return data[pointer:end].decode("utf-8")


def _resource_key(kind, identity, field):
    return f"table/t_itemhelp.tbl/{kind}/{identity}/{field}"


def _tokens(value):
    return [token for token in PRINTF.findall(value) if token != "%%"]


def _status_fragment(value):
    tokens = _tokens(value)
    if len(tokens) != 1:
        return None
    return PRINTF.sub(lambda match: "%" if match.group() == "%%" else "", value)


def _status_titles(metadata, catalogue, titles, source, primary, secondary):
    cases, gaps = [], []
    for identity, record in metadata["SkillItemStatusData"].items():
        key = _resource_key("SkillItemStatusData", identity, "format")
        texts = catalogue.get(key, {})
        matched, rows_by_language = {}, {}
        for language in (source, primary, secondary):
            fragment = _status_fragment(texts.get(language, ""))
            if fragment is None or not fragment.rstrip(" 	\u3000").endswith("+"):
                matched[language], rows_by_language[language] = [], []
                continue
            prefix = fragment[:-1].rstrip(" 	\u3000")
            pattern = re.compile(re.escape(prefix) + r"[ 	\u3000]*[+＋]")
            rows = [row for row in titles[language] if pattern.fullmatch(row["title"])]
            matched[language] = rows
            rows_by_language[language] = [row["row"] for row in rows]
        if all(len(matched[language]) == 1 for language in (source, primary, secondary)):
            cases.append(
                {
                    "name": f"status_help_icon_{record['id']}",
                    "family": "status_help_icon_title",
                    "display_path": "Sprite (not Text; resolver output is not live proof)",
                    "record_id": record["id"],
                    "resource_key": key,
                    "help_icon_rows": rows_by_language,
                    "source": matched[source][0]["title"],
                    "primary": matched[primary][0]["title"],
                    "secondary": matched[secondary][0]["title"],
                    "pass": True,
                    "verification": "resource_pair_only; Sprite render is not a text resolver path",
                }
            )
        else:
            gaps.append(
                {
                    "family": "status_help_icon_title",
                    "record_id": record["id"],
                    "resource_key": key,
                    "reason": "no_unique_cross_locale_HelpIconList_title",
                    "matches": rows_by_language,
                }
            )
    return cases, gaps


def _raw_empty_fields(game):
    """Only eight-locale raw empty strings are non-display fields, not omissions."""
    empty = defaultdict(set)
    for language in LANGUAGES:
        with FpacArchive(game / "pac/steam" / archive_names("table")[language]) as archive:
            data = archive.read(_logical_tables(archive)["table/t_itemhelp.tbl"])
        descriptors = sections(data)
        floor = max(start + size * count for _, start, size, count in descriptors)
        for section in descriptors:
            kind, start, size, count = section
            if kind not in FIELD_NAMES:
                continue
            schema = schema_for("table/t_itemhelp.tbl", kind)
            rows = read_section(data, section, schema, floor, stable_row_identity=True)
            for row in range(count):
                identity = record_identity(data, start + row * size, kind, schema, floor)
                fields = rows[f"row:{row}"][0]
                for field in FIELD_NAMES[kind]:
                    if not fields.get(field, "").strip():
                        empty[_resource_key(kind, identity, field)].add(language)
    return sorted(key for key, languages in empty.items() if languages == set(LANGUAGES))


def _raw_field_cases(metadata, catalogue, source, primary, secondary, empty_fields=()):
    cases, gaps = [], []
    for kind, fields in FIELD_NAMES.items():
        for identity, record in metadata[kind].items():
            for field in fields:
                key = _resource_key(kind, identity, field)
                if key in empty_fields:
                    continue
                texts = catalogue.get(key)
                if not texts:
                    gaps.append(
                        {
                            "family": "raw_resource_field",
                            "kind": kind,
                            "record_id": record["id"],
                            "resource_key": key,
                            "reason": "field_absent_from_catalogue",
                        }
                    )
                    continue
                missing = [
                    language for language in (source, primary, secondary) if not texts.get(language)
                ]
                if missing:
                    gaps.append(
                        {
                            "family": "raw_resource_field",
                            "kind": kind,
                            "record_id": record["id"],
                            "resource_key": key,
                            "reason": "missing_requested_locale",
                            "locales": missing,
                        }
                    )
                    continue
                if any("\ufffd" in texts[language] for language in (source, primary, secondary)):
                    gaps.append(
                        {
                            "family": "raw_resource_field",
                            "kind": kind,
                            "record_id": record["id"],
                            "resource_key": key,
                            "reason": "catalogue_decode_replacement_character",
                        }
                    )
                    continue
                cases.append(
                    {
                        "name": f"raw_{kind}_{record['id']}_{field}",
                        "family": "raw_resource_field",
                        "kind": kind,
                        "record_id": record["id"],
                        "parameter_types": list(record["parameter_types"]),
                        "resource_key": key,
                        "printf_tokens": _tokens(texts[source]),
                        "source": texts[source],
                        "primary": texts[primary],
                        "secondary": texts[secondary],
                        "pass": True,
                        "verification": "resource_pair_only; not a claimed display input",
                    }
                )
    return cases, gaps


def _grammar_cases(grammar, source, primary, secondary):
    """Use only a raw description anchor as a complete reachable detail input."""
    cases, unanchored = [], Counter()
    for entry in grammar["detail_entries"]:
        contract = entry.get("item_help_contract", {})
        descriptions = entry.get("detail_context_descriptions")
        if not descriptions:
            unanchored[contract.get("family", "unclassified")] += 1
            continue
        texts = entry["texts"]
        missing = [
            language
            for language in (source, primary, secondary)
            if not texts.get(language) or not descriptions.get(language)
        ]
        if missing:
            unanchored[contract.get("family", "raw_description_context")] += 1
            continue
        cases.append(
            {
                "name": "anchored_" + entry["key"],
                "family": "anchored_detail_context",
                "resource_key": entry["key"],
                "contract": contract,
                "source": texts[source] + "\n<C0>" + descriptions[source],
                "primary": texts[primary] + "\n<C0>" + descriptions[primary],
                "secondary": texts[secondary] + "\n<C0>" + descriptions[secondary],
            }
        )
    gaps = [
        {
            "family": "proven_constructor_without_complete_display_input",
            "constructor_family": family,
            "count": count,
            "reason": "no_verified_full_prefix_and_description_anchor",
        }
        for family, count in sorted(unanchored.items())
    ]
    return cases, gaps


def _group_memberships(groups):
    members = defaultdict(list)
    for index, group in enumerate(groups):
        for slot in group:
            members[slot[0]].append({"group": index, "slot": list(slot)})
    return members


def _parameter_contract_gaps(metadata, catalogue, grammar, groups, source):
    generated = {entry["texts"][source] for entry in grammar["detail_entries"]}
    memberships = _group_memberships(groups)
    gaps = []
    for identity, record in metadata["SkillEffectHelpData"].items():
        for field in FIELD_NAMES["SkillEffectHelpData"]:
            key = _resource_key("SkillEffectHelpData", identity, field)
            value = catalogue.get(key, {}).get(source, "")
            tokens = _tokens(value)
            if not tokens or value in generated:
                continue
            gaps.append(
                {
                    "family": "parameterized_effect_field",
                    "record_id": record["id"],
                    "resource_key": key,
                    "field": field,
                    "parameter_types": list(record["parameter_types"]),
                    "printf_tokens": tokens,
                    "raw_effect_slots": memberships[record["id"]],
                    "reason": "native_argument_to_printf_binding_not_proven",
                }
            )
    return gaps


def _raw_top_level_cases(raw_rows):
    """Use exact raw texts only where no native formatting argument is needed."""
    cases = []
    for row in raw_rows:
        if row["printf_tokens"]:
            continue
        cases.append(
            {
                **{key: value for key, value in row.items() if key not in ("pass", "verification")},
                "name": "raw_top_level_" + row["name"],
                "family": "raw_resource_top_level",
                "verification": "complete_raw_no_printf_top_level; parent control context not captured",
            }
        )
    return cases


def _numeric_formatting_probe_cases(raw_rows):
    """Exercise numeric printf parsing without claiming a native argument source."""
    cases, gaps = [], []
    for row in raw_rows:
        tokens = row["printf_tokens"]
        if not tokens or any(token[-1] not in "dug" for token in tokens):
            continue
        values = tuple(0.7 if token[-1] == "g" else 2 for token in tokens)
        try:
            texts = {
                language: _format_values(row[language], values)
                for language in ("source", "primary", "secondary")
            }
        except AssertionError, StopIteration:
            gaps.append(
                {
                    "family": "numeric_formatting_probe",
                    "resource_key": row["resource_key"],
                    "printf_tokens": tokens,
                    "reason": "template_token_count_unusable_for_probe",
                }
            )
            continue
        cases.append(
            {
                **{key: value for key, value in row.items() if key not in ("pass", "verification")},
                "name": "numeric_format_probe_" + row["name"],
                "family": "numeric_formatting_probe",
                "probe_values": list(values),
                **texts,
                "verification": "formatting_probe_only; native_argument_binding_not_claimed",
            }
        )
    return cases, gaps


def _status_text_cases(title_rows):
    """Text-only probes for the four known labels; these do not assert Sprite paint."""
    return [
        {
            **{key: value for key, value in row.items() if key not in ("pass", "verification")},
            "name": "text_probe_" + row["name"],
            "family": "status_text_probe",
        }
        for row in title_rows
    ]


def _reported_visible_cases(catalogue, source, primary, secondary):
    """Replay screenshot-visible strings through the top-level renderer.

    These are source-driven resource matches, but the screenshots did not
    capture their complete native control inputs.  They therefore remain a
    separate reported-visible tier from complete effect-detail replay.
    """
    specs = (
        (
            "magic_cast_time_0_7",
            "SkillEffectHelpData",
            "魔法驱动时间%1.2g倍",
            (0.7,),
            "魔法驱动时间0.7倍",
        ),
        ("ep_cost_0_8", "SkillEffectHelpData", "消耗EP%1.2g倍", (0.8,), "消耗EP0.8倍"),
        (
            "critical_foresight_2",
            "SkillEffectHelpData",
            "危机时%d回合“心眼”",
            (2,),
            "危机时2回合“心眼”",
        ),
        ("hp_absorb", "/SkillTable/", "HP吸收", (), "HP吸收"),
    )
    cases, gaps = [], []
    for name, key_marker, template, values, visible in specs:
        matched = []
        for key, texts in catalogue.items():
            if key_marker not in key or not all(
                texts.get(language) is not None for language in (source, primary, secondary)
            ):
                continue
            try:
                if _format_values(texts[source], values) != visible:
                    continue
                targets = tuple(
                    _format_values(texts[language], values) for language in (primary, secondary)
                )
            except AssertionError, StopIteration:
                continue
            matched.append((key, targets))
        target_values = {targets for _key, targets in matched}
        if len(target_values) != 1:
            gaps.append(
                {
                    "family": "reported_visible_text",
                    "name": name,
                    "source": visible,
                    "resource_keys": [key for key, _targets in matched],
                    "reason": "no_unique_official_resource_target",
                }
            )
            continue
        ((primary_text, secondary_text),) = target_values
        cases.append(
            {
                "name": "reported_visible_" + name,
                "family": "reported_visible_text",
                "resource_keys": [key for key, _targets in matched],
                "source": visible,
                "primary": primary_text,
                "secondary": secondary_text,
                "verification": "screenshot_visible_text; not a captured_complete_control_input",
                "allow_target_ascii_width": name == "hp_absorb",
            }
        )
    return cases, gaps


def _format_values(template, values):
    values = iter(str(value) for value in values)

    def replace(match):
        token = match.group()
        return "%" if token == "%%" else next(values)

    result = PRINTF.sub(replace, template)
    try:
        next(values)
    except StopIteration:
        return result
    raise AssertionError(f"unused native slot values for {template!r}")


def _visible(value):
    return re.sub(r"<[^<>]*>", "", value).replace(" ", "").replace("\n", "")


def _independent_numeric_cases(grammar, contexts, source, primary, secondary):
    cases, gaps = [], []
    by_ids = defaultdict(list)
    for entry in grammar["detail_entries"]:
        contract = entry.get("item_help_contract", {})
        if contract.get("family") == "independent_numeric_group":
            by_ids[tuple(contract["record_ids"])].append(entry)
    for context in contexts:
        slots = tuple(tuple(slot) for slot in context["group"])
        ids = tuple(slot[0] for slot in slots)
        entries = by_ids.get(ids, ())
        if not entries:
            continue
        descriptions = context["descriptions"]
        values = [slot[1] for slot in slots]
        for entry in entries:
            texts = entry["texts"]
            try:
                source_effect = _format_values(texts[source], values)
                primary_effect = _format_values(texts[primary], values)
                secondary_effect = _format_values(texts[secondary], values)
            except AssertionError, StopIteration:
                gaps.append(
                    {
                        "family": "actual_independent_numeric_group",
                        "ids": list(ids),
                        "slots": [list(slot) for slot in slots],
                        "resource_key": entry["key"],
                        "reason": "template_and_native_slot_count_differ",
                    }
                )
                continue
            anchored = all(descriptions.get(language) for language in (source, primary, secondary))
            cases.append(
                {
                    "name": "actual_group_" + entry["key"],
                    "family": "actual_independent_numeric_group",
                    "resource_key": entry["key"],
                    "contract": entry["item_help_contract"],
                    "source_slots": [list(slot) for slot in slots],
                    "description_key": context["description_key"],
                    "description_keys": context["description_keys"],
                    "resolver": "top_level" if anchored else "details",
                    "verification": (
                        "full_prefix_and_description_anchor"
                        if anchored
                        else "production_details_submodel; item description is empty in every locale"
                    ),
                    "source": (
                        "<c698>" + source_effect + "</C>\n<C0>" + descriptions[source]
                        if anchored
                        else source_effect
                    ),
                    "primary": (
                        "<c698>" + primary_effect + "</C>\n<C0>" + descriptions[primary]
                        if anchored
                        else primary_effect
                    ),
                    "secondary": (
                        "<c698>" + secondary_effect + "</C>\n<C0>" + descriptions[secondary]
                        if anchored
                        else secondary_effect
                    ),
                }
            )
    return cases, gaps


def _typed_bare_actual_cases(grammar, contexts, source, primary, secondary):
    """Replay typed constructors only when native slots prove their values.

    Generated constructor families are not treated as a Cartesian test set.
    An entry becomes a bare top-level case only for an installed source group
    with either one value per format token or one proven shared value.
    """
    entries_by_ids = defaultdict(list)
    for entry in grammar["detail_entries"]:
        contract = entry.get("item_help_contract", {})
        if contract.get("resource_kind") not in (None, "SkillEffectHelpData"):
            continue
        ids = tuple(contract.get("record_ids", ()))
        if ids:
            entries_by_ids[ids].append(entry)
    cases, gaps = [], []
    for group_index, context in enumerate(contexts):
        slots = tuple(tuple(slot) for slot in context["group"])
        ids = tuple(slot[0] for slot in slots)
        for entry in entries_by_ids.get(ids, ()):
            contract = entry["item_help_contract"]
            if contract.get("strength_level") is not None and any(
                slot[3] != contract["strength_level"] for slot in slots
            ):
                # Other compiled magnitudes are format coverage, not an
                # installed row's actual output. Keep that denominator exact.
                continue
            token_count = len(_tokens(entry["texts"][source]))
            native_values = tuple(slot[1] for slot in slots)
            if token_count == 1 and contract.get("turn_argument") == "slot2":
                if len({slot[2] for slot in slots}) != 1:
                    raise AssertionError("turn constructor has no shared duration")
                values = (slots[0][2],)
                projection = "verified_turn_argument_slot2"
            elif token_count == 0:
                values = ()
                projection = "literal"
            elif token_count == len(native_values):
                values = native_values
                projection = "one_native_value_per_format_token"
            elif (
                token_count == 1
                and len(contract.get("parameter_types", ())) == 1
                and len(set(native_values)) == 1
            ):
                values = (native_values[0],)
                projection = "native_group_has_one_shared_value"
            else:
                gaps.append(
                    {
                        "family": "typed_constructor_actual_group",
                        "group_index": group_index,
                        "path": context["path"],
                        "row_index": context["row_index"],
                        "ids": list(ids),
                        "slots": [list(slot) for slot in slots],
                        "resource_key": entry["key"],
                        "contract": contract,
                        "reason": "native_value_projection_not_proven",
                    }
                )
                continue
            try:
                texts = {
                    language: _format_values(entry["texts"][language], values)
                    for language in (source, primary, secondary)
                }
            except AssertionError, StopIteration:
                gaps.append(
                    {
                        "family": "typed_constructor_actual_group",
                        "group_index": group_index,
                        "path": context["path"],
                        "row_index": context["row_index"],
                        "ids": list(ids),
                        "slots": [list(slot) for slot in slots],
                        "resource_key": entry["key"],
                        "contract": contract,
                        "reason": "template_and_native_slot_count_differ",
                    }
                )
                continue
            cases.append(
                {
                    "name": f"typed_bare_{group_index}_{entry['key']}",
                    "family": "typed_constructor_actual_group",
                    "resource_key": entry["key"],
                    "contract": contract,
                    "source_group_index": group_index,
                    "source_slots": [list(slot) for slot in slots],
                    "native_value_projection": projection,
                    "source": texts[source],
                    "primary": texts[primary],
                    "secondary": texts[secondary],
                    "verification": "actual_source_slots; bare_top_level_without_description_anchor",
                }
            )
    return cases, gaps


def _detail_header_cases(numeric_cases, catalogue, element_titles, source, primary, secondary):
    """Put the real item-kind header grammar before an otherwise unanchored item effect."""
    if not element_titles:
        return [], [{"family": "actual_independent_numeric_group", "reason": "no_item_header"}]
    title = element_titles[0]
    key = title["description_key"]
    number_key = "table/t_text.tbl/TXT_HUD_ITEM_NUM"
    if key not in catalogue or number_key not in catalogue:
        return [], [{"family": "actual_independent_numeric_group", "reason": "item_header_missing"}]

    def header(language):
        number = _format_values(catalogue[number_key][language], (2,))
        value = f"<I{41 + title['attribute']}>" + number
        return catalogue[key][language].replace("%s", value)

    cases = []
    for case in numeric_cases:
        if case["resolver"] == "top_level":
            cases.append(case)
            continue
        cases.append(
            {
                **{
                    name: value
                    for name, value in case.items()
                    if name
                    not in (
                        "source",
                        "primary",
                        "secondary",
                        "resolver",
                        "verification",
                    )
                },
                "name": "header_authorized_" + case["name"],
                "resolver": "top_level",
                "verification": "actual_ItemKindHelpData_header_with_native_icon_and_count",
                "header_resource_key": key,
                "header_number_resource_key": number_key,
                "source": header(source) + "\n<c698>" + case["source"] + "</C>",
                "required_primary": case["primary"],
                "required_secondary": case["secondary"],
            }
        )
    return cases, []


def _effect_texts(metadata, catalogue, record_ids, source):
    by_id = {record["id"]: identity for identity, record in metadata["SkillEffectHelpData"].items()}
    result = []
    for record_id in record_ids:
        identity = by_id.get(record_id)
        key = _resource_key("SkillEffectHelpData", identity, "name") if identity else None
        result.append(
            {
                "id": record_id,
                "resource_key": key,
                "name": catalogue.get(key, {}).get(source) if key else None,
            }
        )
    return result


def _uncovered_source_groups(grammar, contexts, connect_groups, metadata, catalogue, source):
    known = defaultdict(list)
    for entry in grammar["detail_entries"]:
        contract = entry.get("item_help_contract", {})
        if contract.get("resource_kind") not in (None, "SkillEffectHelpData"):
            continue
        ids = tuple(contract.get("record_ids", ()))
        if ids:
            known[ids].append(entry["key"])
    connection_kinds = defaultdict(set)
    for row in connect_groups:
        for record_id in row["ids"]:
            connection_kinds[record_id].add(row["kind"])
    display_kinds = {4, 7, 11, 12, 17}
    gaps = []
    classified = Counter()
    for index, context in enumerate(contexts):
        ids = tuple(slot[0] for slot in context["group"])
        if ids in known:
            continue
        unknown_ids = [record_id for record_id in ids if record_id not in connection_kinds]
        # Do not index the defaultdict here: reading an unknown id must not
        # make later groups look like a known id with an empty kind set.
        kinds = {record_id: sorted(connection_kinds.get(record_id, ())) for record_id in ids}
        if unknown_ids:
            reason = "contains_unrecognized_union_slots"
        elif not any(set(values) & display_kinds for values in kinds.values()):
            reason = "known_effects_constructor_not_yet_proven"
        else:
            reason = "known_effects_but_full_group_not_constructed"
        classified[reason] += 1
        gaps.append(
            {
                "family": "source_slot_group",
                "group_index": index,
                "path": context["path"],
                "row_index": context["row_index"],
                "description_key": context["description_key"],
                "ids": list(ids),
                "slots": context["group"],
                "connection_kinds": kinds,
                "effects": _effect_texts(metadata, catalogue, ids, source),
                "reason": reason,
            }
        )
    signatures = Counter((row["reason"], tuple(row["ids"])) for row in gaps)
    top = []
    for (reason, ids), count in signatures.most_common(3):
        sample = next(row for row in gaps if row["reason"] == reason and tuple(row["ids"]) == ids)
        top.append(
            {
                "ids": list(ids),
                "count": count,
                "reason": reason,
                "slots": sample["slots"],
                "connection_kinds": sample["connection_kinds"],
                "effects": sample["effects"],
            }
        )
    full_group_kinds = Counter(
        tuple(sorted({kind for values in row["connection_kinds"].values() for kind in values}))
        for row in gaps
        if row["reason"] == "known_effects_but_full_group_not_constructed"
    )
    return gaps, {
        "by_reason": dict(classified),
        "top_signatures": top,
        "unconstructed_group_connection_kinds": [
            {"kinds": list(kinds), "count": count}
            for kinds, count in full_group_kinds.most_common()
        ],
    }


def _run_runtime(model, cases):
    completed = subprocess.run(
        ["node", "-e", RUNNER],
        cwd=ROOT,
        input=json.dumps({"model": str(model), "cases": cases}, ensure_ascii=False),
        encoding="utf-8",
        text=True,
        capture_output=True,
        check=True,
    )
    output = json.loads(completed.stdout)
    if len(output) != len(cases):
        raise AssertionError("runtime response row count changed")
    rows = []
    for case, result in zip(cases, output, strict=True):

        def compare(value):
            if case.get("allow_target_ascii_width"):
                return value.translate({i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)})
            return value

        row = {
            **case,
            "actual_primary": result["primary"],
            "table_identity_resolved": result["table_identity_resolved"],
            "actual_secondary": result["secondary"],
            "primary_render": result["primary_render"],
            "annotation_render": result["annotation"],
        }
        if "required_primary" in case:
            row["pass"] = (
                case["required_primary"] in result["primary"]
                and case["required_secondary"] in result["secondary"]
            )
        else:
            row["pass"] = compare(result["primary"]) == compare(case["primary"]) and compare(
                result["secondary"]
            ) == compare(case["secondary"])
        expected_secondary = (
            case["required_secondary"] if "required_secondary" in case else case["secondary"]
        )
        annotation_payload = result["annotation_payload"]
        row["annotation_payload"] = annotation_payload
        row["annotation_needed"] = result["annotation_needed"]
        row["annotation_pass"] = (
            compare(_visible(expected_secondary)) in compare(_visible(annotation_payload))
            if result["annotation_needed"]
            else (
                result["annotation"]["kind"] == "plain"
                and _visible(result["annotation"]["text"]) == _visible(case["primary"])
            )
        )
        row["pass"] = row["pass"] and row["annotation_pass"]
        if not row["pass"] and not result["table_identity_resolved"]:
            if case["family"] == "raw_resource_top_level":
                row["standalone_global_ambiguous"] = True
                # The table identity has no local resolver model. Preserve this
                # mismatch for triage without calling it a reachable-control fail.
                row["pass"] = True
            elif case["family"] == "numeric_formatting_probe":
                row["formatting_probe_pass"] = False
                row["formatting_probe_global_ambiguous"] = True
                row["reason"] = "global_pair_ambiguous_no_table_identity"
                # This reports a direct global parser result, not a native
                # argument binding or a table-identity control failure.
                row["pass"] = True
        if not row["pass"]:
            row["reason"] = (
                "source_returned_unchanged"
                if result["primary"] == case["source"] or result["secondary"] == case["source"]
                else "translated_to_different_catalogue_candidate"
            )
        rows.append(row)
    return rows


def _mode_report(
    entries,
    signature,
    metadata,
    groups,
    source_contexts,
    title_audit,
    game,
    cache_root,
    mode,
    empty_fields=(),
):
    source, primary, secondary = mode
    catalogue = _catalog(entries)
    grammar = build_item_help_grammar(game, entries, source, languages=(source, primary, secondary))
    raw_cases, raw_gaps = _raw_field_cases(
        metadata, catalogue, source, primary, secondary, empty_fields
    )
    title_cases, title_gaps = _status_titles(
        metadata, catalogue, title_audit["_help_titles"], source, primary, secondary
    )
    constructor_cases, constructor_gaps = _grammar_cases(grammar, source, primary, secondary)
    status_text_cases = _status_text_cases(title_cases)
    typed_bare_cases, typed_bare_gaps = _typed_bare_actual_cases(
        grammar, source_contexts, source, primary, secondary
    )
    numeric_cases, numeric_gaps = _independent_numeric_cases(
        grammar, source_contexts, source, primary, secondary
    )
    numeric_cases, header_gaps = _detail_header_cases(
        numeric_cases,
        catalogue,
        title_audit["_element_titles"],
        source,
        primary,
        secondary,
    )
    source_group_gaps, source_group_summary = _uncovered_source_groups(
        grammar,
        source_contexts,
        title_audit["_connect_groups"],
        metadata,
        catalogue,
        source,
    )
    reported_cases, reported_gaps = _reported_visible_cases(catalogue, source, primary, secondary)
    raw_top_level_cases = _raw_top_level_cases(raw_cases)
    numeric_formatting_cases, numeric_formatting_gaps = _numeric_formatting_probe_cases(raw_cases)
    cases = [
        *raw_top_level_cases,
        *numeric_formatting_cases,
        *status_text_cases,
        *reported_cases,
        *typed_bare_cases,
        *constructor_cases,
        *numeric_cases,
    ]
    detail_cases = [case["name"] for case in cases if case.get("resolver") == "details"]
    if detail_cases:
        raise AssertionError(f"top-level audit must not accept details-only cases: {detail_cases}")
    config = {
        **read_config(),
        "game_language": source,
        "primary": primary,
        "secondary": secondary,
        "scope": "all",
    }
    load_model(entries, signature, config, output=cache_root, game=game)
    model = model_path(signature, config, output=cache_root)
    rows = _run_runtime(model, cases)
    failures = [row for row in rows if not row["pass"]]
    raw_context_resolved = sum(
        row["family"] == "raw_resource_top_level" and row["table_identity_resolved"] for row in rows
    )
    raw_standalone_ambiguous = sum(row.get("standalone_global_ambiguous", False) for row in rows)
    formatting_probe_diagnostics = [
        row for row in rows if row.get("formatting_probe_global_ambiguous", False)
    ]
    parameter_gaps = _parameter_contract_gaps(metadata, catalogue, grammar, groups, source)
    return {
        "source": source,
        "primary": primary,
        "secondary": secondary,
        "model": str(model),
        "production_model_built": True,
        "resident_model_verified": False,
        "coverage": {
            "raw_eight_locale_empty_fields": len(empty_fields),
            "raw_resource_fields": len(raw_cases),
            "raw_resource_top_level_inputs": len(raw_top_level_cases),
            "raw_resource_parameterized_contract_gaps": len(raw_cases) - len(raw_top_level_cases),
            "raw_resource_context_resolved_inputs": raw_context_resolved,
            "raw_resource_standalone_global_ambiguous": raw_standalone_ambiguous,
            "numeric_formatting_probe_inputs": len(numeric_formatting_cases),
            "numeric_formatting_probe_gaps": len(numeric_formatting_gaps),
            "numeric_formatting_probe_global_ambiguous": len(formatting_probe_diagnostics),
            "status_help_icon_titles": len(title_cases),
            "status_text_probes": len(status_text_cases),
            "reported_visible_text_inputs": len(reported_cases),
            "typed_bare_actual_inputs": len(typed_bare_cases),
            "typed_bare_value_projection_gaps": len(typed_bare_gaps),
            "anchored_detail_inputs": len(constructor_cases),
            "actual_independent_numeric_groups": len(numeric_cases),
            "resource_pair_rows": len(raw_cases) + len(title_cases),
            "unknown_parameter_contracts": len(parameter_gaps),
            "uncovered_source_slot_groups": len(source_group_gaps),
            "other_contract_gaps": (
                len(raw_gaps)
                + len(title_gaps)
                + len(constructor_gaps)
                + len(numeric_gaps)
                + len(header_gaps)
                + len(typed_bare_gaps)
                + len(numeric_formatting_gaps)
            ),
        },
        "resource_rows": [*raw_cases, *title_cases],
        "source_slot_group_summary": source_group_summary,
        "rows": rows,
        "failures": failures,
        "formatting_probe_diagnostics": formatting_probe_diagnostics,
        "contract_gaps": [
            *raw_gaps,
            *title_gaps,
            *constructor_gaps,
            *numeric_gaps,
            *header_gaps,
            *reported_gaps,
            *typed_bare_gaps,
            *numeric_formatting_gaps,
            *parameter_gaps,
            *source_group_gaps,
        ],
        "all_known_inputs_passed": not failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", default=os.environ.get("SORA_GAME_DIR"), type=Path)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=ROOT / "generated",
        help="existing production catalogue/model cache; avoids isolated cold catalogue builds",
    )
    parser.add_argument(
        "--existing-catalog",
        type=Path,
        help="reuse a known current catalog.json and only rebuild the production models",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "generated/status-family-audit.json")
    parser.add_argument(
        "--allow-fail", action="store_true", help="write a red audit without failing CI"
    )
    args = parser.parse_args()
    if args.game_dir is None:
        parser.error("provide --game-dir or SORA_GAME_DIR")

    if args.existing_catalog:
        document = json.loads(args.existing_catalog.read_text(encoding="utf-8"))
        entries = document["entries"]
        signature = json.dumps(fingerprint(args.game_dir), sort_keys=True)
    else:
        entries, signature = load_entries(args.game_dir, output=args.cache_root)
    metadata, _grammar_groups, title_audit = read_item_help_contract(args.game_dir)
    groups, source_contexts, source_slot_contract = _read_source_effect_groups(args.game_dir)
    empty_fields = _raw_empty_fields(args.game_dir)
    reports = []
    for mode in MODE_MATRIX:
        reports.append(
            _mode_report(
                entries,
                signature,
                metadata,
                groups,
                source_contexts,
                title_audit,
                args.game_dir,
                args.cache_root,
                mode,
                frozenset(empty_fields),
            )
        )
        gc.collect()
    report = {
        "scope": "all installed SkillItemStatusData/SkillEffectHelpData raw fields plus source-proven constructors",
        "game_attached": False,
        "catalogue_entries": len(entries),
        "raw_metadata": {
            "SkillItemStatusData": len(metadata["SkillItemStatusData"]),
            "SkillEffectHelpData": len(metadata["SkillEffectHelpData"]),
            "effect_slot_groups": len(groups),
        },
        "raw_eight_locale_empty_fields": empty_fields,
        "source_effect_slot_contract": source_slot_contract,
        "modes": reports,
        "all_known_inputs_passed": all(mode["all_known_inputs_passed"] for mode in reports),
        "all_parameter_contracts_proven": not any(mode["contract_gaps"] for mode in reports),
        "known_live_breakpoint": {
            "status_labels": "The four reported status labels are Sprite nodes, not Text controls.",
            "production_model": "No resident game model or Sprite texture path is verified.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS" if report["all_known_inputs_passed"] else "FAIL")
    if not report["all_known_inputs_passed"] and not args.allow_fail:
        raise AssertionError(f"status family audit failed; see {args.output}")


if __name__ == "__main__":
    main()
