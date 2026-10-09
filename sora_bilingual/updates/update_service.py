"""Background stable-release checks; no network or archive work on Qt's thread."""

import json
import math
from pathlib import Path
import threading
import time
from sora_bilingual.updates.github_updates import GitHubClient, version_tuple
from sora_bilingual.updates.release_sources import ReleaseSources
from sora_bilingual.updates.release_client import metadata_identity
from sora_bilingual.updates.update_installer import install, UpdateBusy, RuntimeRequired, write_json
from sora_bilingual.paths import build_label

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
            ReleaseSources(
                self.distribution["repository"],
                self.distribution["version"],
                gitee_index=self.distribution.get("gitee_index"),
                directory=self.directory,
                clock=self.clock,
            )
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
        self.backup_download_url = (
            f"https://github.com/{self.distribution['repository']}/releases/latest"
        )
        self.has_domestic_source = self.distribution.get("gitee_mirror") is True
        self.download_url = (
            f"https://gitee.com/{self.distribution['repository']}/releases"
            if self.has_domestic_source
            else self.backup_download_url
        )
        self.progress = None
        state = self._read(self.directory / "check-state.json")
        if (
            state.get("version") != self.distribution["version"]
            or state.get("repository") != self.distribution["repository"]
        ):
            state = {}
        now = self.clock()
        number = lambda value: value if type(value) in (int, float) and math.isfinite(value) else 0
        self.last_check = min(max(number(state.get("last_check")), 0), now)
        self.next_check = min(max(number(state.get("next_check")), 0), now + INTERVAL)
        self.manual_after = min(max(number(state.get("manual_after")), 0), now + 60)
        self.failure_until = min(max(number(state.get("failure_until")), 0), now + INTERVAL)
        self.failure_count = min(max(int(number(state.get("failure_count"))), 0), 5)
        self.history_checked_at = 0
        self._thread = None
        self._lock = threading.Lock()
        remembered = state.get("release")
        if isinstance(remembered, dict):
            try:
                if version_tuple(remembered.get("tag_name")) > version_tuple(
                    self.distribution["version"]
                ):
                    self.available = remembered["tag_name"]
                    self.release = remembered
                    self.message = f"上次检查发现 {self.available}；确认后才会下载安装"
            except ValueError:
                pass
        if state.get("failed") is True:
            self.failed = True
            self.message = "上次更新检查未完成；请稍后重试，或使用下载入口手动重新安装"

    def _save_check_state(self):
        release = None
        if self.release:
            release = {
                key: self.release[key]
                for key in ("tag_name", "name", "_source", "_manifest_identity")
                if key in self.release
            }
        write_json(
            self.directory / "check-state.json",
            {
                "version": self.distribution["version"],
                "repository": self.distribution["repository"],
                "last_check": self.last_check,
                "next_check": self.next_check
                if math.isfinite(self.next_check)
                else self.clock() + INTERVAL,
                "manual_after": self.manual_after,
                "failure_until": self.failure_until,
                "failure_count": self.failure_count,
                "failed": self.failed,
                "release": release,
            },
        )

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

    @property
    def _can_request(self):
        return not self.installed and not self.busy and self.clock() >= self.failure_until

    @property
    def can_check(self):
        return self._can_request and self.clock() >= self.manual_after

    def set_policy(self, value):
        if value not in POLICIES:
            raise ValueError("未知更新策略")
        self.policy = value
        write_json(self.preferences, {"policy": value})
        if not self.busy:
            self.message = "等待检查更新" if value == "notify" else "自动检查已关闭"

    def tick(self, manual=False):
        if not self.can_check or (
            not manual and (self.policy == "off" or self.clock() < self.next_check)
        ):
            return
        # Persist before spawning: a restart during a request must not reset
        # the manual cooldown and repeatedly hammer either provider.
        self.manual_after = self.clock() + 60
        try:
            self._save_check_state()
        except OSError as exc:
            self._record_failure(exc)
            return
        self._start(self._check)

    def load_history(self):
        if not self._can_request or (
            self.history_loaded and 0 <= self.clock() - self.history_checked_at < INTERVAL
        ):
            return
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

    def _record_failure(self, exc):
        self.failed = True
        self.message = (
            "版本操作未完成。请重试，或使用下方下载入口重新安装；"
            "原目录与配置请保留。详细原因见日志。"
        )
        self.failure_count = min(self.failure_count + 1, 5)
        self.failure_until = self.clock() + min(900 * 2 ** (self.failure_count - 1), INTERVAL)
        self.next_check = self.failure_until
        try:
            write_json(
                self.directory / "last-error.json",
                {"time": self.clock(), "error": str(exc)},
            )
        except OSError:
            pass  # A read-only/full disk must not also break the recovery UI.

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
                self._record_failure(exc)
            finally:
                self.progress = None
                try:
                    self._save_check_state()
                except OSError:
                    pass

    def _check(self, manual=False):
        self.message = "正在检查稳定版更新…"
        release, cache = self.client.latest(self._read(self.directory / "release-cache.json"))
        write_json(self.directory / "release-cache.json", cache)
        self.last_check = self.clock()
        self.next_check = self.clock() + INTERVAL
        self.manual_after = self.clock() + 60
        self.failure_until = self.failure_count = 0
        self.failed = False
        self.history_loaded = False
        if not release or version_tuple(release["tag_name"]) <= version_tuple(
            self.distribution["version"]
        ):
            self.available = None
            self.release = None
            self.message = "当前已是最新稳定版" if release else "仓库尚未发布稳定版"
            self._save_check_state()
            return
        self.available = release["tag_name"]
        self.release = release
        self.message = f"发现 {self.available}；点击下载安装后才会更新"
        self._save_check_state()

    def _load_history(self):
        self.message = "正在获取历史稳定版本…"
        current = version_tuple(self.distribution["version"])
        self.history = [r for r in self.client.history() if version_tuple(r["tag_name"]) < current]
        self.history_loaded = True
        self.history_checked_at = self.clock()
        self.message = "请选择要回退的稳定版本" if self.history else "没有可回退的稳定版本"

    def _install(self, selection):
        if build_label(self.root, self.distribution["version"]).startswith("DEV"):
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
        if selection.get("_manifest_identity") and selection[
            "_manifest_identity"
        ] != metadata_identity(meta):
            raise ValueError("所确认版本的更新清单发生变化，请重新检查并确认")
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
