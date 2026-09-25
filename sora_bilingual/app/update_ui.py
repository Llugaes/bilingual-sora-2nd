"""Update settings surface; service is started explicitly by the live controller."""

from pathlib import Path
from sora_bilingual.paths import ROOT
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton
from sora_bilingual.updates.update_service import UpdateService


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
        note = QLabel(
            "每 6 小时检查一次。游戏连接期间先下载，连接结束后安装。\n设置、语言资源和缓存保留；安装完成后界面自动恢复。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        if not (self.service.root / "installed-manifest.json").exists():
            label = QLabel("当前是开发目录：可检查版本，自动更新不会覆盖本地源码。")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.refresh(False)

    def start(self):
        self.timer.start(1000)
        self.service.tick()

    def refresh(self, poll=True):
        if poll:
            self.service.tick()
        s = self.service
        self.check.setEnabled(not s.busy)
        self.state.setText(s.message + (f" {s.progress:.0%}" if s.progress is not None else ""))
