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

from PySide6.QtCore import Qt, QTimer, QEvent, Signal, QSignalBlocker
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QSlider,
    QInputDialog,
    QDialog,
    QScrollArea,
    QFrame,
    QButtonGroup,
)

from sora_bilingual.platform.inputs import vk_for_key, InputManager
from sora_bilingual.app.i18n import UI_LANGUAGES, set_language, tr
from sora_bilingual.app.ui_widgets import (
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QRadioButton,
    QDoubleSpinBox,
    ColorButton,
    QFormLayout,
    QTabWidget,
    apply_native_theme,
    retranslate,
)
from sora_bilingual.config.native_config import (
    read_config,
    normalize_config,
    DEFAULT_BINDINGS,
    DEFAULTS,
    ACTIONS,
    LANGUAGE_DEFAULTS_PENDING,
    replace_file,
)
from sora_bilingual.config.locales import (
    LOCALES,
    DEFAULT_PRIMARY,
    DEFAULT_SECONDARY,
)


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
    "secondary_color": DEFAULTS["secondary_color"],
    "secondary_opacity": DEFAULTS["secondary_opacity"],
    "bilingual_offset_y": 0,
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


def configure_first_run(path: Path = CONTROL_PATH) -> bool:
    """Collect only the local UI locale before the first connection."""
    if path.exists():
        read_config(path)  # Validate without rewriting an existing user's choices.
        return True
    ui_choices = [(code, UI_LANGUAGES[code]) for code in ("zh-Hans", "en", "ja")]
    ui_dialog = QInputDialog()
    ui_dialog.setWindowTitle("Select interface language")
    ui_dialog.setLabelText("选择界面语言 / Choose interface language / 画面言語を選択")
    ui_dialog.setComboBoxItems([label for _, label in ui_choices])
    ui_dialog.setComboBoxEditable(False)
    ui_dialog.setOkButtonText("OK")
    ui_dialog.setCancelButtonText("Cancel")
    if ui_dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    ui_language = next(
        (code for code, label in ui_choices if label == ui_dialog.textValue()), "zh-Hans"
    )
    set_language(ui_language)
    # Only a newly created control file is eligible for source-derived display
    # defaults. Existing files, including an empty legacy file, are left alone.
    update_control({"ui_language": ui_language, LANGUAGE_DEFAULTS_PENDING: True}, path)
    return True


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
    language_changed = any(
        key in patch and patch[key] != latest.get(key) for key in ("primary", "secondary")
    )
    # Freeze the legacy binding before a mode change can influence migration.
    if "switch_binding" not in result and any(k in latest for k in ("hotkeys", "hotkey")):
        result["switch_binding"] = read_config(path)["switch_binding"]
    for key in (
        "primary",
        "secondary",
        "ui_language",
        "switch_binding",
        "enabled",
        "interaction",
        "mode_request",
        "annotation_scale",
        "secondary_color",
        "secondary_opacity",
        "bilingual_offset_y",
        "ruby_scale",
        "ruby_gap",
        "ruby_offset_x",
        "line_gap",
        "capture_controller",
        "capture_action",
        LANGUAGE_DEFAULTS_PENDING,
    ):
        if key in patch:
            result[key] = deepcopy(patch[key])
    if language_changed:
        # A form may submit both language values with an unrelated setting.
        # Cancel the new-user defaults only when a value actually changed.
        result.pop(LANGUAGE_DEFAULTS_PENDING, None)
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

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def __init__(self, control_path: Path = CONTROL_PATH, status_path: Path = STATUS_PATH) -> None:
        super().__init__()
        self.control_path = Path(control_path)
        self.status_path = Path(status_path)
        set_language(read_control(self.control_path)["ui_language"])
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
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        self.tabs = QTabWidget()
        self.pages = []

        def add_page(page, title):
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages.append(scroll)
            self.tabs.addTab(scroll, title)

        language_page = QWidget()
        self.language_page = language_page
        layout_page = QWidget()
        binding_page = QWidget()
        add_page(language_page, "语言")
        add_page(layout_page, "文字排版")
        add_page(binding_page, "快捷键")
        from sora_bilingual.app.update_ui import UpdatePage

        self.updates = UpdatePage()
        add_page(self.updates, "更新")
        layout.addWidget(self.tabs, 1)
        self.save_notice = QLabel()
        self.save_notice.setWordWrap(True)
        self.save_notice.hide()
        layout.addWidget(self.save_notice)
        language_layout = QVBoxLayout(language_page)
        language_layout.setContentsMargins(16, 16, 16, 16)
        style_layout = QVBoxLayout(layout_page)
        style_layout.setContentsMargins(16, 16, 16, 16)
        binding_layout = QVBoxLayout(binding_page)
        binding_layout.setContentsMargins(16, 16, 16, 16)
        form = QFormLayout()
        style_form = QFormLayout()
        # English labels are wider than the compact panel.  Wrap the field
        # below its label instead of forcing a horizontal scroll area.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        style_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.primary = QComboBox()
        self.secondary = QComboBox()
        self.detected_game_language = QLabel("等待检测")
        self.detected_game_language.setObjectName("liveBadge")
        self.detected_game_language.setAccessibleName("检测到的游戏内文字语言")
        self.detected_game_language.setToolTip("由后端检测，无法在设置中编辑。")
        self.connection_state = QLabel("未连接游戏")
        self.connection_state.setObjectName("liveBadge")
        self.connection_state.setAccessibleName("连接状态")
        self.ui_language = QComboBox()
        for code, label in UI_LANGUAGES.items():
            self.ui_language.addItem(label, code)
        for code, label in LANGUAGES:
            self.primary.addItem(label, code)
            self.secondary.addItem(label, code)
        self.enabled = QCheckBox("启用双语 Mod")
        self.bilingual_mode = QRadioButton("双语模式")
        self.single_mode = QRadioButton("单语言模式")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.bilingual_mode)
        self.mode_group.addButton(self.single_mode)
        self.single_toggle = QRadioButton("按一下切换语言")
        self.single_hold = QRadioButton("按住显示副语言")
        self.single_group = QButtonGroup(self)
        self.single_group.addButton(self.single_toggle)
        self.single_group.addButton(self.single_hold)
        for button in (
            self.bilingual_mode,
            self.single_mode,
            self.single_toggle,
            self.single_hold,
        ):
            button.setAccessibleName(button.property("ui_source"))
        self.annotation_scale = QDoubleSpinBox()
        self.annotation_scale.setRange(0.7, 1.0)
        self.annotation_scale.setSingleStep(0.05)
        self.annotation_scale.setDecimals(2)
        self.secondary_color = ColorButton(
            DEFAULTS["secondary_color"], opacity=DEFAULTS["secondary_opacity"]
        )
        self.secondary_opacity = QSlider(Qt.Orientation.Horizontal)
        self.secondary_opacity.setRange(0, 100)
        self.secondary_opacity.setSingleStep(1)
        self.secondary_opacity.setPageStep(10)
        self.secondary_opacity.setProperty("ui_accessible_name", "副语言透明度")
        self.secondary_opacity.setProperty("ui_tooltip", "拖动滑块，实时保存副语言透明度。")
        self.secondary_opacity.setAccessibleName(tr("副语言透明度"))
        self.secondary_opacity.setToolTip(tr("拖动滑块，实时保存副语言透明度。"))
        self.secondary_opacity.valueChanged.connect(self._set_secondary_opacity)
        form.addRow("界面语言", self.ui_language)
        form.addRow("主语言", self.primary)
        form.addRow("副语言", self.secondary)
        language_layout.addLayout(form)
        self.connection_button = QPushButton("连接游戏")
        self.connection_button.setObjectName("primaryAction")
        self.connection_button.setAccessibleName("手动连接游戏")
        self.connection_button.setToolTip(
            "请求自动连接器立即重新检查，不会启动游戏或替换现有连接。"
        )
        self.connection_button.clicked.connect(self._retry_connection)
        self.connection_strip = QWidget()
        self.connection_strip.setObjectName("statusFooter")
        connection_layout = QHBoxLayout(self.connection_strip)
        connection_layout.setContentsMargins(10, 6, 10, 6)
        connection_layout.setSpacing(6)
        connection_layout.addWidget(self.connection_state)
        connection_layout.addWidget(self.detected_game_language, 1)
        connection_layout.addWidget(self.connection_button)
        layout.insertWidget(0, self.connection_strip)
        display_heading = self._section_title("显示设置")
        language_layout.addWidget(display_heading)
        self.display_form = display_form = QFormLayout()
        display_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        display_form.addRow(self.enabled)
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(self.bilingual_mode)
        mode_layout.addWidget(self.single_mode)
        mode_layout.addStretch()
        display_form.addRow("显示模式", mode_row)
        self.single_options = QWidget()
        single_layout = QVBoxLayout(self.single_options)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.addWidget(self.single_toggle)
        single_layout.addWidget(self.single_hold)
        display_form.addRow("单语言切换方式", self.single_options)
        color_row = QWidget()
        color_layout = QVBoxLayout(color_row)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(6)
        color_layout.addWidget(self.secondary_color)
        color_layout.addWidget(self.secondary_opacity)
        display_form.addRow("副语言颜色与透明度", color_row)
        language_layout.addLayout(display_form)
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
        self.bilingual_offset_y = QDoubleSpinBox()
        self.bilingual_offset_y.setRange(-24, 24)
        self.bilingual_offset_y.setSingleStep(1)
        for title, spin, factor in [
            ("主语言字号", self.annotation_scale, 100),
            ("副语言字号", self.ruby_scale, 100),
            ("副语言上方间距", self.ruby_gap, 1),
            ("副语言左右偏移", self.ruby_offset_x, 1),
            ("双语文本上下偏移（正值向下）", self.bilingual_offset_y, 1),
            ("多行间距", self.line_gap, 1),
        ]:
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(round(spin.minimum() * factor), round(spin.maximum() * factor))
            spin.setFixedWidth(80)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spin.setAccessibleName(title)
            slider.setAccessibleName(title)
            slider.valueChanged.connect(lambda v, s=spin, f=factor: s.setValue(v / f))

            def sync_slider(value, slider=slider, factor=factor):
                # Moving the slider steps normally; loading/editing a precise
                # value must not round-trip through the slider's integer ticks.
                with QSignalBlocker(slider):
                    slider.setValue(round(value * factor))

            spin.valueChanged.connect(sync_slider)
            row.addWidget(slider, 1)
            row.addWidget(spin)
            style_form.addRow(title, container)
        for spin in (
            self.annotation_scale,
            self.ruby_scale,
            self.ruby_gap,
            self.ruby_offset_x,
            self.bilingual_offset_y,
            self.line_gap,
        ):
            spin.setKeyboardTracking(False)
        self.retry_language = QPushButton("重试语言切换")
        self.retry_language.clicked.connect(self.select_mode)
        self.retry_language.hide()
        language_layout.addWidget(self.retry_language)
        language_layout.addStretch()
        style_layout.addLayout(style_form)
        self.ruby_scale.setToolTip("以游戏原生注音字号为基准")
        self.ruby_offset_x.setToolTip("负数向左，正数向右")
        note = QLabel("修改实时生效。字号为比例，间距沿用游戏布局单位。")
        note.setObjectName("helpText")
        note.setWordWrap(True)
        style_layout.addWidget(note)
        self.reset_layout = QPushButton("恢复推荐排版")
        self.reset_layout.clicked.connect(self._reset_layout)
        style_layout.addWidget(self.reset_layout)
        style_layout.addStretch()
        self.binding_action = QComboBox()
        for title, action in [
            ("切换语言", "switch"),
            ("展开 / 隐藏界面", "overlay"),
        ]:
            self.binding_action.addItem(title, action)
        binding_form = QFormLayout()
        binding_form.addRow("操作", self.binding_action)
        binding_layout.addLayout(binding_form)
        self.hotkey_label = QLabel()
        self.binding_label = QLabel()
        self.record_keyboard = QPushButton("录制键盘组合")
        self.record_controller = QPushButton("录制手柄组合")
        for label, button in (
            (self.hotkey_label, self.record_keyboard),
            (self.binding_label, self.record_controller),
        ):
            label.setWordWrap(True)
            row = QHBoxLayout()
            row.addWidget(label, 1)
            row.addWidget(button)
            binding_layout.addLayout(row)
        self.capture_help = QLabel()
        self.capture_help.setObjectName("helpText")
        self.capture_help.setWordWrap(True)
        self.capture_help.hide()
        binding_layout.addWidget(self.capture_help)
        self.clear_controller = QPushButton("清除手柄绑定")
        self.clear_controller.clicked.connect(self._clear_controller)
        binding_layout.addWidget(self.clear_controller)
        self.cancel_capture = QPushButton("取消录制")
        self.cancel_capture.clicked.connect(self._cancel_capture)
        self.cancel_capture.hide()
        binding_layout.addWidget(self.cancel_capture)
        self.binding_notice = QLabel("")
        self.binding_notice.setWordWrap(True)
        self.binding_notice.hide()
        binding_layout.addWidget(self.binding_notice)
        self.backend_label = QLabel("后端状态：等待状态文件")
        self.device_label = QLabel()
        self.device_label.setWordWrap(True)
        self.device_label.setObjectName("helpText")
        binding_layout.addWidget(self.device_label)
        binding_layout.addStretch()
        self.backend_label.setWordWrap(True)
        self.status_footer = QWidget()
        self.status_footer.setObjectName("statusFooter")
        status_layout = QVBoxLayout(self.status_footer)
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.addWidget(self.backend_label)
        layout.addWidget(self.status_footer)

        for signal in (
            self.primary.currentIndexChanged,
            self.secondary.currentIndexChanged,
            self.enabled.toggled,
            self.annotation_scale.valueChanged,
            self.ui_language.currentIndexChanged,
            self.ruby_scale.valueChanged,
            self.ruby_gap.valueChanged,
            self.ruby_offset_x.valueChanged,
            self.bilingual_offset_y.valueChanged,
            self.line_gap.valueChanged,
        ):
            signal.connect(self._save_form)
        self.secondary_color.colorChanged.connect(self._save_form)
        self.secondary_color.opacityChanged.connect(self._save_form)
        self.secondary_color.opacityChanged.connect(self._sync_secondary_opacity)
        for button in (self.bilingual_mode, self.single_mode, self.single_toggle, self.single_hold):
            button.toggled.connect(self._mode_changed)
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
        retranslate(self)

    @property
    def capturing(self):
        return self._recording_keyboard or self._capture_action is not None

    def _binding(self, control, action):
        return control["overlay_binding"] if action == "overlay" else control["switch_binding"]

    def _set_secondary_opacity(self, value: int) -> None:
        """Keep the visible slider and the color dialog on one normalized alpha value."""
        self.secondary_color.set_color(self.secondary_color.color(), opacity=value / 100, emit=True)

    def _sync_secondary_opacity(self, value: float) -> None:
        with QSignalBlocker(self.secondary_opacity):
            self.secondary_opacity.setValue(round(value * 100))

    def _save_binding(self, action, binding):
        patch = (
            {"overlay_binding": binding}
            if action == "overlay"
            else {
                "switch_binding": {**read_control(self.control_path)["switch_binding"], **binding}
            }
        )
        update_control(patch, self.control_path)
        self.settings_changed.emit()
        self.reload_control()
        self.binding_notice.setText("绑定已保存")
        self.binding_notice.show()

    def _binding_error(self, message):
        self.binding_notice.setText(message)
        self.binding_notice.show()
        self.backend_label.setText(message)

    def _clear_controller(self):
        self._save_binding(self.binding_action.currentData(), {"gamepad": {}})

    def _cancel_capture(self):
        self._recording_keyboard = False
        self._capture_action = None
        self.record_keyboard.setText("录制键盘组合")
        self.record_controller.setText("录制手柄组合")
        self._update_capture_controls()

    def _update_capture_controls(self):
        self.cancel_capture.setVisible(self.capturing)
        self.capture_help.setVisible(self.capturing)
        self.binding_action.setEnabled(not self.capturing)
        self.record_keyboard.setEnabled(not self.capturing)
        self.record_controller.setEnabled(not self.capturing)
        self.clear_controller.setEnabled(not self.capturing)

    def _reset_layout(self):
        update_control(
            dict(
                annotation_scale=0.85,
                ruby_scale=0.90,
                ruby_gap=0,
                ruby_offset_x=0,
                bilingual_offset_y=0,
                line_gap=6,
            ),
            self.control_path,
        )
        self.reload_control()
        self.settings_changed.emit()

    def select_mode(self):
        update_control(
            {"interaction": self._selected_interaction(), "mode_request": time.time_ns()},
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

    def _retry_connection(self) -> None:
        """Ask the resident connector for one safe retry; it owns spawn policy."""
        self.enable_auto_connect()
        retry = getattr(self._auto_connector, "retry", None)
        if not callable(retry):
            self.connection_button.setText("连接器准备中…")
            self.connection_button.setEnabled(False)
            self.backend_label.setText("自动连接器正在准备，请稍候…")
            return
        try:
            requested = retry()
        except Exception as exc:
            self.backend_label.setText("重新连接请求失败：" + str(exc))
            self.connection_button.setText("重新连接")
            self.connection_button.setEnabled(True)
            return
        if requested is False:
            self.connection_button.setText("连接器已关闭")
            self.connection_button.setEnabled(False)
            self.backend_label.setText("自动连接器已关闭，无法请求重新连接。")
            return
        self.connection_button.setText("正在重新连接…")
        self.connection_button.setEnabled(False)
        self.backend_label.setText("已请求重新连接，正在检查游戏状态…")

    def _update_connection_action(self, status: dict[str, Any], fresh: bool) -> None:
        connector = self._auto_connector
        phase = str(status.get("phase") or "")
        process = getattr(connector, "process", None)
        connecting = phase in ("connecting", "preparing", "applying") or (
            process is not None and process.poll() is None
        )
        if fresh and not connecting:
            self.connection_button.hide()
            return
        self.connection_button.show()
        if connecting:
            self.connection_button.setText("正在连接…")
            self.connection_button.setEnabled(False)
        else:
            self.connection_button.setText(
                "重新连接" if connector and connector.error else "连接游戏"
            )
            self.connection_button.setEnabled(True)

    def enable_auto_connect(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        if self._auto_connector is None:
            self._auto_connector = AutoConnector(self.status_path)

    def reload_control(self) -> None:
        control = read_control(self.control_path)
        self._updating = True
        self._set_combo(self.ui_language, control["ui_language"])
        self._set_combo(self.primary, str(control["primary"]))
        self._set_combo(self.secondary, str(control["secondary"]))
        self.secondary_color.set_color(
            control.get("secondary_color", DEFAULTS["secondary_color"]),
            opacity=control.get("secondary_opacity", DEFAULTS["secondary_opacity"]),
        )
        self._sync_secondary_opacity(self.secondary_color.opacity())
        self.enabled.setChecked(bool(control["enabled"]))
        self._set_interaction(str(control["interaction"]))
        self.annotation_scale.setValue(float(control["annotation_scale"]))
        self.ruby_scale.setValue(float(control["ruby_scale"]))
        self.ruby_gap.setValue(float(control["ruby_gap"]))
        self.line_gap.setValue(float(control["line_gap"]))
        self.ruby_offset_x.setValue(float(control["ruby_offset_x"]))
        self.bilingual_offset_y.setValue(float(control.get("bilingual_offset_y", 0)))
        keys = self._binding(control, self.binding_action.currentData()).get("keyboard", [])
        self.hotkey_label.setText("键盘：" + " + ".join(str(key) for key in keys))
        self.clear_controller.setVisible(
            bool(self._binding(control, self.binding_action.currentData()).get("gamepad"))
        )
        self._updating = False
        self._loaded = control

    def _save_form(self, *_: Any) -> None:
        if self._updating:
            return
        values = {
            "ui_language": self.ui_language.currentData(),
            "primary": self.primary.currentData(),
            "secondary": self.secondary.currentData(),
            "enabled": self.enabled.isChecked(),
            "interaction": self._selected_interaction(),
            "annotation_scale": self.annotation_scale.value(),
            "secondary_color": list(self.secondary_color.color()),
            "secondary_opacity": self.secondary_color.opacity(),
            "ruby_scale": self.ruby_scale.value(),
            "ruby_gap": self.ruby_gap.value(),
            "ruby_offset_x": self.ruby_offset_x.value(),
            "bilingual_offset_y": self.bilingual_offset_y.value(),
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
                self.save_notice.setText("未保存：" + str(exc))
                self.save_notice.show()
                return
            self.save_notice.hide()
            self.reload_control()
            if "ui_language" in patch:
                set_language(values["ui_language"])
                retranslate(self)
            self.settings_changed.emit()

    def _selected_interaction(self) -> str:
        if self.bilingual_mode.isChecked():
            return "annotation"
        return "language_hold" if self.single_hold.isChecked() else "language_toggle"

    def _set_interaction(self, interaction: str) -> None:
        self.bilingual_mode.setChecked(interaction == "annotation")
        self.single_mode.setChecked(interaction != "annotation")
        self.single_hold.setChecked(interaction == "language_hold")
        self.single_toggle.setChecked(interaction != "language_hold")
        self.display_form.setRowVisible(self.single_options, interaction != "annotation")

    def _mode_changed(self, checked: bool) -> None:
        if not checked or self._updating:
            return
        self.display_form.setRowVisible(self.single_options, self.single_mode.isChecked())
        self._save_form()

    def _present_source_language(self, status: dict[str, Any]) -> None:
        detected = status.get("detected_game_language")
        source_status = str(status.get("source_language_status") or "").strip()
        if detected in LOCALES:
            label = LOCALES[detected].name
            suffix = " · " + source_status if source_status else ""
            self.detected_game_language.setText(label + suffix)
            self.detected_game_language.setToolTip("后端已检测到游戏内文字语言。")
        else:
            self.detected_game_language.setText("等待检测")
            self.detected_game_language.setToolTip(
                "等待后端检测游戏内文字语言。"
                + (" 检测状态：" + source_status if source_status else "")
            )

    def _present_connection_state(self, status: dict[str, Any], fresh: bool) -> None:
        """Keep the connection truth beside the read-only source detection."""
        connector = self._auto_connector
        process = getattr(connector, "process", None)
        phase = str(status.get("phase") or "")
        connecting = phase in ("connecting", "preparing", "applying") or (
            process is not None and process.poll() is None
        )
        failed = bool(status.get("failed") or status.get("error") or self._connection_error)
        if connecting:
            text = "正在连接游戏"
            tooltip = "正在连接已有游戏进程，请稍候。"
        elif fresh:
            text = "已连接"
            tooltip = "已连接到游戏，设置会实时同步。"
        elif failed:
            text = "连接异常"
            tooltip = "连接未完成；可使用下方按钮重新连接。"
        else:
            text = "未连接游戏"
            tooltip = "等待已有游戏进程；可离线调整设置。"
        self.connection_state.setText(text)
        self.connection_state.setToolTip(tr(tooltip))

    def _begin_keyboard_capture(self) -> None:
        self._cancel_capture()
        self.binding_notice.clear()
        self.binding_notice.hide()
        self._keyboard_action = self.binding_action.currentData()
        self._keyboard_deadline = time.monotonic() + 30
        self._recording_keyboard = True
        self.capture_help.setText("按下组合键保存；Esc 取消。")
        self._update_capture_controls()
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
        self._update_capture_controls()
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
        self.binding_notice.hide()
        self._capture_action = self.binding_action.currentData()
        self.capture_help.setText("先松开所有按键，再按住组合，全部松开后保存。")
        self._update_capture_controls()
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
            self._update_capture_controls()
            self.record_controller.setText("录制手柄组合")
            self.reload_control()
        elif self._controller.capture_status == "timed_out":
            self._capture_action = None
            self._update_capture_controls()
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
            self._present_source_language({})
            self._present_connection_state({}, False)
            self._update_connection_action({}, False)
            self.backend_label.setText("后端状态：状态文件读取失败：" + str(exc))
            return
        self._present_source_language(status)
        if self.isVisible() and self.tabs.currentIndex() == 2:
            devices = [device.name for device in self._controller.devices()]
            self.device_label.setText("设备：" + ("；".join(devices) or "未检测到手柄，可使用键盘"))
        else:
            devices = status.get("devices", [])
            if devices:
                self.device_label.setText("设备：" + "；".join(map(str, devices)))
        fresh = status.get("running") and 0 <= time.time() - status.get("updated_at", 0) < 5
        self._present_connection_state(status, bool(fresh))
        self._update_connection_action(status, bool(fresh))
        self.retry_language.setVisible(bool(fresh and status.get("reload_error")))
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
            self.backend_label.setText(status["reload_error"])
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
    apply_native_theme(app)
    if not configure_first_run(args.control):
        return 0
    window = NativeSettingsWindow(args.control, args.status)
    window.show()
    if args.connect:
        QTimer.singleShot(200, window._start_backend)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
