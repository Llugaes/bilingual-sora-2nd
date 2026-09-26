import unittest

from sora_bilingual.localization.menu_text import MenuTranslator, item_help_components

RANGE = "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:6a15f570d7d4b310463cc8eb627186cd7e4586d9ab2b87e663ebb1e538c2d090/label"
RECOVERY = "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:cc311d9666993ad7471edb97a4292bd44de5cac259718aab39db45a6008a99a8/name"


def row(key, zh, en, ja):
    return {"key": key, "texts": {"zh-Hans": zh, "en": en, "ja": ja}}


def entries():
    return [
        row(
            RANGE,
            "我方·圆",
            "Ally - Circle ",
            "味方･円",
        ),
        row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_L", "L", "(L)", "Ｌ"),
        row(RECOVERY, "回复HP%s", "Heal %s HP", "HP%s回復"),
        row("table/t_text.tbl/TXT_ITEM_HELP_SMALL", "小", "(S)", "小"),
        # The real global model contains both this generic template and the
        # HP-specific template. Exact generated instances must win over both.
        row(
            "table/t_itemhelp.tbl/SkillEffectHelpData/other/name", "回复%s", "Restore %s", "%s回復"
        ),
        row("table/t_skill.tbl/skill/description", "<C9>说明。", "<C9>Description.", "<C9>説明。"),
    ]


class ItemHelpCompositionTests(unittest.TestCase):
    def test_adjacent_range_and_formatted_effect_use_each_target_locale(self):
        tr = MenuTranslator(entries(), "en", "ja", "zh-Hans")
        source = "<I299><C3>我方·圆L</C><c698>回复HP小</C>\n<C0><C9>说明。"
        self.assertEqual(
            tr.translate(source, "primary"),
            "<I299><C3>Ally - Circle (L)</C><c698>Heal (S) HP</C>\n<C0><C9>Description.",
        )
        self.assertEqual(
            tr.translate(source, "secondary"),
            "<I299><C3>味方･円Ｌ</C><c698>HP小回復</C>\n<C0><C9>説明。",
        )

    def test_generated_components_do_not_split_unknown_adjacent_text(self):
        tr = MenuTranslator(entries(), "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("我方·圆自定义", "primary"), "我方·圆自定义")
        self.assertEqual(tr.translate("自定义我方·圆L", "primary"), "自定义我方·圆L")

    def test_missing_or_conflicting_range_locale_remains_untranslated(self):
        values = entries()
        del values[1]["texts"]["ja"]
        self.assertEqual(MenuTranslator(values, "en", "ja").translate("我方·圆L"), "我方·圆L")
        values = entries()
        # A conflicting native source from another record is not displaced by
        # the resource-defined combination.
        values.append(row("table/t_itemhelp.tbl/other/name", "我方·圆L", "Conflict", "別Ｌ"))
        self.assertEqual(MenuTranslator(values, "en", "ja").translate("我方·圆L"), "我方·圆L")

    def test_unverified_range_kinds_are_not_guessed_from_text(self):
        values = entries()
        values[0] = {**values[0], "key": "table/t_itemhelp.tbl/SkillRangeHelpData/unknown/label"}
        values.append(
            row(
                "table/t_itemhelp.tbl/SkillRangeHelpData/unknown/short_label", "全体", "All", "全体"
            )
        )
        tr = MenuTranslator(values, "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("我方·圆L", "primary"), "我方·圆L")
        self.assertEqual(tr.translate("全体L", "primary"), "全体L")

    def test_attribute_and_numeric_slots_do_not_create_grade_pairs(self):
        values = [
            row("table/t_text.tbl/TXT_ITEM_HELP_SMALL", "小", "(S)", "小"),
            row("table/t_text.tbl/TXT_ITEM_HELP_RANGE_L", "L", "(L)", "Ｌ"),
            row(RECOVERY.removesuffix("/name") + "/format", "回复%s", "Recover %s ", "%s回復"),
            row(
                "table/t_itemhelp.tbl/SkillEffectHelpData/attribute/name",
                "%s属性追击",
                "%s Arts Attribute Attack",
                "%s属性追撃",
            ),
            row("table/t_itemhelp.tbl/SkillEffectHelpData/stat/format", "%s", "%s", "%s"),
            row(
                "table/t_itemhelp.tbl/SkillRangeHelpData/all/short_label",
                "全体（非战斗时）",
                "All (outside combat)",
                "全体（非戦闘時）",
            ),
        ]
        self.assertEqual(item_help_components(values), [])


if __name__ == "__main__":
    unittest.main()
