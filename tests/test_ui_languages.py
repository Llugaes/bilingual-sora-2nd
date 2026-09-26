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
            page.service.message = "当前已是最新稳定版"
            page.refresh(False)
            self.assertTrue(page.download.isHidden())
            self.assertTrue(page.recovery.isHidden())
            page.service.failed = True
            page.refresh(False)
            self.assertFalse(page.download.isHidden())
            self.assertFalse(page.recovery.isHidden())
            self.assertTrue(page.download.isEnabled())
            with patch("sora_bilingual.app.update_ui.QDesktopServices.openUrl") as open_url:
                page.download.click()
                self.assertEqual(open_url.call_args.args[0].toString(), page.service.download_url)
            for language in ("en", "ja"):
                set_language(language)
                self.assertNotEqual(tr("下载完整包（含 EXE）"), "下载完整包（含 EXE）")
            page.service.failed = False
            page.refresh(False)
            self.assertTrue(page.download.isHidden())
            self.assertTrue(page.recovery.isHidden())
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
                    ("en", "Language", "Settings"),
                    ("ja", "言語", "設定"),
                    ("zh-Hans", "语言", "设置"),
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

    def test_update_checkbox_persists_only_on_or_off(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "distribution.json").write_text(
                '{"repository":"example/mod", "version":"0.1.0"}', encoding="utf-8"
            )
            page = UpdatePage(root=root)
            try:
                self.assertTrue(page.automatic.isChecked())
                page.automatic.click()
                self.assertEqual(page.service.policy, "off")
                from sora_bilingual.updates.update_service import UpdateService

                self.assertEqual(UpdateService(root).policy, "off")
                page.automatic.click()
                self.assertEqual(UpdateService(root).policy, "automatic")
            finally:
                page.close()
                page.deleteLater()
                app.processEvents()

    def test_settings_retranslate_categories_and_system_label_without_mixed_copy(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "control.json"
            write_config({}, path)
            panel = OverlayController(
                path, Path(temp) / "status.json", start_timers=False, auto_connect=False
            )
            try:
                panel.expand()
                for code, tabs, system_label, opacity_label in (
                    (
                        "en",
                        ("Language", "Text layout", "Shortcuts", "Updates"),
                        "Follow system",
                        "Secondary text opacity",
                    ),
                    (
                        "ja",
                        ("言語", "文字レイアウト", "ショートカット", "更新"),
                        "システムに従う",
                        "副言語の不透明度",
                    ),
                    (
                        "zh-Hans",
                        ("语言", "文字排版", "快捷键", "更新"),
                        "跟随系统",
                        "副语言透明度",
                    ),
                ):
                    panel.panel.settings.ui_language.setCurrentIndex(
                        panel.panel.settings.ui_language.findData(code)
                    )
                    app.processEvents()
                    self.assertEqual(
                        tuple(panel.panel.settings.tabs.tabText(index) for index in range(4)), tabs
                    )
                    self.assertEqual(panel.panel.settings.ui_language.itemText(0), system_label)
                    self.assertEqual(
                        panel.panel.settings.secondary_opacity.accessibleName(), opacity_label
                    )
                    for index in range(4):
                        panel.panel.settings.tabs.setCurrentIndex(index)
                        app.processEvents()
                        screenshot = panel.panel.grab()
                        self.assertEqual(screenshot.width(), panel.panel.width())
                        page = panel.panel.settings.pages[index]
                        self.assertEqual(page.horizontalScrollBar().maximum(), 0)
                        tab_position = panel.panel.settings.tabs.tabBar().pos()
                        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
                        app.processEvents()
                        self.assertEqual(panel.panel.settings.tabs.tabBar().pos(), tab_position)
                        self.assertTrue(panel.panel.settings.tabs.tabBar().isVisible())
            finally:
                panel.panel.settings._status_timer.stop()
                panel.panel.settings._capture_timer.stop()
                panel.bar.hide()
                panel.panel.hide()
                panel.tray.hide()
                panel.deleteLater()
