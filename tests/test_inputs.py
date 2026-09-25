import unittest

from sora_bilingual.platform.inputs import GamepadState, HotkeyState, InputManager


class InputTests(unittest.TestCase):
    def test_trigger_axis_capture_and_release(self):
        devices = [GamepadState("one", "pad", "Pad", frozenset(), (-1.0,))]
        m = InputManager({}, joystick_provider=lambda: devices)
        m.begin_controller_capture()
        devices[0] = GamepadState("one", "pad", "Pad", frozenset({4}), (1.0,))
        self.assertIsNone(m.poll_capture())
        devices[0] = GamepadState("one", "pad", "Pad", frozenset(), (-1.0,))
        binding = m.poll_capture()
        self.assertEqual(binding["gamepad"]["axes"][0]["threshold"], 0)
        m.update_config({"hotkey": binding})
        m.poll_state(True)
        devices[0] = GamepadState("one", "pad", "Pad", frozenset({4}), (1.0,))
        self.assertTrue(m.poll_state(True).held)
        devices[0] = GamepadState("one", "pad", "Pad", frozenset({4}), (-1.0,))
        self.assertTrue(m.poll_state(True).released)

    def test_keyboard_long_press_only_toggles_once(self):
        held = set()
        manager = InputManager(
            {"hotkey": {"keyboard": ["CTRL", "F8"]}}, key_state=lambda vk: vk in held
        )
        self.assertFalse(manager.poll(True))  # foreground transition is armed safely
        held.update({0x11, 0x77})
        self.assertTrue(manager.poll(True))
        self.assertFalse(manager.poll(True))
        held.clear()
        self.assertFalse(manager.poll(True))
        held.update({0x11, 0x77})
        self.assertTrue(manager.poll(True))

    def test_controller_buttons_cannot_be_combined_across_devices(self):
        devices = [
            GamepadState("one", "guid-one", "Pad one", frozenset({1})),
            GamepadState("two", "guid-two", "Pad two", frozenset({2})),
        ]
        manager = InputManager(
            {"hotkey": {"gamepad": {"buttons": [1, 2]}}}, joystick_provider=lambda: devices
        )
        self.assertFalse(manager.poll(True))
        self.assertFalse(manager.poll(True))
        devices[0] = GamepadState("one", "guid-one", "Pad one", frozenset({1, 2}))
        self.assertTrue(manager.poll(True))
        self.assertFalse(manager.poll(True))

    def test_focus_return_while_held_is_suppressed_until_release(self):
        held = {0x77}
        manager = InputManager({"hotkey": {"keyboard": ["F8"]}}, key_state=lambda vk: vk in held)
        self.assertFalse(manager.poll(False))
        self.assertFalse(manager.poll(True))
        self.assertFalse(manager.poll(True))
        held.clear()
        self.assertFalse(manager.poll(True))
        held.add(0x77)
        self.assertTrue(manager.poll(True))

    def test_state_exposes_effective_hold_press_and_release_edges(self):
        held = set()
        manager = InputManager({"hotkey": {"keyboard": ["F8"]}}, key_state=lambda vk: vk in held)
        self.assertEqual(
            manager.poll_state(True), HotkeyState(True, False, False, False, frozenset())
        )
        held.add(0x77)
        self.assertEqual(
            manager.poll_state(True),
            HotkeyState(True, True, True, False, frozenset({"keyboard"})),
        )
        self.assertEqual(
            manager.state(True),
            HotkeyState(True, True, False, False, frozenset({"keyboard"})),
        )
        held.clear()
        self.assertEqual(
            manager.poll_state(True), HotkeyState(True, False, False, True, frozenset())
        )

    def test_focus_loss_releases_hold_and_focus_regain_held_is_not_a_press(self):
        held = set()
        manager = InputManager({"hotkey": {"keyboard": ["F8"]}}, key_state=lambda vk: vk in held)
        manager.poll_state(True)
        held.add(0x77)
        self.assertTrue(manager.poll_state(True).held)
        self.assertEqual(
            manager.poll_state(False), HotkeyState(False, False, False, True, frozenset())
        )
        # Physical state is still held, but its pre-focus binding remains
        # suppressed until release and a new press.
        self.assertEqual(
            manager.poll_state(True), HotkeyState(True, False, False, False, frozenset())
        )
        self.assertFalse(manager.poll_state(True).held)
        held.clear()
        self.assertFalse(manager.poll_state(True).held)
        held.add(0x77)
        self.assertEqual(
            manager.poll_state(True),
            HotkeyState(True, True, True, False, frozenset({"keyboard"})),
        )

    def test_gamepad_state_requires_one_device_and_releases_when_its_combo_breaks(self):
        devices = [GamepadState("one", "guid-one", "Pad", frozenset())]
        manager = InputManager(
            {"hotkey": {"gamepad": {"guid": "guid-one", "buttons": [1, 2]}}},
            joystick_provider=lambda: devices,
        )
        manager.poll_state(True)
        devices[0] = GamepadState("one", "guid-one", "Pad", frozenset({1, 2}))
        state = manager.poll_state(True)
        self.assertEqual(state, HotkeyState(True, True, True, False, frozenset({"one"})))
        devices[0] = GamepadState("one", "guid-one", "Pad", frozenset({1}))
        self.assertEqual(
            manager.poll_state(True), HotkeyState(True, False, False, True, frozenset())
        )

    def test_unknown_key_never_degrades_to_a_modifier_hotkey(self):
        held = {0x11}
        manager = InputManager(
            {"hotkey": {"keyboard": ["CTRL", "NOT_A_KEY"]}}, key_state=lambda vk: vk in held
        )
        self.assertFalse(manager.poll(True))
        self.assertFalse(manager.poll(True))

    def test_controller_capture_keeps_one_device_buttons_together(self):
        devices = [GamepadState("one", "guid-one", "Pad", frozenset({3}))]
        manager = InputManager({}, joystick_provider=lambda: devices)
        manager.begin_controller_capture()
        self.assertIsNone(manager.poll_capture())
        devices[0] = GamepadState("one", "guid-one", "Pad", frozenset({3, 4}))
        self.assertIsNone(manager.poll_capture())
        devices[0] = GamepadState("one", "guid-one", "Pad", frozenset())
        self.assertEqual(
            manager.poll_capture(), {"gamepad": {"guid": "guid-one", "buttons": [3, 4]}}
        )
