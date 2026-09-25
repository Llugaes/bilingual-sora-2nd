import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sora_bilingual.legacy.ui import OverlayWindow, SettingsWindow, create_ui


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_defaults_and_change_signal(self):
        settings = SettingsWindow(
            languages=[("zh-Hans", "简体中文"), ("ja", "日本語"), ("en", "English")]
        )
        self.assertEqual(settings.primary.currentData(), "zh-Hans")
        self.assertEqual(settings.secondary.currentData(), "ja")
        updates = []
        settings.settings_changed.connect(updates.append)
        settings.font_size.setValue(36)
        self.assertEqual(updates[-1]["font_size"], 36)

    def test_overlay_applies_two_line_mode_and_game_geometry(self):
        overlay = OverlayWindow({"font_size": 20, "width_percent": 50, "bottom_offset_percent": 10})
        overlay.set_game_rect(100, 200, 1000, 800)
        overlay.set_lines("Primary subtitle", "Secondary subtitle")
        self.assertEqual(overlay.width(), 500)
        self.assertFalse(overlay.primary_label.isVisible())  # parent hidden before active
        overlay.set_active(True)
        self.assertEqual(overlay.primary_label.text(), "Primary subtitle")
        overlay.apply_config({"display_mode": "secondary_only"})
        self.assertTrue(overlay.primary_label.isHidden())

    def test_create_ui_wires_settings_to_overlay(self):
        settings, overlay = create_ui(config={"font_size": 24})
        settings.font_size.setValue(31)
        self.assertEqual(overlay.config["font_size"], 31)
