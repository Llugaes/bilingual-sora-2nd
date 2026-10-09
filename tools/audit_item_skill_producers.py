"""Build an unfiltered item/skill producer denominator from raw PAC packets.

The packets are physical display fields and raw metadata, not admitted model
rows. Expected outputs use official fields and native slot contracts here;
neither the translator nor compiled grammar is an oracle. Unknown constructors
remain in the denominator with an explicit gap. No game process is contacted.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


LOCALES = ("en", "ja", "zh-Hans", "zh-Hant", "ko", "fr", "de", "es")
CJK = {"ja", "zh-Hans", "zh-Hant", "ko"}
PRINTF = re.compile(r"%%|%[-+0 #]*\d*(?:\.\d+)?[diusg]")


def concrete(template, args=()):
    values = iter(args)
    return PRINTF.sub(lambda m: "%" if m[0] == "%%" else str(next(values)), template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fields", type=Path, default=Path("generated/r25-raw-entity-denominator.json")
    )
    parser.add_argument(
        "--contracts", type=Path, default=Path("generated/r25-raw-contract-inventory.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("generated/r25-producer-denominator.json")
    )
    args = parser.parse_args()
    raw = json.loads(args.fields.read_text("utf8"))
    contracts = json.loads(args.contracts.read_text("utf8"))
    fields, main_rows, hints, kind_headers = {}, {}, [], defaultdict(list)
    for row in raw["rows"]:
        fields.setdefault((row["kind"], row["entity_id"]), {})[row["field"]] = row
        if row["kind"] in ("ItemTableData", "SkillParam"):
            main_rows.setdefault((row["kind"], row["row"]), {})[row["field"]] = row
        if row["kind"] == "ItemKindHelpData" and row["field"] == "description":
            kind_headers[row["entity_id"]].append(row)
            values = {}
            for locale in LOCALES:
                spans = re.findall(
                    r"<[Cc][0-9a-fA-F]+>([^<>]+)</[Cc]>", row["texts"].get(locale, "")
                )
                if len(spans) != 1 or "%" in spans[0]:
                    break
                values[locale] = spans[0]
            if len(values) == len(LOCALES):
                hints.append((row, values))
    constants = {r["entity_id"]: r["texts"] for r in raw["rows"] if r["kind"] == "TextTableData"}
    metadata = {
        v["id"]: tuple(v["parameter_types"])
        for v in contracts["metadata"]["SkillEffectHelpData"].values()
    }
    connections = {}
    for c in contracts["audit"]["_connect_groups"]:
        for identifier in c["ids"]:
            connections.setdefault(identifier, c["kind"])
    cases, gaps, entities, contexts = [], [], [], []
    totals = Counter()

    def emit(identity, surface, texts, level, **extra):
        cases.append(
            {
                "id": identity,
                "surface": surface,
                "texts": texts,
                "level": level,
                "key": "",
                "scope": "",
                "owner": None,
                **extra,
            }
        )

    def gap(identity, surface, reason, **extra):
        gaps.append({"id": identity, "surface": surface, "reason": reason, **extra})

    def const(name, locale):
        return constants["TXT_ITEM_HELP_" + name][locale]

    def effect(group):
        """Native equal-argument groups in physical order, with bounded slots."""
        used, result, missing = set(), {l: [] for l in LOCALES}, []
        for index, slot in enumerate(group):
            if index in used:
                continue
            identifier, amount, turns, strength = slot
            record = fields.get(("SkillEffectHelpData", identifier))
            if record is None or identifier not in metadata:
                missing.append(
                    {
                        "slot": index,
                        "values": slot,
                        "reason": "raw slot has no help record; native omission/union mapping not proven",
                    }
                )
                continue
            kind = connections.get(identifier)
            selected = [(index, slot)]
            if kind in (1, 2, 4, 6, 7, 11, 12, 13, 16, 17):
                selected += [
                    (j, other)
                    for j, other in enumerate(group[index + 1 :], index + 1)
                    if j not in used
                    and connections.get(other[0]) == kind
                    and (kind == 17 or other[1:] == slot[1:])
                ]
            if any(("SkillEffectHelpData", s[0]) not in fields for _, s in selected):
                missing.append(
                    {"slot": index, "values": slot, "reason": "connection member field missing"}
                )
                continue
            rows = [fields[("SkillEffectHelpData", s[0])] for _, s in selected]
            parameters = metadata[identifier]
            values = {}
            try:
                for locale in LOCALES:
                    name = record["name"]["texts"][locale]
                    stat = record["stat"]["texts"][locale]
                    form = record["format"]["texts"][locale]
                    joined = const("LINK", locale).join(r["stat"]["texts"][locale] for r in rows)
                    if kind in (4, 6) and 1 <= strength <= 3:
                        arrow = "<I" + str((269 if kind == 4 else 266) + strength) + ">"
                        value = name.replace(stat, joined, 1).replace("%s", arrow)
                        if locale == "en":
                            value = (
                                joined
                                + arrow
                                + (record["turns"]["texts"][locale] if kind == 4 else "")
                            )
                        values[locale] = concrete(value, (turns,) if kind == 4 else ())
                    elif kind == 7:
                        values[locale] = concrete(name.replace(stat, joined, 1), (amount,))
                    elif kind == 1:
                        # CAB62 RVA34c4e2 reads "%s\u300c%s\u300d%s"
                        # at RVAb0a2d8; the native constructor owns these quotes.
                        value = (
                            "「" + joined + "」" + form
                            if locale in CJK
                            else form + " " + joined + " %d%%"
                        )
                        values[locale] = concrete(value, (amount,))
                    elif kind == 13 or parameters == (4,):
                        modifier = concrete(const("PERSENT", locale), (amount,))
                        phrase = concrete(form, (modifier,))
                        values[locale] = (
                            joined + (" " if locale == "ko" else "") + phrase
                            if locale in CJK
                            else phrase + joined
                        )
                    elif kind == 16 and parameters == (0, 0):
                        magnitude = (
                            ("SMALL" if amount < 3000 else "MIDDLE" if amount < 4500 else "LARGE")
                            if identifier == 121
                            else ("ALL" if amount == 100 else "PERSENT")
                        )
                        modifier = concrete(const(magnitude, locale), (amount,))
                        values[locale] = (
                            name + const("FORMAT8", locale) + concrete(form, (modifier,))
                        )
                    elif kind == 17:
                        parts = [concrete(name, (amount,))]
                        parts += [
                            concrete(
                                r["stat"]["texts"][locale] + r["format"]["texts"][locale], (s[1],)
                            )
                            for r, (_, s) in zip(rows[1:], selected[1:])
                        ]
                        values[locale] = const("LINK", locale).join(parts)
                    elif kind in (11, 12):
                        # CAB62 34d6cf/34d6d9 share 34eaf5: stat(+LINK)
                        # at 34eb74 precedes final format at 34eb96 in every locale.
                        values[locale] = joined + form
                    elif parameters == (1,):
                        values[locale] = concrete(name, (amount,))
                    elif parameters == (6,) and identifier == 1046:
                        values[locale] = concrete(name, (amount, slot[3]))
                    elif parameters in ((12,), (13,)):
                        boundary = 4500 if parameters == (12,) else 4000
                        magnitude = (
                            "SMALL" if amount < 3000 else "MIDDLE" if amount < boundary else "LARGE"
                        )
                        values[locale] = concrete(name, (const(magnitude, locale),))
                    elif not parameters and "%" not in name:
                        # Timed connection 18 additionally owns its format;
                        # a name alone cannot pretend to cover that constructor.
                        if kind == 18:
                            raise ValueError("timed connection duration getter not reconstructed")
                        values[locale] = name
                    else:
                        raise ValueError(
                            "native parameter dispatcher not reconstructed: " + str(parameters)
                        )
                for j, _ in selected:
                    used.add(j)
                for locale, value in values.items():
                    result[locale].append(value)
            except (KeyError, StopIteration, ValueError) as error:
                missing.append({"slot": index, "values": slot, "reason": str(error)})
        return {l: const("FORMAT8", l).join(v) for l, v in result.items()}, missing

    for (kind, physical), pair in main_rows.items():
        name, body = pair["name"], pair["description"]
        identifier = name["entity_id"]
        native_type = (
            (name["item_class"] >> 8) & 255
            if kind == "ItemTableData"
            else name["native_scalars"]["16"] & 255
        )
        category = (
            (
                "equipment"
                if native_type in (8, 9, 10, 11)
                else "quartz"
                if 20 <= native_type <= 26
                else "other_items"
            )
            if kind == "ItemTableData"
            else ("arts" if native_type == 4 else "other_skills")
        )
        totals[category] += 1
        entity = {
            "id": identifier,
            "kind": kind,
            "physical_row": physical,
            "category": category,
            "native_category": native_type,
            "source_key": name["key"],
            "name": name["texts"],
            "effect_slots": body["effect_slots"],
        }
        entities.append(entity)
        for field, row in pair.items():
            texts = {
                l: concrete(t) if not PRINTF.search(t.replace("%%", "")) else t
                for l, t in row["texts"].items()
            }
            probe_id = f"{kind}/{physical}/{field}"
            if PRINTF.search(row["texts"]["en"].replace("%%", "")):
                gap(
                    probe_id,
                    "literal",
                    "native description printf arguments missing",
                    key=row["key"],
                    source=row["texts"]["en"],
                )
            elif not row["texts"]["en"]:
                gap(probe_id, "literal", "blank raw field retained", key=row["key"])
            else:
                emit(
                    probe_id,
                    "list" if field == "name" else "body",
                    texts,
                    "raw physical field; final caller/ancestry not captured",
                    resource_key=row["key"],
                    entity=entity,
                )
                if field == "name" and category in ("equipment", "quartz"):
                    emit(
                        probe_id + "/equipment_slot",
                        "equipment_slot",
                        texts,
                        "same complete raw name; slot entrance unverified",
                        resource_key=row["key"],
                        entity=entity,
                    )
        group = [s for s in body["effect_slots"] if s[0]]
        if group:
            texts, missing = effect(group)
            context = {
                "id": f"{kind}/{physical}",
                "source_key": body["key"],
                "group": group,
                "complete_effect_input_reconstructed": not missing,
                "missing": missing,
                "header_texts": texts,
            }
            contexts.append(context)
            if missing:
                gap(
                    context["id"],
                    "effect_detail",
                    "complete native effect constructor not reconstructed",
                    context=context,
                    retained_partial_fields_are_not_complete_input=True,
                )
            else:
                emit(
                    context["id"] + "/effects",
                    "effect_detail",
                    {
                        l: "<c698>" + texts[l] + "</C>\n" + body["texts"][l].replace("%%", "%")
                        for l in LOCALES
                    },
                    "actual raw slot group + its own description; outer colour/newline detail wrapper probe",
                    resource_key=body["key"],
                    entity=entity,
                    expected_effect_units=True,
                )
            gap(
                context["id"] + "/drive",
                "drive_battle",
                "skill/item target/style producer selector not yet proven"
                if not missing
                else "complete raw effect input missing before target/style wrapping",
                source_key=body["key"],
                group=group,
            )
        if kind == "ItemTableData":
            selector = native_type << 16 | (name["item_class"] & 255)
            headers = kind_headers.get(selector, [])
            choices = {tuple(r["texts"][l] for l in LOCALES) for r in headers}
            if len(choices) == 1:
                header = headers[0]
                if "%" not in header["texts"]["en"] and header["texts"]["en"]:
                    emit(
                        f"{kind}/{physical}/category",
                        "item_category_header",
                        header["texts"],
                        "raw ItemKindHelp selector derived from category/mode bytes",
                        entity=entity,
                        resource_key=header["key"],
                    )
                    if body["texts"]["en"] and "%" not in body["texts"]["en"].replace("%%", ""):
                        emit(
                            f"{kind}/{physical}/category_body",
                            "item_category_detail",
                            {
                                l: header["texts"][l] + "\n" + body["texts"][l].replace("%%", "%")
                                for l in LOCALES
                            },
                            "raw selected category prefix + its own description; original setter absent",
                            entity=entity,
                            resource_key=header["key"],
                        )
                elif "%" in header["texts"]["en"]:
                    gap(
                        f"{kind}/{physical}/category",
                        "item_category_detail",
                        "dynamic kind-header argument/element stream not reconstructed",
                        selector=selector,
                        entity=entity,
                    )
            elif len(choices) != 1:
                gap(
                    f"{kind}/{physical}/category",
                    "item_category_detail",
                    "raw kind selector missing or conflicting",
                    selector=selector,
                    entity=entity,
                )
    for row, texts in hints:
        emit(
            row["key"] + "/hint_node",
            "item_hint_node",
            texts,
            "entire official coloured hint span, standalone setter hypothesis; no individual word aliases",
            resource_key=row["key"],
        )
        emit(
            row["key"] + "/hint_styled_node",
            "item_hint_node",
            {l: "<c698>" + t + "</C>" for l, t in texts.items()},
            "entire official styled hint span, standalone setter hypothesis",
            resource_key=row["key"],
        )
    assert len(entities) == 1797 and len(contexts) == 804
    report = {
        "schema": 1,
        "denominator": "all 1797 physical raw entities; never model-prefiltered",
        "fields_packet_sha256": hashlib.sha256(args.fields.read_bytes()).hexdigest(),
        "contract_packet_sha256": hashlib.sha256(args.contracts.read_bytes()).hexdigest(),
        "game_attached": False,
        "live_verified": False,
        "positive_owner_supplied": False,
        "classification": {
            "mutually_exclusive": True,
            "counts": dict(totals),
            "item_table_total": 1382,
            "skill_table_total": 415,
            "overlap_views": "all items includes other_items/equipment/quartz; all skills includes arts/other_skills",
            "other_skill_types": sorted(
                {e["native_category"] for e in entities if e["category"] == "other_skills"}
            ),
            "unmapped_skill_types_retained": sorted(
                {e["native_category"] for e in entities if e["kind"] == "SkillParam"}
                - {r["entity_id"] for r in raw["rows"] if r["kind"] == "SkillTypeHelpData"}
            ),
        },
        "entities": entities,
        "contexts": contexts,
        "cases": cases,
        "gaps": gaps,
        "summary": {
            "entities": len(entities),
            "contexts": len(contexts),
            "final_inputs": len(cases),
            "complete_contexts": sum(c["complete_effect_input_reconstructed"] for c in contexts),
            "incomplete_contexts": sum(
                not c["complete_effect_input_reconstructed"] for c in contexts
            ),
            "gaps_by_surface": dict(Counter(g["surface"] for g in gaps)),
        },
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {"classification": report["classification"], "summary": report["summary"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
