"""Update settings surface; service is started explicitly by the live controller."""

from sora_bilingual.paths import ROOT
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from sora_bilingual.updates.update_service import UpdateService
from sora_bilingual.app.i18n import tr
from sora_bilingual.app.ui_widgets import QLabel, QCheckBox, QPushButton


class UpdatePage(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(parent)
        self.service = UpdateService(root or ROOT)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        d = self.service.distribution
        layout.addWidget(QLabel("当前版本：" + str(d["version"])))
        self.automatic = QCheckBox("自动更新")
        self.automatic.setChecked(self.service.policy == "automatic")
        self.automatic.toggled.connect(self.set_automatic)
        layout.addWidget(self.automatic)
        note = QLabel("自动下载稳定版，退出游戏后安装。设置会保留。")
        note.setObjectName("helpText")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.check = QPushButton("检查更新")
        self.check.setObjectName("primaryAction")
        self.check.clicked.connect(lambda: self.service.tick(manual=True))
        layout.addWidget(self.check)
        self.state = QLabel()
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.download = QPushButton("下载完整包（含 EXE）")
        self.download.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.service.download_url))
        )
        layout.addWidget(self.download)
        self.recovery = QLabel(
            "安装版请运行下载的 Setup；便携版请完整解压后运行 EXE。"
            "迁移到新目录前先退出旧工具，复制 generated/native-control.json 和 generated/overlay-window.ini；"
            "保留原目录，不复制旧程序或更新缓存。"
        )
        self.recovery.setWordWrap(True)
        layout.addWidget(self.recovery)
        self.logs = QPushButton("查看更新日志")
        self.logs.clicked.connect(self.open_data)
        layout.addWidget(self.logs)
        if not (self.service.root / "installed-manifest.json").exists():
            label = QLabel("当前是开发目录：可检查版本，自动更新不会覆盖本地源码。")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()
        links = QHBoxLayout()
        for title, callback in [("使用说明", self.open_guide), ("发行说明", self.open_releases)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            links.addWidget(button)
        layout.addLayout(links)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.refresh(False)

    def set_automatic(self, enabled):
        self.service.set_policy("automatic" if enabled else "off")
        self.refresh(False)

    def open_releases(self):
        QDesktopServices.openUrl(
            QUrl(f"https://github.com/{self.service.distribution['repository']}/releases")
        )

    def open_guide(self):
        from sora_bilingual.app.i18n import current_language

        filename = {"en": "README.en.md", "ja": "README.ja.md"}.get(current_language(), "README.md")
        QDesktopServices.openUrl(
            QUrl(
                f"https://github.com/{self.service.distribution['repository']}/blob/main/{filename}"
            )
        )

    def open_data(self):
        directory = self.service.directory
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def start(self):
        self.timer.start(1000)
        self.service.tick()

    def refresh(self, poll=True):
        if poll:
            self.service.tick()
        s = self.service
        self.check.setEnabled(not s.busy)
        self.download.setText("下载安装程序" if s.download_is_installer else "下载完整包（含 EXE）")
        self.download.setVisible(s.failed)
        self.recovery.setVisible(s.failed)
        self.logs.setVisible(s.failed)
        self.state.setText(s.message + (f" {s.progress:.0%}" if s.progress is not None else ""))
