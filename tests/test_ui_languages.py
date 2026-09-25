import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from sora_bilingual.app.native_overlay import OverlayController
from sora_bilingual.app.i18n import MESSAGES, set_language, tr
from sora_bilingual.config.native_config import read_config, write_config


class UiLanguageTests(unittest.TestCase):
    def tearDown(self):
        set_language("zh-Hans")

    def test_all_messages_have_both_translations(self):
        for source, translations in MESSAGES.items():
            self.assertEqual(set(translations), {"en", "ja"}, source)
            self.assertTrue(all(translations.values()), source)

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
