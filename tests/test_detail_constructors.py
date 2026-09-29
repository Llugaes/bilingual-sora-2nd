import unittest

from tests.test_itemhelp_aggregates import fixture, texts
from sora_bilingual.localization.item_help_composition import compile_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator
from tests.check_status_omissions import _typed_bare_actual_cases


class DetailConstructorTests(unittest.TestCase):
    def test_audit_does_not_reuse_status_id_as_effect_id(self):
        grammar = {
            "detail_entries": [
                {
                    "key": "status",
                    "texts": texts(("命中率+%d", "ACC+%d", "命中率+%d")),
                    "item_help_contract": {
                        "family": "status_value",
                        "record_ids": [13],
                        "resource_kind": "SkillItemStatusData",
                    },
                }
            ]
        }
        contexts = [{"group": [[13, 7, 0, 0]], "path": "table/t_skill.tbl", "row_index": 0}]
        cases, gaps = _typed_bare_actual_cases(grammar, contexts, "zh-Hans", "en", "ja")
        self.assertEqual((cases, gaps), ([], []))

    def test_audit_reads_duration_not_activation_chance(self):
        grammar = {
            "detail_entries": [
                {
                    "key": "critical",
                    "texts": texts(("危机时%d回合STR↑", "STR↑ for %d turns", "%dターンSTR↑")),
                    "item_help_contract": {
                        "family": "critical_turn_group",
                        "record_ids": [1059],
                        "turn_argument": "slot2",
                    },
                }
            ]
        }
        contexts = [{"group": [[1059, 100, 4, 0]], "path": "table/t_item.tbl", "row_index": 0}]
        cases, gaps = _typed_bare_actual_cases(grammar, contexts, "zh-Hans", "en", "ja")
        self.assertFalse(gaps)
        self.assertEqual(cases[0]["source"], "危机时4回合STR↑")

    def test_target_ascii_width_is_not_a_competing_translation(self):
        entries = [
            {"texts": {"zh-Hans": "HP吸收", "ja": "ＨＰ吸収", "en": "HP Absorb"}},
            {"texts": {"zh-Hans": "HP吸收", "ja": "HP吸収", "en": "HP Absorb"}},
        ]
        tr = MenuTranslator(entries, "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("HP吸收", "secondary"), "HP吸収")
        entries.append({"texts": {"zh-Hans": "HP吸收", "ja": "HP回復", "en": "Restore HP"}})
        self.assertEqual(
            MenuTranslator(entries, "en", "ja", "zh-Hans").translate("HP吸收", "secondary"),
            "HP吸收",
        )

    def test_single_absorb_uses_stat_and_format_inside_full_description(self):
        entries, metadata, groups = fixture()
        description = {
            "key": "table/t_skill.tbl/test/description",
            "texts": texts(("技能说明", "Skill description", "技の説明")),
        }
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        tr = MenuTranslator(
            entries + grammar["detail_entries"] + [description], "zh-Hans", "en", "zh-Hans"
        )
        source = "<c698>HP吸收</C>\n<C0>技能说明"
        self.assertIn("HP Absorb", tr.translate(source, "secondary"))

    def test_status_name_value_constructor_keeps_percentage(self):
        entries, metadata, groups = fixture()
        identity = next(iter(metadata["SkillItemStatusData"]))
        base = "table/t_itemhelp.tbl/SkillItemStatusData/" + identity
        entries += [
            {"key": base + "/name", "texts": texts(("命中率", "ACC", "命中率"))},
            {"key": base + "/value", "texts": texts(("+%d％", "+%d%%", "+%d％"))},
        ]
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        tr = MenuTranslator(entries + grammar["detail_entries"], "zh-Hans", "en", "zh-Hans")
        self.assertEqual(tr.translate("命中率+75％", "secondary"), "ACC+75%")
        self.assertEqual(tr.translate("命中率+75%", "secondary"), "ACC+75%")

    def test_critical_turn_arguments_reorder_without_translating_stat_fragments(self):
        entries, metadata, groups = fixture()
        for record_id, stat in [(1059, "STR"), (1063, "SPD"), (1088, "MOV")]:
            identity = f"test-critical-{record_id}"
            metadata["SkillEffectHelpData"][identity] = {"id": record_id, "parameter_types": (9,)}
            base = "table/t_itemhelp.tbl/SkillEffectHelpData/" + identity
            for field, value in {
                "name": texts(
                    (
                        f"危机时{stat}上升·%s",
                        f"{stat} UP%s when critical health",
                        f"ピンチ時に{stat}アップ・%s",
                    )
                ),
                "stat": texts(
                    (
                        "危机时%d回合%s%s",
                        "%s%s when critical health (%d turns)",
                        "ピンチ時に%dターン%s%s",
                    )
                ),
                "format": texts((stat, stat, stat)),
            }.items():
                entries.append({"key": base + "/" + field, "texts": value})
        groups += [((1059, 100, 4, 0),), ((1063, 100, 4, 0), (1088, 100, 4, 0))]
        grammar = compile_item_help_grammar(
            entries,
            "zh-Hans",
            metadata,
            groups,
            connect_groups=[{"kind": 2, "ids": [1059, 1063, 1088]}],
        )
        tr = MenuTranslator(entries + grammar["detail_entries"], "zh-Hans", "en", "zh-Hans")
        for source, target in [
            ("危机时4回合STR↑", "STR↑ when critical health (4 turns)"),
            ("危机时4回合SPD･MOV↑", "SPD/MOV↑ when critical health (4 turns)"),
        ]:
            self.assertEqual(tr.translate(source, "secondary"), target)


if __name__ == "__main__":
    unittest.main()
