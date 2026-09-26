"""Background stable-release checks; no network or archive work on Qt's thread."""

import json
from pathlib import Path
import threading
import time
from sora_bilingual.updates.github_updates import GitHubClient, version_tuple
from sora_bilingual.updates.update_installer import install, UpdateBusy, RuntimeRequired, write_json

INTERVAL = 6 * 3600
POLICIES = {"automatic", "off"}


class UpdateService:
    def __init__(self, root, *, client=None, clock=time.time):
        self.root = Path(root)
        self.clock = clock
        self.distribution = json.loads((self.root / "distribution.json").read_text("utf-8"))
        self.directory = self.root / "generated/updates"
        self.preferences = self.directory / "preferences.json"
        self.policy = self._read(self.preferences).get("policy", "automatic")
        # The old notify-only choice never authorized installation. Migrate it
        # to off rather than silently enabling updates when simplifying the UI.
        if self.policy == "notify":
            self.policy = "off"
        if self.policy not in POLICIES:
            self.policy = "automatic"
        self.client = client or GitHubClient(self.distribution["repository"])
        self.message = "等待检查更新" if self.policy == "automatic" else "自动更新已关闭"
        self.available = None
        self.pending = None
        self.component_update = False
        self.runtime_package = None
        self.release = None
        self.failed = False
        self.download_is_installer = False
        self.download_url = f"https://github.com/{self.distribution['repository']}/releases/latest"
        self.progress = None
        self.last_check = 0
        self.next_check = 0
        self._thread = None
        self._lock = threading.Lock()

    @staticmethod
    def _read(path):
        try:
            data = json.loads(path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except OSError, ValueError:
            return {}

    @property
    def busy(self):
        return bool(self._thread and self._thread.is_alive())

    def set_policy(self, value):
        if value not in POLICIES:
            raise ValueError("未知更新策略")
        self.policy = value
        write_json(self.preferences, {"policy": value})
        self.next_check = 0
        if not self.busy:
            self.message = "等待检查更新" if value == "automatic" else "自动更新已关闭"

    def tick(self, manual=False):
        if self.busy or (not manual and (self.policy == "off" or self.clock() < self.next_check)):
            return
        self._thread = threading.Thread(
            target=self._run, args=(manual,), name="release-update", daemon=True
        )
        self._thread.start()

    def _run(self, manual):
        # A process may terminate during network work; installer transactions
        # recover at next bootstrap. Native hooks never belong to this worker.
        with self._lock:
            try:
                self.failed = False
                self._check(manual)
            except Exception as exc:
                self.failed = True
                self.pending = None
                self.message = (
                    "自动更新未完成。请重试，或使用下方下载入口重新安装；"
                    "原目录与配置请保留。详细原因见日志。"
                )
                self.next_check = self.clock() + 900
                try:
                    write_json(
                        self.directory / "last-error.json",
                        {"time": self.clock(), "error": str(exc)},
                    )
                except OSError:
                    pass  # A read-only/full disk must not also break the recovery UI.
            finally:
                self.progress = None

    def _check(self, manual=False):
        if self.pending and self.policy == "automatic":
            meta, path = self.pending
            try:
                try:
                    installed = install(
                        self.root,
                        path,
                        meta,
                        component_update=self.component_update,
                        runtime_package=self.runtime_package,
                    )
                except RuntimeRequired:
                    if self.runtime_package is not None:
                        raise
                    self.runtime_package = self._download_component(meta, "runtime")
                    installed = install(
                        self.root,
                        path,
                        meta,
                        component_update=True,
                        runtime_package=self.runtime_package,
                    )
                self.message = f"已安装 {installed}，界面正在刷新"
                self.pending = None
                self.next_check = float("inf")
            except UpdateBusy as exc:
                self.message = str(exc)
                self.next_check = self.clock() + 10
            return
        self.message = "正在检查 GitHub 稳定版…"
        release, cache = self.client.latest(self._read(self.directory / "release-cache.json"))
        write_json(self.directory / "release-cache.json", cache)
        self.last_check = self.clock()
        self.next_check = self.clock() + INTERVAL
        if not release or version_tuple(release["tag_name"]) <= version_tuple(
            self.distribution["version"]
        ):
            self.message = "当前已是最新稳定版" if release else "仓库尚未发布稳定版"
            return
        self.available = release["tag_name"]
        self.release = release
        if self.policy != "automatic":
            self.message = f"发现 {self.available}；开启自动更新即可安装"
            return
        if not (self.root / "installed-manifest.json").is_file():
            self.message = f"发现 {self.available}；开发目录不会被覆盖，请使用发行包"
            return
        meta, asset = self.client.metadata(release)
        self.download_url = asset["browser_download_url"] if asset else self.download_url
        if "installer" in meta:
            setup = self.client.component_asset(release, meta["installer"])
            self.download_url = setup["browser_download_url"]
            self.download_is_installer = True
        self.component_update = bool(meta.get("components"))
        self.runtime_package = None
        self.message = f"正在下载 {self.available}…"
        if self.component_update:
            path = self._download_component(meta, "application")
            receipt = self._read(self.root / "installed-manifest.json")
            if not receipt.get("runtime_id"):
                raise ValueError("旧源码版需要手动迁移到便携版")
            if receipt["runtime_id"] != meta["components"]["runtime_id"]:
                self.runtime_package = self._download_component(meta, "runtime")
        else:
            path = self.directory / meta["asset"]
            self.client.download(asset, meta, path, lambda ratio: setattr(self, "progress", ratio))
        self.pending = (meta, path)
        # Respect a policy change made while downloading.
        if self.policy == "automatic":
            self._check()

    def _download_component(self, meta, kind):
        descriptor = meta["components"][kind]
        asset = self.client.component_asset(self.release, descriptor)
        path = self.directory / descriptor["asset"]
        self.message = "正在下载程序更新…" if kind == "application" else "正在下载变更的运行依赖…"
        self.client.download(
            asset, descriptor, path, lambda ratio: setattr(self, "progress", ratio)
        )
        return path
