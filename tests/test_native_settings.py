import json
import tempfile
import unittest
from pathlib import Path

from native_settings import read_control, update_control, valid_keyboard_keys


class NativeSettingsTests(unittest.TestCase):
    def test_update_preserves_backend_fields_and_unknown_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "native-control.json"
            original = {
                "sources": ["backend source"], "stop": False, "backend_token": "keep",
                "hotkey": {"keyboard": ["F8"], "gamepad": {"guid": "pad", "buttons": [1, 2]}},
            }
            path.write_text(json.dumps(original), encoding="utf-8")
            updated = update_control({"primary": "zh-Hans", "interaction": "annotation", "hotkey": {"keyboard": ["CTRL", "F10"]}}, path)
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
