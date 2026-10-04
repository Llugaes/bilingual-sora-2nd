import struct
import threading
import unittest
from unittest.mock import patch

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.game.source_language import (
    RuntimeTextTableReader,
    SourceLanguageMonitor,
    SourceLanguageResult,
    detect_current_language,
)
from tests.test_source_language import references


class TableMemory:
    """Bytes following the verified TextTableData layout, not detector answers."""

    base = 0x1000
    report = {"text_table_global": 0x100}

    def __init__(self):
        self.data = bytearray(0x10000)
        self.reads = []
        self.closed = False
        self.put(0x1100, "Q", 0x2000)
        self.put(0x26B8, "Q", 0x3000)
        self.put(0x3010, "Q", 0x4000)
        self.put(0x3020, "Q", 0x5000)
        self.put(0x3028, "Q", 0x6000)
        self.put(0x3030, "I", 4)
        self.put(0x5044, "II", 0, 16)
        for i, key in enumerate(references().keys):
            self.put(0x6000 + i * 8, "II", 100 + i, i)
            self.put(0x4000 + i * 16, "QQ", 0x7000 + i * 256, 0x8000 + i * 256)
            self.text_at(0x7000 + i * 256, key)
        self.set_language("zh-Hans")

    def put(self, address, fmt, *values):
        struct.pack_into("<" + fmt, self.data, address, *values)

    def text_at(self, address, value):
        raw = value.encode("utf-8") + b"\0"
        self.data[address : address + len(raw)] = raw

    def set_language(self, language):
        for i, key in enumerate(references().keys):
            self.text_at(0x8000 + i * 256, f"{language}:{key}")

    def read(self, address, size):
        self.reads.append((address, size))
        if address < 0 or address + size > len(self.data):
            raise OSError("unreadable address")
        return bytes(self.data[address : address + size])

    def text(self, address, limit):
        raw = self.read(address, limit)
        end = raw.find(b"\0")
        if end < 0:
            raise ValueError("unbounded string")
        return raw[:end].decode("utf-8")

    def close(self):
        self.closed = True


