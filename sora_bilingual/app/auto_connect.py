"""Background game discovery. Never launches games or replaces live hooks."""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import frida

from sora_bilingual.paths import ROOT


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
        from sora_bilingual.game.native_loading import ModelPreparation, prepare_fresh
        from sora_bilingual.config.locales import LOCALES
        from sora_bilingual.config.native_config import read_config
        from sora_bilingual.localization.native_catalog import fingerprint, model_path
        from sora_bilingual.localization.model_wire import wire_ready
        from sora_bilingual.updates.tool_updates import ReleaseWatch
        from sora_bilingual.fonts.font_delivery import ensure, prepare, source_fingerprint

        releases = ReleaseWatch()
        device = None
        preparation = ModelPreparation(
            lambda c: prepare_fresh(c["game"], c["config"], cache_only=True), lambda c: c
        )
        font_preparation = ModelPreparation(lambda c: prepare(c["game"]), lambda c: c)

        def is_game_running():
            try:
                return any(
                    process.name.lower() == "sora_2nd.exe"
                    for process in frida.get_local_device().enumerate_processes()
                )
            except Exception:
                # Font delivery fails closed if a fresh process query is unavailable.
                return True

        font_apply = ModelPreparation(
            lambda c: ensure(
                c["game"],
                c["candidate"],
                game_running=c["game_running"],
                is_game_running=is_game_running,
            ),
            lambda c: c,
        )
        preparing_key = None
        preparation_error = None
        installed_game = None
        font_game = None
        font_candidate = None
        font_action = None
        font_fingerprint = None
        next_font_check = 0
        next_discovery = 0
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
                prepared = preparation.poll()
                if prepared:
                    preparation_error = "预缓存失败：" + str(prepared[2]) if prepared[2] else None
                fonts_prepared = font_preparation.poll()
                if fonts_prepared:
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
                            "message": "字体已准备，等待安全安装",
                            "candidate": str(font_candidate),
                        }
                fonts_applied = font_apply.poll()
                if fonts_applied:
                    applied_config, result, error = fonts_applied
                    font_action = (
                        str(applied_config["candidate"]),
                        bool(applied_config["game_running"]),
                    )
                    if error:
                        self.font_status = {
                            "state": "error",
                            "message": "字体安装失败",
                            "detail": str(error),
                        }
                    else:
                        state = result["state"]
                        messages = {
                            "healthy": "多语言字体已就绪",
                            "installed": "多语言字体已安装",
                            "restart-required": "字体已准备；请退出并重启游戏后生效",
                            "conflict": "字体安装与已有 MOD 文件冲突",
                        }
                        self.font_status = {
                            "state": state,
                            "message": messages.get(state, "字体状态未知"),
                            "detail": result.get("conflicts") or result.get("missing") or [],
                            "restart_required": state == "restart-required",
                        }
                        if state == "restart-required":
                            # The fresh pre-write query can see a game that
                            # started after the snapshot. Treat it as the
                            # running action until the process later exits.
                            font_action = (str(applied_config["candidate"]), True)
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
                            # Retry a transient installation error at this
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
                    # A game process may keep its atlas in memory. Never alter
                    # its files until it is gone. Verification and the
                    # transaction run off this connection coordinator so they
                    # cannot delay attaching an already healthy backend.
                    action = (str(font_candidate), bool(games))
                    if action != font_action and not font_apply.active:
                        font_apply.request(
                            {
                                "game": installed_game,
                                "candidate": font_candidate,
                                "game_running": bool(games),
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
                        ):
                            config = None
                        else:
                            config = {**config, "game_language": previous_source}
                    else:
                        config = None
                    if config is not None:
                        identity = {
                            k: config.get(k)
                            for k in ("primary", "secondary", "game_language", "scope", "sources")
                        }
                        key = (
                            str(installed_game),
                            json.dumps(fingerprint(installed_game), sort_keys=True),
                            json.dumps(identity, sort_keys=True),
                        )
                        if key != preparing_key:
                            if not wire_ready(model_path(key[1], config)):
                                preparation_error = None
                                preparation.request({"game": installed_game, "config": config})
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
                    executable = Path(sys.executable).with_name("pythonw.exe")
                    self.process = subprocess.Popen(
                        [str(executable), "-m", "sora_bilingual.game.native_probe"],
                        cwd=ROOT,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                elif self.error:
                    self.message = "连接失败：" + self.error
                if preparation.active and not games:
                    self.message = "正在后台准备语言缓存，完成后自动连接"
                elif preparation_error and not games:
                    self.message = preparation_error
                elif self.font_status.get("state") == "restart-required":
                    self.message = self.font_status["message"]
            except Exception as exc:
                device = None
                self.message = "自动检测暂不可用：" + str(exc)
            self.wake.wait(0.25)
            self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=2)
