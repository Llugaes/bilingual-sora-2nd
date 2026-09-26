import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sora_bilingual.app.native_settings import read_control, update_control, valid_keyboard_keys


class NativeSettingsTests(unittest.TestCase):
    def test_changing_mode_preserves_the_migrated_controller_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "control.json"
            path.write_text(
                json.dumps(
                    {
                        "interaction": "annotation",
                        "hotkeys": {
                            "annotation": {"gamepad": {"buttons": [1]}},
                            "language_hold": {"gamepad": {"buttons": [2]}},
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = update_control({"interaction": "language_hold"}, path)
            self.assertEqual(result["switch_binding"]["gamepad"], {"buttons": [1]})

    def test_first_run_saves_only_ui_language_and_never_asks_source_language(self):
        from sora_bilingual.app.native_settings import configure_first_run, QDialog

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
        ):
            path = Path(temp) / "control.json"
            ui_dialog = MagicMock()
            dialog_type.return_value = ui_dialog
            ui_dialog.exec.return_value = QDialog.DialogCode.Accepted
            ui_dialog.textValue.return_value = "English"
            self.assertTrue(configure_first_run(path))
            self.assertEqual(read_control(path)["ui_language"], "en")
            self.assertTrue(
                json.loads(path.read_text(encoding="utf-8"))["language_defaults_pending"]
            )
            dialog_type.assert_called_once()
            saved = path.read_bytes()
            self.assertTrue(configure_first_run(path))
            self.assertEqual(path.read_bytes(), saved)
            dialog_type.assert_called_once()

    def test_pending_defaults_survive_unrelated_save_and_clear_on_real_language_change(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "control.json"
            path.write_text(
                json.dumps(
                    {
                        "primary": "zh-Hans",
                        "secondary": "ja",
                        "game_language": "zh-Hans",
                        "language_defaults_pending": True,
                    }
                ),
                encoding="utf-8",
            )
            update_control({"line_gap": 7}, path)
            self.assertTrue(
                json.loads(path.read_text(encoding="utf-8"))["language_defaults_pending"]
            )
            # Settings forms can include both combo values for a style save;
            # equal values must not be treated as an explicit language choice.
            update_control({"primary": "zh-Hans", "secondary": "ja", "ruby_gap": 2}, path)
            self.assertTrue(
                json.loads(path.read_text(encoding="utf-8"))["language_defaults_pending"]
            )
            update_control({"primary": "en"}, path)
            self.assertNotIn(
                "language_defaults_pending", json.loads(path.read_text(encoding="utf-8"))
            )

    def test_existing_empty_control_is_not_marked_as_a_new_user(self):
        from sora_bilingual.app.native_settings import configure_first_run

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
        ):
            path = Path(temp) / "control.json"
            path.write_text("{}", encoding="utf-8")
            self.assertTrue(configure_first_run(path))
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")
            dialog_type.assert_not_called()

    def test_first_run_cancel_does_not_create_or_rewrite_configuration(self):
        from sora_bilingual.app.native_settings import configure_first_run, QDialog

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
        ):
            path = Path(temp) / "control.json"
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.assertFalse(configure_first_run(path))
            self.assertFalse(path.exists())
            path.write_text('{"enabled": false}', encoding="utf-8")
            saved = path.read_bytes()
            self.assertTrue(configure_first_run(path))
            self.assertEqual(path.read_bytes(), saved)

    def test_existing_explicit_ui_language_is_not_reset_or_prompted(self):
        from sora_bilingual.app.native_settings import configure_first_run

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
        ):
            path = Path(temp) / "control.json"
            path.write_text('{"ui_language": "en"}', encoding="utf-8")
            saved = path.read_bytes()
            self.assertTrue(configure_first_run(path))
            self.assertEqual(path.read_bytes(), saved)
            dialog_type.assert_not_called()

    def test_update_preserves_backend_fields_and_unknown_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "native-control.json"
            original = {
                "sources": ["backend source"],
                "stop": False,
                "backend_token": "keep",
                "hotkey": {"keyboard": ["F8"], "gamepad": {"guid": "pad", "buttons": [1, 2]}},
            }
            path.write_text(json.dumps(original), encoding="utf-8")
            updated = update_control(
                {
                    "primary": "zh-Hans",
                    "interaction": "annotation",
                    "hotkey": {"keyboard": ["CTRL", "F10"]},
                },
                path,
            )
            disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(disk["sources"], original["sources"])
            self.assertFalse(disk["stop"])
            self.assertEqual(disk["backend_token"], "keep")
            self.assertEqual(disk["hotkey"]["gamepad"], original["hotkey"]["gamepad"])
            self.assertEqual(updated["hotkey"]["keyboard"], ["CTRL", "F10"])

    def test_keyboard_validation_rejects_partial_modifier_combo(self):
        self.assertEqual(valid_keyboard_keys(["ctrl", "f10"]), ["CTRL", "F10"])
        self.assertIsNone(valid_keyboard_keys(["CTRL", "MEDIA_PLAY"]))

    def test_backend_owned_fields_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "native-control.json"
            with self.assertRaises(ValueError):
                update_control({"stop": True}, path)
            with self.assertRaises(ValueError):
                update_control({"sources": []}, path)

    def test_read_control_fills_only_missing_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "native-control.json"
            path.write_text(json.dumps({"primary": "en", "sources": ["x"]}), encoding="utf-8")
            result = read_control(path)
            self.assertEqual(result["primary"], "en")
            self.assertEqual(result["secondary"], "ja")
            self.assertEqual(result["sources"], ["x"])


if __name__ == "__main__":
    unittest.main()
