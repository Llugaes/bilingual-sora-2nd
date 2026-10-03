import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import Mock
import urllib.error

from sora_bilingual.updates.gitee_updates import GiteeClient
from sora_bilingual.updates.release_client import (
    ASSET_MANIFEST,
    GITEE_HOSTS,
    ReleaseRedirect,
    allowed_url,
    sha256,
)
from sora_bilingual.updates.release_sources import ReleaseSources
from sora_bilingual.updates.update_service import UpdateService
from tools.build_release import build
from tests.test_portable_updates import payload
from tests.test_updates import Response
from tools.publish_gitee import GiteePublisher, MARKER, MAX_ATTACHMENT, validated_files


def fixture(version="1.0.0", host="gitee.com"):
    prefix = "bilingual-sora-2nd"
    payloads = {}

    def descriptor(name):
        payloads[name] = name.encode()
        return {"asset": name, "size": len(payloads[name]), "sha256": sha256(payloads[name])}

    meta = {
        "schema": 1,
        "application": "sora-bilingual",
        "platform": "windows-x64",
        "version": version,
        "repository": "a/b",
        **descriptor(f"{prefix}-{version}-windows-x64.zip"),
        "components": {
            "schema": 1,
            "runtime_id": "a" * 16,
            "application": descriptor(f"{prefix}-{version}-app-windows-x64.zip"),
            "runtime": descriptor(f"{prefix}-runtime-{'a' * 16}-windows-x64.zip"),
        },
        "installer": descriptor(f"{prefix}-{version}-windows-x64-setup.exe"),
    }
    payloads.pop(meta["asset"])
    payloads[ASSET_MANIFEST] = json.dumps(meta).encode()
    assets = [
        {
            "name": name,
            "size": len(data),
            "state": "uploaded",
            "browser_download_url": f"https://{host}/a/b/releases/download/v{version}/{name}",
        }
        for name, data in payloads.items()
    ]
    return (
        {"id": 10, "tag_name": "v" + version, "prerelease": False, "assets": assets},
        meta,
        payloads,
    )


class Router:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return Response(response if isinstance(response, bytes) else json.dumps(response).encode())


class GiteeTests(unittest.TestCase):
    def test_preview_latest_is_skipped_and_descending_list_is_requested(self):
        release, meta, payloads = fixture()
        previews = [
            {"id": 20, "tag_name": "v2.0.0", "prerelease": True},
            {"tag_name": "nightly"},
            release,
        ]
        router = Router([previews, release["assets"], payloads[ASSET_MANIFEST]])
        client = GiteeClient("a/b", router)
        selected, cache = client.latest({"etag": "github-only"})
        self.assertEqual(selected["tag_name"], "v1.0.0")
        self.assertIn("direction=desc", router.requests[0].full_url)
        self.assertIsNone(router.requests[0].get_header("If-none-match"))
        self.assertEqual(client.metadata(selected), (meta, None))
        self.assertEqual(cache, {})

    def test_preview_only_has_no_stable_release(self):
        client = GiteeClient("a/b", Router([[{"tag_name": "v1.0.0", "prerelease": True}]]))
        self.assertIsNone(client.latest()[0])

    def test_component_only_mirror_requires_every_component(self):
        release, _, payloads = fixture()
        release["assets"] = [a for a in release["assets"] if "-runtime-" not in a["name"]]
        with self.assertRaises(ValueError):
            GiteeClient("a/b", Router([payloads[ASSET_MANIFEST]])).metadata(release)

    def test_host_and_repository_boundaries(self):
        self.assertEqual(
            allowed_url("https://foruda.gitee.com/asset?signature=x", GITEE_HOSTS),
            "https://foruda.gitee.com/asset?signature=x",
        )
        for url in [
            "https://gitee.com.evil.test/x",
            "http://gitee.com/x",
            "https://u:p@gitee.com/x",
            "https://github.com/x",
            "https://gitee.com:444/x",
        ]:
            with self.assertRaises(ValueError):
                allowed_url(url, GITEE_HOSTS)
        with self.assertRaises(ValueError):
            ReleaseRedirect(GITEE_HOSTS).redirect_request(
                None, None, 302, "", {}, "https://evil.test/a"
            )
        release, _, _ = fixture()
        release["assets"][0]["browser_download_url"] = (
            "https://gitee.com/other/repo/releases/download/v1/a"
        )
        with self.assertRaises(ValueError):
            GiteeClient("a/b")._asset(release, release["assets"][0]["name"])

    def test_bad_manifest_digest_and_oversized_attachment_list_fail_closed(self):
        release, meta, _ = fixture()
        meta["components"]["runtime"]["sha256"] = "broken"
        with self.assertRaises(ValueError):
            GiteeClient("a/b", Router([meta])).metadata(release)
        with self.assertRaises(ValueError):
            GiteeClient("a/b", Router([[release], release["assets"] * 25])).latest()

    def test_first_party_download_reuse_and_from_start_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b"complete"
            path = Path(tmp) / "app.zip"
            path.with_suffix(".zip.part").write_bytes(b"old partial")
            router = Router([data])
            client = GiteeClient("a/b", router)
            descriptor = {"size": len(data), "sha256": sha256(data)}
            asset = {"browser_download_url": "https://gitee.com/a/b/releases/download/v1/app.zip"}
            client.download(asset, descriptor, path)
            client.download(asset, descriptor, path)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(len(router.requests), 1)
            self.assertIsNone(router.requests[0].get_header("Range"))


