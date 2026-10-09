"""Reported raw-input shapes, typed role admission, and final renderer parity."""

import json
from pathlib import Path
import subprocess
import unittest

from sora_bilingual.localization.item_help_composition import compile_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator
from test_itemhelp_aggregates import fixture, texts


def rows():
    entries, metadata, groups = fixture()
    for key, values in [
        ("table/t_text.tbl/TXT_ITEM_HELP_FORMAT5", ("【", "[", "【")),
        ("table/t_text.tbl/TXT_ITEM_HELP_FORMAT6", ("】", "]", "】")),
        ("table/t_text.tbl/TXT_ITEM_HELP_RANGE_S", ("S", "(S)", "Ｓ")),
        (
            "table/t_itemhelp.tbl/SkillTextArrayData/physical/format",
            ("【物理攻击%s／", "[Physical%s - ", "【物理攻撃%s／"),
        ),
        (
            "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:2a2c762e0d6517c7db916fe291eb0c21a61dbb9804f6b0c338a115132e4962f9/label",
            ("地点·圆", "Target - Circle ", "地点･円"),
        ),
        (
            "table/t_itemhelp.tbl/SkillEffectHelpData/impede/name",
            ("解除驱动", "Impede", "駆動解除"),
        ),
        (
            "table/t_itemhelp.tbl/SkillEffectHelpData/back/name",
            ("背面特效", "Back Attack Bonus", "背面特効"),
        ),
        (
            "table/t_itemhelp.tbl/SkillEffectHelpData/cp/name",
            ("CP逐渐上升", "CP Regen", "CP徐々上昇"),
        ),
        (
            "table/t_itemhelp.tbl/SkillEffectHelpData/hp/name",
            ("逐渐回复HP", "HP Regen", "HP徐々回復"),
        ),
        (
            "table/t_skill.tbl/description/description",
            ("技能说明", "Official description", "技能説明"),
        ),
    ]:
        entries.append({"key": key, "texts": texts(values)})
    grammar = compile_item_help_grammar(entries, "en", metadata, groups)
    return entries + grammar["detail_entries"], metadata, groups


