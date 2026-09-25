import json
from pathlib import Path
import subprocess
import unittest
from sora_bilingual.localization.menu_text import MenuTranslator

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTextTests(unittest.TestCase):
    def test_save_details_translate_every_line_and_preserve_levels(self):
        names = [
            ("艾丝蒂尔", "エステル"),
            ("克萝赛", "クローゼ"),
            ("雪拉扎德", "シェラザード"),
            ("奥利维尔", "オリビエ"),
        ]
        tr = MenuTranslator([{"texts": {"zh-Hans": a, "ja": b}} for a, b in names], "zh-Hans", "ja")
        cases = []
        for newline in ("\n", "\r\n", "\\n"):
            source = newline.join("　·" + a + "　　　Lv.39" for a, _ in names)
            plan = tr.render(source)
            for _, translated in names:
                self.assertIn(translated, plan["text"])
            self.assertEqual(plan["text"].count("Lv.39"), 4)
            self.assertNotIn("<R>39", plan["text"])
            cases.append({"source": source, "plan": plan})
        code = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(data.model);
for(const c of data.cases)assert.deepEqual(r.render(c.source),c.plan);"""
        result = subprocess.run(
            ["node", "-e", code],
            input=json.dumps({"model": tr.runtime_model(), "cases": cases}),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_annotation_filter_preserves_numeric_icon_and_untranslated_runs(self):
        pairs = [
            ("4", "４"),
            ("HP", "ＨＰ"),
            ("<I1544>", "<I1544>"),
            ("<s27>4", "<s30>４"),
            ("A\n4", "B\n４"),
            ("<C2>A</C>\n4", "<C2>B</C>\n４"),
        ]
        tr = MenuTranslator([{"texts": {"en": a, "fr": b}} for a, b in pairs], "en", "fr", "en")
        cases = [{"source": a, "plan": tr.render(a)} for a, _ in pairs]
        for case in cases[:4]:
            self.assertEqual(case["plan"], {"text": case["source"], "layers": [], "kind": "plain"})
        for case in cases[4:]:
            self.assertTrue(case["plan"]["text"].endswith("\n4"))
        code = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(data.model);
for(const c of data.cases)assert.deepEqual(r.render(c.source),c.plan);"""
        result = subprocess.run(
            ["node", "-e", code],
            input=json.dumps({"model": tr.runtime_model(), "cases": cases}),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_resolver_matches_python_for_composites_and_dialogue(self):
        entries = [
            {"texts": {"zh-Hans": a, "ja": b}}
            for a, b in [
                ("妈妈从刚才开始", "さっきからママが"),
                ("就一直盯着海报看。", "ポスターを見てるの。"),
                ("强化", "強化"),
                ("单体", "単体"),
                ("HP上限+%d", "最大HP+%d"),
                ("说明。", "説明。"),
                ("勇猛果敢", "勇猛果敢"),
                ("HP", "HP"),
                ("选择%s？", "%sを選択？"),
                ("艾丝蒂尔", "エステル"),
                ("甲\n乙", "一二"),
                ("保存", "セーブ"),
                ("保存", "セーブする"),
                ("第２章“大地翻腾”", "２章「荒ぶる大地」"),
            ]
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        sources = [
            "<#E_0#M_0#B_0>妈妈从刚才开始\n就一直盯着海报看。",
            "强化【<I299>单体：<c698>HP上限+20</C>】\n说明。",
            "勇猛果敢",
            "HP",
            "选择艾丝蒂尔？",
            "选择自定姓名？",
            "甲\n乙",
            "保存",
            "药草",
            "\n  单体\n",
            "constructor",
            "__proto__",
            "第２章“大地翻腾”\u3000\u3000\u3000\u3000 ＜Nightmare＞",
            "\u3000·艾丝蒂尔\u3000\u3000\u3000Lv.39",
        ]
        cases = [
            {"source": s, "mode": m, "expected": tr.translate(s, m)}
            for s in sources
            for m in ("annotation", "primary", "secondary")
        ]
        runner = "const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');const data=JSON.parse(fs.readFileSync(0,'utf8'));const r=new RuntimeText(data.model);for(const c of data.cases)require('assert').strictEqual(r.translate(c.source,c.mode),c.expected);console.log(data.cases.length);"
        result = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps({"model": tr.runtime_model(), "cases": cases}),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
