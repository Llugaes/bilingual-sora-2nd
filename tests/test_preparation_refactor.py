"""Boundary fixtures for behavior-preserving preparation refactors."""

import unittest
from unittest.mock import patch

from sora_bilingual.localization.runtime_identity import compile_table_identities
from tests.test_runtime_identity import text_table


class TableSelectionTests(unittest.TestCase):
    def test_needed_table_selection_matches_slash_boundary_prefixes(self):
        entries = [
            {"key": key, "texts": {"en": "same", "ja": "訳"}}
            for key in (
                "table/t_text.tbl/TXT",
                "table/deep/dir/t_text.tbl/TXT",
                "table/t_other.tbl/Section/group:1/name",
                "table/t_direct.tbl",
            )
        ]
        entries += [
            {"key": "table/t_resolved.tbl/TXT", "texts": {"en": "resolved", "ja": "対応済み"}},
            {"key": "table/t_book.tbl/TXT", "texts": {"en": "same", "ja": "訳"}, "book_pages": {}},
            {"key": "table/t_blank.tbl/TXT", "texts": {"en": " ", "ja": "訳"}},
            {"key": "table/t_unpaired.tbl/TXT", "texts": {"en": "same"}},
            {"key": "script/table/t_script.tbl/TXT", "texts": {"en": "same", "ja": "訳"}},
        ]
        logical = dict.fromkeys(
            (
                "table/t_text.tbl",
                "table/deep/dir/t_text.tbl",
                "table/t_other.tbl",
                "table/t_text.tbl_extra",
                "table/deep/dir/t_text",
                "table/dir/t_text.tbl",
                "table/t_direct.tbl",
                "table/t_resolved.tbl",
                "table/t_book.tbl",
                "table/t_blank.tbl",
                "table/t_unpaired.tbl",
                "script/table/t_script.tbl",
            )
        )
        logical = {path: "actual/" + path for path in logical}
        needed = entries[:4]
        expected = [
            actual
            for path, actual in logical.items()
            if any(entry["key"].startswith(path + "/") for entry in needed)
        ]
        reads = []
        closed = []

        class Archive:
            def __init__(self, *_):
                pass

            def read(self, actual):
                reads.append(actual)
                return text_table((("TXT", "same"),))

            def close(self):
                closed.append(True)

        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", Archive),
            patch("sora_bilingual.localization.tables._logical_tables", return_value=logical),
        ):
            result = compile_table_identities(
                "unused",
                entries,
                "en",
                "ja",
                "en",
                resolved_pairs={"resolved": ("resolved", "対応済み")},
            )
        self.assertEqual(reads, expected)
        self.assertEqual(closed, [True])
        self.assertEqual(
            set(result["models"]), {"table/t_text.tbl/TXT", "table/deep/dir/t_text.tbl/TXT"}
        )
