import unittest

from tools.audit_locale_coverage import LANGUAGES, audit


def texts(seed="x"):
    return {language: f"{seed}-{language}" for language in LANGUAGES}


class AuditLocaleCoverageTest(unittest.TestCase):
    def test_separates_complete_records_from_bytecode_fragments_and_conflicts(self):
        first = texts("same")
        second = texts("same")
        second["fr"] = "different-fr"
        missing = texts("table")
        del missing["de"]
        report = audit(
            [
                {"key": "script/a/called/1/assembled_display", "texts": first},
                {"key": "script/a/called/1/assembled_dialogue", "texts": first},
                {"key": "script/a/called/2/assembled_display", "texts": second},
                {"key": "script/a/called/3/arg/1", "texts": texts("bytecode-fragment")},
                {"key": "table/t.tbl/row", "texts": missing},
            ]
        )
        dialogue = report["scopes"]["complete_dialogue"]
        table = report["scopes"]["table_entries"]
        self.assertEqual(dialogue["records"], 2)
        self.assertEqual(dialogue["complete_all_8"], 2)
        self.assertEqual(dialogue["same_source_different_targets"]["source_values"], 7)
        self.assertEqual(table["records"], 1)
        self.assertEqual(table["missing_by_locale"], {"de": 1})
        self.assertTrue(report["not_screen_untranslated_count"])
