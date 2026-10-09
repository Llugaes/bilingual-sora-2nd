"""Replay CAB62 cooking outcomes from physical rows, without fake word inputs."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.item_help_headers import compile_item_help_headers
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.item_help_composition import _read_connect_groups
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

GAME = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
LANGUAGES = tuple(_TABLE_ARCHIVES)


def read_resources(locale):
    with FpacArchive(GAME / "pac/steam" / _TABLE_ARCHIVES[locale]) as archive:
        logical = _logical_tables(archive)
        item = archive.read(logical["table/t_item.tbl"])
        help_data = archive.read(logical["table/t_itemhelp.tbl"])
        note = archive.read(logical["table/t_notemenu.tbl"])

    def table(data, kind):
        _, start, size, count = next(row for row in sections(data) if row[0] == kind)
        return [
            (start + i * size, data[start + i * size : start + (i + 1) * size])
            for i in range(count)
        ]

    def text(data, at):
        pointer = struct.unpack_from("<Q", data, at)[0]
        return data[pointer : data.index(b"\0", pointer)].decode("utf8")

    items = {}
    item_rows = table(item, "ItemTableData")
    for physical, (at, row) in enumerate(item_rows):
        identifier = struct.unpack_from("<I", row)[0]
        items[identifier] = {
            "physical": physical,
            "mode": row[40],
            "category": row[41],
            "third": struct.unpack_from("<H", row, 42)[0],
            "name": text(item, at + 224),
            "body": text(item, at + 232),
            "slots": [
                struct.unpack_from("<4I", row, 60 + i * 16)
                for i in range(5)
                if struct.unpack_from("<I", row, 60 + i * 16)[0]
            ],
        }
    effects = {}
    kinds = {}
    for connection in _read_connect_groups(help_data):
        for identifier in connection["ids"]:
            kinds.setdefault(identifier, connection["kind"])
    for at, row in table(help_data, "SkillEffectHelpData"):
        identifier = struct.unpack_from("<I", row)[0]
        pointer, count, mode = struct.unpack_from("<QII", row, 16)
        effects[identifier] = {
            "mode": mode,
            "types": struct.unpack_from(f"<{count}I", help_data, pointer),
            "kind": kinds.get(identifier),
            "icon": struct.unpack_from("<I", row, 64)[0],
            "parameter_icon": struct.unpack_from("<I", row, 68)[0],
            **{
                field: text(help_data, at + offset)
                for field, offset in [
                    ("name", 8),
                    ("stat", 32),
                    ("format", 40),
                    ("colour", 48),
                    ("turns", 72),
                ]
            },
        }
    outcomes = set()
    for _, row in table(note, "NoteCookItem"):
        outcomes.update(i for i in struct.unpack_from("<3I", row, 4) if i)
    return items, effects, sorted(outcomes)


def effect_output(item, effects, constants, locale, join=" - ", compact=True, styled=False):
    """Audited r9=1 icon/name dispatch, kind10 late append and kind18 duration."""
    ordinary, deferred, skipped = [], [], set()
    icon_text = lambda icon: (f"<C9><I{icon}></C>" if compact else f"<I{icon}>") if icon else ""
    paint = lambda row, value: row["colour"] + value + "</C>" if styled else value
    slots = item["slots"]
    cure = [slot for slot in slots if slot[0] in (95, 96)]
    if cure:
        ids = tuple(slot[0] for slot in cure)
        if len(ids) == 2 and set(ids) == {95, 96}:
            value = constants["DEBUFF_CANCEL"][locale]
        elif len(ids) == 1:
            value = effects[ids[0]]["name"]
        else:
            raise ValueError("unproved repeated cure group")
        row = effects[ids[0]]
        deferred.append(icon_text(row["icon"]) + paint(row, value))
        skipped.update(ids)
    for ident, amount, turns, strength in slots:
        if ident in skipped:
            continue
        if ident in (12, 15):
            continue  # The attack header, rather than effects, consumes power.
        row = effects[ident]
        mode, types = row["mode"], row["types"]
        leading = icon_text(row["icon"])
        if row["kind"] == 7:
            members = [
                slot for slot in slots if slot[0] in effects and effects[slot[0]]["kind"] == 7
            ]
            value = constants["LINK"][locale].join(effects[slot[0]]["stat"] for slot in members)
            value += row["format"] % amount
            skipped.update(slot[0] for slot in members)
            ordinary.append(paint(row, value))
        elif row["kind"] == 6:
            if strength not in (1, 2, 3):
                raise ValueError("stat-down strength outside native ranks")
            ordinary.append(paint(row, row["stat"] + f"<I{266 + strength}>"))
        elif ident == 45:
            if turns != 30:
                raise ValueError("Delay magnitude outside fixed recipe proof")
            ordinary.append(paint(row, row["name"] % constants["SMALL"][locale]))
        elif 1200 <= ident <= 1205:
            duration = next((slot for slot in slots if slot[0] == 1206), None)
            if duration is None:
                raise ValueError("timed label without duration")
            value = row["stat"] + row["format"] % duration[1]
            skipped.add(1206)
            ordinary.append(paint(row, leading + value))
        elif mode == 0 and not types:
            if "%" in row["name"]:
                raise ValueError("unproved zero-parameter name format")
            ordinary.append(leading + paint(row, row["name"]))
        elif mode == 0 and types == (1,):
            ordinary.append(leading + paint(row, row["name"] % amount))
        elif mode == 0 and types == (4,):
            if row["kind"] != 13:
                raise ValueError("unproved percent recovery connection")
            # CAB62 34DB97..34DD05: ALL and percent use format+stat, never
            # name. The separate kind16 revival branch below retains name.
            magnitude = (
                constants["ALL"][locale] if amount == 100 else constants["PERSENT"][locale] % amount
            )
            form = row["format"] % magnitude
            value = (
                row["stat"] + (" " if locale == "ko" else "") + form
                if locale in ("ja", "zh-Hans", "zh-Hant", "ko")
                else form + row["stat"]
            )
            ordinary.append(leading + paint(row, value))
        elif mode == 1 and types in ((0, 1), (0, 4)):
            magnitude = (
                amount
                if types == (0, 1)
                else constants["ALL"][locale]
                if amount == 100
                else constants["PERSENT"][locale] % amount
            )
            value = (
                leading
                + row["stat"]
                + join
                + icon_text(row["parameter_icon"])
                + row["format"] % magnitude
            )
            ordinary.append(paint(row, value))
        elif mode == 0 and types == (16,):
            if strength not in (1, 2, 3):
                raise ValueError("type16 strength outside native ranks")
            arrow = f"<I{269 + strength}>"
            if locale == "en":
                value = row["stat"] + arrow + row["turns"] % turns
            else:
                value = re.sub(
                    r"%s|%d", lambda m: arrow if m[0] == "%s" else str(turns), row["name"]
                )
            ordinary.append(paint(row, value))
        else:
            raise ValueError(f"unreconstructed mode{mode} types{types} id{ident}")
    return join.join(ordinary + deferred)


def visible(text):
    return re.sub(r"<[^<>]*>", "", text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "generated/r32-recipe-producers.json")
    parser.add_argument("--locales", nargs="+", default=["en", "zh-Hans", "zh-Hant", "ja"])
    parser.add_argument("--models", action="store_true")
    parser.add_argument(
        "--inputs-only",
        action="store_true",
        help="Generate physical native inputs without building or validating a translator",
    )
    args = parser.parse_args()
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
    compact = {
        locale: {
            identifier: r
            for r in [*h["compact_rows"], *h["attack_rows"]]
            for identifier in r["item_ids"]
        }
        for locale, h in headers.items()
    }
    grammar = (
        None
        if args.inputs_only
        else build_item_help_grammar(GAME, entries, "en", languages=LANGUAGES)
    )
    outcomes = resources["en"][2]
    assert len(outcomes) == 157 and all(r[2] == outcomes for r in resources.values())
    cases, failures, unresolved = [], [], []
    for locale in args.locales:
        tr = (
            None
            if args.inputs_only
            else MenuTranslator(
                entries + grammar["status_entries"] + grammar["detail_entries"],
                "ja",
                "zh-Hans",
                locale,
                item_help_headers=headers[locale],
            )
        )
        for identifier in outcomes:
            for join in (" - ", " "):
                try:
                    values = {}
                    for language, (items, effects, _) in resources.items():
                        row = compact[language][identifier]
                        values[language] = (
                            row["prefix"]
                            + effect_output(items[identifier], effects, constants, language, join)
                            + row.get("close", [""])[0]
                        )
                except (ValueError, KeyError, TypeError) as error:
                    unresolved.append(
                        {
                            "locale": locale,
                            "item_id": identifier,
                            "join": join,
                            "reason": str(error),
                        }
                    )
                    continue
                plans = (
                    {}
                    if args.inputs_only
                    else {
                        mode: tr.render(values[locale], mode)
                        for mode in ("primary", "secondary", "annotation")
                    }
                )
                for mode, target in (
                    []
                    if args.inputs_only
                    else [("primary", "ja"), ("secondary", "zh-Hans"), ("annotation", "ja")]
                ):
                    if visible(plans[mode]["text"]) != visible(values[target]):
                        failures.append(
                            {
                                "locale": locale,
                                "item_id": identifier,
                                "join": join,
                                "mode": mode,
                                "source": values[locale],
                                "actual": plans[mode],
                                "expected": values[target],
                            }
                        )
                cases.append(
                    {
                        "locale": locale,
                        "item_id": identifier,
                        "join": join,
                        "source": values[locale],
                        "texts": values,
                        "modes": plans,
                    }
                )
        if args.models and tr is not None:
            args.out.with_name(args.out.stem + "-" + locale + "-model.json").write_text(
                json.dumps(tr.runtime_model(), ensure_ascii=False), "utf8"
            )
        print(
            json.dumps(
                {
                    "locale_done": locale,
                    "cases": len(cases),
                    "failures": len(failures),
                    "unresolved": len(unresolved),
                }
            ),
            flush=True,
        )
    result = {
        "schema": 1,
        "denominator_outcomes": 157,
        "categories": dict(Counter(resources["en"][0][i]["category"] for i in outcomes)),
        "checks": 0 if args.inputs_only else len(cases) * 3,
        "failure_count": len(failures),
        "failures": failures,
        "unresolved_producers": unresolved,
        "cases": cases,
        "actual_game_capture": False,
        "inputs_only": args.inputs_only,
        "source_locales": args.locales,
        "all_recovery_constructor": "CAB62 kind13 stat/format ALL branch; historical wrong name fixtures preserved separately",
        "input_origin": "physical NoteCookItem outcomes; CAB62 compact effect dispatcher; no invented words",
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("cases", "failures", "unresolved_producers")
            }
        )
    )
    return bool(failures or unresolved)


if __name__ == "__main__":
    raise SystemExit(main())
