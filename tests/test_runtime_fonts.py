import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.fonts.runtime_fonts import runtime_manifest
from sora_bilingual.app.presentation import connection_activity
from test_font_delivery import _candidate, _fnt
import test_font_delivery as fixtures


class RuntimeFontTests(unittest.TestCase):
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
