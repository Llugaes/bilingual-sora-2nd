"""Mechanical state sequences; resource acceptance has separate original-data oracles."""

import hashlib
import json

from test_r19_effect_contract import rows


def inputs():
    entries, _, _ = rows()
    for ident, source, a, b in (
        ("a", "A", "JA", "ZA"),
        ("b", "B", "JB", "ZB"),
        ("c", "C", "JC", "ZC"),
        ("abc", "A, B, C", "JABC", "ZABC"),
    ):
        entries.append(
            {
                "key": f"table/t_itemhelp.tbl/SkillEffectHelpData/{ident}/name",
                "texts": {"en": source, "ja": a, "zh-Hans": b},
            }
        )
    cases = [
        {
            "name": "cold_and_hot",
            "steps": [
                ["atom", "HP Regen"],
                ["atom", "Unknown"],
                ["atom", "Blind 2147483648%"],
                ["atom", "Blind nope%"],
                ["atom", "Blind 2147483648%"],
                ["atom", "HP Regen"],
            ],
        },
        {
            "name": "reject_then_match",
            "steps": [
                ["units", "A, B, C"],
                ["atom", "A, B, C"],
                ["rejected", "A, B, C"],
                ["translate", "A, B, C", "primary"],
                ["render", "A, B, C", "annotation"],
            ],
        },
        {
            "name": "coalesced_success",
            "seed": [["<c698>HP Regen</C>", "conflicting_effect_member"]],
            "steps": [["atom", "<c698>HP </C><c698>Regen</C>"], ["atom", "Unknown"]],
        },
        {
            "name": "frame_direction_history",
            "seed": [["Blind 30%", "unproven_direction_parameter"]],
            "steps": [
                ["atom", "<C2>Blind 30%</C>"],
                ["render", "<C2>Blind 30%</C>\nOfficial description", "annotation"],
            ],
        },
        {
            "name": "opaque_cold",
            "steps": [
                ["units", "HP Regen, Unknown", True],
                ["render", "HP Regen, Unknown\nOfficial description", "annotation"],
            ],
        },
        {
            "name": "opaque_history",
            "seed": [["Unknown", "invalid_effect_parameter"]],
            "steps": [
                ["atom", "Unknown"],
                ["units", "HP Regen, Unknown", True],
                ["render", "HP Regen, Unknown\nOfficial description", "annotation"],
            ],
        },
        {
            "name": "short_circuit",
            "steps": [
                ["units", "HP Regen, Blind 2147483648%, Unknown"],
                ["units", "Unknown, Blind nope%, HP Regen"],
            ],
        },
        {
            "name": "fragment_traversal",
            "steps": [["units", "HP Regen, Unknown<C2>Blind nope%</C>Blind 2147483648%", True]],
        },
        {
            "name": "capacity_19999",
            "seed_count": 19999,
            "steps": [["atom", "Blind 2147483648%"], ["units", "Bad\nLine"]],
        },
        {
            "name": "capacity_20000",
            "seed_count": 20000,
            "steps": [
                ["atom", "HP Regen"],
                ["atom", "Unknown"],
                ["units", "HP Regen"],
                ["units", "Bad\nLine"],
            ],
        },
        {
            "name": "capacity_update_existing",
            "seed_count": 19999,
            "seed_before": [["Blind 2147483648%", "prior_reason"]],
            "steps": [["atom", "Blind 2147483648%"], ["units", "Bad\nLine"]],
        },
    ]
    return entries, cases


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot(failures):
    ordered = list(failures.items())
    return {
        "count": len(ordered),
        "sha256": hashlib.sha256(canonical(ordered).encode()).hexdigest(),
        "edges": ordered if len(ordered) < 8 else ordered[:3] + ordered[-3:],
    }


def evaluate(translator_class):
    entries, cases = inputs()
    results = []
    for case in cases:
        outer = translator_class(entries, "ja", "zh-Hans", "en")
        tr = outer.details
        tr.effect_unit_failures.update(case.get("seed_before", []))
        for index in range(case.get("seed_count", 0)):
            tr.effect_unit_failures[f"seed/{index}"] = "unassociated_effect_unit"
        tr.effect_unit_failures.update(case.get("seed", []))
        calls = []
        method = "_effect_unit_result" if hasattr(tr, "_effect_unit_result") else "_effect_unit"
        original = getattr(tr, method)

        def traced(source, coalesced=False):
            calls.append([source, coalesced])
            return original(source, coalesced)

        setattr(tr, method, traced)
        events = []
        for action, source, *args in case["steps"]:
            calls.clear()
            if action == "atom":
                value = tr._effect_unit(source)
            elif action == "units":
                value = tr.effect_units(source, *args)
            elif action == "rejected":
                value = tr._effect_rejected(source)
            elif action == "translate":
                value = outer.translate(source, *args)
            else:
                value = outer.render(source, *args)
            events.append(
                {
                    "value": value,
                    "failures": snapshot(tr.effect_unit_failures),
                    "calls": list(calls),
                }
            )
        results.append({"name": case["name"], "events": events})
    return results
