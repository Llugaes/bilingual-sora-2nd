"""Replay the three P0 producers from shipped resources, never screenshot bytes."""

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


def visible(value):
    return re.sub(r"<[^<>]*>", "", re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", value, flags=re.S))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-dir",
        type=Path,
        default=Path(r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter"),
    )
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "generated/r25-production/catalog.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r26-p0-producers-current.json"
    )
    args = parser.parse_args()
    entries = [
        e
        for e in json.loads(args.catalog.read_text("utf8"))["entries"]
        if e["key"].startswith("table/")
    ]
    proof = json.loads((ROOT / "generated/r26-p0-target-producer-report.json").read_text("utf8"))[
        "locales"
    ]
    ranks = {}
    for locale in proof:
        with FpacArchive(args.game_dir / "pac/steam" / _TABLE_ARCHIVES[locale]) as archive:
            table = archive.read(_logical_tables(archive)["table/t_quest.tbl"])
        _, start, size, count = next(s for s in sections(table) if s[0] == "QuestRankBefore")
        ranks[locale] = {}
        for physical in range(count):
            at = start + size * physical
            identifier = struct.unpack_from("<I", table, at)[0]
            pointer = struct.unpack_from("<Q", table, at + 8)[0]
            ranks[locale][identifier] = table[pointer : table.index(b"\0", pointer)].decode("utf8")
    failures, cases, checks = [], [], 0
    for locale in proof:
        grammar = build_item_help_grammar(args.game_dir, entries, locale, languages=tuple(proof))
        contract = compile_item_help_headers(args.game_dir, entries, "ja", "zh-Hans", locale)
        tr = MenuTranslator(
            entries + grammar["status_entries"] + grammar["detail_entries"],
            "ja",
            "zh-Hans",
            locale,
            item_help_headers=contract,
        )
        texts = [
            ("all_ep", {l: proof[l]["all_ep"]["full_plain_source_candidates"][0] for l in proof})
        ]
        for variant in range(2):
            texts.append(
                (
                    "permanent_STR/" + str(variant),
                    {
                        l: proof[l]["permanent_STR"]["full_plain_source_candidates"][variant]
                        for l in proof
                    },
                )
            )
        for rank_id in ranks[locale]:
            texts.append(
                (
                    "junior/" + str(rank_id),
                    {
                        l: proof[l]["junior_rank_1"]["item"]["fields"]["description"].replace(
                            "%s", ranks[l][rank_id]
                        )
                        for l in proof
                    },
                )
            )
        for name, values in texts:
            source, plans = values[locale], {}
            for mode, target in (("primary", "ja"), ("secondary", "zh-Hans"), ("annotation", "ja")):
                plan = tr.render(source, mode)
                checks += 1
                if visible(plan["text"]) != visible(values[target]):
                    failures.append(
                        {
                            "locale": locale,
                            "case": name,
                            "mode": mode,
                            "expected": values[target],
                            "actual": plan,
                        }
                    )
                if mode == "annotation" and values["ja"] != values["zh-Hans"]:
                    if not plan["layers"] and "</R" not in plan["text"]:
                        failures.append(
                            {
                                "locale": locale,
                                "case": name,
                                "mode": mode,
                                "reason": "secondary annotation missing",
                            }
                        )
                if re.findall(r"<I\d+>", plan["text"]) != re.findall(r"<I\d+>", values[target]):
                    failures.append(
                        {
                            "locale": locale,
                            "case": name,
                            "mode": mode,
                            "reason": "native icon changed",
                        }
                    )
                plans[mode] = plan
            cases.append(
                {"name": name, "locale": locale, "source": source, "texts": values, "modes": plans}
            )
        model_file = args.output.with_name(args.output.stem + "-" + locale + "-model.json")
        model_file.write_text(json.dumps(tr.runtime_model(), ensure_ascii=False), "utf8")
    receipt = {
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures,
        "cases": cases,
        "input_origin": "static native producer reconstruction using shipped full resources; dynamic style and current save rank not captured",
        "game_attached": False,
    }
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), "utf8")
    print(
        json.dumps(
            {
                "checks": checks,
                "failure_count": len(failures),
                "failing_cases": sorted({r["case"] for r in failures}),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
