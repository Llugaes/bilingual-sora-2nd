import json
import unittest
from tools.identity_check import same_pair


class IdentityAuditTests(unittest.TestCase):
    def test_cached_and_fresh_pairs_have_identical_audit_results(self):
        expected = ["Texte", "Text"]
        for actual in (tuple(expected), json.loads(json.dumps(expected))):
            self.assertTrue(same_pair(actual, expected))
            self.assertFalse(same_pair(actual, ["Text", "Texte"]))
        self.assertFalse(same_pair(None, expected))
        self.assertFalse(same_pair([], expected))
