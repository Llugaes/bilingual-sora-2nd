"""Offline CAB62 ordinary Tools producer audit, independent of grammar templates.

Only physical table parameters and reviewed native branches produce inputs.
The plain presentation strips colour controls from the native styled wire; it
is explicitly not an alleged colour-off setter capture. Runtime flags retain
their uncertainty. The original r30 evidence and failed audits are read only.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from check_r32_recipe_producers import GAME, LANGUAGES, read_resources
from sora_bilingual.localization.item_help_headers import compile_item_help_headers
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator

EXE_SHA256 = "cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea"
PROOFS = {
    "slot_copy": "CAB62 RVA 23F5E0: Item+3C..7C -> normalized+30..70, five 16-byte slots",
    "first_connection": "345980: first physical connection match, including 95/96 kind10 before kind14",
    "ordinary": "347B70..34A1F8: kind3 FORMAT1 range + effects + FORMAT7 close/newline/body; r9=0",
    "literal": "34EF35..34F26E: plain icon before +48 colour; name receives getter parameter",
    "typed": "350195..350676: (0,1)/(0,4), separate icon/color/stat and icon/color/format lanes",
    "recovery": "34D6E3..34DDD0: kind13 format/stat locale ordering, first C9 icon inside effect colour",
    "stat": "34CAD2..34D337: LINK stat group, bare directional arrow; C5E6E0 nonzero turns prefix, zero suffix",
    "cure": "34D508..34D6CA;35098D..350A4E: kind10 first icon, DEBUFF_CANCEL if two members, deferred append",
    "timed": "34E8AF..34EAF0: first C9 icon + stat + format, companion1206 getter consumes slot1",
    "getter": "352A90..352D74: selector tables;40->352B03 slot2;122..127/150..154/223/224/226->352C44 slot1",
    "capture": "generated/r30-tools-real-failure-native-oracle.json: English physical387 displayed firstline + raw body",
}


class Unresolved(ValueError):
    pass


def printf(value, *arguments):
    """Resource printf only; reject unresolved placeholders instead of guessing."""
    try:
        return value % arguments if arguments else value.replace("%%", "%")
    except (TypeError, ValueError) as error:
        raise Unresolved(f"physical printf {value!r}: {error}") from error


def lanes(value):
    """Collapse both annotation lanes independently, retaining opaque controls."""
    pattern = r"<R>(.*?)</R([^<>]*)>"
    return tuple(
        re.sub(pattern, lambda m: m[1] if i == 0 else m[2], value, flags=re.S) for i in (0, 1)
    )


def visible(value):
    return re.sub(r"<[^<>]*>", "", value)


def plain(value):
    return re.sub(r"</?C(?:\d+)?>|<c\d+>", "", value)


def effect_output(item, effects, constants, locale, turns_first=None):
    """r9=0 producer, official locale ordering and percent-at100 disabled.

    These are declared native branch states, not claims about a live caller.
    No recipe helper's old name+format or independent cure append is reused.
    """
    ordinary, deferred, skipped, trace = [], [], set(), []
    slots = item["slots"]
    icon = lambda n: f"<I{n:03d}>" if n else ""
    c9 = lambda n: f"<C9><I{n}></C>" if n else ""
    paint = lambda row, text: row["colour"] + text + "</C>"
    const = lambda key: constants[key][locale]

    def getter(slot):
        # CAB62 selector table, read as true uint32 tags. Only nonzero slot2
        # Foresight is admitted: its zero fallback needs runtime skill data.
        if slot[0] == 40:
            if not slot[2]:
                raise Unresolved("Foresight zero slot2 runtime fallback")
            return slot[2]
        if slot[0] in (
            122,
            123,
            124,
            125,
            126,
            127,
            120,
            150,
            151,
            152,
            153,
            154,
            223,
            224,
            226,
            1206,
        ):
            return slot[1]
        raise Unresolved(f"unproved getter effect{slot[0]}")

    cure = [s for s in slots if effects[s[0]]["kind"] == 10]
    if cure:
        if len(cure) > 2 or len({s[0] for s in cure}) != len(cure):
            raise Unresolved("repeated cure group")
        if any(s[1:] != cure[0][1:] for s in cure):
            raise Unresolved("unequal cure group parameters")
        row = effects[cure[0][0]]
        text = const("DEBUFF_CANCEL") if len(cure) == 2 else row["name"]
        deferred.append(icon(row["icon"]) + paint(row, text))
        skipped.update(s[0] for s in cure)
        trace.append(
            {
                "branch": "kind10_deferred",
                "slots": cure,
                "flag60": int(len(cure) == 2),
                "output": deferred[-1],
                "proof": PROOFS["cure"],
            }
        )

    for slot in slots:
        ident, amount, turns, strength = slot
        if ident in skipped:
            continue
        row = effects[ident]
        mode, types, kind = row["mode"], row["types"], row["kind"]
        used = [slot]
        branch = "literal"
        if kind == 4 and types == (16,):
            used = [s for s in slots if effects[s[0]]["kind"] == 4 and s[1:] == slot[1:]]
            if strength not in (1, 2, 3) or not turns:
                raise Unresolved("stat rank/default turns outside physical proof")
            stats = const("LINK").join(effects[s[0]]["stat"] for s in used)
            duration = printf(row["turns"], turns)
            arrow = f"<I{269 + strength}>"
            if turns_first is None and locale in ("ja", "zh-Hans", "zh-Hant", "ko"):
                # Reviewed official CJK complete name owns printf order. The
                # group replaces only this row's stat with its LINK stat list.
                template = row["name"].replace(row["stat"], stats, 1)
                text = re.sub(
                    r"%s|%d", lambda match: arrow if match[0] == "%s" else str(turns), template
                )
            else:
                text = duration + stats + arrow if turns_first else stats + arrow + duration
            value = paint(row, text)
            skipped.update(s[0] for s in used)
            branch = "stat"
        elif kind == 18 and 1200 <= ident <= 1205:
            duration = [s for s in slots if s[0] == 1206]
            if len(duration) != 1:
                raise Unresolved("timed companion count differs from one")
            used += duration
            value = paint(
                row, c9(row["icon"]) + row["stat"] + printf(row["format"], getter(duration[0]))
            )
            skipped.add(1206)
            branch = "timed"
        elif kind == 13 and mode == 0 and types == (4,):
            used = [s for s in slots if effects[s[0]]["kind"] == 13 and s[1:] == slot[1:]]
            magnitude = const("ALL") if amount == 100 else printf(const("PERSENT"), getter(slot))
            stats = const("LINK").join(effects[s[0]]["stat"] for s in used)
            form = printf(effects[used[-1][0]]["format"], magnitude)
            text = (
                stats + (" " if locale == "ko" else "") + form
                if locale in ("ja", "zh-Hans", "zh-Hant", "ko")
                else form + stats
            )
            value = paint(row, c9(row["icon"]) + text)
            skipped.update(s[0] for s in used)
            branch = "recovery"
        elif mode == 1 and types in ((0, 1), (0, 4)):
            magnitude = getter(slot)
            if types == (0, 4):
                magnitude = (
                    const("ALL") if magnitude == 100 else printf(const("PERSENT"), magnitude)
                )
            value = icon(row["icon"]) + paint(row, row["stat"])
            value += (
                " - " + icon(row["parameter_icon"]) + paint(row, printf(row["format"], magnitude))
            )
            branch = "typed"
        elif mode == 0 and not types:
            if ident == 97 and cure:
                raise Unresolved("cure+97 absent in189 items; do not borrow SkillParam fixture")
            if re.search(r"%(?!%)", row["name"]):
                raise Unresolved("literal with unbound argument")
            value = icon(row["icon"]) + paint(row, printf(row["name"]))
        elif mode == 0 and types == (1,):
            value = icon(row["icon"]) + paint(row, printf(row["name"], getter(slot)))
        else:
            raise Unresolved(f"unproved mode{mode} uint32 types{types} kind{kind} effect{ident}")
        ordinary.append(value)
        trace.append({"branch": branch, "slots": used, "output": value, "proof": PROOFS[branch]})
    return " - ".join(ordinary + deferred), trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "generated/r32-tools-canonical-audit.json"
    )
    parser.add_argument("--locales", nargs="+", default=["en"])
    args = parser.parse_args()
    production_files = [
        "sora_bilingual/localization/item_help_headers.py",
        "sora_bilingual/localization/item_help_composition.py",
        "sora_bilingual/localization/menu_text.py",
    ]
    production_before = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in production_files
    }
    entries = [
        e
        for e in json.loads((ROOT / "generated/r25-production/catalog.json").read_text("utf8"))[
            "entries"
        ]
        if e["key"].startswith("table/")
    ]
    constants = {
        e["key"].removeprefix("table/t_text.tbl/TXT_ITEM_HELP_"): e["texts"]
        for e in entries
        if e["key"].startswith("table/t_text.tbl/TXT_ITEM_HELP_")
    }
    resources = {locale: read_resources(locale) for locale in LANGUAGES}
    headers = {
        locale: compile_item_help_headers(GAME, entries, "ja", "zh-Hans", locale)
        for locale in LANGUAGES
    }
    by_physical = {
        locale: {r["physical"]: r for r in header["rows"]} for locale, header in headers.items()
    }
    item_at = {
        locale: {r["physical"]: (ident, r) for ident, r in items.items()}
        for locale, (items, _, _) in resources.items()
    }
    physicals = sorted(by_physical["en"])
    if len(physicals) != 189 or any(sorted(rows) != physicals for rows in by_physical.values()):
        raise ValueError("ordinary189 denominator changed")
    sources, unresolved, parameter_failures = {}, [], []
    for physical in physicals:
        texts, alternate_texts, traces = {}, {}, {}
        for locale in LANGUAGES:
            ident, item = item_at[locale][physical]
            try:
                if item["slots"] != item_at["en"][physical][1]["slots"]:
                    raise Unresolved("cross-locale physical parameters differ")
                effect, traces[locale] = effect_output(
                    item, resources[locale][1], constants, locale
                )
                row = by_physical[locale][physical]
                # Prefix/close reuse is intentional: this audit owns effects,
                # and checks the admitted full Tools row plus its physical body.
                texts[locale] = (
                    row["prefix"]
                    + effect
                    + row["close"][0]
                    + "\n"
                    + item["body"].replace("%%", "%")
                )
                alternate_effect, _ = effect_output(
                    item,
                    resources[locale][1],
                    constants,
                    locale,
                    turns_first=locale not in ("ja", "zh-Hans", "zh-Hant", "ko"),
                )
                alternate_texts[locale] = (
                    row["prefix"]
                    + alternate_effect
                    + row["close"][0]
                    + "\n"
                    + item["body"].replace("%%", "%")
                )
            except (Unresolved, KeyError, TypeError) as error:
                failure = {
                    "physical": physical,
                    "item_id": ident,
                    "locale": locale,
                    "slots": item["slots"],
                    "reason": str(error),
                }
                unresolved.append(failure)
                parameter_failures.append(failure)
        if len(texts) == len(LANGUAGES):
            sources[physical] = {
                "texts": texts,
                "alternate_turns_first_texts": alternate_texts,
                "traces": traces,
            }
    capture = json.loads(
        (ROOT / "generated/r30-tools-real-failure-native-oracle.json").read_text("utf8")
    )
    capture_checks = []
    for case in capture["cases"]:
        reconstructed = sources.get(case["physical"], {}).get("texts", {}).get("en")
        capture_checks.append(
            {
                "physical": case["physical"],
                "source_sha256": hashlib.sha256(case["source"].encode()).hexdigest(),
                "exact_reconstruction_matches_capture_source": reconstructed == case["source"],
                "capture_kind": capture["capture_kind"],
                "original_setter_captured": False,
            }
        )
    cases, failures, wire_failures, target_state_unresolved, checks = [], [], [], [], 0
    for locale in args.locales:
        grammar = build_item_help_grammar(GAME, entries, locale, languages=LANGUAGES)
        tr = MenuTranslator(
            entries + grammar["status_entries"] + grammar["detail_entries"],
            "ja",
            "zh-Hans",
            locale,
            item_help_headers=headers[locale],
        )
        for physical, source in sources.items():
            ident, item = item_at[locale][physical]
            for styled in (False, True):
                values = (
                    source["texts"] if styled else {l: plain(t) for l, t in source["texts"].items()}
                )
                alternatives = (
                    source["alternate_turns_first_texts"]
                    if styled
                    else {l: plain(t) for l, t in source["alternate_turns_first_texts"].items()}
                )
                plans = {}
                for mode, target in [
                    ("primary", "ja"),
                    ("secondary", "zh-Hans"),
                    ("annotation", "ja"),
                ]:
                    plan = tr.render(values[locale], mode)
                    plans[mode] = plan
                    actual = lanes(plan["text"])[0]
                    expected = values[target]
                    checks += 1
                    common = {
                        "locale": locale,
                        "physical": physical,
                        "item_id": ident,
                        "name": item["name"],
                        "styled": styled,
                        "mode": mode,
                        "source": values[locale],
                        "actual": plan,
                        "expected": expected,
                        "alternative_expected_other_C5E6E0_state": alternatives[target],
                    }
                    if visible(actual) != visible(expected):
                        failures.append(common)
                        if visible(actual) == visible(alternatives[target]):
                            target_state_unresolved.append(common)
                    if actual != expected:
                        wire_failures.append(common)
                cases.append(
                    {
                        "locale": locale,
                        "physical": physical,
                        "item_id": ident,
                        "styled": styled,
                        "source": values[locale],
                        "texts": values,
                        "slots": item["slots"],
                        "modes": plans,
                        "input_origin": "physical resource + fixed CAB62 branches; not live setter",
                    }
                )
        print(
            json.dumps(
                {
                    "locale_done": locale,
                    "checks": checks,
                    "visible_failures": len(failures),
                    "wire_failures": len(wire_failures),
                    "unresolved": len(unresolved),
                }
            ),
            flush=True,
        )
    result = {
        "schema": 1,
        "exe_sha256": EXE_SHA256,
        "ordinary_denominator": 189,
        "target_resource_languages": list(LANGUAGES),
        "source_locales_checked": args.locales,
        "rebuilt_complete_physical_rows": len(sources),
        "rebuilt_styled_and_plain_variants": len(sources) * 2,
        "complete_three_mode_checks": checks,
        "failure_count": len(failures),
        "failures": failures,
        "other_runtime_state_match_count": len(target_state_unresolved),
        "other_runtime_state_matches_do_not_erase_failures": target_state_unresolved,
        "wire_failure_count": len(wire_failures),
        "wire_failures": wire_failures,
        "real_parameter_failures": parameter_failures,
        "unresolved_producers": unresolved,
        "branch_denominator": dict(
            Counter(t["branch"] for s in sources.values() for t in s["traces"]["en"])
        ),
        "capture_checks": capture_checks,
        "proofs": PROOFS,
        "unknown_runtime_state": [
            {
                "address": "C5E6E0",
                "branch": "stat turns order",
                "audited_state": "EN suffix; CJK official complete name; opposite native flag topology also listed",
                "live_value": None,
            },
            {
                "call": "345AC0(C5DCD0)",
                "branch": "kind13 stat/format order",
                "audited_state": "CJK stat-first; Western format-first; physical resource/capture oracle",
                "live_value": None,
            },
            {
                "call": "153390(C5DCD0)",
                "branch": "percentage-at100 override",
                "audited_state": False,
                "live_value": None,
            },
            {
                "address": "manager+623A31",
                "branch": "effect internal/deferred join",
                "audited_state": "nonzero / -",
                "live_value": None,
            },
            {
                "branch": "colour-off r9=0 setter",
                "audited_state": "plain is color-tag projection only",
                "live_value": None,
            },
        ],
        "absent_physical_branches": [
            "type12 magnitude not present in ordinary189",
            "cure+97 not present in ordinary189",
        ],
        "original_r30_artifacts_preserved": True,
        "actual_game_capture": False,
        "cases": cases,
        "constructors": sources,
        "production_source_sha256_before": production_before,
        "production_source_sha256_after": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in production_files
        },
    }
    result["production_snapshot_unchanged_during_audit"] = (
        result["production_source_sha256_before"] == result["production_source_sha256_after"]
    )
    result["failure_domains"] = dict(
        Counter(
            "header"
            if visible(lanes(r["actual"]["text"])[0].split("\n", 1)[0])
            != visible(r["expected"].split("\n", 1)[0])
            else "body"
            for r in failures
        )
    )
    result["failure_count_by_source_locale"] = dict(Counter(r["locale"] for r in failures))
    result["physical_uint32_parameter_tag_denominator"] = dict(
        Counter(
            str(tag)
            for physical in physicals
            for slot in item_at["en"][physical][1]["slots"]
            for tag in resources["en"][1][slot[0]]["types"]
        )
    )
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k
                not in (
                    "cases",
                    "constructors",
                    "failures",
                    "wire_failures",
                    "proofs",
                    "production_source_sha256_before",
                    "production_source_sha256_after",
                    "other_runtime_state_matches_do_not_erase_failures",
                )
            }
        )
    )
    return bool(
        failures
        or unresolved
        or any(not c["exact_reconstruction_matches_capture_source"] for c in capture_checks)
    )


if __name__ == "__main__":
    raise SystemExit(main())
