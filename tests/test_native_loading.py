import threading
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
import tempfile
from unittest.mock import patch
from sora_bilingual.game.native_loading import ConnectionHeartbeat, ModelPreparation, prepare_fresh


class LoadingTests(unittest.TestCase):
    def test_ui_font_validation_uses_cancellable_worker_without_loading_model(self):
        import json
        from sora_bilingual.game.native_loading import prepare_runtime_fonts_fresh

        cancel = threading.Event()

        def worker(command, **kwargs):
            request = json.loads(Path(command[command.index("--request") + 1]).read_text("utf-8"))
            self.assertTrue(request["runtime_fonts"])
            self.assertFalse(request["fonts_only"])
            self.assertIs(kwargs["cancel"], cancel)
            result = Path(command[command.index("--result") + 1])
            result.write_text('{"path":"fonts","runtime_fonts":{"faces":[]}}', "utf-8")
            return SimpleNamespace(returncode=0, stderr=b"")

        with (
            patch("sora_bilingual.platform.worker_process.run_worker", side_effect=worker),
            patch("sora_bilingual.localization.cache_io.read_model", side_effect=AssertionError),
            patch(
                "sora_bilingual.fonts.runtime_fonts.runtime_manifest", side_effect=AssertionError
            ),
        ):
            result = prepare_runtime_fonts_fresh("game", cancel=cancel)
        self.assertEqual(result, {"path": "fonts", "runtime_fonts": {"faces": []}})

    def test_failed_attach_and_destroyed_cleanup_always_clear_connecting_heartbeat(self):
        from unittest.mock import Mock
        from sora_bilingual.game import native_probe as probe
        from sora_bilingual.config.native_config import read_config, write_config

        native = Mock(session=None, eternalized=True)
        native.exited = threading.Event()
        native.attach.side_effect = probe.frida.InvalidOperationError("script has been destroyed")
        native.park.side_effect = probe.frida.InvalidOperationError("script has been destroyed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({}, control)
            lock = Mock()
            telemetry = []
            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    InputManager=lambda *a, **k: SimpleNamespace(),
                    BackendLock=lambda: lock,
                    NativeLabels=lambda _: native,
                    native_report=lambda _: {},
                    detect_current_language=lambda *a, **k: SimpleNamespace(
                        language="zh-Hans", reason="matched"
                    ),
                    prepare_fresh=lambda *a, **k: {"path": "fixture.json"},
                    read_config=lambda: read_config(control),
                    write_config=lambda v, p=None: write_config(v, p or control),
                    write_telemetry=lambda value, path: telemetry.append((value, path)),
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                ),
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                ),
                patch.object(probe.signal, "signal"),
                patch("sora_bilingual.game.install.remember_game"),
            ):
                with self.assertRaisesRegex(probe.frida.InvalidOperationError, "destroyed"):
                    probe.run(root)
            for filename in ("native-live.json", "native-status.json"):
                final = [v for v, p in telemetry if p.name == filename][-1]
                self.assertFalse(final["running"])
                self.assertNotIn("phase", final)
            self.assertIn(
                "destroyed",
                [v for v, p in telemetry if p.name == "native-status.json"][-1]["error"],
            )
            lock.close.assert_called_once()

    def test_cache_summary_does_not_read_prepared_model(self):
        def worker(command, **_):
            result = Path(command[command.index("--result") + 1])
            result.write_text(
                '{"path":"prepared-model.json","coverage":{"source_records":3}}', "utf-8"
            )
            return SimpleNamespace(returncode=0, stderr=b"")

        with patch("sora_bilingual.platform.worker_process.run_worker", side_effect=worker):
            self.assertEqual(
                prepare_fresh("game", {"primary": "en"}, cache_only="summary"),
                {"path": "prepared-model.json", "coverage": {"source_records": 3}, "pair_count": 0},
            )

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
        prep.request({"primary": "en"}, force=True)
        prep.request({"primary": "en"})
        release.set()
        result = None
        end = time.monotonic() + 2
        while result is None and time.monotonic() < end:
            result = prep.poll()
            time.sleep(0.001)
        self.assertEqual(result[1], 2)

    def test_same_locale_request_keeps_matching_inflight_build(self):
        release = threading.Event()
        entered = threading.Event()
        calls = []

        def build(c):
            calls.append(c)
            entered.set()
            release.wait(2)
            return "prepared"

        prep = ModelPreparation(build, lambda c: c["primary"])
        prep.request({"primary": "en"})
        self.assertTrue(entered.wait(1))
        prep.request({"primary": "en"})
        release.set()
        end = time.monotonic() + 2
        result = None
        while result is None and time.monotonic() < end:
            result = prep.poll()
            time.sleep(0.001)
        self.assertEqual(calls, [{"primary": "en"}])
        self.assertEqual(result[1], "prepared")

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
            write_config(
                {"primary": "zh-Hans", "secondary": "ja", "experimental_primary": True},
                control,
            )
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
                        native_report=lambda _: {"text_table_global": 0x100},
                        detect_current_language=lambda *_args, **_kwargs: SimpleNamespace(
                            language="zh-Hans", reason="matched"
                        ),
                        prepare_fresh=lambda g, c, **_: {
                            **prepare(g, c)[0],
                            "path": "prepared-model.json",
                        },
                        read_config=lambda: read_config(control),
                        write_config=lambda v, p=None: write_config(v, p or control),
                        write_telemetry=publish,
                        foreground_rect=lambda _: None,
                        process_path=lambda _: root / "sora_2nd.exe",
                        process_identity=lambda _: 123,
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
                    patch("sora_bilingual.game.install.remember_game"),
                ):
                    probe.run(root)
            finally:
                watchdog.cancel()
            self.assertTrue(any(v.get("reload_error") for v in written))
            self.assertFalse(native.disabled)
            self.assertTrue(
                any(v.get("primary") == "zh-Hans" and v.get("running") for v in written)
            )

    def test_locale_reload_uses_worker_wire_cache_without_reading_model(self):
        """A prepared cache is applied atomically; the old live model is never sent again."""
        from sora_bilingual.game import native_probe as probe
        from sora_bilingual.config.native_config import read_config, write_config

        class FakeNative:
            def __init__(self, *_):
                self.session = object()
                self.exited = threading.Event()
                self.loads = []

            def attach(self, *_, **__):
                changed = read_config(control)
                changed["primary"] = "fr"
                write_config(changed, control)

            def load(self, model, _config, _mode, *, cache_path=None):
                self.loads.append((model, cache_path))
                self.exited.set()

            def select(self, *_):
                pass

            def status(self):
                return {"failed": False}

            def disable(self):
                pass

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
            # Manual target-language edits are permitted only in Experimental.
            write_config({"experimental_primary": True}, control)
            native = FakeNative()

            ready_configs = []

            def ready(_game, model_config):
                ready_configs.append(model_config)
                return {"pairs": {}, "coverage": {"source_records": 1}}, "signature", None

            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    InputManager=FakeInput,
                    BackendLock=lambda: SimpleNamespace(close=lambda: None),
                    NativeLabels=lambda _: native,
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=lambda *_args, **_kwargs: SimpleNamespace(
                        language="en", reason="matched"
                    ),
                    prepare_fresh=lambda g, c, **_: {
                        **ready(g, c)[0],
                        "path": "prepared-model.json",
                    },
                    read_config=lambda: read_config(control),
                    write_config=lambda v, p=None: write_config(v, p or control),
                    write_telemetry=lambda *_: True,
                    foreground_rect=lambda _: None,
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                ),
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                ),
                patch.object(probe.signal, "signal"),
                patch("sora_bilingual.game.install.remember_game"),
            ):
                probe.run(root)
            self.assertEqual(native.loads, [(None, "prepared-model.json")])
            self.assertEqual(ready_configs[0]["game_language"], "en")
            self.assertEqual(read_config(control)["game_language"], "en")
            self.assertEqual(read_config(control)["primary"], "fr")

    def test_source_detection_rereads_explicit_pair_before_consuming_new_user_defaults(self):
        from sora_bilingual.game import native_probe as probe
        from sora_bilingual.config.native_config import (
            LANGUAGE_DEFAULTS_PENDING,
            normalize_config,
            read_config,
            write_config,
        )

        class FakeNative:
            def __init__(self, *_):
                self.session = object()
                self.exited = threading.Event()
                self.config = None

            def attach(self, _pid, _exe, *, config, **_):
                self.config = config
                self.exited.set()

            def status(self):
                return {}

            def disable(self):
                pass

        class FakeInput:
            capture_status = "idle"

            def __init__(self, *_):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config(normalize_config({LANGUAGE_DEFAULTS_PENDING: True}), control)
            native = FakeNative()

            def detected(*_args, **_kwargs):
                from sora_bilingual.app.native_settings import update_control

                # Selection during the source probe precedes its transaction.
                update_control(
                    {"primary": "fr", "secondary": "de", "experimental_primary": True}, control
                )
                return SimpleNamespace(language="en", reason="matched")

            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    BackendLock=lambda: SimpleNamespace(close=lambda: None),
                    NativeLabels=lambda _: native,
                    InputManager=FakeInput,
                    prepare_fresh=lambda *_, **kw: {"path": "prepared-model.json", "coverage": {}},
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=detected,
                    read_config=lambda: read_config(control),
                    write_config=lambda value, _path=None: write_config(value, control),
                    write_telemetry=lambda *_: True,
                    foreground_rect=lambda _: None,
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                ),
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                ),
                patch.object(probe.signal, "signal"),
                patch("sora_bilingual.game.install.remember_game"),
            ):
                probe.run(root)
            self.assertEqual((native.config["primary"], native.config["secondary"]), ("fr", "de"))
            self.assertNotIn(LANGUAGE_DEFAULTS_PENDING, read_config(control))

    def test_unready_source_does_not_build_or_attach_a_model(self):
        from sora_bilingual.game import native_probe as probe
        from sora_bilingual.config.native_config import read_config, write_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({}, control)
            telemetry = []
            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    BackendLock=lambda: SimpleNamespace(close=lambda: None),
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=lambda *_args, **_kwargs: SimpleNamespace(
                        language=None, reason="table_unready"
                    ),
                    prepare_fresh=lambda *_, **kw: (_ for _ in ()).throw(
                        AssertionError("model built")
                    ),
                    NativeLabels=lambda *_: (_ for _ in ()).throw(AssertionError("attached")),
                    read_config=lambda: read_config(control),
                    write_config=lambda v, p=None: write_config(v, p or control),
                    write_telemetry=lambda value, _path: telemetry.append(value) or True,
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                ),
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                ),
                patch.object(probe.signal, "signal"),
                patch("sora_bilingual.game.install.remember_game"),
            ):
                probe.run(root)
            final = next(
                value for value in reversed(telemetry) if "source_language_status" in value
            )
            self.assertEqual(final["source_language_status"], "table_unready")
            self.assertIsNone(final["detected_game_language"])

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
