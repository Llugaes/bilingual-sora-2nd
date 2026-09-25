"""Update settings surface; service is started explicitly by the live controller."""

from pathlib import Path
from sora_bilingual.paths import ROOT
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton
from sora_bilingual.updates.update_service import UpdateService
from sora_bilingual.app.ui_widgets import QLabel, QComboBox, QPushButton


class UpdatePage(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(parent)
        self.service = UpdateService(root or ROOT)
        layout = QVBoxLayout(self)
        d = self.service.distribution
        layout.addWidget(QLabel(f"当前版本：{d['version']}"))
        repo = QLabel(
            f'<a style="color:#8ecde6" href="https://github.com/{d["repository"]}/releases">GitHub 发行版本 · {d["repository"]}</a>'
        )
        repo.setOpenExternalLinks(True)
        layout.addWidget(repo)
        self.policy = QComboBox()
        for title, value in [
            ("自动检查并安装稳定版", "automatic"),
            ("仅检查并提示", "notify"),
            ("关闭自动检查", "off"),
        ]:
            self.policy.addItem(title, value)
        self.policy.setCurrentIndex(self.policy.findData(self.service.policy))
        self.policy.currentIndexChanged.connect(
            lambda _: self.service.set_policy(self.policy.currentData())
        )
        layout.addWidget(self.policy)
        self.check = QPushButton("立即检查更新")
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
        note = QLabel(
            "每 6 小时检查一次。游戏连接期间先下载，连接结束后安装。\n设置、语言资源和缓存保留；安装完成后界面自动恢复。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        help_note = QLabel("× / Esc 只收起设置；隐藏界面后可从托盘或再次双击程序打开。")
        help_note.setWordWrap(True)
        layout.addWidget(help_note)
        for title, callback in [
            ("打开使用说明", self.open_guide),
            ("打开日志与配置文件夹", self.open_data),
            ("创建桌面快捷方式", self.create_shortcut),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            layout.addWidget(button)
        self.help_state = QLabel()
        self.help_state.setWordWrap(True)
        layout.addWidget(self.help_state)
        if not (self.service.root / "installed-manifest.json").exists():
            label = QLabel("当前是开发目录：可检查版本，自动更新不会覆盖本地源码。")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.refresh(False)

    def open_guide(self):
        from sora_bilingual.app.i18n import current_language

        filename = {"en": "README.en.md", "ja": "README.ja.md"}.get(current_language(), "README.md")
        QDesktopServices.openUrl(
            QUrl(
                f"https://github.com/{self.service.distribution['repository']}/blob/main/{filename}"
            )
        )

    def open_data(self):
        directory = self.service.root / "generated"
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def create_shortcut(self):
        from sora_bilingual.platform.shortcuts import create_desktop_shortcut

        try:
            create_desktop_shortcut(self.service.root)
            self.help_state.setText("桌面快捷方式已创建")
        except Exception as exc:
            self.help_state.setText("创建快捷方式失败：" + str(exc))

    def start(self):
        self.timer.start(1000)
        self.service.tick()

    def refresh(self, poll=True):
        if poll:
            self.service.tick()
        s = self.service
        self.check.setEnabled(not s.busy)
        self.download.setText("下载安装程序" if s.download_is_installer else "下载完整包（含 EXE）")
        self.recovery.setVisible(s.failed)
        self.state.setText(s.message + (f" {s.progress:.0%}" if s.progress is not None else ""))
