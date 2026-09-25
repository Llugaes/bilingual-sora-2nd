import unittest

from sora_bilingual.legacy.display_policy import DisplayPolicy, DisplayState


class DisplayPolicyTests(unittest.TestCase):
    def test_annotation_starts_as_primary_with_small_secondary_annotation_and_toggles(self):
        policy = DisplayPolicy("ja", "zh-Hans", "annotation")
        self.assertEqual(
            policy.state(),
            DisplayState("ja", "zh-Hans", "annotation", True, "annotation"),
        )
        self.assertEqual(policy.advance(held=False, pressed=True).render_mode, "primary")
        self.assertEqual(
            policy.advance(held=False, pressed=False, released=True).render_mode, "primary"
        )
        self.assertEqual(policy.advance(held=False, pressed=True).render_mode, "annotation")

    def test_language_toggle_starts_primary_and_switches_on_each_press_for_any_languages(self):
        policy = DisplayPolicy("fr", "ko", "language_toggle")
        self.assertEqual(policy.state().render_mode, "primary")
        self.assertEqual(policy.advance(held=True, pressed=True).render_mode, "secondary")
        self.assertEqual(
            policy.advance(held=False, pressed=False, released=True).render_mode, "secondary"
        )
        self.assertEqual(policy.advance(held=False, pressed=True).render_mode, "primary")

    def test_language_hold_uses_secondary_only_while_effectively_held(self):
        policy = DisplayPolicy("zh-Hant", "de", "language_hold")
        self.assertEqual(policy.state().render_mode, "primary")
        self.assertEqual(policy.advance(held=True, pressed=True).render_mode, "secondary")
        self.assertEqual(policy.advance(held=True, pressed=False).render_mode, "secondary")
        self.assertEqual(
            policy.advance(held=False, pressed=False, released=True).render_mode, "primary"
        )

    def test_switching_interaction_resets_language_selection_to_primary(self):
        policy = DisplayPolicy("en", "es", "language_toggle")
        policy.advance(held=False, pressed=True)
        self.assertEqual(policy.state().render_mode, "secondary")
        self.assertEqual(policy.set_interaction("language_hold").render_mode, "primary")
        self.assertEqual(
            policy.set_interaction("annotation", annotation_enabled=False).render_mode, "primary"
        )

    def test_invalid_interaction_and_empty_language_are_rejected(self):
        with self.assertRaises(ValueError):
            DisplayPolicy("ja", "en", "unknown")
        with self.assertRaises(ValueError):
            DisplayPolicy("", "en")


if __name__ == "__main__":
    unittest.main()
