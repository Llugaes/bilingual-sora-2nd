import unittest
from sora_bilingual.localization.menu_text import MenuTranslator


def entry(sc, ja, en=None):
    return {"texts": {"zh-Hans": sc, "ja": ja, **({"en": en} if en else {})}}


class MenuTextTests(unittest.TestCase):
    def test_complete_pair_renders_when_only_source_has_controls(self):
        for source, primary, secondary in (
            ("<R>言葉</Rことば>", "话语", "Words"),
            ("Source<w1800>\nsecond line", "第一行\n第二行", "First line\nsecond line"),
            ("1,100...1,000...900...", "１１００、１０００、９００……", "1,100...1,000...900..."),
        ):
            tr = MenuTranslator(
                [entry(primary, secondary, source)], "zh-Hans", "ja", source_language="en"
            )
            plan = tr.render(source)
            self.assertEqual(plan["kind"], "ruby", source)
            for line in secondary.split("\n"):
                self.assertIn("</R" + line + ">", plan["text"])

    def test_native_reading_difference_is_visible_even_with_same_latin_base(self):
        source = "<R>Ｆｌａｍｍｅ！</R火焰啊！>"
        for target in ("<R>Ｆｌａｍｍｅ！</R炎よ！>", "<R>Flamme!"):
            plan = MenuTranslator([entry(source, target)], "zh-Hans", "ja").render(source)
            self.assertEqual(plan["kind"], "layered")
            self.assertEqual(len(plan["layers"]), 1)
            self.assertEqual(plan["layers"][0]["text"], target)
            self.assertTrue(plan["text"].endswith(source))

    def test_complete_numeric_wording_precedes_freeform_constructor(self):
        records = [
            entry("危机时%d回合“心眼”", "ピンチ時に%dターン「心眼」", "Foresight (%d turns)"),
            entry("危机时%d回合%s%s", "ピンチ時に%dターン%s%s", "Critical %d turns %s%s"),
            entry("2", "２", "Two"),
        ]
        for primary in ("zh-Hans", "en"):
            tr = MenuTranslator(records, primary, "ja")
            self.assertEqual(
                tr.translate("危机时2回合“心眼”", "secondary"), "ピンチ時に2ターン「心眼」"
            )
            self.assertNotEqual(tr.render("危机时2回合“心眼”")["kind"], "plain")
        # Two equally concrete resources remain ambiguous, irrespective of order.
        records.append(entry("危机时%u回合“心眼”", "別の効果%u", "Other effect %u"))
        self.assertEqual(
            MenuTranslator(records, "zh-Hans", "ja").translate("危机时2回合“心眼”", "secondary"),
            "危机时2回合“心眼”",
        )

    def test_only_string_arguments_use_name_translation(self):
        tr = MenuTranslator(
            [
                entry("2", "２", "Two"),
                entry("药", "薬", "Potion"),
                entry("<C1>%s</C> %d", "<C1>%s</C> %d", "<C1>%s</C> %d"),
            ],
            "en",
            "ja",
        )
        self.assertEqual(tr.translate("<C1>药</C> 2", "primary"), "<C1>Potion</C> 2")
        self.assertEqual(tr.translate("<C1>药</C> 2", "secondary"), "<C1>薬</C> 2")

    def test_overdrive_trim_alias_cannot_conflict_with_unchanged_source(self):
        prefix = "table/t_condition_info.tbl/OverDriveEffect/test/"
        records = [
            {
                "key": "table/t_text.tbl/TXT_CAMP_STATUS_OVERDRIVE_INFO_TEMPLATE",
                **entry(
                    "基本：%s%s%s\n特有：%s%s%s",
                    "基本：%s%s%s\n固有：%s%s%s",
                    "Base: %s%s%s\nUnique: %s%s%s ",
                ),
            },
            {"key": prefix + "name", **entry("强化", "強化", "Enhancement")},
            {"key": prefix + "common_effect", **entry("解除减益", "デバフ解除", "Remove debuffs")},
            {"key": prefix + "effect_1", **entry("STR+10%", "STR+10%", "STR+10%")},
        ]
        source = "基本：解除减益\n特有：STR+10%"
        tr = MenuTranslator(records, "en", "ja")
        self.assertEqual(tr.translate(source, "primary"), "Base: Remove debuffs\nUnique: STR+10% ")
        self.assertEqual(tr.translate(source, "secondary"), "基本：デバフ解除\n固有：STR+10%")

    def test_producer_numeric_width_and_full_sentence_annotation(self):
        records = [
            {
                **entry(
                    "BP上升了<C2>%d<C0>点。",
                    "ＢＰが<C2>%d<C0>上がった。",
                    "BP increased by <C2>%d<C0>.",
                ),
                "dynamic_producer": {
                    "family": "on_quest_add_bp",
                    "numbers": {"zh-Hans": ["ascii"], "ja": ["ascii"], "en": ["ascii"]},
                },
            },
            {
                **entry(
                    "要支付%d米拉休息吗？", "%dミラ払って休憩しますか？", "Spend %d mira to rest?"
                ),
                "dynamic_producer": {
                    "family": "rest_shop_process",
                    "numbers": {"zh-Hans": ["fullwidth"], "ja": ["fullwidth"], "en": ["ascii"]},
                },
            },
            # A global numeric name must not translate the producer's value.
            entry("2", "２", "two"),
        ]
        for target, expected in (
            ("ja", "ＢＰが<C2>2<C0>上がった。"),
            ("en", "BP increased by <C2>2<C0>."),
        ):
            tr = MenuTranslator(records, "zh-Hans", target)
            source = "BP上升了<C2>2<C0>点。"
            self.assertEqual(tr.raw_pair(source), (source, expected))
            plan = tr.render(source)
            self.assertEqual(plan["text"], "<R></R_>" + source)
            self.assertEqual([layer["text"] for layer in plan["layers"]], [expected + "</C></C>"])
            rest = "要支付１００米拉休息吗？"
            self.assertEqual(
                tr.raw_pair(rest),
                (
                    rest,
                    "１００ミラ払って休憩しますか？"
                    if target == "ja"
                    else "Spend 100 mira to rest?",
                ),
            )
            self.assertIsNone(tr.raw_pair("要支付100米拉休息吗？"))
            self.assertIsNone(tr.raw_pair("要支付１００米拉休息吗？额外"))

    def test_mutable_emotion_header_does_not_resolve_a_conflicting_body(self):
        body = "啊，说的也是呢。"
        first, second = "<#E[1118]#M_0#B[#60s7]>", "<#E_0#M_0#B_0>"
        records = [
            {
                "display_role": "dialogue",
                **entry(
                    first + body, first + "あっと、そうだったわね。", first + "Oh, I almost forgot!"
                ),
            },
            {
                "display_role": "dialogue",
                **entry(second + body, second + "そうね。", second + "You're right."),
            },
        ]
        tr = MenuTranslator(records, "en", "ja")
        self.assertIn(body, tr.ambiguous_display)
        for row in records:
            source = row["texts"]["zh-Hans"]
            self.assertNotIn(source, tr.pairs)  # native caller must capture real provenance
            self.assertEqual(tr.translate(source, "primary"), source)
            self.assertEqual(tr.translate(source, "secondary"), source)
            self.assertEqual(tr.render(source)["kind"], "plain")
            scoped = MenuTranslator([row], "en", "ja")
            self.assertEqual(scoped.translate(source, "primary"), row["texts"]["en"])
        self.assertEqual(tr.translate(body, "primary"), body)
        unknown = "<#E_9#M_0#B_0>" + body
        self.assertEqual(tr.translate(unknown, "secondary"), unknown)

    def test_verified_name_authority_clears_conflicting_speaker_guard(self):
        records = [
            {"display_role": "speaker", **entry("绯", "フェイ", "Fey")},
            {"display_role": "speaker", **entry("绯", "フェイ", "Voice_Fey")},
            {"key": "table/t_name.tbl/verified/name", **entry("绯", "フェイ", "Fey")},
        ]
        tr = MenuTranslator(records, "en", "ja")
        self.assertEqual(tr.translate("绯", "primary"), "Fey")
        self.assertNotIn("绯", tr.runtime_model()["ambiguous_display"])

    def test_conflicting_complete_dialogue_cannot_fall_back_to_freeform_format(self):
        body = "<K>啊，绯小姐！"
        entries = [
            {"display_role": "dialogue", **entry(body, "<K>Fey!")},
            {"display_role": "dialogue", **entry(body, "<K>Oh! Fey!")},
            entry("<K>啊，%s！", "<K>Oh! %s!"),
            entry("<#E_E#M_4#B_0><K>啊，%s！", "<#E_E#M_4#B_0><K>Oh! %s!"),
            entry("绯小姐", "Fey"),
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        source = "<#E_E#M_4#B_0>" + body
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(tr.translate(source, mode), source)
        self.assertEqual(tr.render(source), {"text": source, "layers": [], "kind": "plain"})

    def test_changed_dialogue_emotion_prefix_keeps_whole_body_lookup(self):
        for source, target in (
            ("<K>绯小姐也是，过得好吗？", "<K>フェイさんこそ元気だった？"),
            ("哈哈，这边还是\n忙得不可开交噢。", "はは、こっちは\n相変わらず忙しいよ。"),
        ):
            full = {
                "display_role": "dialogue",
                **entry("<#E_4#M_4#B_0>" + source, "<#E_4#M_4#B_0>" + target),
            }
            fragment = {"texts": {"zh-Hans": source}}
            tr = MenuTranslator([full, fragment], "zh-Hans", "ja")
            live = "<#E_8#M_4#B_0>" + source
            self.assertEqual(tr.translate(live, "secondary"), "<#E_8#M_4#B_0>" + target)
            self.assertEqual(tr.translate(live, "primary"), live)
            plan = tr.render(live)
            self.assertNotEqual(plan["kind"], "plain")
            if source.startswith("<K>"):
                self.assertEqual(
                    [layer["text"] for layer in plan["layers"]], [target.removeprefix("<K>")]
                )
            conflict = {"display_role": "dialogue", **entry(source, "異なる訳。")}
            self.assertEqual(
                MenuTranslator([full, fragment, conflict], "zh-Hans", "ja").translate(
                    live, "secondary"
                ),
                live,
            )

    def test_icon_only_line_keeps_each_following_annotation_payload(self):
        source = "<c930><I300>\n甲\n乙"
        target = "<c930><I300>\n一\n二"
        plan = MenuTranslator([entry(source, target)], "zh-Hans", "ja").render(source)
        self.assertEqual([layer["primary"] for layer in plan["layers"]], ["甲", "乙"])
        self.assertEqual(
            [layer["text"] for layer in plan["layers"]], ["<c930>一</C>", "<c930>二</C>"]
        )

    def test_complete_dialogue_padding_differences_do_not_block_translation(self):
        source = "<C1>　　　起降坪管制塔　　　\n 《利贝尔飞行船公社》"
        a = {
            "display_role": "dialogue",
            **entry(source, "<C1>　　　発着場管制塔　　　\n 《リベール飛行船公社》"),
        }
        b = {
            "display_role": "dialogue",
            **entry(source, "<C1>　　　発着場管制塔　　　\n《リベール飛行船公社》 "),
        }
        tr = MenuTranslator([a, b], "zh-Hans", "ja")
        self.assertEqual(tr.translate(source, "primary"), source)
        self.assertIn(tr.translate(source, "secondary"), (a["texts"]["ja"], b["texts"]["ja"]))
        conflict = {"display_role": "dialogue", **entry(source, "<C1>関係者以外立入禁止")}
        self.assertEqual(
            MenuTranslator([a, b, conflict], "zh-Hans", "ja").translate(source, "secondary"), source
        )
        # Interior word boundaries and actual wording are never normalized.
        x = {"display_role": "dialogue", **entry("提示", "a part")}
        y = {"display_role": "dialogue", **entry("提示", "apart")}
        self.assertEqual(
            MenuTranslator([x, y], "zh-Hans", "ja").translate("提示", "secondary"), "提示"
        )

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

    def test_unique_complete_label_is_not_blacklisted_by_missing_fragment(self):
        complete = {
            "key": "table/t_text.tbl/TXT_USE_HEAL_MACHINE",
            "texts": {"zh-Hans": "休息", "ja": "休憩する", "en": "Rest"},
        }
        fragment = {"key": "script/map/bed/code/0/alignment/partial", "texts": {"zh-Hans": "休息"}}
        tr = MenuTranslator([complete, fragment], "en", "ja", "zh-Hans")
        self.assertEqual(tr.translate("休息", "primary"), "Rest")
        self.assertEqual(tr.translate("休息", "secondary"), "休憩する")
        conflict = {"texts": {"zh-Hans": "休息", "ja": "別の文", "en": "Different"}}
        self.assertEqual(
            MenuTranslator([complete, fragment, conflict], "en", "ja", "zh-Hans").translate(
                "休息", "secondary"
            ),
            "休息",
        )
        self.assertEqual(
            MenuTranslator([fragment], "en", "ja", "zh-Hans").translate("休息", "secondary"), "休息"
        )

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
