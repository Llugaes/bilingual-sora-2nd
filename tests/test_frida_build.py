import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from tools.build_frida_runtime import unpack_contents


class ToolchainExtractionTests(unittest.TestCase):
    def test_final_redist_wins_and_second_pass_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "compiler.zip"
            binary = "VC/Tools/MSVC/test/bin/Hostx64/x64/runtime.dll"
            redist = "VC/Redist/MSVC/test/x64/Microsoft.VC145.CRT/runtime.dll"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Contents/" + redist, b"new runtime")
                package.writestr("Contents/" + binary, b"old runtime")
            destination = root / "toolchain"
            unpack_contents([archive], destination, "test")
            self.assertEqual((destination / binary).read_bytes(), b"new runtime")
            with patch.object(Path, "write_bytes", side_effect=AssertionError("rewritten")):
                unpack_contents([archive], destination, "test")

    def test_archive_cannot_write_outside_toolchain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("Contents/../escape", b"bad")
            with self.assertRaisesRegex(ValueError, "escapes"):
                unpack_contents([archive], root / "toolchain", "test")
            self.assertFalse((root / "escape").exists())
