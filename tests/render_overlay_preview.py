"""Capture the real settings UI with isolated offline state.

Review generated/ui-guide before copying selected PNGs to docs/images. No game,
network, input recorder, update installer or player configuration is used.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from sora_bilingual.app.native_overlay import OverlayController, STYLE, describe_state
from sora_bilingual.app.native_settings import load_cjk_font
from sora_bilingual.app.i18n import tr
from sora_bilingual.config.native_config import write_config, DEFAULTS
from sora_bilingual.updates.update_service import UpdateService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/ui-guide")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    load_cjk_font(app)
    app.setStyleSheet(STYLE)
    captures = []

    def capture(widget, filename):
        app.processEvents()
        image = widget.grab()
        if not image.save(str(args.output / filename)):
            raise RuntimeError(f"Could not save {filename}")
        captures.append({"file": filename, "width": image.width(), "height": image.height()})

    for language in ("zh-Hans", "en", "ja"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "distribution.json").write_bytes((ROOT / "distribution.json").read_bytes())
            # Show the installed UI, without the developer-only notice. This
            # marker is only an offline fixture; updates remain forbidden below.
            (root / "installed-manifest.json").write_text("{}", encoding="utf-8")
            control, status = root / "control.json", root / "status.json"
            config = {**DEFAULTS, "ui_language": language, "interaction": "language_hold"}
            write_config(config, control)
            # Isolate the update policy as well as window/game preferences.
            with (
                patch("sora_bilingual.app.native_overlay.DEVELOPMENT", False),
                patch("sora_bilingual.app.native_overlay.BUILD_SUFFIX", ""),
                patch("sora_bilingual.app.update_ui.UpdateService", lambda *_: UpdateService(root)),
                patch.object(UpdateService, "tick", side_effect=AssertionError("Offline capture")),
            ):
                controller = OverlayController(
                    control, status, start_timers=False, auto_connect=False
                )
                try:
                    settings = controller.panel.settings
                    settings._status_timer.stop()
                    settings._capture_timer.stop()
                    settings.updates.timer.stop()
                    controller.tray.hide()
                    controller.bar.move(10, 10)
                    controller.expand()
                    controller.panel.resize(850, 720)
                    offline = describe_state(config, {}, {}, 100)
                    controller.panel.present(offline)
                    controller.bar.present(offline, "Ctrl + Shift + F9")
                    settings.backend_label.setText(
                        {
                            "zh-Hans": "离线界面演示 · 未连接游戏",
                            "en": "Offline UI preview · no game connected",
                            "ja": "オフライン画面例 · ゲーム未接続",
                        }[language]
                    )
                    pages = (
                        ("语言与显示", "settings"),
                        ("文字排版", "layout"),
                        ("快捷操作", "shortcuts"),
                        ("工具外观", "appearance"),
                    )
                    for index, (title, name) in enumerate(pages):
                        controller.panel.resize(850, 720)
                        settings.nav_buttons[index].click()
                        app.processEvents()
                        page = settings.pages[index]
                        assert settings.tabs.tabText(index) == tr(title), "Navigation changed"
                        # Use the real resizable window to show every control in
                        # documentation, including taller localized layouts.
                        for _ in range(3):
                            overflow = page.verticalScrollBar().maximum()
                            if not overflow:
                                break
                            controller.panel.resize(850, controller.panel.height() + overflow)
                            app.processEvents()
                        page.verticalScrollBar().setValue(0)
                        assert page.verticalScrollBar().maximum() == 0, (language, name)
                        assert page.horizontalScrollBar().maximum() == 0, (language, name)
                        filename = (
                            "appearance.png"
                            if name == "appearance" and language == "zh-Hans"
                            else f"{name}-{language}.png"
                        )
                        capture(controller.panel, filename)

                    settings.nav_buttons[0].click()
                    controller.panel.show_updates()
                    assert controller.panel.update_popup.isVisible()
                    capture(controller.panel.update_popup, f"updates-{language}.png")
                    controller.panel.update_popup.hide()
                    controller.bar.adjustSize()
                    capture(controller.bar, f"status-bar-{language}.png")
                finally:
                    controller.close_interface()
                    controller.panel.deleteLater()
                    controller.bar.deleteLater()
                    controller.deleteLater()
                    app.processEvents()

    (args.output / "captures.json").write_text(
        json.dumps({"offline": True, "game_attached": False, "captures": captures}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(captures)} real Qt captures to {args.output}")


if __name__ == "__main__":
    main()
