"""Compact headers and preserved unknown/foreign-role neighbours in final plans."""

import json
from pathlib import Path
import re
import subprocess
import unittest

from sora_bilingual.localization.menu_text import EFFECT_REFUSAL_POLICY, MenuTranslator
from test_r19_effect_contract import rows
from test_itemhelp_aggregates import texts


class R21ReportedBoundaries(unittest.TestCase):
    def test_admitted_role_fenced_from_unproved_parameter_precedes_opaque(self):
        entries, _, _ = rows()
        delay = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/delay/stat",
            "texts": texts(("延迟", "Delay", "遅延")),
        }
        entries.append(delay)
        entries.append(
            {
                "key": "table/t_place.tbl/global_name/name",
                "texts": texts(("埃尔赛尤", "Arseille", "アルセイユ")),
            }
        )
        source = "[Physical] <c698>HP Regen</C><c698>, </C><c698>Delay <c698>(M)</C></C>, Arseille"
        invalid = "[Physical] <c698>Blind 2147483648% <c698>(M)</C></C>"
        unsupported = source + ", <X999>Arseille</X>"
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        for mode in ("primary", "secondary", "annotation"):
            plan = tr.render(source, mode)
            self.assertNotIn("Delay", plan["text"])
            self.assertIn("(M)", plan["text"])
            self.assertIn("Arseille", plan["text"])
            self.assertNotIn("HP Regen", plan["text"])
            for rejected in (invalid, unsupported):
                self.assertEqual(
                    tr.render(rejected, mode), {"text": rejected, "layers": [], "kind": "plain"}
                )
        conflict = MenuTranslator(
            entries + [{**delay, "texts": texts(("另一个延迟", "Delay", "別の遅延"))}],
            "ja",
            "zh-Hans",
            "en",
        )
        self.assertEqual(conflict.render(source), {"text": source, "layers": [], "kind": "plain"})
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const i=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(i.sources.map(s=>['primary','secondary','annotation'].map(m=>new RuntimeText(i.model).render(s,m)))));
"""
        sources = [source, invalid, unsupported]
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            check=True,
            input=json.dumps({"model": tr.runtime_model(), "sources": sources}),
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(
            json.loads(result.stdout),
            [[tr.render(s, m) for m in ("primary", "secondary", "annotation")] for s in sources],
        )

    def test_refusal_enumeration_and_final_entry_orders(self):
        root = Path(__file__).resolve().parents[1]
        python = (root / "sora_bilingual/localization/menu_text.py").read_text("utf-8")
        javascript = (root / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf-8")
        expressions = re.findall(r"\brefuse\(([^)\n]*)\)", python + javascript)
        declared = {
            reason
            for expression in expressions
            for reason in re.findall(r"['\"]([a-z_]+)['\"]", expression)
        }
        declared |= set(re.findall(r'effect_unit_failures\[source\] = "([a-z_]+)"', python))
        declared |= set(re.findall(r"effectUnitFailures\.set\(source,'([a-z_]+)'", javascript))
        self.assertEqual(
            declared,
            set(EFFECT_REFUSAL_POLICY),
            "Every emitted refusal must have an explicit policy",
        )
        entries, _, _ = rows()
        entries.append(
            {
                "key": "table/t_itemhelp.tbl/SkillTextArrayData/support/format",
                "texts": texts(("【辅助／", "[Support - ", "【補助／")),
            }
        )
        sources = [
            "[Support] HP Regen, <X999>Arseille</X>",
            "[Support] HP Regen, <R>Arseille</Rforeign>",
            "[Support] HP Regen, , CP Regen",
            "[Support] " + ", ".join(["HP Regen"] * 33),
            "[Support] HP Regen" + "<C1>" * 17 + ", " + "</C>" * 17 + "CP Regen",
        ]
        for source in sources:
            for order in (
                ("primary", "secondary", "annotation"),
                ("annotation", "secondary", "primary"),
            ):
                tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
                for mode in order:
                    self.assertEqual(
                        tr.render(source, mode), {"text": source, "layers": [], "kind": "plain"}
                    )
                    self.assertEqual(tr.translate(source, mode), source)
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const i=JSON.parse(fs.readFileSync(0,'utf8'));
const plans=i.sources.map(s=>[['primary','secondary','annotation'],['annotation','secondary','primary']].map(order=>{
 const tr=new RuntimeText(i.model);return order.map(m=>[tr.render(s,m),tr.translate(s,m)]);
}));
process.stdout.write(JSON.stringify({policy:RuntimeText.effectRefusalPolicy,plans}));
"""
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            check=True,
            input=json.dumps({"model": tr.runtime_model(), "sources": sources}),
            capture_output=True,
            cwd=root,
        )
        decoded = json.loads(result.stdout)
        self.assertEqual(decoded["policy"], EFFECT_REFUSAL_POLICY)
        expected = [
            [[[{"text": s, "layers": [], "kind": "plain"}, s] for _ in range(3)] for _ in range(2)]
            for s in sources
        ]
        self.assertEqual(decoded["plans"], expected)

    def test_compact_headers_unknown_neighbours_and_facility_domain_match_js(self):
        entries, _, _ = rows()
        entries += [
            {
                "key": "table/t_itemhelp.tbl/SkillTextArrayData/enhance/format",
                "texts": texts(("【强化／", "[Enhance - ", "【強化／")),
            },
            {
                "key": "table/t_name.tbl/foreign/name",
                "texts": texts(("埃尔赛尤", "Arseille", "アルセイユ")),
            },
            {
                "key": "table/t_place.tbl/foreign/name",
                "texts": texts(("埃尔赛尤号・工房", "Arseille - Factory", "アルセイユ号・工房")),
            },
            {
                "key": "script/scena/mp8300_01.dat/TK_npc_setting_PAYTON/called/0/arg/2",
                "texts": texts(("埃尔赛尤号·工房", "Arseille - Factory", "アルセイユ号・工房")),
            },
            {
                "key": "script/scena/mp8300_01.dat/TK_npc_setting_PAYTON/called/0/arg/2/generated/npc_facility",
                "texts": texts(
                    (
                        "<c990>埃尔赛尤号·工房</c>",
                        "<c990>Arseille - Factory</c>",
                        "<c990>アルセイユ号・工房</c>",
                    )
                ),
                "npc_facility_contract": {"callee": "chr_set_shop_function", "argument": 2},
            },
        ]
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        sources = [
            "[Physical]",
            "<C3></C>[Enhance] <c698>HP Regen</C>, Arseille",
            "[Enhance] HP Regen, CP Regen, UNKNOWN",
            "<c990>Arseille - Factory</c>",
            "[PhysicalXYZ] HP Regen",
            "<c990>Factory</c>",
            "<c990>Arseille - Factory Annex</c>",
        ]
        plans = [tr.render(source) for source in sources]
        self.assertNotIn("Physical", plans[0]["text"])
        self.assertEqual(len([l for l in plans[2]["layers"] if l.get("semantic_ids")]), 3)
        self.assertIn("UNKNOWN", plans[2]["text"])
        self.assertIn("Arseille", plans[1]["text"])
        self.assertNotIn("HP Regen", plans[1]["text"])
        self.assertNotIn("Factory", plans[3]["text"])
        self.assertEqual(tr.npc_facilities.get(sources[6]), None)
        self.assertEqual(tr.npc_facilities.get(sources[5]), None)
        for suffix in ("Blind 2147483648%", "DEF↑ (2147483648 turns)"):
            original = "[Physical] " + suffix
            self.assertEqual(tr.render(original), {"text": original, "layers": [], "kind": "plain"})
        # A direct full-source conflict remains stronger than a constructor.
        tr.ambiguous_display.add(sources[3])
        self.assertEqual(tr.render(sources[3]), {"text": sources[3], "layers": [], "kind": "plain"})
        tr.ambiguous_display.remove(sources[3])
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const i=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(i.sources.map(s=>['primary','secondary','annotation'].map(m=>new RuntimeText(i.model).render(s,m)))));
"""
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            check=True,
            input=json.dumps({"model": tr.runtime_model(), "sources": sources}),
            capture_output=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(
            json.loads(result.stdout),
            [[tr.render(s, m) for m in ("primary", "secondary", "annotation")] for s in sources],
        )


if __name__ == "__main__":
    unittest.main()
