"""Audit all admitted item headers using physical slots and native field rules.

Reconstructed inputs remain distinct from the two captured English headers.
Unsupported native parameter branches are recorded, never replaced with words.
"""

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.item_help_headers import compile_item_help_headers
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

LANGUAGES = tuple(_TABLE_ARCHIVES)


def visible(text):
    return re.sub(r"<[^<>]*>", "", re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", text, flags=re.S))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "generated/r30-tools-producers.json")
    ap.add_argument("--locales", nargs="+", default=list(LANGUAGES))
    args = ap.parse_args()
    game = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    entries = [
        e
        for e in json.loads((ROOT / "generated/r25-production/catalog.json").read_text("utf8"))[
            "entries"
        ]
        if e["key"].startswith("table/")
    ]
    raw = json.loads((ROOT / "generated/r25-raw-entity-denominator.json").read_text("utf8"))["rows"]
    bodies = {
        r["row"]: r for r in raw if r["kind"] == "ItemTableData" and r["field"] == "description"
    }
    fields = {
        (r["entity_id"], r["field"]): r["texts"] for r in raw if r["kind"] == "SkillEffectHelpData"
    }
    constants = {
        e["key"].removeprefix("table/t_text.tbl/TXT_ITEM_HELP_"): e["texts"]
        for e in entries
        if e["key"].startswith("table/t_text.tbl/TXT_ITEM_HELP_")
    }
    headers = {l: compile_item_help_headers(game, entries, "ja", "zh-Hans", l) for l in LANGUAGES}
    by_physical = {l: {r["physical"]: r for r in h["rows"]} for l, h in headers.items()}
    with FpacArchive(game / "pac/steam" / _TABLE_ARCHIVES["en"]) as z:
        data = z.read(_logical_tables(z)["table/t_itemhelp.tbl"])
    _, start, size, count = next(s for s in sections(data) if s[0] == "SkillEffectHelpData")
    scalar = {}
    for i in range(count):
        at = start + i * size
        ident = struct.unpack_from("<I", data, at)[0]
        pointer, n, mode = struct.unpack_from("<QII", data, at + 16)
        scalar[ident] = (
            mode,
            struct.unpack_from(f"<{n}I", data, pointer),
            *struct.unpack_from("<II", data, at + 64),
        )

    def effect(physical, locale, styled, percent_at_100=False):
        result = []
        skip = set()
        slots = [s for s in bodies[physical]["effect_slots"] if s[0]]
        color = lambda t: "<c698>" + t + "</C>" if styled else t
        for ident, amount, turns, strength in slots:
            if ident in skip:
                continue
            mode, types, icon, param_icon = scalar[ident]
            leading = f"<I{icon}>" if icon else ""
            name = fields[ident, "name"][locale]
            if ident in range(1200, 1206):
                companion = next((s for s in slots if s[0] == 1206), None)
                if companion is None:
                    raise ValueError("timed label without duration")
                result.append(
                    leading + color(name + fields[ident, "format"][locale] % companion[1])
                )
                skip.add(1206)
            elif mode == 0 and not types:
                if "%" in name:
                    raise ValueError("unproved literal printf")
                result.append(leading + color(name))
            elif mode == 0 and types == (1,):
                result.append(leading + color(name % amount))
            elif mode == 0 and types == (4,):
                if amount == 100 and not percent_at_100:
                    result.append(leading + color(name % constants["ALL"][locale]))
                else:
                    # The native percentage branch uses format/stat, not name.
                    # Captured English effect123 proves Recover 75% HP with
                    # this color topology. Locale order follows the existing
                    # native type4 contract; raw resource fields own the words.
                    magnitude = constants["PERSENT"][locale] % amount
                    form = fields[ident, "format"][locale] % magnitude
                    stat = fields[ident, "stat"][locale]
                    phrase = (
                        stat + (" " if locale == "ko" else "") + form
                        if locale in ("ja", "zh-Hans", "zh-Hant", "ko")
                        else form + stat
                    )
                    result.append(
                        "<c698><C9>" + leading + "</C>" + phrase + "</C>"
                        if styled
                        else leading + phrase
                    )
            elif mode == 1 and types in ((0, 1), (0, 4)):
                if ident == 121:
                    raise ValueError("ID121 magnitude branch not reconstructed")
                stat = fields[ident, "stat"][locale]
                value = (
                    amount
                    if types == (0, 1)
                    else (
                        constants["ALL"][locale]
                        if amount == 100
                        else constants["PERSENT"][locale] % amount
                    )
                )
                form = fields[ident, "format"][locale] % value
                middle = f"<I{param_icon}>"
                if styled and leading:
                    result.append(
                        "<c698><C9>"
                        + leading
                        + "</C>"
                        + stat
                        + "<C9> - "
                        + middle
                        + "</C>"
                        + form
                        + "</C>"
                    )
                elif styled:
                    result.append("<c698>" + stat + "<C9> - " + middle + "</C>" + form + "</C>")
                else:
                    result.append(leading + stat + " - " + middle + form)
            elif mode == 0 and types == (16,):
                if strength not in (1, 2, 3):
                    raise ValueError("type16 strength outside proved icon ranks")
                arrow = f"<I{269 + strength}>"
                if locale == "en":
                    value = (
                        fields[ident, "stat"][locale]
                        + arrow
                        + fields[ident, "turns"][locale] % turns
                    )
                else:
                    value = re.sub(r"%s|%d", lambda m: arrow if m[0] == "%s" else str(turns), name)
                result.append(color(value))
            else:
                raise ValueError(f"unreconstructed native mode{mode} types{types} id{ident}")
        return " - ".join(result)

    cases = []
    unresolved = []
    failures = []
    checks = 0
    body_checks = 0
    for locale in args.locales:
        grammar = build_item_help_grammar(game, entries, locale, languages=LANGUAGES)
        tr = MenuTranslator(
            entries + grammar["status_entries"] + grammar["detail_entries"],
            "ja",
            "zh-Hans",
            locale,
            item_help_headers=headers[locale],
        )
        for physical in by_physical[locale]:
            has_all_type4 = any(
                s[0] in (123, 125) and s[1] == 100 for s in bodies[physical]["effect_slots"]
            )
            variants = [(False, False), (True, False)] + (
                [(False, True), (True, True)] if has_all_type4 else []
            )
            for styled, percent_at_100 in variants:
                try:
                    values = {
                        l: by_physical[l][physical]["prefix"]
                        + effect(physical, l, styled, percent_at_100)
                        + by_physical[l][physical]["close"][0]
                        + "\n"
                        + bodies[physical]["texts"][l]
                        for l in LANGUAGES
                    }
                except (ValueError, TypeError, KeyError) as err:
                    unresolved.append(
                        {
                            "locale": locale,
                            "physical": physical,
                            "styled": styled,
                            "percent_at_100": percent_at_100,
                            "reason": str(err),
                        }
                    )
                    continue
                source = values[locale]
                plans = {}
                for mode, target in [
                    ("primary", "ja"),
                    ("secondary", "zh-Hans"),
                    ("annotation", "ja"),
                ]:
                    p = tr.render(source, mode)
                    plans[mode] = p
                    checks += 1
                    if visible(p["text"]) != visible(values[target]):
                        failures.append(
                            {
                                "locale": locale,
                                "physical": physical,
                                "styled": styled,
                                "percent_at_100": percent_at_100,
                                "mode": mode,
                                "actual": p,
                                "expected": values[target],
                            }
                        )
                    bp = tr.render(bodies[physical]["texts"][locale], mode)
                    body_checks += 1
                    if visible(bp["text"]) != visible(bodies[physical]["texts"][target]):
                        failures.append(
                            {
                                "locale": locale,
                                "physical": physical,
                                "mode": mode,
                                "body_only": True,
                                "actual": bp,
                            }
                        )
                cases.append(
                    {
                        "name": f"native-item/{physical}/styled/{styled}/percent_at_100/{percent_at_100}",
                        "locale": locale,
                        "physical": physical,
                        "source": source,
                        "texts": values,
                        "modes": plans,
                        "input_origin": "physical resource/native field reconstruction; not captured setter",
                    }
                )
        args.out.with_name(args.out.stem + "-" + locale + "-model.json").write_text(
            json.dumps(tr.runtime_model(), ensure_ascii=False), "utf8"
        )
        print(
            json.dumps(
                {
                    "locale_done": locale,
                    "checks_so_far": checks,
                    "failed_assertions_so_far": len(failures),
                    "unresolved_source_variants": len(unresolved),
                }
            ),
            flush=True,
        )
    result = {
        "schema": 1,
        "denominator_item_headers": len(by_physical["en"]),
        "complete_mode_checks": checks,
        "body_checks": body_checks,
        "failure_count": len(failures),
        "failures": failures,
        "unresolved_source_reconstructions": unresolved,
        "cases": cases,
        "source_generation": "actual table slots and reviewed ordinary native field rules; uncertainty retained",
        "original_setter_captured": False,
        "capture_based_branch": "effect123 Recover 75% HP with C9/icon field edges; other items reconstructed",
        "r29_name_percent_fixtures_retained_and_not_used_as_real_branch_oracle": True,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["cases", "failures", "unresolved_source_reconstructions"]
            }
        )
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
