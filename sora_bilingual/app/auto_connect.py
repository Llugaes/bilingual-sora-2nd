"""Background discovery and external caches. Never writes game installation files."""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import frida

from sora_bilingual.platform.runtime_process import runtime_executable
from sora_bilingual.paths import ROOT


def _resource_change_hint(game):
    """Cheap prewarm scheduling only; never a cache/connection validity proof."""
    return tuple(
        (path.name, (stat := path.stat()).st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
        for path in sorted((Path(game) / "pac/steam").glob("*.pac"))
        if path.name.startswith(("script", "table"))
    )


class ConnectionPolicy:
    def __init__(self):
        self.attempted = set()

    def choose(self, games, backend_busy):
        if backend_busy or len(games) != 1:
            return None
        game = next(iter(games))
        if game in self.attempted:
            return None
        self.attempted.add(game)
        return game

    def retry(self, games):
        """Allow one fresh launch for the currently observed game identity."""
        self.attempted.difference_update(games)


class AutoConnector:
    def __init__(self, status_path):
        self.status_path = Path(status_path)
        self.policy = ConnectionPolicy()
        self.process = None
        self.message = "自动连接已开启，等待游戏启动"
        self.error = None
        # A separate durable prerequisite from the live text backend. The UI
        # can display this object even while a game is already connected.
        self.font_status = {"state": "idle", "message": "等待发现游戏目录"}
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.retry_requested = threading.Event()
        self.preparations = []
        self.thread = threading.Thread(target=self._run, name="auto-connect", daemon=True)
        self.thread.start()

    def retry(self):
        """Request a safe reconnect after a failed, non-resident backend.

        The coordinator owns process creation, so this never terminates or
        detaches a resident backend and cannot create a second live process.
        """
        if self.stop.is_set():
            return False
        self.error = None
        self.retry_requested.set()
        self.wake.set()
        return True

    def _run(self):
        from sora_bilingual.platform.win32 import process_identity, process_path
        from sora_bilingual.game.install import find_game
        from sora_bilingual.game.native_loading import (
            ModelPreparation,
            prepare_fresh,
            prepare_fonts_fresh,
            prepare_runtime_fonts_fresh,
        )
        from sora_bilingual.config.locales import LOCALES
        from sora_bilingual.config.native_config import read_config, apply_detected_game_language
        from sora_bilingual.localization.native_catalog import fingerprint, model_path
        from sora_bilingual.localization.model_wire import wire_ready
        from sora_bilingual.updates.tool_updates import ReleaseWatch
        from sora_bilingual.fonts.font_delivery import source_fingerprint

        releases = ReleaseWatch()
        device = None
        preparation = ModelPreparation(
            lambda c: prepare_fresh(c["game"], c["config"], cache_only=True, cancel=self.stop),
            lambda c: c,
        )
        font_preparation = ModelPreparation(
            lambda c: prepare_fonts_fresh(c["game"], cancel=self.stop), lambda c: c
        )

        font_apply = ModelPreparation(
            lambda c: prepare_runtime_fonts_fresh(c["game"], cancel=self.stop),
            lambda c: c,
        )
        self.preparations = [preparation, font_preparation, font_apply]
        self.game_running = None
        preparing_key = None
        preparation_error = None
        installed_game = None
        font_game = None
        font_candidate = None
        font_action = None
        font_fingerprint = None
        next_font_check = 0
        next_discovery = 0
        next_model_check = 0
        model_check_identity = None
        model_resource_hint = None
        source_retry_identity = None
        source_retry_count = 0
        next_source_retry = 0
        while not self.stop.is_set():
            try:
                if (ROOT / "generated/update-installing.json").exists():
                    self.message = "正在安装更新，稍后自动连接"
                    self.wake.wait(1)
                    self.wake.clear()
                    continue
                if device is None:
                    device = frida.get_local_device()
                games = set()
                for p in device.enumerate_processes():
                    if p.name.lower() == "sora_2nd.exe":
                        try:
                            games.add((p.pid, process_identity(p.pid)))
                        except OSError:
                            pass
                self.game_running = bool(games)
                try:
                    status = json.loads(self.status_path.read_text("utf-8"))
                except OSError, ValueError:
                    status = {}
                busy = bool(
                    status.get("running") and 0 <= time.time() - status.get("updated_at", 0) < 5
                )
                if self.process is not None:
                    if self.process.poll() is None:
                        busy = True
                    else:
                        source_unready = status.get("source_language_status") == "table_unready"
                        if source_unready and len(games) == 1:
                            identity = next(iter(games))
                            if identity != source_retry_identity:
                                source_retry_identity = identity
                                source_retry_count = 0
                            source_retry_count += 1
                            # The table is populated after process creation on
                            # some machines.  Retry the same PID identity at a
                            # bounded cadence, without treating it as an
                            # ordinary launch failure or replacing a resident.
                            next_source_retry = time.monotonic() + min(
                                8, 0.5 * (2 ** min(source_retry_count - 1, 4))
                            )
                            self.policy.retry(games)
                            self.message = "等待游戏文本表就绪，稍后自动重试"
                        elif self.process.returncode:
                            try:
                                self.error = (
                                    (ROOT / "generated/native-error.log")
                                    .read_text("utf-8")
                                    .strip()
                                    .splitlines()[-1]
                                )
                            except OSError, IndexError:
                                self.error = "连接未成功"
                        self.process = None
                # A manual retry only clears the one-shot identity after the
                # old launcher is gone and status no longer says a resident
                # backend is alive.  It cannot duplicate an active attach.
                if self.retry_requested.is_set() and self.process is None and not busy:
                    self.policy.retry(games)
                    next_source_retry = 0
                    self.retry_requested.clear()
                changes = releases.poll()
                if not busy and changes & {"resident", "catalog", "logic"}:
                    # One attempt with the new release, never replace a live
                    # or initializing resident backend.
                    self.policy.attempted.difference_update(games)
                    next_model_check = 0
                    model_resource_hint = None
                prepared = preparation.poll()
                if prepared and prepared[0].get("key") == preparing_key:
                    preparation_error = "预缓存失败：" + str(prepared[2]) if prepared[2] else None
                fonts_prepared = font_preparation.poll()
                if fonts_prepared and fonts_prepared[0]["game"] == installed_game:
                    if fonts_prepared[2]:
                        font_fingerprint = None
                        next_font_check = time.monotonic() + 30
                        self.font_status = {
                            "state": "error",
                            "message": "字体准备失败",
                            "detail": str(fonts_prepared[2]),
                        }
                    else:
                        font_candidate = fonts_prepared[1]
                        font_action = None
                        self.font_status = {
                            "state": "prepared",
                            "message": "字体已准备，正在校验运行时资源",
                            "candidate": str(font_candidate),
                        }
                fonts_applied = font_apply.poll()
                if fonts_applied and fonts_applied[0]["game"] == installed_game:
                    applied_config, _, error = fonts_applied
                    font_action = str(applied_config["candidate"])
                    if error:
                        self.font_status = {
                            "state": "error",
                            "message": "字体资源校验失败",
                            "detail": str(error),
                        }
                    else:
                        self.font_status = {
                            "state": "runtime-required",
                            "message": "字体已准备，连接后将在游戏内加载，无需重启",
                            "restart_required": False,
                        }
                # Resolving a running process is read-only and lets font
                # preparation start without waiting for the live backend.
                if len(games) == 1:
                    try:
                        installed_game = process_path(next(iter(games))[0]).parent
                    except OSError:
                        pass
                if installed_game is None and time.monotonic() >= next_discovery:
                    installed_game = find_game()
                    next_discovery = time.monotonic() + 30
                if installed_game is not None and str(installed_game) != font_game:
                    font_game = str(installed_game)
                    font_candidate = None
                    font_action = None
                    font_fingerprint = None
                    next_font_check = 0
                    preparing_key = None
                # The source identity uses only archive metadata and source
                # hashes. Poll it infrequently so an idle coordinator never
                # re-reads or rebuilds fonts every connection tick.
                if (
                    installed_game is not None
                    and not font_preparation.active
                    and time.monotonic() >= next_font_check
                ):
                    next_font_check = time.monotonic() + 30
                    try:
                        current_font_fingerprint = source_fingerprint(installed_game)
                    except Exception as exc:
                        font_fingerprint = None
                        self.font_status = {
                            "state": "error",
                            "message": "字体准备失败",
                            "detail": str(exc),
                        }
                    else:
                        if self.font_status.get("state") == "error" and font_candidate is not None:
                            # Retry a transient verification error at this
                            # low-frequency boundary, never each connection tick.
                            font_action = None
                        if current_font_fingerprint != font_fingerprint:
                            font_fingerprint = current_font_fingerprint
                            font_candidate = None
                            font_action = None
                            self.font_status = {
                                "state": "preparing",
                                "message": "正在从本机游戏资源准备多语言字体",
                            }
                            font_preparation.request({"game": installed_game})
                if font_candidate is not None and not font_preparation.active:
                    # Verify external resources off the coordinator. Starting,
                    # exiting or reconnecting a game never installs loose files.
                    action = str(font_candidate)
                    if action != font_action and not font_apply.active:
                        font_apply.request(
                            {
                                "game": installed_game,
                                "candidate": font_candidate,
                            }
                        )
                # Offline prewarming can only use a language confirmed during
                # the previous game process. A newly observed PID is always
                # left to native_probe's one-shot table detector before any
                # model for that process is selected or applied.
                if not busy and not games:
                    if installed_game is not None:
                        config = read_config()
                        previous_source = status.get("last_detected_game_language")
                        if (
                            status.get("source_language_status") != "game_not_running"
                            or previous_source not in LOCALES
                            or status.get("game_directory", str(installed_game.resolve()))
                            != str(installed_game.resolve())
                        ):
                            config = None
                        else:
                            config = apply_detected_game_language(config, previous_source)
                    else:
                        config = None
                    if config is not None:
                        identity = {
                            k: config.get(k)
                            for k in ("primary", "secondary", "game_language", "scope", "sources")
                        }
                        check_identity = (str(installed_game), json.dumps(identity, sort_keys=True))
                        now = time.monotonic()
                        if check_identity != model_check_identity or now >= next_model_check:
                            # fingerprint verifies the contents of every script/table
                            # archive. It is no longer a cheap metadata query: do not
                            # hash hundreds of MiB on each 250 ms process poll.
                            # Stat is only a prewarm hint. Actual preparation and
                            # every new connection still verify complete contents,
                            # including same-size/same-mtime resource changes.
                            next_model_check = now + 30
                            hint = _resource_change_hint(installed_game)
                            if (
                                check_identity != model_check_identity
                                or hint != model_resource_hint
                            ):
                                key = (
                                    str(installed_game),
                                    json.dumps(fingerprint(installed_game), sort_keys=True),
                                    check_identity[1],
                                )
                                model_check_identity = check_identity
                                model_resource_hint = hint
                                if key != preparing_key:
                                    if not wire_ready(model_path(key[1], config)):
                                        preparation_error = None
                                        preparation.request(
                                            {"game": installed_game, "config": config, "key": key}
                                        )
                                    preparing_key = key
                # An old-process prewarm is never a reason to delay checking
                # the new process's current source language.
                selected = self.policy.choose(games, busy)
                if selected is not None and time.monotonic() < next_source_retry:
                    # ``choose`` records an identity; restore it while the
                    # table-ready retry backoff is still in force.
                    self.policy.attempted.discard(selected)
                    selected = None
                if not games:
                    if self.font_status.get("state") == "runtime-ready":
                        self.font_status = {
                            "state": "runtime-required",
                            "message": "字体已准备，连接后将在游戏内加载，无需重启",
                            "restart_required": False,
                        }
                    self.error = None
                    source_retry_identity = None
                    source_retry_count = 0
                    next_source_retry = 0
                    self.message = self.font_status.get("message", "自动连接已开启，等待游戏启动")
                elif len(games) > 1:
                    self.message = "检测到多个游戏进程，请保留一个"
                elif busy:
                    self.error = None
                    self.message = "自动连接正在运行"
                elif len(games) == 1 and time.monotonic() < next_source_retry:
                    self.message = "等待游戏文本表就绪，稍后自动重试"
                elif selected is not None:
                    self.error = None
                    self.message = "已发现游戏，正在自动连接…"
                    executable = runtime_executable("backend")
                    self.process = subprocess.Popen(
                        [str(executable), "-m", "sora_bilingual.game.native_probe"],
                        cwd=ROOT,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                elif self.error:
                    self.message = "连接失败：" + self.error
                if preparation.active and not games:
                    self.message = "正在后台准备语言缓存，可直接启动游戏"
                elif preparation_error and not games:
                    self.message = preparation_error
                # A staged runtime font is a separate prerequisite.  It must
                # not replace the failed backend's diagnostic: the same game
                # can have a valid staged font and an unsupported executable
                # (or another connection failure).
                elif self.font_status.get("state") == "runtime-required" and not self.error:
                    self.message = self.font_status["message"]
                runtime_fonts = status.get("runtimeFonts")
                if (
                    runtime_fonts
                    and status.get("running")
                    and 0 <= time.time() - status.get("updated_at", 0) < 5
                    and any(pid == status.get("pid") for pid, _ in games)
                ):
                    if runtime_fonts.get("ready"):
                        self.font_status = {
                            "state": "runtime-ready",
                            "message": "游戏内多语言字体已就绪",
                        }
                    elif runtime_fonts.get("state") == "error":
                        self.font_status = {
                            "state": "error",
                            "message": "游戏内字体加载失败",
                            "detail": runtime_fonts.get("error"),
                        }
            except Exception as exc:
                device = None
                self.message = "自动检测暂不可用：" + str(exc)
            # Process discovery/status is not the input/render loop. Two checks
            # per second bound idle enumeration cost; explicit retry/close still
            # wake immediately through the event.
            self.wake.wait(0.5)
            self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError("自动连接尚未停止，请稍后重试退出")
        for preparation in self.preparations:
            preparation.close()
