import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sora_bilingual.app.auto_connect import AutoConnector
from sora_bilingual.fonts import font_delivery
import test_font_delivery as fixtures


class AutomaticFontTests(unittest.TestCase):
    def test_lifecycle_is_read_only_and_unknown_fonts_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            game = fixtures.FontDeliveryTests().make_game(root)
            state, ui = root / "cache", root / "ui"
            ui.mkdir()
            status = ui / "status.json"
            games, launches, builds, attempts = [], [], [], []
            exit_code = [None]

            def snapshot():
                return {
                    p.relative_to(game).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in game.rglob("*")
                    if p.is_file()
                }

            def builder(source, output):
                builds.append(source)
                return fixtures._candidate(output, 0x42)

            def prepare(source, *, cancel):
                return font_delivery.prepare(source, root=state, builder=builder)

            def launch(*args, **kwargs):
                launches.append(args)
                exit_code[0] = None
                return SimpleNamespace(poll=lambda: exit_code[0], returncode=0)

            original_open = Path.open

            def checked_open(path, mode="r", *args, **kwargs):
                if path.resolve().is_relative_to(game) and any(c in mode for c in "wax+"):
                    attempts.append(str(path))
                    raise AssertionError("Automatic game-file write is forbidden")
                return original_open(path, mode, *args, **kwargs)

            def tick_until(auto, predicate):
                end = time.monotonic() + 3
                while not predicate() and time.monotonic() < end:
                    auto.wake.set()
                    time.sleep(0.01)
                self.assertTrue(predicate(), (auto.font_status, auto.message, auto.error))

            before = snapshot()
            with (
                patch("sora_bilingual.app.auto_connect.ROOT", ui),
                patch(
                    "sora_bilingual.app.auto_connect.frida.get_local_device",
                    return_value=SimpleNamespace(enumerate_processes=lambda: list(games)),
                ),
                patch("sora_bilingual.game.install.find_game", return_value=game),
                patch(
                    "sora_bilingual.platform.win32.process_path", return_value=game / "sora_2nd.exe"
                ),
                patch(
                    "sora_bilingual.platform.win32.process_identity",
                    side_effect=lambda pid: pid * 10,
                ),
                patch(
                    "sora_bilingual.game.native_loading.prepare_fonts_fresh", side_effect=prepare
                ),
                patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archives,
                patch(
                    "sora_bilingual.fonts.font_delivery.ensure",
                    side_effect=AssertionError("No automatic installation"),
                ) as install,
                patch(
                    "sora_bilingual.fonts.font_delivery._create_bytes",
                    side_effect=AssertionError("No game-file creation"),
                ) as create,
                patch(
                    "sora_bilingual.fonts.font_delivery._replace_bytes",
                    side_effect=AssertionError("No game-file replacement"),
                ) as replace,
                patch(
                    "sora_bilingual.fonts.font_delivery._write_receipt",
                    side_effect=AssertionError("No automatic adoption"),
                ) as receipt,
                patch("sora_bilingual.app.auto_connect.subprocess.Popen", side_effect=launch),
                patch.object(Path, "open", new=checked_open),
            ):
                # Only the synthetic PAC reader is replaced; candidate generation,
                # whole-candidate validation and default runtime_manifest are real.
                archives.return_value.read.return_value = fixtures._fnt(0x41)
                auto = AutoConnector(status)
                try:
                    tick_until(auto, lambda: auto.font_status.get("state") == "runtime-required")
                    self.assertEqual(launches, [])
                    self.assertEqual(before, snapshot())
                    games[:] = [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    tick_until(auto, lambda: len(launches) == 1)
                    status.write_text(
                        json.dumps(
                            {
                                "running": True,
                                "pid": 42,
                                "updated_at": time.time(),
                                "runtimeFonts": {"ready": True},
                            }
                        ),
                        "utf-8",
                    )
                    tick_until(auto, lambda: auto.font_status.get("state") == "runtime-ready")
                    games.clear()
                    exit_code[0] = 0
                    status.write_text("{}", "utf-8")
                    tick_until(
                        auto,
                        lambda: (
                            auto.font_status.get("state") == "runtime-required"
                            and auto.process is None
                        ),
                    )
                    self.assertEqual(before, snapshot())
                    games[:] = [SimpleNamespace(pid=43, name="sora_2nd.exe")]
                    tick_until(auto, lambda: len(launches) == 2)
                    auto.retry()
                    time.sleep(0.04)
                    self.assertEqual(len(launches), 2, "A resident cannot be replaced")
                    exit_code[0] = 0
                    tick_until(auto, lambda: len(launches) == 3)
                    self.assertEqual(before, snapshot())
                finally:
                    auto.close()
                games.clear()
                auto = AutoConnector(status)
                try:
                    tick_until(auto, lambda: auto.font_status.get("state") == "runtime-required")
                    self.assertEqual(len(builds), 1, "A new UI reuses the external cache")
                finally:
                    auto.close()
                self.assertEqual(before, snapshot())
                self.assertEqual(attempts, [])
                for spy in (install, create, replace, receipt):
                    spy.assert_not_called()
            # Refuse an unrelated font, retaining every file and byte.
            foreign = game / "asset/common/font/font_0.fnt"
            foreign.parent.mkdir(parents=True)
            foreign.write_bytes(fixtures._fnt(0x43))
            before = snapshot()
            with (
                patch("sora_bilingual.app.auto_connect.ROOT", ui),
                patch(
                    "sora_bilingual.app.auto_connect.frida.get_local_device",
                    return_value=SimpleNamespace(enumerate_processes=lambda: []),
                ),
                patch("sora_bilingual.game.install.find_game", return_value=game),
                patch(
                    "sora_bilingual.game.native_loading.prepare_fonts_fresh", side_effect=prepare
                ),
                patch(
                    "sora_bilingual.fonts.font_delivery.ensure",
                    side_effect=AssertionError("No unknown overwrite"),
                ) as install,
                patch.object(Path, "open", new=checked_open),
            ):
                auto = AutoConnector(status)
                try:
                    tick_until(auto, lambda: auto.font_status.get("state") == "error")
                    self.assertEqual(auto.font_status["message"], "字体资源校验失败")
                    self.assertIn("完整受管收据", auto.font_status["detail"])
                    self.assertEqual(before, snapshot())
                    self.assertEqual(attempts, [])
                    install.assert_not_called()
                finally:
                    auto.close()
