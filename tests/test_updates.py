import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile
import subprocess
import sys
from tools.build_release import build
from sora_bilingual.updates.github_updates import GitHubClient, version_tuple, allowed_url, sha256
from sora_bilingual.updates import update_installer as installer
from sora_bilingual.updates.update_service import UpdateService


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"ETag": '"one"'}


class Opener:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return Response(self.data)


class GitHubTests(unittest.TestCase):
    def test_semver(self):
        self.assertGreater(version_tuple("v1.10.0"), version_tuple("1.9.99"))
        for value in ["1.0.0-beta", "01.0.0", "1.2", "banana"]:
            with self.assertRaises(ValueError):
                version_tuple(value)

    def test_url_constraints(self):
        for value in [
            "http://github.com/a",
            "https://evil.test/a",
            "https://github.com.evil.test/a",
            "https://me:secret@github.com/a",
        ]:
            with self.assertRaises(ValueError):
                allowed_url(value)

    def test_latest_and_conditional_cache(self):
        opener = Opener(
            json.dumps({"tag_name": "v1.0.0", "draft": False, "prerelease": False}).encode()
        )
        client = GitHubClient("a/b", opener)
        release, cache = client.latest()
        self.assertEqual(cache["etag"], '"one"')
        opener.error = urllib.error.HTTPError("url", 304, "unchanged", {}, None)
        self.assertEqual(client.latest(cache)[0], release)
        self.assertEqual(opener.requests[-1].get_header("If-none-match"), '"one"')

    def test_nonstable_rejected(self):
        for key in ("draft", "prerelease"):
            client = GitHubClient(
                "a/b", Opener(json.dumps({"tag_name": "v1.0.0", key: True}).encode())
            )
            with self.assertRaises(ValueError):
                client.latest()

    def test_rate_limit(self):
        client = GitHubClient(
            "a/b", Opener(error=urllib.error.HTTPError("url", 429, "limit", {}, None))
        )
        with self.assertRaisesRegex(RuntimeError, "检查频率"):
            client.latest()

    def test_download_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "update.zip"
            client = GitHubClient("a/b", Opener(b"wrong"))
            with self.assertRaises(ValueError):
                client.download(
                    {"browser_download_url": "https://github.com/a/b/releases/download/v1/x"},
                    {"size": 5, "sha256": "0" * 64},
                    path,
                )
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix(".zip.part").exists())

    def test_foreign_asset_rejected(self):
        client = GitHubClient("a/b")
        with self.assertRaises(ValueError):
            client._asset(
                {
                    "assets": [
                        {
                            "name": "x",
                            "state": "uploaded",
                            "browser_download_url": "https://github.com/other/repo/releases/download/v1/x",
                        }
                    ]
                },
                "x",
            )


