import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import tempfile
import time
import unittest
import hashlib
import subprocess
import sys
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalSocket
from sora_bilingual.config.native_config import read_config, write_config, ActionPolicy
from sora_bilingual.app.native_settings import NativeSettingsWindow, update_control, ROOT
from sora_bilingual.app.native_overlay import describe_state, JsonSnapshot, OverlayController, STYLE
from sora_bilingual.platform.inputs import InputManager
from sora_bilingual.app.i18n import tr, current_language, set_language
from sora_bilingual.app.presentation import with_font_status


class OverlayStatusTests(unittest.TestCase):
    def test_font_restart_notice_does_not_claim_connection_failed(self):
        state = {"title": "双语同时显示", "connected": True, "detail": "设置实时生效"}
        value = with_font_status(state, {"state": "restart-required"})
        self.assertTrue(value["connected"])
        self.assertEqual(value["title"], state["title"])
        self.assertIn("退出游戏后自动安装", value["font_notice"])
        self.assertNotIn("font_notice", state)
        self.assertEqual(with_font_status(state, {"state": "healthy"}), state)

    def test_font_conflict_keeps_connection_error_and_exposes_file_details(self):
        state = {"title": "连接异常", "connected": False, "detail": "existing failure"}
        value = with_font_status(state, {"state": "conflict", "detail": ["xinput1_4.dll"]})
        self.assertEqual(value["detail"], "existing failure")
        self.assertEqual(value["font_detail"], "xinput1_4.dll")
        language_before = current_language()
        try:
            for language in ("en", "ja"):
                set_language(language)
                self.assertNotEqual(tr(value["font_notice"]), value["font_notice"])
        finally:
            set_language(language_before)

    def test_preparing_locale_is_connected_and_still_reports_old_language(self):
        config = read_config(Path("__missing_test_config__.json"))
        config["primary"] = "en"
        live = dict(
            running=True,
            updated_at=100,
            enabled=True,
            primary="zh-Hans",
            secondary="ja",
            render_mode="annotation",
        )
        value = describe_state(
            config, live, dict(running=True, updated_at=100, phase="preparing"), 100
        )
        self.assertTrue(value["connected"])
        self.assertEqual(value["pair"], "简中 → 日文")
        self.assertIn("正在准备", value["detail"])

    def test_hold_colors_follow_acknowledged_state_and_release_restores_base(self):
        config = read_config(Path("__missing_test_config__.json"))
        physical = set()
        inputs = {
            a: InputManager(
                {"hotkey": b}, key_state=lambda k: k in physical, joystick_provider=lambda: []
            )
            for a, b in {"switch": config["switch_binding"]}.items()
        }
        policy = ActionPolicy("language_hold")

        def sample():
            states = {a: i.poll_state(True) for a, i in inputs.items()}
            mode = policy.advance(states["switch"])
            return describe_state(
                config,
                dict(
                    running=True,
                    updated_at=100,
                    enabled=True,
                    render_mode=mode,
                    hold_active=states["switch"].held,
                    interaction="language_hold",
                    primary="zh-Hans",
                    secondary="ja",
                ),
                {},
                100,
            )

        base = sample()
        physical.update((0x11, 0x10, 0x79))
        held = sample()
        physical.clear()
        released = sample()
        self.assertIn("主语言", base["title"])
        self.assertIn("按住中", held["title"])
        self.assertNotEqual(base["color"], held["color"])
        self.assertEqual(released, base)

    def test_status_colors_remain_readable_on_the_paper_surface(self):
        config = read_config(Path("__missing_test_config__.json"))
        error = describe_state(config, {}, {"updated_at": 100, "error": "offline"}, 100)
        loading = describe_state(
            config, {}, {"running": True, "updated_at": 100, "phase": "connecting"}, 100
        )
        connected = describe_state(
            config,
            {"running": True, "updated_at": 100, "enabled": True},
            {},
            100,
        )
        self.assertEqual(error["color"], "#a32b22")
        self.assertEqual(loading["color"], "#4f6270")
        self.assertEqual(connected["color"], "#086b68")

    def test_stale_live_state_cannot_claim_secondary_is_active(self):
        config = read_config(Path("__missing_test_config__.json"))
        value = describe_state(
            config,
            dict(running=True, updated_at=10, hold_active=True, render_mode="secondary"),
            {},
            100,
        )
        self.assertFalse(value["connected"])
        self.assertIn("未连接", value["title"])

    def test_pending_mode_change_does_not_lie_about_current_output(self):
        config = read_config(Path("__missing_test_config__.json"))
        config.update(interaction="annotation", mode_request=5)
        value = describe_state(
            config,
            dict(
                running=True,
                updated_at=100,
                render_mode="secondary",
                interaction="language_toggle",
                primary="zh-Hans",
                secondary="ja",
                mode_request=4,
            ),
            {},
            100,
        )
        self.assertIn("副语言", value["title"])
        self.assertIn("正在应用", value["detail"])

    def test_hotkey_changed_strategy_is_not_mistaken_for_pending_configuration(self):
        config = read_config(Path("__missing_test_config__.json"))
        value = describe_state(
            config,
            dict(
                running=True,
                updated_at=100,
                render_mode="primary",
                interaction="language_toggle",
                primary="zh-Hans",
                secondary="ja",
            ),
            {},
            100,
        )
        self.assertIn("单击切换", value["title"])
        self.assertNotIn("正在应用", value["detail"])

    def test_half_written_status_keeps_snapshot_but_freshness_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_config({"running": True, "updated_at": 10}, path)
            reader = JsonSnapshot(path)
            self.assertTrue(reader.read()["running"])
            path.write_text("{", encoding="utf-8")
            self.assertEqual(reader.read()["updated_at"], 10)
            self.assertFalse(
                describe_state(read_config(Path(tmp) / "config.json"), reader.read(), {}, 100)[
                    "connected"
                ]
            )


class OverlayUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.control = Path(self.temp.name) / "config.json"
        self.status = self.control.with_name("status.json")
        write_config({"sources": ["keep"], "stop": False}, self.control)
        self.window = NativeSettingsWindow(self.control, self.status)
        self.window._status_timer.stop()
        self.window._capture_timer.stop()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_layout_update_preserves_external_language_and_backend_state(self):
        update_control({"primary": "en"}, self.control)
        self.window.ruby_offset_x.setValue(7)
        config = read_config(self.control)
        self.assertEqual(config["primary"], "en")
        self.assertEqual(config["ruby_offset_x"], 7)
        self.assertEqual(config["sources"], ["keep"])
        self.assertFalse(config["stop"])

    def test_source_language_is_read_only_status_and_secondary_color_saves_normalized_rgb(self):
        self.assertFalse(hasattr(self.window, "game_language"))
        self.assertEqual(self.window.detected_game_language.text(), tr("等待检测"))
        write_config(
            {
                "running": True,
                "updated_at": time.time(),
                "detected_game_language": "ja",
                "source_language_status": "matched",
            },
            self.status,
        )
        self.window.refresh_status()
        self.assertIn("matched", self.window.detected_game_language.text())
        self.assertNotEqual(self.window.detected_game_language.text(), tr("等待检测"))
        self.window.secondary_color.set_color((0.2, 0.4, 0.6), emit=True)
        self.assertEqual(read_config(self.control)["secondary_color"], [0.2, 0.4, 0.6])

    def test_display_mode_controls_preserve_the_existing_interaction_contract(self):
        label = self.window.display_form.labelForField(self.window.single_options)
        self.assertTrue(self.window.bilingual_mode.isChecked())
        self.assertTrue(self.window.single_options.isHidden())
        self.assertTrue(label.isHidden())
        self.window.single_mode.click()
        self.assertFalse(self.window.single_options.isHidden())
        self.assertFalse(label.isHidden())
        self.assertEqual(read_config(self.control)["interaction"], "language_toggle")
        self.window.single_hold.click()
        self.assertEqual(read_config(self.control)["interaction"], "language_hold")
        self.window.bilingual_mode.click()
        self.assertTrue(self.window.single_options.isHidden())
        self.assertTrue(label.isHidden())
        self.assertEqual(read_config(self.control)["interaction"], "annotation")

    def test_secondary_alpha_and_bilingual_offset_save_and_reset(self):
        update_control({"secondary_opacity": 0.37}, self.control)
        self.window.reload_control()
        self.assertEqual(self.window.secondary_opacity.value(), 37)
        self.window.secondary_color.set_color((0.2, 0.4, 0.6), opacity=0.45, emit=True)
        self.assertEqual(self.window.secondary_opacity.value(), 45)
        self.window.secondary_opacity.setValue(72)
        self.window.bilingual_offset_y.setValue(-7)
        control = read_config(self.control)
        self.assertEqual(control["secondary_color"], [0.2, 0.4, 0.6])
        self.assertEqual(control["secondary_opacity"], 0.72)
        self.assertEqual(self.window.secondary_color.opacity(), 0.72)
        self.assertEqual(control["bilingual_offset_y"], -7)
        self.window._reset_layout()
        self.assertEqual(read_config(self.control)["bilingual_offset_y"], 0)

    def test_connection_state_is_grouped_with_read_only_detection(self):
        write_config(
            {
                "running": True,
                "updated_at": time.time(),
                "detected_game_language": "ja",
                "source_language_status": "matched",
            },
            self.status,
        )
        self.window.refresh_status()
        self.assertEqual(self.window.connection_state.text(), tr("已连接"))
        self.assertIn("matched", self.window.detected_game_language.text())

    def test_connection_strip_stays_outside_language_scroll_and_single_modes_fit_first_view(self):
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        try:
            controller.expand()
            settings = controller.panel.settings
            settings.single_mode.click()
            self.app.processEvents()
            page = settings.pages[0]
            self.assertIs(settings.connection_strip.parentWidget(), settings)
            self.assertFalse(settings.language_page.isAncestorOf(settings.connection_strip))
            self.assertFalse(settings.single_options.isHidden())
            for option in (settings.single_toggle, settings.single_hold):
                visible = option.rect().translated(option.mapTo(page.viewport(), QPoint()))
                self.assertTrue(page.viewport().rect().contains(visible))
        finally:
            controller.bar.hide()
            controller.panel.hide()
            controller.tray.hide()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_compact_status_bar_exposes_state_and_shortcut_in_tooltips(self):
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        try:
            state = describe_state(
                read_config(self.control),
                {"running": True, "updated_at": time.time(), "enabled": True},
                {},
            )
            controller.bar.present(state, "CTRL + SHIFT + F9")
            self.assertLessEqual(controller.bar.width(), 300)
            self.assertTrue(controller.bar.marker.accessibleName())
            self.assertIn("CTRL + SHIFT + F9", controller.bar.status.toolTip())
            self.assertTrue(controller.bar.open_button.accessibleName())
            self.assertTrue(controller.bar.exit_button.accessibleName())
        finally:
            controller.bar.hide()
            controller.panel.hide()
            controller.tray.hide()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_manual_reconnect_delegates_once_and_tracks_connection_state(self):
        class Connector:
            error = "previous failure"
            process = None

            def __init__(self):
                self.calls = 0

            def retry(self):
                self.calls += 1
                return True

        connector = Connector()
        self.window._auto_connector = connector
        self.window._update_connection_action({}, False)
        self.assertFalse(self.window.connection_button.isHidden())
        self.assertTrue(self.window.connection_button.isEnabled())
        self.window.connection_button.click()
        self.window.connection_button.click()
        self.assertEqual(connector.calls, 1)
        self.assertFalse(self.window.connection_button.isEnabled())
        self.window._update_connection_action({"phase": "connecting"}, False)
        self.assertFalse(self.window.connection_button.isHidden())
        self.assertFalse(self.window.connection_button.isEnabled())
        self.window._update_connection_action({"running": True, "updated_at": time.time()}, True)
        self.assertTrue(self.window.connection_button.isHidden())

    def test_fractional_spacing_survives_reload_and_an_unrelated_setting_change(self):
        update_control({"ruby_gap": 2.35, "line_gap": 7.65}, self.control)
        self.window.reload_control()
        self.assertEqual(self.window.ruby_gap.value(), 2.35)
        self.assertEqual(self.window.line_gap.value(), 7.65)
        self.window.ruby_offset_x.setValue(3)
        config = read_config(self.control)
        self.assertEqual(config["ruby_gap"], 2.35)
        self.assertEqual(config["line_gap"], 7.65)

    def test_fresh_connection_clears_old_launch_failure(self):
        self.window._connection_error = "旧的启动失败"
        write_config(
            {"running": True, "updated_at": time.time(), "phase": "preparing"}, self.status
        )
        self.window.refresh_status()
        self.assertIsNone(self.window._connection_error)
        self.assertEqual(
            tr("正在准备语言索引，当前语言继续显示…"), self.window.backend_label.text()
        )

    def test_reselecting_same_mode_issues_a_new_request_not_backend_restart(self):
        with patch(
            "sora_bilingual.app.native_settings.subprocess.Popen",
            side_effect=AssertionError("must not restart"),
        ):
            self.window.select_mode()
            one = read_config(self.control)["mode_request"]
            self.window.select_mode()
            two = read_config(self.control)["mode_request"]
        self.assertGreater(two, one)

    def test_panel_keyboard_capture_conflict_keeps_previous_binding_and_escape_cancels(self):
        self.window.binding_action.setCurrentIndex(self.window.binding_action.findData("overlay"))
        self.window.show()
        self.app.processEvents()
        self.window._begin_keyboard_capture()
        QTest.keyClick(
            self.window,
            Qt.Key.Key_F10,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertEqual(
            read_config(self.control)["overlay_binding"]["keyboard"], ["CTRL", "SHIFT", "F9"]
        )
        self.assertIn(tr("未保存："), self.window.backend_label.text())
        self.window._begin_keyboard_capture()
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertFalse(self.window.capturing)
        self.window._begin_keyboard_capture()
        QTest.keyClick(self.window, Qt.Key.Key_F8, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(read_config(self.control)["overlay_binding"]["keyboard"], ["CTRL", "F8"])

    def test_controller_binding_is_saved_to_selected_action_and_can_be_cleared(self):
        self.window.binding_action.setCurrentIndex(self.window.binding_action.findData("overlay"))
        self.window._capture_action = "overlay"
        binding = {
            "gamepad": {
                "guid": "test-device",
                "buttons": [2, 4],
                "axes": [{"index": 1, "direction": 1, "threshold": 0.5}],
            }
        }
        with patch.object(self.window._controller, "poll_capture", return_value=binding):
            self.window._poll_controller()
        self.assertEqual(
            read_config(self.control)["overlay_binding"]["gamepad"], binding["gamepad"]
        )
        self.window._clear_controller()
        self.assertEqual(read_config(self.control)["overlay_binding"]["gamepad"], {})

    def test_controller_conflict_does_not_replace_existing_binding(self):
        binding = {"gamepad": {"guid": "pad", "buttons": [1, 2]}}
        update_control({"switch_binding": binding}, self.control)
        with self.assertRaises(ValueError):
            update_control({"overlay_binding": binding}, self.control)
        self.assertEqual(read_config(self.control)["overlay_binding"]["gamepad"], {})

    def test_overlay_lifecycle_does_not_start_or_signal_backend(self):
        with patch(
            "sora_bilingual.app.native_settings.subprocess.Popen",
            side_effect=AssertionError("must not launch"),
        ):
            controller = OverlayController(self.control, self.status, start_timers=False)
            controller.expand()
            self.assertTrue(controller.panel.isVisible())
            controller.collapse()
            self.assertFalse(controller.panel.isVisible())
            self.assertTrue(controller.bar.isVisible())
            self.assertFalse(read_config(self.control)["stop"])
            original = self.control.read_bytes()
            controller.hide_interface()
            controller.tick()
            controller.tick()
            self.assertFalse(controller.bar.isVisible())
            self.assertFalse(controller.panel.isVisible())
            with patch.object(controller.hotkey, "poll", return_value=True):
                controller.poll_input()
            self.assertTrue(controller.panel.isVisible())
            controller.panel.hide_button.click()
            controller.tick()
            self.assertFalse(controller.panel.isVisible())
            self.assertTrue(controller.bar.isVisible())
            controller.expand()
            controller.panel.close()
            controller.tick()
            self.assertFalse(controller.panel.isVisible())
            self.assertTrue(controller.bar.isVisible())
            controller.hide_interface()
            controller.tick()
            self.assertFalse(controller.bar.isVisible())
            controller.tray.contextMenu().actions()[0].trigger()
            self.assertTrue(controller.panel.isVisible())
            self.assertEqual(
                self.control.read_bytes(), original, "visibility must not change backend settings"
            )
            controller.bar.hide()
            controller.panel.hide()
            controller.tray.hide()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_close_settings_keeps_status_bar_when_game_loses_foreground(self):
        controller = OverlayController(self.control, self.status, start_timers=False)
        live = dict(running=True, pid=123, updated_at=time.time(), enabled=True)
        try:
            with (
                patch.object(controller.live, "read", return_value=live),
                patch("sora_bilingual.app.native_overlay.foreground_rect", return_value=None),
            ):
                for close in (
                    controller.panel.hide_button.click,
                    controller.panel.close,
                    lambda: QTest.keyClick(controller.panel, Qt.Key.Key_Escape),
                ):
                    controller.expand()
                    close()
                    controller.tick()
                    controller.tick()
                    self.assertFalse(controller.panel.isVisible())
                    self.assertTrue(controller.bar.isVisible())
                controller.hide_interface()
                controller.tick()
                self.assertFalse(controller.bar.isVisible())
        finally:
            controller.bar.hide()
            controller.panel.hide()
            controller.tray.hide()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_settings_button_toggles_and_both_headers_drag_the_same_group(self):
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        original = self.control.read_bytes()
        try:
            controller.bar.move(12, 12)
            controller.bar.open_button.click()
            self.app.processEvents()
            self.assertTrue(controller.panel.isVisible())
            for grip in (
                controller.bar.grip,
                controller.bar.marker,
                controller.bar.status,
                controller.bar,
                controller.panel.grip,
            ):
                old_bar = controller.bar.pos()
                old_panel = controller.panel.pos()
                QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
                QTest.mouseMove(grip, QPoint(16, 12))
                QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=QPoint(16, 12))
                self.app.processEvents()
                delta = controller.bar.pos() - old_bar
                self.assertNotEqual(delta, QPoint())
                self.assertEqual(controller.panel.pos() - old_panel, delta)
                self.assertEqual(controller.preferences.value("bar_position"), controller.bar.pos())
                controller.tick()
                self.assertEqual(controller.panel.pos() - controller.bar.pos(), old_panel - old_bar)
            old_bar = controller.bar.pos()
            controller.bar.open_button.click()
            self.assertEqual(controller.bar.pos(), old_bar)
            self.assertFalse(controller.panel.isVisible())
            controller.bar.open_button.click()
            self.assertEqual(controller.bar.pos(), old_bar)
            self.assertTrue(controller.panel.isVisible())
            quit_events = []
            controller.bar.quit_requested.disconnect(controller.quit)
            controller.bar.quit_requested.connect(lambda: quit_events.append(True))
            old_bar = controller.bar.pos()
            QTest.mouseClick(controller.bar.exit_button, Qt.MouseButton.LeftButton)
            self.assertEqual(quit_events, [True])
            self.assertEqual(controller.bar.pos(), old_bar)
            controller.move_group(QPoint(99999, 99999))
            area = controller.bar.screen().availableGeometry()
            self.assertTrue(area.contains(controller.bar.geometry()))
            self.assertTrue(area.contains(controller.panel.geometry()))
            controller.bar.open_button.click()
            self.assertFalse(controller.panel.isVisible())
            self.assertTrue(controller.bar.isVisible())
            controller.bar.open_button.click()
            self.assertTrue(controller.panel.isVisible())
            self.assertEqual(self.control.read_bytes(), original)
        finally:
            controller.bar.hide()
            controller.panel.hide()
            controller.tray.hide()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_second_offline_launch_activates_resident_process_then_exits(self):
        command = [
            sys.executable,
            str(ROOT / "launch.py"),
            "--no-auto-connect",
            "--control",
            str(self.control),
            "--status",
            str(self.status),
        ]
        name = (
            "SoraBilingual-" + hashlib.sha256(str(self.control.resolve()).encode()).hexdigest()[:16]
        )
        environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        first = subprocess.Popen(
            command,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                socket = QLocalSocket()
                socket.connectToServer(name)
                if socket.waitForConnected(100):
                    socket.disconnectFromServer()
                    break
                if first.poll() is not None:
                    self.fail(first.stderr.read().decode(errors="replace"))
                time.sleep(0.05)
            else:
                self.fail("Overlay did not open its local single-instance server")
            second = subprocess.run(
                [*command, "--expanded"],
                env=environment,
                capture_output=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(second.returncode, 0, second.stderr.decode(errors="replace"))
            self.assertIsNone(first.poll())
            self.assertFalse(self.status.exists(), "Offline launch must never start the backend")
        finally:
            first.terminate()
            first.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
