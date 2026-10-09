import unittest

from sora_bilingual.localization.menu_text import MenuTranslator


class HelpTitleScopeTests(unittest.TestCase):
    def entry(self, key, target="Tips owner", source="Shared"):
        return {"key": key, "texts": {"en": source, "ja": target}}

    def test_complete_title_family_is_separate_from_bodies_names_and_viewer(self):
        rows = [
            self.entry("table/t_tips.tbl/sha256:tips/title"),
            self.entry("table/t_help.tbl/sha256:help/title", "Help owner", "Help"),
            self.entry("table/t_help.tbl/HelpPage/sha256:page/title", "Page owner", "Page"),
            self.entry("table/t_tips.tbl/sha256:tips/body", "Body owner"),
            self.entry("table/t_name.tbl/sha256:name/name", "Actor owner"),
            self.entry("table/t_viewer.tbl/sha256:viewer/title", "Viewer owner"),
        ]
        tr = MenuTranslator(rows, "en", "ja", "en")
        # Names cannot override conflicting complete records globally. The
        # exact title scope still resolves its own complete record.
        self.assertNotIn("Shared", tr.pairs)
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(tr.translate("Shared", mode), "Shared")
        actor = MenuTranslator([rows[4]], "en", "ja", "en")
        self.assertEqual(actor.pairs["Shared"], ("Shared", "Actor owner"))
        self.assertEqual(tr.scoped["tips_title"].pairs["Shared"], ("Shared", "Tips owner"))
        self.assertEqual(tr.scoped["note_help_title"].pairs["Shared"], ("Shared", "Tips owner"))
        self.assertIn("Help", tr.scoped["note_help_title"].pairs)
        self.assertNotIn("Page", tr.scoped["note_help_title"].pairs)
        self.assertNotIn("Help", tr.scoped["tips_title"].pairs)

    def test_real_help_tips_conflict_blocks_shared_list_but_not_tips_pane(self):
        tr = MenuTranslator(
            [
                self.entry("table/t_tips.tbl/sha256:tips/title"),
                self.entry("table/t_help.tbl/sha256:help/title", "Different Help owner"),
            ],
            "en",
            "ja",
            "en",
        )
        self.assertNotIn("Shared", tr.pairs)
        self.assertNotIn("Shared", tr.scoped["note_help_title"].pairs)
        self.assertIn("Shared", tr.scoped["tips_title"].pairs)

    def test_tips_record_conflicts_and_missing_target_remain_denied(self):
        for conflicting in [
            self.entry("table/t_tips.tbl/sha256:second/title", "Another owner"),
            {"key": "table/t_tips.tbl/sha256:missing/title", "texts": {"en": "Shared"}},
        ]:
            tr = MenuTranslator(
                [self.entry("table/t_tips.tbl/sha256:first/title"), conflicting], "en", "ja", "en"
            )
            for scope in ("note_help_title", "tips_title"):
                self.assertNotIn("Shared", tr.scoped[scope].pairs)

    def test_raw_tips_reader_keeps_conditions_and_rejects_out_of_bounds_array(self):
        from tools.audit_title_name_families import raw_tips
        import struct

        def data(condition, pointer=None):
            raw = bytearray(146)
            raw[:4] = b"#TBL"
            struct.pack_into("<I", raw, 4, 1)
            raw[8:21] = b"TipsTableData"
            struct.pack_into("<III", raw, 76, 88, 56, 1)
            struct.pack_into("<Q", raw, 96, 144 if pointer is None else pointer)
            struct.pack_into("<I", raw, 104, 1)
            for at in (112, 128, 136):
                struct.pack_into("<Q", raw, at, 144)
            struct.pack_into("<H", raw, 144, condition)
            # Zero low byte gives a valid empty selector/title/body.
            return bytes(raw)

        self.assertNotEqual(set(raw_tips(data(256))), set(raw_tips(data(512))))
        with self.assertRaises(ValueError):
            raw_tips(data(256, 145))
