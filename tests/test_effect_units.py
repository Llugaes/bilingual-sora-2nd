"""Independent formatter-role and annotation-granularity boundaries."""

import unittest
import json
from pathlib import Path
import subprocess

from sora_bilingual.localization.menu_text import MenuTranslator


def entries():
    return [
        {
            "key": "table/t_skill.tbl/example/description",
            "texts": {"en": "Official description", "ja": "説明", "zh-Hans": "说明"},
        },
        {
            "key": "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8",
            "texts": {"en": ", ", "ja": "／", "zh-Hans": "／"},
        },
        {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/hp/name",
            "texts": {"en": "HP Regen", "ja": "HP徐々回復", "zh-Hans": "逐渐回复HP"},
        },
        {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/hp/turns",
            "texts": {"en": "HP Regen", "ja": "行動後HP回復", "zh-Hans": "行动后回复HP"},
        },
        {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/cp/name",
            "texts": {"en": "CP Regen", "ja": "CP徐々上昇", "zh-Hans": "CP逐渐上升"},
        },
        {
            "key": "table/t_text.tbl/TXT_ITEM_HELP_DEBUFF_CANCEL",
            "texts": {"en": "Remove Debuff", "ja": "デバフ解除", "zh-Hans": "解除减益"},
        },
    ]