class FallbackTests(unittest.TestCase):
    def test_component_upgrade_uses_only_gitee_and_preserves_config_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            old, _ = build(
                "1.0.0", "a/b", base / "old", extra=payload("a" * 16), runtime_id="a" * 16
            )
            new, meta = build(
                "1.0.1", "a/b", base / "new", extra=payload("a" * 16), runtime_id="a" * 16
            )
            root = base / "installed"
            with zipfile.ZipFile(old) as archive:
                archive.extractall(root)
            (root / "generated").mkdir()
            config = root / "generated/native-control.json"
            config.write_text('{"primary":"en"}')
            assets = [
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "browser_download_url": f"https://gitee.com/a/b/releases/download/v1.0.1/{p.name}",
                }
                for p in new.parent.iterdir()
                if p.name != new.name
            ]
            release = {"id": 1, "tag_name": "v1.0.1", "prerelease": False}
            app = new.parent / meta["components"]["application"]["asset"]
            router = Router([[release], assets, json.dumps(meta).encode(), app.read_bytes()])
            github = Mock()
            client = ReleaseSources("a/b", "1.0.0", github=github, gitee=GiteeClient("a/b", router))
            service = UpdateService(root, client=client)
            service._check()
            self.assertEqual(
                json.loads((root / "distribution.json").read_text())["version"], "1.0.1"
            )
            self.assertEqual(config.read_text(), '{"primary":"en"}')
            self.assertIsNone(service.runtime_package)
            self.assertEqual(len(router.requests), 4)
            github.latest.assert_not_called()

    def test_primary_complete_release_does_not_wait_for_github(self):
        release, meta, _ = fixture()
        primary = Mock()
        primary.latest.return_value = release, {}
        primary.metadata.return_value = meta, None
        github = Mock()
        sources = ReleaseSources("a/b", "0.9.0", gitee=primary, github=github)
        chosen, _ = sources.latest()
        self.assertEqual(chosen["_source"], "gitee")
        self.assertEqual(sources.metadata(chosen), (meta, None))
        github.latest.assert_not_called()

    def test_incomplete_mirror_and_network_errors_fall_back(self):
        release, meta, _ = fixture()
        for error in [ValueError("missing manifest"), urllib.error.URLError("offline")]:
            primary = Mock()
            primary.latest.return_value = release, {}
            primary.metadata.side_effect = error
            github = Mock()
            github.latest.return_value = release, {"etag": "gh"}
            github.metadata.return_value = meta, None
            sources = ReleaseSources("a/b", "0.9.0", gitee=primary, github=github)
            chosen, _ = sources.latest()
            self.assertEqual(chosen["_source"], "github")

    def test_stale_mirror_does_not_hide_new_github_release(self):
        primary = Mock()
        primary.latest.return_value = fixture("1.0.0")[0], {}
        github = Mock()
        release, meta, _ = fixture("1.0.1")
        github.latest.return_value = release, {}
        github.metadata.return_value = meta, None
        sources = ReleaseSources("a/b", "1.0.0", gitee=primary, github=github)
        self.assertEqual(sources.latest()[0]["tag_name"], "v1.0.1")

    def test_both_sources_offline_is_not_up_to_date(self):
        clients = [Mock(), Mock()]
        for client in clients:
            client.latest.side_effect = OSError("offline")
        with self.assertRaises(RuntimeError):
            ReleaseSources("a/b", "1.0.0", gitee=clients[0], github=clients[1]).latest()

    def test_download_fallback_keeps_version_and_digest(self):
        primary, github = Mock(), Mock()
        github.host = "github.com"
        primary.download.side_effect = OSError("interrupted")
        sources = ReleaseSources("a/b", "0.9.0", gitee=primary, github=github)
        descriptor = fixture()[1]["components"]["application"]
        sources.download({"_source": "gitee", "_tag": "v1.0.0"}, descriptor, "out.zip")
        args = github.download.call_args.args
        self.assertEqual(args[1], descriptor)
        self.assertEqual(
            args[0]["browser_download_url"],
            "https://github.com/a/b/releases/download/v1.0.0/" + descriptor["asset"],
        )


