"""Reverse inventory of excluded resource inputs, with full rendering witnesses.

Reads installed resources and compiled models only. Exclusion is a review lead,
not proof that a visible control is untranslated. Unproved bindings stay open.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from sora_bilingual.localization.item_help_composition import (
    build_item_help_grammar,
    read_item_help_contract,
)
from sora_bilingual.localization.menu_text import display_text, plain
from tests.check_status_omissions import _run_runtime


def reverse_groups(metadata, contexts, connections):
    known = {row["id"] for row in metadata["SkillEffectHelpData"].values()}
    kinds = {i: row["kind"] for row in connections for i in row["ids"]}
    rows = []
    for context in contexts:
        ids = [slot[0] for slot in context["group"]]
        unknown = sorted(set(ids) - known)
        rows.append(
            {
                **context,
                "unknown_ids": unknown,
                "connection_kinds": [kinds.get(i) for i in ids],
                "classification": "whole_group_excluded_unknown_union_slots"
                if unknown
                else "known_effect_group",
            }
        )
    return rows


def reverse_pairs(entries, model, source, primary, secondary):
    """Retain every complete record absent from unkeyed exact lookup.

    Do not call these misses: numeric rules, dialogue identity and producer
    handlers are separate routes. This deliberately starts before admission.
    """
    pairs, normalized = model["pairs"], model["plain_pairs"]
    ambiguous = set(model["ambiguous_display"])
    rows = []
    for entry in entries:
        texts = entry["texts"]
        if not all(texts.get(l, "").strip() for l in (source, primary, secondary)):
            continue
        value = texts[source]
        if value in pairs or plain(value) in normalized or display_text(value) in pairs:
            continue
        reason = (
            "ambiguous_complete_display"
            if display_text(value) in ambiguous
            else "parameterized_requires_constructor"
            if "%" in value
            else "not_in_global_exact_pairs"
        )
        rows.append(
            {
                "key": entry["key"],
                "source": value,
                "targets": [texts[primary], texts[secondary]],
                "reason": reason,
                "display_role": entry.get("display_role"),
                "has_script_identity": bool(entry.get("called_ids")),
                "review_status": "other_routes_not_proven_by_this_inventory",
            }
        )
    return rows


def witnesses(entries, grammar, contexts, source, primary, secondary):
    catalogue = {e["key"]: e["texts"] for e in entries}
    cases, gaps = [], []
    for e in grammar["detail_entries"]:
        c = e.get("item_help_contract", {})
        family = c.get("family")
        if family not in (
            "critical_turn_group",
            "literal_stat_group",
            "debuff_cancel_immunity",
            "status_value",
        ):
            continue
        ids = c["record_ids"]
        if family == "status_value":
            # Numeric formatting probe; 75 is not claimed to be a native slot.
            choices = [(None, 75)]
        else:
            choices = []
            for context in contexts:
                slots = [s for s in context["group"] if s[0] in ids]
                if [s[0] for s in slots] != ids:
                    continue
                if family == "critical_turn_group":
                    if c["strength_level"] != 1 or len({s[2] for s in slots}) != 1:
                        continue
                    number = slots[0][2]
                else:
                    number = None
                choices.append((context, number))
        for context, number in choices:
            texts = {
                l: e["texts"][l].replace("%d", str(number)).replace("%%", "%")
                for l in (source, primary, secondary)
            }
            desc = catalogue.get(context["description_key"]) if context else None
            if desc and all(re.search(r"[\w\u3040-\u9fff]", plain(desc.get(l, ""))) for l in texts):
                texts = {l: v + "\n<C0>" + desc[l] for l, v in texts.items()}
                route = "full_detail_with_actual_resource_description"
            else:
                route = "anchored_detail_resolver_only"
            case = {
                "name": e["key"] + "/" + str(len(cases)),
                "family": family,
                "resource_key": e["key"],
                "contract": c,
                "source": texts[source],
                "primary": texts[primary],
                "secondary": texts[secondary],
                "verification": route,
                "raw_context": context,
            }
            if route == "anchored_detail_resolver_only":
                case["resolver"] = "details"
            cases.append(case)
            if family == "status_value" and "％" in case["source"]:
                cases.append(
                    {
                        **case,
                        "name": case["name"] + "/narrow-percent",
                        "source": case["source"].replace("％", "%"),
                    }
                )
        if not choices:
            gaps.append(
                {"key": e["key"], "reason": "no_actual_ordered_group_witness", "contract": c}
            )
    for e in entries:
        if e.get("display_role") != "popup_line" or not all(
            e["texts"].get(l) for l in (source, primary, secondary)
        ):
            continue
        cases.append(
            {
                "name": e["key"],
                "family": "popup_literal_line",
                "resource_key": e["key"],
                "source": e["texts"][source],
                "primary": e["texts"][primary],
                "secondary": e["texts"][secondary],
            }
        )
        if plain(e["texts"][source]) != e["texts"][source]:
            cases.append(
                {
                    "name": e["key"] + "/style-consumed",
                    "family": "popup_literal_line_style_consumed",
                    "source": plain(e["texts"][source]),
                    "primary": e["texts"][primary],
                    "secondary": e["texts"][secondary],
                }
            )
    return cases, gaps


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", type=Path, required=True)
    p.add_argument(
        "--models", type=Path, required=True, help="JSON list containing config and model path"
    )
    p.add_argument("--catalog", type=Path, default=Path("generated/catalog.json"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--capture", type=Path, help="existing native-labels snapshot; never attaches")
    a = p.parse_args()
    entries = json.loads(a.catalog.read_text("utf-8"))["entries"]
    metadata, _, audit = read_item_help_contract(a.game)
    contexts = audit["_effect_contexts"]
    groups = reverse_groups(metadata, contexts, audit["_connect_groups"])
    reports = []
    for m in json.loads(a.models.read_text("utf-8")):
        config = m["config"]
        source, primary, secondary = (config[k] for k in ("game_language", "primary", "secondary"))
        model = json.loads(Path(m["path"]).read_text("utf-8"))
        exclusions = reverse_pairs(entries, model, source, primary, secondary)
        del model
        grammar = build_item_help_grammar(
            a.game, entries, source, languages=(source, primary, secondary)
        )
        cases, gaps = witnesses(entries, grammar, contexts, source, primary, secondary)
        if a.capture:
            captures = json.loads(a.capture.read_text("utf-8"))
            for row in captures:
                original = row.get("original", "")
                if "HP吸收" not in original:
                    continue
                entry = next(
                    e for e in grammar["detail_entries"] if e["texts"].get(source) == "HP吸收"
                )
                cases.append(
                    {
                        "name": "captured_complete_HP_absorb",
                        "family": "captured_complete_detail",
                        "source": original,
                        "required_primary": entry["texts"][primary],
                        "required_secondary": entry["texts"][secondary],
                    }
                )
        rows = _run_runtime(m["path"], cases)
        failures = [r for r in rows if not r["pass"]]
        reports.append(
            {
                "config": config,
                "model": m["path"],
                "excluded_exact_records": exclusions,
                "excluded_reasons": dict(Counter(r["reason"] for r in exclusions)),
                "rows": rows,
                "failures": failures,
                "unwitnessed_constructed_entries": gaps,
            }
        )
        print(config, "witnesses", len(rows), "failures", len(failures), flush=True)
    report = {
        "game_attached": False,
        "groups": groups,
        "group_counts": dict(Counter(r["classification"] for r in groups)),
        "modes": reports,
        "all_witnesses_pass": all(not m["failures"] for m in reports),
        "all_exclusions_verified_safe": False,
    }
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["all_witnesses_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