class EffectUnitTests(unittest.TestCase):
    def test_bound_role_precedes_unowned_complete_fragment_but_not_global_use(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en").details
        # A constructor-wide template can decorate a globally used term;
        # the independently bound description role keeps its own unit target.
        tr.pairs["CP Regen"] = ("<C2>Other constructor</C>", "<C2>其他构造器</C>")
        for mode, expected in (("primary", "CP徐々上昇"), ("secondary", "CP逐渐上升")):
            self.assertEqual(
                tr.translate("CP Regen", mode), tr.pairs["CP Regen"][mode == "secondary"]
            )
            self.assertEqual(
                tr.translate("CP Regen", mode, detail_context="Official description"), expected
            )

    def test_partition_authority_matches_resident_and_refusal_survives_fallback(self):
        rows = [
            {
                "key": "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8",
                "texts": {"en": ", ", "ja": "、", "zh-Hans": "，"},
            }
        ]
        for ident, source, left, right in [
            ("a", "A", "JA", "ZA"),
            ("b", "B", "JB", "ZB"),
            ("c", "C", "JC", "ZC"),
            ("ab", "A, B", "JAB", "ZAB"),
        ]:
            rows.append(
                {
                    "key": f"table/t_itemhelp.tbl/SkillEffectHelpData/{ident}/name",
                    "texts": {"en": source, "ja": left, "zh-Hans": right},
                }
            )
        tr = MenuTranslator(rows, "ja", "zh-Hans", "en").details
        for mode in ("primary", "secondary", "annotation"):
            for context in (None, "", "Known description"):
                self.assertIsNone(tr.effect_units("A, B, C"))
                self.assertEqual(tr.effect_unit_failures["A, B, C"], "different_partition_targets")
                self.assertEqual(tr.translate("A, B, C", mode, detail_context=context), "A, B, C")
        self.assertEqual(tr.render("A, B, C")["text"], "A, B, C")
        rows[-1]["texts"].update({"ja": "JA、JB", "zh-Hans": "ZA，ZB"})
        equivalent = MenuTranslator(rows, "ja", "zh-Hans", "en").details
        self.assertEqual(
            len([u for u in equivalent.effect_units("A, B, C") if u.get("semantic_ids")]), 3
        )
        self.assertEqual(
            equivalent.translate("A, B, C", "primary", detail_context="known"), "JA、JB、JC"
        )

    def test_partial_effects_preserve_rejection_and_non_effect_header_fallback(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en").details
        source = "CP Regen, Unknown"
        self.assertEqual(
            tr.translate(source, "primary", detail_context="Official description"), source
        )
        self.assertEqual(tr.effect_unit_failures[source], "partial_effect_members")
        self.assertEqual(
            tr.translate("Official description", "primary", detail_context="known"), "説明"
        )

    def test_display_fragments_and_unbound_parameters_are_not_effect_roles(self):
        fragment = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/dynamic/name/fragment/prefix",
            "texts": {"en": "CP Regen", "ja": "別の引数の前半", "zh-Hans": "另一参数的前半"},
        }
        tr = MenuTranslator(entries() + [fragment], "ja", "zh-Hans", "en")
        self.assertEqual(
            tr.details.effect_units("CP Regen")[0]["pair"], ("CP徐々上昇", "CP逐渐上升")
        )
        other = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/unbound/name",
            "texts": {"en": "%d custom", "ja": "%d未確認", "zh-Hans": "%d未知"},
        }
        tr = MenuTranslator(entries() + [other], "ja", "zh-Hans", "en")
        self.assertIsNone(tr.details.effect_units("5 custom"))
        rejection = next(
            r for r in tr.details.detail_effect_rejections if r["source"] == "%d custom"
        )
        self.assertEqual(rejection["reason"], "unproven_parameter_contract")

    def test_resource_owned_whitespace_is_not_external_padding(self):
        rows = entries() + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/spaced/stat",
                "texts": {"en": "Resist ", "ja": "耐性", "zh-Hans": "抗性 "},
            }
        ]
        tr = MenuTranslator(rows, "ja", "zh-Hans", "en")
        self.assertEqual(tr.details.effect_units("Resist ")[0]["pair"], ("耐性", "抗性 "))
        self.assertEqual(
            tr.details.effect_units("<c698>Resist </C>")[0]["pair"],
            ("<c698>耐性</C>", "<c698>抗性 </C>"),
        )
        self.assertEqual(tr.details.effect_units("  Resist ")[0]["pair"], ("  耐性", "  抗性 "))
        self.assertEqual(
            tr.details.effect_units("CP Regen ")[0]["pair"], ("CP徐々上昇 ", "CP逐渐上升 ")
        )

    def test_role_local_identity_ignores_unrelated_homograph_but_not_role_collision(self):
        rows = entries() + [
            {
                "key": "table/t_item.tbl/unrelated/name",
                "texts": {"en": "CP Regen", "ja": "別のアイテム", "zh-Hans": "另一物品"},
            }
        ]
        tr = MenuTranslator(rows, "ja", "zh-Hans", "en")
        self.assertEqual(tr.translate("CP Regen", "primary"), "CP Regen")
        unit = tr.details.effect_units("CP Regen")[0]
        self.assertEqual(unit["pair"], ("CP徐々上昇", "CP逐渐上升"))
        self.assertTrue(all("SkillEffectHelpData" in key for key in unit["semantic_ids"]))
        for texts in (
            {"en": "CP Regen", "ja": "違う効果", "zh-Hans": "不同效果"},
            {"en": "CP Regen", "ja": "CP徐々上昇"},
        ):
            conflicting = rows + [
                {"key": "table/t_itemhelp.tbl/SkillEffectHelpData/other/name", "texts": texts}
            ]
            denied = MenuTranslator(conflicting, "ja", "zh-Hans", "en")
            self.assertIsNone(denied.details.effect_units("CP Regen"))
            rejection = next(
                row
                for row in denied.details.detail_effect_rejections
                if row["source"] == "CP Regen"
            )
            self.assertEqual(rejection["reason"], "missing_or_ambiguous_effect_role")
            self.assertIn("table/t_itemhelp.tbl/SkillEffectHelpData/other/name", rejection["ids"])

    def test_unchanged_latin_effect_with_ruby_body_has_ruby_plan(self):
        rows = entries() + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/plain/name",
                "texts": {"en": "ATS", "ja": "ATS", "zh-Hans": "ATS"},
            }
        ]
        tr = MenuTranslator(rows, "en", "ja", "en")
        plan = tr.render("ATS\nOfficial description")
        self.assertEqual(plan["layers"], [])
        self.assertEqual(plan["kind"], "ruby")
        self.assertIn("<R>Official description</R説明>", plan["text"])

    def test_lowercase_close_does_not_leak_colour_into_next_semantic_unit(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en")
        plan = tr.render("<c698>HP Regen</c>, CP Regen\nOfficial description")
        effects = [layer for layer in plan["layers"] if layer.get("semantic_ids")]
        self.assertEqual(len(effects), 2)
        self.assertNotIn("<c698>", effects[1]["text"])

    def test_shipped_js_preserves_the_same_semantic_contract(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en")
        sources = [
            "<c698>HP Regen</C>, CP Regen, Remove Debuff\nOfficial description",
            "<c698>HP Regen, CP Regen</C>\r\nRemove Debuff\nOfficial description",
            "HP Regen, UNKNOWN\nOfficial description",
            "<c698>HP Regen</c>, CP Regen\nOfficial description",
        ]
        script = """
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),tr=new RuntimeText(input.model);
process.stdout.write(JSON.stringify(input.sources.map(source=>({
primary:tr.translate(source,'primary'),secondary:tr.translate(source,'secondary'),plan:tr.render(source)}))));
"""
        result = subprocess.run(
            ["node", "-e", script],
            input=json.dumps({"model": tr.runtime_model(), "sources": sources}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(
            json.loads(result.stdout),
            [
                {
                    "primary": tr.translate(s, "primary"),
                    "secondary": tr.translate(s, "secondary"),
                    "plan": tr.render(s),
                }
                for s in sources
            ],
        )

    def test_style_isolated_role_and_independent_annotations(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en")
        source = "<c698>HP Regen</C>, CP Regen, Remove Debuff\nOfficial description"
        self.assertEqual(
            tr.translate(source, "primary"), "<c698>HP徐々回復</C>／CP徐々上昇／デバフ解除\n説明"
        )
        plan = tr.render(source)
        effects = [layer for layer in plan["layers"] if layer.get("semantic_ids")]
        self.assertEqual(len(effects), 3)
        self.assertEqual(
            [layer["primary"] for layer in effects],
            ["<c698>HP徐々回復</C>", "CP徐々上昇", "デバフ解除"],
        )
        self.assertTrue(all("／" not in layer["text"] for layer in effects))
        self.assertEqual(tr.translate("HP Regen", "primary"), "HP Regen")

    def test_unknown_member_and_native_ruby_do_not_gain_role_authority(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en")
        source = "HP Regen, UNKNOWN"
        self.assertIsNone(tr.details.effect_units(source))
        self.assertFalse(
            any(
                layer.get("semantic_ids")
                for layer in tr.render(source + "\nOfficial description")["layers"]
            )
        )
        # A protected native reading has no effect role. Its independently
        # compiled neighbour keeps its own role at the admitted body boundary.
        native = "<R>HP Regen</R[reading]>"
        source = native + ", CP Regen"
        self.assertIsNone(tr.details.effect_units(source))
        plan = tr.render(source + "\nOfficial description")
        self.assertTrue(plan["text"].startswith(native), plan)
        roles = [layer for layer in plan["layers"] if layer.get("semantic_ids")]
        self.assertEqual(len(roles), 1, plan)
        self.assertEqual(
            roles[0]["semantic_ids"], ["table/t_itemhelp.tbl/SkillEffectHelpData/cp/name"]
        )

    def test_unit_boundaries_keep_real_newlines(self):
        tr = MenuTranslator(entries(), "ja", "zh-Hans", "en")
        source = "HP Regen, CP Regen\r\nRemove Debuff\nOfficial description"
        plan = tr.render(source)
        self.assertIn("\r\n", plan["text"])
        self.assertEqual(len([l for l in plan["layers"] if l.get("semantic_ids")]), 3)

    def test_colour_state_and_different_locale_separators_are_not_ruby_units(self):
        tr = MenuTranslator(entries(), "ja", "en", "en")
        source = "<c698>HP Regen, CP Regen, Remove Debuff</C>\nOfficial description"
        plan = tr.render(source)
        effects = [layer for layer in plan["layers"] if layer.get("semantic_ids")]
        self.assertEqual(len(effects), 3)
        self.assertEqual(
            [l["text"] for l in effects],
            ["<c698>HP Regen</C>", "<c698>CP Regen</C>", "<c698>Remove Debuff</C>"],
        )
        self.assertFalse(any(l["text"] == ", " for l in plan["layers"]))


if __name__ == "__main__":
    unittest.main()
