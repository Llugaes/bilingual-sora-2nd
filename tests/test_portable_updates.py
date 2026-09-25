"""Exercise locked-runtime behavior without loading real DLLs or touching the game."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.build_release import build
from sora_bilingual.updates import update_installer as installer
from sora_bilingual.updates.update_service import UpdateService


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

    def service(self, runtime_id, marker=b"old"):
        package, meta = self.upgrade(runtime_id, marker)
        downloaded = []

        class Client:
            def latest(inner, cache):
                return {"tag_name": "v1.0.1"}, {}

            def metadata(inner, release):
                return meta, {}

            def component_asset(inner, release, descriptor):
                return {"name": descriptor["asset"]}

            def download(inner, asset, descriptor, path, progress):
                downloaded.append(descriptor["asset"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((package.parent / descriptor["asset"]).read_bytes())

        return UpdateService(self.root, client=Client()), meta, downloaded

    def test_unchanged_runtime_downloads_only_application(self):
        service, meta, downloaded = self.service(self.old_id)
        original = installer.atomic_bytes

        def guard(path, data):
            if Path(path).is_relative_to(self.root / "runtime" / self.old_id):
                raise AssertionError("loaded runtime must not be overwritten")
            return original(path, data)

        with patch.object(installer, "atomic_bytes", guard):
            service._run(True)
        self.assertFalse(service.failed, service.message)
        self.assertEqual(downloaded, [meta["components"]["application"]["asset"]])
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "1.0.1"
        )

    def test_changed_runtime_downloads_both_components_and_preserves_old(self):
        service, meta, downloaded = self.service(self.new_id, b"new")
        service._run(True)
        self.assertFalse(service.failed, service.message)
        self.assertEqual(
            downloaded, [meta["components"][k]["asset"] for k in ("application", "runtime")]
        )
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.new_id)
        self.assertEqual(
            (self.root / "runtime" / self.old_id / "python314.dll").read_bytes(), b"old"
        )
        self.assertEqual(
            json.loads((self.root / "generated/native-control.json").read_text()), {"primary": "de"}
        )

    def test_game_connection_defers_component_install_without_redownload(self):
        service, meta, downloaded = self.service(self.old_id)
        with installer.UpdateLease(self.root):
            service._run(True)
        self.assertIsNotNone(service.pending)
        self.assertFalse(service.failed)
        service._run(False)
        self.assertIsNone(service.pending)
        self.assertEqual(len(downloaded), 1)

    def test_missing_new_runtime_requests_download_before_any_change(self):
        package, meta = self.upgrade(self.new_id, b"new")
        app = package.parent / meta["components"]["application"]["asset"]
        with self.assertRaises(installer.RuntimeRequired):
            installer.install(self.root, app, meta, component_update=True)
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.old_id)
        self.assertFalse(installer._journal(self.root).exists())

    def test_component_corruption_provides_recovery_without_changing_installation(self):
        service, meta, _ = self.service(self.new_id, b"new")
        runtime = self.base / "new" / meta["components"]["runtime"]["asset"]
        runtime.write_bytes(b"truncated")
        service._run(True)
        self.assertTrue(service.failed)
        self.assertIn("重新安装", service.message)
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.old_id)
        self.assertFalse(installer._journal(self.root).exists())

    def test_component_interrupted_upgrade_rolls_back(self):
        package, meta = self.upgrade(self.new_id, b"new")
        app = package.parent / meta["components"]["application"]["asset"]
        runtime = package.parent / meta["components"]["runtime"]["asset"]
        original = installer.atomic_bytes

        def crash(path, data):
            original(path, data)
            if Path(path) == self.root / "runtime/current.txt":
                raise KeyboardInterrupt("power loss")

        with patch.object(installer, "atomic_bytes", crash):
            with self.assertRaises(KeyboardInterrupt):
                installer.install(
                    self.root, app, meta, component_update=True, runtime_package=runtime
                )
        self.assertEqual(installer.recover(self.root), "rolled_back")
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), self.old_id)
