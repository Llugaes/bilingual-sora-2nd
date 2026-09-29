"""Reconnect to one disabled game-owned agent; never leave a helper process."""

import json
import secrets
import socket
import struct
import threading
from pathlib import Path

import frida

from sora_bilingual.config.native_config import write_config
from sora_bilingual.paths import STATE
from sora_bilingual.platform.win32 import process_identity

AGENT = STATE / "native-agent.json"
LIMIT = 16 * 1024 * 1024


class AgentClient:
    def __init__(self, record):
        self.revision = record.get("revision")
        self.socket = socket.create_connection(("127.0.0.1", record["port"]), timeout=15)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.lock = threading.Lock()
        try:
            hello = self._exchange({"token": record["token"], "method": "hello"})
            if hello != {"protocol": 1, "pid": record["pid"]}:
                raise ValueError("游戏内模块身份不符")
        except Exception:
            self.close()
            raise

    def _read(self, size):
        data = bytearray()
        while len(data) < size:
            part = self.socket.recv(size - len(data))
            if not part:
                raise OSError("游戏内模块连接已结束")
            data.extend(part)
        return data

    def _exchange(self, request):
        data = json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        if len(data) > LIMIT:
            raise ValueError("Control request too large")
        self.socket.sendall(struct.pack("<I", len(data)) + data)
        size = struct.unpack("<I", self._read(4))[0]
        if not 0 < size <= LIMIT:
            raise ValueError("Invalid control response")
        response = json.loads(self._read(size))
        if not response.get("ok"):
            raise frida.RPCException(response.get("error", "Control failed"))
        return response.get("value")

    def __getattr__(self, name):
        def call(*args):
            with self.lock:
                return self._exchange({"method": name, "args": args})

        return call

    def close(self):
        self.socket.close()


def reconnect(pid, exe, path=AGENT):
    try:
        record = json.loads(Path(path).read_text("utf-8"))
    except OSError, ValueError:
        return None
    if record.get("pid") != pid or record.get("created") != process_identity(pid):
        return None
    if record.get("exe") != str(Path(exe).resolve()) or record.get("protocol") != 1:
        raise ValueError("当前游戏已有不同版本的驻留模块，请重新启动游戏")
    if record.get("unavailable"):
        raise ValueError("上次游戏内模块初始化未完成，请重新启动游戏")
    # A matching but unreachable agent is never permission to double-hook.
    return AgentClient(record)


def reserve(pid, exe, path=AGENT):
    """A partial initialization must never authorize a second hook install."""
    write_config(
        {
            "pid": pid,
            "created": process_identity(pid),
            "exe": str(Path(exe).resolve()),
            "protocol": 1,
            "unavailable": True,
        },
        Path(path),
    )


def publish(script, pid, exe, path=AGENT, *, revision=None, eternalize=True):
    token = secrets.token_hex(32)
    address = script.exports_sync.startcontrol(token)
    if address.get("protocol") != 1 or address.get("pid") != pid:
        raise ValueError("Invalid resident control endpoint")
    if eternalize:
        script.eternalize()
    record = {
        **address,
        "token": token,
        "created": process_identity(pid),
        "exe": str(Path(exe).resolve()),
        "revision": revision,
    }
    write_config(record, Path(path))
    return AgentClient(record)
