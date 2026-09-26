"""Offline 8-language semantic matrix against catalog-owned target strings."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import LANGUAGES

MODES = (("primary", 0), ("secondary", 1))
MIXED_KEYS = {
    "range_label": "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:6a15f570d7d4b310463cc8eb627186cd7e4586d9ab2b87e663ebb1e538c2d090/label",
    "range_size": "table/t_text.tbl/TXT_ITEM_HELP_RANGE_L",
    "effect_name_template": "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:cc311d9666993ad7471edb97a4292bd44de5cac259718aab39db45a6008a99a8/name",
    "effect_size": "table/t_text.tbl/TXT_ITEM_HELP_SMALL",
    "description": "table/t_skill.tbl/sha256:139a56fe653e61a1c69623e46e9cfbf650b3f7318a0a066168aa889ed42ffab9/description",
}
VERIFIED_RANGE_LABEL = MIXED_KEYS["range_label"]
VERIFIED_RECOVERY_NAMES = {
    MIXED_KEYS["effect_name_template"],
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:df1cd77615efffbef0c60ea7948cf4aebb17da0a9efa21aea8d9794c8796d00c/name",
}


def complete(entries):
    return [
        e
        for e in entries
        if all(
            isinstance(e.get("texts", {}).get(l), str) and e["texts"][l].strip() for l in LANGUAGES
        )
    ]


def one(rows, description):
    if not rows:
        raise AssertionError(f"Missing real resource fixture: {description}")
    return rows[0]


def fixtures(entries):
    rows = complete(entries)
    marked = [e for e in rows if any("<R>" in value for value in e["texts"].values())]
    result = marked[:: max(1, len(marked) // 24)][:24]
    for prefix in (
        "table/t_name.tbl/",
        "table/t_chapter.tbl/",
        "table/t_item.tbl/",
        "table/t_skill.tbl/",
        "table/t_quest.tbl/NaviText/",
        "table/t_active_voice.tbl/",
    ):
        matching = [e for e in rows if e["key"].startswith(prefix)]
        result.extend(matching[:: max(1, len(matching) // 8)][:8])
    for prefix in (
        "script/scena/mp2000_ev.dat/EV_02_00_00/called/401/assembled_display",
        "script/scena/mp2000_ev.dat/EV_02_00_00/called/410/assembled_display",
        "script/scena/mp2000_ev.dat/EV_02_00_00/called/183/arg/1",
        "script/scena/mp2000_ev.dat/EV_02_00_00/called/444/arg/1",
        "script/scena/mp2010_04.dat/EV_01_36_00/called/366/assembled_display",
        "script/scena/mp2010_07.dat/QS201_07_00/called/933/assembled_display",
        "script/scena/mp2010_07.dat/QS201_07_00/called/935/assembled_display",
        "script/scena/mp2010_07.dat/QS201_07_00/called/941/assembled_display",
        "script/scena/mp2010_07.dat/QS201_07_00/called/944/assembled_display",
    ):
        result.append(one([e for e in rows if e["key"].startswith(prefix)], prefix))
    result.append(
        one([e for e in rows if e["key"] == "table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL"], "level")
    )
    result.append(
        one(
            [
                e
                for e in rows
                if e["key"].startswith("table/t_name.tbl/") and e["key"].endswith("/name")
            ],
            "save name",
        )
    )
    result.append(
        one(
            [
                e
                for e in rows
                if e["key"].startswith(
                    "script/scena/mp0000_ev.dat/EV_04_37_00/called/416/assembled_display"
                )
            ],
            "S5 emphasis",
        )
    )
    result.append(
        one(
            [e for e in rows if e["texts"].get("zh-Hans") == "完成总计<C3>15件</C>委托并汇报。"],
            "achievement colour",
        )
    )
    result.append(
        one(
            [e for e in rows if e["texts"].get("zh-Hans") == "完成总计<C3>25件</C>委托并汇报。"],
            "achievement colour 25",
        )
    )
    return list({e["key"]: e for e in result}.values())


def index_by_source(entries):
    result = {language: defaultdict(list) for language in LANGUAGES}
    for entry in entries:
        for language in LANGUAGES:
            value = entry.get("texts", {}).get(language)
            if isinstance(value, str) and value:
                result[language][value].append(entry)
    return result


def support_entries(source_index, selected, source_language, item_help):
    result = {}
    for entry in selected:
        for candidate in source_index[source_language].get(entry["texts"][source_language], []):
            result[candidate["key"]] = candidate
    # item_help_components() intentionally synthesizes only this bounded,
    # resource-defined family.  Include its inputs so matrix rows exercise
    # every range size and effect magnitude/template, rather than a single
    # reported L/small example.
    for candidate in item_help:
        result[candidate["key"]] = candidate
    return list(result.values())


def target_conflict(source_index, source_language, value, primary, secondary):
    variants = {
        (e.get("texts", {}).get(primary), e.get("texts", {}).get(secondary))
        for e in source_index[source_language].get(value, [])
    }
    return len(variants) > 1


def compose_mixed_slots(parts, language):
    v = {part["role"]: part["texts"][language] for part in parts}
    # The closer source is still under native audit.  These are three known
    # semantic slots inside fixed markup, deliberately without a guessed UI
    # separator/closer contract.
    return (
        "<C3><I299>"
        + v["range_label"]
        + v["range_size"]
        + "</C>\n<c698>"
        + (v["effect_name_template"] % v["effect_size"])
        + "</C>\n<C0>"
    )


def mixed_fixture_from_catalog(entries):
    by_key = {entry["key"]: entry for entry in entries}
    missing = [key for key in MIXED_KEYS.values() if key not in by_key]
    if missing:
        raise AssertionError(f"Catalog lacks stable mixed fixture key(s): {missing}")
    return {
        "components": [
            {"role": role, "key": key, "texts": by_key[key]["texts"]}
            for role, key in MIXED_KEYS.items()
            if role != "description"
        ],
        "skill": {"description": by_key[MIXED_KEYS["description"]]["texts"]},
    }


def component_slot_entries(entries):
    """Every resource-defined range/effect composition, in fixed markup."""
    by_key = {entry["key"]: entry for entry in entries}
    ranges = [by_key[VERIFIED_RANGE_LABEL]]
    sizes = [
        entry
        for entry in entries
        if entry.get("key", "").startswith("table/t_text.tbl/TXT_ITEM_HELP_RANGE_")
        and entry["key"].rsplit("_", 1)[-1] in {"S", "M", "L", "LL"}
        and complete([entry])
    ]
    effects = [by_key[key] for key in sorted(VERIFIED_RECOVERY_NAMES)]
    magnitudes = [
        entry
        for entry in entries
        if entry.get("key", "").startswith("table/t_text.tbl/TXT_ITEM_HELP_")
        and entry["key"].rsplit("_", 1)[-1]
        in {"MOSTSMALL", "SMALL", "MIDDLE", "LARGE", "MOSTLARGE"}
        and complete([entry])
    ]
    candidates = [
        entry
        for entry in entries
        if entry.get("key", "").startswith(
            (
                "table/t_itemhelp.tbl/SkillRangeHelpData/",
                "table/t_itemhelp.tbl/SkillEffectHelpData/",
            )
        )
        and entry["key"].rsplit("/", 1)[-1] in {"label", "short_label", "name", "format"}
    ]
    return ranges, sizes, effects, magnitudes, len(candidates) - len(ranges) - len(effects)


def component_slot_cases(slot_entries, source_language, primary, secondary):
    ranges, sizes, effects, magnitudes, _ = slot_entries
    cases = []
    for label in ranges:
        for size in sizes:
            cases.append(
                {
                    "fixture": f"range:{label['key']}+{size['key']}",
                    "source": "<C3><I299>"
                    + label["texts"][source_language]
                    + size["texts"][source_language]
                    + "</C>",
                    "expected": "<C3><I299>"
                    + label["texts"][primary]
                    + size["texts"][primary]
                    + "</C>",
                    "secondary_expected": "<C3><I299>"
                    + label["texts"][secondary]
                    + size["texts"][secondary]
                    + "</C>",
                }
            )
    for effect in effects:
        for magnitude in magnitudes:
            cases.append(
                {
                    "fixture": f"effect:{effect['key']}+{magnitude['key']}",
                    "source": "<c698>"
                    + (effect["texts"][source_language] % magnitude["texts"][source_language])
                    + "</C>",
                    "expected": "<c698>"
                    + (effect["texts"][primary] % magnitude["texts"][primary])
                    + "</C>",
                    "secondary_expected": "<c698>"
                    + (effect["texts"][secondary] % magnitude["texts"][secondary])
                    + "</C>",
                }
            )
    return cases


def run_matrix(entries, mixed_fixture, slice_index=0, slice_count=1):
    selected, source_index = fixtures(entries), index_by_source(entries)
    item_help = [
        e
        for e in entries
        if e.get("key", "").startswith(("table/t_itemhelp.tbl/", "table/t_text.tbl/TXT_ITEM_HELP_"))
    ]
    parts, description = mixed_fixture["components"], mixed_fixture["skill"]["description"]
    slot_entries = component_slot_entries(entries)
    unverified_slot_templates = slot_entries[-1]
    (
        py_failures,
        batches,
        semantic_checks,
        ambiguous_skipped,
        component_ambiguous,
        component_attempted,
    ) = [], [], 0, 0, [], 0
    for source_language in LANGUAGES:
        supported = support_entries(source_index, selected, source_language, item_help)
        # The native-audit description is an independent catalog fixture, not
        # necessarily the generic table/t_skill sample selected above.
        for entry in entries:
            if entry.get("texts") == description:
                supported.append(entry)
        for primary in LANGUAGES:
            for secondary in LANGUAGES:
                configuration = (
                    LANGUAGES.index(source_language) * len(LANGUAGES) ** 2
                    + LANGUAGES.index(primary) * len(LANGUAGES)
                    + LANGUAGES.index(secondary)
                )
                if configuration % slice_count != slice_index:
                    continue
                translator = MenuTranslator(supported, primary, secondary, source_language)
                cases, parity_cases, keyed_cases, ambiguous_cases = [], [], [], []
                for entry in selected:
                    source = entry["texts"][source_language]
                    for mode in ("annotation", "bilingual", "primary", "secondary"):
                        parity_cases.append(
                            {
                                "source": source,
                                "mode": mode,
                                "plan": translator.render(source, mode),
                            }
                        )
                    for mode, side in MODES:
                        conflict = target_conflict(
                            source_index, source_language, source, primary, secondary
                        )
                        if conflict and translator.raw_pair(source) is not None:
                            # The global display-priority route chose a pair,
                            # but source-only input cannot establish which
                            # colliding catalog identity supplied it.
                            ambiguous_skipped += 1
                            if entry["key"].startswith("table/t_text.tbl/"):
                                keyed_cases.append(
                                    {
                                        "source": source,
                                        "mode": mode,
                                        "expected": entry["texts"][(primary, secondary)[side]],
                                        "key": entry["key"].removeprefix("table/t_text.tbl/"),
                                        "fixture": entry["key"],
                                        "source_language": source_language,
                                        "primary": primary,
                                        "secondary": secondary,
                                        "classification": "keyed_resource_semantic_mismatch",
                                    }
                                )
                            continue
                        expected = (
                            source if conflict else entry["texts"][(primary, secondary)[side]]
                        )
                        actual = translator.render(source, mode)["text"]
                        semantic_checks += 1
                        if actual != expected:
                            py_failures.append(
                                {
                                    "runtime": "python",
                                    "fixture": entry["key"],
                                    "source_language": source_language,
                                    "primary": primary,
                                    "secondary": secondary,
                                    "mode": mode,
                                    "expected": expected,
                                    "actual": actual,
                                    "classification": "global_route_unresolved"
                                    if conflict
                                    else "semantic_mismatch",
                                }
                            )
                        cases.append(
                            {
                                "source": source,
                                "mode": mode,
                                "expected": expected,
                                "fixture": entry["key"],
                                "source_language": source_language,
                                "primary": primary,
                                "secondary": secondary,
                                "classification": "global_route_unresolved"
                                if conflict
                                else "semantic_mismatch",
                            }
                        )
                        if entry["key"].startswith("table/t_text.tbl/"):
                            keyed_cases.append(
                                {
                                    "source": source,
                                    "mode": mode,
                                    "expected": entry["texts"][(primary, secondary)[side]],
                                    "key": entry["key"].removeprefix("table/t_text.tbl/"),
                                    "fixture": entry["key"],
                                    "source_language": source_language,
                                    "primary": primary,
                                    "secondary": secondary,
                                    "classification": "keyed_resource_semantic_mismatch",
                                }
                            )
                source = compose_mixed_slots(parts, source_language) + description[source_language]
                for mode, side in MODES:
                    target = (primary, secondary)[side]
                    expected = compose_mixed_slots(parts, target) + description[target]
                    actual = translator.render(source, mode)["text"]
                    semantic_checks += 1
                    if actual != expected:
                        py_failures.append(
                            {
                                "runtime": "python",
                                "fixture": "audit-mixed-header-8lang-slots-no-closer",
                                "source_language": source_language,
                                "primary": primary,
                                "secondary": secondary,
                                "mode": mode,
                                "expected": expected,
                                "actual": actual,
                                "classification": "known_composite_semantic_mismatch",
                            }
                        )
                    cases.append(
                        {
                            "source": source,
                            "mode": mode,
                            "expected": expected,
                            "fixture": "audit-mixed-header-8lang-slots-no-closer",
                            "source_language": source_language,
                            "primary": primary,
                            "secondary": secondary,
                            "classification": "known_composite_semantic_mismatch",
                        }
                    )
                slot_cases = component_slot_cases(slot_entries, source_language, primary, secondary)
                slot_variants = defaultdict(set)
                for slot in slot_cases:
                    slot_variants[slot["source"]].add(
                        (slot["expected"], slot["secondary_expected"])
                    )
                for slot in slot_cases:
                    variants = slot_variants[slot["source"]]
                    for mode, expected in (
                        ("primary", slot["expected"]),
                        ("secondary", slot["secondary_expected"]),
                    ):
                        component_attempted += 1
                        actual = translator.render(slot["source"], mode)["text"]
                        if actual != expected:
                            side = 0 if mode == "primary" else 1
                            alternatives = {pair[side] for pair in variants}
                            category = (
                                "original"
                                if actual == slot["source"]
                                else "other_variant"
                                if actual in alternatives
                                else "unexpected"
                            )
                            detail = {
                                "fixture": slot["fixture"],
                                "source_language": source_language,
                                "primary": primary,
                                "secondary": secondary,
                                "mode": mode,
                                "expected": expected,
                                "actual": actual,
                                "variants": [list(pair) for pair in variants],
                                "actual_category": category,
                            }
                            if len(variants) > 1 and category != "unexpected":
                                component_ambiguous.append(detail)
                                ambiguous_cases.append(
                                    {
                                        "source": slot["source"],
                                        "mode": mode,
                                        "fixture": slot["fixture"],
                                        "source_language": source_language,
                                        "primary": primary,
                                        "secondary": secondary,
                                        "variants": [list(pair) for pair in variants],
                                    }
                                )
                                continue
                            py_failures.append(
                                {
                                    "runtime": "python",
                                    "classification": "component_slot_semantic_mismatch",
                                    **detail,
                                }
                            )
                        semantic_checks += 1
                        cases.append(
                            {
                                "source": slot["source"],
                                "mode": mode,
                                "expected": expected,
                                "fixture": slot["fixture"],
                                "source_language": source_language,
                                "primary": primary,
                                "secondary": secondary,
                                "classification": "component_slot_semantic_mismatch",
                            }
                        )
                name = next(
                    e
                    for e in selected
                    if e["key"].startswith("table/t_name.tbl/") and e["key"].endswith("/name")
                )
                level = next(
                    e for e in selected if e["key"] == "table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL"
                )
                composite = (
                    " ·"
                    + name["texts"][source_language]
                    + "  "
                    + level["texts"][source_language]
                    + "39"
                )
                for mode in ("annotation", "bilingual", "primary", "secondary"):
                    parity_cases.append(
                        {
                            "source": composite,
                            "mode": mode,
                            "plan": translator.render(composite, mode),
                        }
                    )
                batches.append(
                    {
                        "model": translator.runtime_model(),
                        "cases": cases,
                        "keyed_cases": keyed_cases,
                        "ambiguous_cases": ambiguous_cases,
                        "parity_cases": parity_cases,
                    }
                )
    return (
        selected,
        batches,
        py_failures,
        semantic_checks,
        ambiguous_skipped,
        component_ambiguous,
        component_attempted,
        unverified_slot_templates,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "generated/catalog.json")
    parser.add_argument("--mixed-fixture", type=Path)
    parser.add_argument("--slice", default="0/1", help="zero-based shard index/count")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/language-matrix-check.json"
    )
    args = parser.parse_args()
    slice_index, slice_count = (int(value) for value in args.slice.split("/", 1))
    if not 0 <= slice_index < slice_count:
        raise ValueError("--slice must be INDEX/COUNT with 0 <= INDEX < COUNT")
    entries = json.loads(args.catalog.read_text(encoding="utf-8"))["entries"]
    mixed_fixture = (
        json.loads(args.mixed_fixture.read_text(encoding="utf-8"))
        if args.mixed_fixture
        else mixed_fixture_from_catalog(entries)
    )
    (
        selected,
        batches,
        py_failures,
        checks,
        ambiguous_skipped,
        component_ambiguous,
        component_attempted,
        unverified_slot_templates,
    ) = run_matrix(entries, mixed_fixture, slice_index, slice_count)
    fixture = ROOT / f"generated/markup-language-matrix-{slice_index}.tmp.json"
    fixture.write_text(json.dumps(batches, ensure_ascii=False), encoding="utf-8")
    code = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');const bad=[],all=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));let n=0,parity=0;for(const b of all){const r=new RuntimeText(b.model);for(const c of b.parity_cases){assert.deepEqual(r.render(c.source,c.mode),c.plan);parity++;}for(const c of [...b.cases,...b.keyed_cases]){const actual=r.render(c.source,c.mode,c.key||'').text;n++;if(actual!==c.expected)bad.push({...c,actual});}for(const c of b.ambiguous_cases){const actual=r.render(c.source,c.mode).text,side=c.mode==='primary'?0:1,values=new Set(c.variants.map(v=>v[side]));n++;if(actual!==c.source&&!values.has(actual))bad.push({...c,actual,classification:'component_ambiguous_unexpected'});}}console.log(JSON.stringify({checks:n,parity,failures:bad}));"""
    try:
        run = subprocess.run(
            ["node", "-e", code, str(fixture)], cwd=ROOT, capture_output=True, text=True, check=True
        )
    finally:
        fixture.unlink(missing_ok=True)
    js = json.loads(run.stdout)

    def failure_group(rows):
        groups = defaultdict(int)
        for row in rows:
            groups[row["classification"]] += 1
        return dict(groups)

    def fixture_group(rows):
        groups = defaultdict(int)
        for row in rows:
            groups[row["fixture"]] += 1
        return dict(groups)

    report = {
        "contract": "primary/secondary rendered text is compared with catalog-owned target strings; no resolver creates expected values",
        "matrix": {
            "source_x_primary_x_secondary": len(LANGUAGES) ** 3,
            "configurations_checked": len(batches),
            "slice": f"{slice_index}/{slice_count}",
            "languages": list(LANGUAGES),
            "fixtures": [e["key"] for e in selected] + ["audit-mixed-header-8lang-slots-no-closer"],
            "semantic_checks_per_runtime": checks,
            "ambiguous_source_only_cases_skipped": ambiguous_skipped,
            "component_slot_cases_ambiguous": len(component_ambiguous),
            "component_slot_cases_attempted": component_attempted,
            "unverified_slot_templates": unverified_slot_templates,
            "component_slot_ambiguous_examples": component_ambiguous[:100],
            "javascript_keyed_semantic_checks": js["checks"],
            "python_javascript_parity_cases": js["parity"],
        },
        "failures": {
            "python": {
                "count": len(py_failures),
                "by_classification": failure_group(py_failures),
                "by_fixture": fixture_group(py_failures),
                "examples": py_failures[:100],
            },
            "javascript": {
                "count": len(js["failures"]),
                "by_classification": failure_group(js["failures"]),
                "by_fixture": fixture_group(js["failures"]),
                "examples": js["failures"][:100],
            },
        },
        "not_a_screen_untranslated_count": True,
        "game_started": False,
        "game_attached": False,
        "code_sha256": hashlib.sha256(
            (ROOT / "sora_bilingual/localization/menu_text.py").read_bytes()
            + (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
        ).hexdigest(),
    }
    output = args.output
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(output),
                "python_failures": len(py_failures),
                "javascript_failures": len(js["failures"]),
                "checks": checks,
            }
        )
    )
    if py_failures or js["failures"]:
        raise SystemExit(
            "semantic language matrix has failures; see generated/language-matrix-check.json"
        )


if __name__ == "__main__":
    main()
