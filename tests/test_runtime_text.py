import json
from pathlib import Path
import subprocess
import unittest
from sora_bilingual.localization.menu_text import (
    MenuTranslator,
    annotation_plan,
    reflow_annotation_lines,
)

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTextTests(unittest.TestCase):
    def test_dialogue_controls_reflow_secondary_lines_without_losing_line_ownership(self):
        primary = "<#E_0#M_0#B_0>那个眼神……\n难道是在期待能得到什么吗？"
        secondary = "<#E_0#M_0#B_0>その眼差し……\nもしかして何か貰えると\n期待しているのかしら？"
        translator = MenuTranslator(
            [{"texts": {"zh-Hans": primary, "ja": secondary}}], "zh-Hans", "ja"
        )

        plan = translator.render(primary)

        self.assertEqual(plan["kind"], "layered")
        self.assertEqual(plan["text"].replace("<R></R_>", ""), primary)
        self.assertEqual([layer["primary"] for layer in plan["layers"]], primary.split("\n"))
        self.assertEqual(len(plan["layers"]), 2)
        self.assertTrue(all(layer["text"] for layer in plan["layers"]))
        self.assertEqual(
            "".join(layer["text"] for layer in plan["layers"]),
            "その眼差し……もしかして何か貰えると期待しているのかしら？",
        )
        runner = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(data.model);assert.deepEqual(r.render(data.source),data.plan);"""
        result = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                {"model": translator.runtime_model(), "source": primary, "plan": plan}
            ),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reflow_keeps_native_ruby_atomic_and_reopens_secondary_style_context(self):
        primary = "<#E_0#M_0#B_0>甲甲\n乙乙"
        secondary = "<#E_0#M_0#B_0><C1><B><s27><R>一二</Rいちに>三\n四五</B></C>"
        translator = MenuTranslator(
            [{"texts": {"zh-Hans": primary, "ja": secondary}}], "zh-Hans", "ja"
        )

        plan = translator.render(primary)

        self.assertEqual(plan["text"].replace("<R></R_>", ""), primary)
        self.assertEqual(
            [layer["text"] for layer in plan["layers"]],
            [
                "<C1><B><s27><R>一二</Rいちに>三</B></C>",
                "<C1><B><s27>四五</B></C>",
            ],
        )
        self.assertTrue(all(layer["protected"] for layer in plan["layers"]))
        runner = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(data.model);assert.deepEqual(r.render(data.source),data.plan);"""
        result = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                {"model": translator.runtime_model(), "source": primary, "plan": plan}
            ),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reflow_rejects_unknown_or_incomplete_markup_without_replaying_events(self):
        primary = "甲甲\n乙乙"
        self.assertIsNone(reflow_annotation_lines(primary, "<#wait>一二\n三四"))
        self.assertIsNone(reflow_annotation_lines(primary, "<R>一二\n三四"))

        plan = annotation_plan(primary, "<#wait>一二\n三四")
        self.assertEqual([layer["text"] for layer in plan["layers"]], ["一二", "三四"])
        self.assertNotIn("<#wait>", "".join(layer["text"] for layer in plan["layers"]))

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

    def test_annotation_reflow_preserves_secondary_icon_once_and_keeps_pure_icon_plain(self):
        source = "甲甲\n乙乙\n丙丙"
        secondary = "<I1537>一二\n三四\n五六"
        icon = "<I1537>"
        tr = MenuTranslator(
            [
                {"texts": {"zh-Hans": source, "ja": secondary}},
                {"texts": {"zh-Hans": icon, "ja": icon}},
            ],
            "zh-Hans",
            "ja",
        )

        plan = tr.render(source)

        self.assertEqual(plan["kind"], "layered")
        self.assertEqual(plan["text"].replace("<R></R_>", ""), source)
        payload = "".join(layer["text"] for layer in plan["layers"])
        self.assertEqual(payload, secondary.replace("\n", ""))
        self.assertEqual(payload.count(icon), 1)
        self.assertEqual(tr.render(icon), {"text": icon, "layers": [], "kind": "plain"})

        code = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(0,'utf8')),r=new RuntimeText(data.model);
