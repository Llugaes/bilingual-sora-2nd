"""Exercise the actual settings form against isolated control/status files."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication
from sora_bilingual.app.native_settings import NativeSettingsWindow, update_control
from sora_bilingual.config.native_config import (
    read_config,
    write_config,
    update_config,
    apply_detected_game_language,
)


class PrimaryFollowUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.control = Path(self.temp.name) / "control.json"
        self.status = self.control.with_name("status.json")
        write_config(
            {
                "game_language": "en",
                "primary": "en",
                "secondary": "ja",
                "ui_language": "zh-Hans",
                "sources": ["keep"],
                "line_gap": 6,
            },
            self.control,
        )
        self.window = NativeSettingsWindow(self.control, self.status)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_default_only_secondary_is_editable_and_primary_cannot_be_changed(self):
        self.assertFalse(self.window.experimental_primary.isChecked())
        self.assertTrue(self.window.primary.isHidden())
        self.assertFalse(self.window.primary.isEnabled())
        self.assertFalse(self.window.follow_game_primary.isHidden())
        self.assertFalse(self.window.experimental_primary_note.isHidden())
        self.assertEqual(self.window.secondary.findData("en"), -1)
        before = self.control.read_bytes()
        self.window.primary.setCurrentIndex(self.window.primary.findData("de"))
        self.assertEqual(self.control.read_bytes(), before)
        self.assertEqual(read_config(self.control)["primary"], "en")

    def test_explicit_experimental_switch_unlocks_primary_and_shows_warning(self):
        self.window.experimental_primary.setChecked(True)
        self.assertFalse(self.window.primary.isHidden())
        self.assertTrue(self.window.primary.isEnabled())
        self.assertFalse(self.window.experimental_primary_note.isHidden())
        self.assertIn("实验性质", self.window.experimental_primary_note.text())
        self.window.primary.setCurrentIndex(self.window.primary.findData("de"))
        self.assertEqual(read_config(self.control)["primary"], "de")
        self.window.experimental_primary.setChecked(False)
        self.assertEqual(read_config(self.control)["primary"], "en")
        self.assertTrue(self.window.primary.isHidden())
        self.assertEqual(self.window.secondary.findData("en"), -1)
        self.assertEqual(read_config(self.control)["sources"], ["keep"])

    def test_backend_source_swap_refreshes_the_open_form_without_saving_stale_choices(self):
        update_config(lambda latest: apply_detected_game_language(latest, "ja"), self.control)
        self.status.write_text(
            json.dumps(
                {
                    "running": True,
                    "updated_at": time.time(),
                    "detected_game_language": "ja",
                    "source_language_status": "matched",
                }
            ),
            encoding="utf-8",
        )
        self.window.refresh_status()
        self.assertEqual(self.window.primary.currentData(), "ja")
        self.assertEqual(self.window.secondary.currentData(), "en")
        self.assertEqual(self.window.secondary.findData("ja"), -1)
        self.assertEqual(self.window.follow_game_primary.text(), "日本語")
        self.window.line_gap.setValue(7)
        saved = read_config(self.control)
        self.assertEqual((saved["primary"], saved["secondary"]), ("ja", "en"))
        self.assertEqual(saved["line_gap"], 7)

    def test_unconfirmed_or_stale_source_is_not_presented_as_current_game_language(self):
        self.status.write_text(
            json.dumps(
                {"running": False, "updated_at": time.time(), "detected_game_language": "de"}
            ),
            encoding="utf-8",
        )
        self.window.refresh_status()
        self.assertIn("等待检测", self.window.follow_game_primary.text())


if __name__ == "__main__":
    unittest.main()
