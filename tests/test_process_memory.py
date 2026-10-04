import ctypes
import os
import sys
import unittest

from sora_bilingual.platform.process_memory import ReadOnlyProcess


@unittest.skipUnless(sys.platform == "win32", "Windows read-only process API")
class ReadOnlyProcessTests(unittest.TestCase):
    def test_reads_owned_process_buffer_and_releases_handle(self):
        from sora_bilingual.platform.win32 import process_path

        # A venv launcher redirects to the base interpreter; use the OS path.
        reader = ReadOnlyProcess(os.getpid(), process_path(os.getpid()))
        value = ctypes.create_string_buffer("日本語 / 中文".encode("utf-8"))
        try:
            self.assertGreater(reader.base, 0)
            self.assertEqual(reader.text(ctypes.addressof(value), 100), "日本語 / 中文")
            self.assertEqual(reader.read(reader.base, 2), b"MZ")
            for address, size in ((0, 16), (1, 0), (1, 1024 * 1024 + 1)):
                with self.assertRaises(ValueError):
                    reader.read(address, size)
            with self.assertRaises(ValueError):
                reader.text(ctypes.addressof(value), 3)
        finally:
            reader.close()
        reader.close()
        with self.assertRaises(ValueError):
            reader.read(ctypes.addressof(value), 1)

    def test_unrelated_executable_is_rejected(self):
        with self.assertRaises(ProcessLookupError):
            ReadOnlyProcess(os.getpid(), "unrelated-game.exe")
