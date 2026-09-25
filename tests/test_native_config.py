import tempfile
import threading
import unittest
import os
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from sora_bilingual.config.native_config import (
    ActionPolicy,
    BackendLock,
    read_config,
    write_config,
    normalize_config,
)
from sora_bilingual.game.native_runtime import NativeLabels
from sora_bilingual.game.native_probe import write_telemetry


class NativeConfigTests(unittest.TestCase):
    def test_language_defaults_follow_source_and_explicit_pairs_are_preserved(self):
        from sora_bilingual.config.locales import LOCALES

        for source in LOCALES:
            with self.subTest(source=source):
                config = normalize_config({"game_language": source})
                self.assertEqual(config["primary"], source)
                self.assertEqual(config["secondary"], "en" if source == "ja" else "ja")
                for primary in LOCALES:
                    for secondary in LOCALES:
                        chosen = dict(game_language=source, primary=primary, secondary=secondary)
                        result = normalize_config(chosen)
                        self.assertEqual({k: result[k] for k in chosen}, chosen)

    def test_invalid_source_is_rejected_before_deriving_defaults(self):
        for source in (None, [], "unknown"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize_config({"game_language": source})

    def test_malformed_config_is_rejected_as_recoverable_validation_error(self):
        cases = [
            {"primary": []},
            {"hotkeys": None},
            {"interaction": {}},
            {"enabled": "false"},
            {"scope": []},
            {"sources": None},
            {"annotation_scale": True},
            {"overlay_binding": {"keyboard": None}},
            {"overlay_binding": {"keyboard": ["UNKNOWN_KEY"]}},
            {"overlay_binding": {"gamepad": {"buttons": [[]]}}},
            {"overlay_binding": {"gamepad": {"axes": [None]}}},
            {
                "overlay_binding": {
                    "gamepad": {"axes": [{"index": 0, "direction": 1, "threshold": float("nan")}]}
                }
            },
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_config(value)

    def test_selected_mode_defines_press_hold_and_release(self):
        up = SimpleNamespace(pressed=False, held=False)
        down = SimpleNamespace(pressed=True, held=True)
        held = SimpleNamespace(pressed=False, held=True)
        for mode, expected in (
            ("language_hold", "secondary"),
            ("language_toggle", "secondary"),
            ("annotation", "primary"),
        ):
            policy = ActionPolicy(mode)
            self.assertEqual(policy.advance(down), expected)
            for _ in range(20):
                self.assertEqual(policy.advance(held), expected)
            self.assertEqual(policy.advance(up), "primary" if mode == "language_hold" else expected)
            self.assertEqual(policy.interaction, mode)
            if mode != "language_hold":
                self.assertEqual(
                    policy.advance(down), "annotation" if mode == "annotation" else "primary"
                )

    def test_legacy_controller_binding_follows_mode_after_migration(self):
        from sora_bilingual.platform.inputs import InputManager

        pad = {"guid": "pad", "buttons": [1]}
        config = normalize_config(
            {"interaction": "language_hold", "hotkeys": {"annotation": {"gamepad": pad}}}
        )
        self.assertEqual(config["switch_binding"]["gamepad"], pad)
        buttons = set()
        manager = InputManager(
            {"hotkey": config["switch_binding"]},
            key_state=lambda _: False,
            joystick_provider=lambda: [{"id": "1", "guid": "pad", "buttons": buttons}],
        )
        policy = ActionPolicy("language_hold")
        self.assertEqual(policy.advance(manager.poll_state(True)), "primary")
        buttons.add(1)
        self.assertEqual(policy.advance(manager.poll_state(True)), "secondary")
        self.assertEqual(policy.advance(manager.poll_state(True)), "secondary")
        buttons.clear()
        self.assertEqual(policy.advance(manager.poll_state(True)), "primary")
        buttons.add(1)
        self.assertEqual(policy.advance(manager.poll_state(True)), "secondary")
        self.assertEqual(policy.advance(manager.poll_state(False)), "primary")

    def test_legacy_binding_migrates_only_to_its_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            write_config({"interaction": "language_hold", "hotkey": {"keyboard": ["F7"]}}, path)
            c = read_config(path)
            self.assertEqual(c["hotkeys"]["language_hold"]["keyboard"], ["F7"])
            self.assertEqual(c["hotkeys"]["annotation"]["keyboard"], ["CTRL", "SHIFT", "F10"])

    def test_live_backend_is_never_detached_even_with_no_modified_labels(self):
        native = NativeLabels(lambda _: None)
        native.session = SimpleNamespace(detach=lambda: self.fail("unsafe hot detach"))
        native.status = lambda: {"modified": 0}
        self.assertFalse(native.detach_if_restored())
        native.exited.set()
        self.assertTrue(native.detach_if_restored())

    def test_os_lock_prevents_second_backend_and_can_be_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backend.lock"
            one = BackendLock(path)
            try:
                with self.assertRaises((RuntimeError, OSError)):
                    BackendLock(path)
            finally:
                one.close()
            BackendLock(path).close()

    def test_transient_windows_reader_does_not_lose_atomic_status_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_config({"old": True}, path)
            replace = os.replace
            attempts = []

            def transient(source, destination):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError("reader still open")
                replace(source, destination)

            with (
                patch("sora_bilingual.config.native_config.os.replace", side_effect=transient),
                patch("sora_bilingual.config.native_config.time.sleep"),
            ):
                self.assertTrue(write_telemetry({"new": True}, path))
            self.assertEqual(read_config(path)["new"], True)
            self.assertEqual(len(attempts), 3)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_persistent_status_lock_never_escapes_into_resident_backend_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_config({"old": True}, path)
            with (
                patch(
                    "sora_bilingual.config.native_config.os.replace",
                    side_effect=PermissionError("locked"),
                ),
                patch("sora_bilingual.config.native_config.time.sleep") as pause,
            ):
                self.assertFalse(write_telemetry({"new": True}, path))
                self.assertLess(sum(call.args[0] for call in pause.call_args_list), 0.01)
            self.assertTrue(read_config(path)["old"])
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
