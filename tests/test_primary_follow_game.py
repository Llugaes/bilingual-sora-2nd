"""Primary follows the confirmed source; manual override is opt-in only.

The backend fixture runs the production loop and replaces OS/resource/build
boundaries. It is separate from actual game verification.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sora_bilingual.config import native_config as config
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.app.native_settings import update_control
from tests.test_runtime_source_switch import BackendFixture
from sora_bilingual.game import native_probe as probe


class PrimaryFollowGameTests(unittest.TestCase):
    def synchronize(self, values, source):
        return config.apply_detected_game_language(config.normalize_config(values), source)

    def test_normal_start_uses_confirmed_game_primary_and_preserves_secondary(self):
        for source in LANGUAGES:
            secondary = "en" if source == "ja" else "ja"
            case = BackendFixture(source, settings={"primary": "zh-Hans", "secondary": secondary})
            reader = SimpleNamespace(read=lambda *_: [], close=lambda: None)
            with (
                self.subTest(source=source),
                patch.object(probe, "RuntimeTextTableReader", return_value=reader),
            ):
                case.run(lambda c: c.exited.set())
                self.assertEqual(case.attached["primary"], source)
                self.assertEqual(case.builds[0]["primary"], source)
                self.assertEqual(case.saved["game_language"], source)
                self.assertNotEqual(case.attached["primary"], case.attached["secondary"])

    def test_collision_swaps_and_third_language_preserves_secondary_in_backend(self):
        for target, expected_secondary in [("ja", "zh-Hans"), ("en", "ja")]:
            case = BackendFixture("zh-Hans", settings={"primary": "zh-Hans", "secondary": "ja"})

            def step(c):
                c.source = target
                if c.loads:
                    c.exited.set()

            reader = SimpleNamespace(read=lambda *_: [], close=lambda: None)
            with (
                self.subTest(target=target),
                patch.object(probe, "RuntimeTextTableReader", return_value=reader),
            ):
                case.run(step)
                self.assertEqual(case.loads[-1][0]["primary"], target)
                self.assertEqual(case.loads[-1][0]["secondary"], expected_secondary)
                self.assertEqual(case.saved["primary"], target)
                self.assertEqual(case.saved["secondary"], expected_secondary)

    def test_every_supported_pair_source_transition_is_deterministic(self):
        for before in LANGUAGES:
            for secondary in LANGUAGES:
                if secondary == before:
                    continue
                for after in LANGUAGES:
                    with self.subTest(before=before, secondary=secondary, after=after):
                        values = {
                            "game_language": before,
                            "primary": before,
                            "secondary": secondary,
                            "line_gap": 7,
                            "annotation_scale": 0.8,
                            "backend_token": "preserved",
                        }
                        result = self.synchronize(values, after)
                        self.assertEqual(result["primary"], after)
                        self.assertEqual(
                            result["secondary"], before if after == secondary else secondary
                        )
                        self.assertEqual(result["game_language"], after)
                        self.assertEqual(result["line_gap"], 7)
                        self.assertEqual(result["annotation_scale"], 0.8)
                        self.assertEqual(result["backend_token"], "preserved")
                        self.assertEqual(self.synchronize(result, after), result)

    def test_manual_override_is_disabled_by_default_and_strictly_boolean(self):
        result = config.normalize_config(
            {"game_language": "en", "primary": "ja", "secondary": "zh-Hans"}
        )
        self.assertIs(result["experimental_primary"], False)
        self.assertEqual(result["primary"], "en")
        for invalid in ("false", "true", 0, 1, None, []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                config.normalize_config({"experimental_primary": invalid})

    def test_ui_cannot_enable_override_without_the_experimental_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            config.write_config({"game_language": "en", "primary": "en", "secondary": "ja"}, path)
            after = update_control({"primary": "de"}, path)
            self.assertEqual(after["primary"], "en")
            self.assertIs(after["experimental_primary"], False)
            manual = update_control({"experimental_primary": True, "primary": "de"}, path)
            self.assertEqual(manual["primary"], "de")
            automatic = update_control({"experimental_primary": False}, path)
            self.assertEqual(automatic["primary"], "en")
            self.assertEqual(automatic["secondary"], "ja")


if __name__ == "__main__":
    unittest.main()
