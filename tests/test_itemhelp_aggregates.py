import struct
import unittest

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.item_help_composition import (
    _read_effect_groups,
    compile_item_help_grammar,
)
from sora_bilingual.localization.menu_text import MenuTranslator


STATUS = {
    "sha256:55a5a0f6872f18e3a7b1d5428b25c74d1bb84a6f795e803dd7874e238fda4b9a": (
        10,
        "命中率+%d",
        "ACC+%d",
        "命中率+%d",
    ),
    "sha256:d4703b2ecfcfd095304140cc120a066f40b4489647484f58d76ef8fd2b77bf18": (
        11,
        "回避率+%d",
        "EVA+%d",
        "回避率+%d",
    ),
    "sha256:e48212d6153564454ab23da892511aae3d867fb054bb1e8f2afbb6d9754cbc1c": (
        12,
        "魔法回避率+%d",
        "AEV+%d",
        "魔法回避率+%d",
    ),
    "sha256:d549c92b86709094e6cf4dd6c06b598dab8f84fce89d1abf3936cbf525cb6c53": (
        13,
        "必杀率+%d",
        "CRT+%d",
        "必殺率+%d",
    ),
}

EFFECTS = {
    "sha256:38eb3285f312386a3c5eb3b8fbf733ca9195c0e5bf2754b75258e50bccf92448": (
        39,
        (1,),
        ("混乱%d％", "Confuse %d%%", "混乱%d％"),
        ("混乱", "Confuse", "混乱"),
        ("%d％", " %d%%", "%d％"),
    ),
    "sha256:82fee96a7caa7bda848c3c254685b9bde94bdf220e4dd115978aaee1a13cc22b": (
        31,
        (1,),
        ("中毒%d％", "Poison %d%%", "毒%d％"),
        ("中毒", "Poison", "毒"),
        ("%d％", " %d%%", "%d％"),
    ),
    "sha256:27ca42a5a80f43e6aa96ea0804cce9f3ab9e6832de1ae351719a0a86d25377d7": (
        34,
        (1,),
        ("睡眠%d％", "Sleep %d%%", "睡眠%d％"),
        ("睡眠", "Sleep", "睡眠"),
        ("%d％", " %d%%", "%d％"),
    ),
    "sha256:a47925fc08e37eaff87bd2c4473c58d54d6309dcdd78981f18f9456ddb46b1c1": (
        38,
        (1,),
        ("黑暗%d％", "Blind %d%%", "暗闇%d％"),
        ("黑暗", "Blind", "暗闇"),
        ("%d％", " %d%%", "%d％"),
    ),
    "sha256:d833076b3ae7e9525c6af28af320c28c2bd2d4afce293b8c715cd8324008b959": (
        81,
        (16,),
        ("%d回合DEF%s", "DEF%s (%d turns)", "%dターンDEF%s"),
        ("DEF", "DEF", "DEF"),
        ("%s", "%s", "%s"),
    ),
    "sha256:dae76d0cf2b20ddbefd134ee7bbc2e0d776c897ceb6b337d5644ce7fc4f62108": (
        83,
        (16,),
        ("%d回合ADF%s", "ADF%s (%d turns) ", "%dターンADF%s"),
        ("ADF", "ADF", "ADF"),
        ("%s", "%s", "%s"),
    ),
    "sha256:c7647ebab85291ee4b9d0ce443c043cb89c22397cfad696daec27e7ee1191211": (
        80,
        (16,),
        ("%d回合STR%s", "STR%s (%d turns)", "%dターンSTR%s"),
        ("STR", "STR", "STR"),
        ("%s", "%s", "%s"),
    ),
    "sha256:2a68563858e5e8c03f097e398ac352be7dded163c6769db4d71ad59e45ed2f0b": (
        84,
        (16,),
        ("%d回合SPD%s", "SPD%s (%d turns)", "%dターンSPD%s"),
        ("SPD", "SPD", "SPD"),
        ("%s", "%s", "%s"),
    ),
    "sha256:904e5382bf5031d10d3edb4bf09a20bdc410483984e1d195b27a261c73eb3e5c": (
        46,
        (),
        ("加速", "Quick", "加速"),
        ("", "", ""),
        ("", "", ""),
    ),
    "sha256:8bfe55842e7ad4b7787d885eb96b96db998b979027468f4a06d8ad6c2118dc8a": (
        210,
        (),
        ("吸收HP", "Absorb HP", "HP吸収"),
        ("HP", "HP", "HP"),
        ("吸收", " Absorb", "吸収"),
    ),
    "sha256:2d48bc91299ce7a9643709ae1d0eab20dda6ae0ea5de55290e890665787a6540": (
        205,
        (),
        ("吸收EP", "Absorb EP", "EP吸収"),
        ("EP", "EP", "EP"),
        ("吸收", " Absorb", "吸収"),
    ),
    "sha256:single-all": (
        92,
        (16,),
        ("%d回合所有能力%s", "All Stats%s (%d turns) ", "%dターン全能力%s"),
        ("所有能力", "All Stats", "全能力"),
        ("%s", "%s", "%s"),
    ),
    "sha256:timed-fortune": (
        1202,
        (),
        ("强运", "Fortune", "強運"),
        ("强运", "Fortune", "強運"),
        ("（%d秒）", "(%d Seconds)", "（%d秒）"),
    ),
    "sha256:debuff-immunity": (
        97,
        (),
        ("免疫减益效果", "Debuff Immunity", "デバフ無効"),
        ("减益", "Debuff", "デバフ"),
        ("无效", "Immunity", "無効"),
    ),
    "sha256:duration": (
        1206,
        (1,),
        ("（%d秒）", "(%d Seconds)", "（%d秒）"),
        ("", "", ""),
        ("（%d秒）", "(%d Seconds)", "（%d秒）"),
    ),
    "sha256:cure-status": (
        95,
        (),
        ("解除异常状态", "Cure Status Ailments", "状態異常解除"),
        ("", "", ""),
        ("", "", ""),
    ),
    "sha256:cure-debuff": (
        96,
        (),
        ("解除能力降低", "Cure Stat Debuff", "能力低下解除"),
        ("", "", ""),
        ("", "", ""),
    ),
    "sha256:cc311d9666993ad7471edb97a4292bd44de5cac259718aab39db45a6008a99a8": (
        123,
        (4,),
        ("回复HP%s", "Heal %s HP", "HP%s回復"),
        ("HP", "HP", "HP"),
        ("回复%s", "Recover %s ", "%s回復"),
    ),
    "sha256:9792ad85797c0b1a6ea1d3a7efb83d51b75a2d47d37d762623d852392fa0595e": (
        125,
        (4,),
        ("回复EP%s", "Recover %s EP", "EP%s回復"),
        ("EP", "EP", "EP"),
        ("回复%s", "Recover %s ", "%s回復"),
    ),
}


