"""Offline preparation reuses one build across installer/UI/backend callers."""

import tempfile
import subprocess
import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from sora_bilingual.localization import model_worker


class ModelWorkerTests(unittest.TestCase):
    def test_two_processes_recheck_after_one_shared_build(self):
        code = """
import sys,time
from pathlib import Path
from sora_bilingual.localization.model_worker import preparation_lock
root=Path(sys.argv[1]); print('ready',flush=True)
while not (root/'go').exists(): time.sleep(.01)
with preparation_lock(root):
    marker=root/'published'
    if not marker.exists():
        time.sleep(.3); marker.write_text('complete'); print('built')
    else: print('reused')
"""
        with tempfile.TemporaryDirectory() as tmp:
            children = []
            try:
                for _ in range(2):
                    children.append(
                        subprocess.Popen(
                            [sys.executable, "-c", code, tmp],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                    )
                for child in children:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                (Path(tmp) / "go").touch()
                results = [child.communicate(timeout=15) for child in children]
                self.assertEqual(sorted(out.strip() for out, _ in results), ["built", "reused"])
                self.assertEqual([child.returncode for child in children], [0, 0], results)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()

    def test_catalog_preparation_needs_no_detected_source_language(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(
                model_worker, "load_entries", return_value=([{}, {}], "signature")
            ) as load,
            patch.object(model_worker, "ready_model") as ready,
        ):
            result = model_worker.prepare_request(
                {"game": "installed-game", "catalog_only": True}, Path(tmp)
            )
            load.assert_called_once_with(Path("installed-game"), Path(tmp))
            ready.assert_not_called()
            self.assertEqual(result["stage"], "catalog")
            self.assertEqual(result["records"], 2)

    def test_full_preparation_preserves_selected_source_and_packs_cache(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(
                model_worker, "ready_model", return_value=({"coverage": {"n": 2}}, "sig", None)
            ) as ready,
            patch.object(model_worker, "prepare_wire") as wire,
        ):
            result = model_worker.prepare_request(
                {
                    "game": "installed-game",
                    "config": {"primary": "en", "secondary": "ja", "game_language": "zh-Hant"},
                },
                Path(tmp),
            )
            self.assertEqual(ready.call_args.args[1]["game_language"], "zh-Hant")
            self.assertEqual(ready.call_args.args[2], Path(tmp))
            wire.assert_called_once()
            self.assertEqual(result["coverage"], {"n": 2})
