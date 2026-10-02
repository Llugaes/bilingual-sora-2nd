"""Resident control overlay. Never starts the game or unloads its hooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QEvent, QTimer, QObject, Signal, QPoint, QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QFrame,
    QProgressBar,
    QScrollArea,
)

from sora_bilingual.platform.inputs import InputManager
from sora_bilingual.app.native_settings import (
    NativeSettingsWindow,
    load_cjk_font,
    read_control,
    CONTROL_PATH,
    STATUS_PATH,
    ROOT,
)
from sora_bilingual.platform.win32 import foreground_rect
from sora_bilingual.platform.runtime_process import runtime_executable
from sora_bilingual.app.presentation import describe_state, with_font_status, STATUS_COLORS
from sora_bilingual.app.i18n import set_language, tr
from sora_bilingual.app.ui_widgets import NATIVE_THEME, QLabel, QPushButton, retranslate
from sora_bilingual.app.handbook import (
    SkinSurface,
    BadgeButton,
    artwork,
    draw_slice,
    gear_icon,
    PANEL_INSET,
    CONTENT_LEFT,
    paint_surface,
)
from sora_bilingual.app.appearance import apply_appearance, appearance_for, stylesheet

# Kept as a public alias because preview and regression tests import STYLE.
STYLE = NATIVE_THEME


class JsonSnapshot:
    """Atomic writer may briefly replace files; retain the last valid snapshot."""

    def __init__(self, path):
        self.path = Path(path)
        self.signature = None
        self.value = {}

    def read(self):
        try:
            stat = self.path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature != self.signature:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    self.value = value
                    self.signature = signature
        except OSError, ValueError:
            pass
        return self.value


class DragSurface(QObject):
    """One press is either a click or a drag, using the desktop drag threshold."""

    dragged = Signal(QPoint)
    moved = Signal()
    clicked = Signal()

    def __init__(self, window, surfaces):
        super().__init__(window)
        self._window = window
        self._press = None
        self._dragging = False
        for surface in surfaces:
            surface.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._press = event.globalPosition().toPoint()
                self._offset = self._press - self._window.pos()
                self._dragging = False
                event.accept()
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if event.buttons() & Qt.MouseButton.LeftButton and self._press is not None:
                point = event.globalPosition().toPoint()
                if (point - self._press).manhattanLength() >= QApplication.startDragDistance():
                    self._dragging = True
                if self._dragging:
                    self.dragged.emit(point - self._offset - self._window.pos())
                event.accept()
                return True
        elif (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and self._press is not None
        ):
            distance = (event.globalPosition().toPoint() - self._press).manhattanLength()
            self._press = None
            if self._dragging:
                self.moved.emit()
            elif distance < QApplication.startDragDistance() and watched.rect().contains(
                event.position().toPoint()
            ):
                self.clicked.emit()
            event.accept()
            return True
        elif event.type() in (QEvent.Type.Hide, QEvent.Type.UngrabMouse):
            self._press = None
            self._dragging = False
        return super().eventFilter(watched, event)


class StatusBar(QWidget):
    expand = Signal()
    minimize = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("bar")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 7, 18, 7)
        row.setSpacing(6)
        self.grip = QLabel("⋮")
        self.grip.setStyleSheet("color:#e6d795;")
        self.grip.setToolTip("单击打开设置，按住拖动状态条")
        self.grip.setAccessibleName("单击打开设置，按住拖动状态条")
        row.addWidget(self.grip)
        self.marker = QLabel("○")
        self.marker.setObjectName("statusMarker")
        self.marker.setFixedWidth(14)
        self.marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.marker)
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.open_button = BadgeButton()
        self.open_button.setFixedSize(32, 32)
        self.open_button.setStyleSheet("padding:0;")
        self.open_button.setIcon(gear_icon())
        self.open_button.setIconSize(QSize(20, 20))
        self.open_button.setAccessibleName("打开或关闭设置")
        self.open_button.setToolTip("打开或关闭设置。快捷键显示在状态提示中。")
        self.open_button.clicked.connect(self.expand)
        row.addWidget(self.open_button)
        self.minimize_button = QPushButton("—")
        self.minimize_button.setFixedSize(32, 32)
        self.minimize_button.setStyleSheet("padding:0;font-size:18px;color:#fff1be;")
        self.minimize_button.setAccessibleName("最小化到托盘")
        self.minimize_button.setToolTip("隐藏到托盘；右键托盘图标可彻底退出。")
        self.minimize_button.clicked.connect(self.minimize)
        row.addWidget(self.minimize_button)
        self.setFixedWidth(340)
        # The status text and spare bar surface are easier to target than the
        # compact grip. Buttons are intentionally excluded so their actions
        # remain reliable click targets.
        self.drag_surface = DragSurface(self, (self, self.grip, self.marker, self.status))
        self.drag_surface.clicked.connect(self.expand)
        for surface in (self, self.grip, self.marker, self.status):
            surface.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_appearance("sky")
        self.set_background_transparency(0)

    def set_appearance(self, key):
        apply_appearance(self, key)
        self.setStyleSheet(
            stylesheet(appearance_for(self))
            + "QWidget#bar { background: transparent; border: none; }"
            "QWidget#bar QPushButton { background: transparent; border: none; }"
            "QWidget#bar QPushButton:hover { border: 1px solid #e5cf82; }"
        )

    def set_background_transparency(self, value):
        # One alpha step keeps the visually clear surface hit-testable on
        # Windows layered windows. Text/icons never inherit this alpha.
        self._background_alpha = max(1, round(255 * (1 - value / 100)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.setOpacity(self._background_alpha / 255)
        theme = appearance_for(self)
        if theme.key == "sky":
            draw_slice(painter, self.rect(), "blue-bar", (48, 18), (30, 15))
        else:
            paint_surface(painter, self.rect(), "blue-bar", theme)

    def closeEvent(self, event):
        event.ignore()
        self.minimize.emit()

    def present(self, state, hint):
        detail = state.get("font_notice") or state["detail"]
        if not state.get("connected"):
            detail += " · " + tr("可打开设置后手动重新连接。")
        marker_name = tr("状态：") + tr(state["title"])
        marker_hint = marker_name + "。" + tr(detail)
        self.marker.setText(state.get("marker", "●"))
        # Pale semantic colours remain visible on the dark game metal.
        self.marker.setStyleSheet(
            "color:"
            + {
                "#a32b22": "#ff9b87",
                "#086b68": "#b6e3b4",
                "#4f6270": "#e9d386",
            }.get(state["color"], "#f3da93")
        )
        self.marker.setAccessibleName(marker_name)
        self.marker.setToolTip(marker_hint)
        activity = state.get("activity", {})
        self.status.setText(
            activity["title"]
            if activity and activity["tone"] != "ready"
            else state.get("short_pair", state["pair"]) + "\n" + tr(state["title"])
        )
        self.status.setAccessibleName(tr("语言组合：") + tr(state["pair"]))
        if activity and activity["tone"] != "ready":
            self.status.setAccessibleName(tr(activity["title"]))
        self.status.setToolTip(
            tr(detail) + " · " + tr("单击打开设置，按住拖动状态条") + " · " + tr("快捷键：") + hint
        )
        self.open_button.setToolTip(tr("打开或关闭设置。") + tr("快捷键：") + hint)


class OverlayPanel(SkinSurface):
    collapse = Signal()
    minimize = Signal()

    def __init__(self, control, status):
        super().__init__(
            "handbook",
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Sora Bilingual")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(PANEL_INSET, 14, PANEL_INSET, 18)
        outer.setSpacing(9)
        self.header = SkinSurface("blue-bar")
        header = QHBoxLayout(self.header)
        header.setContentsMargins(24, 8, 20, 8)
        emblem = QLabel()
        self.emblem = emblem
        emblem.setPixmap(
            artwork("guild-emblem").scaled(
                42,
                46,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        header.addWidget(emblem)
        self.grip = QLabel(
            'S O R A<br><span style="font-size:9px;letter-spacing:1px">BILINGUAL COMPANION</span>'
        )
        self.grip.setObjectName("brand")
        self.grip.setToolTip("拖动顶部，一起移动状态条和设置")
        header.addWidget(self.grip, 1)
        self.drag_surface = DragSurface(self, (self.header, self.grip, emblem))
        self.update_button = BadgeButton("更新")
        self.update_button.setObjectName("headerButton")
        self.update_button.setAccessibleName("检查更新")
        self.update_button.clicked.connect(self.show_updates)
        header.addWidget(self.update_button)
        self.more_button = QPushButton("···")
        self.more_button.setObjectName("headerButton")
        self.more_button.setAccessibleName("帮助和关于")
        header.addWidget(self.more_button)
        self.hide_button = QPushButton("×")
        self.hide_button.setObjectName("headerButton")
        self.hide_button.setFixedWidth(32)
        self.hide_button.setToolTip("隐藏到托盘；右键托盘图标可彻底退出。")
        self.hide_button.setAccessibleName("最小化到托盘")
        self.hide_button.clicked.connect(self.minimize)
        header.addWidget(self.hide_button)
        outer.addWidget(self.header)
        self.phase_card = QFrame()
        self.phase_card.setObjectName("phaseCard")
        phase_layout = QVBoxLayout(self.phase_card)
        phase_layout.setContentsMargins(14, 10, 12, 10)
        phase_layout.setSpacing(6)
        self.phase_title = QLabel()
        self.phase_title.setWordWrap(True)
        phase_layout.addWidget(self.phase_title)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setObjectName("detail")
        phase_layout.addWidget(self.detail)
        self.phase_progress = QProgressBar()
        self.phase_progress.setTextVisible(False)
        self.phase_progress.setFixedHeight(4)
        self.phase_progress.setAccessibleName("当前阶段正在进行")
        phase_layout.addWidget(self.phase_progress)
        self.settings = NativeSettingsWindow(control, status)
        # Connection feedback belongs to the content area, not over the ribbon.
        self.settings.language_page.layout().insertWidget(2, self.phase_card)
        self.settings.font_card.setProperty("presented_by_shell", True)
        self.settings.font_card.hide()
        self.settings.status_footer.hide()
        outer.addWidget(self.settings, 1)
        self.setMinimumWidth(780)
        self.resize(850, 720)
        self.settings.layout().setContentsMargins(0, 0, 0, 0)
        footer = QLabel("修改自动保存  ·  Esc 收起设置")
        footer.setObjectName("detail")
        footer.setContentsMargins(CONTENT_LEFT, 0, 12, 0)
        outer.addWidget(footer)
        self.update_popup = SkinSurface(
            "dialogue-frame", self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.update_popup.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        popup_layout = QVBoxLayout(self.update_popup)
        popup_layout.setContentsMargins(16, 16, 16, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.settings.updates)
        self.settings.updates.show()
        popup_layout.addWidget(scroll)
        self.settings.updates.availability_changed.connect(self.present_update)
        self.help_menu = QMenu(self)
        for title, callback in (
            ("使用说明", self.settings.updates.open_guide),
            ("发行说明", self.settings.updates.open_releases),
            ("关于", self.show_about),
        ):
            action = self.help_menu.addAction(tr(title))
            action.setData(title)
            action.triggered.connect(callback)
        self.more_button.clicked.connect(
            lambda: self.help_menu.exec(
                self.more_button.mapToGlobal(self.more_button.rect().bottomLeft())
            )
        )
        self.settings.appearance_changed.connect(self.set_appearance)
        self.set_appearance(self.settings.appearance_key)

    def set_appearance(self, key):
        apply_appearance(self, key)
        self.emblem.setPixmap(
            artwork(appearance_for(self).emblem).scaled(
                42,
                46,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def present_update(self, available):
        self.update_button.setText("新版本" if available else "更新")
        self.update_button.set_notice(available)

    def show_updates(self):
        if self.update_popup.isVisible():
            self.update_popup.hide()
            return
        self.settings.updates.refresh(False)
        area = self.screen().availableGeometry()
        self.update_popup.resize(380, min(520, area.height() - 32))
        point = self.update_button.mapToGlobal(self.update_button.rect().bottomRight())
        point.setX(
            max(
                area.left(),
                min(
                    point.x() - self.update_popup.width(),
                    area.right() - self.update_popup.width() + 1,
                ),
            )
        )
        point.setY(
            max(area.top(), min(point.y() + 8, area.bottom() - self.update_popup.height() + 1))
        )
        self.update_popup.move(point)
        self.update_popup.show()
        self.settings.updates.check.setFocus()

    def show_about(self):
        QMessageBox.about(
            self,
            tr("关于"),
            "Sora Bilingual "
            + self.settings.updates.service.distribution["version"]
            + "\n"
            + tr("游戏美术资源：Nihon Falcom Corporation。"),
        )

    def present(self, state):
        activity = state.get("activity")
        title = activity["title"] if activity else state["title"]
        tone = activity["tone"] if activity else "ready" if state["connected"] else "waiting"
        working = bool(activity and activity["working"])
        detail = activity["detail"] if activity else state["detail"]
        if tone == "ready":
            title = "已连接" + " · " + state["title"]
            detail = state["detail"]
        if tone == "waiting" and state.get("font_state") in (
            "preparing",
            "prepared",
            "runtime-required",
            "error",
            "conflict",
        ):
            font_state = state["font_state"]
            title = "正在准备字体" if font_state == "preparing" else "字体需要处理"
            tone = "error" if font_state in ("error", "conflict") else "preparing"
            working = font_state == "preparing"
            detail = ""
        if state.get("font_notice"):
            detail += ("\n" if detail else "") + state["font_notice"]
            if state.get("font_detail"):
                detail += "\n" + state["font_detail"]
        marker = "!" if tone == "error" else "…" if working else "●"
        self.phase_title.setText(marker + "  " + title)
        self.detail.setText(detail)
        self.phase_progress.setRange(0, 0 if working else 1)
        self.phase_progress.setVisible(working)
        self.phase_card.setVisible(
            tone in ("error", "preparing", "connecting")
            or working
            or bool(state.get("font_notice"))
        )
        self.phase_progress.setValue(0)
        if self.phase_card.property("tone") != tone:
            foreground, background = STATUS_COLORS[tone]
            self.phase_card.setProperty("tone", tone)
            self.phase_card.setStyleSheet(
                f"QFrame#phaseCard {{background:{background};border:1px solid {foreground};border-left:6px solid {foreground};border-radius:8px;}} QLabel {{color:{foreground};}} QProgressBar {{border:0;background:transparent;}} QProgressBar::chunk {{background:{foreground};}}"
            )
            self.phase_title.setStyleSheet(f"color:{foreground};font-size:18px;font-weight:700;")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and not self.settings.capturing:
            self.collapse.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.minimize.emit()


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#f2e7d1"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#176b6b"))
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "双")
    painter.end()
    return QIcon(pixmap)


class OverlayController(QObject):
    exit_finished = Signal(object)

    def __init__(
        self, control=CONTROL_PATH, status=STATUS_PATH, *, start_timers=True, auto_connect=True
    ):
        super().__init__()
        self.control_path = Path(control)
        set_language(read_control(control)["ui_language"])
        self.live = JsonSnapshot(Path(status).with_name("native-live.json"))
        self.backend = JsonSnapshot(status)
        self.auto_connect = auto_connect
        self._reload_started = False
        self._exiting = False
        self.exit_finished.connect(self._finish_exit)
        from sora_bilingual.updates.tool_updates import ReleaseWatch

        self.release_watch = ReleaseWatch()
        self._last_release_check = 0
        self.bar = StatusBar()
        self.panel = OverlayPanel(control, status)
        self.preferences = self.panel.settings.window_preferences
        self._interface_hidden = False
        self.bar.expand.connect(self.toggle_settings)
        # The compact status remains visible over the game until minimized.
        # Ignore the retired pin preference, without rewriting user game settings.
        self.panel.settings.bar_transparency.valueChanged.connect(
            self.bar.set_background_transparency
        )
        self.bar.set_background_transparency(self.panel.settings.bar_transparency.value())
        self.panel.settings.appearance_changed.connect(self.bar.set_appearance)
        self.bar.set_appearance(self.panel.settings.appearance_key)
        self.panel.collapse.connect(self.collapse)
        self.panel.minimize.connect(self.hide_interface)
        self.bar.minimize.connect(self.hide_interface)
        self.panel.settings.updates.availability_changed.connect(self.bar.open_button.set_notice)
        self.panel.drag_surface.moved.connect(self.save_position)
        self.bar.drag_surface.moved.connect(self.save_position)
        self.panel.drag_surface.dragged.connect(self.move_group)
        self.bar.drag_surface.dragged.connect(self.move_group)
        self.config = read_control(control)
        self.hotkey = InputManager({"hotkey": self.config["overlay_binding"]})
        self.panel.settings.settings_changed.connect(self.reload)
        self._last_config = 0
        self._capture_was_active = False
        self._last_pid = None
        self._last_state = None
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(tr("Sora 双语控制台"))
        menu = QMenu()
        for title, callback in [
            ("打开设置", self.expand),
            ("隐藏界面（后台继续运行）", self.hide_interface),
            ("退出工具", self.quit),
        ]:
            action = QAction(tr(title), menu)
            action.setData(title)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        retranslate(self.bar)
        retranslate(self.panel)
        self.tray.activated.connect(
            lambda reason: (
                self.expand() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
            )
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        point = self.preferences.value("bar_position", None)
        if isinstance(point, QPoint) and any(
            screen.availableGeometry().contains(point) for screen in QApplication.screens()
        ):
            self.bar.move(point)
        else:
            area = QApplication.primaryScreen().availableGeometry()
            self.bar.move(area.right() - self.bar.width() - 24, area.top() + 30)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.input_timer = QTimer(self)
        self.input_timer.timeout.connect(self.poll_input)
        if start_timers:
            self.timer.start(80)
            self.input_timer.start(16)
            if auto_connect:
                self.panel.settings.enable_auto_connect()
            if self.control_path.resolve() == CONTROL_PATH.resolve():
                self.panel.settings.updates.start()
        self.bar.show()
        self.tick()

    def reload(self):
        try:
            config = read_control(self.control_path)
            if config["overlay_binding"] != self.config["overlay_binding"]:
                self.hotkey.update_config({"hotkey": config["overlay_binding"]})
            if config["ui_language"] != self.config["ui_language"]:
                set_language(config["ui_language"])
                retranslate(self.bar)
                retranslate(self.panel)
                self.tray.setToolTip(tr("Sora 双语控制台"))
                for action in self.tray.contextMenu().actions():
                    action.setText(tr(action.data()))
                for action in self.panel.help_menu.actions():
                    action.setText(tr(action.data()))
            self.config = config
        except OSError, ValueError:
            return

    def save_position(self):
        self.preferences.setValue("bar_position", self.bar.pos())

    def move_group(self, delta):
        bounds = self.bar.geometry()
        if self.panel.isVisible():
            bounds = bounds.united(self.panel.geometry())
        target = bounds.topLeft() + delta
        screen = QApplication.screenAt(target) or self.bar.screen()
        area = screen.availableGeometry()
        x = max(area.left(), min(target.x(), area.right() - bounds.width() + 1))
        y = max(area.top(), min(target.y(), area.bottom() - bounds.height() + 1))
        delta = QPoint(x, y) - bounds.topLeft()
        self.bar.move(self.bar.pos() + delta)
        self.panel.move(self.panel.pos() + delta)

    def toggle_settings(self):
        if self.panel.isVisible():
            self.collapse()
        else:
            self.expand()

    def position_panel(self):
        area = self.bar.screen().availableGeometry()
        self.panel.resize(
            min(850, area.width() - 24), min(760, area.height() - self.bar.height() - 24)
        )
        width = max(self.panel.width(), self.bar.width())
        height = self.panel.height() + self.bar.height() + 8
        x = max(area.left(), min(self.bar.x(), area.right() - width + 1))
        y = max(area.top(), min(self.bar.y(), area.bottom() - height + 1))
        self.bar.move(x, y)
        self.panel.move(x, y + self.bar.height() + 8)

    def expand(self):
        self._interface_hidden = False
        if self.panel.isVisible():
            self.panel.raise_()
            self.panel.activateWindow()
            return
        self.panel.settings.reload_control()
        self.position_panel()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()
        self.tick()

    def collapse(self):
        self.panel.settings._cancel_capture()
        self.hotkey.reset()
        self.panel.hide()
        self.panel.update_popup.hide()

    def hide_interface(self):
        # Explicit visibility state survives telemetry refresh, Alt-Tab and
        # game exit. Polling and tray remain alive; no backend action is sent.
        self._interface_hidden = True
        self.panel.settings._cancel_capture()
        self.hotkey.reset()
        self.panel.hide()
        self.panel.update_popup.hide()
        self.bar.hide()

    def quit(self):
        if self._exiting:
            return
        import threading
        from sora_bilingual.game.tool_shutdown import shutdown

        self._exiting = True
        self.save_position()
        self.timer.stop()
        self.input_timer.stop()
        self.panel.settings._cancel_capture()
        self.tray.contextMenu().actions()[-1].setEnabled(False)
        self.tray.setToolTip(tr("正在退出…"))

        def stop():
            error = None
            try:
                shutdown(self.control_path.parent, self.panel.settings._auto_connector)
            except Exception as exc:
                error = str(exc)
            self.exit_finished.emit(error)

        threading.Thread(target=stop, name="tool-shutdown").start()

    def _finish_exit(self, error):
        if error:
            self._exiting = False
            self.tray.contextMenu().actions()[-1].setEnabled(True)
            self.tray.setToolTip(tr("退出尚未完成"))
            QMessageBox.warning(self.bar, tr("退出尚未完成"), error)
            return
        self._exit_application()

    def _exit_application(self):
        self.tray.hide()
        self.bar.hide()
        self.panel.hide()
        # quit() sends a cancellable Quit event; our close-to-hide windows reject
        # it. Explicit program exit/handoff must bypass those user-close handlers.
        QApplication.instance().exit(0)

    def close_interface(self):
        """UI code handoff is not a user-requested tool exit."""
        self.save_position()
        if self.panel.settings._auto_connector:
            self.panel.settings._auto_connector.close()
        self._exit_application()

    def reload_interface(self):
        if self._reload_started:
            return
        import os, subprocess

        self.preferences.setValue("restore_hidden", self._interface_hidden)
        self.preferences.setValue("restore_expanded", self.panel.isVisible())
        self.preferences.setValue("restore_tab", self.panel.settings.tabs.currentIndex())
        self.save_position()
        self.preferences.sync()
        command = [
            runtime_executable("ui"),
            "-m",
            "sora_bilingual.app.overlay_reloader",
            "--pid",
            str(os.getpid()),
            "--control",
            str(self.control_path),
            "--status",
            str(self.backend.path),
        ]
        if not self.auto_connect:
            command.append("--no-auto-connect")
        subprocess.Popen(command, cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW)
        self._reload_started = True
        self.close_interface()

    def restore_interface(self):
        self.panel.settings.tabs.setCurrentIndex(self.preferences.value("restore_tab", 0, type=int))
        if self.preferences.value("restore_hidden", False, type=bool):
            self.hide_interface()
        elif self.preferences.value("restore_expanded", False, type=bool):
            self.expand()

    def poll_input(self):
        capturing = self.panel.settings.capturing
        if capturing:
            self.hotkey.reset()
            self._capture_was_active = True
            return
        if self._capture_was_active:
            self.hotkey.reset()
            self._capture_was_active = False
        active = self.panel.isActiveWindow() or bool(
            self._last_pid and foreground_rect(self._last_pid)
        )
        if self.hotkey.poll(active):
            if self.panel.isVisible():
                self.hide_interface()
            else:
                self.expand()

    def tick(self):
        if self.timer.isActive() and time.monotonic() - self._last_release_check >= 1:
            self._last_release_check = time.monotonic()
            if "ui" in self.release_watch.poll():
                self.reload_interface()
                return
        if time.monotonic() - self._last_config >= 0.5:
            self.reload()
            self._last_config = time.monotonic()
        live = self.live.read()
        backend = self.backend.read()
        state = describe_state(self.config, live, backend)
        auto = self.panel.settings._auto_connector
        if (
            auto
            and not state["connected"]
            and not (backend.get("running") and time.time() - backend.get("updated_at", 0) < 5)
        ):
            state["title"] = "自动连接异常" if auto.error else "等待游戏 · 自动连接"
            state["detail"] = auto.message
        if auto:
            state = with_font_status(state, getattr(auto, "font_status", {}))
        activity = self.panel.settings.connection_activity(
            backend,
            bool(backend.get("running") and 0 <= time.time() - backend.get("updated_at", 0) < 5),
        )
        state["activity"] = activity
        if activity["tone"] in ("waiting", "error"):
            state["connected"] = False
        if activity["tone"] != "ready":
            state.update(
                color=STATUS_COLORS[activity["tone"]][0],
                marker="▲" if activity["tone"] == "error" else "○",
                title=activity["title"],
            )
        self._last_state = state
        now = time.time()
        source = (
            live if live.get("running") and 0 <= now - live.get("updated_at", 0) < 2 else backend
        )
        self._last_pid = (
            source.get("pid")
            if source.get("running") and 0 <= now - source.get("updated_at", 0) < 5
            else None
        )
        hint = " + ".join(self.config["overlay_binding"].get("keyboard", [])) or "单击状态条展开"
        self.bar.present(state, hint)
        self.panel.present(state)
        if self.panel.isVisible():
            self.position_panel()
        # Only the explicit hide action owns bar visibility. Closing settings
        # can leave focus on another window; that must not hide the bar too.
        wanted = not self._interface_hidden
        if wanted != self.bar.isVisible():
            self.bar.setVisible(wanted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connect", action="store_true", help="connect only to an already running game"
    )
    parser.add_argument("--expanded", action="store_true")
    parser.add_argument(
        "--restore", action="store_true", help="restore interface state after a published update"
    )
    parser.add_argument(
        "--no-auto-connect", action="store_true", help="offline preview and tests only"
    )
    parser.add_argument("--control", type=Path, default=CONTROL_PATH)
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    load_cjk_font(app)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    # A second launch opens the resident panel instead of creating two pollers.
    import hashlib

    name = "SoraBilingual-" + hashlib.sha256(str(args.control.resolve()).encode()).hexdigest()[:16]
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(250):
        socket.write(b"connect\n" if args.connect else b"open\n")
        socket.waitForBytesWritten(250)
        return 0
    server = QLocalServer()
    if not server.listen(name):
        return 1
    from sora_bilingual.game.tool_shutdown import reset_exit

    reset_exit(args.control.parent)
    from sora_bilingual.app.native_settings import configure_first_run

    first_run = not args.control.exists()
    if not args.no_auto_connect and not configure_first_run(args.control):
        server.close()
        return 0
    controller = OverlayController(args.control, args.status, auto_connect=not args.no_auto_connect)
    clients = []

    def connected():
        client = server.nextPendingConnection()
        clients.append(client)

        def message():
            if not client.canReadLine():
                return
            command = bytes(client.readLine()).strip()
            if command == b"status":
                import os

                client.write(
                    json.dumps(
                        {
                            "pid": os.getpid(),
                            "hidden": controller._interface_hidden,
                            "expanded": controller.panel.isVisible(),
                            "tab": controller.panel.settings.tabs.currentIndex(),
                            "auto_connect": controller.auto_connect,
                            "connection_message": controller.panel.settings._auto_connector.message
                            if controller.panel.settings._auto_connector
                            else None,
                            "release": controller.release_watch.current.get("version")
                            if controller.release_watch.current
                            else None,
                        }
                    ).encode()
                    + b"\n"
                )
                client.flush()
            elif command == b"reload":
                controller.reload_interface()
            elif command == b"hide":
                controller.hide_interface()
            elif command == b"quit":
                controller.quit()
            else:
                controller.expand()
                if command == b"connect":
                    controller.panel.settings._start_backend()
            client.disconnectFromServer()

        client.readyRead.connect(message)
        client.disconnected.connect(lambda: clients.remove(client) if client in clients else None)
        # Bind the QObject slot directly so Qt disconnects it during shutdown;
        # a Python lambda can outlive the socket while the UI hands off.
        client.disconnected.connect(client.deleteLater)
        message()

    server.newConnection.connect(connected)
    if args.expanded or (first_run and not args.no_auto_connect):
        controller.expand()
    if args.restore:
        controller.restore_interface()
    if args.connect and not args.no_auto_connect:
        QTimer.singleShot(200, controller.panel.settings._start_backend)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
