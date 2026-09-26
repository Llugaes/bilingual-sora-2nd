import unittest
from sora_bilingual.localization.menu_text import MenuTranslator, annotation_plan
from sora_bilingual.localization.resources import Called, assembled_dialogue


def translator(a, b):
    return MenuTranslator([{"texts": {"zh-Hans": a, "ja": b}}], "zh-Hans", "ja")


class MarkupPreservationTests(unittest.TestCase):
    def test_full_dialogue_preserves_commands_and_explicit_line_breaks(self):
        call = Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 19),
                ("int", 11005),
                ("string", "<#E_0>"),
                ("string", "甲"),
                ("int", 10),
                ("string", "乙"),
            ),
        )
        self.assertEqual(assembled_dialogue(call), "<#E_0>甲\n乙")
        for tail in [(("int", 99),), (("float", 1),)]:
            self.assertIsNone(assembled_dialogue(Called(None, 3, call.args + tail)))

    def test_other_script_commands_are_not_treated_as_dialogue(self):
        self.assertIsNone(
            assembled_dialogue(Called(None, 3, (("int", 5), ("int", 99), ("string", "甲"))))
        )

    def test_trailing_secondary_blank_reflows_complete_secondary_without_loss(self):
        plan = translator("甲\n乙", "一二\n").render("甲\n乙")
        self.assertEqual(plan["kind"], "layered")
        self.assertEqual(plan["text"].replace("<R></R_>", ""), "甲\n乙")
        self.assertEqual([layer["text"] for layer in plan["layers"]], ["一", "二"])
        self.assertEqual("".join(layer["text"] for layer in plan["layers"]), "一二")

    def test_all_verified_dialogue_commands_assemble_complete_blocks(self):
        for command in (0, 6, 7, 19):
            call = Called(
                None,
                3,
                (
                    ("int", 5),
                    ("int", command),
                    ("int", 3),
                    ("string", "甲"),
                    ("int", 10),
                    ("string", "乙"),
                ),
            )
            self.assertEqual(assembled_dialogue(call), "甲\n乙")

    def test_complete_dialogue_disambiguates_repeated_fragments(self):
        entries = [
            {"texts": {"zh-Hans": "好。", "ja": "はい。"}},
            {"texts": {"zh-Hans": "好。", "ja": "よし。"}},
            {"texts": {"zh-Hans": "好。\n出发吧。", "ja": "よし。\n行こう。"}},
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja")
        self.assertEqual(tr.translate("好。"), "好。")
        self.assertIn("よし。", tr.render("好。\n出发吧。")["text"])

    def test_primary_ruby_stays_byte_exact_in_independent_lane(self):
        a = "来到<R>女神</R爱德斯>身旁。"
        b = "女神の傍へ。"
        plan = translator(a, b).render(a)
        self.assertEqual(plan["text"].replace("<R></R_>", ""), a)
        self.assertEqual(
            plan["layers"], [{"offset": 6, "text": b, "primary": a, "protected": True}]
        )

    def test_secondary_original_ruby_is_not_flattened(self):
        a = "翡翠之塔"
        b = "<R>翡翠</Rひすい>の塔"
        self.assertEqual(translator(a, b).render(a)["layers"][0]["text"], b)

    def test_emphasis_points_kept_in_both_languages(self):
        a = "<R>绝对不行</R・・・・>"
        b = "<R>絶対に駄目</R・・・・>"
        plan = translator(a, b).render(a)
        self.assertEqual(plan["text"], "<R></R_>" + a)
        self.assertEqual(plan["layers"][0]["text"], b)

    def test_original_ruby_does_not_disable_language_switch(self):
        a = "<R>女神</R爱德斯>"
        b = "<R>女神</Rエイドス>"
        tr = translator(a, b)
        self.assertEqual(tr.translate(a, "primary"), a)
        self.assertEqual(tr.translate(a, "secondary"), b)
        self.assertEqual(tr.render(a, "secondary")["kind"], "plain")

    def test_tagged_sentence_uses_complete_pair_not_fragment_guess(self):
        a = "命中率<C2>提升</C>。"
        b = "<C2>命中率アップ</C>。"
        plan = translator(a, b).render(a)
        self.assertEqual(plan["text"], "<R></R_>" + a)
        self.assertEqual(plan["layers"][0]["text"], b)

    def test_legacy_cutscene_mode_uses_annotations_without_extra_lines(self):
        a = "第一行\n第二行"
        b = "一行目\n二行目"
        tr = translator(a, b)
        self.assertEqual(tr.render(a, "bilingual"), tr.render(a, "annotation"))
        self.assertEqual(tr.render(a, "bilingual")["text"].count("\n"), a.count("\n"))

    def test_subtitle_colour_stack_does_not_leak_across_languages(self):
        plan = translator("<C2>甲", "<C3>一").render("<C2>甲", "bilingual")
        self.assertEqual(plan["text"], "<R></R_><C2>甲")
        self.assertEqual(plan["layers"][0]["text"], "<C3>一</C>")

    def test_composite_cutscene_is_not_interleaved(self):
        tr = MenuTranslator(
            [{"texts": {"zh-Hans": "甲", "ja": "一"}}, {"texts": {"zh-Hans": "乙", "ja": "二"}}],
            "zh-Hans",
            "ja",
        )
        self.assertEqual(tr.translate("甲\n乙", "bilingual"), "<R>甲</R一>\n<R>乙</R二>")

    def test_nonvisual_secondary_commands_are_not_replayed(self):
        a = "<#E_0#M_0>甲"
        b = "<#E_0#M_0><K3><C2>一</C><T>"
        self.assertEqual(translator(a, b).render(a)["layers"][0]["text"], "<C2>一</C>")

    def test_consumed_native_dialogue_controls_have_a_complete_display_variant(self):
        tr = translator("<#E_0>这里是梭哈牌桌。", "<#E_2>こちらはポーカー台です。")
        self.assertEqual(tr.translate("这里是梭哈牌桌。", "secondary"), "こちらはポーカー台です。")

    def test_formatted_dialogue_keeps_original_markup_and_translates_inserted_name(self):
        tr = MenuTranslator(
            [
                {"texts": {"zh-Hans": "<#E_0><C2>%s</C>啊。", "ja": "<#E_2><C2>%s</C>ですね。"}},
                {"texts": {"zh-Hans": "同花", "ja": "フラッシュ"}},
            ],
            "zh-Hans",
            "ja",
        )
        source = "<#E_0><C2>同花</C>啊。"
        plan = tr.render(source)
        self.assertEqual(plan["text"].replace("<R></R_>", ""), source)
        self.assertEqual(plan["layers"][0]["text"], "<C2>フラッシュ</C>ですね。")

    def test_offsets_are_utf8_bytes_and_linebreaks_are_preserved(self):
        a = "<R>神</Rかみ>\r\n第二行"
        b = "A\nB"
        plan = annotation_plan(a, b)
        data = plan["text"].encode()
        self.assertEqual(plan["text"].replace("<R></R_>", ""), a)
        for layer in plan["layers"]:
            self.assertEqual(data[layer["offset"] : layer["offset"] + 2], b"_>")

    def test_unmatched_line_counts_do_not_reflow_primary(self):
        a = "<C2>甲</C>\n乙"
        b = "一二三"
        plan = translator(a, b).render(a)
        self.assertEqual(plan["text"].replace("<R></R_>", ""), a)
        self.assertEqual([v["text"] for v in plan["layers"]], ["一二", "三"])

    def test_trailing_newline_and_blank_primary_never_drop_secondary(self):
        for a, b in [("甲\n", "一\n二"), ("甲\n\n乙", "一\n二\n三"), ("\n甲\n\n", "一\n二")]:
            plan = translator(a, b).render(a)
            self.assertEqual(plan["text"].replace("<R></R_>", ""), a)
            self.assertEqual(
                "".join(v["text"] for v in plan["layers"]).replace(" ", ""), b.replace("\n", "")
            )

    def test_dialogue_prefix_does_not_hide_original_ruby_pair(self):
        a = "<R>女神</R爱德斯>的身旁"
        b = "<R>女神</Rエイドス>の傍"
        tr = translator(a, b)
        source = "<#E_0#M_0#B_0>" + a
        self.assertEqual(tr.translate(source, "secondary"), "<#E_0#M_0#B_0>" + b)
        plan = tr.render(source)
        self.assertEqual(plan["text"].replace("<R></R_>", ""), source)
        self.assertEqual(plan["layers"][0]["text"], b)

    def test_unknown_original_ruby_is_left_intact(self):
        source = "<R>未知</Rみち>"
        self.assertEqual(
            translator("药", "薬").render(source), {"text": source, "layers": [], "kind": "plain"}
        )

    def test_same_language_has_no_extra_layer_or_geometry(self):
        a = "<R>神</Rかみ>"
        tr = MenuTranslator([{"texts": {"ja": a}}], "ja", "ja", "ja")
        self.assertEqual(tr.render(a), {"text": a, "layers": [], "kind": "plain"})
