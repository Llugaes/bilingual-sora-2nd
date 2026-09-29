from concurrent.futures import CancelledError
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from sora_bilingual.platform.worker_process import run_worker
from sora_bilingual.platform.win32 import process_identity
from sora_bilingual.game.tool_shutdown import ExitSignal, reset_exit, shutdown


class ShutdownTests(unittest.TestCase):
    def test_exit_request_is_separate_from_user_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "native-control.json"
            config.write_text('{"enabled":true,"primary":"en"}', "utf8")
            original = config.read_bytes()
            reset_exit(root)
            self.assertFalse(ExitSignal(root).is_set())
            shutdown(root)
            self.assertTrue(ExitSignal(root).is_set())
            self.assertEqual(config.read_bytes(), original)
            reset_exit(root)
            self.assertFalse(ExitSignal(root).is_set())

    def test_cannot_report_exit_while_backend_is_alive(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sora_bilingual.game.tool_shutdown.backend_alive", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "尚未安全退出"):
                shutdown(tmp, timeout=0.05)

    @unittest.skipUnless(os.name == "nt", "Windows worker lifetime")
    def test_cancelling_compiler_terminates_and_reaps_its_descendants(self):
        code = """
import json,os,subprocess,sys,time
from pathlib import Path
from sora_bilingual.platform.worker_process import own_worker_job
job=own_worker_job()
child=subprocess.Popen([sys._base_executable,'-c','import time;time.sleep(60)'],
                       creationflags=subprocess.CREATE_NO_WINDOW)
Path(sys.argv[1]).write_text(json.dumps({'parent':os.getpid(),'child':child.pid}))
time.sleep(60)
"""
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "started.json"
            cancel = threading.Event()
            observed = {}

            def stop():
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                if marker.exists():
                    observed.update(json.loads(marker.read_text()))
                    observed["created"] = process_identity(observed["child"])
                cancel.set()

            watcher = threading.Thread(target=stop)
            watcher.start()
            with self.assertRaises(CancelledError):
                run_worker([sys.executable, "-c", code, str(marker)], cwd=Path.cwd(), cancel=cancel)
            watcher.join(timeout=6)
            self.assertIn("created", observed, "Worker did not create its test child")
            for name in ("parent", "child"):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    try:
                        process_identity(observed[name])
                    except OSError:
                        break
                    time.sleep(0.02)
                else:
                    self.fail(f"Cancelled preparation left its {name} process alive")
