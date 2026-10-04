"""Startup failures must retain the cause and never progress to hooks."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sora_bilingual.config.native_config import read_config, write_config
from sora_bilingual.game import native_probe as probe
from sora_bilingual.game.source_language import SourceLanguageResult


class ConnectionFailureTests(unittest.TestCase):
    def run_startup(self, *, failure=None, source=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({}, control)
            report = Mock(return_value={}, side_effect=failure)
            detect = Mock(return_value=source)
            prepare = Mock(side_effect=AssertionError("must not build after failed detection"))
            native = Mock(side_effect=AssertionError("must not install hooks"))
            lock = Mock()
            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    BackendLock=lambda: lock,
                    native_report=report,
                    detect_current_language=detect,
                    NativeLabels=native,
                    prepare_fresh=prepare,
                    read_config=lambda: read_config(control),
                    write_config=lambda value, path=None: write_config(value, path or control),
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
                patch("sora_bilingual.game.install.remember_game"),
            ):
                raised = None
                try:
                    probe.run(root)
                except (ValueError, RuntimeError, OSError) as exc:
                    raised = exc
            status = json.loads((root / "generated/native-status.json").read_text("utf-8"))
            live = json.loads((root / "generated/native-live.json").read_text("utf-8"))
            self.assertFalse(status["running"])
            self.assertFalse(live["running"])
            self.assertNotIn("phase", status)
            prepare.assert_not_called()
            native.assert_not_called()
            lock.close.assert_called_once()
            if failure:
                detect.assert_not_called()
            return status, raised

    def test_executable_failure_reaches_status_with_original_detail(self):
        status, raised = self.run_startup(failure=ValueError("text parser ABI changed at 0x5877a0"))
        self.assertIsNotNone(raised)
        self.assertEqual(status["source_language_status"], "unverified_exe")
        self.assertIn("0x5877a0", status["error"])

    def test_executable_read_error_is_not_reported_as_wrong_version(self):
        status, raised = self.run_startup(failure=PermissionError("access denied"))
        self.assertIsNotNone(raised)
        self.assertEqual(status["source_language_status"], "exe_unreadable")
        self.assertIn("access denied", status["error"])

    def test_non_transient_source_failures_do_not_silently_wait_forever(self):
        for reason in (
            "source_unavailable",
            "probe_unavailable",
            "unknown_value",
            "inconsistent_samples",
        ):
            with self.subTest(reason=reason):
                status, raised = self.run_startup(source=SourceLanguageResult(None, reason))
                self.assertIsNotNone(raised)
                self.assertIn(reason, status["error"])
                self.assertEqual(status["source_language_status"], reason)

    def test_initializing_table_remains_retryable_without_error(self):
        status, raised = self.run_startup(source=SourceLanguageResult(None, "table_unready"))
        self.assertIsNone(raised)
        self.assertIsNone(status["error"])
        self.assertEqual(status["source_language_status"], "table_unready")


if __name__ == "__main__":
    unittest.main()
