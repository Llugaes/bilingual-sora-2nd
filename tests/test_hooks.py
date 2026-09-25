import unittest
from sora_bilingual.game.hooks import signature_matches, script_source


class HookTests(unittest.TestCase):
    def test_ambiguity_including_overlaps(self):
        self.assertEqual(signature_matches(b"\xaa\xaa\xaa", "aa aa"), [0, 1])

    def test_wildcard_includes_newline(self):
        self.assertEqual(signature_matches(b"\xaa\x0a\xbb", "aa ?? bb"), [0])

    def test_literal_regex_metacharacter(self):
        self.assertEqual(signature_matches(b"\x2e\x2a\xff", "2e 2a ??"), [0])


if __name__ == "__main__":
    unittest.main()
