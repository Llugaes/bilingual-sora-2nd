"""Describe raw bindings using SDL's device mapping, without changing input semantics.

Profiles store positional SDL controls, so selecting a label style never changes
the raw button/axis that activates a shortcut. SDL metadata is read only when a
device is discovered, not on each input tick; saved profiles also work offline.
"""

from __future__ import annotations

import ctypes
from functools import lru_cache
from pathlib import Path
import re
import sys
from typing import Any, Iterable


LABEL_STYLES = ("auto", "playstation", "xbox", "switch")
_SWITCH_TYPES = {5, 11, 12, 13}
_BUTTONS = {
    "playstation": {
        "a": "×",
        "b": "○",
        "x": "□",
        "y": "△",
        "leftshoulder": "L1",
        "rightshoulder": "R1",
        "lefttrigger": "L2",
        "righttrigger": "R2",
        "leftstick": "L3",
        "rightstick": "R3",
        "back": "SHARE / Create",
        "start": "OPTIONS",
        "guide": "PS",
        "touchpad": "触摸板按下",
        "misc1": "麦克风键",
    },
    "xbox": {
        "a": "A",
        "b": "B",
        "x": "X",
        "y": "Y",
        "leftshoulder": "LB",
        "rightshoulder": "RB",
        "lefttrigger": "LT",
        "righttrigger": "RT",
        "leftstick": "LS（按下）",
        "rightstick": "RS（按下）",
        "back": "View",
        "start": "Menu",
        "guide": "Xbox",
        "misc1": "Share",
    },
    "switch": {
        "a": "B",
        "b": "A",
        "x": "Y",
        "y": "X",
        "leftshoulder": "L",
        "rightshoulder": "R",
        "lefttrigger": "ZL",
        "righttrigger": "ZR",
        "leftstick": "左摇杆按下",
        "rightstick": "右摇杆按下",
        "back": "−",
        "start": "+",
        "guide": "HOME",
        "misc1": "截图键",
    },
    "generic": {
        "a": "下方面键",
        "b": "右侧面键",
        "x": "左侧面键",
        "y": "上方面键",
        "leftshoulder": "左肩键",
        "rightshoulder": "右肩键",
        "lefttrigger": "左扳机",
        "righttrigger": "右扳机",
        "leftstick": "左摇杆按下",
        "rightstick": "右摇杆按下",
        "back": "返回键",
        "start": "菜单键",
        "guide": "主菜单键",
        "touchpad": "触摸板按下",
    },
}
_DIRECTIONS = {"dpup": "↑", "dpright": "→", "dpdown": "↓", "dpleft": "←"}
# SDL's single-Joy-Con mini-gamepad mode rotates controls and exposes rail
# buttons as shoulders. These are semantic labels, never raw index guesses.
_JOYCON_MINI = {
    11: {
        "a": "←",
        "b": "↓",
        "x": "↑",
        "y": "→",
        "start": "−",
        "guide": "截图键",
        "leftshoulder": "SL",
        "rightshoulder": "SR",
        "paddle2": "L",
        "paddle4": "ZL",
    },
    12: {
        "a": "A",
        "b": "X",
        "x": "B",
        "y": "Y",
        "start": "+",
        "leftstick": "右摇杆按下",
        "leftshoulder": "SL",
        "rightshoulder": "SR",
        "paddle1": "R",
        "paddle3": "ZR",
    },
}
_JOYCON_RAILS = {
    "paddle1": "右侧 SR",
    "paddle2": "左侧 SL",
    "paddle3": "右侧 SL",
    "paddle4": "左侧 SR",
}
_RAW = re.compile(r"([+-]?)([ab])(\d+)(~?)$|h(\d+)\.(\d+)$")
_CONTROLS = set().union(*_BUTTONS.values(), _DIRECTIONS) | {
    "leftx",
    "lefty",
    "rightx",
    "righty",
    "paddle1",
    "paddle2",
    "paddle3",
    "paddle4",
    "misc1",
}


