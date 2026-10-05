import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.fonts.runtime_fonts import runtime_manifest
from sora_bilingual.fonts import font_delivery
from sora_bilingual.app.presentation import connection_activity
from test_font_delivery import _candidate, _fnt
import test_font_delivery as fixtures


class RuntimeFontTests(unittest.TestCase):
    def owned_installation(self, root):
        game = root / "game"
        state = root / "cache"
        previous = state / font_delivery._path_key(game) / ("a" * 24)
        old_manifest = _candidate(previous, 0x41)
        old_manifest["source_fingerprint"] = previous.name
        (previous / "manifest.json").write_text(json.dumps(old_manifest), "utf-8")
        candidate = state / font_delivery._path_key(game) / ("b" * 24)
        _candidate(candidate, 0x42)
        # The synthetic game has no executable. Native compatibility has its own
        # actual-PE regressions; all font validation and transaction code runs.
        with patch("sora_bilingual.game.hooks.verify_target"):
            installed = font_delivery.ensure(game, previous, game_running=False, root=state)
        self.assertEqual(installed["state"], "installed")
        receipt = installed["receipt"]
        return game, state, previous, candidate, receipt

    def test_owned_prior_complete_font_installation_is_a_valid_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            game, state, _, candidate, _ = self.owned_installation(root)
            before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archive:
                archive.return_value.read.return_value = _fnt(0x43)
                packet = runtime_manifest(game, candidate, root=state)
            self.assertEqual(len(packet["faces"]), 4)
            for row in packet["faces"]:
                self.assertEqual(row["source_sha256"], hashlib.sha256(_fnt(0x41)).hexdigest())
                self.assertEqual(row["sha256"], hashlib.sha256(_fnt(0x42)).hexdigest())
            self.assertEqual(
                before, {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            )

    def test_byte_identical_current_candidate_needs_no_prior_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            game, state, _, candidate, _ = self.owned_installation(root)
            _, files, _ = font_delivery._candidate_manifest(candidate)
            for relative, data in files.items():
                (game / relative).write_bytes(data)
            font_delivery.receipt_path(game, state).unlink()
            with patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archive:
                archive.return_value.read.return_value = _fnt(0x43)
                packet = runtime_manifest(game, candidate, root=state)
            self.assertEqual(
                packet["faces"][0]["source_sha256"], hashlib.sha256(_fnt(0x43)).hexdigest()
            )

    def test_prior_fonts_require_whole_owned_installation_and_bounded_cache(self):
        cases = (
            "no_receipt",
            "cross_game",
            "legacy",
            "external_candidate",
            "other_game_cache",
            "nested_candidate",
            "manifest_digest",
            "source_fingerprint",
            "missing_row",
            "duplicate_row",
            "external_target",
            "relative_target",
            "missing_font",
            "mixed_font",
            "modified_atlas",
            "modified_loader",
            "receipt_digest",
            "receipt_size",
            "boolean_size",
            "corrupt_candidate",
            "missing_candidate",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                game, state, previous, candidate, receipt = self.owned_installation(root)
                if case == "no_receipt":
                    font_delivery.receipt_path(game, state).unlink()
                elif case == "cross_game":
                    receipt["game"] = str(root / "other-game")
                elif case == "legacy":
                    receipt["version"] = 1
                elif case == "external_candidate":
                    receipt["candidate"] = str(root / previous.name)
                elif case == "other_game_cache":
                    receipt["candidate"] = str(state / ("0" * 20) / previous.name)
                elif case == "nested_candidate":
                    receipt["candidate"] = str(previous / previous.name)
                elif case == "manifest_digest":
                    receipt["manifest_sha256"] = "0" * 64
                elif case == "source_fingerprint":
                    manifest = json.loads((previous / "manifest.json").read_text("utf-8"))
                    manifest["source_fingerprint"] = "c" * 24
                    (previous / "manifest.json").write_text(json.dumps(manifest), "utf-8")
                    receipt["manifest_sha256"] = hashlib.sha256(
                        (previous / "manifest.json").read_bytes()
                    ).hexdigest()
                elif case == "missing_row":
                    receipt["files"].pop()
                elif case == "duplicate_row":
                    receipt["files"][1] = receipt["files"][0]
                elif case == "external_target":
                    receipt["files"][0]["path"] = str(root / "foreign.fnt")
                elif case == "relative_target":
                    receipt["files"][0]["path"] = "asset/common/font/font_0.fnt"
                elif case == "missing_font":
                    (game / "asset/common/font/font_0.fnt").unlink()
                elif case == "mixed_font":
                    (game / "asset/common/font/font_0.fnt").write_bytes(_fnt(0x42))
                elif case == "modified_atlas":
                    (game / "asset/dx11/image/font_0.dds").write_bytes(b"foreign")
                elif case == "modified_loader":
                    (game / "xinput1_4.dll").write_bytes(b"foreign")
                elif case == "receipt_digest":
                    receipt["files"][0]["sha256"] = "0" * 64
                elif case == "receipt_size":
                    receipt["files"][0]["size"] += 1
                elif case == "boolean_size":
                    receipt["files"][0]["size"] = True
                elif case == "corrupt_candidate":
                    (previous / "asset/common/font/font_0.fnt").write_bytes(b"foreign")
                elif case == "missing_candidate":
                    (previous / "manifest.json").unlink()
                if case != "no_receipt":
                    font_delivery._write_receipt(game, receipt, state)
                with patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archive:
                    archive.return_value.read.return_value = _fnt(0x43)
                    with self.assertRaises(font_delivery.FontDeliveryError):
                        runtime_manifest(game, candidate, root=state)

    def test_complete_packet_reads_only_small_source_font_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Windows runners may supply an 8.3 TEMP path (RUNNER~1).
            # Production emits resolved paths; compare the same path form.
            root = Path(tmp).resolve()
            _candidate(root, 0x42)
            with patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archive:
                archive.return_value.read.return_value = _fnt(0x41)
                packet = runtime_manifest(root / "game", root)
            self.assertEqual(len(packet["faces"]), 4)
            self.assertEqual(archive.call_count, 4)
            self.assertTrue(
                all("asset_common_font" in str(c.args[0]) for c in archive.call_args_list)
            )
            for row in packet["faces"]:
                self.assertEqual(row["source_sha256"], hashlib.sha256(_fnt(0x41)).hexdigest())
                self.assertEqual(
                    row["sha256"], hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()
                )
                self.assertTrue(Path(row["image"]["path"]).is_relative_to(root))
            self.assertFalse((root / "game").exists())

    def test_font_phase_never_claims_bilingual_ready(self):
        for phase in ("fonts_preparing", "fonts_applying", "fonts_error"):
            value = connection_activity({"phase": phase}, True)
            self.assertFalse(value["connected"])
            self.assertEqual(value["working"], phase != "fonts_error")

    def test_ui_and_backend_build_once_across_real_processes(self):
        code = r"""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_font_delivery import _candidate
from sora_bilingual.fonts.font_delivery import prepare
root=Path(sys.argv[1])
def build(game,output):
    with (root/'builds').open('a') as f:f.write('built\n')
    time.sleep(.2)
    return _candidate(output,0x42)
print(prepare(root/'game',root=root/'cache',builder=build),flush=True)
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures.FontDeliveryTests().make_game(root)
            children = []
            try:
                for _ in range(2):
                    children.append(
                        subprocess.Popen(
                            [sys.executable, "-X", "utf8", "-c", code, tmp],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                    )
                results = [child.communicate(timeout=15) for child in children]
                self.assertEqual([child.returncode for child in children], [0, 0], results)
                self.assertEqual(results[0][0], results[1][0])
                self.assertEqual((root / "builds").read_text().splitlines(), ["built"])
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
