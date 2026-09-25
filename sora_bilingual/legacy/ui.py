"""PySide6 settings and click-through desktop subtitle overlay.

The overlay is a desktop window positioned against a supplied game rectangle;
it is not an in-game/native game UI.  The runtime owns foreground detection,
capture, and persistent configuration.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sora_bilingual.platform.inputs import vk_for_key


DEFAULT_CONFIG = {
    "primary_language": "zh-Hans",
    "secondary_language": "ja",
    "overlay_enabled": True,
    "font_size": 24,
    "secondary_font_size": 21,
    "bottom_offset_percent": 4,
    "width_percent": 80,
    "display_mode": "two_lines",
    "hotkey": {"keyboard": ["CTRL", "SHIFT", "F10"], "gamepad": {}},
}


def _config(config: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            result[key] = deepcopy(value)
    return result


def _language_values(languages: list[Any] | tuple[Any, ...] | None) -> list[tuple[str, str]]:
    if not languages:
        return [
            ("zh-Hans", "简体中文"),
            ("zh-Hant", "繁體中文"),
            ("ja", "日本語"),
            ("en", "English"),
            ("ko", "한국어"),
            ("fr", "Français"),
            ("de", "Deutsch"),
            ("es", "Español"),
        ]
    values: list[tuple[str, str]] = []
    for language in languages:
        if isinstance(language, dict):
            code = str(language.get("code", language.get("id", "")))
            label = str(language.get("name", code))
        elif isinstance(language, (list, tuple)) and len(language) >= 2:
            code, label = str(language[0]), str(language[1])
        else:
            code = label = str(language)
        if code:
            values.append((code, label))
    return values


class SettingsWindow(QWidget):
    attach_requested = Signal()
    settings_changed = Signal(dict)

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        languages: list[Any] | None = None,
        callbacks: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.callbacks = callbacks or {}
        self.config = _config(config)
        self._updating = False
        self._recording_keyboard = False
        self.setWindowTitle("Sora Bilingual Subtitles")
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.primary = QComboBox()
        self.secondary = QComboBox()
        for code, label in _language_values(languages):
            self.primary.addItem(label, code)
            self.secondary.addItem(label, code)
        self.enabled = QCheckBox("启用桌面外挂字幕")
        self.font_size = QSpinBox()
        self.font_size.setRange(12, 96)
        self.font_size.setSuffix(" px")
        self.bottom_offset = QSpinBox()
        self.bottom_offset.setRange(0, 35)
        self.bottom_offset.setSuffix(" %")
        self.width = QSpinBox()
        self.width.setRange(25, 100)
        self.width.setSuffix(" %")
        self.mode = QComboBox()
        self.mode.addItem("双语两行", "two_lines")
        self.mode.addItem("仅副字幕", "secondary_only")
        form.addRow("主语言", self.primary)
        form.addRow("副语言", self.secondary)
        form.addRow(self.enabled)
        form.addRow("字号", self.font_size)
        form.addRow("距游戏底部", self.bottom_offset)
        form.addRow("字幕宽度", self.width)
        form.addRow("显示模式", self.mode)
        layout.addLayout(form)

        hotkey_row = QHBoxLayout()
        self.hotkey_label = QLabel()
        self.record_keyboard = QPushButton("录制键盘组合")
        self.record_controller = QPushButton("录制手柄组合")
        hotkey_row.addWidget(self.hotkey_label, 1)
        hotkey_row.addWidget(self.record_keyboard)
        hotkey_row.addWidget(self.record_controller)
        layout.addLayout(hotkey_row)
        self.device_label = QLabel("手柄状态：等待运行时刷新")
        self.device_label.setWordWrap(True)
        self.status_label = QLabel("未连接")
        self.status_label.setWordWrap(True)
        self.connect_button = QPushButton("连接游戏")
        layout.addWidget(self.device_label)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("显示方式：无边框桌面透明窗（原型，非原生游戏 UI）"))
        self.connect_button.setText("附加已有 Sora_2nd")
        layout.addWidget(self.connect_button)
        self._apply_controls()

        for widget, signal in (
            (self.primary, self.primary.currentIndexChanged),
            (self.secondary, self.secondary.currentIndexChanged),
            (self.enabled, self.enabled.toggled),
            (self.font_size, self.font_size.valueChanged),
            (self.bottom_offset, self.bottom_offset.valueChanged),
            (self.width, self.width.valueChanged),
            (self.mode, self.mode.currentIndexChanged),
        ):
            signal.connect(self._emit_changes)
        self.record_keyboard.clicked.connect(self._begin_keyboard_capture)
        self.record_controller.clicked.connect(self._begin_controller_capture)
        self.connect_button.clicked.connect(self._request_attach)

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_controls(self) -> None:
        self._updating = True
        self._set_combo(self.primary, self.config["primary_language"])
        self._set_combo(self.secondary, self.config["secondary_language"])
        self.enabled.setChecked(bool(self.config["overlay_enabled"]))
        self.font_size.setValue(int(self.config["font_size"]))
        self.bottom_offset.setValue(int(self.config["bottom_offset_percent"]))
        self.width.setValue(int(self.config["width_percent"]))
        self._set_combo(self.mode, self.config["display_mode"])
        self._refresh_hotkey_label()
        self._updating = False

    def _current_config(self) -> dict[str, Any]:
        result = deepcopy(self.config)
        result.update(
            {
                "primary_language": self.primary.currentData(),
                "secondary_language": self.secondary.currentData(),
                "overlay_enabled": self.enabled.isChecked(),
                "font_size": self.font_size.value(),
                "bottom_offset_percent": self.bottom_offset.value(),
                "width_percent": self.width.value(),
                "display_mode": self.mode.currentData(),
            }
        )
        return result

    def _emit_changes(self, *_: Any) -> None:
        if self._updating:
            return
        self.config = self._current_config()
        self.settings_changed.emit(deepcopy(self.config))
        callback = self.callbacks.get("settings_changed")
        if callable(callback):
            callback(deepcopy(self.config))

    def _refresh_hotkey_label(self) -> None:
        binding = self.config.get("hotkey", {})
        keys = binding.get("keyboard", [])
        gamepad = binding.get("gamepad", {})
        buttons = "+".join(f"B{button}" for button in gamepad.get("buttons", []))
        if keys:
            text = "键盘：" + " + ".join(self._key_name(key) for key in keys)
            self.hotkey_label.setText(text + ("；手柄：" + buttons if buttons else ""))
        else:
            self.hotkey_label.setText("手柄：" + buttons)

    @staticmethod
    def _key_name(key: Any) -> str:
        if not isinstance(key, int):
            return str(key)
        sequence = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
        return sequence or hex(key)

    def _begin_keyboard_capture(self) -> None:
        self._recording_keyboard = True
        self.record_keyboard.setText("请按组合键…")
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _begin_controller_capture(self) -> None:
        callback = self.callbacks.get("begin_controller_capture")
        if callable(callback):
            callback()
        self.set_status("请在同一手柄上同时按下组合键")

    def set_controller_binding(self, binding: dict[str, Any]) -> None:
        self.config.setdefault("hotkey", {})["gamepad"] = deepcopy(binding.get("gamepad", {}))
        self._refresh_hotkey_label()
        self._emit_changes()

    def keyPressEvent(self, event: Any) -> None:
        if not self._recording_keyboard:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        sequence = QKeySequence(event.keyCombination()).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        keys = [
            part.strip().upper().replace("CONTROL", "CTRL")
            for part in sequence.split("+")
            if part.strip()
        ]
        if keys and all(vk_for_key(item) is not None for item in keys):
            self.config.setdefault("hotkey", {})["keyboard"] = keys
            self._recording_keyboard = False
            self.record_keyboard.setText("录制键盘组合")
            self._refresh_hotkey_label()
            self._emit_changes()
        elif keys:
            self._recording_keyboard = False
            self.record_keyboard.setText("录制键盘组合")
            self.set_status("该键不支持 Win32 热键轮询；未保存组合")
        event.accept()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_device_status(self, devices: list[str]) -> None:
        detail = "；".join(devices) if devices else "未检测到 SDL 可见手柄"
        self.device_label.setText("手柄状态：" + detail)

    def apply_config(self, config: dict[str, Any]) -> None:
        self.config = _config(config)
        self._apply_controls()

    def _request_attach(self) -> None:
        self.attach_requested.emit()
        callback = self.callbacks.get("attach_requested")
        if callable(callback):
            callback()


class OverlayWindow(QWidget):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.config = _config(config)
        self._game_rect = (0, 0, 1920, 1080)
        self._active = False
        self.frame = QFrame(self)
        self.frame.setObjectName("subtitleFrame")
        self.primary_label = QLabel()
        self.secondary_label = QLabel()
        for label in (self.primary_label, self.secondary_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(2)
        layout.addWidget(self.primary_label)
        layout.addWidget(self.secondary_label)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.apply_config(self.config)

    def set_lines(self, primary: str, secondary: str) -> None:
        self.primary_label.setText(primary or "")
        self.secondary_label.setText(secondary or "")
        self._relayout()

    def set_game_rect(self, x: int, y: int, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self._game_rect = (x, y, width, height)
            self._relayout()

    def apply_config(self, config: dict[str, Any]) -> None:
        self.config = _config(config)
        size = int(self.config["font_size"])
        secondary_size = int(self.config["secondary_font_size"])
        self.primary_label.setStyleSheet(f"color: white; font-size: {size}px; font-weight: 600;")
        self.secondary_label.setStyleSheet(f"color: #f2d98b; font-size: {secondary_size}px;")
        self.frame.setStyleSheet(
            "QFrame#subtitleFrame { background-color: rgba(0, 0, 0, 160); border-radius: 7px; }"
        )
        self.primary_label.setVisible(self.config["display_mode"] == "two_lines")
        self._relayout()
        if self._active and self.config["overlay_enabled"]:
            self.show()
        else:
            self.hide()

    def _relayout(self) -> None:
        x, y, game_width, game_height = self._game_rect
        width = max(220, int(game_width * int(self.config["width_percent"]) / 100))
        font_size = int(self.config["font_size"])
        content_width = max(1, width - 36)
        secondary_height = (
            self.secondary_label.fontMetrics()
            .boundingRect(
                QRect(0, 0, content_width, 10000),
                Qt.TextFlag.TextWordWrap,
                self.secondary_label.text(),
            )
            .height()
        )
        primary_height = 0
        if self.config["display_mode"] == "two_lines":
            primary_height = (
                self.primary_label.fontMetrics()
                .boundingRect(
                    QRect(0, 0, content_width, 10000),
                    Qt.TextFlag.TextWordWrap,
                    self.primary_label.text(),
                )
                .height()
            )
        height = max(font_size + 30, primary_height + secondary_height + 30)
        left = x + (game_width - width) // 2
        bottom = (
            y + game_height - int(game_height * int(self.config["bottom_offset_percent"]) / 100)
        )
        self.setGeometry(left, bottom - height, width, height)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if self._active and self.config["overlay_enabled"]:
            self.show()
        else:
            self.hide()


def create_ui(
    callbacks: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    languages: list[Any] | None = None,
) -> tuple[SettingsWindow, OverlayWindow]:
    settings = SettingsWindow(config, languages, callbacks)
    overlay = OverlayWindow(config)
    settings.settings_changed.connect(overlay.apply_config)
    return settings, overlay
