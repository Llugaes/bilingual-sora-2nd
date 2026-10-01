"""Offline handbook interactions: use the real controller, never attach to a game."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sora_bilingual.app.native_overlay import OverlayController, STYLE
from sora_bilingual.app.handbook import ASSETS, artwork
from sora_bilingual.config.native_config import write_config


class HandbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.control = Path(self.temp.name) / "control.json"
        write_config({"ui_language": "zh-Hans"}, self.control)
        self.controller = OverlayController(
            self.control,
            self.control.with_name("status.json"),
            start_timers=False,
            auto_connect=False,
        )
        self.controller.panel.settings._status_timer.stop()
        self.controller.panel.settings._capture_timer.stop()

    def tearDown(self):
        c = self.controller
        c.hide_interface()
        c.tray.hide()
        c.panel.deleteLater()
        c.bar.deleteLater()
        c.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_badges_follow_release_state_not_opening_the_panel(self):
        c = self.controller
        page = c.panel.settings.updates
        c.expand()
        original = self.control.read_bytes()
        self.assertEqual(c.panel.update_button.text(), "更新")
        self.assertFalse(c.bar.open_button._notice)
        page.service.available = "v9.0.0"
        page.service.release = {"tag_name": "v9.0.0", "name": "Release 9"}
        page.refresh(False)
        self.assertEqual(c.panel.update_button.text(), "新版本")
        self.assertTrue(c.bar.open_button._notice)
        with patch.object(page.service, "tick") as tick:
            c.panel.update_button.click()
            self.app.processEvents()
            self.assertTrue(c.panel.update_popup.isVisible())
            self.assertIn("9.0.0", page.available_version.text())
            self.assertEqual(page.release_title.text(), "Release 9")
            tick.assert_not_called()
            page.check.click()
            tick.assert_called_once_with(manual=True)
        QTest.keyClick(page.check, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(c.panel.update_popup.isVisible())
        self.assertTrue(c.panel.isVisible())
        self.assertTrue(c.bar.open_button._notice)
        c.panel.update_button.click()
        c.bar.minimize_button.click()
        self.assertFalse(c.panel.update_popup.isVisible())
        c.tray.contextMenu().actions()[0].trigger()
        self.assertTrue(c.panel.isVisible())
        self.assertTrue(c.bar.open_button._notice)
        page.service.available = None
        page.refresh(False)
        self.assertEqual(c.panel.update_button.text(), "更新")
        self.assertFalse(c.bar.open_button._notice)
        self.assertEqual(self.control.read_bytes(), original)

    def test_close_and_minimize_hide_but_only_tray_exit_stops_backend(self):
        c = self.controller
        original = self.control.read_bytes()
        with patch("sora_bilingual.game.tool_shutdown.shutdown") as shutdown:
            for hide in (
                c.panel.close,
                c.panel.hide_button.click,
                c.bar.close,
                c.bar.minimize_button.click,
            ):
                c.expand()
                hide()
                c.tick()
                self.assertFalse(c.bar.isVisible())
                self.assertFalse(c.panel.isVisible())
                self.assertFalse(c._exiting)
            shutdown.assert_not_called()
        self.assertEqual(c.tray.contextMenu().actions()[-1].text(), "退出工具")
        with (
            patch.object(c, "_exit_application") as exit_app,
            patch("sora_bilingual.game.tool_shutdown.shutdown") as shutdown,
        ):
            c.tray.contextMenu().actions()[-1].trigger()
            for _ in range(50):
                QTest.qWait(10)
                if exit_app.called:
                    break
            shutdown.assert_called_once()
            exit_app.assert_called_once()
        self.assertEqual(self.control.read_bytes(), original)

    def test_bundled_artwork_is_allowlisted_and_decoded_once(self):
        root = Path(__file__).resolve().parents[1]
        files = json.loads((root / "release-files.json").read_text("utf-8"))
        self.assertIn("sora_bilingual/app/handbook_resources.py", files)
        slices = json.loads((ASSETS / "provenance.json").read_text("utf-8"))["slices"]
        for name in slices:
            with self.subTest(name=name):
                first = artwork(name)
                self.assertFalse(first.isNull())
                self.assertIs(artwork(name), first)

    def test_mode_cards_remain_visible_after_resize_and_language_switch(self):
        c = self.controller
        c.expand()
        settings = c.panel.settings
        for locale in ("en", "ja", "zh-Hans"):
            settings.ui_language.setCurrentIndex(settings.ui_language.findData(locale))
            for width in (780, 1000, 780):
                c.panel.resize(width, 720)
                self.app.processEvents()
                for button in (settings.bilingual_mode, settings.single_mode):
                    self.assertTrue(button.isVisible())
                    self.assertGreaterEqual(button.height(), 24)
                    self.assertGreaterEqual(button.parentWidget().height(), button.height())
                self.assertEqual(settings.pages[0].horizontalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
