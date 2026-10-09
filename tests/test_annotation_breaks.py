"""Paragraph segmentation boundaries, independently of native glyph width."""

import json
from pathlib import Path
import re
import subprocess
import unittest

from sora_bilingual.localization.menu_text import annotation_plan, reflow_annotation_lines

ROOT = Path(__file__).resolve().parents[1]


class AnnotationBreakTests(unittest.TestCase):
    def test_aligned_rich_rows_keep_their_own_secondary_text_and_style(self):
        primary = "<c698>STR<I270> (4 turns), CP Regen</C>\n<C9>Grant fire protection and slowly increase CP."
        secondary = "<c698>4ターンSTR<I270>／CP徐々上昇</C>\n<C9>炎による守護を与えつつ、ＣＰを徐々に上昇させる。"
        plan = annotation_plan(primary, secondary)
        self.assertEqual(plan["layers"][0]["text"], secondary.split("\n")[0])
        self.assertEqual(plan["layers"][1]["text"], secondary.split("\n")[1] + "</C>")
        self.assertEqual(plan["text"].replace("<R></R_>", ""), primary)
        # A style crossing a hard row boundary belongs to both independent
        # lanes, while the text and an atomic native reading stay on that row.
        styled = annotation_plan("AAA\nBBB", "<C2><B><s24>一<R>二</Rに>\n三四</B></C>")
        self.assertEqual(styled["layers"][0]["text"], "<C2><B><s24>一<R>二</Rに></B></C>")
        self.assertEqual(styled["layers"][1]["text"], "<C2><B><s24>三四</B></C>")
        runner = r"""
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const assert=require('node:assert/strict');
for(const [a,b,p] of JSON.parse(require('fs').readFileSync(0,'utf8')))
 assert.deepEqual(RuntimeText.annotationPlan(a,b),p);
"""
        subprocess.run(
            ["node", "-e", runner],
            cwd=ROOT,
            check=True,
            input=json.dumps(
                [
                    (primary, secondary, plan),
                    ("AAA\nBBB", "<C2><B><s24>一<R>二</Rに>\n三四</B></C>", styled),
                ]
            ).encode(),
        )

    def test_official_water_pump_segments_keep_the_comma_with_the_previous_clause(self):
        # script/scena/mp3010_01.dat/QS802_08_00/called/84
        primary = "<C1>ポンプ装置の件を説明して\n備蓄してあるガソリンを分けてもらえないか頼んだ。"
        secondary = "<C1>说明了水泵装置的事，\n并询问是否能分装\n一些备用的汽油。"
        lines = reflow_annotation_lines(primary, secondary)
        visible = [re.sub("<[^<>]*>", "", line) for line in lines]
        self.assertEqual(len(lines), 2)
        self.assertTrue(visible[0].endswith("，"), visible)
        self.assertEqual("".join(visible), secondary.replace("<C1>", "").replace("\n", ""))
        self.assert_js_parity([(primary, secondary, lines)])

    def test_unicode_punctuation_words_and_readings_keep_safe_boundaries(self):
        # Layout probes; these synthetic strings are not linguistic evidence.
        probes = [
            ("甲乙\n丙丁", "<C1>甲乙，丙丁</C>"),
            ("甲乙\n丙丁", "甲乙：丙丁"),
            ("甲乙丙\n丁戊", "甲乙（丙丁戊）"),
            ("甲乙\n丙丁", "甲乙<R>丙</Rへい>，丁"),
            ("甲乙\n丙丁", "甲乙\u0301，丙丁"),
            ("甲乙\n丙丁", "Greek Ελληνικά words"),
            ("甲乙\n丙丁", "Latin café words"),
        ]
        cases = []
        for primary, secondary in probes:
            lines = reflow_annotation_lines(primary, secondary)
            visible = [re.sub("<[^<>]*>", "", line) for line in lines]
            self.assertEqual("".join(visible), re.sub("<[^<>]*>", "", secondary))
            self.assertFalse(any(line.startswith(("，", "：", "）", "\u0301")) for line in visible))
            self.assertFalse(any(line.endswith("（") for line in visible[:-1]))
            if "Ελληνικά" in secondary:
                self.assertTrue(any("Ελληνικά" in line for line in visible), visible)
            cases.append((primary, secondary, lines))
        self.assert_js_parity(cases)

    def assert_js_parity(self, cases):
        runner = r"""
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const assert=require('node:assert/strict');
for(const [a,b,expected] of JSON.parse(require('fs').readFileSync(0,'utf8')))
 assert.deepEqual(RuntimeText.reflowAnnotationLines(a,b),expected);
"""
        subprocess.run(
            ["node", "-e", runner], cwd=ROOT, check=True, input=json.dumps(cases).encode()
        )


if __name__ == "__main__":
    unittest.main()
