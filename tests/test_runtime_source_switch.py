"""Exercise source-language changes through the running production backend."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.config.native_config import read_config, write_config
from sora_bilingual.game import native_probe as probe
from sora_bilingual.game.source_language import SourceLanguageResult
from sora_bilingual.app.presentation import connection_activity, describe_state


class BackendFixture:
    """Drive the real connection loop; replace only OS/game/build boundaries."""

    def __init__(self, source="zh-Hans", settings=None):
        self.source = source
        self.settings = settings or {}
        self.builds, self.loads, self.selections, self.phases = [], [], [], []
        self.attached = None
        self.exited = threading.Event()
        self.session = object()
        self.tick = 0
        self.source_failure = None
        self.on_prepare = lambda _: None

    def attach(self, *_, **kwargs):
        self.attached = kwargs["config"].copy()

    def load(self, model, config, mode, *, cache_path=None):
        self.loads.append((dict(config), mode, cache_path))

    def select(self, mode, enabled):
        self.selections.append((mode, enabled))

    def status(self):
        return {"failed": False}

    def disable(self):
        pass

    def configure(self, **changes):
        write_config({**read_config(self.control_path), **changes}, self.control_path)

    def run(self, step):
        case = self

        class Monitor:
            def __init__(self, *_):
                pass

            def poll(self):
                case.tick += 1
                step(case)
                if case.tick > 200:
                    case.exited.set()
                if case.source_failure is not None:
                    return case.source_failure
                return SourceLanguageResult(
                    case.source, "matched" if case.source else "table_unready"
                )

            def close(self):
                pass

        class Input:
            capture_status = "idle"

            def __init__(self, *_, **__):
                pass

            def devices(self):
                return []

            def poll_state(self, *_):
                return SimpleNamespace(held=False, pressed=False)

            def poll_capture(self):
                return None

            def update_config(self, *_):
                pass

        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            (root / "generated").mkdir()
            self.control_path = root / "control.json"
            write_config(
                {"primary": "ja", "secondary": "zh-Hans", **self.settings}, self.control_path
            )

            def prepare(_game, config, **kwargs):
                if kwargs.get("cache_only") == "runtime_fonts":
                    return {}
                self.builds.append(dict(config))
                self.on_prepare(config)
                return {"path": config["game_language"] + ".json", "coverage": {}}

            heartbeat = probe.ConnectionHeartbeat

            def capture_heartbeat(*args):
                result = heartbeat(*args)
                loading = result.loading

                def capture(phase, error=None):
                    case.phases.append((phase, error))
                    loading(phase, error)

                result.loading = capture
                return result

            stack.enter_context(
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=self.control_path,
                    BackendLock=lambda: SimpleNamespace(close=lambda: None),
                    NativeLabels=lambda _: self,
                    InputManager=Input,
                    ConnectionHeartbeat=capture_heartbeat,
                    prepare_fresh=prepare,
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=lambda *_, **__: SourceLanguageResult(
                        self.source, "matched"
                    ),
                    SourceLanguageMonitor=Monitor,
                    read_config=lambda: read_config(self.control_path),
                    write_config=lambda value, path=None: write_config(
                        value, path or self.control_path
                    ),
                    write_telemetry=lambda *_: True,
                    foreground_rect=lambda _: None,
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                )
            )
            stack.enter_context(
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                )
            )
            stack.enter_context(patch.object(probe.signal, "signal"))
            stack.enter_context(patch("sora_bilingual.game.install.remember_game"))
            watchdog = threading.Timer(4, self.exited.set)
            watchdog.start()
            try:
                probe.run(root)
                self.saved = read_config(self.control_path)
            finally:
                watchdog.cancel()


class RuntimeSourceSwitchTests(unittest.TestCase):
    def test_source_switch_progress_and_errors_are_not_shown_as_user_disabled(self):
        config = {"primary": "ja", "secondary": "zh-Hans", "enabled": True}
        live = {"running": True, "updated_at": 100, "enabled": False}
        for phase, error in (
            ("preparing", None),
            ("waiting_source_language", None),
            ("source_language_error", "probe_unavailable: access denied"),
            ("preparing", "cache write failed"),
        ):
            with self.subTest(phase=phase, error=error):
                backend = {
                    "running": True,
                    "updated_at": 100,
                    "phase": phase,
                    "reload_error": error,
                }
                state = describe_state(config, live, backend, 100)
                activity = connection_activity(backend, True)
                self.assertNotIn("已停用", state["title"])
                self.assertFalse(state["connected"])
                if error:
                    self.assertEqual(state["detail"], error)
                    self.assertEqual(activity["tone"], "error")
                else:
                    self.assertTrue(activity["working"])

    def test_cold_start_uses_each_supported_source_language(self):
        for source in LANGUAGES:
            with self.subTest(source=source):
                case = BackendFixture(source)
                case.run(lambda c: c.exited.set())
                self.assertEqual(case.attached["game_language"], source)
                self.assertEqual(case.builds[0]["game_language"], source)
                self.assertEqual(len(case.builds), 1)

    def test_continuous_source_switch_keeps_display_pair_and_mode(self):
        for mode, enabled in (
            ("annotation", True),
            ("primary", True),
            ("secondary", True),
            ("annotation", False),
        ):
            with self.subTest(mode=mode, enabled=enabled):
                case = BackendFixture(
                    settings={"interaction": None, "mode": mode, "enabled": enabled}
                )

                def step(c):
                    if len(c.loads) == len(LANGUAGES):
                        c.exited.set()
                    else:
                        # Visit every other source, then return to Chinese.
                        c.source = (*[l for l in LANGUAGES if l != "zh-Hans"], "zh-Hans")[
                            len(c.loads)
                        ]

                case.run(step)
                self.assertEqual(len(case.loads), len(LANGUAGES))
                expected_pair = (case.attached["primary"], case.attached["secondary"])
                for config, loaded_mode, path in case.loads:
                    self.assertEqual((config["primary"], config["secondary"]), expected_pair)
                    self.assertEqual((loaded_mode, config["enabled"]), (mode, enabled))
                    self.assertEqual(path, config["game_language"] + ".json")
                self.assertEqual((case.saved["primary"], case.saved["secondary"]), expected_pair)

    def test_missing_table_pauses_then_restores_existing_model_without_rebuild(self):
        case = BackendFixture()

        def step(c):
            c.source = None if c.tick == 1 else "zh-Hans"
            if c.tick == 3:
                c.exited.set()

        case.run(step)
        self.assertTrue(case.selections[-1][1])
        self.assertTrue(all(not value for _, value in case.selections[:-1]))
        self.assertEqual(len(case.builds), 1)
        self.assertIn(("waiting_source_language", None), case.phases)
        self.assertEqual(case.phases[-1], ("ready", None))

    def test_user_can_reenable_after_temporarily_disabling_mod(self):
        case = BackendFixture()

        def step(c):
            if c.tick < 3:
                c.configure(enabled=c.tick == 2)
            else:
                c.exited.set()

        case.run(step)
        self.assertEqual([value for _, value in case.selections], [False, True])

    def test_new_source_and_user_pair_supersede_inflight_build(self):
        case = BackendFixture()
        building, release = threading.Event(), threading.Event()

        def prepare(config):
            if config["game_language"] == "ja":
                building.set()
                if not release.wait(1):
                    raise RuntimeError("test failed to replace pending source")

        case.on_prepare = prepare

        def step(c):
            if c.tick == 1:
                c.source = "ja"
            if building.is_set():
                c.source = "en"
                c.configure(primary="fr", secondary="de")
                release.set()
            if c.loads:
                c.exited.set()

        case.run(step)
        self.assertEqual(len(case.loads), 1)
        config = case.loads[0][0]
        self.assertEqual(
            (config["game_language"], config["primary"], config["secondary"]), ("en", "fr", "de")
        )
        self.assertTrue(config["enabled"])

    def test_permission_or_resource_failure_is_visible_and_retries(self):
        for reason in ("probe_unavailable", "source_unavailable"):
            with self.subTest(reason=reason):
                case = BackendFixture()

                def step(c):
                    if c.tick == 1:
                        c.source_failure = SourceLanguageResult(
                            None, reason, detail="access denied"
                        )
                    elif c.tick == 2:
                        self.assertEqual(c.phases[-1][0], "source_language_error")
                        self.assertIn("access denied", c.phases[-1][1])
                        self.assertIn(reason, c.phases[-1][1])
                        c.source_failure = None
                    else:
                        c.exited.set()

                case.run(step)
                self.assertTrue(case.selections[-1][1])
                self.assertEqual(case.phases[-1], ("ready", None))

    def test_failed_source_build_stays_disabled_and_can_be_retried(self):
        case = BackendFixture()
        failed = [False]

        def prepare(config):
            if config["game_language"] == "ja" and not failed[0]:
                failed[0] = True
                raise OSError("cache write failed")

        case.on_prepare = prepare

        def step(c):
            c.source = "ja"
            if any(error for _, error in c.phases):
                self.assertFalse(any(enabled for _, enabled in c.selections))
                c.configure(mode_request=1)
            if c.loads:
                c.exited.set()

        case.run(step)
        self.assertTrue(failed[0])
        self.assertEqual(len(case.loads), 1)
        self.assertTrue(case.loads[0][0]["enabled"])
        self.assertEqual(case.phases[-1], ("ready", None))

    def test_same_game_process_rebuilds_mapping_after_source_language_change(self):
        language = ["zh-Hans"]
        builds, loads = [], []

        class Native:
            session = object()

            def __init__(self):
                self.exited = threading.Event()

            def attach(self, *_args, **_kwargs):
                # The language option reloads game tables without changing PID.
                language[0] = "ja"

            def load(self, model, config, mode, *, cache_path=None):
                loads.append((dict(config), cache_path))
                self.exited.set()

            def status(self):
                return {"failed": False}

            def select(self, *_):
                pass

            def disable(self):
                pass

        class Input:
            capture_status = "idle"

            def __init__(self, *_, **__):
                pass

            def devices(self):
                return []

            def poll_state(self, *_):
                return SimpleNamespace(held=False, pressed=False)

            def poll_capture(self):
                return None

        native = Native()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({"primary": "ja", "secondary": "zh-Hans"}, control)

            def prepare(_game, config, **kwargs):
                if kwargs.get("cache_only") == "runtime_fonts":
                    return {}
                builds.append(dict(config))
                return {"path": config["game_language"] + ".json", "coverage": {}}

            stack.enter_context(
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    BackendLock=lambda: SimpleNamespace(close=lambda: None),
                    NativeLabels=lambda _: native,
                    InputManager=Input,
                    prepare_fresh=prepare,
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=lambda *_, **__: SimpleNamespace(
                        language=language[0], reason="matched"
                    ),
                    read_config=lambda: read_config(control),
                    write_config=lambda value, path=None: write_config(value, path or control),
                    write_telemetry=lambda *_: True,
                    foreground_rect=lambda _: None,
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                )
            )
            stack.enter_context(
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                )
            )
            stack.enter_context(patch.object(probe.signal, "signal"))
            stack.enter_context(patch("sora_bilingual.game.install.remember_game"))
            watchdog = threading.Timer(2.5, native.exited.set)
            watchdog.start()
            try:
                probe.run(root)
            finally:
                watchdog.cancel()
            self.assertEqual([c["game_language"] for c in builds], ["zh-Hans", "ja"])
            self.assertEqual([c["game_language"] for c, _ in loads], ["ja"])
            self.assertEqual(loads[0][1], "ja.json")
            self.assertEqual(
                (loads[0][0]["primary"], loads[0][0]["secondary"]),
                (builds[0]["primary"], builds[0]["secondary"]),
                "a game source switch must preserve the selected display languages",
            )


if __name__ == "__main__":
    unittest.main()
