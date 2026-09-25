"""Resident control overlay. Never starts the game or unloads its hooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QPoint, QSettings
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
    QScrollArea,
    QFrame,
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
from sora_bilingual.app.presentation import describe_state

STYLE = """
QWidget { background:#141e29; color:#e9edf1; font-size:13px; }
QWidget#bar, QWidget#panel { border:1px solid #466073; border-radius:12px; }
QLabel { background:transparent; border:none; }
QLabel#brand { color:#91acbe; font-size:11px; letter-spacing:2px; }
QLabel#title { font-size:20px; font-weight:600; }
QLabel#detail { color:#a9b9c8; font-size:12px; }
QLabel#status { font-size:14px; font-weight:600; }
QPushButton { background:#223547; border:1px solid #3a5266; border-radius:6px; padding:8px 12px; }
QPushButton:hover { background:#304b60; border-color:#73b9c8; }
QPushButton:focus { border-color:#83daca; }
QPushButton:disabled { color:#718496; }
QComboBox, QDoubleSpinBox { background:#1c2c3a; border:1px solid #3a5266; border-radius:5px; padding:6px; min-height:20px; }
QComboBox QAbstractItemView { background:#213343; selection-background-color:#3c657a; }
QTabWidget::pane { border:1px solid #314959; border-radius:8px; }
QTabBar::tab { background:#192735; color:#a9b9c8; padding:12px 22px; margin:0 4px 8px 0; border-radius:5px; }
QTabBar::tab:selected { background:#315466; color:#e4fffa; }
QCheckBox { spacing:10px; padding:8px 0; }
QCheckBox::indicator { width:17px; height:17px; border:1px solid #648196; border-radius:4px; background:#203343; }
QCheckBox::indicator:checked { background:#6dcabb; border-color:#a6f4d8; }
QSlider::groove:horizontal { background:#263c4b; height:5px; border-radius:2px; }
QSlider::sub-page:horizontal { background:#63b8ab; border-radius:2px; }
QSlider::handle:horizontal { background:#b6eee2; width:14px; margin:-5px 0; border-radius:7px; }
QScrollArea { border:none; }
"""


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


class DragHandle(QLabel):
    moved = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.window().pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, "_drag"):
            self.window().move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.moved.emit()


class StatusBar(QWidget):
    expand = Signal()
    hide_requested = Signal()

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
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 10, 10)
        self.grip = DragHandle("≡")
        self.grip.setToolTip("拖动状态条")
        row.addWidget(self.grip)
        column = QVBoxLayout()
        column.setSpacing(3)
        self.status = QLabel()
        self.status.setObjectName("status")
        self.detail = QLabel()
        self.detail.setObjectName("detail")
        column.addWidget(self.status)
        column.addWidget(self.detail)
        row.addLayout(column, 1)
        self.open_button = QPushButton("设置")
        self.open_button.clicked.connect(self.expand)
        row.addWidget(self.open_button)
        self.hide_button = QPushButton("×")
        self.hide_button.setFixedWidth(32)
        self.hide_button.setToolTip("隐藏界面，后台继续运行；可从托盘或快捷键打开")
        self.hide_button.clicked.connect(self.hide_requested)
        row.addWidget(self.hide_button)
        self.setFixedWidth(430)

    def closeEvent(self, event):
        event.ignore()
        self.hide_requested.emit()

    def present(self, state, hint):
        self.status.setText("●  " + state["title"])
        self.status.setStyleSheet("color:" + state["color"])
        self.detail.setText(state["pair"] + "  ·  " + hint)


class OverlayPanel(QWidget):
    collapse = Signal()

    def __init__(self, control, status):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("panel")
        self.setWindowTitle("Sora Bilingual")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)
        header = QHBoxLayout()
        brand = DragHandle("S O R A   /   B I L I N G U A L")
        brand.setObjectName("brand")
        header.addWidget(brand, 1)
        self.hide_button = QPushButton("×")
        self.hide_button.setFixedWidth(32)
        self.hide_button.setToolTip("关闭设置，保留小状态条")
        self.hide_button.clicked.connect(self.collapse)
        header.addWidget(self.hide_button)
        outer.addLayout(header)
        self.title = QLabel("双语控制台")
        self.title.setObjectName("title")
        outer.addWidget(self.title)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setObjectName("detail")
        outer.addWidget(self.detail)
        self.settings = NativeSettingsWindow(control, status)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.settings)
        self.scroll.setMinimumHeight(200)
        outer.addWidget(self.scroll, 1)
        self.setMinimumWidth(620)
        self.resize(620, 650)
        self.settings.layout().setContentsMargins(0, 0, 0, 0)
        footer = QLabel("× / Esc 关闭设置，保留状态条  ·  拖动顶部移动")
        footer.setObjectName("detail")
        outer.addWidget(footer)

    def present(self, state):
        self.title.setText(state["title"])
        self.title.setStyleSheet("color:" + state["color"])
        self.detail.setText(state["pair"] + "   /   " + state["detail"])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and not self.settings.capturing:
            self.collapse.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.collapse.emit()


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#152737"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#83decc"))
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "双")
    painter.end()
    return QIcon(pixmap)


class OverlayController(QObject):
    def __init__(
        self, control=CONTROL_PATH, status=STATUS_PATH, *, start_timers=True, auto_connect=True
    ):
        super().__init__()
        self.control_path = Path(control)
        self.live = JsonSnapshot(Path(status).with_name("native-live.json"))
        self.backend = JsonSnapshot(status)
        self.auto_connect = auto_connect
        self._reload_started = False
        from sora_bilingual.updates.tool_updates import ReleaseWatch

        self.release_watch = ReleaseWatch()
        self._last_release_check = 0
        self.preferences = QSettings(
            str(self.control_path.with_name("overlay-window.ini")), QSettings.Format.IniFormat
        )
        self.bar = StatusBar()
        self.panel = OverlayPanel(control, status)
        self._interface_hidden = False
        self.bar.expand.connect(self.expand)
        self.panel.collapse.connect(self.collapse)
        self.bar.hide_requested.connect(self.hide_interface)
        self.bar.grip.moved.connect(self.save_position)
        self.config = read_control(control)
        self.hotkey = InputManager({"hotkey": self.config["overlay_binding"]})
        self.panel.settings.settings_changed.connect(self.reload)
        self._last_config = 0
        self._capture_was_active = False
        self._last_pid = None
        self._last_state = None
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Sora 双语控制台")
        menu = QMenu()
        for title, callback in [
            ("打开设置", self.expand),
            ("隐藏界面（后台继续运行）", self.hide_interface),
            ("退出界面程序（保留双语连接）", self.quit),
        ]:
            action = QAction(title, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
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
            self.config = config
        except OSError, ValueError:
            return

    def save_position(self):
        self.preferences.setValue("bar_position", self.bar.pos())

    def expand(self):
        self._interface_hidden = False
        if self.panel.isVisible():
            self.panel.raise_()
            self.panel.activateWindow()
            return
        self.panel.settings.reload_control()
        area = self.bar.screen().availableGeometry()
        self.panel.resize(620, min(650, area.height() - 16))
        x = max(area.left(), min(self.bar.x(), area.right() - self.panel.width()))
        y = max(
            area.top(),
            min(self.bar.y() + self.bar.height() + 8, area.bottom() - self.panel.height()),
        )
        self.panel.move(x, y)
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()
        self.tick()

    def collapse(self):
        self.panel.settings._cancel_capture()
        self.hotkey.reset()
        self.panel.hide()

    def hide_interface(self):
        # Explicit visibility state survives telemetry refresh, Alt-Tab and
        # game exit. Polling and tray remain alive; no backend action is sent.
        self._interface_hidden = True
        self.panel.settings._cancel_capture()
        self.hotkey.reset()
        self.panel.hide()
        self.bar.hide()

    def quit(self):
        # Only own Qt windows exit. Never signal, detach, or terminate backend.
        self.save_position()
        self.tray.hide()
        if self.panel.settings._auto_connector:
            self.panel.settings._auto_connector.close()
        QApplication.instance().quit()

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
            str(Path(sys.executable).with_name("pythonw.exe")),
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
        self.quit()

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
        hint = " + ".join(self.config["overlay_binding"].get("keyboard", [])) or "点击设置展开"
        self.bar.present(state, hint)
        self.panel.present(state)
        # Keep it out of unrelated applications while the game is connected.
        # The panel is an explicit user interaction and stays open until folded.
        wanted = not self._interface_hidden and (
            not self._last_pid or bool(foreground_rect(self._last_pid)) or self.panel.isVisible()
        )
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
        client.disconnected.connect(lambda: (clients.remove(client), client.deleteLater()))
        message()

    server.newConnection.connect(connected)
    if args.expanded:
        controller.expand()
    if args.restore:
        controller.restore_interface()
    if args.connect and not args.no_auto_connect:
        QTimer.singleShot(200, controller.panel.settings._start_backend)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
