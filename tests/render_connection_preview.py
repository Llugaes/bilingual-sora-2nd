"""Offline status-card review using actual Qt widgets; no game or user settings."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor
from sora_bilingual.app.native_overlay import OverlayController, STYLE
from sora_bilingual.app.native_settings import load_cjk_font
from sora_bilingual.app.presentation import connection_activity, describe_state, with_font_status
from sora_bilingual.app.i18n import set_language
from sora_bilingual.app.ui_widgets import retranslate
from sora_bilingual.config.native_config import DEFAULTS, write_config


def render():
    app = QApplication([])
    load_cjk_font(app)
    app.setStyleSheet(STYLE)
    output = Path("generated")
    with tempfile.TemporaryDirectory() as tmp:
        control, status = Path(tmp) / "control.json", Path(tmp) / "status.json"
        write_config(DEFAULTS, control)
        controller = OverlayController(control, status, start_timers=False, auto_connect=False)
        panel = controller.panel
        panel.settings._status_timer.stop()
        controller.expand()
        for language in ("zh-Hans", "en", "ja"):
            set_language(language)
            retranslate(panel)
            canvas = QPixmap(1240, 900)
            canvas.fill(QColor("#f4efe2"))
            painter = QPainter(canvas)
            for index, phase in enumerate(
                ("fonts", "waiting", "detecting", "preparing", "connecting", "failed")
            ):
                backend = dict(running=True, updated_at=100, phase=phase)
                if phase == "failed":
                    backend["error"] = "连接失败，请重新连接。"
                fresh = phase not in ("fonts", "waiting")
                state = describe_state(DEFAULTS, {}, backend if fresh else {}, 100)
                state["activity"] = connection_activity(backend, fresh)
                if phase == "fonts":
                    state = with_font_status(state, {"state": "preparing"})
                panel.settings._present_connection_state(backend, fresh)
                panel.settings._update_connection_action(backend, fresh)
                panel.present(state)
                app.processEvents()
                assert panel.phase_card.geometry().bottom() < panel.settings.geometry().top()
                assert panel.phase_title.text()
                painter.drawPixmap(
                    (index % 2) * 620, (index // 2) * 300, panel.grab().copy(0, 0, 620, 300)
                )
            painter.end()
            canvas.save(str(output / f"connection-states-{language}.png"))
        controller.bar.hide()
        panel.hide()
        controller.tray.hide()


if __name__ == "__main__":
    render()
