import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtWidgets import QApplication
from sora_bilingual.app.native_overlay import OverlayController
from sora_bilingual.app.i18n import MESSAGES, set_language, tr
from sora_bilingual.config.native_config import read_config, write_config
from sora_bilingual.app.update_ui import UpdatePage


class UiLanguageTests(unittest.TestCase):
    def test_automatic_ui_locale_uses_system_language(self):
        for system, text in (
            ("English_United States", "Settings"),
            ("ja_JP", "設定"),
            ("Chinese (Simplified)_China", "设置"),
            ("de_DE", "Settings"),
        ):
            with patch("sora_bilingual.app.i18n.locale.getlocale", return_value=(system, "UTF-8")):
                set_language("auto")
                self.assertEqual(tr("设置"), text)

    def tearDown(self):
        set_language("zh-Hans")

    def test_all_messages_have_both_translations(self):
        for source, translations in MESSAGES.items():
            self.assertEqual(set(translations), {"en", "ja"}, source)
            self.assertTrue(all(translations.values()), source)

    def test_update_failure_exposes_localized_download_action(self):
        app = QApplication.instance() or QApplication([])
        page = UpdatePage()
        try:
            page.service.failed = True
            page.refresh(False)
            self.assertFalse(page.recovery.isHidden())
            self.assertTrue(page.download.isEnabled())
            with patch("sora_bilingual.app.update_ui.QDesktopServices.openUrl") as open_url:
                page.download.click()
                self.assertEqual(open_url.call_args.args[0].toString(), page.service.download_url)
            for language in ("en", "ja"):
                set_language(language)
                self.assertNotEqual(tr("下载完整包（含 EXE）"), "下载完整包（含 EXE）")
        finally:
            page.close()
            page.deleteLater()
            app.processEvents()

    def test_live_language_switch_preserves_game_pair_bindings_and_modes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "control.json"
            write_config(
                {
                    "primary": "de",
                    "secondary": "fr",
                    "game_language": "ja",
                    "ui_language": "zh-Hans",
                    "interaction": "language_hold",
                },
                path,
            )
            panel = OverlayController(
                path, Path(temp) / "status.json", start_timers=False, auto_connect=False
            )
            settings = panel.panel.settings
            before = read_config(path)
            try:
                for code, title, button in (
                    ("en", "Languages and mode", "Settings"),
                    ("ja", "言語とモード", "設定"),
                    ("zh-Hans", "语言与模式", "设置"),
                ):
                    settings.ui_language.setCurrentIndex(settings.ui_language.findData(code))
                    app.processEvents()
                    self.assertEqual(settings.tabs.tabText(0), title)
                    self.assertEqual(panel.bar.open_button.text(), button)
                    self.assertEqual(panel.tray.contextMenu().actions()[0].text(), tr("打开设置"))
                    after = read_config(path)
                    self.assertEqual(after["ui_language"], code)
                    self.assertEqual(
                        {k: v for k, v in after.items() if k != "ui_language"},
                        {k: v for k, v in before.items() if k != "ui_language"},
                    )
            finally:
                settings._status_timer.stop()
                settings._capture_timer.stop()
                panel.bar.hide()
                panel.panel.hide()
                panel.tray.hide()
                panel.deleteLater()