class RuntimeSourceReaderTests(unittest.TestCase):
    def setUp(self):
        self.memory = TableMemory()
        # Leave room for bounded string reads at the end of the fake address space.
        self.memory.data.extend(bytearray(0x10000))
        self.reader = RuntimeTextTableReader(42, "game.exe", opener=lambda *_: self.memory)
        self.addCleanup(self.reader.close)

    def detect(self):
        with patch(
            "sora_bilingual.game.source_language.load_references", return_value=references()
        ):
            return detect_current_language(
                "game", 42, report=self.memory.report, read_values=self.reader.read
            )

    def test_cold_start_and_in_place_switch_across_all_eight_languages(self):
        for locale in LANGUAGES:
            self.memory.set_language(locale)
            self.assertEqual(self.detect().language, locale)
        # Polling never scans the full table again while its checked rows are stable.
        self.assertEqual(self.memory.reads.count((0x6000, 32)), 1)

    def test_reallocated_and_reordered_table_is_rediscovered(self):
        self.assertEqual(self.detect().language, "zh-Hans")
        self.memory.data[0x9000:0x9040] = self.memory.data[0x4000:0x4040]
        self.memory.put(0x3010, "Q", 0x9000)
        self.memory.set_language("en")
        self.assertEqual(self.detect().language, "en")
        a, b = self.memory.read(0x9000, 16), self.memory.read(0x9010, 16)
        self.memory.data[0x9000:0x9010], self.memory.data[0x9010:0x9020] = b, a
        self.memory.set_language("ja")
        self.assertIsNone(self.detect().language)
        self.assertEqual(self.detect().language, "ja")

    def test_transition_conflicts_and_unready_table_do_not_guess(self):
        self.memory.text_at(0x8000, "ja:TXT_A")
        self.assertEqual(self.detect().reason, "inconsistent_samples")
        self.memory.put(0x26B8, "Q", 0)
        self.assertEqual(self.detect().reason, "table_unready")
        self.memory.put(0x26B8, "Q", 0x3000)
        self.memory.set_language("fr")
        self.assertEqual(self.detect().language, "fr")

    def test_three_samples_tolerate_one_modified_value(self):
        self.memory.text_at(0x8000, "modded value")
        self.assertEqual(self.detect().language, "zh-Hans")

    def test_partial_index_filling_without_header_change_is_resampled(self):
        self.memory.put(0x6004, "I", 0xFFFFFFFF)
        self.memory.put(0x600C, "I", 0xFFFFFFFF)
        self.assertIsNone(self.detect().language)
        self.memory.put(0x6004, "I", 0)
        self.assertEqual(self.detect().language, "zh-Hans")
        # The previously absent fourth sample must participate once populated.
        self.memory.put(0x600C, "I", 1)
        self.memory.text_at(0x8100, "ja:TXT_B")
        self.assertEqual(self.detect().reason, "inconsistent_samples")

    def test_table_reloaded_during_snapshot_is_not_published(self):
        header = self.reader._header
        calls = []

        def racing_header(rva):
            calls.append(rva)
            result = header(rva)
            return None if len(calls) == 2 else result

        with patch.object(self.reader, "_header", racing_header):
            self.assertIsNone(self.detect().language)
        self.assertEqual(self.detect().language, "zh-Hans")

    def test_corrupt_table_bounds_and_wrong_stride_are_rejected(self):
        for address, fmt, values in (
            (0x3030, "I", (20001,)),
            (0x5048, "I", (32,)),
            (0x6004, "I", (4,)),
            (0x6008, "I", (100,)),
        ):
            original = self.memory.read(address, struct.calcsize("<" + fmt))
            with self.subTest(address=address):
                self.memory.put(address, fmt, *values)
                self.reader.signature = None
                self.assertIsNone(self.detect().language)
                self.memory.data[address : address + len(original)] = original

    def test_close_invalidates_cached_pointers(self):
        self.detect()
        self.reader.close()
        self.assertTrue(self.memory.closed)
        self.assertIsNone(self.reader.signature)
        self.assertEqual(self.reader.rows, {})

    def test_read_permission_failure_keeps_diagnostic_and_recovers(self):
        with patch.object(self.memory, "read", side_effect=PermissionError(5, "access denied")):
            result = self.detect()
        self.assertEqual(result.reason, "probe_unavailable")
        self.assertIn("access denied", result.detail)
        self.assertEqual(self.detect().language, "zh-Hans")


class SourceLanguageMonitorTests(unittest.TestCase):
    def test_reads_on_own_thread_and_closes_on_same_thread(self):
        sampled, closed = threading.Event(), threading.Event()
        thread_ids = []

        def sample():
            thread_ids.append(threading.get_ident())
            sampled.set()
            return SourceLanguageResult("ja", "matched")

        def close():
            thread_ids.append(threading.get_ident())
            closed.set()

        monitor = SourceLanguageMonitor(sample, close, interval=60)
        self.assertTrue(sampled.wait(1))
        monitor.close()  # Interrupts the interval; never waits the full minute.
        self.assertTrue(closed.is_set())
        self.assertFalse(monitor.thread.is_alive())
        self.assertEqual(monitor.poll().language, "ja")
        self.assertIsNone(monitor.poll())
        self.assertEqual(thread_ids[0], thread_ids[-1])
        self.assertNotEqual(thread_ids[0], threading.get_ident())

    def test_sample_failure_is_reported_without_leaking_worker(self):
        sampled = threading.Event()

        def sample():
            sampled.set()
            raise OSError("process exited")

        monitor = SourceLanguageMonitor(sample, lambda: None, interval=60)
        self.assertTrue(sampled.wait(1))
        monitor.close()
        self.assertEqual(monitor.poll().reason, "probe_unavailable")