def texts(values):
    zh, en, ja = values
    return {
        language: {"zh-Hans": zh, "en": en, "ja": ja}.get(language, en) for language in LANGUAGES
    }


def fixture():
    entries = []
    metadata = {"SkillItemStatusData": {}, "SkillEffectHelpData": {}}
    for identity, (record_id, zh, en, ja) in STATUS.items():
        base = "table/t_itemhelp.tbl/SkillItemStatusData/" + identity
        entries.append({"key": base + "/format", "texts": texts((zh, en, ja))})
        metadata["SkillItemStatusData"][identity] = {"id": record_id, "parameter_types": ()}
    for identity, (record_id, parameter_types, name, stat, form) in EFFECTS.items():
        base = "table/t_itemhelp.tbl/SkillEffectHelpData/" + identity
        entries.append({"key": base + "/name", "texts": texts(name)})
        if any(stat):
            entries.append({"key": base + "/stat", "texts": texts(stat)})
        if any(form):
            entries.append({"key": base + "/format", "texts": texts(form)})
        if parameter_types == (16,):
            entries.append(
                {
                    "key": base + "/turns",
                    "texts": texts(("%d回合", "(%d turns)", "%dターン")),
                }
            )
        metadata["SkillEffectHelpData"][identity] = {
            "id": record_id,
            "parameter_types": parameter_types,
        }
    entries.extend(
        [
            {"key": "table/t_text.tbl/TXT_ITEM_HELP_LINK", "texts": texts(("･", "/", "･"))},
            {"key": "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8", "texts": texts(("／", ", ", "／"))},
            {
                "key": "table/t_text.tbl/TXT_ITEM_HELP_PERSENT",
                "texts": texts(("%d％", "%d%%", "%d％")),
            },
        ]
    )
    groups = [
        ((39, 30, 0, 0), (34, 30, 0, 0), (38, 30, 0, 0)),
        ((81, 100, 5, 1), (83, 100, 5, 1)),
        ((46, 100, 0, 0), (80, 100, 3, 1), (84, 100, 3, 1)),
        ((210, 100, 0, 0), (205, 100, 0, 0)),
        ((80, 100, 3, 1),),
        ((83, 100, 4, 1),),
        ((92, 100, 3, 1),),
        ((1202, 1, 50, 5), (1206, 60, 0, 0)),
        ((123, 25, 0, 0), (125, 25, 0, 0), (95, 100, 0, 0), (96, 100, 0, 0)),
    ]
    return entries, metadata, groups


