import unittest

from tools.audit_table_strings import classify


class TableStringAuditTests(unittest.TestCase):
    def test_new_ascii_only_localized_field_remains_unresolved(self):
        fields = {("table/new.tbl", "NewText", 0, 8): {"ja": ["PLAY"], "en": ["START"]}}
        result = classify(fields, {"classified": [], "all_classified": True})
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["unresolved_different_fields"]), 1)

    def test_placeholder_rule_cannot_hide_a_new_word(self):
        key = ("table/t_skill.tbl", "SkillParam", 0, 160)
        evidence = {"classified": [], "all_classified": True}
        self.assertTrue(classify({key: {"ja": ["－－－"], "en": ["---"]}}, evidence)["passed"])
        self.assertFalse(classify({key: {"ja": ["能力"], "en": ["Ability"]}}, evidence)["passed"])

    def test_changed_native_evidence_does_not_pass(self):
        key = ("table/t_evtable.tbl", "EventTableData", 0, 32)
        result = classify(
            {key: {"ja": ["Title"], "en": ["Other title"]}},
            {"classified": [], "all_classified": False},
        )
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
