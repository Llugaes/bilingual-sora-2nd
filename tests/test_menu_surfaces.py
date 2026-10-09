"""Resource-scoped menu composition must not inherit unrelated text collisions."""

import unittest

from sora_bilingual.localization.menu_text import MenuTranslator


def record(key, source, japanese, english):
    return {"key": key, "texts": {"zh-Hans": source, "ja": japanese, "en": english}}


class MenuSurfaceTests(unittest.TestCase):
    def test_registration_parameter_uses_entire_map_spot_family(self):
        template = record(
            "table/t_text.tbl/TXT_HUD_ADD_MAPJUMP_SPOT",
            "移动目标<c984>【%s】</c>已登录完成",
            "移動先<c984>【%s】</c>が登録された",
            "Location <c984>[%s]</c> added to map.",
        )
        spot = record("table/t_mapjump.tbl/MapJumpSpotData/spot/name", "工房", "工房名", "Factory")
        unrelated = record("table/t_tips.tbl/tip/title", "【工房】", "【工房名】", "Factory")
        tr = MenuTranslator([template, spot, unrelated], "zh-Hans", "ja", "en")
        source = "<s28>Location <c984>[Factory]</c> added to map."
        self.assertEqual(
            tr.translate(source, "primary"), "<s28>移动目标<c984>【工房】</c>已登录完成"
        )
        self.assertEqual(
            tr.translate(source, "secondary"), "<s28>移動先<c984>【工房名】</c>が登録された"
        )
        self.assertEqual(tr.translate("Factory", "secondary"), "Factory")

    def test_registration_rejects_unknown_partial_and_conflicting_names(self):
        template = record(
            "table/t_text.tbl/TXT_HUD_ADD_MAPJUMP_SPOT", "登录【%s】", "登録【%s】", "Added [%s]"
        )
        first = record("table/t_mapjump.tbl/MapJumpSpotData/one/name", "地点一", "場所一", "Place")
        unrelated = record("table/t_name.tbl/actor/name", "演员", "俳優", "Actor")
        for extra, name in (
            (unrelated, "Actor"),
            (
                {"key": "table/t_mapjump.tbl/MapJumpSpotData/two/name", "texts": {"en": "Place"}},
                "Place",
            ),
            (
                record("table/t_mapjump.tbl/MapJumpSpotData/two/name", "地点二", "場所二", "Place"),
                "Place",
            ),
        ):
            with self.subTest(extra=extra):
                tr = MenuTranslator([template, first, extra], "zh-Hans", "ja", "en")
                source = f"Added [{name}]"
                self.assertEqual(tr.translate(source, "primary"), source)
                self.assertEqual(tr.translate(source, "secondary"), source)

    def test_map_confirmation_uses_map_record_not_quest_client_or_partial_code(self):
        records = [
            record(
                "table/t_text.tbl/TXT_MAPJUMP_CONFIRM_MAPJUMP",
                "确定要移动至<C1>%s</C>吗？",
                "<C1>%s</C>へ移動しますか？",
                "Fast Travel to <C1>%s</C>?",
            ),
            record(
                "table/t_mapjump.tbl/MapJumpSpotData/map-hotel/name",
                "蔡恩拉德酒店",
                "ツァンラートホテル",
                "Zahnrad Hotel",
            ),
            record(
                "table/t_quest.tbl/QuestTitle/quest/client",
                "蔡恩拉德酒店",
                "ツァンラート・ホテル",
                "Zahnrad Hotel",
            ),
            record(
                "table/t_mapjump.tbl/MapJumpSpotData/map-tower/name",
                "红莲之塔",
                "紅蓮の塔",
                "Carnelia Tower",
            ),
            {
                "key": "script/scena/map.dat/select/code/4/alignment/partial",
                "texts": {"zh-Hans": "红莲之塔", "zh-Hant": "紅蓮之塔"},
            },
        ]
        tr = MenuTranslator(records, "en", "ja")
        for name, ja, en in (
            ("蔡恩拉德酒店", "ツァンラートホテル", "Zahnrad Hotel"),
            ("红莲之塔", "紅蓮の塔", "Carnelia Tower"),
        ):
            source = f"<s28>确定要移动至<C1>{name}</C>吗？"
            self.assertEqual(tr.translate(source, "primary"), f"<s28>Fast Travel to <C1>{en}</C>?")
            self.assertEqual(
                tr.translate(source, "secondary"), f"<s28><C1>{ja}</C>へ移動しますか？"
            )
            self.assertEqual(tr.render(source)["kind"], "layered")
            self.assertIn(ja, tr.render(source)["layers"][0]["text"])
        # The complete confirmation supplies context; a bare homonym does not.
        self.assertEqual(tr.translate("蔡恩拉德酒店", "secondary"), "蔡恩拉德酒店")

    def test_conflicting_or_missing_map_target_is_not_borrowed(self):
        template = record(
            "table/t_text.tbl/TXT_MAPJUMP_CONFIRM_MAPJUMP",
            "前往<C1>%s</C>？",
            "<C1>%s</C>へ？",
            "To <C1>%s</C>?",
        )
        first = record("table/t_mapjump.tbl/MapJumpSpotData/one/name", "地点", "場所一", "Site One")
        for second in (
            record("table/t_mapjump.tbl/MapJumpSpotData/two/name", "地点", "場所二", "Site Two"),
            {"key": "table/t_mapjump.tbl/MapJumpSpotData/two/name", "texts": {"zh-Hans": "地点"}},
        ):
            with self.subTest(second=second):
                tr = MenuTranslator([template, first, second], "en", "ja")
                source = "前往<C1>地点</C>？"
                result = tr.translate(source, "secondary")
                self.assertIn("<C1>地点</C>", result)
                self.assertNotIn("場所一", result)
                self.assertNotIn("場所二", result)


if __name__ == "__main__":
    unittest.main()