def make_profile(
    controller_type: int, mapping: dict[str, str], *, button_labels=True, joycon_vertical=False
) -> dict:
    """Normalize Nintendo's label-based SDL mapping to physical button positions.

    SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS defaults to true. With it enabled,
    Nintendo's SDL `a` is east, unlike Xbox's south. Keep that distinction at the
    device boundary rather than guessing it again in each display style.
    """
    family = (
        "playstation"
        if controller_type in (3, 4, 7)
        else "xbox"
        if controller_type in (1, 2)
        else "switch"
        if controller_type in _SWITCH_TYPES
        else "generic"
    )
    positional = {}
    for control, raw in mapping.items():
        if control.lstrip("+-") not in _CONTROLS or not _RAW.fullmatch(raw):
            continue
        if family == "switch" and button_labels:
            control = {"a": "b", "b": "a", "x": "y", "y": "x"}.get(control, control)
        positional[control] = raw
    profile = {"family": family, "type": controller_type, "mapping": positional}
    if controller_type in (11, 12):
        profile["joycon_vertical"] = joycon_vertical
    return profile


@lru_cache(maxsize=1)
def _sdl():
    # Use pygame's exact SDL instance, not an unrelated system DLL. These SDL2
    # functions use cdecl and return an allocated string, freed by SDL itself.
    if sys.platform != "win32":
        return None
    try:
        import pygame
        from pygame._sdl2 import controller

        controller.init()
        library = ctypes.CDLL(str(Path(pygame.__file__).parent / "SDL2.dll"))
        for name, arguments, result in (
            ("SDL_GameControllerTypeForIndex", [ctypes.c_int], ctypes.c_int),
            ("SDL_GameControllerMappingForDeviceIndex", [ctypes.c_int], ctypes.c_void_p),
            ("SDL_GetHintBoolean", [ctypes.c_char_p, ctypes.c_int], ctypes.c_int),
            ("SDL_free", [ctypes.c_void_p], None),
        ):
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
        return library
    except ImportError, OSError, AttributeError, RuntimeError:
        return None


def read_profile(device_index: int) -> dict | None:
    """Read metadata for the current SDL index without opening a controller."""
    library = _sdl()
    if library is None:
        return None
    pointer = library.SDL_GameControllerMappingForDeviceIndex(device_index)
    if not pointer:
        return None
    try:
        fields = ctypes.string_at(pointer).decode("utf-8", errors="replace").split(",")[2:]
        mapping = dict(field.split(":", 1) for field in fields if ":" in field)
        return make_profile(
            library.SDL_GameControllerTypeForIndex(device_index),
            mapping,
            button_labels=bool(
                library.SDL_GetHintBoolean(b"SDL_GAMECONTROLLER_USE_BUTTON_LABELS", 1)
            ),
            joycon_vertical=bool(
                library.SDL_GetHintBoolean(b"SDL_JOYSTICK_HIDAPI_VERTICAL_JOY_CONS", 0)
            ),
        )
    finally:
        library.SDL_free(pointer)


def _control_label(
    control: str, style: str, controller_type: int, direction=0, joycon_vertical=False
) -> str | None:
    if style == "switch":
        if controller_type in _JOYCON_MINI and not joycon_vertical:
            if control in _JOYCON_MINI[controller_type]:
                return _JOYCON_MINI[controller_type][control]
            if controller_type == 12 and control in ("leftx", "lefty"):
                control = control.replace("left", "right")
        elif controller_type in (11, 12, 13) and control in _JOYCON_RAILS:
            return _JOYCON_RAILS[control]
    if control in _DIRECTIONS:
        return "十字键 " + _DIRECTIONS[control]
    if control in ("leftx", "lefty", "rightx", "righty") and direction:
        stick = "左摇杆 " if control.startswith("left") else "右摇杆 "
        arrows = ("←", "→") if control.endswith("x") else ("↑", "↓")
        return stick + arrows[direction > 0]
    if control.startswith("paddle"):
        return "背键 " + control[-1]
    if style == "playstation":
        if control == "back":
            return {3: "SELECT", 4: "SHARE", 7: "Create"}.get(controller_type, "SHARE / Create")
        if control == "start" and controller_type == 3:
            return "START"
    if style == "xbox" and controller_type == 1:
        if control in ("back", "start"):
            return {"back": "Back", "start": "Start"}[control]
    return _BUTTONS[style].get(control) or _BUTTONS["generic"].get(control)


