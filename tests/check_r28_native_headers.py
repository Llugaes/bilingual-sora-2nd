"""Replay bounded Tools producers; only one English header was captured live."""

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
PHYSICAL = (143, 145, 150, 151, *range(167, 177), 256)


def visible(text):
    return re.sub(r"<[^<>]*>", "", re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", text, flags=re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "generated/r28-header-scoped.json")
    args = parser.parse_args()
    game = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    entries = [
        e
        for e in json.loads((ROOT / "generated/r25-production/catalog.json").read_text("utf8"))[
            "entries"
        ]
        if e["key"].startswith("table/")
    ]
    catalogue = {e["key"]: e["texts"] for e in entries}
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
    scalar, contracts = {}, {}
    for locale in LANGUAGES:
        with FpacArchive(game / "pac/steam" / _TABLE_ARCHIVES[locale]) as archive:
            data = archive.read(_logical_tables(archive)["table/t_itemhelp.tbl"])
        _, start, size, count = next(s for s in sections(data) if s[0] == "SkillEffectHelpData")
        records = {}
        for j in range(count):
            at = start + j * size
            identifier = struct.unpack_from("<I", data, at)[0]
            pointer = struct.unpack_from("<Q", data, at + 16)[0]
            n, mode = struct.unpack_from("<II", data, at + 24)
            icon, parameter_icon = struct.unpack_from("<II", data, at + 64)
            records[identifier] = (
                mode,
                struct.unpack_from(f"<{n}I", data, pointer),
                icon,
                parameter_icon,
            )
        scalar[locale] = records
        contracts[locale] = {
            r["physical"]: r
            for r in compile_item_help_headers(game, entries, "ja", "zh-Hans", locale)["rows"]
        }
    assert all(scalar[l] == scalar[LANGUAGES[0]] for l in LANGUAGES)

    def effect(physical, locale, styled, separator):
        slots = [s for s in bodies[physical]["effect_slots"] if s[0]]
        values, skip = [], set()
        colour = lambda t: "<c698>" + t + "</C>" if styled else t
        for identifier, amount, second, third in slots:
            if identifier in skip:
                continue
            mode, types, icon, parameter_icon = scalar[locale][identifier]
            leading = f"<I{icon}>" if icon else ""
            if identifier == 1203:
                # The existing timed constructor binds the companion's slot1;
                # the pictured meal's real group includes heal + timed pair.
                duration = next(s[1] for s in slots if s[0] == 1206)
                assert mode == 0 and types == () and scalar[locale][1206] == (0, (1,), 0, 0)
                value = (
                    fields[(identifier, "name")][locale]
                    + fields[(identifier, "format")][locale] % duration
                )
                skip.add(1206)
                values.append(leading + colour(value))
            elif mode == 0 and types == (1,):
                values.append(leading + colour(fields[(identifier, "name")][locale] % amount))
            elif identifier == 125:
                assert amount == 100 and types == (4,) and mode == 0
                values.append(
                    leading
                    + colour(fields[(identifier, "name")][locale] % constants["ALL"][locale])
                )
            elif mode == 1 and types == (0, 1):
                values.append(
                    leading
                    + fields[(identifier, "stat")][locale]
                    + separator
                    + f"<I{parameter_icon}>"
                    + colour(fields[(identifier, "format")][locale] % amount)
                )
            else:
                raise AssertionError((physical, identifier, mode, types))
        return constants["FORMAT8"][locale].join(values)

    cases, failures, body_checks = [], [], 0
    for locale in LANGUAGES:
        grammar = build_item_help_grammar(game, entries, locale, languages=LANGUAGES)
        tr = MenuTranslator(
            entries + grammar["status_entries"] + grammar["detail_entries"],
            "ja",
            "zh-Hans",
            locale,
            item_help_headers={"schema": 1, "rows": list(contracts[locale].values())},
        )
        for physical in PHYSICAL:
            for styled in (False, True):
                separators = (" ", " - ") if 167 <= physical <= 176 or physical == 151 else (" - ",)
                for separator in separators:
                    values = {}
                    for l in LANGUAGES:
                        h = contracts[l][physical]
                        values[l] = (
                            h["prefix"]
                            + effect(physical, l, styled, separator)
                            + h["close"][0]
                            + "\n"
                            + bodies[physical]["texts"][l]
                        )
                    if physical == 145 and styled:
                        observed = json.loads(
                            (
                                ROOT / "generated/r27-live-test001-firstline-capture-receipt.json"
                            ).read_text("utf8")
                        )["rows"][0]["observed_english_header"]
                        assert values["en"].split("\n")[0] == observed
                    source, plans = values[locale], {}
                    for mode, target in (
                        ("primary", "ja"),
                        ("secondary", "zh-Hans"),
                        ("annotation", "ja"),
                    ):
                        plan = tr.render(source, mode)
                        if visible(plan["text"]) != visible(values[target]):
                            failures.append(
                                {
                                    "locale": locale,
                                    "physical": physical,
                                    "styled": styled,
                                    "separator": separator,
                                    "mode": mode,
                                    "actual": plan,
                                    "expected": values[target],
                                }
                            )
                        plans[mode] = plan
                        body_plan = tr.render(bodies[physical]["texts"][locale], mode)
                        if visible(body_plan["text"]) != visible(bodies[physical]["texts"][target]):
                            failures.append(
                                {
                                    "locale": locale,
                                    "physical": physical,
                                    "mode": mode,
                                    "body": body_plan,
                                }
                            )
                        body_checks += 1
                    cases.append(
                        {
                            "name": f"item/{physical}/styled/{styled}/separator/{separator}",
                            "locale": locale,
                            "physical": physical,
                            "styled": styled,
                            "source": source,
                            "texts": values,
                            "modes": plans,
                            "input_origin": "observed exact English header + resource body reconstruction"
                            if physical == 145 and styled and locale == "en"
                            else "static native resource reconstruction; colour placement diagnostic variant, not captured setter",
                        }
                    )
        args.out.with_name(args.out.stem + "-" + locale + "-model.json").write_text(
            json.dumps(tr.runtime_model(), ensure_ascii=False), "utf8"
        )
    result = {
        "checks": len(cases) * 3,
        "body_checks": body_checks,
        "failure_count": len(failures),
        "failures": failures,
        "cases": cases,
        "actual_full_setter_captured": False,
        "owners_keys_scopes_supplied": False,
        "source_proofs": [
            "r26-p0-effect-native-trace.json",
            "r26-p0-effect-style-trace.json",
            "r27-live-test001-firstline-capture-receipt.json",
        ],
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("cases", "failures")}))
    print(json.dumps(failures[:3], ensure_ascii=False))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
