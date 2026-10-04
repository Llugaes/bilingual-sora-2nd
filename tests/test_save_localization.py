import struct
import unittest

from sora_bilingual.localization.menu_tables import read_section, SCHEMAS
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FormatError


def navi(rows):
    data = bytearray(56 * len(rows))
    for i, (text, start, end) in enumerate(rows):
        at = i * 56
        struct.pack_into("<Q", data, at, 2)
        struct.pack_into("<Q", data, at + 8, len(data))
        data.extend(text.encode() + b"\0")
        for off, value in ((24, start), (40, end)):
            struct.pack_into("<QQ", data, at + off, len(data), 1)
            data.extend(struct.pack("<H", value))
    return data


class SaveLocalizationTests(unittest.TestCase):
    def test_saved_metadata_keeps_its_own_language_after_runtime_source_changes(self):
        entries = [
            {
                "key": "table/t_chapter.tbl/id/title",
                "texts": {
                    "zh-Hans": "第８章“混沌大地”",
                    "ja": "８章「混迷の大地」",
                    "en": "Chapter 8: Land of Turmoil",
                },
            },
            {
                "key": "table/t_place.tbl/id/name",
                "texts": {
                    "zh-Hans": "卢安市・北街区",
                    "ja": "ルーアン市・北街区",
                    "en": "Ruan - North Block",
                },
            },
            {
                "key": "table/t_name.tbl/id/name",
                "texts": {"zh-Hans": "艾丝蒂尔", "ja": "エステル", "en": "Estelle"},
            },
            {
                "key": "table/t_quest.tbl/NaviText/id/title",
                "texts": {
                    "zh-Hans": "将零力场生成器送去各个协会分部",
                    "ja": "各ギルド支部に零力場発生器を届けよう",
                    "en": "Deliver the Zero Field Generators",
                },
            },
        ]
        for current in ("zh-Hans", "ja", "en"):
            tr = MenuTranslator(entries, "ja", "en", current)
            # The production scope must use the language of each saved field,
            # independent of the current runtime table and other saved rows.
            saved = tr.scoped.get("save_summary", tr)
            for entry in entries:
                for text in entry["texts"].values():
                    with self.subTest(current=current, text=text):
                        self.assertEqual(saved.translate(text, "primary"), entry["texts"]["ja"])
                        self.assertEqual(saved.translate(text, "secondary"), entry["texts"]["en"])
            if current != "zh-Hans":
                self.assertEqual(tr.translate("艾丝蒂尔", "primary"), "艾丝蒂尔")

    def test_level_prefix_comes_from_requested_locales(self):
        tr = MenuTranslator(
            [
                {
                    "key": "table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL",
                    "texts": {"fr": "Niv.", "de": "St. ", "es": "Nv."},
                },
                {"texts": {"fr": "Nom", "de": "Name", "es": "Nombre"}},
            ],
            "de",
            "es",
            "fr",
        )
        self.assertEqual(tr.translate(" ·Nom  Niv.39", "primary"), " ·Name  St. 39")
        self.assertEqual(tr.translate(" ·Nom  Niv.39", "secondary"), " ·Nombre  Nv.39")
        self.assertEqual(tr.translate("Unknown Name", "primary"), "Unknown Name")

    def test_saved_aliases_keep_conflicts_and_missing_targets(self):
        entries = [
            {
                "key": "table/t_place.tbl/1/name",
                "texts": {"en": "Gate", "ja": "門", "zh-Hans": "旧城门"},
            },
            {
                "key": "table/t_place.tbl/2/name",
                "texts": {"en": "Gate", "ja": "関所", "zh-Hans": "关卡"},
            },
            {"key": "table/t_name.tbl/1/name", "texts": {"en": "Person", "ja": "人"}},
            {
                "key": "script/old/dialogue",
                "texts": {"en": "Only dialogue", "ja": "对白", "zh-Hans": "对白"},
            },
        ]
        tr = MenuTranslator(entries, "ja", "zh-Hans", "zh-Hans").scoped["save_summary"]
        for source in (
            "Gate",
            "Person",
            "Only dialogue",
            "Player chosen name",
            "2026/10/4 18:14:44",
        ):
            self.assertEqual(tr.translate(source, "primary"), source)
            self.assertEqual(tr.translate(source, "secondary"), source)

    def test_current_language_cannot_choose_between_conflicting_saved_names(self):
        entries = [
            {
                "key": "table/t_name.tbl/1/name",
                "texts": {"en": "Shared", "ja": "甲", "zh-Hans": "角色甲"},
            },
            {
                "key": "table/t_name.tbl/2/name",
                "texts": {"en": "Second", "ja": "Shared", "zh-Hans": "角色乙"},
            },
            {
                "key": "table/t_name.tbl/3/name",
                "texts": {"en": "Ship", "ja": "船", "zh-Hans": "船"},
            },
            {
                "key": "table/t_place.tbl/1/name",
                "texts": {"en": "Ship", "ja": "《船》", "zh-Hans": "《船》"},
            },
        ]
        for current in ("en", "ja", "zh-Hans"):
            saved = MenuTranslator(entries, "ja", "zh-Hans", current).scoped["save_summary"]
            for text in ("Shared", "Ship"):
                for mode in ("primary", "secondary", "annotation"):
                    self.assertEqual(saved.translate(text, mode), text, (current, text, mode))

    def test_navigation_uses_condition_ids_not_chapter_or_row_order(self):
        a = navi([("准备搭船", 18081, 18086), ("交谈", 18086, 18090)])
        b = navi([("Talk", 18086, 18090), ("Board", 18081, 18086)])

        def read(data):
            return read_section(data, ("NaviText", 0, 56, 2), SCHEMAS["NaviText"], 112)

        left, right = read(a), read(b)
        self.assertEqual(len(left), 2)
        self.assertEqual(
            {(v[0]["title"], right[k][0]["title"]) for k, v in left.items()},
            {("准备搭船", "Board"), ("交谈", "Talk")},
        )
        struct.pack_into("<Q", a, 32, 1000000)
        with self.assertRaises(FormatError):
            read(a)

    def test_character_name_table_survives_incomplete_voice_records(self):
        entries = [
            {
                "key": "table/t_name.tbl/id/name",
                "texts": {"zh-Hans": "艾丝蒂尔", "ja": "エステル", "en": "Estelle"},
            },
            {"key": "script/x/voice", "texts": {"zh-Hans": "艾丝蒂尔", "ja": "エステル"}},
        ]
        tr = MenuTranslator(entries, "en", "ja")
        self.assertEqual(tr.translate("艾丝蒂尔", "primary"), "Estelle")
        self.assertEqual(tr.translate("艾丝蒂尔", "secondary"), "エステル")
        self.assertEqual(tr.translate("艾丝蒂尔的日记", "primary"), "艾丝蒂尔的日记")

    def test_save_heading_and_party_keep_difficulty_and_levels(self):
        tr = MenuTranslator(
            [
                {"texts": {"zh-Hans": "第２章“大地翻腾”", "ja": "２章「荒ぶる大地」"}},
                {"texts": {"zh-Hans": "艾丝蒂尔", "ja": "エステル"}},
            ],
            "zh-Hans",
            "ja",
        )
        self.assertEqual(
            tr.translate("第２章“大地翻腾”\u3000\u3000\u3000\u3000 ＜Nightmare＞", "secondary"),
            "２章「荒ぶる大地」\u3000\u3000\u3000\u3000 ＜Nightmare＞",
        )
        self.assertEqual(
            tr.translate("\u3000·艾丝蒂尔\u3000\u3000\u3000Lv.39", "secondary"),
            "\u3000·エステル\u3000\u3000\u3000Lv.39",
        )


if __name__ == "__main__":
    unittest.main()
