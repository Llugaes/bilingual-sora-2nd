"""Non-invasive hotkey polling for the subtitle overlay.

Keyboard polling reads the Windows async key state and is deliberately gated by
the caller's foreground-game check.  Controllers are read through SDL/pygame,
which sees the devices exposed by the OS (including many DirectInput devices).
Steam Input may expose a virtual controller instead; applications cannot
reliably enumerate devices that Steam or the operating system hides.
"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
import sys
import time
from typing import Any, Callable, Iterable

# SDL normally ignores controller changes while a different application owns
# focus. This only requests ordinary background joystick events; it neither
# installs a hook nor changes Steam Input/OS device configuration.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

try:
    import pygame
except ImportError:  # Allows configuration/UI tests before optional install.
    pygame = None


KEY_TO_VK = {
    "CTRL": 0x11,
    "LCTRL": 0xA2,
    "RCTRL": 0xA3,
    "SHIFT": 0x10,
    "LSHIFT": 0xA0,
    "RSHIFT": 0xA1,
    "ALT": 0x12,
    "LALT": 0xA4,
    "RALT": 0xA5,
    "WIN": 0x5B,
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "BACKSPACE": 0x08,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}
KEY_TO_VK.update({chr(code): code for code in range(ord("A"), ord("Z") + 1)})
KEY_TO_VK.update({chr(code): code for code in range(ord("0"), ord("9") + 1)})
KEY_TO_VK.update({f"F{index}": 0x6F + index for index in range(1, 25)})


def vk_for_key(key: str) -> int | None:
    """Translate the portable hotkey spelling used in config to a Win32 VK."""
    return KEY_TO_VK.get(str(key).strip().upper())


def _windows_key_down(vk: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


@dataclass(frozen=True)
class GamepadState:
    """A button snapshot. instance_id identifies one physical SDL device."""

    instance_id: str
    guid: str
    name: str
    buttons: frozenset[int]
    axes: tuple[float, ...] = ()


@dataclass(frozen=True)
class HotkeyState:
    """Effective configured-combination state for one input polling tick.

    ``held`` is deliberately false while focus is regained with the binding
    already physically held.  Consumers can therefore implement hold-to-show
    without an accidental secondary-language flash.  ``pressed`` is a rising
    edge from any valid keyboard or one-device gamepad combination; ``released``
    reports the effective combination becoming inactive, including focus loss.
    """

    active: bool
    held: bool
    pressed: bool
    released: bool
    sources: frozenset[str]


class InputManager:
    """Poll configured keyboard or *one* controller button combination.

    ``poll(active)`` returns True once when a configured combination rises.  An
    inactive game window suppresses input; held controls must be released after
    focus returns before they can trigger.  This class never consumes keys,
    changes Steam settings, or installs global hooks.

    Controller capture is explicit: call ``begin_controller_capture()``, then
    call ``poll_capture()`` from the main timer.  It returns a config-ready
    ``{"gamepad": {"guid": ..., "buttons": [...]}}`` when buttons are held.
    The first device with a non-empty held set wins; all captured buttons belong
    to that one device.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        key_state: Callable[[int], bool] | None = None,
        joystick_provider: Callable[[], Iterable[GamepadState | dict[str, Any]]] | None = None,
    ) -> None:
        self.config = config or {}
        self._key_state = key_state or _windows_key_down
        self._joystick_provider = joystick_provider
        # SDL indices are unstable after hot-unplug. Cache only by the SDL
        # instance id and rebuild the index->device view on every poll.
        self._joysticks: dict[str, Any] = {}
        self._keyboard_latched = True
        self._gamepad_latched: set[str] = set()
        self._keyboard_accepted = False
        self._gamepad_accepted: set[str] = set()
        self._effective_held = False
        self._was_active = False
        self._capturing_controller = False
        self._capture_device: GamepadState | None = None
        self._capture_buttons: set[int] = set()
        self._capture_axes: dict[int, dict] = {}
        self._capture_neutral: dict[str, tuple[float, ...]] = {}
        self._capture_deadline = 0.0
        self.capture_status = "idle"

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._keyboard_latched = True
        self._gamepad_latched.clear()
        self._keyboard_accepted = False
        self._gamepad_accepted.clear()
        self._effective_held = False
        self._was_active = False

    def binding(self) -> dict[str, Any]:
        binding = self.config.get("hotkey", self.config.get("toggle_binding", {}))
        return binding if isinstance(binding, dict) else {}

    def _keyboard_keys(self) -> list[str]:
        binding = self.binding()
        keys = binding.get("keyboard", [])
        if isinstance(keys, str):
            keys = [part.strip() for part in keys.split("+")]
        if not isinstance(keys, (list, tuple)):
            return []
        result = [str(key).upper() for key in keys]
        return result if result and all(vk_for_key(key) is not None for key in result) else []

    def _keyboard_pressed(self) -> bool:
        keys = self._keyboard_keys()
        return bool(keys) and all(self._key_state(vk_for_key(key)) for key in keys)

    def _refresh_joysticks(self) -> None:
        if pygame is None:
            return
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            # pygame's SDL event queue is what updates joystick button state.
            # display.init starts the event/video subsystem but does not create
            # a window; in particular, no display.set_mode call is made here.
            if not pygame.display.get_init():
                pygame.display.init()
            pygame.event.pump()

            current: dict[str, Any] = {}
            for index in range(pygame.joystick.get_count()):
                stick = pygame.joystick.Joystick(index)
                stick.init()
                current[str(stick.get_instance_id())] = stick
            # Replacing rather than index-muting makes A-unplug/B-reindex work
            # and drops stale disconnected devices immediately.
            self._joysticks = current
        except pygame.error:
            self._joysticks.clear()

    def devices(self) -> list[GamepadState]:
        if self._joystick_provider is not None:
            return [self._as_state(item) for item in self._joystick_provider()]
        self._refresh_joysticks()
        states: list[GamepadState] = []
        for stick in self._joysticks.values():
            try:
                buttons = {i for i in range(stick.get_numbuttons()) if stick.get_button(i)}
                # Raw DirectInput D-pads may be hats rather than buttons.
                for hat in range(stick.get_numhats()):
                    x, y = stick.get_hat(hat)
                    for direction, pressed in enumerate((y > 0, x > 0, y < 0, x < 0)):
                        if pressed:
                            buttons.add(1000 + hat * 4 + direction)
                states.append(
                    GamepadState(
                        instance_id=str(stick.get_instance_id()),
                        guid=str(stick.get_guid()),
                        name=str(stick.get_name()),
                        buttons=frozenset(buttons),
                        axes=tuple(stick.get_axis(i) for i in range(stick.get_numaxes())),
                    )
                )
            except pygame.error:
                continue
        return states

    @staticmethod
    def _as_state(item: GamepadState | dict[str, Any]) -> GamepadState:
        if isinstance(item, GamepadState):
            return item
        return GamepadState(
            instance_id=str(item.get("instance_id", item.get("id", ""))),
            guid=str(item.get("guid", "")),
            name=str(item.get("name", "Unknown controller")),
            buttons=frozenset(int(button) for button in item.get("buttons", [])),
            axes=tuple(float(value) for value in item.get("axes", [])),
        )

    def device_status(self) -> list[str]:
        return [f"{device.name} ({device.guid or device.instance_id})" for device in self.devices()]

    def _matching_gamepads(self) -> list[GamepadState]:
        gamepad = self.binding().get("gamepad")
        if not isinstance(gamepad, dict):
            return []
        buttons = frozenset(int(button) for button in gamepad.get("buttons", []))
        axes = gamepad.get("axes", [])
        if not buttons and not axes:
            return []
        target_id = str(gamepad.get("instance_id", ""))
        target_guid = str(gamepad.get("guid", ""))
        return [
            device
            for device in self.devices()
            if buttons.issubset(device.buttons)
            and all(
                0 <= a["index"] < len(device.axes)
                and (device.axes[a["index"]] - a["threshold"]) * a["direction"] > 0
                for a in axes
            )
            and (not target_id or device.instance_id == target_id)
            and (not target_guid or device.guid == target_guid)
        ]

    def poll_state(self, active: bool) -> HotkeyState:
        """Poll the binding and return its effective held/edge state.

        This is the API for a native-rendering harness that needs both a press
        edge (language toggle) and the currently effective hold (temporary
        secondary language).  ``poll(active)`` remains the compatible
        press-only toggle adapter.
        """
        keyboard_pressed = self._keyboard_pressed()
        matching_gamepads = self._matching_gamepads()
        matching_ids = {device.instance_id for device in matching_gamepads}
        if not active:
            released = self._effective_held
            self._was_active = False
            # A focus transition releases policy state immediately, but keeps
            # physically held inputs latched so focus regain cannot synthesize
            # a new press or a hold-to-secondary transition.
            self._keyboard_latched = keyboard_pressed
            self._gamepad_latched = set(matching_ids)
            self._keyboard_accepted = False
            self._gamepad_accepted.clear()
            self._effective_held = False
            return HotkeyState(False, False, False, released, frozenset())

        if not self._was_active:
            # Focus may have returned while a combination is still held.
            self._keyboard_latched = keyboard_pressed
            self._gamepad_latched = set(matching_ids)
            self._keyboard_accepted = False
            self._gamepad_accepted.clear()
            self._effective_held = False
            self._was_active = True
            return HotkeyState(True, False, False, False, frozenset())

        pressed = False
        if keyboard_pressed:
            if not self._keyboard_latched:
                pressed = True
                self._keyboard_accepted = True
            self._keyboard_latched = True
        else:
            self._keyboard_latched = False
            self._keyboard_accepted = False

        self._gamepad_latched.intersection_update(matching_ids)
        self._gamepad_accepted.intersection_update(matching_ids)
        for device in matching_gamepads:
            if device.instance_id not in self._gamepad_latched:
                pressed = True
                self._gamepad_latched.add(device.instance_id)
                self._gamepad_accepted.add(device.instance_id)
        held = self._keyboard_accepted or bool(self._gamepad_accepted)
        released = self._effective_held and not held
        self._effective_held = held
        sources = set(self._gamepad_accepted)
        if self._keyboard_accepted:
            sources.add("keyboard")
        return HotkeyState(True, held, pressed, released, frozenset(sources))

    def state(self, active: bool) -> HotkeyState:
        """Alias for ``poll_state`` for timer-driven native harnesses."""
        return self.poll_state(active)

    def poll(self, active: bool) -> bool:
        """Return a single toggle event, without stealing any input."""
        return self.poll_state(active).pressed

    def begin_controller_capture(self, timeout_seconds: float = 10.0) -> None:
        self._capturing_controller = True
        self._capture_device = None
        self._capture_buttons.clear()
        self._capture_axes.clear()
        self._capture_neutral = {d.instance_id: d.axes for d in self.devices()}
        self._capture_deadline = time.monotonic() + max(timeout_seconds, 1.0)
        self.capture_status = "recording"

    def cancel_capture(self) -> None:
        self._capturing_controller = False
        self.capture_status = "cancelled"

    def poll_capture(self) -> dict[str, Any] | None:
        if not self._capturing_controller:
            return None
        if time.monotonic() >= self._capture_deadline:
            self._capturing_controller = False
            self.capture_status = "timed_out"
            return None
        for device in self.devices():
            neutral = self._capture_neutral.setdefault(device.instance_id, device.axes)
            excursions = {
                i: {"index": i, "direction": 1 if v > n else -1, "threshold": (v + n) / 2}
                for i, (v, n) in enumerate(zip(device.axes, neutral))
                if abs(v - n) > 0.7
            }
            if self._capture_device is None and (device.buttons or excursions):
                self._capture_device = device
                self._capture_buttons.update(device.buttons)
                self._capture_axes.update(excursions)
                self.capture_status = "release_to_save"
                return None
            if self._capture_device and device.instance_id == self._capture_device.instance_id:
                still_axes = any(
                    a["index"] < len(device.axes)
                    and (device.axes[a["index"]] - a["threshold"]) * a["direction"] > 0
                    for a in self._capture_axes.values()
                )
                if device.buttons or excursions or still_axes:
                    self._capture_buttons.update(device.buttons)
                    for i, a in excursions.items():
                        self._capture_axes.setdefault(i, a)
                    return None
                self._capturing_controller = False
                self.capture_status = "complete"
                binding = {
                    "guid": self._capture_device.guid,
                    "buttons": sorted(self._capture_buttons),
                }
                if self._capture_axes:
                    binding["axes"] = list(self._capture_axes.values())
                return {"gamepad": binding}
        return None
