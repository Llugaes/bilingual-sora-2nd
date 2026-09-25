"""Native-only settings, usable without Qt or a running game."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import math
import time
from sora_bilingual.config.locales import LOCALES, DEFAULT_PRIMARY, DEFAULT_SECONDARY

from sora_bilingual.paths import ROOT

CONTROL = ROOT / "generated" / "native-control.json"
ACTIONS = ("annotation", "language_toggle", "language_hold")
DEFAULT_BINDINGS = {
    action: {"keyboard": ["CTRL", "SHIFT", f"F{10 + i}"], "gamepad": {}}
    for i, action in enumerate(ACTIONS)
}
DEFAULTS = {
    "primary": DEFAULT_PRIMARY,
    "secondary": DEFAULT_SECONDARY,
    "game_language": DEFAULT_PRIMARY,
    "scope": "all",
    "sources": [],
    "enabled": True,
    "interaction": "annotation",
    "annotation_scale": 0.9,
    "ruby_scale": 0.8,
    "ruby_gap": 3,
    "ruby_offset_x": 0,
    "line_gap": 12,
    "hotkeys": DEFAULT_BINDINGS,
    "overlay_binding": {"keyboard": ["CTRL", "SHIFT", "F9"], "gamepad": {}},
}


def read_config(path=CONTROL):
    value = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    return normalize_config(value)


def normalize_config(value):
    if not isinstance(value, dict):
        raise ValueError("配置必须是 JSON 对象")
    result = deepcopy(DEFAULTS)
    result.update(value)
    if result["interaction"] not in (*ACTIONS, None):
        raise ValueError("未知显示模式")
    if not isinstance(value.get("hotkeys", {}), dict):
        raise ValueError("快捷键配置必须是对象")
    if any(
        not isinstance(result[k], str) or result[k] not in LOCALES
        for k in ("primary", "secondary", "game_language")
    ):
        raise ValueError("未知语言")
    if not isinstance(result["enabled"], bool):
        raise ValueError("启用状态必须是布尔值")
    if result.get("scope") not in ("all", "menu", "selected"):
        raise ValueError("未知文本范围")
    if not isinstance(result["sources"], list) or any(
        not isinstance(s, str) for s in result["sources"]
    ):
        raise ValueError("文本筛选必须是字符串列表")
    if result.get("mode", "primary") not in ("annotation", "primary", "secondary", "bilingual"):
        raise ValueError("未知渲染模式")
    result["hotkeys"] = deepcopy(DEFAULT_BINDINGS)
    for action, binding in value.get("hotkeys", {}).items():
        if action not in ACTIONS or not isinstance(binding, dict):
            raise ValueError("无效的快捷键配置")
        result["hotkeys"][action].update(binding)
    if "hotkeys" not in value and isinstance(value.get("hotkey"), dict):
        result["hotkeys"][value.get("interaction") or "annotation"] = deepcopy(value["hotkey"])
    for key, lo, hi in [
        ("annotation_scale", 0.7, 1),
        ("ruby_scale", 0.5, 1),
        ("ruby_gap", 0, 8),
        ("ruby_offset_x", -24, 24),
        ("line_gap", 0, 24),
    ]:
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("字号或间距超出范围：" + key)
    all_bindings = [*result["hotkeys"].values(), result["overlay_binding"]]
    for binding in all_bindings:
        if not isinstance(binding, dict):
            raise ValueError("快捷键配置必须是对象")
        keys = binding.get("keyboard", [])
        if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
            raise ValueError("键盘组合必须是按键名列表")
        from sora_bilingual.platform.inputs import vk_for_key

        if any(vk_for_key(k) is None for k in keys):
            raise ValueError("键盘组合含不支持的按键")
        pad = binding.get("gamepad", {})
        if not isinstance(pad, dict):
            raise ValueError("手柄配置必须是对象")
        buttons = pad.get("buttons", [])
        axes = pad.get("axes", [])
        if not isinstance(buttons, list) or any(type(b) is not int or b < 0 for b in buttons):
            raise ValueError("无效手柄按钮列表")
        if not isinstance(axes, list) or any(not isinstance(a, dict) for a in axes):
            raise ValueError("无效手柄轴列表")
        for axis in pad.get("axes", []):
            if (
                type(axis.get("index")) is not int
                or not 0 <= axis["index"] < 64
                or type(axis.get("direction")) is not int
                or axis.get("direction") not in (-1, 1)
                or type(axis.get("threshold")) not in (int, float)
                or not math.isfinite(axis["threshold"])
                or not -1 <= axis["threshold"] <= 1
            ):
                raise ValueError("无效手柄轴配置")
    bindings = [frozenset(str(k).upper() for k in b.get("keyboard", [])) for b in all_bindings]
    if len([b for b in bindings if b]) != len({b for b in bindings if b}):
        raise ValueError("显示动作和面板需要使用不同的键盘快捷键")
    for i, left in enumerate(bindings):
        if left and any(right and (left < right or right < left) for right in bindings[i + 1 :]):
            raise ValueError("快捷键不能包含另一个动作的完整组合，否则会同时触发")
    for i, binding in enumerate(all_bindings):
        pad = binding.get("gamepad", {})
        if not (pad.get("buttons") or pad.get("axes")):
            continue
        for other in all_bindings[i + 1 :]:
            other = other.get("gamepad", {})
            same_device = all(
                not pad.get(k) or not other.get(k) or pad[k] == other[k]
                for k in ("guid", "instance_id")
            )
            if (
                same_device
                and set(pad.get("buttons", [])) == set(other.get("buttons", []))
                and sorted(pad.get("axes", []), key=lambda a: a["index"])
                == sorted(other.get("axes", []), key=lambda a: a["index"])
            ):
                raise ValueError("显示动作和面板需要使用不同的手柄组合")
    return result


def replace_file(source, destination):
    # Windows readers may briefly omit FILE_SHARE_DELETE. Retry the atomic
    # replacement, never truncate a status/config file that another reader uses.
    for attempt in range(5):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.002)


def write_config(value, path=CONTROL):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        replace_file(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


class ActionPolicy:
    """Independent bindings. Hold is temporary and restores the previous view."""

    def __init__(self, interaction="annotation"):
        self.interaction = interaction
        self.base = "annotation" if interaction == "annotation" else "primary"

    def advance(self, states):
        if states["annotation"].pressed:
            self.base = "primary" if self.base == "annotation" else "annotation"
            self.interaction = "annotation"
        if states["language_toggle"].pressed:
            self.base = "primary" if self.base == "secondary" else "secondary"
            self.interaction = "language_toggle"
        return "secondary" if states["language_hold"].held else self.base


class BackendLock:
    """OS-owned lock: crashes release it, a stale file never blocks startup."""

    def __init__(self, path=ROOT / "generated" / "native-backend.lock"):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        import msvcrt

        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise RuntimeError("双语后端已经运行，请直接打开设置。")

    def close(self):
        self.file.close()
