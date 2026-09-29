import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from sora_bilingual.platform.gamepad_labels import binding_labels, make_profile, read_profile
from sora_bilingual.platform.inputs import GamepadState, InputManager


# Actual SDL 2.32.10 mapping read from the attached DualSense, not a guessed
# DirectInput button order. Tests below also use intentionally different orders.
DUALSENSE = {
    "a": "b0",
    "b": "b1",
    "x": "b2",
    "y": "b3",
    "back": "b4",
    "guide": "b5",
    "start": "b6",
    "leftstick": "b7",
    "rightstick": "b8",
    "leftshoulder": "b9",
    "rightshoulder": "b10",
    "dpup": "b11",
    "dpdown": "b12",
    "dpleft": "b13",
    "dpright": "b14",
    "touchpad": "b15",
    "misc1": "b16",
    "leftx": "a0",
    "lefty": "a1",
    "rightx": "a2",
    "righty": "a3",
    "lefttrigger": "a4",
    "righttrigger": "a5",
}


def axis(index, direction=1):
    return {"index": index, "direction": direction, "threshold": 0}


class GamepadLabelTests(unittest.TestCase):
    def test_dualsense_complete_binding_labels(self):
        pad = {"profile": make_profile(7, DUALSENSE), "buttons": list(range(17))}
        self.assertEqual(
            binding_labels(pad),
            [
                "×",
                "○",
                "□",
                "△",
                "Create",
                "PS",
                "OPTIONS",
                "L3",
                "R3",
                "L1",
                "R1",
                "十字键 ↑",
                "十字键 ↓",
                "十字键 ←",
                "十字键 →",
                "触摸板按下",
                "麦克风键",
            ],
        )
        pad = {"profile": make_profile(7, DUALSENSE), "axes": [axis(4), axis(5)]}
        self.assertEqual(binding_labels(pad), ["L2", "R2"])

    def test_stick_movements_are_not_stick_clicks(self):
        pad = {
            "profile": make_profile(2, DUALSENSE),
            "buttons": [7, 8],
            "axes": [axis(i, d) for i in range(4) for d in (-1, 1)],
        }
        self.assertEqual(
            binding_labels(pad),
            [
                "LS（按下）",
                "RS（按下）",
                "左摇杆 ←",
                "左摇杆 →",
                "左摇杆 ↑",
                "左摇杆 ↓",
                "右摇杆 ←",
                "右摇杆 →",
                "右摇杆 ↑",
                "右摇杆 ↓",
            ],
        )

    def test_device_specific_axis_button_and_hat_mapping(self):
        profile = make_profile(
            4,
            {
                "leftshoulder": "b12",
                "rightshoulder": "b6",
                "lefttrigger": "b8",
                "righttrigger": "a1~",
                "dpup": "h1.1",
                "dpright": "h1.2",
                "dpdown": "h1.4",
                "dpleft": "h1.8",
                "lefty": "a7~",
            },
        )
        self.assertEqual(
            binding_labels(
                {
                    "profile": profile,
                    "buttons": [12, 6, 8, 1004, 1005, 1006, 1007],
                    "axes": [axis(1, -1), axis(7, -1)],
                }
            ),
            ["L1", "R1", "L2", "十字键 ↑", "十字键 →", "十字键 ↓", "十字键 ←", "R2", "左摇杆 ↓"],
        )

    def test_shared_axis_triggers_and_inverted_half_axes(self):
        profile = make_profile(1, {"lefttrigger": "-a2", "righttrigger": "+a2"})
        for direction, label in ((-1, "LT"), (1, "RT")):
            self.assertEqual(
                binding_labels({"profile": profile, "axes": [axis(2, direction)]}), [label]
            )
        profile = make_profile(7, {"lefttrigger": "-a2~"})
        self.assertEqual(binding_labels({"profile": profile, "axes": [axis(2)]}), ["L2"])
        self.assertEqual(binding_labels({"profile": profile, "axes": [axis(2, -1)]}), ["轴 3 反向"])

    def test_digital_controls_mapped_to_axes_and_axes_mapped_to_buttons(self):
        profile = make_profile(
            2, {"dpup": "-a6", "dpdown": "+a6", "-leftx": "b17", "+leftx": "b18"}
        )
        self.assertEqual(
            binding_labels(
                {
                    "profile": profile,
                    "buttons": [17, 18],
                    "axes": [axis(6, -1), axis(6)],
                }
            ),
            ["左摇杆 ←", "左摇杆 →", "十字键 ↑", "十字键 ↓"],
        )

    def test_nintendo_labels_and_positional_hint_have_same_visible_result(self):
        # Physical south/east/west/north are raw buttons 0/1/2/3 in this fixture.
        for controller_type in (5, 13):
            for button_labels, face in (
                (True, {"a": "b1", "b": "b0", "x": "b3", "y": "b2"}),
                (False, {"a": "b0", "b": "b1", "x": "b2", "y": "b3"}),
            ):
                with self.subTest(type=controller_type, hint=button_labels):
                    mapping = {**DUALSENSE, **face}
                    pad = {
                        "profile": make_profile(
                            controller_type, mapping, button_labels=button_labels
                        ),
                        "buttons": [0, 1, 2, 3, 7, 8, 9, 10],
                        "axes": [axis(4), axis(5)],
                    }
                    self.assertEqual(
                        binding_labels(pad),
                        ["B", "A", "Y", "X", "左摇杆按下", "右摇杆按下", "L", "R", "ZL", "ZR"],
                    )

    def test_signed_stick_output_keeps_its_direction_with_inverted_input(self):
        profile = make_profile(2, {"-leftx": "+a0~", "+leftx": "-a1~", "righty": "b21"})
        self.assertEqual(
            binding_labels({"profile": profile, "axes": [axis(0, -1), axis(1)], "buttons": [21]}),
            ["右摇杆 ↓", "左摇杆 ←", "左摇杆 →"],
        )

    def test_manual_style_changes_only_names_and_works_with_virtual_xbox(self):
        pad = {
            "guid": "virtual",
            "profile": make_profile(2, DUALSENSE),
            "buttons": [0, 1, 2, 3, 7, 8, 9, 10],
            "axes": [axis(4), axis(5)],
        }
        before = json.dumps(pad, sort_keys=True)
        self.assertEqual(
            binding_labels({**pad, "label_style": "playstation"}),
            ["×", "○", "□", "△", "L3", "R3", "L1", "R1", "L2", "R2"],
        )
        self.assertEqual(
            binding_labels({**pad, "label_style": "switch"}),
            ["B", "A", "Y", "X", "左摇杆按下", "右摇杆按下", "L", "R", "ZL", "ZR"],
        )
        self.assertEqual(json.dumps(pad, sort_keys=True), before)

    def test_single_joycons_use_physical_face_and_rail_names(self):
        mapping = {
            **{key: value for key, value in DUALSENSE.items() if key not in ("touchpad", "misc1")},
            "misc1": "b15",
            "paddle1": "b16",
            "paddle2": "b17",
            "paddle3": "b18",
            "paddle4": "b19",
        }
        left = make_profile(11, mapping)
        self.assertEqual(
            binding_labels({"profile": left, "buttons": [0, 1, 2, 3, 9, 10, 17, 19, 6, 5]}),
            ["↓", "←", "→", "↑", "SL", "SR", "L", "ZL", "−", "截图键"],
        )
        right = make_profile(12, mapping)
        self.assertEqual(
            binding_labels(
                {"profile": right, "buttons": [0, 1, 2, 3, 9, 10, 16, 18, 7], "axes": [axis(0)]}
            ),
            ["X", "A", "Y", "B", "SL", "SR", "R", "ZR", "右摇杆按下", "右摇杆 →"],
        )
        vertical = make_profile(12, mapping, joycon_vertical=True)
        self.assertEqual(
            binding_labels({"profile": vertical, "buttons": [0, 1, 2, 3, 10, 16, 18, 8]}),
            ["A", "B", "X", "Y", "R", "右侧 SR", "右侧 SL", "右摇杆按下"],
        )
        pair = make_profile(13, mapping)
        self.assertEqual(
            binding_labels({"profile": pair, "buttons": [16, 17, 18, 19]}),
            ["右侧 SR", "左侧 SL", "右侧 SL", "左侧 SR"],
        )

    def test_duplicate_reports_deduplicate_and_unknown_inputs_stay_visible(self):
        profile = make_profile(
            7, {"lefttrigger": "a4", "righttrigger": "b19", "rightshoulder": "b19"}
        )
        self.assertEqual(
            binding_labels(
                {"profile": profile, "buttons": [19, 32, 1000], "axes": [axis(4), axis(4), axis(8)]}
            ),
            ["R2 / R1", "按钮 33", "十字键 ↑", "L2", "轴 9 正向"],
        )
        generic = make_profile(0, {"a": "b17", "paddle2": "b20"})
        self.assertEqual(
            binding_labels({"profile": generic, "buttons": [17, 20]}), ["下方面键", "背键 2"]
        )

    def test_old_bindings_use_matching_live_device_not_first_attached_device(self):
        ps = GamepadState("ps", "ps-guid", "PS", frozenset(), profile=make_profile(7, DUALSENSE))
        xbox = GamepadState("xb", "xb-guid", "XB", frozenset(), profile=make_profile(2, DUALSENSE))
        self.assertEqual(binding_labels({"guid": "ps-guid", "buttons": [10]}, [xbox, ps]), ["R1"])
        self.assertEqual(binding_labels({"instance_id": "xb", "buttons": [10]}, [ps, xbox]), ["RB"])
        self.assertEqual(binding_labels({"buttons": [10]}, [ps, xbox]), ["按钮 11"])

    def test_saved_profile_works_offline_and_live_mapping_wins(self):
        pad = {"guid": "pad", "buttons": [0], "profile": make_profile(7, {"a": "b0"})}
        self.assertEqual(binding_labels(json.loads(json.dumps(pad))), ["×"])
        connected = GamepadState(
            "1", "pad", "PS", frozenset(), profile=make_profile(7, {"b": "b0"})
        )
        self.assertEqual(binding_labels(pad, [connected]), ["○"])
        for invalid in (None, [], {"mapping": []}, {"family": []}):
            self.assertEqual(binding_labels({"buttons": [0], "profile": invalid}), ["按钮 1"])

    def test_capture_persists_mapping_but_matching_uses_only_raw_inputs(self):
        profile = make_profile(7, {"leftshoulder": "b9", "lefttrigger": "a0"})
        devices = [GamepadState("1", "pad", "PS", frozenset(), (-1.0,), profile)]
        manager = InputManager(joystick_provider=lambda: devices)
        manager.begin_controller_capture()
        devices[0] = GamepadState("1", "pad", "PS", frozenset({9}), (1.0,), profile)
        self.assertIsNone(manager.poll_capture())
        devices[0] = GamepadState("1", "pad", "PS", frozenset(), (-1.0,), profile)
        captured = json.loads(json.dumps(manager.poll_capture()))
        self.assertEqual(binding_labels(captured["gamepad"]), ["L1", "L2"])
        captured["gamepad"]["label_style"] = "switch"
        manager.update_config({"hotkey": captured})
        self.assertFalse(manager.poll_state(True).held)
        devices[0] = GamepadState("1", "pad", "PS", frozenset({9}), (1.0,), profile)
        self.assertTrue(manager.poll_state(True).pressed)
        self.assertEqual(binding_labels(captured["gamepad"]), ["L", "ZL"])

    def test_metadata_is_read_once_per_connection_and_not_in_backend(self):
        stick = MagicMock()
        stick.get_instance_id.return_value = 42
        fake_pygame = SimpleNamespace(
            error=RuntimeError,
            joystick=MagicMock(),
            display=MagicMock(),
            event=MagicMock(),
        )
        fake_pygame.joystick.get_count.return_value = 1
        fake_pygame.joystick.Joystick.return_value = stick
        with (
            patch("sora_bilingual.platform.inputs.pygame", fake_pygame),
            patch("sora_bilingual.platform.inputs.read_profile", return_value={}) as reader,
        ):
            backend = InputManager()
            backend._refresh_joysticks()
            reader.assert_not_called()
            ui = InputManager(describe_devices=True)
            for _ in range(20):
                ui._refresh_joysticks()
            reader.assert_called_once_with(0)
            fake_pygame.joystick.get_count.return_value = 0
            ui._refresh_joysticks()
            self.assertEqual(ui._profiles, {})
            fake_pygame.joystick.get_count.return_value = 1
            stick.get_instance_id.return_value = 43
            ui._refresh_joysticks()
            self.assertEqual(reader.call_count, 2)

    def test_native_metadata_reader_copies_and_frees_sdl_owned_string(self):
        import ctypes

        buffer = ctypes.create_string_buffer(
            b"guid,name,lefttrigger:a4,righttrigger:a5,platform:Windows,"
        )
        library = MagicMock()
        library.SDL_GameControllerMappingForDeviceIndex.return_value = ctypes.addressof(buffer)
        library.SDL_GameControllerTypeForIndex.return_value = 7
        with patch("sora_bilingual.platform.gamepad_labels._sdl", return_value=library):
            profile = read_profile(3)
        self.assertEqual(
            binding_labels({"profile": profile, "axes": [axis(4), axis(5)]}), ["L2", "R2"]
        )
        library.SDL_free.assert_called_once_with(ctypes.addressof(buffer))
        library.SDL_GameControllerMappingForDeviceIndex.assert_called_once_with(3)

    def test_label_metadata_does_not_bypass_binding_conflict_validation(self):
        from sora_bilingual.config.native_config import normalize_config

        for field in ("switch_binding", "overlay_binding"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "无效手柄按键样式"):
                normalize_config({field: {"gamepad": {"buttons": [1], "label_style": "invalid"}}})
        with self.assertRaisesRegex(ValueError, "不同的手柄组合"):
            normalize_config(
                {
                    "switch_binding": {"gamepad": {"buttons": [1], "label_style": "playstation"}},
                    "overlay_binding": {"gamepad": {"buttons": [1], "label_style": "xbox"}},
                }
            )
