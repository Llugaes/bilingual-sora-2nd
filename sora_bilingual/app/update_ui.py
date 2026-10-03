"""Update settings surface; service is started explicitly by the live controller."""

from sora_bilingual.paths import ROOT
from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox
from sora_bilingual.updates.update_service import UpdateService
from sora_bilingual.app.i18n import tr
from sora_bilingual.app.ui_widgets import QLabel, QCheckBox, QPushButton, QComboBox


class UpdatePage(QWidget):
    availability_changed = Signal(bool)

    def __init__(self, parent=None, root=None):
        super().__init__(parent)
        self.service = UpdateService(root or ROOT)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        d = self.service.distribution
        layout.addWidget(QLabel("当前版本：" + str(d["version"])))
        self.available_version = QLabel()
        self.available_version.setObjectName("sectionTitle")
        layout.addWidget(self.available_version)
        self.release_title = QLabel()
        self.release_title.setWordWrap(True)
        layout.addWidget(self.release_title)
        self._announced_available = False
        self.automatic = QCheckBox("自动检查新版本")
        self.automatic.setChecked(self.service.policy == "notify")
        self.automatic.toggled.connect(self.set_automatic)
        layout.addWidget(self.automatic)
        note = QLabel("只检查和提醒；点击确认后才下载安装。设置会保留。")
        note.setObjectName("helpText")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.check = QPushButton("检查更新")
        self.check.clicked.connect(lambda: self.service.tick(manual=True))
        layout.addWidget(self.check)
        self.install = QPushButton("下载安装")
        self.install.setObjectName("primaryAction")
        self.install.clicked.connect(lambda: self.confirm_install(self.service.release))
        layout.addWidget(self.install)
        self.state = QLabel()
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.history_check = QPushButton("选择历史稳定版本…")
        self.history_check.clicked.connect(self.service.load_history)
        layout.addWidget(self.history_check)
        self.history = QComboBox()
        self.history.setAccessibleName(tr("历史稳定版本"))
        self.rollback = QPushButton("回退到所选版本")
        self.rollback.clicked.connect(
            lambda: self.confirm_install(self.history.currentData(), rollback=True)
        )
        row = QHBoxLayout()
        row.addWidget(self.history, 1)
        row.addWidget(self.rollback)
        layout.addLayout(row)
        self.rollback_note = QLabel(
            "回退会保留设置并关闭自动检查，防止旧版自动升级。可随时手动检查。"
        )
        self.rollback_note.setObjectName("helpText")
        self.rollback_note.setWordWrap(True)
        layout.addWidget(self.rollback_note)
        self._history_tags = None
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
            label = QLabel("当前是开发目录：可检查版本，不会覆盖本地源码。")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.refresh(False)

    def set_automatic(self, enabled):
        self.service.set_policy("notify" if enabled else "off")
        self.refresh(False)

    def confirm_install(self, release, rollback=False):
        if not release or self.service.busy:
            return
        # Capture the selected version before showing a modal dialog. A timer
        # check must not silently change the version that the user approved.
        release = dict(release)
        title = "确认回退" if rollback else "确认更新"
        message = tr("当前版本：") + self.service.distribution["version"]
        message += "\n" + tr("目标版本：") + release["tag_name"] + "\n\n"
        message += tr("设置会保留。请先退出游戏，再执行安装。")
        if rollback:
            message += "\n" + tr("回退会关闭自动检查，防止旧版自动升级。")
        answer = QMessageBox.question(
            self,
            tr(title),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.service.install_release(release)
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
        available = bool(s.available)
        self.available_version.setText("发现新版本：" + s.available if available else "")
        self.available_version.setVisible(available)
        self.release_title.setText((s.release or {}).get("name", ""))
        if self._announced_available != available:
            self._announced_available = available
            self.availability_changed.emit(available)
        self.check.setEnabled(not s.busy)
        installable = (s.root / "installed-manifest.json").exists() and not s.installed
        self.install.setText("下载安装 " + s.available if available else "下载安装")
        self.install.setVisible(available)
        self.install.setEnabled(installable and not s.busy)
        self.history_check.setEnabled(not s.busy and not s.installed)
        tags = tuple(r["tag_name"] for r in s.history)
        if tags != self._history_tags:
            selected = (self.history.currentData() or {}).get("tag_name")
            self.history.clear()
            for release in s.history:
                self.history.addItem(release["tag_name"], release)
            if selected in tags:
                self.history.setCurrentIndex(tags.index(selected))
            self._history_tags = tags
        self.history.setVisible(bool(tags))
        self.rollback.setVisible(bool(tags))
        self.rollback_note.setVisible(s.history_loaded)
        self.history.setEnabled(not s.busy)
        self.rollback.setEnabled(installable and not s.busy and bool(tags))
        self.download.setText("下载安装程序" if s.download_is_installer else "下载完整包（含 EXE）")
        self.download.setVisible(s.failed)
        self.recovery.setVisible(s.failed)
        self.logs.setVisible(s.failed)
        self.state.setText(s.message + (f" {s.progress:.0%}" if s.progress is not None else ""))
