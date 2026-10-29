import unittest

from tools.audit_history_dialogue_coverage import passed_targets


class HistoryAuditGateTests(unittest.TestCase):
    def test_existing_official_resource_absence_is_separate_from_runtime_failure(self):
        report = {
            "id_counts": {"missing_resource_pair": 8, "id_final_render_passed": 63248},
            "history_counts": {"history_exact_render_passed": 1, "history_fallback_selected": 1},
        }
        self.assertTrue(passed_targets([report]))
        for reason in (
            "history_exact_nonofficial",
            "history_final_render_failed",
            "history_conflict_unresolved",
        ):
            self.assertFalse(passed_targets([{**report, "history_counts": {reason: 1}}]))
        self.assertFalse(passed_targets([{**report, "id_counts": {"id_runtime_missing": 1}}]))


if __name__ == "__main__":
    unittest.main()
