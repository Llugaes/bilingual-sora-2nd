"""Native settings and explicit connection to an already-running game.

Configuration and controller recording work offline. Connecting starts the
independent resident backend; closing this window does not unload game hooks.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import time
import subprocess
import sys
from typing import Any

from PySide6.QtCore import Qt, QTimer, QEvent, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QSlider,
)

from sora_bilingual.platform.inputs import vk_for_key, InputManager
from sora_bilingual.config.native_config import (
    read_config,
    normalize_config,
    DEFAULT_BINDINGS,
    ACTIONS,
    replace_file,
)
from sora_bilingual.config.locales import LOCALES, DEFAULT_PRIMARY, DEFAULT_SECONDARY


from sora_bilingual.paths import ROOT

CONTROL_PATH = ROOT / "generated" / "native-control.json"
STATUS_PATH = ROOT / "generated" / "native-status.json"
LANGUAGES = tuple((code, locale.name) for code, locale in LOCALES.items())
DEFAULT_CONTROL = {
    "primary": DEFAULT_PRIMARY,
    "secondary": DEFAULT_SECONDARY,
    "enabled": True,
    "interaction": "annotation",
    "annotation_scale": 0.9,
    "hotkey": {"keyboard": ["CTRL", "SHIFT", "F10"], "gamepad": {}},
}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 必须是 JSON 对象")
    return data


def read_control(path: Path = CONTROL_PATH) -> dict[str, Any]:
    """Read a fresh control snapshot without modifying it."""
    control = deepcopy(DEFAULT_CONTROL)
    disk = read_config(path)
    control.update(disk)
    hotkey = deepcopy(DEFAULT_CONTROL["hotkey"])
    if isinstance(disk.get("hotkey"), dict):
        hotkey.update(disk["hotkey"])
    control["hotkey"] = hotkey
    return control


def valid_keyboard_keys(keys: list[str] | tuple[str, ...]) -> list[str] | None:
    """Return normalized keys only when every member has a Win32 mapping."""
    normalized = [str(key).strip().upper().replace("CONTROL", "CTRL") for key in keys]
    if not normalized or not all(vk_for_key(key) is not None for key in normalized):
        return None
    return normalized


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        replace_file(handle.name, path)
    except Exception:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass
        raise


def update_control(patch: dict[str, Any], path: Path = CONTROL_PATH) -> dict[str, Any]:
    """Atomically merge UI-owned settings into the latest on-disk control.

    ``sources`` and ``stop`` are backend-owned and are always left untouched.
    Per-action updates preserve the other actions and unedited binding fields.
    """
    if "sources" in patch or "stop" in patch:
        raise ValueError("sources 和 stop 由后端管理，设置窗口不能修改")
    latest = _read_json_object(path)
    result = deepcopy(latest)
    for key in (
        "primary",
        "secondary",
        "game_language",
        "enabled",
        "interaction",
        "mode_request",
        "annotation_scale",
        "ruby_scale",
        "ruby_gap",
        "ruby_offset_x",
        "line_gap",
        "capture_controller",
        "capture_action",
    ):
        if key in patch:
            result[key] = deepcopy(patch[key])
    if "hotkey" in patch:
        requested = patch["hotkey"]
        if not isinstance(requested, dict) or set(requested) - {"keyboard"}:
            raise ValueError("设置窗口只允许更新键盘组合；手柄绑定由后端同步")
        keyboard = valid_keyboard_keys(requested.get("keyboard", []))
        if keyboard is None:
            raise ValueError("键盘组合含不支持的 Win32 按键")
        current = (
            deepcopy(latest.get("hotkey", {})) if isinstance(latest.get("hotkey"), dict) else {}
        )
        current["keyboard"] = keyboard
        result["hotkey"] = current
    if "hotkeys" in patch:
        current = read_config(path)["hotkeys"]
        for action, binding in patch["hotkeys"].items():
            if action not in ACTIONS:
                raise ValueError("未知快捷键动作")
            if "keyboard" in binding:
                keys = valid_keyboard_keys(binding["keyboard"])
                if keys is None:
                    raise ValueError("不支持的键盘组合")
                current[action]["keyboard"] = keys
            if "gamepad" in binding:
                current[action]["gamepad"] = deepcopy(binding["gamepad"])
        result["hotkeys"] = current
    if "overlay_binding" in patch:
        binding = deepcopy(read_config(path)["overlay_binding"])
        binding.update(patch["overlay_binding"])
        if binding.get("keyboard") and valid_keyboard_keys(binding["keyboard"]) is None:
            raise ValueError("不支持的面板键盘组合")
        result["overlay_binding"] = binding
    result = normalize_config(result)
    _atomic_write(path, result)
    return read_control(path)


def load_cjk_font(app: QApplication) -> None:
    """Load system CJK fonts explicitly; unavailable candidates are harmless."""
    from PySide6.QtGui import QFontDatabase

    families: list[str] = []
    for font_path in (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\YuGothM.ttc"),
        Path(r"C:\Windows\Fonts\YuGothR.ttc"),
    ):
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))
    app.setFont(QFont(families[0] if families else "Microsoft YaHei UI", 10))


class NativeSettingsWindow(QWidget):
    settings_changed = Signal()

    def __init__(self, control_path: Path = CONTROL_PATH, status_path: Path = STATUS_PATH) -> None:
        super().__init__()
        self.control_path = Path(control_path)
        self.status_path = Path(status_path)
        self._updating = False
        self._recording_keyboard = False
        self._controller = InputManager()
        self._capture_action = None
        self._keyboard_action = None
        self._loaded = {}
        self._connect_process = None
        self._connection_error = None
        self._auto_connector = None
        self.setWindowTitle("Sora Native 双语设置")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        self.connect_backend = QLabel("自动关联已运行的游戏；游戏稍后启动也会自动连接")
        layout.addWidget(self.connect_backend)
        self.tabs = QTabWidget()
        language_page = QWidget()
        layout_page = QWidget()
        binding_page = QWidget()
        self.tabs.addTab(language_page, "语言与模式")
        self.tabs.addTab(layout_page, "字号与位置")
        self.tabs.addTab(binding_page, "按键绑定")
        from sora_bilingual.app.update_ui import UpdatePage

        self.updates = UpdatePage()
        self.tabs.addTab(self.updates, "版本更新")
        layout.addWidget(self.tabs)
        language_layout = QVBoxLayout(language_page)
        style_layout = QVBoxLayout(layout_page)
        binding_layout = QVBoxLayout(binding_page)
        form = QFormLayout()
        style_form = QFormLayout()
        self.primary = QComboBox()
        self.secondary = QComboBox()
        self.game_language = QComboBox()
        for code, label in LANGUAGES:
            self.primary.addItem(label, code)
            self.secondary.addItem(label, code)
            self.game_language.addItem(label, code)
        self.enabled = QCheckBox("启用双语 Mod")
        self.interaction = QComboBox()
        self.interaction.addItem("同时显示双语", "annotation")
        self.interaction.addItem("按一下切换语言", "language_toggle")
        self.interaction.addItem("按住显示副语言", "language_hold")
        self.annotation_scale = QDoubleSpinBox()
        self.annotation_scale.setRange(0.7, 1.0)
        self.annotation_scale.setSingleStep(0.05)
        self.annotation_scale.setDecimals(2)
        form.addRow("主语言", self.primary)
        form.addRow("副语言", self.secondary)
        form.addRow(self.enabled)
        form.addRow("显示模式", self.interaction)
        self.ruby_scale = QDoubleSpinBox()
        self.ruby_scale.setRange(0.5, 1)
        self.ruby_scale.setSingleStep(0.05)
        self.ruby_gap = QDoubleSpinBox()
        self.ruby_gap.setRange(0, 8)
        self.ruby_gap.setSingleStep(1)
        self.line_gap = QDoubleSpinBox()
        self.line_gap.setRange(0, 24)
        self.line_gap.setSingleStep(1)
        self.ruby_offset_x = QDoubleSpinBox()
        self.ruby_offset_x.setRange(-24, 24)
        self.ruby_offset_x.setSingleStep(1)
        for title, spin, factor in [
            ("主文字号比例", self.annotation_scale, 100),
            ("副字相对原生注音比例", self.ruby_scale, 100),
            ("副字向上偏移 / 间距", self.ruby_gap, 1),
            ("副字水平偏移（右为正）", self.ruby_offset_x, 1),
            ("多行额外行距", self.line_gap, 1),
        ]:
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(round(spin.minimum() * factor), round(spin.maximum() * factor))
            spin.setFixedWidth(80)
            slider.valueChanged.connect(lambda v, s=spin, f=factor: s.setValue(v / f))
            spin.valueChanged.connect(lambda v, s=slider, f=factor: s.setValue(round(v * f)))
            row.addWidget(slider, 1)
            row.addWidget(spin)
            style_form.addRow(title, container)
        for spin in (
            self.annotation_scale,
            self.ruby_scale,
            self.ruby_gap,
            self.ruby_offset_x,
            self.line_gap,
        ):
            spin.setKeyboardTracking(False)
        language_layout.addLayout(form)
        self.apply_mode = QPushButton("立即切换到所选模式")
        self.apply_mode.clicked.connect(self.select_mode)
        language_layout.addWidget(self.apply_mode)
        note = QLabel(
            "同时显示：普通文本用上方小字注解；过场字幕用整段上下双语。\n按住副语言时临时覆盖当前显示，松开恢复。"
        )
        note.setWordWrap(True)
        language_layout.addWidget(note)
        language_layout.addStretch()
        source_toggle = QPushButton("高级：原文识别")
        source_toggle.setCheckable(True)
        source_box = QWidget()
        source_form = QFormLayout(source_box)
        source_note = QLabel(
            "这是游戏输出文本的来源，仅在更改游戏自身语言后调整。\n主语言决定 Mod 显示的正文；切换主语言无需改此项。"
        )
        source_note.setWordWrap(True)
        source_form.addRow(source_note)
        source_form.addRow("识别源语言（与游戏设置一致）", self.game_language)
        source_box.hide()
        source_toggle.toggled.connect(source_box.setVisible)
        language_layout.addWidget(source_toggle)
        language_layout.addWidget(source_box)
        style_layout.addLayout(style_form)
        note = QLabel(
            "修改自动保存并热应用。偏移和行距采用游戏布局单位。\n原文自带注音、强调点的位置保持不变；只调整新增的副语言层。\n这些参数用于注解文本；过场字幕继续使用原生上下段落排版。"
        )
        note.setWordWrap(True)
        style_layout.addWidget(note)
        self.reset_layout = QPushButton("恢复推荐排版")
        self.reset_layout.clicked.connect(self._reset_layout)
        style_layout.addWidget(self.reset_layout)
        style_layout.addStretch()
        row = QHBoxLayout()
        self.binding_action = QComboBox()
        for title, action in [
            ("同时显示双语 / 主语言", "annotation"),
            ("单击切换语言", "language_toggle"),
            ("按住副语言", "language_hold"),
            ("展开 / 隐藏界面", "overlay"),
        ]:
            self.binding_action.addItem(title, action)
        binding_layout.addWidget(self.binding_action)
        self.hotkey_label = QLabel()
        self.record_keyboard = QPushButton("录制键盘组合")
        self.record_controller = QPushButton("录制手柄组合")
        row.addWidget(self.hotkey_label, 1)
        row.addWidget(self.record_keyboard)
        row.addWidget(self.record_controller)
        binding_layout.addLayout(row)
        note = QLabel(
            "三个显示动作同时有效，游戏在前台时响应。\n录制键盘：按下组合键；Esc 取消。\n录制手柄：先松开所有按键和摇杆，再按住组合，全部松开后保存。"
        )
        note.setWordWrap(True)
        binding_layout.addWidget(note)
        self.clear_controller = QPushButton("清除该动作的手柄绑定")
        self.clear_controller.clicked.connect(self._clear_controller)
        binding_layout.addWidget(self.clear_controller)
        self.cancel_capture = QPushButton("取消录制")
        self.cancel_capture.clicked.connect(self._cancel_capture)
        binding_layout.addWidget(self.cancel_capture)
        self.binding_notice = QLabel("")
        self.binding_notice.setWordWrap(True)
        binding_layout.addWidget(self.binding_notice)
        self.backend_label = QLabel("后端状态：等待状态文件")
        self.device_label = QLabel("设备：等待后端上报")
        self.binding_label = QLabel("手柄绑定：由后端同步")
        for label in (self.device_label, self.binding_label):
            label.setWordWrap(True)
            binding_layout.addWidget(label)
        binding_layout.addStretch()
        self.backend_label.setWordWrap(True)
        layout.addWidget(self.backend_label)

        for signal in (
            self.primary.currentIndexChanged,
            self.secondary.currentIndexChanged,
            self.enabled.toggled,
            self.interaction.currentIndexChanged,
            self.annotation_scale.valueChanged,
            self.game_language.currentIndexChanged,
            self.ruby_scale.valueChanged,
            self.ruby_gap.valueChanged,
            self.ruby_offset_x.valueChanged,
            self.line_gap.valueChanged,
        ):
            signal.connect(self._save_form)
        self.record_keyboard.clicked.connect(self._begin_keyboard_capture)
        self.record_controller.clicked.connect(self._request_controller_capture)
        self.binding_action.currentIndexChanged.connect(self.reload_control)
        self.reload_control()
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.refresh_status)
        self._status_timer.start(600)
        self._capture_timer = QTimer(self)
        self._capture_timer.timeout.connect(self._poll_controller)
        self._capture_timer.start(16)
        self.refresh_status()
        QApplication.instance().installEventFilter(self)

    @property
    def capturing(self):
        return self._recording_keyboard or self._capture_action is not None

    def _binding(self, control, action):
        return control["overlay_binding"] if action == "overlay" else control["hotkeys"][action]

    def _save_binding(self, action, binding):
        patch = (
            {"overlay_binding": binding} if action == "overlay" else {"hotkeys": {action: binding}}
        )
        update_control(patch, self.control_path)
        self.settings_changed.emit()
        self.reload_control()
        self.binding_notice.setText("绑定已保存")

    def _binding_error(self, message):
        self.binding_notice.setText(message)
        self.backend_label.setText(message)

    def _clear_controller(self):
        self._save_binding(self.binding_action.currentData(), {"gamepad": {}})

    def _cancel_capture(self):
        self._recording_keyboard = False
        self._capture_action = None
        self.record_keyboard.setText("录制键盘组合")
        self.record_controller.setText("录制手柄组合")

    def _reset_layout(self):
        update_control(
            dict(annotation_scale=0.9, ruby_scale=0.8, ruby_gap=3, ruby_offset_x=0, line_gap=12),
            self.control_path,
        )
        self.reload_control()
        self.settings_changed.emit()

    def select_mode(self):
        update_control(
            {"interaction": self.interaction.currentData(), "mode_request": time.time_ns()},
            self.control_path,
        )
        self.reload_control()
        self.settings_changed.emit()

    def eventFilter(self, watched, event):
        if self.capturing and (
            watched is self or (isinstance(watched, QWidget) and self.isAncestorOf(watched))
        ):
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_capture()
                    return True
                if self._recording_keyboard:
                    self.keyPressEvent(event)
                    return True
        return super().eventFilter(watched, event)

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _start_backend(self):
        if self._auto_connector is not None:
            self._auto_connector.wake.set()
            return
        if self._connect_process is not None and self._connect_process.poll() is None:
            self.backend_label.setText("正在连接，请稍候…")
            return
        try:
            status = _read_json_object(self.status_path)
        except ValueError, OSError:
            status = {}
        if status.get("running") and time.time() - status.get("updated_at", 0) < 5:
            self._connection_error = None
            self.backend_label.setText("后端已连接，直接调整设置即可")
            return
        self._connection_error = None
        executable = Path(sys.executable).with_name("pythonw.exe")
        self._connect_process = subprocess.Popen(
            [str(executable), "-m", "sora_bilingual.game.native_probe"],
            cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.backend_label.setText("正在连接；首次加载索引需要几秒。不会启动游戏。")

    def enable_auto_connect(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        if self._auto_connector is None:
            self._auto_connector = AutoConnector(self.status_path)

    def reload_control(self) -> None:
        control = read_control(self.control_path)
        self._updating = True
        self._set_combo(self.primary, str(control["primary"]))
        self._set_combo(self.secondary, str(control["secondary"]))
        self._set_combo(self.game_language, str(control["game_language"]))
        self.enabled.setChecked(bool(control["enabled"]))
        self._set_combo(self.interaction, str(control["interaction"]))
        self.annotation_scale.setValue(float(control["annotation_scale"]))
        self.ruby_scale.setValue(float(control["ruby_scale"]))
        self.ruby_gap.setValue(float(control["ruby_gap"]))
        self.line_gap.setValue(float(control["line_gap"]))
        self.ruby_offset_x.setValue(float(control["ruby_offset_x"]))
        keys = self._binding(control, self.binding_action.currentData()).get("keyboard", [])
        self.hotkey_label.setText("键盘：" + " + ".join(str(key) for key in keys))
        self._updating = False
        self._loaded = control

    def _save_form(self, *_: Any) -> None:
        if self._updating:
            return
        values = {
            "primary": self.primary.currentData(),
            "secondary": self.secondary.currentData(),
            "enabled": self.enabled.isChecked(),
            "interaction": self.interaction.currentData(),
            "annotation_scale": self.annotation_scale.value(),
            "game_language": self.game_language.currentData(),
            "ruby_scale": self.ruby_scale.value(),
            "ruby_gap": self.ruby_gap.value(),
            "ruby_offset_x": self.ruby_offset_x.value(),
            "line_gap": self.line_gap.value(),
        }
        patch = {k: v for k, v in values.items() if v != self._loaded.get(k)}
        if patch:
            if "interaction" in patch:
                patch["mode_request"] = time.time_ns()
            try:
                update_control(patch, self.control_path)
            except (OSError, ValueError) as exc:
                self.backend_label.setText("未保存：" + str(exc))
                return
            self.reload_control()
            self.settings_changed.emit()

    def _begin_keyboard_capture(self) -> None:
        self._cancel_capture()
        self.binding_notice.clear()
        self._keyboard_action = self.binding_action.currentData()
        self._keyboard_deadline = time.monotonic() + 30
        self._recording_keyboard = True
        self.record_keyboard.setText("请按组合键…")
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def keyPressEvent(self, event: Any) -> None:
        if not self._recording_keyboard:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            event.accept()
            return
        sequence = QKeySequence(event.keyCombination()).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        keys = [
            part.strip().upper().replace("CONTROL", "CTRL")
            for part in sequence.split("+")
            if part.strip()
        ]
        self._recording_keyboard = False
        self.record_keyboard.setText("录制键盘组合")
        normalized = valid_keyboard_keys(keys)
        if normalized is None:
            self._binding_error("该按键暂不支持；未保存")
        else:
            try:
                self._save_binding(self._keyboard_action, {"keyboard": normalized})
            except (ValueError, OSError) as exc:
                self._binding_error("未保存：" + str(exc))
        event.accept()

    def _request_controller_capture(self) -> None:
        self._cancel_capture()
        self.binding_notice.clear()
        self._capture_action = self.binding_action.currentData()
        self._controller.begin_controller_capture(30)
        self.record_controller.setText("按住组合键后全部松开…")

    def _poll_controller(self):
        if self._recording_keyboard and time.monotonic() > self._keyboard_deadline:
            self._cancel_capture()
            self.record_keyboard.setText("录制超时，点击重试")
        if self._capture_action is None:
            return
        binding = self._controller.poll_capture()
        if binding:
            try:
                self._save_binding(self._capture_action, binding)
            except (ValueError, OSError) as exc:
                self._binding_error("未保存：" + str(exc))
            self._capture_action = None
            self.record_controller.setText("录制手柄组合")
            self.reload_control()
        elif self._controller.capture_status == "timed_out":
            self._capture_action = None
            self.record_controller.setText("录制超时，点击重试")

    def refresh_status(self) -> None:
        if self._connect_process is not None and self._connect_process.poll() is not None:
            if self._connect_process.returncode:
                try:
                    self._connection_error = (
                        (ROOT / "generated" / "native-error.log")
                        .read_text(encoding="utf-8")
                        .strip()
                        .splitlines()[-1]
                    )
                except OSError, IndexError:
                    self._connection_error = "连接未成功，请确认游戏已运行后重试。"
            self._connect_process = None
        try:
            control = read_control(self.control_path)
        except (OSError, ValueError) as exc:
            self.backend_label.setText("配置读取失败：" + str(exc))
            return
        action = self.binding_action.currentData()
        pad = self._binding(control, action).get("gamepad", {})
        buttons = ["按钮 " + str(b + 1) for b in pad.get("buttons", [])]
        axes = [
            "轴 " + str(a["index"] + 1) + (" 正向" if a["direction"] > 0 else " 反向")
            for a in pad.get("axes", [])
        ]
        self.binding_label.setText("手柄：" + (" + ".join(buttons + axes) or "未绑定"))
        try:
            status = _read_json_object(self.status_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.backend_label.setText("后端状态：状态文件读取失败：" + str(exc))
            return
        if self.isVisible() and self.tabs.currentIndex() == 2:
            devices = [device.name for device in self._controller.devices()]
            self.device_label.setText("设备：" + ("；".join(devices) or "未检测到手柄，可使用键盘"))
        else:
            devices = status.get("devices", [])
            if devices:
                self.device_label.setText("设备：" + "；".join(map(str, devices)))
        fresh = status.get("running") and 0 <= time.time() - status.get("updated_at", 0) < 5
        if fresh:
            self._connection_error = None
        if not fresh and self._auto_connector is not None:
            self.backend_label.setText(self._auto_connector.message)
            return
        if self._connection_error:
            self.backend_label.setText("连接失败：" + self._connection_error)
            return
        if not status:
            self.backend_label.setText("未连接游戏 · 可离线调整并保存设置")
            return
        if status.get("running") is False or (
            "updated_at" in status and time.time() - status["updated_at"] > 5
        ):
            self.backend_label.setText("后端状态：未运行或连接已中断")
        elif status.get("phase") in ("connecting", "preparing", "applying"):
            self.backend_label.setText(
                "正在连接并准备索引…"
                if status["phase"] == "connecting"
                else "正在准备语言索引，当前语言继续显示…"
                if status["phase"] == "preparing"
                else "正在应用语言索引…"
            )
        elif status.get("reload_error"):
            self.backend_label.setText(status["reload_error"] + "；可点击“立即切换”重试")
        elif status.get("update_notice"):
            self.backend_label.setText(status["update_notice"])
        elif status.get("stopping"):
            self.backend_label.setText("后端状态：已停用，连接保留至游戏退出")
        elif status.get("failed") or status.get("error"):
            self.backend_label.setText("后端状态：异常，正在恢复原文")
        else:
            self.backend_label.setText(
                "后端状态："
                + str(status.get("render_mode", "运行中"))
                + "；已应用 "
                + str(status.get("modified", 0))
                + " 处；"
                + str(status.get("capture_status", ""))
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Open native probe settings only")
    parser.add_argument("--control", type=Path, default=CONTROL_PATH)
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    parser.add_argument("--connect", action="store_true", help="connect to an already running game")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    load_cjk_font(app)
    window = NativeSettingsWindow(args.control, args.status)
    window.show()
    if args.connect:
        QTimer.singleShot(200, window._start_backend)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
