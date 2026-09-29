import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.game.native_probe import PerformanceJournal


class PerformanceJournalTests(unittest.TestCase):
    def test_retains_event_time_and_mode_without_repeating_heartbeat_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = PerformanceJournal(Path(tmp), 123, 456)
            state = {
                "renderMode": "primary",
                "enabled": True,
                "nativeLabelTiming": {
                    "dropped": 2,
                    "recent": [{"sequence": 5, "at": 1234567, "enterMs": 201}],
                },
            }
            journal.append(state)
            journal.append(state)
            rows = journal.path.read_text("utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            saved = json.loads(rows[0])
            self.assertEqual(saved["events"][0]["at"], 1234567)
            self.assertEqual(saved["mode"], "primary")
            self.assertEqual(saved["missed"], 4)
            self.assertEqual(saved["dropped"], 2)

    def test_io_failure_is_retried_and_rotated_storage_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = PerformanceJournal(Path(tmp), 123, 456)
            state = {"nativeLabelTiming": {"recent": [{"sequence": 1}]}}
            with patch.object(Path, "open", side_effect=OSError("busy")):
                journal.append(state)
            self.assertEqual(journal.sequence, 0)
            journal.append(state)
            self.assertEqual(journal.sequence, 1)
            old = "x" * (512 * 1024)
            journal.path.write_text(old, "utf-8")
            state["nativeLabelTiming"]["recent"][0]["sequence"] = 2
            journal.append(state)
            self.assertEqual(journal.path.with_suffix(".previous.jsonl").read_text(), old)
            self.assertLess(journal.path.stat().st_size, 1024)

    def test_disabled_instrumentation_creates_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = PerformanceJournal(Path(tmp), 123, 456)
            journal.append({"nativeLabelTiming": None})
            self.assertFalse(journal.path.exists())
