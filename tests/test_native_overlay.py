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

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalSocket
from sora_bilingual.config.native_config import read_config, write_config, ActionPolicy
from sora_bilingual.app.native_settings import NativeSettingsWindow, update_control, ROOT
from sora_bilingual.app.native_overlay import describe_state, JsonSnapshot, OverlayController, STYLE
from sora_bilingual.platform.inputs import InputManager


class OverlayStatusTests(unittest.TestCase):
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
            for a, b in config["hotkeys"].items()
        }
        policy = ActionPolicy("annotation")

        def sample():
            states = {a: i.poll_state(True) for a, i in inputs.items()}
            mode = policy.advance(states)
            return describe_state(
                config,
                dict(
                    running=True,
                    updated_at=100,
                    enabled=True,
                    render_mode=mode,
                    hold_active=states["language_hold"].held,
                    interaction="annotation",
                    primary="zh-Hans",
                    secondary="ja",
                ),
                {},
                100,
            )

        base = sample()
        physical.update((0x11, 0x10, 0x7B))
        held = sample()
        physical.clear()
        released = sample()
        self.assertIn("双语", base["title"])
        self.assertIn("按住中", held["title"])
        self.assertNotEqual(base["color"], held["color"])
        self.assertEqual(released, base)

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

    def test_fresh_connection_clears_old_launch_failure(self):
        self.window._connection_error = "旧的启动失败"
        write_config(
            {"running": True, "updated_at": time.time(), "phase": "preparing"}, self.status
        )
        self.window.refresh_status()
        self.assertIsNone(self.window._connection_error)
        self.assertIn("正在准备", self.window.backend_label.text())

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
        self.window.binding_action.setCurrentIndex(3)
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
        self.assertIn("未保存", self.window.backend_label.text())
        self.window._begin_keyboard_capture()
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertFalse(self.window.capturing)
        self.window._begin_keyboard_capture()
        QTest.keyClick(self.window, Qt.Key.Key_F8, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(read_config(self.control)["overlay_binding"]["keyboard"], ["CTRL", "F8"])

    def test_controller_binding_is_saved_to_selected_action_and_can_be_cleared(self):
        self.window.binding_action.setCurrentIndex(3)
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
        update_control({"hotkeys": {"language_hold": binding}}, self.control)
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
            controller.bar.hide_button.click()
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
            controller.bar.hide_button.click()
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