class PublisherTests(unittest.TestCase):
    def test_local_validation_rejects_modified_and_oversized_artifacts(self):
        _, meta, payloads = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name, data in payloads.items():
                (directory / name).write_bytes(data)
            _, files = validated_files("v1.0.0", "a/b", directory)
            self.assertEqual(list(files)[-1], ASSET_MANIFEST)
            changed = copy.deepcopy(meta)
            changed["installer"]["size"] = MAX_ATTACHMENT + 1
            (directory / ASSET_MANIFEST).write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                validated_files("v1.0.0", "a/b", directory)
            (directory / ASSET_MANIFEST).write_bytes(payloads[ASSET_MANIFEST])
            (directory / meta["installer"]["asset"]).write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                validated_files("v1.0.0", "a/b", directory)

    def test_retention_keeps_three_newest_and_unmanaged_previews(self):
        publisher = GiteePublisher("a/b", "placeholder")
        releases = [{"id": i, "tag_name": f"v1.0.{i}", "body": MARKER} for i in range(5)]
        releases += [
            {"id": 98, "tag_name": "v1.1.0", "body": MARKER, "prerelease": True},
            {"id": 99, "tag_name": "v0.1.0", "body": "manual"},
        ]
        publisher.releases = Mock(return_value=releases)
        publisher.request = Mock()
        publisher.prune()
        self.assertEqual([call.args[0] for call in publisher.request.call_args_list], ["/1", "/0"])

    def test_failed_upload_never_promotes_or_prunes(self):
        _, _, payloads = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name, data in payloads.items():
                (directory / name).write_bytes(data)
            publisher = GiteePublisher("a/b", "placeholder")
            publisher.releases = Mock(return_value=[])
            publisher.prune = Mock()
            calls = []

            def request(suffix="", **kwargs):
                calls.append((suffix, kwargs))
                if suffix.startswith("/tags/"):
                    return None
                if not suffix:
                    return {"id": 1, "prerelease": True}
                raise OSError("interrupted upload")

            publisher.request = request
            with self.assertRaises(OSError):
                publisher.publish("v1.0.0", directory)
            self.assertFalse(any(args.get("method") == "PATCH" for _, args in calls))
            publisher.prune.assert_not_called()


if __name__ == "__main__":
    unittest.main()
