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
from sora_bilingual.app.native_overlay import (
    describe_state,
    JsonSnapshot,
    OverlayController,
    StatusBar,
    STYLE,
)
from sora_bilingual.platform.inputs import InputManager
from sora_bilingual.app.i18n import tr, current_language, set_language
from sora_bilingual.app.presentation import with_font_status
from sora_bilingual.paths import build_label


class OverlayStatusTests(unittest.TestCase):
    def test_packaged_dev_marker_identifies_only_its_matching_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text('{"version":"0.4.3"}', "utf-8")
            self.assertEqual(build_label(root), "DEV 0.4.3")
            (root / "installed-manifest.json").write_text("{}", "utf-8")
            self.assertEqual(build_label(root), "0.4.3")
            (root / "generated").mkdir()
            marker = root / "generated/development-version.txt"
            marker.write_text("0.4.3\n", "utf-8")
            self.assertEqual(build_label(root), "DEV 0.4.3")
            marker.write_text("1.0.0\n", "utf-8")
            self.assertEqual(build_label(root), "0.4.3")
            marker.write_bytes(b"\xff")
            self.assertEqual(build_label(root), "0.4.3")

    def test_runtime_font_notice_does_not_claim_connection_failed(self):
        state = {"title": "双语同时显示", "connected": True, "detail": "设置实时生效"}
        value = with_font_status(state, {"state": "runtime-required"})
        self.assertTrue(value["connected"])
        self.assertEqual(value["title"], state["title"])
        self.assertIn("无需重启", value["font_notice"])
        self.assertNotIn("font_notice", state)
        self.assertEqual(with_font_status(state, {"state": "healthy"}), state)

    def test_font_conflict_keeps_connection_error_and_exposes_file_details(self):
        state = {"title": "连接异常", "connected": False, "detail": "existing failure"}
        value = with_font_status(state, {"state": "conflict", "detail": ["xinput1_4.dll"]})
        self.assertEqual(value["detail"], "existing failure")
        self.assertEqual(value["font_detail"], "xinput1_4.dll")
        self.assertIn("无法确认其归属", value["font_notice"])
        self.assertIn("暂未覆盖", value["font_notice"])
        self.assertNotIn("已有 MOD 文件", value["font_notice"])
        language_before = current_language()
        try:
            for language in ("en", "ja"):
                set_language(language)
                self.assertNotEqual(tr(value["font_notice"]), value["font_notice"])
        finally:
            set_language(language_before)

    def test_incompatible_executable_has_a_distinct_font_notice(self):
        state = {"title": "未连接游戏", "connected": False, "detail": "等待游戏启动"}
        value = with_font_status(
            state,
            {"state": "unsupported-exe", "detail": "native contract changed"},
        )
        self.assertEqual(value["font_state"], "unsupported-exe")
        self.assertIn("兼容检查", value["font_notice"])
        self.assertEqual(value["font_detail"], "native contract changed")

    def test_status_bar_keeps_connection_failure_before_runtime_font_notice(self):
        app = QApplication.instance() or QApplication([])
        bar = StatusBar()
        try:
            bar.present(
                {
                    "title": "连接失败",
                    "detail": "游戏 EXE 版本未验证，停止连接。",
                    "color": "#a32b22",
                    "connected": False,
                    "pair": "简中 → 日文",
                    "font_notice": "字体已准备，连接后在游戏内加载，无需重启",
                },
                "Ctrl + Shift + B",
            )
            tooltip = bar.status.toolTip()
            self.assertIn("游戏 EXE 版本未验证", tooltip)
            self.assertIn("字体已准备", tooltip)
            self.assertLess(tooltip.index("游戏 EXE 版本未验证"), tooltip.index("字体已准备"))
        finally:
            bar.deleteLater()
            app.processEvents()

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
    def test_language_settings_grouping_and_wheel_does_not_change_saved_selection(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QWheelEvent

        window = self.window
        window.show()
        self.app.processEvents()
        self.assertTrue(window.appearance_page.isAncestorOf(window.ui_language))
        self.assertFalse(window.language_page.isAncestorOf(window.ui_language))
        self.assertEqual(window.primary.y(), window.secondary.y())
        self.assertLess(window.primary.x(), window.secondary.x())
        self.assertLess(window.enabled.y(), window.primary.y())
        before = self.control.read_bytes()
        for combo in (
            window.primary,
            window.secondary,
            window.ui_language,
            window.controller_style,
        ):
            selected = combo.currentIndex()
            combo.setFocus()
            event = QWheelEvent(
                QPointF(4, 4),
                QPointF(4, 4),
                QPoint(),
                QPoint(0, -120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            self.app.sendEvent(combo, event)
            self.assertEqual(combo.currentIndex(), selected)
        self.assertEqual(self.control.read_bytes(), before)

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

    def test_controller_styles_preserve_raw_binding_and_are_per_action(self):
        from sora_bilingual.platform.gamepad_labels import make_profile

        pad = {
            "guid": "controller",
            "buttons": [9],
            "axes": [{"index": 5, "direction": 1, "threshold": 0.25}],
            "profile": make_profile(7, {"leftshoulder": "b9", "righttrigger": "a5"}),
        }
        update_control({"switch_binding": {"gamepad": pad}}, self.control)
        self.window.reload_control()
        self.assertEqual(self.window.binding_label.text(), tr("手柄：L1 + R2"))
        self.assertTrue(self.window.controller_style.isEnabled())
        self.window.controller_style.setCurrentIndex(self.window.controller_style.findData("xbox"))
        saved = read_config(self.control)["switch_binding"]["gamepad"]
        self.assertEqual(saved, {**pad, "label_style": "xbox"})
        self.assertEqual(self.window.binding_label.text(), tr("手柄：LB + RT"))
        before = self.control.read_bytes()
        self.window.binding_action.setCurrentIndex(self.window.binding_action.findData("overlay"))
        self.assertEqual(self.window.controller_style.currentData(), "auto")
        self.assertFalse(self.window.controller_style.isEnabled())
        self.assertEqual(self.control.read_bytes(), before)
        self.window.binding_action.setCurrentIndex(self.window.binding_action.findData("switch"))
        self.assertEqual(self.window.controller_style.currentData(), "xbox")
        self.assertEqual(self.control.read_bytes(), before)
        self.window._clear_controller()
        self.assertFalse(self.window.controller_style.isEnabled())

    def test_controller_capture_saves_profile_and_preserves_style(self):
        from sora_bilingual.platform.gamepad_labels import make_profile

        update_control(
            {"switch_binding": {"gamepad": {"buttons": [1], "label_style": "switch"}}}, self.control
        )
        self.window.reload_control()
        self.window._capture_action = "switch"
        self.window._update_capture_controls()
        self.assertFalse(self.window.controller_style.isEnabled())
        captured = {
            "gamepad": {"guid": "pad", "buttons": [2], "profile": make_profile(2, {"a": "b2"})}
        }
        with patch.object(self.window._controller, "poll_capture", return_value=captured):
            self.window._poll_controller()
        self.assertEqual(
            read_config(self.control)["switch_binding"]["gamepad"],
            {**captured["gamepad"], "label_style": "switch"},
        )
        self.assertEqual(self.window.binding_label.text(), tr("手柄：B"))
        self.assertTrue(self.window.controller_style.isEnabled())

    def test_legacy_controller_label_resolves_before_game_status_is_available(self):
        from sora_bilingual.platform.gamepad_labels import make_profile
        from sora_bilingual.platform.inputs import GamepadState

        update_control(
            {"switch_binding": {"gamepad": {"guid": "pad", "buttons": [8]}}}, self.control
        )
        self.window.reload_control()
        device = GamepadState(
            "1", "pad", "DualSense", frozenset(), profile=make_profile(7, {"rightstick": "b8"})
        )
        self.window.tabs.setCurrentIndex(2)
        # An invalid status file must not block offline device discovery.
        self.status.write_text("{", encoding="utf-8")
        with (
            patch.object(self.window, "isVisible", return_value=True),
            patch.object(self.window._controller, "devices", return_value=[device]) as read_devices,
        ):
            before = self.control.read_bytes()
            self.window.refresh_status()
            read_devices.assert_called_once()
        self.assertEqual(self.window.binding_label.text(), tr("手柄：R3"))
        self.assertEqual(self.window.device_label.text(), tr("设备：DualSense"))
        self.assertEqual(self.control.read_bytes(), before)

    def test_controller_label_selector_fits_narrow_page_with_larger_system_text(self):
        self.window.setStyleSheet("QWidget { font-size: 17px; }")
        self.window.resize(620, 560)
        self.window.tabs.setCurrentIndex(2)
        self.window.show()
        for locale in ("en", "ja", "zh-Hans"):
            with self.subTest(locale=locale):
                self.window.ui_language.setCurrentIndex(self.window.ui_language.findData(locale))
                self.app.processEvents()
                page = self.window.pages[2]
                self.assertEqual(page.horizontalScrollBar().maximum(), 0)

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

    def test_automatic_font_status_needs_no_directory_language_or_prepare_action(self):
        connector = type("Connector", (), {"font_status": {}})()
        self.window._auto_connector = connector
        for locale in ("zh-Hans", "en", "ja"):
            with self.subTest(locale=locale):
                self.window.ui_language.setCurrentIndex(self.window.ui_language.findData(locale))
                before = self.control.read_bytes()
                connector.font_status = {
                    "state": "preparing",
                    "message": "正在从本机游戏资源准备多语言字体",
                }
                self.window._present_font_preparation()
                self.assertNotIn(
                    tr("字体已就绪，可以启动游戏"), self.window.font_preparation_status.text()
                )
                connector.font_status = {"state": "installed"}
                self.window._present_font_preparation()
                self.assertEqual(
                    self.window.font_preparation_status.text(), tr("字体已就绪，可以启动游戏")
                )
                self.assertEqual(
                    self.window.font_preparation_detail.text(),
                    tr("首次进入游戏后会自动初始化语言映射，可能需要几分钟。"),
                )
                connector.font_status = {
                    "state": "error",
                    "message": "字体准备失败",
                    "detail": "failure details",
                }
                self.window._present_font_preparation()
                self.assertEqual(self.window.font_preparation_detail.text(), "failure details")
                self.assertNotIn(
                    tr("字体已就绪，可以启动游戏"), self.window.font_preparation_status.text()
                )
                self.assertEqual(self.control.read_bytes(), before)
        for field in ("choose_game", "preparation_language", "prepare_game"):
            self.assertFalse(hasattr(self.window, field), field)

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

    def test_connection_strip_stays_visible_and_single_modes_remain_reachable(self):
        update_control({"ui_language": "en"}, self.control)
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        try:
            controller.expand()
            settings = controller.panel.settings
            settings.single_mode.click()
            self.app.processEvents()
            page = settings.pages[0]
            self.assertTrue(settings.isAncestorOf(settings.connection_strip))
            self.assertFalse(settings.language_page.isAncestorOf(settings.connection_strip))
            self.assertFalse(settings.single_options.isHidden())
            for option in (settings.single_toggle, settings.single_hold):
                page.ensureWidgetVisible(option)
                self.app.processEvents()
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
            self.assertLessEqual(controller.bar.width(), 340)
            self.assertTrue(controller.bar.marker.accessibleName())
            self.assertIn("CTRL + SHIFT + F9", controller.bar.status.toolTip())
            self.assertTrue(controller.bar.open_button.accessibleName())
            self.assertFalse(hasattr(controller.bar, "pin_button"))
            self.assertTrue(controller.bar.minimize_button.accessibleName())
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
        self.window._update_connection_action({"phase": "connecting"}, True)
        self.assertFalse(self.window.connection_button.isHidden())
        self.assertFalse(self.window.connection_button.isEnabled())
        self.window._update_connection_action({"running": True, "updated_at": time.time()}, True)
        self.assertTrue(self.window.connection_button.isHidden())

    def test_old_connecting_phase_cannot_disable_reconnect_or_claim_work(self):
        stale = {"phase": "connecting", "running": True, "updated_at": 1}
        self.window._update_connection_action(stale, False)
        self.window._present_connection_state(stale, False)
        self.assertTrue(self.window.connection_button.isEnabled())
        self.assertNotEqual(self.window.connection_state.text(), tr("正在连接游戏"))

    def test_connected_backend_process_is_not_a_pending_connection(self):
        from unittest.mock import Mock

        connector = Mock(process=Mock(poll=Mock(return_value=None)), error=None, game_running=True)
        self.window._auto_connector = connector
        ready = {"running": True, "phase": "ready", "updated_at": time.time()}
        self.window._update_connection_action(ready, True)
        self.window._present_connection_state(ready, True)
        self.assertTrue(self.window.connection_button.isHidden())
        self.assertEqual(self.window.connection_state.text(), tr("已连接"))

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
        self.assertEqual(tr("正在构建语言映射"), self.window.backend_label.text())

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
            self.assertFalse(controller.bar.isVisible())
            controller.expand()
            controller.panel.close()
            controller.tick()
            self.assertFalse(controller.panel.isVisible())
            self.assertFalse(controller.bar.isVisible())
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

    def test_close_hides_to_tray_while_escape_keeps_bar_when_game_loses_foreground(self):
        controller = OverlayController(self.control, self.status, start_timers=False)
        live = dict(running=True, pid=123, updated_at=time.time(), enabled=True)
        try:
            with (
                patch.object(controller.live, "read", return_value=live),
                patch("sora_bilingual.app.native_overlay.foreground_rect", return_value=None),
            ):
                for close, keep_bar in (
                    (controller.panel.hide_button.click, False),
                    (controller.panel.close, False),
                    (lambda: QTest.keyClick(controller.panel, Qt.Key.Key_Escape), True),
                ):
                    controller.expand()
                    close()
                    controller.tick()
                    controller.tick()
                    self.assertFalse(controller.panel.isVisible())
                    self.assertEqual(controller.bar.isVisible(), keep_bar)
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
            controller.panel.resize(780, 500)
            for grip in (
                controller.bar.grip,
                controller.bar.marker,
                controller.bar.status,
                controller.bar,
                controller.panel.grip,
            ):
                # Leave room for each independent drag on the 800px offscreen display.
                controller.bar.move(2, 12)
                controller.panel.move(2, 12 + controller.bar.height() + 8)
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
            minimize_events = []
            controller.bar.minimize.connect(lambda: minimize_events.append(True))
            old_bar = controller.bar.pos()
            QTest.mouseClick(controller.bar.minimize_button, Qt.MouseButton.LeftButton)
            self.assertEqual(minimize_events, [True])
            self.assertFalse(controller.bar.isVisible())
            self.assertFalse(controller.panel.isVisible())
            controller.expand()
            controller.panel.resize(780, 500)
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

    def test_background_opacity_preserves_legacy_appearance_and_survives_recreation(self):
        self.assertEqual(self.window.bar_opacity.value(), 100)
        self.window.window_preferences.setValue("bar_transparency", 70)
        self.window.window_preferences.sync()
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        original = self.control.read_bytes()
        try:
            controller.expand()
            self.assertFalse(hasattr(controller.bar, "pin_button"))
            self.assertEqual(controller.panel.settings.bar_opacity.value(), 30)
            self.assertEqual(controller.panel.settings.bar_opacity_value.text(), "30%")
            self.assertEqual(controller.bar._background_alpha, 77)
            self.assertEqual(controller.bar.windowOpacity(), 1.0)
            self.assertEqual(controller.panel.windowOpacity(), 1.0)
            controller.panel.settings.bar_opacity.setValue(100)
            self.assertEqual(controller.bar._background_alpha, 255)
            self.assertEqual(controller.preferences.value("bar_transparency", type=int), 0)
            controller.panel.settings.bar_opacity.setValue(0)
            self.assertEqual(controller.preferences.value("bar_transparency", type=int), 100)
            self.app.processEvents()
            rendered = controller.bar.grab().toImage()
            ratio = controller.bar.devicePixelRatioF()
            self.assertLessEqual(rendered.pixelColor(QPoint(176, 16) * ratio).alpha(), 2)
            for button in (
                controller.bar.open_button,
                controller.bar.minimize_button,
            ):
                corner = button.pos() + QPoint(4, button.height() // 2)
                self.assertLessEqual(rendered.pixelColor(corner * ratio).alpha(), 3)
            self.assertTrue(
                any(
                    rendered.pixelColor(QPoint(x, y) * ratio).alpha() == 255
                    for x in range(40, 100)
                    for y in range(8, 35)
                )
            )
            controller.panel.settings.bar_opacity.setValue(30)
            controller.tick()
            self.assertFalse(controller._exiting)
            self.assertEqual(self.control.read_bytes(), original)
            controller.preferences.sync()
            other = OverlayController(
                self.control, self.status, start_timers=False, auto_connect=False
            )
            try:
                self.assertFalse(hasattr(other.bar, "pin_button"))
                self.assertEqual(other.panel.settings.bar_opacity.value(), 30)
                self.assertEqual(other.bar._background_alpha, 77)
            finally:
                other.close_interface()
                other.panel.deleteLater()
                other.bar.deleteLater()
                other.deleteLater()
            controller.hide_interface()
            controller.tick()
            self.assertFalse(controller.bar.isVisible())
            self.assertFalse(controller.panel.isVisible())
            controller.tray.contextMenu().actions()[0].trigger()
            self.assertTrue(controller.panel.isVisible())
            self.assertTrue(controller.bar.isVisible())
            self.assertTrue(controller.bar.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.assertEqual(self.control.read_bytes(), original)
        finally:
            controller.close_interface()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_bar_click_and_small_jitter_toggle_settings_without_moving(self):
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        original = self.control.read_bytes()
        try:
            controller.bar.move(12, 12)
            for surface in (
                controller.bar,
                controller.bar.grip,
                controller.bar.marker,
                controller.bar.status,
            ):
                with self.subTest(surface=surface.objectName()):
                    old_position = controller.bar.pos()
                    QTest.mouseClick(surface, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
                    self.assertTrue(controller.panel.isVisible())
                    self.assertEqual(controller.bar.pos(), old_position)
                    QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
                    QTest.mouseMove(surface, QPoint(5, 4))
                    QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=QPoint(5, 4))
                    self.assertFalse(controller.panel.isVisible())
                    self.assertEqual(controller.bar.pos(), old_position)
                    QTest.mouseClick(surface, Qt.MouseButton.RightButton, pos=QPoint(4, 4))
                    self.assertFalse(controller.panel.isVisible())
            self.assertEqual(self.control.read_bytes(), original)
        finally:
            controller.close_interface()
            controller.panel.deleteLater()
            controller.bar.deleteLater()
            controller.deleteLater()
            self.app.processEvents()

    def test_bar_drag_never_opens_settings_even_if_pointer_returns_to_start(self):
        controller = OverlayController(
            self.control, self.status, start_timers=False, auto_connect=False
        )
        try:
            controller.bar.move(12, 12)
            start = controller.bar.pos()
            surface = controller.bar.status
            QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
            QTest.mouseMove(surface, QPoint(24, 4))
            self.assertNotEqual(controller.bar.pos(), start)
            # Move back to the same global location, accounting for the moved window.
            QTest.mouseMove(surface, QPoint(-16, 4))
            QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
            self.assertEqual(controller.bar.pos(), start)
            self.assertFalse(controller.panel.isVisible())
            self.assertEqual(controller.preferences.value("bar_position"), start)
        finally:
            controller.close_interface()
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
            socket = QLocalSocket()
            socket.connectToServer(name)
            self.assertTrue(socket.waitForConnected(1000))
            socket.write(b"quit\n")
            socket.flush()
            socket.waitForBytesWritten(1000)
            # Let the server consume and acknowledge the command by closing
            # its endpoint, as the portable handoff test does. Closing this
            # short-lived client immediately can race delivery on CI pipes.
            self.assertTrue(
                socket.state() == QLocalSocket.LocalSocketState.UnconnectedState
                or socket.waitForDisconnected(2000),
                "Quit command was not consumed",
            )
            self.assertEqual(first.wait(timeout=8), 0)
            socket = QLocalSocket()
            socket.connectToServer(name)
            self.assertFalse(socket.waitForConnected(100))
        finally:
            if first.poll() is None:
                first.terminate()
            first.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
