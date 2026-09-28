import json
import unittest
import tempfile, time, threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sora_bilingual.app.auto_connect import ConnectionPolicy


class AutoConnectTests(unittest.TestCase):
    def test_newer_runtime_source_supersedes_offline_hint_for_same_game(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        entered = threading.Event()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: []),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.localization.native_catalog.fingerprint", return_value={}),
            patch("sora_bilingual.localization.model_wire.wire_ready", return_value=False),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch("sora_bilingual.fonts.font_delivery.prepare", return_value=Path(tmp) / "fonts"),
            patch("sora_bilingual.fonts.font_delivery.ensure", return_value={"state": "healthy"}),
            patch(
                "sora_bilingual.game.native_loading.prepare_fresh",
                side_effect=lambda *a, **k: entered.set() or "cache",
            ) as prepare,
        ):
            status = Path(tmp) / "status.json"
            status.write_text(
                json.dumps(
                    {
                        "game_directory": str(Path(tmp).resolve()),
                        "source_language_status": "game_not_running",
                        "last_detected_game_language": "ja",
                        "updated_at": 2,
                    }
                ),
                "utf8",
            )
            status.with_name("preparation-choice.json").write_text(
                json.dumps(
                    {
                        "game": str(Path(tmp).resolve()),
                        "source": "en",
                        "selected_at": 1,
                    }
                ),
                "utf8",
            )
            auto = AutoConnector(status)
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(prepare.call_args.args[1]["game_language"], "ja")
            finally:
                auto.close()

    def test_completed_old_build_cannot_replace_new_cached_selection(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        entered, release = threading.Event(), threading.Event()
        ready = [False]

        def build(*args, **kwargs):
            entered.set()
            release.wait(3)
            raise ValueError("obsolete build failed")

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch("sora_bilingual.game.install.remember_game"),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: []),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.localization.native_catalog.fingerprint", return_value={}),
            patch(
                "sora_bilingual.localization.model_wire.wire_ready", side_effect=lambda _: ready[0]
            ),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch("sora_bilingual.fonts.font_delivery.prepare", return_value=Path(tmp) / "fonts"),
            patch("sora_bilingual.fonts.font_delivery.ensure", return_value={"state": "healthy"}),
            patch("sora_bilingual.game.native_loading.prepare_fresh", side_effect=build),
        ):
            (Path(tmp) / "sora_2nd.exe").touch()
            (Path(tmp) / "pac/steam").mkdir(parents=True)
            auto = AutoConnector(Path(tmp) / "status.json")
            try:
                self.assertTrue(entered.wait(2))
                ready[0] = True
                auto.prepare_game(Path(tmp), "en")
                end = time.monotonic() + 2
                while auto.preparation_status["state"] != "ready" and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertEqual(auto.preparation_status["state"], "ready")
                release.set()
                # Let the coordinator consume the obsolete worker error.
                time.sleep(0.35)
                self.assertEqual(auto.preparation_status["state"], "ready")
            finally:
                release.set()
                auto.close()

    def test_explicit_preparation_source_builds_offline_without_claiming_detection(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        entered = threading.Event()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: []),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.localization.native_catalog.fingerprint", return_value={}),
            patch("sora_bilingual.localization.model_wire.wire_ready", return_value=False),
            patch(
                "sora_bilingual.config.native_config.read_config",
                return_value={
                    "primary": "zh-Hans",
                    "secondary": "ja",
                    "language_defaults_pending": True,
                },
            ),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch("sora_bilingual.fonts.font_delivery.prepare", return_value=Path(tmp) / "fonts"),
            patch("sora_bilingual.fonts.font_delivery.ensure", return_value={"state": "installed"}),
            patch(
                "sora_bilingual.game.native_loading.prepare_fresh",
                side_effect=lambda *a, **k: entered.set() or "cache",
            ) as prepare,
            patch("sora_bilingual.app.auto_connect.subprocess.Popen") as launch,
        ):
            status = Path(tmp) / "status.json"
            status.with_name("preparation-choice.json").write_text(
                json.dumps({"game": str(Path(tmp).resolve()), "source": "en"}), "utf8"
            )
            auto = AutoConnector(status)
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(prepare.call_args.args[1]["game_language"], "en")
                self.assertEqual(prepare.call_args.args[1]["primary"], "en")
                self.assertTrue(prepare.call_args.kwargs["cache_only"] is True)
                self.assertFalse(status.exists(), "offline hint must not claim runtime detection")
                launch.assert_not_called()
            finally:
                auto.close()

    def test_new_install_prepares_resources_before_any_game_was_seen(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        entered = threading.Event()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.app.auto_connect.ROOT", Path(tmp)),
            patch(
                "sora_bilingual.app.auto_connect.frida.get_local_device",
                return_value=SimpleNamespace(enumerate_processes=lambda: []),
            ),
            patch("sora_bilingual.game.install.find_game", return_value=Path(tmp)),
            patch("sora_bilingual.localization.native_catalog.fingerprint", return_value={}),
            patch("sora_bilingual.fonts.font_delivery.source_fingerprint", return_value="fonts"),
            patch("sora_bilingual.fonts.font_delivery.prepare", return_value=Path(tmp) / "fonts"),
            patch("sora_bilingual.fonts.font_delivery.ensure", return_value={"state": "installed"}),
            patch(
                "sora_bilingual.game.native_loading.prepare_fresh",
                side_effect=lambda *a, **k: entered.set() or "cache",
            ) as prepare,
            patch("sora_bilingual.app.auto_connect.subprocess.Popen") as launch,
        ):
            auto = AutoConnector(Path(tmp) / "missing-status.json")
            try:
                self.assertTrue(
                    entered.wait(2), "fresh install waits for a game instead of preparing offline"
                )
                self.assertEqual(prepare.call_args.kwargs["cache_only"], "catalog")
                launch.assert_not_called()
            finally:
                auto.close()

    def test_prewarms_only_last_confirmed_source_and_does_not_delay_new_process(self):
        from sora_bilingual.app.auto_connect import AutoConnector

        games, builds, launches = [], [], []
        entered, release = threading.Event(), threading.Event()
        ready = [False]

        def prepare(game, config, *, cache_only):
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
