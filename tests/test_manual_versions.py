"""Explicit version consent, provider history and crash-safe rollback contracts."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from sora_bilingual.updates import update_installer as installer
from sora_bilingual.updates.github_updates import GitHubClient
from sora_bilingual.updates.gitee_updates import GiteeClient
from sora_bilingual.updates.release_sources import ReleaseSources
from sora_bilingual.updates.update_service import UpdateService
from tests.test_gitee_updates import Router, fixture
from tests.test_portable_updates import payload
from tools.build_release import build


class ReleaseHistoryTests(unittest.TestCase):
    def test_history_filters_previews_sorts_numerically_and_follows_pages(self):
        first = [{"tag_name": "v1.0.0"}] * 100
        second = [{"tag_name": v} for v in ("v1.2.0", "v1.10.0", "nightly")]
        second += [
            {"tag_name": "v2.0.0", "draft": True},
            {"tag_name": "v3.0.0", "prerelease": True},
        ]
        for kind in (GitHubClient, GiteeClient):
            router = Router([first, second])
            rows = kind("a/b", router).history()
            self.assertEqual([r["tag_name"] for r in rows], ["v1.10.0", "v1.2.0", "v1.0.0"])
            self.assertTrue(router.requests[-1].full_url.endswith("page=2"))

    def test_confirmed_tag_must_still_be_stable(self):
        for data in ({"tag_name": "v1.0.0", "prerelease": True}, {"tag_name": "v9.0.0"}):
            with self.assertRaises(ValueError):
                GitHubClient("a/b", Router([data])).release("v1.0.0")

    def test_history_merges_by_version_and_survives_one_offline_source(self):
        primary, backup = Mock(), Mock()
        primary.history.return_value = [{"tag_name": "v1.2.0"}]
        backup.history.return_value = [{"tag_name": "v1.2.0"}, {"tag_name": "v1.0.0"}]
        sources = ReleaseSources("a/b", "2.0.0", gitee=primary, github=backup)
        rows = sources.history()
        self.assertEqual(
            [(r["tag_name"], r["_source"]) for r in rows],
            [("v1.2.0", "gitee"), ("v1.0.0", "github")],
        )
        primary.history.side_effect = OSError("offline")
        self.assertEqual(len(sources.history()), 2)
        backup.history.side_effect = OSError("offline")
        with self.assertRaises(RuntimeError):
            sources.history()

    def test_metadata_cache_never_reuses_another_versions_manifest(self):
        primary = Mock()
        primary.metadata.side_effect = lambda r: ({"version": r["tag_name"]}, None)
        sources = ReleaseSources("a/b", "2.0.0", gitee=primary, github=Mock())
        for tag in ("v1.9.0", "v1.0.0", "v1.9.0"):
            self.assertEqual(
                sources.metadata({"tag_name": tag, "_source": "gitee"})[0]["version"], tag
            )
        self.assertEqual(primary.metadata.call_count, 2)

    def test_pruned_mirror_resolves_exact_historical_tag_from_backup(self):
        primary, backup = Mock(), Mock()
        primary.release.side_effect = ValueError("pruned")
        release, meta, _ = fixture("1.0.0")
        backup.release.return_value = release
        backup.metadata.return_value = meta, None
        sources = ReleaseSources("a/b", "2.0.0", gitee=primary, github=backup)
        self.assertEqual(sources.release("v1.0.0")["_source"], "github")
        backup.release.assert_called_once_with("v1.0.0")
        backup.latest.assert_not_called()


class RollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.old, cls.old_meta = build(
            "1.0.0", "a/b", cls.base / "old", extra=payload("a" * 16), runtime_id="a" * 16
        )
        cls.new, cls.new_meta = build(
            "1.2.0", "a/b", cls.base / "new", extra=payload("b" * 16, b"new"), runtime_id="b" * 16
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        self.root = Path(self.case.name)
        with zipfile.ZipFile(self.new) as archive:
            archive.extractall(self.root)
        self.config = self.root / "generated/native-control.json"
        self.prefs = self.root / "generated/updates/preferences.json"
        installer.write_json(self.config, {"primary": "de", "secondary": "ja"})
        installer.write_json(self.prefs, {"policy": "notify", "other": "kept"})

    def tearDown(self):
        self.case.cleanup()

    def test_explicit_rollback_preserves_settings_and_disables_legacy_auto_install(self):
        with self.assertRaisesRegex(ValueError, "更旧"):
            installer.install(self.root, self.old, self.old_meta)
        installer.install(self.root, self.old, self.old_meta, rollback=True)
        self.assertEqual(json.loads(self.prefs.read_text()), {"policy": "off", "other": "kept"})
        self.assertEqual(json.loads(self.config.read_text()), {"primary": "de", "secondary": "ja"})
        self.assertEqual((self.root / "runtime/current.txt").read_text().strip(), "a" * 16)
        self.assertTrue((self.root / ("runtime/" + "b" * 16 + "/python314.dll")).exists())
        self.assertEqual(UpdateService(self.root).policy, "off")

    def test_rollback_crash_recovers_previous_version_and_preferences_together(self):
        original = installer.atomic_bytes

        def crash(path, data):
            original(path, data)
            if Path(path) == self.prefs:
                raise KeyboardInterrupt("power loss after rollback preferences")

        with patch.object(installer, "atomic_bytes", crash), self.assertRaises(KeyboardInterrupt):
            installer.install(self.root, self.old, self.old_meta, rollback=True)
        self.assertEqual(installer.recover(self.root), "rolled_back")
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "1.2.0"
        )
        self.assertEqual(json.loads(self.prefs.read_text())["policy"], "notify")

    def test_old_release_cannot_be_substituted_after_confirmation(self):
        client = Mock()
        client.release.return_value = {"tag_name": "v1.1.0"}
        service = UpdateService(self.root, client=client)
        service._run(service._install, {"tag_name": "v1.0.0"})
        self.assertTrue(service.failed)
        client.download.assert_not_called()
        self.assertEqual(
            json.loads((self.root / "distribution.json").read_text())["version"], "1.2.0"
        )

    def test_historical_selection_uses_verified_components_and_not_latest(self):
        downloaded = []

        class Client:
            def release(inner, tag):
                self.assertEqual(tag, "v1.0.0")
                return {"tag_name": tag}

            def metadata(inner, release):
                return self.old_meta, None

            def component_asset(inner, release, descriptor):
                return {"name": descriptor["asset"]}

            def download(inner, asset, descriptor, path, progress):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((self.old.parent / descriptor["asset"]).read_bytes())
                downloaded.append(descriptor["asset"])

        service = UpdateService(self.root, client=Client())
        service._run(service._install, {"tag_name": "v1.0.0"})
        self.assertTrue(service.installed, service.message)
        self.assertEqual(len(downloaded), 2)
        self.assertEqual(json.loads(self.prefs.read_text())["policy"], "off")


if __name__ == "__main__":
    unittest.main()
