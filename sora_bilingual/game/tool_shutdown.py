"""Installation-local exit request and verified backend process ownership."""

import json
import os
from pathlib import Path
import time

from sora_bilingual.config.native_config import BackendLock, write_config
from sora_bilingual.platform.win32 import process_identity


class ExitSignal:
    def __init__(self, state):
        self.path = Path(state) / "tool-exit.json"
        self.next_check = 0
        self.requested = False

    def is_set(self):
        if self.requested or time.monotonic() < self.next_check:
            return self.requested
        self.next_check = time.monotonic() + 0.05
        try:
            self.requested = json.loads(self.path.read_text("utf-8")).get("requested") is True
        except OSError, ValueError:
            pass
        return self.requested


def register_backend(state):
    pid = os.getpid()
    write_config({"pid": pid, "created": process_identity(pid)}, Path(state) / "native-owner.json")


def backend_alive(state):
    try:
        value = json.loads((Path(state) / "native-owner.json").read_text("utf-8"))
        return process_identity(value["pid"]) == value["created"]
    except OSError, ValueError, KeyError:
        return False


def reset_exit(state):
    write_config({"requested": False}, Path(state) / "tool-exit.json")


def shutdown(state, connector=None, timeout=20):
    state = Path(state)
    write_config({"requested": True}, state / "tool-exit.json")
    if connector is not None:
        connector.close()
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock = BackendLock(state / "native-backend.lock")
        except RuntimeError:
            lock = None
        if lock is not None:
            lock.close()
            child = getattr(connector, "process", None)
            if not backend_alive(state) and (child is None or child.poll() is not None):
                return
        if time.monotonic() >= deadline:
            raise RuntimeError("后端尚未安全退出；若当前游戏连接来自旧版本，请退出游戏后重试。")
        time.sleep(0.05)