def _mapped_labels(profile: dict, style: str, *, button=None, axis=None) -> list[str]:
    labels = []
    for output, raw in profile.get("mapping", {}).items():
        if not isinstance(output, str):
            continue
        match = _RAW.fullmatch(raw) if isinstance(raw, str) else None
        if not match:
            continue
        sign, kind, index, inverted, hat, mask = match.groups()
        control = output.lstrip("+-")
        direction = -1 if output.startswith("-") else 1 if output.startswith("+") else 0
        if button is not None:
            if kind == "b" and int(index) == button:
                pass
            elif hat is not None and button >= 1000:
                hat_index, hat_direction = divmod(button - 1000, 4)
                if int(hat) != hat_index or int(mask) != 1 << hat_direction:
                    continue
            else:
                continue
            direction = direction or 1
        elif axis is not None and kind == "a" and int(index) == axis["index"]:
            raw_direction = axis["direction"]
            # Half axes can share one raw axis (e.g. left/right trigger).
            press_direction = (-1 if sign == "-" else 1) * (-1 if inverted else 1)
            if control not in ("leftx", "lefty", "rightx", "righty"):
                if raw_direction != press_direction:
                    continue
            else:
                if (sign or direction) and raw_direction != press_direction:
                    continue
                direction = direction or raw_direction * press_direction
        else:
            continue
        controller_type = profile.get("type", 0)
        label = _control_label(
            control,
            style,
            controller_type if type(controller_type) is int else 0,
            direction,
            profile.get("joycon_vertical", False),
        )
        if label and label not in labels:
            labels.append(label)
    return labels


def binding_labels(binding: dict, devices: Iterable[Any] = ()) -> list[str]:
    """Format recorded raw inputs; connected matching devices override saved metadata.

    If a legacy binding targets any device and attached mappings disagree, do
    not borrow a random device's names. Raw names remain an honest fallback.
    """
    candidates = [
        device.profile
        for device in devices
        if (not binding.get("guid") or binding["guid"] == device.guid)
        and (not binding.get("instance_id") or binding["instance_id"] == device.instance_id)
    ]
    profile = binding.get("profile") or {}
    if candidates:
        profile = candidates[0] if all(p == candidates[0] for p in candidates) else {}
    if not isinstance(profile, dict) or not isinstance(profile.get("mapping", {}), dict):
        profile = {}
    style = binding.get("label_style", "auto")
    if style not in LABEL_STYLES or style == "auto":
        style = profile.get("family", "generic")
    if not isinstance(style, str) or style not in _BUTTONS:
        style = "generic"
    labels = []
    for button in binding.get("buttons", []):
        mapped = _mapped_labels(profile, style, button=button)
        fallback = (
            "十字键 " + ("↑", "→", "↓", "←")[(button - 1000) % 4]
            if button >= 1000
            else "按钮 " + str(button + 1)
        )
        labels.append(" / ".join(mapped) if mapped else fallback)
    for axis in binding.get("axes", []):
        mapped = _mapped_labels(profile, style, axis=axis)
        fallback = "轴 " + str(axis["index"] + 1) + (" 正向" if axis["direction"] > 0 else " 反向")
        labels.append(" / ".join(mapped) if mapped else fallback)
    return list(dict.fromkeys(labels))
