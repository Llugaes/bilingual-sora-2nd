import unittest
from sora_bilingual.localization.menu_text import MenuTranslator


def entry(sc, ja, en=None):
    return {"texts": {"zh-Hans": sc, "ja": ja, **({"en": en} if en else {})}}


class MenuTextTests(unittest.TestCase):
    def test_item_name_scope_resolves_only_unambiguous_inventory_records(self):
        item = {
            "key": "table/t_item.tbl/id/name",
            "texts": {"fr": "Carte", "en": "Map", "de": "Landkarte"},
        }
        menu = {
            "key": "table/t_text.tbl/TXT_MAP",
            "texts": {"fr": "Carte", "en": "World map", "de": "Weltkarte"},
        }
        tr = MenuTranslator([item, menu], "en", "de", "fr")
        self.assertEqual(tr.translate("Carte", "secondary"), "Carte")
        self.assertEqual(tr.scoped["item_name"].translate("Carte", "secondary"), "Landkarte")
        duplicate = {"key": "table/t_item.tbl/other/name", "texts": menu["texts"]}
        tr = MenuTranslator([item, menu, duplicate], "en", "de", "fr")
        self.assertEqual(tr.scoped["item_name"].translate("Carte", "secondary"), "Carte")

    def test_complete_display_records_survive_unpaired_script_fragments(self):
        for role in ("dialogue", "speaker"):
            authoritative = {
                "display_role": role,
                "texts": {"fr": "Source", "en": "Primary", "de": "Secondary"},
            }
            fragment = {"texts": {"fr": "Source", "en": "Primary"}}
            tr = MenuTranslator([authoritative, fragment], "en", "de", "fr")
            self.assertEqual(tr.translate("Source", "secondary"), "Secondary")
            conflict = {
                "display_role": role,
                "texts": {"fr": "Source", "en": "Other", "de": "Different"},
            }
            tr = MenuTranslator([authoritative, fragment, conflict], "en", "de", "fr")
            self.assertEqual(tr.translate("Source", "secondary"), "Source")
        # Missing fragments alone do not become an invented translation.
        self.assertEqual(MenuTranslator([fragment], "en", "de", "fr").translate("Source"), "Source")

    def test_incomplete_or_blank_locale_never_erases_source_or_invents_translation(self):
        for missing in (None, "", "   "):
            texts = {"fr": "Texte", "de": "Text"}
            if missing is not None:
                texts["es"] = missing
            tr = MenuTranslator([{"texts": texts}], "de", "es", "fr")
            for mode in ("primary", "secondary", "annotation", "bilingual"):
                self.assertEqual(tr.translate("Texte", mode), "Texte")

    def test_composed_description_keeps_icons_colour_and_values(self):
        tr = MenuTranslator(
            [
                entry("强化", "強化"),
                entry("单体", "単体"),
                entry("HP上限+%d", "最大HP+%d"),
                entry("说明。", "説明。"),
            ],
            "zh-Hans",
            "ja",
        )
        raw = "强化【<I299>单体：<c698>HP上限+20</C>】\n说明。"
        result = tr.translate(raw)
        self.assertEqual(
            result,
            "<R>强化</R強化>【<I299><R>单体</R単体>：<c698><R>HP上限+20</R最大HP+20></C>】\n<R>说明。</R説明。>",
        )
        self.assertEqual(
            tr.translate(raw, "secondary"), "強化【<I299>単体：<c698>最大HP+20</C>】\n説明。"
        )

    def test_no_partial_word_replacement_or_ambiguous_translation(self):
        tr = MenuTranslator(
            [entry("药", "薬"), entry("保存", "セーブ"), entry("保存", "セーブする")],
            "zh-Hans",
            "ja",
        )
        self.assertEqual(tr.translate("药草"), "药草")
        self.assertEqual(tr.translate("保存"), "保存")

    def test_text_key_resolves_duplicate_word_without_weakening_raw_match(self):
        entries = [
            {"key": "table/t_text.tbl/TXT_SAVE", **entry("保存", "セーブ")},
            {"key": "table/t_text.tbl/TXT_CHAPTER_RESULT_SAVE", **entry("保存", "セーブする")},
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        values = tr.dictionary("annotation")
        self.assertNotIn("保存", values)
        self.assertEqual(values["\x01TXT_SAVE\x00保存"], "<R>保存</Rセーブ>")
        self.assertEqual(values["\x01TXT_CHAPTER_RESULT_SAVE\x00保存"], "<R>保存</Rセーブする>")

    def test_language_pair_is_independent_of_game_source_language(self):
        tr = MenuTranslator([entry("回复药", "ティアの薬", "Tear Balm")], "en", "ja")
        self.assertEqual(tr.translate("回复药"), "<R>Tear Balm</Rティアの薬>")
        self.assertEqual(tr.translate("回复药", "primary"), "Tear Balm")
        self.assertEqual(tr.translate("回复药", "secondary"), "ティアの薬")

    def test_colour_is_not_nested_in_ruby_and_same_text_not_duplicated(self):
        tr = MenuTranslator([entry("<C9>单体", "<C9>単体"), entry("HP", "HP")], "zh-Hans", "ja")
        self.assertEqual(tr.translate("<C9>单体"), "<C9><R>单体</R単体>")
        self.assertEqual(tr.translate("HP"), "HP")

    def test_numeric_placeholder_contract_mismatch_is_not_translated(self):
        tr = MenuTranslator([entry("HP%d", "HP%d/%d")], "zh-Hans", "ja")
        self.assertEqual(tr.translate("HP20"), "HP20")

    def test_string_template_translates_known_name_and_keeps_unknown_value(self):
        tr = MenuTranslator(
            [entry("选择%s？", "%sを選択？"), entry("艾丝蒂尔", "エステル")], "zh-Hans", "ja"
        )
        self.assertEqual(tr.translate("选择艾丝蒂尔？", "secondary"), "エステルを選択？")
        self.assertEqual(tr.translate("选择自定姓名？", "secondary"), "自定姓名を選択？")

    def test_placeholder_kind_reordering_is_rejected_without_positions(self):
        tr = MenuTranslator([entry("物品%s：%d个", "%d個の%s")], "zh-Hans", "ja")
        self.assertEqual(tr.translate("物品药：2个"), "物品药：2个")

    def test_line_breaks_preserve_all_text_when_translations_wrap_differently(self):
        tr = MenuTranslator([entry("甲\n乙", "一二")], "zh-Hans", "ja")
        plan = tr.render("甲\n乙")
        self.assertEqual(plan["text"].replace("<R></R_>", ""), "甲\n乙")
        self.assertEqual([layer["text"] for layer in plan["layers"]], ["一", "二"])

    def test_exact_description_suffix_disambiguates_item_effect_header(self):
        entries = [
            {"key": "table/t_itemhelp.tbl/type/label", **entry("强化", "強化")},
            {"key": "table/t_text.tbl/TXT_SHOP_CUSTOMIZE_YES", **entry("强化", "強化する")},
            {"key": "table/t_item.tbl/item/description", **entry("这是药。", "これは薬。")},
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        self.assertEqual(tr.translate("强化"), "强化")
        self.assertEqual(
            tr.translate("强化\n这是药。"), "<R>强化</R強化>\n<R>这是药。</Rこれは薬。>"
        )


if __name__ == "__main__":
    unittest.main()
