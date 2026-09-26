"""Native-only settings, usable without Qt or a running game."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import math
import time
from sora_bilingual.config.locales import (
    LOCALES,
    DEFAULT_PRIMARY,
    DEFAULT_SECONDARY,
    language_defaults,
)

from sora_bilingual.paths import ROOT

CONTROL = ROOT / "generated" / "native-control.json"
LANGUAGE_DEFAULTS_PENDING = "language_defaults_pending"
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
    "annotation_scale": 0.85,
    "ruby_scale": 0.9,
    "ruby_gap": 0,
    "ruby_offset_x": 0,
    "line_gap": 6,
    "secondary_color": [230 / 255, 230 / 255, 230 / 255],
    "secondary_opacity": 0.9,
    "bilingual_offset_y": 0,
    "hotkeys": DEFAULT_BINDINGS,
    "overlay_binding": {"keyboard": ["CTRL", "SHIFT", "F9"], "gamepad": {}},
    "ui_language": "auto",
}


def switch_binding(value):
    """Migrate the user's actual controller/keyboard bindings once, not on mode changes."""
    if "switch_binding" in value:
        return deepcopy(value["switch_binding"])
    bindings = value.get("hotkeys", {})
    preferred = value.get("interaction") or "annotation"
    order = list(dict.fromkeys((preferred, *ACTIONS)))
    result = deepcopy(DEFAULT_BINDINGS["annotation"])
    for action in order:
        binding = bindings.get(action, {})
        if binding.get("keyboard") and binding["keyboard"] != DEFAULT_BINDINGS[action]["keyboard"]:
            result["keyboard"] = deepcopy(binding["keyboard"])
            break
    for action in order:
        pad = bindings.get(action, {}).get("gamepad", {})
        if not isinstance(pad, dict):
            raise ValueError("手柄配置必须是对象")
        if pad.get("buttons") or pad.get("axes"):
            result["gamepad"] = deepcopy(pad)
            break
    if not bindings and isinstance(value.get("hotkey"), dict):
        result.update(deepcopy(value["hotkey"]))
    return result


def read_config(path=CONTROL):
    value = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    return normalize_config(value)


def normalize_config(value):
    if not isinstance(value, dict):
        raise ValueError("配置必须是 JSON 对象")
    result = deepcopy(DEFAULTS)
    result.update(language_defaults(value.get("game_language", DEFAULT_PRIMARY)))
    result.update(value)
    if LANGUAGE_DEFAULTS_PENDING in value and type(value[LANGUAGE_DEFAULTS_PENDING]) is not bool:
        raise ValueError("首次语言默认标记必须是布尔值")
    if result["interaction"] not in (*ACTIONS, None):
        raise ValueError("未知显示模式")
    if not isinstance(value.get("hotkeys", {}), dict):
        raise ValueError("快捷键配置必须是对象")
    if result["ui_language"] not in ("auto", "zh-Hans", "en", "ja"):
        raise ValueError("未知界面语言")
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
        ("secondary_opacity", 0, 1),
        ("bilingual_offset_y", -24, 24),
    ]:
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("字号或间距超出范围：" + key)
    result["switch_binding"] = switch_binding(value)
    color = result["secondary_color"]
    if (
        not isinstance(color, list)
        or len(color) != 3
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in color
        )
    ):
        raise ValueError("副语言颜色必须为三个 0..1 的 RGB 系数")
    all_bindings = [result["switch_binding"], result["overlay_binding"]]
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


def apply_pending_language_defaults(config, game_language):
    """Consume a new-user default marker after source detection succeeds."""
    if config.get(LANGUAGE_DEFAULTS_PENDING) is not True:
        return config
    result = deepcopy(config)
    result.update(language_defaults(game_language))
    result.pop(LANGUAGE_DEFAULTS_PENDING, None)
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
    """One binding, whose semantics follow the selected mode. No implicit mode changes."""

    def __init__(self, interaction="annotation"):
        self.interaction = interaction
        self.base = "annotation" if interaction == "annotation" else "primary"

    def advance(self, state):
        if self.interaction == "language_hold":
            return "secondary" if state.held else "primary"
        if self.interaction == "annotation" and state.pressed:
            self.base = "primary" if self.base == "annotation" else "annotation"
        if self.interaction == "language_toggle" and state.pressed:
            self.base = "primary" if self.base == "secondary" else "secondary"
        return self.base


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
