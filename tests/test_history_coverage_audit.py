import unittest

from tools.audit_history_dialogue_coverage import _dialogue_groups, _history_candidates


class HistoryCoverageAuditTests(unittest.TestCase):
    def test_proven_display_alias_is_an_official_history_candidate(self):
        base = "script/scena/test.dat/Talk/called/7/"
        entries = [
            {
                "key": base + "control_variant:abc/assembled_dialogue",
                "display_role": "dialogue",
                "texts": {"zh-Hans": "<K3>笑。", "ja": "<K3>クスクス。"},
            },
            {
                "key": base + "control_dialogue_display",
                "display_role": "dialogue",
                "texts": {"zh-Hans": "笑。", "ja": "クスクス。"},
            },
        ]
        self.assertEqual(len(_dialogue_groups(entries)), 1)
        candidates, calls = _history_candidates(entries, {}, "zh-Hans", "ja")
        lookup = ("body", "", "笑。")
        self.assertEqual(candidates[lookup], {("笑。", "クスクス。")})
        self.assertEqual(calls[lookup], {base + "control_dialogue_display"})
