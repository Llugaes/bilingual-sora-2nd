"""Composite labels exercise the public translator and final render plan."""

import json
from pathlib import Path
import subprocess
import unittest

from sora_bilingual.localization.menu_text import MenuTranslator

ROOT = Path(__file__).resolve().parents[1]


class CompositeTextTests(unittest.TestCase):
    def test_list_precedes_greedy_format_and_keeps_whole_resources(self):
        tr = MenuTranslator(
            [
                {"texts": {"ja": "封技", "en": "Seal"}},
                {"texts": {"ja": "HP徐々回復", "en": "HP Regen"}},
                {"texts": {"ja": "%s回復", "en": "Recover %s"}},
                {"texts": {"ja": "HP", "en": "HP"}},
                {"texts": {"ja": "単体･円", "en": "Single - Circle"}},
            ],
            "ja",
            "en",
            "ja",
        )
        for source, expected in (
            ("「封技･HP徐々回復」", "「Seal･HP Regen」"),
            ("<C3>封技･HP徐々回復</C>\nHP", "<C3>Seal･HP Regen</C>\nHP"),
            ("「単体･円」\nHP", "「Single - Circle」\nHP"),
        ):
            self.assertEqual(tr.translate(source, "secondary"), expected)

    def test_compound_string_argument_uses_same_boundaries_without_recursing_templates(self):
        entries = [
            {"texts": {"zh-Hans": "冻结", "ja": "凍結"}},
            {"texts": {"zh-Hans": "炎伤", "ja": "炎傷"}},
            {
                "texts": {
                    "zh-Hans": "对“%s”状态敌人造成的伤害+%d％",
                    "ja": "「%s」状態の敵に与えるダメージ+%d％",
                }
            },
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        source = "对“冻结·炎伤”状态敌人造成的伤害+25％"
        expected = "「凍結·炎傷」状態の敵に与えるダメージ+25％"
        self.assertEqual(tr.translate(source, "secondary"), expected)
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const d=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(d.model);
process.stdout.write(JSON.stringify([r.translate(d.source,'secondary'),r.render(d.source)]));
"""
        actual = json.loads(
            subprocess.run(
                ["node", "-e", script],
                input=json.dumps({"model": tr.runtime_model(), "source": source}),
                text=True,
                capture_output=True,
                cwd=ROOT,
                check=True,
            ).stdout
        )
        self.assertEqual(actual[0], expected)
        self.assertEqual(actual[1], tr.render(source))

    def test_delimited_components_have_no_member_count_limit(self):
        rows = [
            ("冻结", "凍結"),
            ("中毒", "毒"),
            ("炎伤", "炎傷"),
            ("延迟", "遅延"),
            ("HP吸收", "HP吸収"),
            ("魔法回避率+7%", "魔法回避率+7%"),
        ]
        tr = MenuTranslator([{"texts": {"zh-Hans": a, "ja": b}} for a, b in rows], "zh-Hans", "ja")
        cases = []
        for separator in ("·", "・", "･", "/", "／"):
            for count in (2, 3, 4, 5, 6, 32):
                members = [rows[i % len(rows)] for i in range(count)]
                for prefix, suffix in (("", ""), ("「", "」"), ("<c698>「", "」</C>")):
                    source = prefix + separator.join(a for a, _ in members) + suffix
                    expected = prefix + separator.join(b for _, b in members) + suffix
                    cases.append({"source": source, "expected": expected})
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(input.model);
process.stdout.write(JSON.stringify(input.cases.map(c=>({text:r.translate(c.source,'secondary'),plan:r.render(c.source,'annotation')}))));
"""
        result = subprocess.run(
            ["node", "-e", script],
            input=json.dumps({"model": tr.runtime_model(), "cases": cases}),
            text=True,
            capture_output=True,
            cwd=ROOT,
            check=True,
        )
        for case, actual in zip(cases, json.loads(result.stdout), strict=True):
            with self.subTest(source=case["source"]):
                self.assertEqual(tr.translate(case["source"], "secondary"), case["expected"])
                self.assertEqual(actual["text"], case["expected"])
                self.assertNotEqual(actual["plan"]["kind"], "plain")
                self.assertEqual(actual["plan"], tr.render(case["source"]))

    def test_complete_identity_and_unknown_parts_are_preserved(self):
        tr = MenuTranslator(
            [
                {"texts": {"zh-Hans": "冻结", "ja": "凍結"}},
                {"texts": {"zh-Hans": "炎伤", "ja": "炎傷"}},
                {"texts": {"zh-Hans": "冻结·炎伤", "ja": "完整资源译文"}},
                {"display_role": "dialogue", "texts": {"zh-Hans": "冲突·冻结", "ja": "译文一"}},
                {"display_role": "dialogue", "texts": {"zh-Hans": "冲突·冻结", "ja": "译文二"}},
            ],
            "zh-Hans",
            "ja",
        )
        self.assertEqual(tr.translate("冻结·炎伤", "secondary"), "完整资源译文")
        self.assertEqual(tr.translate("冲突·冻结", "secondary"), "冲突·冻结")
        self.assertEqual(tr.translate("冻结·未知·炎伤", "secondary"), "凍結·未知·炎傷")
        self.assertEqual(tr.translate("<I42>×3·冻结", "secondary"), "<I42>×3·凍結")
        self.assertEqual(tr.translate("0.7·×2", "secondary"), "0.7·×2")


if __name__ == "__main__":
    unittest.main()
