import unittest
from sora_bilingual.legacy.core import Catalog, Presentation, display_text


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog(
            {
                "version": 1,
                "entries": [
                    {
                        "key": "a",
                        "texts": {"zh-Hans": "早上好。", "ja": "おはよう。", "en": "Good morning."},
                    },
                    {"key": "b", "texts": {"zh-Hans": "好", "ja": "はい"}},
                    {"key": "c", "texts": {"zh-Hans": "好", "ja": "いいよ"}},
                ],
            }
        )

    def test_free_pair(self):
        pair, state = self.catalog.lookup("早上好。", "en", "ja")
        self.assertEqual(pair, ("Good morning.", "おはよう。"))
        self.assertEqual(state, "matched")

    def test_ambiguous_is_never_guessed(self):
        self.assertEqual(self.catalog.lookup("好", "zh-Hans", "ja"), (None, "ambiguous"))

    def test_live_toggle_and_language_switch(self):
        state = Presentation(self.catalog, {})
        self.assertEqual(state.update("早上好。"), ("早上好。", "おはよう。"))
        state.config["overlay_enabled"] = False
        self.assertEqual(state.lines(), ("", ""))
        state.config.update(overlay_enabled=True, primary_language="en")
        self.assertEqual(state.lines(), ("Good morning.", "おはよう。"))

    def test_no_stale_translation_after_unknown_line(self):
        state = Presentation(self.catalog, {})
        state.update("早上好。")
        self.assertEqual(state.update("未知对白"), ("", ""))

    def test_cleaning_preserves_words_and_numbers(self):
        self.assertEqual(display_text("<color>r2d2 has 100 HP.</color>"), "r2d2 has 100 HP.")

    def test_markup_whitespace_match(self):
        self.assertEqual(
            self.catalog.lookup("<c>早上\n好。</c>", "en", "ja")[0], ("Good morning.", "おはよう。")
        )


if __name__ == "__main__":
    unittest.main()