for(const c of data.cases)assert.deepEqual(r.render(c.source),c.plan);"""
        result = subprocess.run(
            ["node", "-e", code],
            input=json.dumps(
                {
                    "model": tr.runtime_model(),
                    "cases": [
                        {"source": source, "plan": plan},
                        {"source": icon, "plan": tr.render(icon)},
                    ],
                }
            ),
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mismatched_plain_book_lines_reflow_secondary_payloads_without_loss(self):
        fixtures = [
            (
                "luan",
                "【特辑】深入报道！　卢安市长选举\n\n◆从２位候选人　预见卢安往后将面对的课题◆\n卢安市民会选择将未来托付给何者。",
                "【特集】迫る！　ルーアンの市長選挙\n\n◆２名の候補者　垣間見えるルーアンの課題◆\nルーアン市長選挙。\n白熱する選挙戦の模様をお伝えする。",
            ),
            (
                "pact",
                "【外交】女王陛下倡导！　与３国之间的不战条约\n　外交部发表了签署不战条约的声明。\n希望能为３个国家之间的关系带来曙光。",
                "【外交】女王陛下が提唱！　３ヶ国間の不戦条約\n　外交部の発表によると、３ヶ国は不戦条約の締結に合意。\n早急に調印を行うべく調整に入った模様だ。\n関係に光明をもたらすことを切に願いたい。",
            ),
            ("paragraphs", "甲甲\n\n乙乙\n丙丙", "一一\n二二\n三三\n\n"),
            (
                "latin",
                "甲甲\n乙乙\n丙丙\n丁丁",
                "Supercalifragilisticexpialidocious longestword remains intact while this much longer English paragraph is distributed across each available primary line without a final-line pileup",
            ),
            ("unicode", "甲甲\n乙乙\n丙丙", "😀好\n，世\n界！\n结束"),
        ]
        entries = [
            {"texts": {"zh-Hans": primary, "ja": secondary}} for _, primary, secondary in fixtures
        ]
        entries.append({"texts": {"zh-Hans": "甲甲\n乙乙", "ja": "一一\n二二"}})
        entries.append({"texts": {"zh-Hans": "<C1>甲\n乙</C>", "ja": "<C1>一\n二\n三</C>"}})
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        cases = []
        for name, primary, secondary in fixtures:
            plan = tr.render(primary)
            payloads = [layer["text"] for layer in plan["layers"]]
            reflowed = reflow_annotation_lines(primary, secondary)
            expected = (
                secondary.replace("\n", " ") if name == "latin" else secondary.replace("\n", "")
            )
            self.assertEqual(plan["kind"], "layered", name)
            self.assertGreater(len(payloads), 1, name)
            self.assertEqual(plan["text"].replace("<R></R_>", ""), primary, name)
            self.assertIsNotNone(reflowed, name)
            self.assertEqual(payloads, [line for line in reflowed if line], name)
            self.assertEqual("".join(payloads), expected, name)
            self.assertTrue(
                all(
                    not payload.startswith(tuple("、。！？）】》〉」』〕］｝"))
                    for payload in payloads
                    if payload
                ),
                name,
            )
            if name == "latin":
                self.assertEqual(len(payloads), 4)
                self.assertLess(len(payloads[-1]), len(expected) // 2)
                self.assertTrue(
                    any("Supercalifragilisticexpialidocious" in payload for payload in payloads)
                )
            cases.append({"source": primary, "plan": plan})
        aligned = tr.render("甲甲\n乙乙")
        self.assertEqual(aligned["kind"], "ruby")
        self.assertFalse(aligned["layers"])
        markup = tr.render("<C1>甲\n乙</C>")
        self.assertEqual(markup["kind"], "layered")
        self.assertEqual(len(markup["layers"]), 2)
        self.assertEqual(
            [layer["text"] for layer in markup["layers"]], ["<C1>一二</C>", "<C1>三</C>"]
        )
        cases.extend(
            [
                {"source": "甲甲\n乙乙", "plan": aligned},
                {"source": "<C1>甲\n乙</C>", "plan": markup},
            ]
        )
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
