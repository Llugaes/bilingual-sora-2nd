import threading
import time
import unittest
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from sora_bilingual.game.native_loading import ModelPreparation, ConnectionHeartbeat


class LoadingTests(unittest.TestCase):
    def test_same_locale_new_release_discards_previous_compiler_result(self):
        release = threading.Event()
        entered = threading.Event()
        calls = []

        def build(c):
            calls.append(c)
            if len(calls) == 1:
                entered.set()
                release.wait(2)
            return len(calls)

        prep = ModelPreparation(build, lambda c: c["primary"])
        prep.request({"primary": "en"})
        self.assertTrue(entered.wait(1))
        prep.request({"primary": "en"})
        release.set()
        result = None
        end = time.monotonic() + 2
        while result is None and time.monotonic() < end:
            result = prep.poll()
            time.sleep(0.001)
        self.assertEqual(result[1], 2)

    def test_backend_survives_locale_build_failure_without_disabling_hooks(self):
        from sora_bilingual.game import native_probe as probe
        from sora_bilingual.config.native_config import read_config, write_config

        class FakeNative:
            def __init__(self, *_):
                self.session = object()
                self.exited = threading.Event()
                self.disabled = False

            def attach(self, *_, **__):
                c = read_config(control)
                c["primary"] = "en"
                write_config(c, control)

            def select(self, *_):
                pass

            def status(self):
                return {"failed": False}

            def disable(self):
                self.disabled = True

        class FakeInput:
            capture_status = "idle"

            def __init__(self, *_, **__):
                pass

            def devices(self):
                return []

            def poll_state(self, *_):
                return SimpleNamespace(held=False, pressed=False)

            def poll_capture(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({}, control)
            native = FakeNative()
            written = []

            def prepare(_game, c):
                if c["primary"] == "en":
                    raise KeyError("empty fixture source")
                return {"pairs": {}}, "signature", None

            def publish(value, path):
                written.append(value)
                if value.get("reload_error"):
                    native.exited.set()
                return True

            # Guard a regression from hanging the test after the assertion seam.
            watchdog = threading.Timer(3, native.exited.set)
            watchdog.start()
            try:
                with (
                    patch.multiple(
                        probe,
                        ROOT=root,
                        CONTROL=control,
                        InputManager=FakeInput,
                        BackendLock=lambda: SimpleNamespace(close=lambda: None),
                        NativeLabels=lambda _: native,
                        ready_model=prepare,
                        prepare_fresh=lambda g, c: prepare(g, c)[0],
                        read_config=lambda: read_config(control),
                        write_config=lambda v, p=None: write_config(v, p or control),
                        write_telemetry=publish,
                        foreground_rect=lambda _: None,
                        process_path=lambda _: root / "sora_2nd.exe",
                    ),
                    patch.object(
                        probe.frida,
                        "get_local_device",
                        return_value=SimpleNamespace(
                            enumerate_processes=lambda: [
                                SimpleNamespace(pid=42, name="sora_2nd.exe")
                            ]
                        ),
                    ),
                    patch.object(probe.signal, "signal"),
                ):
                    probe.run(root)
            finally:
                watchdog.cancel()
            self.assertTrue(any(v.get("reload_error") for v in written))
            self.assertFalse(native.disabled)
            self.assertTrue(
                any(v.get("primary") == "zh-Hans" and v.get("running") for v in written)
            )

    def test_slow_reload_keeps_acknowledged_locale_and_connection_fresh(self):
        writes = []
        hb = ConnectionHeartbeat(lambda v, p: writes.append((p, v)), "live", "status", 42, 0.01)
        try:
            hb.update(0, {"running": True, "primary": "zh-Hans", "enabled": True})
            hb.loading("preparing")
            time.sleep(0.06)
            live = [v for p, v in writes if p == "live" and v.get("primary")]
            self.assertGreaterEqual(len(live), 2)
            self.assertEqual(live[-1]["primary"], "zh-Hans")
            self.assertEqual(live[-1]["phase"], "preparing")
            self.assertGreater(live[-1]["updated_at"], live[0]["updated_at"])
        finally:
            hb.close()

    def test_latest_language_wins_and_build_failure_is_a_result(self):
        release = threading.Event()
        entered = threading.Event()
        calls = []

        def loader(c):
            calls.append(c["primary"])
            if c["primary"] == "en":
                entered.set()
                release.wait(2)
            if c["primary"] == "de":
                raise ValueError("bad cache")
            return c["primary"]

        prep = ModelPreparation(loader, lambda c: c["primary"])
        prep.request({"primary": "en"})
        self.assertTrue(entered.wait(1))
        prep.request({"primary": "ja"})
        prep.request({"primary": "de"})
        release.set()
        end = time.monotonic() + 2
        result = None
        while time.monotonic() < end and result is None:
            result = prep.poll()
            time.sleep(0.001)
        self.assertIsNotNone(result)
        self.assertEqual(calls, ["en", "de"])
        self.assertEqual(result[0]["primary"], "de")
        self.assertIsInstance(result[2], ValueError)


if __name__ == "__main__":
    unittest.main()