class InstallationTests(unittest.TestCase):
    def test_explicit_game_names_and_legacy_upgrade_assets(self):
        from sora_bilingual.updates.github_updates import ASSET_MANIFEST, LEGACY_MANIFEST

        modern = self.new.parent / ASSET_MANIFEST
        legacy = self.new.parent / LEGACY_MANIFEST
        old_meta = json.loads(legacy.read_text("utf-8"))
        old_zip = self.new.parent / old_meta["asset"]
        self.assertTrue(self.new.name.startswith("bilingual-sora-2nd-"))
        self.assertEqual(self.new.read_bytes(), old_zip.read_bytes())

        def asset(path):
            return {
                "name": path.name,
                "state": "uploaded",
                "size": path.stat().st_size,
                "digest": "sha256:" + sha256(path.read_bytes()),
                "browser_download_url": "https://github.com/test/mod/releases/download/v0.1.1/"
                + path.name,
            }

        release = {
            "tag_name": "v0.1.1",
            "assets": [asset(p) for p in (modern, legacy, self.new, old_zip)],
        }
        client = GitHubClient("test/mod", Opener(modern.read_bytes()))
        self.assertEqual(client.metadata(release)[0]["asset"], self.new.name)
        release["assets"] = [asset(p) for p in (legacy, old_zip)]
        client = GitHubClient("test/mod", Opener(legacy.read_bytes()))
        self.assertEqual(client.metadata(release)[0]["asset"], old_zip.name)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.old, cls.old_meta = build("0.1.0", "test/mod", cls.base / "old")
        cls.new, cls.meta = build("0.1.1", "test/mod", cls.base / "new")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.root = Path(self.case.name).resolve()
        with zipfile.ZipFile(self.old) as archive:
            archive.extractall(self.root)
        (self.root / "generated").mkdir()
        (self.root / "generated/native-control.json").write_text('{"primary":"en"}')

    def tearDown(self):
        self.case.cleanup()

    def test_upgrade_preserves_configuration(self):
        self.assertEqual(installer.install(self.root, self.new, self.meta), "0.1.1")
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "0.1.1"
        )
        self.assertEqual(
            (self.root / "generated/native-control.json").read_text(), '{"primary":"en"}'
        )
        self.assertTrue((self.root / "generated/tool-release.json").exists())
        self.assertFalse(installer._journal(self.root).exists())

    def test_release_launches_without_source_checkout(self):
        command = "from sora_bilingual.paths import ROOT; print(ROOT)"
        result = subprocess.run(
            [sys.executable, "-c", command],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(Path(result.stdout.strip()), self.root)
        result = subprocess.run(
            [sys.executable, str(self.root / "launch.py"), "--help"],
            cwd=self.root.parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--no-auto-connect", result.stdout)

    def test_local_edits_and_development_tree_protected(self):
        (self.root / "sora_bilingual/app/native_overlay.py").write_text("user modifications")
        with self.assertRaisesRegex(ValueError, "本地文件修改"):
            installer.install(self.root, self.new, self.meta)
        (self.root / "installed-manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "开发目录"):
            installer.install(self.root, self.new, self.meta)

    def test_lock_defers_without_modification(self):
        with installer.UpdateLease(self.root):
            with self.assertRaises(installer.UpdateBusy):
                installer.install(self.root, self.new, self.meta)
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "0.1.0"
        )

    def test_crash_during_install_is_recovered(self):
        write = installer.atomic_bytes
        count = 0

        def crash(path, data):
            nonlocal count
            write(path, data)
            if Path(path).parent == self.root / "sora_bilingual/app":
                count += 1
                if count == 2:
                    raise KeyboardInterrupt("simulated process death")

        with patch.object(installer, "atomic_bytes", crash):
            with self.assertRaises(KeyboardInterrupt):
                installer.install(self.root, self.new, self.meta)
        self.assertTrue(installer._journal(self.root).exists())
        self.assertEqual(installer.recover(self.root), "rolled_back")
        original = json.loads((self.root / "installed-manifest.json").read_text())
        for name, digest in original["files"].items():
            self.assertEqual(installer.digest((self.root / name).read_bytes()), digest)

    def test_post_commit_crash_finishes_marker(self):
        real = installer._recover_locked
        calls = 0

        def crash(root):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt("commit completed")
            return real(root)

        with patch.object(installer, "_recover_locked", crash):
            with self.assertRaises(KeyboardInterrupt):
                installer.install(self.root, self.new, self.meta)
        self.assertEqual(installer.recover(self.root), "committed")
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "0.1.1"
        )

    def test_unsafe_paths(self):
        for name in [
            "../escape.py",
            "/file.py",
            "C:/file.py",
            "generated/config.json",
            "AUX.py",
            "a\\b.py",
            "name.py.",
            "assets/../x.py",
        ]:
            self.assertFalse(installer.relative_file(name), name)

    def test_tampered_and_extra_archive_files(self):
        wrong = {**self.meta, "sha256": "0" * 64}
        with self.assertRaises(ValueError):
            installer.package_contents(self.new, wrong)
        file = self.root / "bad.zip"
        file.write_bytes(self.new.read_bytes())
        with zipfile.ZipFile(file, "a") as archive:
            archive.writestr("../escape.py", "bad")
        meta = {**self.meta, "sha256": sha256(file.read_bytes()), "size": file.stat().st_size}
        with self.assertRaises(ValueError):
            installer.package_contents(file, meta)

    def test_no_downgrade(self):
        with self.assertRaisesRegex(ValueError, "更旧"):
            installer.install(self.root, self.old, self.old_meta)

    def test_automatic_service_downloads_and_defers(self):
        class Client:
            def latest(inner, cache):
                return {"tag_name": "v0.1.1"}, {}

            def metadata(inner, release):
                return self.meta, {}

            def download(inner, asset, meta, path, progress):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.new.read_bytes())

        service = UpdateService(self.root, client=Client())
        self.assertEqual(service.policy, "automatic")
        with installer.UpdateLease(self.root):
            service._check()
        self.assertIsNotNone(service.pending)
        self.assertIn("连接结束", service.message)
        service._check()
        self.assertIsNone(service.pending)
        self.assertIn("已安装", service.message)

    def test_notify_does_not_download(self):
        class Client:
            def latest(inner, cache):
                return {"tag_name": "v0.1.1"}, {}

            def metadata(inner, release):
                raise AssertionError("must not download")

        service = UpdateService(self.root, client=Client())
        service.set_policy("notify")
        service._check()
        self.assertIn("发现", service.message)


if __name__ == "__main__":
    unittest.main()
