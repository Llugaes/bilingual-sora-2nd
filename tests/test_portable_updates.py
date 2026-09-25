"""Exercise locked-runtime behavior without loading real DLLs or touching the game."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.build_release import build
from sora_bilingual.updates import update_installer as installer


def payload(runtime_id, marker=b"old"):
    return {
        "BilingualSora2nd.exe": b"launcher",
        "runtime/current.txt": (runtime_id + "\n").encode(),
        **{
            f"runtime/{runtime_id}/{name}": marker
            for name in ("python.exe", "pythonw.exe", "python314._pth", "python314.dll")
        },
    }


class PortableUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "install"
        self.old_id, self.new_id = "a" * 16, "b" * 16
        package, _ = build(
            "1.0.0",
            "test/mod",
            self.base / "old",
            extra=payload(self.old_id),
            runtime_id=self.old_id,
        )
        with zipfile.ZipFile(package) as archive:
            archive.extractall(self.root)
        (self.root / "generated").mkdir()
        (self.root / "generated/native-control.json").write_text('{"primary":"de"}')

    def tearDown(self):
        self.temp.cleanup()

    def upgrade(self, runtime_id, marker=b"old"):
        return build(
            "1.0.1",
            "test/mod",
            self.base / "new",
            extra=payload(runtime_id, marker),
            runtime_id=runtime_id,
        )

    def test_same_runtime_is_never_rewritten_even_for_rollback(self):
        package, meta = self.upgrade(self.old_id)
        original = installer.atomic_bytes

        def guarded(path, data):
            if Path(path).is_relative_to(self.root / "runtime" / self.old_id):
                raise AssertionError("attempt to overwrite loaded DLL")
            return original(path, data)

        with patch.object(installer, "atomic_bytes", guarded):
            self.assertEqual(installer.install(self.root, package, meta), "1.0.1")

    def test_runtime_upgrade_is_side_by_side_and_preserves_configuration(self):
        package, meta = self.upgrade(self.new_id, b"new")
        installer.install(self.root, package, meta)
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.new_id)
        self.assertEqual(
            (self.root / "runtime" / self.old_id / "python314.dll").read_bytes(), b"old"
        )
        self.assertEqual(
            (self.root / "runtime" / self.new_id / "python314.dll").read_bytes(), b"new"
        )
        self.assertEqual(
            json.loads((self.root / "generated/native-control.json").read_text()), {"primary": "de"}
        )

    def test_same_runtime_identifier_cannot_mask_changed_binary(self):
        package, meta = self.upgrade(self.old_id, b"modified")
        with self.assertRaisesRegex(ValueError, "原地修改"):
            installer.install(self.root, package, meta)

    def test_failed_runtime_upgrade_restores_selector_and_old_files(self):
        package, meta = self.upgrade(self.new_id, b"new")
        original = installer.atomic_bytes

        def crash(path, data):
            original(path, data)
            if Path(path) == self.root / "runtime/current.txt":
                raise KeyboardInterrupt("power failure after selector swap")

        with patch.object(installer, "atomic_bytes", crash):
            with self.assertRaises(KeyboardInterrupt):
                installer.install(self.root, package, meta)
        self.assertEqual(installer.recover(self.root), "rolled_back")
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.old_id)
        self.assertEqual(
            (self.root / "runtime" / self.old_id / "python314.dll").read_bytes(), b"old"
        )

    def test_runtime_paths_stay_inside_versioned_directory(self):
        for path in [
            "runtime/pythonw.exe",
            "runtime/current.exe",
            "runtime/../bad.dll",
            "runtime/" + self.old_id + "/../../bad.dll",
            "Other.exe",
        ]:
            self.assertFalse(installer.relative_file(path), path)
