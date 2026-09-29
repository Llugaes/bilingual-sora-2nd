"""Named hosts preserve CPython code and expose an app name to Task Manager."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pefile

from sora_bilingual.platform.runtime_process import runtime_executable
from tools.runtime_branding import branded_hosts


class RuntimeHostTests(unittest.TestCase):
    def test_roles_use_named_hosts_and_development_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            interpreter = directory / "python.exe"
            interpreter.touch()
            with patch("sys.executable", str(interpreter)):
                self.assertEqual(runtime_executable("worker"), str(interpreter))
                for role in ("ui", "backend", "worker"):
                    name = {"ui": "UI", "backend": "Backend", "worker": "Worker"}[role]
                    path = directory / f"BilingualSora2nd.{name}.exe"
                    path.touch()
                    self.assertEqual(runtime_executable(role), str(path))

    @unittest.skipUnless(os.name == "nt", "Windows version resources")
    def test_named_host_preserves_code_and_changes_process_description(self):
        import sys

        directory = Path(sys._base_executable).parent
        files = {name: (directory / name).read_bytes() for name in ("python.exe", "pythonw.exe")}
        hosts = branded_hosts(files)
        self.assertEqual(len(hosts), 3)
        for name, data in hosts.items():
            original = files["python.exe" if ".Worker." in name else "pythonw.exe"]
            with pefile.PE(data=data) as actual, pefile.PE(data=original) as source:
                code = lambda pe: next(
                    s.get_data() for s in pe.sections if s.Name.startswith(b".text")
                )
                self.assertEqual(code(actual), code(source))
                self.assertEqual(
                    actual.OPTIONAL_HEADER.AddressOfEntryPoint,
                    source.OPTIONAL_HEADER.AddressOfEntryPoint,
                )
                tables = [
                    table.entries
                    for groups in actual.FileInfo
                    for group in groups
                    for table in getattr(group, "StringTable", [])
                ]
                self.assertTrue(tables)
                self.assertTrue(
                    all(t[b"FileDescription"].startswith(b"Bilingual Sora 2nd") for t in tables)
                )
                self.assertTrue(all(t[b"OriginalFilename"] == name.encode() for t in tables))