class R19EffectContractTests(unittest.TestCase):
    def test_whole_conflicts_and_native_integer_boundaries_survive_final_render(self):
        entries, _, _ = rows()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        header = "<C3></C>[Physical<I278> - <I295><C3>Target - Circle (S)</C>] "
        source = (
            header + "<c698>Impede</C><c698>, </C><c698>Blind 30%</C><c698>, Back Attack Bonus</C>"
        )
        tr.ambiguous_display.add(source)
        self.assertIsNone(tr.effect_detail_plan(source))
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(tr.render(source, mode)["text"], source)
        fresh = MenuTranslator(entries, "ja", "zh-Hans", "en")
        for value in ("-2147483648", "2147483647", "101"):
            self.assertIsNotNone(fresh.details.effect_units("Blind " + value + "%"))
        for value in ("-2147483649", "2147483648", "9" * 100):
            self.assertIsNone(fresh.details.effect_units("Blind " + value + "%"))
            original = source.replace("Blind 30%", "Blind " + value + "%")
            self.assertEqual(
                fresh.render(original), {"text": original, "layers": [], "kind": "plain"}
            )

    def test_single_probability_needs_the_native_type_and_connection_kind(self):
        entries, metadata, groups = fixture()
        proof = [{"kind": 7, "ids": [31, 34, 38, 39]}]
        grammar = compile_item_help_grammar(entries, "en", metadata, groups, connect_groups=proof)
        singles = [
            e
            for e in grammar["detail_entries"]
            if e["item_help_contract"]["family"] == "chance_single"
        ]
        self.assertEqual(
            {tuple(e["item_help_contract"]["record_ids"]) for e in singles},
            {(31,), (34,), (38,), (39,)},
        )
        tr = MenuTranslator(entries + singles, "ja", "zh-Hans", "en")
        self.assertEqual(tr.details.effect_units("Blind 30%")[0]["pair"], ("暗闇30％", "黑暗30％"))
        for connections in ([], [{"kind": 17, "ids": [31, 34, 38, 39]}]):
            refused = compile_item_help_grammar(
                entries, "en", metadata, groups, connect_groups=connections
            )
            self.assertFalse(
                any(
                    e["item_help_contract"]["family"] == "chance_single"
                    for e in refused["detail_entries"]
                )
            )
        changed = {k: dict(v) for k, v in metadata.items()}
        changed["SkillEffectHelpData"] = {
            k: dict(v) for k, v in metadata["SkillEffectHelpData"].items()
        }
        identity = next(k for k, v in changed["SkillEffectHelpData"].items() if v["id"] == 38)
        changed["SkillEffectHelpData"][identity]["parameter_types"] = (4,)
        refused = compile_item_help_grammar(entries, "en", changed, groups, connect_groups=proof)
        self.assertFalse(
            any(
                e["item_help_contract"].get("record_ids") == [38]
                and e["item_help_contract"]["family"] == "chance_single"
                for e in refused["detail_entries"]
            )
        )

    def test_complete_header_and_render_retain_unknown_and_conflict_refusals(self):
        entries, _, _ = rows()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        header = "<C3></C>[Physical<I278> - <I295><C3>Target - Circle (S)</C>] "
        tail = "<c698>Impede</C><c698>, </C><c698>Blind 30%</C><c698>, Back Attack Bonus</C>"
        plan = tr.render(header + tail)
        self.assertGreaterEqual(len([l for l in plan["layers"] if l.get("semantic_ids")]), 5)
        visible = plan["text"] + "".join(l["text"] for l in plan["layers"])
        for value in ("Physical", "Impede", "Blind", "Back Attack Bonus"):
            self.assertNotIn(value, visible)
        self.assertTrue(
            all("<I278>" not in l["text"] and "<I295>" not in l["text"] for l in plan["layers"])
        )
        self.assertIn("<I278>", plan["text"])
        self.assertIn("<I295>", plan["text"])
        partial = tr.effect_detail_plan(header + tail + ", UNKNOWN")
        self.assertIsNotNone(partial)
        self.assertIn("UNKNOWN", partial["text"])
        self.assertEqual(
            len(
                [
                    l
                    for l in partial["layers"]
                    if any("SkillEffectHelpData" in key for key in l.get("semantic_ids", []))
                ]
            ),
            3,
        )
        for suffix in ("<c698>Impede</C><K3>", "<R>Impede</Rbad>"):
            original = header + suffix
            self.assertIsNone(tr.effect_detail_plan(original))
            # A failed unit plan cannot suppress independently proven fields.
            # Unknown words/controls/readings must still survive the fallback.
            plan = tr.render(original)
            visible = plan["text"] + "".join(l["text"] for l in plan["layers"])
            unknown = (
                "UNKNOWN"
                if "UNKNOWN" in suffix
                else "<K3>"
                if "<K3>" in suffix
                else "<R>Impede</Rbad>"
            )
            self.assertIn(unknown, visible)
        self.assertIsNone(tr.skill_header(header.replace("<I278>", "unproved argument")))
        self.assertIsNone(tr.skill_header(header.replace("Target - Circle (S)", "UNKNOWN")))
        conflicting = entries + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/other/name",
                "texts": texts(("别的效果", "Blind %d%%", "別の効果%d％")),
            }
        ]
        self.assertIsNone(
            MenuTranslator(conflicting, "ja", "zh-Hans", "en").effect_detail_plan(header + tail)
        )
        self.assertIsNotNone(tr.effect_detail_plan(header.rstrip()))

    def test_resource_compiler_model_matches_shipped_js_for_final_modes(self):
        entries, _, _ = rows()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        header = "<C3></C>[Physical<I278> - <I295><C3>Target - Circle (S)</C>] "
        sources = [
            header + "<c698>Impede</C><c698>, </C><c698>Blind 30%</C><c698>, Back Attack Bonus</C>",
            header.rstrip(),
            header + "<c698>HP Regen</C>",
            header + "UNKNOWN",
            header + "HP Regen, UNKNOWN",
            "<c698>HP Regen</C><c698>, </C><c698>CP Regen</C>\n<C0>Official description",
        ]
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const i=JSON.parse(fs.readFileSync(0,'utf8')),tr=new RuntimeText(i.model);
process.stdout.write(JSON.stringify(i.sources.map(s=>['primary','secondary','annotation'].map(m=>tr.render(s,m)))));
"""
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            input=json.dumps({"model": tr.runtime_model(), "sources": sources}),
            capture_output=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(
            json.loads(result.stdout),
            [[tr.render(s, m) for m in ("primary", "secondary", "annotation")] for s in sources],
        )

    def test_verified_owner_can_resolve_a_global_whole_conflict(self):
        entries, _, _ = rows()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en")
        source = "<C3></C>[Physical<I278> - <I295><C3>Target - Circle (S)</C>] <c698>Blind 30%</C>"
        script = """
const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const i=JSON.parse(fs.readFileSync(0,'utf8')),unowned=new RuntimeText(i.model),
      pair=['primary','secondary'].map(m=>unowned.translate(i.source,m));
const model={...i.model,ambiguous_display:[...i.model.ambiguous_display,i.source],
  keyed:{...i.model.keyed,verified_owner:{source:i.source,model:{pairs:{[i.source]:pair}}}}};
const tr=new RuntimeText(model);
assert.equal(tr.ownerPair(i.source,'verified_owner').join(''),pair.join(''));
assert.equal(tr.render(i.source).text,i.source);
assert.equal(tr.render(i.source,'annotation','stale_owner').text,i.source);
assert.ok(tr.render(i.source,'annotation','verified_owner').layers.some(l=>l.semantic_ids?.length));
assert.equal(tr.translate(i.source,'primary','verified_owner'),pair[0]);
"""
        subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            input=json.dumps({"model": tr.runtime_model(), "source": source}),
            capture_output=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )


if __name__ == "__main__":
    unittest.main()
