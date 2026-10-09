"""Exact physical description variants when primary equals the source."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator


class SourcePrimaryDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(
            (
                Path(__file__).parent / "fixtures/r31-source-primary-description-padding.json"
            ).read_text("utf-8")
        )["rows"]

    def test_real_padded_and_unpadded_records_keep_source_and_complete_secondary(self):
        for source in LANGUAGES:
            for secondary in LANGUAGES:
                if secondary == source:
                    continue
                tr = MenuTranslator(self.rows, source, secondary, source)
                for row in self.rows:
                    raw = row["texts"][source]
                    for value in (raw, raw.rstrip(" \t")):
                        with self.subTest(source=source, secondary=secondary, text=value):
                            self.assertEqual(tr.details.render(value, "primary")["text"], value)
                            targets = {
                                candidate["texts"][secondary]
                                for candidate in self.rows
                                if candidate["texts"][source] == value
                                or candidate["texts"][source].rstrip(" \t") == value
                            }
                            # The same source cannot distinguish records whose
                            # targets differ only in trailing layout padding.
                            # The result must be one complete physical target.
                            self.assertIn(tr.details.render(value, "secondary")["text"], targets)

    def test_existing_japanese_chinese_outputs_do_not_change(self):
        tr = MenuTranslator(self.rows, "ja", "zh-Hans", "en")
        for row in self.rows:
            for value in (row["texts"]["en"], row["texts"]["en"].rstrip(" \t")):
                self.assertEqual(tr.details.render(value, "primary")["text"], row["texts"]["ja"])
                self.assertEqual(
                    tr.details.render(value, "secondary")["text"], row["texts"]["zh-Hans"]
                )

    def test_real_translation_conflict_still_rejects_complete_body(self):
        # A deliberately conflicting negative, separate from unchanged positives.
        conflict = deepcopy(self.rows[-1])
        conflict["key"] = "table/t_item.tbl/test_conflict/description"
        conflict["texts"]["zh-Hans"] = "不同的完整含义。"
        tr = MenuTranslator([*self.rows, conflict], "en", "zh-Hans", "en")
        source = self.rows[-1]["texts"]["en"].rstrip(" \t")
        self.assertEqual(tr.details.render(source, "secondary")["text"], source)


if __name__ == "__main__":
    unittest.main()
