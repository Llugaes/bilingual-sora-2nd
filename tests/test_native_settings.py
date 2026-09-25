import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_first_run_saves_selected_pair_and_preserves_it_on_relaunch(self):
        from sora_bilingual.app.native_settings import configure_first_run, QDialog
        from sora_bilingual.config.locales import LOCALES

        for source in LOCALES:
            with (
                tempfile.TemporaryDirectory() as temp,
                patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
            ):
                path = Path(temp) / "control.json"
                path.write_text('{"enabled": false}', encoding="utf-8")
                dialog = dialog_type.return_value
                dialog.exec.return_value = QDialog.DialogCode.Accepted
                secondary = "en" if source == "ja" else "ja"
                dialog.textValue.return_value = (
                    f"{LOCALES[source].name} → {LOCALES[secondary].name}"
                )
                self.assertTrue(configure_first_run(path))
                config = read_control(path)
                self.assertEqual(config["primary"], source)
                self.assertEqual(config["game_language"], source)
                self.assertEqual(config["secondary"], secondary)
                self.assertFalse(config["enabled"])
                update_control({"primary": "de", "secondary": "fr"}, path)
                saved = path.read_bytes()
                self.assertTrue(configure_first_run(path))
                self.assertEqual(path.read_bytes(), saved)
                dialog.exec.assert_called_once()

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
            self.assertFalse(configure_first_run(path))
            self.assertEqual(path.read_bytes(), saved)

    def test_existing_partial_language_config_is_not_reset_or_prompted(self):
        from sora_bilingual.app.native_settings import configure_first_run

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("sora_bilingual.app.native_settings.QInputDialog") as dialog_type,
        ):
            path = Path(temp) / "control.json"
            path.write_text('{"primary": "en"}', encoding="utf-8")
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
