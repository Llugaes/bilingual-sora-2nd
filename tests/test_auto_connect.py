import json
import unittest
import tempfile, time, threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sora_bilingual.app.auto_connect import ConnectionPolicy


class AutoConnectTests(unittest.TestCase):
    def test_idle_ticks_do_not_rehash_entire_game_archives(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        ticks = []
        clock = [100.0]
        config = {"primary": "zh-Hans", "secondary": "ja", "scope": "all", "sources": []}
        hint = ["resources-v1"]

        def enumerate_processes():
            ticks.append(1)
            return []

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect._resource_change_hint",
                side_effect=lambda _: hint[0],
            ),
            patch(
                "sora_bilingual.app.auto_connect.time",
                SimpleNamespace(time=time.time, monotonic=lambda: clock[0]),
            ),
            patch(
                "sora_bilingual.config.native_config.read_config", side_effect=lambda: dict(config)
            ),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=enumerate_processes),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch(
                "sora_bilingual.game.native_loading.prepare_fonts_fresh",
                return_value=Path(tmp) / "fonts",
            ),
            patch(
                "sora_bilingual.game.native_loading.prepare_runtime_fonts_fresh", return_value={}
            ),
            patch(
                "sora_bilingual.localization.native_catalog.fingerprint", return_value={}
            ) as fingerprint,
            patch("sora_bilingual.localization.model_wire.wire_ready", return_value=True),
            patch("sora_bilingual.game.native_loading.prepare_fresh") as prepare,
            patch("sora_bilingual.updates.tool_updates.ReleaseWatch.poll", return_value=set()),
            patch("sora_bilingual.app.auto_connect.subprocess.Popen") as launch,
        ):
            status = Path(tmp) / "status.json"
            status.write_text(
                json.dumps(
                    {
                        "running": False,
                        "source_language_status": "game_not_running",
                        "last_detected_game_language": "zh-Hans",
                    }
                ),
                "utf-8",
            )
            auto = AutoConnector(status)
            try:
                deadline = time.monotonic() + 3
                while len(ticks) < 8 and time.monotonic() < deadline:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(fingerprint.call_count, 1)
                # Unchanged prewarm hints never authorize use of a cached model;
                # the separate preparation/connection tests verify full contents.
                for expected, action in (
                    (1, lambda: clock.__setitem__(0, 131.0)),
                    (2, lambda: (hint.__setitem__(0, "resources-v2"), clock.__setitem__(0, 162.0))),
                    (3, lambda: config.update(secondary="en")),
                ):
                    previous_ticks = len(ticks)
                    action()
                    deadline = time.monotonic() + 2
                    while (
                        fingerprint.call_count < expected or len(ticks) < previous_ticks + 2
                    ) and time.monotonic() < deadline:
                        auto.wake.set()
                        time.sleep(0.01)
                    self.assertEqual(fingerprint.call_count, expected)
            finally:
                auto.close()
            self.assertGreaterEqual(len(ticks), 8)
            self.assertEqual(
                fingerprint.call_count,
                3,
                "Idle polling must not continuously hash all PAC contents",
            )
            prepare.assert_not_called()
            launch.assert_not_called()

    def test_first_start_prepares_external_fonts_without_installing_or_mapping_build(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: []),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch(
                "sora_bilingual.game.native_loading.prepare_fonts_fresh",
                return_value=Path(tmp) / "fonts",
            ) as fonts,
            patch(
                "sora_bilingual.game.native_loading.prepare_runtime_fonts_fresh",
                return_value={"faces": []},
            ) as verify,
            patch(
                "sora_bilingual.fonts.font_delivery.ensure",
                side_effect=AssertionError("Automatic font installation is forbidden"),
            ) as install,
            patch("sora_bilingual.game.native_loading.prepare_fresh") as mappings,
            patch("sora_bilingual.app.auto_connect.subprocess.Popen") as launch,
        ):
            status = Path(tmp) / "missing-status.json"
            # A retired candidate's hint must not bring the manual workflow back.
            status.with_name("preparation-choice.json").write_text(
                json.dumps({"game": str(Path(tmp).resolve()), "source": "en"}), "utf8"
            )
            auto = AutoConnector(status)
            try:
                end = time.monotonic() + 2
                while (
                    auto.font_status.get("state") != "runtime-required" and time.monotonic() < end
                ):
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(auto.font_status["state"], "runtime-required")
                self.assertEqual(auto.message, "字体已准备，连接后将在游戏内加载，无需重启")
                fonts.assert_called_once_with(Path(tmp), cancel=auto.stop)
                verify.assert_called_once_with(Path(tmp), cancel=auto.stop)
                install.assert_not_called()
                mappings.assert_not_called()
                launch.assert_not_called()
                self.assertFalse(
                    status.exists(), "font preparation must not claim a detected language"
                )
            finally:
                auto.close()

    def test_prewarms_only_last_confirmed_source_and_does_not_delay_new_process(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        games, builds, launches = [], [], []
        entered, release = threading.Event(), threading.Event()
        ready = [False]

        def prepare(game, config, *, cache_only, cancel):
            self.assertTrue(cache_only)
            builds.append((game, config))
            entered.set()
            release.wait(3)
            ready[0] = True
            return "cache.json"

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: list(games)),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch(
                "sora_bilingual.platform.win32.process_path",
                return_value=Path(tmp) / "sora_2nd.exe",
            ),
            patch("sora_bilingual.platform.win32.process_identity", return_value=123),
            patch("sora_bilingual.localization.native_catalog.fingerprint", return_value={}),
            patch(
                "sora_bilingual.localization.model_wire.wire_ready",
                side_effect=lambda _: ready[0],
            ),
            patch("sora_bilingual.game.native_loading.prepare_fresh", side_effect=prepare),
            patch(
                "sora_bilingual.app.auto_connect.subprocess.Popen",
                side_effect=lambda *a, **k: (
                    launches.append(a) or SimpleNamespace(poll=lambda: None)
                ),
            ),
        ):
            status = Path(tmp) / "status.json"
            status.write_text(
                json.dumps(
                    {
                        "running": False,
                        "source_language_status": "game_not_running",
                        "last_detected_game_language": "zh-Hans",
                    }
                ),
                "utf-8",
            )
            auto = AutoConnector(status)
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(launches, [])
                games.append(SimpleNamespace(pid=42, name="sora_2nd.exe"))
                end = time.monotonic() + 2
                while not launches and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(len(launches), 1)
                self.assertEqual(len(builds), 1)
                self.assertEqual(builds[0][1]["game_language"], "zh-Hans")
            finally:
                release.set()
                auto.close()
            # A new UI session uses the disk cache and can connect immediately.
            entered.clear()
            auto = AutoConnector(status)
            try:
                end = time.monotonic() + 2
                while len(launches) < 2 and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(len(launches), 2)
                self.assertFalse(entered.is_set())
            finally:
                auto.close()

    def test_detector_launches_backend_after_late_game_start_and_never_terminates_it(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        games = []
        launched = []
        exit_code = [None]

        def launch(*args, **kwargs):
            launched.append(args)
            return SimpleNamespace(poll=lambda: exit_code[0], returncode=0)

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: list(games)),
            ),
            patch(
                "sora_bilingual.platform.win32.process_identity", side_effect=lambda pid: pid * 10
            ),
            patch("sora_bilingual.app.auto_connect.subprocess.Popen", side_effect=launch),
            patch("sora_bilingual.game.install.find_game", return_value=None),
            patch("sora_bilingual.platform.win32.process_path", side_effect=OSError),
        ):
            auto = AutoConnector(Path(tmp) / "status.json")

            def tick_until(predicate):
                end = time.monotonic() + 2
                while not predicate() and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertTrue(predicate())

            try:
                time.sleep(0.02)
                self.assertEqual(launched, [])
                games.append(SimpleNamespace(pid=42, name="sora_2nd.exe"))
                tick_until(lambda: len(launched) == 1)
                auto.wake.set()
                time.sleep(0.02)
                self.assertEqual(len(launched), 1)
                games[:] = [SimpleNamespace(pid=43, name="sora_2nd.exe")]
                exit_code[0] = 0
                tick_until(lambda: len(launched) == 2)
            finally:
                auto.close()

    def test_table_unready_retries_same_game_identity_with_backoff(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        games = [SimpleNamespace(pid=42, name="sora_2nd.exe")]
        launched = []

        def launch(*args, **kwargs):
            launched.append(args)
            # The first probe exits after table_unready; the retried backend
            # remains live.  Both represent the exact same process identity.
            code = 0 if len(launched) == 1 else None
            return SimpleNamespace(poll=lambda: code, returncode=code)

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: list(games)),
            ),
            patch("sora_bilingual.platform.win32.process_identity", return_value=123),
            patch("sora_bilingual.platform.win32.process_path", side_effect=OSError),
            patch("sora_bilingual.game.install.find_game", return_value=None),
            patch("sora_bilingual.app.auto_connect.subprocess.Popen", side_effect=launch),
        ):
            status = Path(tmp) / "status.json"
            status.write_text(
                json.dumps({"running": False, "source_language_status": "table_unready"}),
                "utf-8",
            )
            auto = AutoConnector(status)
            try:
                end = time.monotonic() + 3
                while len(launched) < 2 and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.02)
                self.assertEqual(len(launched), 2)
            finally:
                auto.close()

    def test_runtime_font_hint_does_not_hide_failed_connection(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        game = SimpleNamespace(pid=42, name="sora_2nd.exe")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: [game]),
            ),
            patch("sora_bilingual.platform.win32.process_identity", return_value=123),
            patch(
                "sora_bilingual.platform.win32.process_path",
                return_value=Path(tmp) / "sora_2nd.exe",
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch(
                "sora_bilingual.game.native_loading.prepare_fonts_fresh",
                return_value=Path(tmp) / "fonts",
            ),
            patch(
                "sora_bilingual.game.native_loading.prepare_runtime_fonts_fresh",
                return_value={"faces": []},
            ),
            patch(
                "sora_bilingual.app.auto_connect.subprocess.Popen",
                return_value=SimpleNamespace(poll=lambda: 1, returncode=1),
            ),
        ):
            root = Path(tmp)
            (root / "generated").mkdir()
            (root / "generated" / "native-error.log").write_text("unsupported executable", "utf-8")
            auto = AutoConnector(root / "native-status.json")
            try:
                end = time.monotonic() + 2
                while (
                    auto.error != "unsupported executable"
                    or auto.font_status.get("state") != "runtime-required"
                ) and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(auto.error, "unsupported executable")
                self.assertEqual(auto.font_status["state"], "runtime-required")
                self.assertEqual(auto.message, "连接失败：unsupported executable")
            finally:
                auto.close()

    def test_wait_connect_once_and_reconnect_after_game_restart(self):
        p = ConnectionPolicy()
        self.assertIsNone(p.choose(set(), False))
        self.assertEqual(p.choose({(42, 1)}, False), (42, 1))
        self.assertIsNone(p.choose({(42, 1)}, False))
        self.assertIsNone(p.choose(set(), False))
        self.assertEqual(p.choose({(42, 2)}, False), (42, 2))

    def test_live_backend_and_multiple_games_prevent_duplicate_injection(self):
        p = ConnectionPolicy()
        self.assertIsNone(p.choose({(42, 1)}, True))
        self.assertIsNone(p.choose({(42, 1), (43, 1)}, False))
        self.assertEqual(p.choose({(42, 1)}, False), (42, 1))

    def test_retry_rearms_only_the_current_game_identity(self):
        p = ConnectionPolicy()
        current = {(42, 1)}
        self.assertEqual(p.choose(current, False), (42, 1))
        p.retry(current)
        self.assertEqual(p.choose(current, False), (42, 1))
