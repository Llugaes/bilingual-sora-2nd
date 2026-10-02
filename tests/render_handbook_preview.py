"""Render production widgets with temporary state, without a game connection.

Pass --native for an explicit, briefly visible Windows desktop verification.
"""

import os
import sys
from pathlib import Path

if "--native" not in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctypes
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from sora_bilingual.app.native_overlay import OverlayController, STYLE
from sora_bilingual.app.native_settings import load_cjk_font
from sora_bilingual.app.appearance import APPEARANCES
from sora_bilingual.config.native_config import write_config

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
load_cjk_font(app)
app.setStyleSheet(STYLE)
output = Path(__file__).resolve().parents[1] / "generated/handbook-preview"
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    control = Path(directory) / "control.json"
    status = Path(directory) / "status.json"
    write_config({"ui_language": "zh-Hans", "interaction": "annotation"}, control)
    state = dict(
        running=True,
        pid=os.getpid(),
        updated_at=time.time(),
        primary="zh-Hans",
        secondary="ja",
        detected_game_language="zh-Hans",
        render_mode="annotation",
        phase="ready",
        enabled=True,
    )
    write_config(state, status)
    write_config(state, status.with_name("native-live.json"))
    c = OverlayController(control, status, start_timers=False, auto_connect=False)
    c.panel.settings._status_timer.stop()
    c.panel.settings._capture_timer.stop()
    c.expand()
    c.panel.resize(850, 720)
    for locale in ("en", "ja", "zh-Hans"):
        c.panel.settings.ui_language.setCurrentIndex(c.panel.settings.ui_language.findData(locale))
        for index, name in enumerate(("language", "layout", "shortcuts", "appearance")):
            c.panel.settings.tabs.setCurrentIndex(index)
            app.processEvents()
            if index == 0:
                for button in (c.panel.settings.bilingual_mode, c.panel.settings.single_mode):
                    assert button.isVisible() and button.height() >= 24, locale
                    assert button.parentWidget().height() >= button.height(), locale
            c.panel.grab().save(str(output / f"{locale}-{name}.png"))
            assert c.panel.settings.pages[index].horizontalScrollBar().maximum() == 0, (
                locale,
                name,
            )
    for locale in ("en", "ja", "zh-Hans"):
        c.panel.settings.ui_language.setCurrentIndex(c.panel.settings.ui_language.findData(locale))
        c.panel.settings.tabs.setCurrentIndex(0)
        for width, text_size in ((780, 17), (1000, 13)):
            c.panel.setStyleSheet(f"QWidget {{ font-size: {text_size}px; }}")
            c.panel.resize(width, 720)
            app.processEvents()
            for button in c.panel.settings.nav_buttons:
                label = button.label_layout(button.width())
                assert label.boundingRect().height() <= button.height() - 20, locale
                assert all(
                    label.lineAt(i).naturalTextWidth() <= button.width() - 40
                    for i in range(label.lineCount())
                ), locale
            assert c.panel.settings.pages[0].horizontalScrollBar().maximum() == 0, locale
            c.panel.grab().save(str(output / f"{locale}-navigation-{width}-{text_size}.png"))
    c.panel.setStyleSheet("")
    c.panel.resize(850, 720)
    for theme in APPEARANCES:
        c.panel.settings.appearance_choices[theme].click()
        for locale in ("zh-Hans", "en", "ja"):
            c.panel.settings.ui_language.setCurrentIndex(
                c.panel.settings.ui_language.findData(locale)
            )
            for index, name in enumerate(("language", "layout", "shortcuts", "appearance")):
                c.panel.settings.tabs.setCurrentIndex(index)
                app.processEvents()
                assert c.panel.settings.pages[index].horizontalScrollBar().maximum() == 0, (
                    theme,
                    locale,
                    name,
                )
                c.panel.grab().save(str(output / f"{theme}-{locale}-{name}.png"))
        c.bar.grab().save(str(output / f"{theme}-bar.png"))
        c.panel.update_button.click()
        app.processEvents()
        c.panel.update_popup.grab().save(str(output / f"{theme}-updates.png"))
        c.panel.update_popup.hide()
    c.panel.settings.appearance_choices["sky"].click()
    c.panel.settings.ui_language.setCurrentIndex(c.panel.settings.ui_language.findData("zh-Hans"))
    c.panel.settings.tabs.setCurrentIndex(0)
    page = c.panel.settings.updates
    page.service.available = "v9.0.0"
    page.service.release = {"name": "UI verification example"}
    page.service.message = "发现 v9.0.0；开发目录不会被覆盖，请使用发行包"
    page.refresh(False)
    c.panel.update_button.click()
    app.processEvents()
    c.panel.update_popup.grab().save(str(output / "updates.png"))
    QTest.keyClick(page.check, Qt.Key.Key_Escape)
    app.processEvents()
    assert not c.panel.update_popup.isVisible()
    assert c.panel.isVisible() and c.bar.open_button._notice
    c.bar.grab().save(str(output / "bar-update.png"))
    c.panel.settings.bar_transparency.setValue(100)
    app.processEvents()
    c.bar.grab().save(str(output / "bar-transparent.png"))
    c.panel.settings.bar_transparency.setValue(0)
    original = control.read_bytes()
    c.panel.hide_button.click()
    c.tick()
    assert not c.bar.isVisible() and not c.panel.isVisible()
    if "--native" in sys.argv:
        visible = ctypes.windll.user32.IsWindowVisible
        visible.argtypes = [ctypes.c_void_p]
        assert not visible(int(c.bar.winId())) and not visible(int(c.panel.winId()))
    c.tray.contextMenu().actions()[0].trigger()
    app.processEvents()
    assert c.bar.isVisible() and c.panel.isVisible()
    if "--native" in sys.argv:
        assert visible(int(c.bar.winId())) and visible(int(c.panel.winId()))
    assert control.read_bytes() == original
    assert not c._exiting
    page.service.available = None
    page.service.release = None
    page.refresh(False)
    c.panel.grab().save(str(output / "handbook.png"))
    c.hide_interface()
    c.tray.hide()
print(
    "Passed: three locales, four pages, update popup Esc, dual badges, transparency, native tray hide/restore; no game access."
)
print(output)