class ItemHelpAggregateTests(unittest.TestCase):
    def test_skill_raw_slots_use_table_record_offset_not_object_relative_offset(self):
        # The PAC row starts a verified five-slot sequence at +0x30.  The
        # normalizer's object-relative +0x3c is inside that first raw tuple,
        # so treating it as a distinct PAC slot base silently drops ID 123.
        stride = 176
        start = 88
        raw = bytearray(start + stride)
        raw[:4] = b"#TBL"
        struct.pack_into("<I", raw, 4, 1)
        raw[8 : 8 + len(b"SkillParam")] = b"SkillParam"
        struct.pack_into("<III", raw, 8 + 68, start, stride, 1)
        expected = (
            (123, 25, 0, 0),
            (125, 25, 0, 0),
            (95, 100, 0, 0),
            (96, 100, 0, 0),
            (97, 100, 0, 0),
        )
        for slot, values in enumerate(expected):
            struct.pack_into("<4I", raw, start + 0x30 + slot * 16, *values)
        self.assertEqual(
            _read_effect_groups(bytes(raw), "table/t_skill.tbl", "SkillParam", 0x30, 5),
            (expected,),
        )
        self.assertNotEqual(
            _read_effect_groups(bytes(raw), "table/t_skill.tbl", "SkillParam", 0x3C, 5),
            (expected,),
        )

    def test_compiles_only_verified_status_and_detail_families(self):
        entries, metadata, groups = fixture()
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        status = {row["key"].rsplit("/", 1)[-1]: row["texts"] for row in grammar["status_entries"]}
        detail = {row["texts"]["zh-Hans"]: row["texts"] for row in grammar["detail_entries"]}

        self.assertEqual(status["10"]["zh-Hans"], "命中率+")
        self.assertEqual(status["10"]["en"], "ACC+")
        self.assertEqual(status["13"]["ja"], "必殺率+")
        self.assertEqual(detail["混乱･中毒%d％"]["en"], "Confuse/Poison %d%%")
        self.assertEqual(detail["混乱･睡眠･黑暗%d％"]["en"], "Confuse/Sleep/Blind %d%%")
        self.assertEqual(detail["混乱･睡眠･黑暗%d％"]["ja"], "混乱･睡眠･暗闇%d％")
        self.assertEqual(detail["%d回合DEF･ADF↑"]["en"], "DEF/ADF↑ (%d turns)")
        self.assertEqual(detail["加速／%d回合STR･SPD↑"]["en"], "Quick, STR/SPD↑ (%d turns)")
        self.assertEqual(detail["HP･EP吸收"]["en"], "HP/EP Absorb")
        self.assertTrue(all(row["detail_authority"] for row in grammar["detail_entries"]))
        self.assertEqual(
            len({row["key"] for row in grammar["detail_entries"]}),
            len(grammar["detail_entries"]),
        )
        self.assertEqual(grammar["audit"]["status_families"], 4)
        self.assertGreater(grammar["audit"]["detail_templates"], 5)
        self.assertEqual(grammar["audit"]["max_group_slots"], 3)
        self.assertEqual(grammar["audit"]["max_raw_group_slots"], 5)

    def test_does_not_admit_parameter_type_drift_to_the_chance_family(self):
        entries, metadata, groups = fixture()
        changed = {
            kind: {identity: dict(value) for identity, value in rows.items()}
            for kind, rows in metadata.items()
        }
        changed["SkillEffectHelpData"][
            "sha256:38eb3285f312386a3c5eb3b8fbf733ca9195c0e5bf2754b75258e50bccf92448"
        ]["parameter_types"] = (16,)
        grammar = compile_item_help_grammar(entries, "zh-Hans", changed, groups)
        sources = {row["texts"]["zh-Hans"] for row in grammar["detail_entries"]}
        self.assertNotIn("混乱･中毒%d％", sources)

    def test_pair_build_does_not_require_unrelated_locale_text(self):
        entries, metadata, groups = fixture()
        for entry in entries:
            entry["texts"] = {
                language: text
                for language, text in entry["texts"].items()
                if language in ("zh-Hans", "en", "ja")
            }
        grammar = compile_item_help_grammar(
            entries,
            "zh-Hans",
            metadata,
            groups,
            languages=("zh-Hans", "en", "ja"),
        )
        self.assertTrue(grammar["detail_entries"])

    def test_actual_single_slot_and_timed_builders_stay_anchored(self):
        entries, metadata, groups = fixture()
        description = {
            "key": "table/t_skill.tbl/example/description",
            "texts": texts(("技能说明", "Skill description", "技の説明")),
        }
        grammar = compile_item_help_grammar(entries + [description], "zh-Hans", metadata, groups)
        detail = {row["texts"]["zh-Hans"]: row["texts"] for row in grammar["detail_entries"]}
        self.assertEqual(detail["%d回合STR↑"]["en"], "STR↑ (%d turns)")
        self.assertEqual(detail["%d回合ADF↑"]["ja"], "%dターンADF↑")
        self.assertEqual(detail["%d回合所有能力↑"]["en"], "All Stats↑ (%d turns)")
        self.assertEqual(detail["强运（%d秒）"]["en"], "Fortune(%d Seconds)")

        translator = MenuTranslator(
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"],
            "en",
            "ja",
            "zh-Hans",
        )
        suffix = "\n<C0>技能说明"
        expected = {
            "无效": "Immunity",
            "强运（60秒）": "Fortune(60 Seconds)",
            "5回合STR↑": "STR↑ (5 turns)",
            "5回合ADF↑": "ADF↑ (5 turns)",
            "5回合所有能力↑": "All Stats↑ (5 turns)",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(
                    translator.translate(source + suffix, "primary"),
                    target + "\n<C0>Skill description",
                )
        self.assertEqual(translator.translate("强运（60秒）", "primary"), "强运（60秒）")

    def test_live_turn_icon_segment_is_replaced_only_under_the_detail_anchor(self):
        entries, metadata, groups = fixture()
        entries.append(
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/cp-regen/name",
                "texts": texts(("CP逐渐上升", "CP Regen", "CP徐々上昇")),
            }
        )
        metadata["SkillEffectHelpData"]["cp-regen"] = {"id": 131, "parameter_types": ()}
        description = {
            "key": "table/t_skill.tbl/live-str/description",
            "texts": texts(("技能说明", "Skill description", "技の説明")),
        }
        grammar = compile_item_help_grammar(entries + [description], "zh-Hans", metadata, groups)
        inline = {
            (
                tuple(row["item_help_contract"]["record_ids"]),
                tuple(row["item_help_contract"]["inline_icons"]),
            ): row
            for row in grammar["detail_entries"]
            if row.get("detail_inline_icon")
        }
        self.assertEqual(
            inline[((80,), ("<I270>",))]["texts"]["en"], "<c698>STR<I270> (%d turns)</C>"
        )
        self.assertNotIn(((81,), ("<I267>",)), inline)

        # This is the live STR page after restoring the Chinese primary text
        # from its resident <R> wrappers. The actual token order is text,
        # native icon, closing colour; a Unicode-arrow template cannot match it.
        source = (
            "<C3></C>【辅助／<I299><C3>我方·单体</C>】"
            "<c698>5回合STR<I270></C><c698>／</C><c698>CP逐渐上升</C>"
            "<c698>／</C><c698>解除能力降低</C>\n<C0><C9>技能说明"
        )
        unpatched = [row for row in grammar["detail_entries"] if not row.get("detail_inline_icon")]
        red = MenuTranslator(
            entries + [description] + grammar["status_entries"] + unpatched, "en", "ja", "zh-Hans"
        )
        self.assertIn("<c698>5回合STR<I270></C>", red.translate(source, "primary"))

        translator = MenuTranslator(
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"],
            "en",
            "ja",
            "zh-Hans",
        )
        expected_primary = (
            "<C3></C>【辅助／<I299><C3>我方·单体</C>】"
            "<c698>STR<I270> (5 turns)</C><c698>／</C><c698>CP Regen</C>"
            "<c698>／</C><c698>Cure Stat Debuff</C>\n<C0><C9>Skill description"
        )
        expected_secondary = (
            "<C3></C>【辅助／<I299><C3>我方·单体</C>】"
            "<c698>5ターンSTR<I270></C><c698>／</C><c698>CP徐々上昇</C>"
            "<c698>／</C><c698>能力低下解除</C>\n<C0><C9>技の説明"
        )
        self.assertEqual(translator.translate(source, "primary"), expected_primary)
        self.assertEqual(translator.translate(source, "secondary"), expected_secondary)
        plan = translator.render(source, "annotation")
        self.assertEqual(plan["kind"], "layered")
        self.assertEqual(plan["text"].count("<I270>"), 1)
        self.assertIn("5ターンSTR<I270>", "".join(layer["text"] for layer in plan["layers"]))
        outside_detail = translator.translate(source.removesuffix("\n<C0><C9>技能说明"), "primary")
        self.assertIn("<c698>5回合STR<I270></C>", outside_detail)
        self.assertNotIn("STR<I270> (5 turns)", outside_detail)
        malformed_ruby = "<R>已配对</Rpaired><R>" + source
        self.assertFalse(translator.details.has_detail_inline_icon(malformed_ruby))
        self.assertIn("<c698>5回合STR<I270></C>", translator.translate(malformed_ruby, "primary"))

    def test_raw_description_context_scopes_cp_and_keeps_original_ruby_atomic(self):
        entries, metadata, groups = fixture()
        entries.extend(
            [
                {
                    "key": "table/t_itemhelp.tbl/SkillEffectHelpData/cp-regen/name",
                    "texts": texts(("CP逐渐上升", "CP Regen", "CP徐々上昇")),
                },
                {
                    # The same English short phrase is used by a distinct
                    # condition/help record, so it must stay globally denied.
                    "key": "table/t_condition_info.tbl/cp-regen/name",
                    "texts": texts(("逐渐回复CP", "CP Regen", "CP徐々回復")),
                },
            ]
        )
        metadata["SkillEffectHelpData"]["cp-regen"] = {"id": 131, "parameter_types": ()}
        description = {
            "key": "table/t_skill.tbl/cp-context/description",
            "texts": texts(("技能说明", "Skill description", "技の説明")),
        }
        grammar = compile_item_help_grammar(
            entries + [description],
            "en",
            metadata,
            groups,
            actual_contexts=(
                {
                    "description_key": description["key"],
                    "group": ((80, 100, 5, 1), (131, 15, 3, 0), (96, 100, 0, 0)),
                },
            ),
        )
        context_entries = [
            row for row in grammar["detail_entries"] if row.get("detail_context_only")
        ]
        self.assertEqual(len(context_entries), 1)
        self.assertEqual(context_entries[0]["item_help_contract"]["record_ids"], [131])
        translator = MenuTranslator(
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"],
            "zh-Hans",
            "ja",
            "en",
        )
        source = "<c698>CP Regen</C>\n<C0><C9>Skill description"
        self.assertEqual(
            translator.translate(source, "primary"),
            "<c698>CP逐渐上升</C>\n<C0><C9>技能说明",
        )
        self.assertEqual(
            translator.translate("<c698>CP Regen</C>", "primary"), "<c698>CP Regen</C>"
        )
        self.assertEqual(
            translator.translate("<c698>CP Regen</C>\n<C0><C9>Other description", "primary"),
            "<c698>CP Regen</C>\n<C0><C9>Other description",
        )
        ruby_source = (
            "<R><c698>CP Regen</C></RCP Regen><c698>CP Regen</C>\n<C0><C9>Skill description"
        )
        self.assertEqual(
            translator.translate(ruby_source, "primary"),
            "<R><c698>CP Regen</C></RCP Regen><c698>CP逐渐上升</C>\n<C0><C9>技能说明",
        )
        malformed_ruby = "<R>已配对</Rpaired><R>" + source
        self.assertFalse(
            translator.details.has_detail_context(malformed_ruby, "<C0><C9>Skill description")
        )
        self.assertIn("<c698>CP Regen</C>", translator.translate(malformed_ruby, "primary"))

    def test_element_title_uses_only_the_raw_category_icon_contract(self):
        entries, metadata, groups = fixture()
        number = {"key": "table/t_text.tbl/TXT_HUD_ITEM_NUM", "texts": texts(("×%d", "x%d", "×%d"))}
        templates = (
            ("地属性", "地属性", "Earth Element"),
            ("水属性", "水属性", "Water Element"),
            ("火属性", "火属性", "Fire Element"),
            ("风属性", "風属性", "Wind Element"),
            ("时属性", "時属性", "Time Element"),
            ("空属性", "空属性", "Space Element"),
            ("幻属性", "幻属性", "Mirage Element"),
        )
        contract = []
        for attribute, (zh, ja, en) in enumerate(templates, start=1):
            key = f"table/t_itemhelp.tbl/ItemKindHelpData/element-{attribute}/description"
            entries.append(
                {
                    "key": key,
                    "texts": texts(
                        (
                            f"{zh}【 属性值：%s 】",
                            f"{en} [Elemental Value: %s]",
                            f"{ja}【 属性値：%s 】",
                        )
                    ),
                }
            )
            contract.append(
                {
                    "description_key": key,
                    "category": 19 + attribute,
                    "attribute": attribute,
                    "icon": 41 + attribute,
                }
            )
        red = MenuTranslator(entries + [number], "en", "ja", "zh-Hans")
        source = "幻属性【 属性值：<I48>×2 】"
        # The standalone number formatter may localize ×, but it cannot build
        # the element title without the category/icon contract.
        self.assertNotIn("Mirage Element", red.translate(source, "primary"))

        grammar = compile_item_help_grammar(
            entries + [number],
            "zh-Hans",
            metadata,
            groups,
            element_titles=tuple(contract),
        )
        generated = [
            row
            for row in grammar["detail_entries"]
            if row.get("dynamic_producer", {}).get("family") == "item_help_element_title"
        ]
        self.assertEqual(len(generated), 7)
        translator = MenuTranslator(
            entries + [number] + grammar["status_entries"] + grammar["detail_entries"],
            "en",
            "ja",
            "zh-Hans",
        )
        self.assertEqual(
            translator.translate(source, "primary"),
            "Mirage Element [Elemental Value: <I48>x2]",
        )
        self.assertEqual(
            translator.translate(source, "secondary"),
            "幻属性【 属性値：<I48>×2 】",
        )
        self.assertNotIn(
            "Mirage Element",
            translator.translate("幻属性【 属性值：<I47>×2 】", "primary"),
        )
        plan = translator.render(source, "annotation")
        self.assertEqual(plan["kind"], "layered")
        self.assertIn("Mirage Element", plan["text"])
        self.assertIn("幻属性", "".join(layer["text"] for layer in plan["layers"]))

    def test_menu_translator_keeps_typed_aggregates_inside_anchored_details(self):
        entries, metadata, groups = fixture()
        description = {
            "key": "table/t_skill.tbl/example/description",
            "texts": texts(("技能说明", "Skill description", "技の説明")),
        }
        entries.append(description)
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        translator = MenuTranslator(
            entries + grammar["status_entries"] + grammar["detail_entries"],
            "en",
            "ja",
            "zh-Hans",
        )

        bare = "混乱･睡眠･黑暗90％"
        self.assertEqual(translator.translate(bare, "primary"), bare)
        self.assertEqual(
            translator.translate(bare + "\n技能说明", "primary"),
            "Confuse/Sleep/Blind 90%\nSkill description",
        )
        self.assertEqual(translator.translate("混乱･中毒90％", "primary"), "混乱･中毒90％")
        self.assertEqual(
            translator.translate("混乱･中毒90％\n技能说明", "primary"),
            "Confuse/Poison 90%\nSkill description",
        )
        self.assertEqual(translator.translate("命中率+", "primary"), "ACC+")
        self.assertEqual(translator.translate("命中率+", "secondary"), "命中率+")

    def test_literal_stat_boundary_padding_selects_one_original_record(self):
        entries, metadata, groups = fixture()
        original = (
            "table/t_itemhelp.tbl/SkillEffectHelpData/"
            "sha256:8bfe55842e7ad4b7787d885eb96b96db998b979027468f4a06d8ad6c2118dc8a"
        )
        duplicate_identity = "sha256:" + "a" * 64
        duplicate = "table/t_itemhelp.tbl/SkillEffectHelpData/" + duplicate_identity
        for field in ("name", "stat", "format"):
            value = next(row["texts"] for row in entries if row["key"] == original + "/" + field)
            copied = dict(value)
            if field == "stat":
                for language in ("en", "fr", "de", "es"):
                    copied[language] += " "
            entries.append({"key": duplicate + "/" + field, "texts": copied})
        metadata["SkillEffectHelpData"][duplicate_identity] = {
            "id": 213,
            "parameter_types": (),
        }
        groups.append(((213, 100, 0, 0), (205, 100, 0, 0)))

        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        candidates = [
            row for row in grammar["detail_entries"] if row["texts"]["zh-Hans"] == "HP･EP吸收"
        ]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["texts"]["de"], "HP/EP Absorb")

    def test_literal_stat_wording_difference_is_not_collapsed(self):
        entries, metadata, groups = fixture()
        original = (
            "table/t_itemhelp.tbl/SkillEffectHelpData/"
            "sha256:8bfe55842e7ad4b7787d885eb96b96db998b979027468f4a06d8ad6c2118dc8a"
        )
        different_identity = "sha256:" + "b" * 64
        different = "table/t_itemhelp.tbl/SkillEffectHelpData/" + different_identity
        name = dict(next(row["texts"] for row in entries if row["key"] == original + "/name"))
        stat = dict(next(row["texts"] for row in entries if row["key"] == original + "/stat"))
        form = dict(next(row["texts"] for row in entries if row["key"] == original + "/format"))
        name["en"], stat["en"] = "Absorb Health", "Health"
        entries.extend(
            [
                {"key": different + "/name", "texts": name},
                {"key": different + "/stat", "texts": stat},
                {"key": different + "/format", "texts": form},
            ]
        )
        metadata["SkillEffectHelpData"][different_identity] = {
            "id": 214,
            "parameter_types": (),
        }
        groups.append(((214, 100, 0, 0), (205, 100, 0, 0)))

        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        targets = {
            row["texts"]["en"]
            for row in grammar["detail_entries"]
            if row["texts"]["zh-Hans"] == "HP･EP吸收"
        }
        self.assertEqual(targets, {"HP/EP Absorb", "Health/EP Absorb"})

    def test_independent_literal_group_is_audited_without_an_exact_constructor(self):
        entries, metadata, groups = fixture()
        for record_id, zh, en, ja in (
            (998, "解除甲", "Cure A", "甲解除"),
            (999, "解除乙", "Cure B", "乙解除"),
        ):
            identity = f"sha256:literal-{record_id}"
            entries.append(
                {
                    "key": f"table/t_itemhelp.tbl/SkillEffectHelpData/{identity}/name",
                    "texts": texts((zh, en, ja)),
                }
            )
            metadata["SkillEffectHelpData"][identity] = {"id": record_id, "parameter_types": ()}
        groups.append(((998, 100, 0, 0), (999, 100, 0, 0)))
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        self.assertIn([998, 999], grammar["audit"]["independent_literal_groups"])
        self.assertNotIn([998, 999], grammar["audit"]["unsupported_multi_record_groups"])
        # Existing literal-stat constructors stay outside the original
        # unsupported denominator, even though their raw group is also literal.
        self.assertNotIn([210, 205], grammar["audit"]["independent_literal_groups"])

    def test_native_happy_trigger_recovery_header_stays_one_typed_template(self):
        entries, metadata, groups = fixture()
        description = {
            "key": "table/t_skill.tbl/happy-trigger/description",
            "texts": texts(("幸福扳机说明", "Happy Trigger description", "ハッピートリガー説明")),
        }
        grammar = compile_item_help_grammar(entries + [description], "zh-Hans", metadata, groups)
        recovery = [
            row
            for row in grammar["detail_entries"]
            if row["item_help_contract"]["family"] == "percent_recovery_group"
        ]
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0]["texts"]["zh-Hans"], "HP･EP回复%d％")
        self.assertEqual(recovery[0]["texts"]["en"], "Recover %d%% HP/EP")
        self.assertEqual(recovery[0]["item_help_contract"]["record_ids"], [123, 125])
        self.assertEqual(grammar["audit"]["percent_recovery_records"], 2)
        self.assertEqual(grammar["audit"]["percent_recovery_groups_proven"], 1)
        self.assertEqual(grammar["audit"]["percent_recovery_headers_proven"], 1)

        all_entries = (
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"]
        )
        for source_language in LANGUAGES:
            source = recovery[0]["texts"][source_language].replace("%d", "25").replace("%%", "%")
            source += "\n<C0>" + description["texts"][source_language]
            for target_language in LANGUAGES:
                target = (
                    recovery[0]["texts"][target_language].replace("%d", "25").replace("%%", "%")
                )
                target += "\n<C0>" + description["texts"][target_language]
                translator = MenuTranslator(all_entries, target_language, "ja", source_language)
                with self.subTest(source=source_language, target=target_language):
                    self.assertEqual(translator.translate(source, "primary"), target)

        translator = MenuTranslator(all_entries, "en", "ja", "zh-Hans")
        self.assertEqual(
            translator.translate("HP回复25％\n<C0>幸福扳机说明", "primary"),
            "Recover 25% HP\n<C0>Happy Trigger description",
        )
        self.assertEqual(
            translator.translate("EP回复25％\n<C0>幸福扳机说明", "primary"),
            "Recover 25% EP\n<C0>Happy Trigger description",
        )
        self.assertEqual(
            translator.translate("HP回复25％･EP回复30％\n<C0>幸福扳机说明", "primary"),
            "HP回复25％･EP回复30％\n<C0>Happy Trigger description",
        )

    def test_complete_native_recovery_header_beats_slash_fragmentation(self):
        entries, metadata, groups = fixture()
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        headers = [
            row
            for row in grammar["detail_entries"]
            if row["item_help_contract"]["family"] == "percent_recovery_header"
        ]
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0]["item_help_contract"]["record_ids"], [123, 125, 95, 96])
        description = {
            "key": "table/t_skill.tbl/happy/description",
            "texts": texts(("幸福扳机说明", "Happy Trigger description", "ハッピートリガー説明")),
        }
        translator = MenuTranslator(
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"],
            "ja",
            "en",
            "en",
        )
        source = (
            "Recover 25% HP/EP, Cure Status Ailments, Cure Stat Debuff"
            "\n<C0>Happy Trigger description"
        )
        self.assertEqual(
            translator.translate(source, "primary"),
            "HP･EP25％回復／状態異常解除／能力低下解除\n<C0>ハッピートリガー説明",
        )
        all_entries = (
            entries + [description] + grammar["status_entries"] + grammar["detail_entries"]
        )
        for source_language in LANGUAGES:
            source_header = (
                headers[0]["texts"][source_language].replace("%d", "25").replace("%%", "%")
            )
            source_value = source_header + "\n<C0>" + description["texts"][source_language]
            for target_language in LANGUAGES:
                target_header = (
                    headers[0]["texts"][target_language].replace("%d", "25").replace("%%", "%")
                )
                target_value = target_header + "\n<C0>" + description["texts"][target_language]
                with self.subTest(source=source_language, target=target_language):
                    self.assertEqual(
                        MenuTranslator(
                            all_entries, target_language, "ja", source_language
                        ).translate(source_value, "primary"),
                        target_value,
                    )

        # Translation to every target is not sufficient for a detail: the
        # production path finally asks for the annotation plan.  Replay the
        # reported target directions from every installed source language so
        # both header and description retain an owned ruby pair.
        for source_language in LANGUAGES:
            source_header = (
                headers[0]["texts"][source_language].replace("%d", "25").replace("%%", "%")
            )
            source_value = source_header + "\n<C0>" + description["texts"][source_language]
            for primary, secondary in (("en", "ja"), ("ja", "en"), ("zh-Hans", "ja")):
                translator = MenuTranslator(all_entries, primary, secondary, source_language)
                primary_header = headers[0]["texts"][primary].replace("%d", "25").replace("%%", "%")
                secondary_header = (
                    headers[0]["texts"][secondary].replace("%d", "25").replace("%%", "%")
                )
                with self.subTest(
                    source=source_language, primary=primary, secondary=secondary, mode="annotation"
                ):
                    plan = translator.render(source_value, "annotation")
                    self.assertEqual(plan["kind"], "ruby")
                    self.assertEqual(plan["layers"], [])
                    self.assertIn(primary_header, plan["text"])
                    self.assertIn(secondary_header, plan["text"])
                    self.assertIn(description["texts"][primary], plan["text"])
                    self.assertIn(description["texts"][secondary], plan["text"])


if __name__ == "__main__":
    unittest.main()
