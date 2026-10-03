"""Background stable-release checks; no network or archive work on Qt's thread."""

import json
from pathlib import Path
import threading
import time
from sora_bilingual.updates.github_updates import GitHubClient, version_tuple
from sora_bilingual.updates.release_sources import ReleaseSources
from sora_bilingual.updates.update_installer import install, UpdateBusy, RuntimeRequired, write_json

INTERVAL = 6 * 3600
POLICIES = {"notify", "off"}


class UpdateService:
    def __init__(self, root, *, client=None, clock=time.time):
        self.root = Path(root)
        self.clock = clock
        self.distribution = json.loads((self.root / "distribution.json").read_text("utf-8"))
        self.directory = self.root / "generated/updates"
        self.preferences = self.directory / "preferences.json"
        self.policy = self._read(self.preferences).get("policy", "notify")
        # Legacy automatic installations become notifications only. The worker
        # never infers installation consent from a preference or timer tick.
        if self.policy not in POLICIES:
            self.policy = "notify"
            write_json(self.preferences, {"policy": self.policy})
        self.client = client or (
            ReleaseSources(self.distribution["repository"], self.distribution["version"])
            if self.distribution.get("gitee_mirror") is True
            else GitHubClient(self.distribution["repository"])
        )
        self.message = "等待检查更新" if self.policy == "notify" else "自动检查已关闭"
        self.available = None
        self.release = None
        self.history = []
        self.history_loaded = False
        self.installed = False
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
            self.message = "等待检查更新" if value == "notify" else "自动检查已关闭"

    def tick(self, manual=False):
        if (
            self.installed
            or self.busy
            or (not manual and (self.policy == "off" or self.clock() < self.next_check))
        ):
            return
        self._start(self._check)

    def load_history(self):
        self._start(self._load_history)

    def install_release(self, release):
        """Called only after the UI confirms this exact version."""
        self._start(self._install, dict(release))

    def _start(self, action, *args):
        if self.busy or self.installed:
            return
        self._thread = threading.Thread(
            target=self._run, args=(action, *args), name="release-update", daemon=True
        )
        self._thread.start()

    def _run(self, action, *args):
        # A process may terminate during network work; installer transactions
        # recover at next bootstrap. Native hooks never belong to this worker.
        with self._lock:
            try:
                self.failed = False
                action(*args)
            except UpdateBusy as exc:
                self.message = str(exc)
                self.next_check = self.clock() + INTERVAL
            except Exception as exc:
                self.failed = True
                self.message = (
                    "版本操作未完成。请重试，或使用下方下载入口重新安装；"
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
        self.message = "正在检查稳定版更新…"
        release, cache = self.client.latest(self._read(self.directory / "release-cache.json"))
        write_json(self.directory / "release-cache.json", cache)
        self.last_check = self.clock()
        self.next_check = self.clock() + INTERVAL
        if not release or version_tuple(release["tag_name"]) <= version_tuple(
            self.distribution["version"]
        ):
            self.available = None
            self.release = None
            self.message = "当前已是最新稳定版" if release else "仓库尚未发布稳定版"
            return
        self.available = release["tag_name"]
        self.release = release
        self.message = f"发现 {self.available}；点击下载安装后才会更新"

    def _load_history(self):
        self.message = "正在获取历史稳定版本…"
        current = version_tuple(self.distribution["version"])
        self.history = [r for r in self.client.history() if version_tuple(r["tag_name"]) < current]
        self.history_loaded = True
        self.message = "请选择要回退的稳定版本" if self.history else "没有可回退的稳定版本"

    def _install(self, selection):
        if not (self.root / "installed-manifest.json").is_file():
            self.message = "开发目录不会被覆盖，请使用发行包"
            return
        tag = selection["tag_name"]
        current = version_tuple(self.distribution["version"])
        target = version_tuple(tag)
        if current == target:
            raise ValueError("所选版本已经安装")
        # Refresh only the confirmed tag. Checks/history never fetch packages,
        # and a newer release appearing during confirmation cannot replace it.
        self.message = "正在核对所选版本…"
        release = self.client.release(tag)
        if release["tag_name"] != tag:
            raise ValueError("所选版本发生变化")
        meta, asset = self.client.metadata(release)
        self.download_url = asset["browser_download_url"] if asset else self.download_url
        if "installer" in meta:
            setup = self.client.component_asset(release, meta["installer"])
            self.download_url = setup["browser_download_url"]
            self.download_is_installer = True
        component_update = bool(meta.get("components"))
        runtime_package = None
        self.message = f"正在下载 {tag}…"
        if component_update:
            path = self._download_component(release, meta, "application")
            receipt = self._read(self.root / "installed-manifest.json")
            if not receipt.get("runtime_id"):
                raise ValueError("旧源码版需要手动迁移到便携版")
            if receipt["runtime_id"] != meta["components"]["runtime_id"]:
                runtime_package = self._download_component(release, meta, "runtime")
        else:
            path = self.directory / meta["asset"]
            self.client.download(asset, meta, path, lambda ratio: setattr(self, "progress", ratio))
        self.message = "正在校验并安装所选版本…"
        options = {
            "component_update": component_update,
            "runtime_package": runtime_package,
            "rollback": target < current,
        }
        try:
            installed = install(self.root, path, meta, **options)
        except RuntimeRequired:
            if runtime_package is not None:
                raise
            options["runtime_package"] = self._download_component(release, meta, "runtime")
            installed = install(self.root, path, meta, **options)
        self.installed = True
        self.message = f"已安装 {installed}，界面正在刷新"
        self.next_check = float("inf")

    def _download_component(self, release, meta, kind):
        descriptor = meta["components"][kind]
        asset = self.client.component_asset(release, descriptor)
        path = self.directory / descriptor["asset"]
        self.message = "正在下载程序更新…" if kind == "application" else "正在下载变更的运行依赖…"
        self.client.download(
            asset, descriptor, path, lambda ratio: setattr(self, "progress", ratio)
        )
        return path
