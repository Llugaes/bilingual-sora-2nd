import unittest

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.item_help_composition import (
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
        ]
    )
    groups = [
        ((39, 30, 0, 0), (34, 30, 0, 0), (38, 30, 0, 0)),
        ((81, 100, 5, 1), (83, 100, 5, 1)),
        ((46, 100, 0, 0), (80, 100, 3, 1), (84, 100, 3, 1)),
        ((210, 100, 0, 0), (205, 100, 0, 0)),
    ]
    return entries, metadata, groups


class ItemHelpAggregateTests(unittest.TestCase):
    def test_compiles_only_verified_status_and_detail_families(self):
        entries, metadata, groups = fixture()
        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        status = {row["key"].rsplit("/", 1)[-1]: row["texts"] for row in grammar["status_entries"]}
        detail = {row["texts"]["zh-Hans"]: row["texts"] for row in grammar["detail_entries"]}

        self.assertEqual(status["10"]["zh-Hans"], "命中率+")
        self.assertEqual(status["10"]["en"], "ACC+")
        self.assertEqual(status["13"]["ja"], "必殺率+")
        self.assertEqual(detail["混乱･中毒%d％"]["en"], "Confuse/Poison %d%%")
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

        bare = "混乱･中毒90％"
        self.assertEqual(translator.translate(bare, "primary"), bare)
        self.assertEqual(
            translator.translate(bare + "\n技能说明", "primary"),
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

        grammar = compile_item_help_grammar(entries, "zh-Hans", metadata, groups)
        targets = {
            row["texts"]["en"]
            for row in grammar["detail_entries"]
            if row["texts"]["zh-Hans"] == "HP･EP吸收"
        }
        self.assertEqual(targets, {"HP/EP Absorb", "Health/EP Absorb"})


if __name__ == "__main__":
    unittest.main()
