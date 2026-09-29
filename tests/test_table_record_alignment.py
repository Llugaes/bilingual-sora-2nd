import struct
import tempfile
import unittest
from pathlib import Path

from test_tables import ARCHIVES, fpac
from sora_bilingual.localization.tables import build_table_entries
from sora_bilingual.localization.runtime_identity import compile_table_identities


def table(kind, size, rows):
    data = bytearray(88 + size * len(rows))
    struct.pack_into("<4sI64sIIII", data, 0, b"#TBL", 1, kind.encode(), 0, 88, size, len(rows))
    for i, (scalars, strings) in enumerate(rows):
        at = 88 + size * i
        for offset, fmt, value in scalars:
            struct.pack_into("<" + fmt, data, at + offset, value)
        for offset, value in strings.items():
            struct.pack_into("<Q", data, at + offset, len(data))
            data.extend(value.encode() + b"\0")
    return bytes(data)


class TableRecordAlignmentTests(unittest.TestCase):
    def game(self, root, files):
        folder = root / "pac/steam"
        folder.mkdir(parents=True)
        for language, records in files.items():
            (folder / ARCHIVES[language]).write_bytes(fpac(list(records.items())))

    def test_same_category_and_same_text_keep_distinct_achievement_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.game(
                root,
                {
                    language: {
                        "table/t_achievement.tbl": table(
                            "PlayRecordData",
                            40,
                            [
                                (
                                    [(0, "I", 0)],
                                    {8: "", 16: title, 24: f"{language} description {i}", 32: ""},
                                )
                                for i, title in enumerate(titles)
                            ],
                        )
                    }
                    for language, titles in {
                        "zh-Hans": ["同名", "同名"],
                        "en": ["First", "Second"],
                        "ja": ["一", "二"],
                    }.items()
                },
            )
            entries, _ = build_table_entries(root)
            titles = [e for e in entries if e["key"].endswith("/title")]
            self.assertEqual(len(titles), 2)
            self.assertEqual({e["texts"]["en"] for e in titles}, {"First", "Second"})
            models = compile_table_identities(root, entries, "en", "ja", "zh-Hans")
            self.assertEqual(len(models["sources"]["同名"]), 2)
            self.assertEqual(len({r["key"] for r in models["sources"]["同名"]}), 2)

    def test_help_continuations_and_page_changes_do_not_shift_next_topic_entry(self):
        def row(page, title, detail):
            return ([(0, "H", 63), (2, "H", page)], {8: title, 24: "", 40: detail, 48: ""})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.game(
                root,
                {
                    "zh-Hans": {
                        "table/t_help.tbl": table(
                            "HelpIconList",
                            56,
                            [row(1, "攻击力", "物理攻击伤害"), row(1, "防御力", "物理防御")],
                        )
                    },
                    "en": {
                        "table/t_help.tbl": table(
                            "HelpIconList",
                            56,
                            [
                                row(1, "STR", "Physical attack"),
                                row(1, "", "damage"),
                                row(2, "DEF", "Physical defense"),
                            ],
                        )
                    },
                    "ja": {
                        "table/t_help.tbl": table(
                            "HelpIconList",
                            56,
                            [row(1, "攻撃力", "物理攻撃ダメージ"), row(1, "防御力", "物理防御")],
                        )
                    },
                },
            )
            entries, _ = build_table_entries(root)
            match = next(
                (
                    e
                    for e in entries
                    if e["texts"].get("zh-Hans") == "防御力" and e["texts"].get("en") == "DEF"
                ),
                None,
            )
            self.assertIsNotNone(match)
            self.assertTrue(
                any(
                    e["texts"].get("zh-Hans") == "物理攻击伤害"
                    and e["texts"].get("en") == "Physical attack\ndamage"
                    for e in entries
                )
            )

    def test_changed_ordered_structure_does_not_pair_shifted_achievements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.game(
                root,
                {
                    language: {
                        "table/t_achievement.tbl": table(
                            "PlayRecordData",
                            40,
                            [
                                (
                                    [(0, "I", category)],
                                    {8: "", 16: f"{language} {i}", 24: "", 32: ""},
                                )
                                for i, category in enumerate(categories)
                            ],
                        )
                    }
                    for language, categories in {"ja": [0, 1, 0], "en": [0, 0]}.items()
                },
            )
            entries, _ = build_table_entries(root)
            self.assertFalse(any(len(e["texts"]) > 1 for e in entries))

    def test_help_icon_order_change_is_not_silently_zipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.game(
                root,
                {
                    language: {
                        "table/t_help.tbl": table(
                            "HelpIconList",
                            56,
                            [
                                (
                                    [(0, "H", 66), (4, "I", icon)],
                                    {8: f"{language} {icon}", 24: "", 40: "", 48: ""},
                                )
                                for icon in icons
                            ],
                        )
                    }
                    for language, icons in {"ja": [10, 11], "en": [11, 10]}.items()
                },
            )
            entries, audit = build_table_entries(root)
            self.assertEqual(entries, [])
            self.assertTrue(audit["diagnostics"])

    def test_raw_audit_checks_physical_row_even_when_another_row_has_same_text(self):
        from unittest.mock import patch
        from tools.audit_resource_inventory import audit_tables, catalog_inventory

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.game(
                root,
                {
                    language: {
                        "table/t_achievement.tbl": table(
                            "PlayRecordData",
                            40,
                            [
                                (
                                    [(0, "I", 0)],
                                    {
                                        8: "",
                                        16: "同名" if language == "zh-Hans" else str(i),
                                        24: "",
                                        32: "",
                                    },
                                )
                                for i in range(2)
                            ],
                        )
                    }
                    for language in ("zh-Hans", "en")
                },
            )
            entries, audit = build_table_entries(root)
            index, _, _ = catalog_inventory(entries[:1])
            with patch(
                "tools.audit_resource_inventory.build_table_entries",
                return_value=(entries[:1], audit),
            ):
                result = audit_tables(root, ["zh-Hans"], index)
            self.assertEqual(result["counts"]["zh-Hans"]["schema_fields_not_catalogued"], 1)


if __name__ == "__main__":
    unittest.main()
