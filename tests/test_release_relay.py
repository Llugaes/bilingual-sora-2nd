import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from sora_bilingual.updates.github_updates import GitHubClient
from sora_bilingual.updates.release_client import ASSET_MANIFEST, sha256
from tests.test_gitee_updates import fixture
from tests.test_updates import Response
from tools.relay_gitee import exclusive_directory, relay


class Source:
    def __init__(self):
        self.release, self.meta, self.payloads = fixture(host="github.com")
        self.release["draft"] = False
        for i, asset in enumerate(self.release["assets"]):
            asset.update(id=i + 1, digest="sha256:" + sha256(self.payloads[asset["name"]]))
        self.requests = []
        self.client = GitHubClient("a/b", self)

    def open(self, request, timeout):
        url = request.full_url
        self.requests.append(url)
        if "api.github.com" in url:
            return Response(json.dumps(self.release).encode())
        return Response(self.payloads[url.rsplit("/", 1)[-1]])


class RelayTests(unittest.TestCase):
    def publisher(self, source):
        publisher = Mock()
        publisher.request.return_value = {"id": 9, "prerelease": False}
        publisher.attachments.return_value = [
            {"id": a["id"], "name": a["name"], "size": a["size"]} for a in source.release["assets"]
        ]
        return publisher

    def test_source_bytes_unchanged_and_completed_checks_never_transfer_packages(self):
        source = Source()
        publisher = self.publisher(source)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            def publish(tag, packages):
                self.assertEqual(tag, "v1.0.0")
                self.assertEqual(
                    {p.name: p.read_bytes() for p in packages.iterdir()}, source.payloads
                )

            publisher.publish.side_effect = publish
            relay(source.client, directory, publisher=publisher)
            self.assertTrue((directory / "verified.json").is_file())
            self.assertEqual(len(source.requests), 5)  # latest + 4 original assets
            relay(source.client, directory, publisher=publisher)
            self.assertEqual(len(source.requests), 6)  # only version discovery
            self.assertEqual(publisher.publish.call_count, 1)
            # Deleted/replaced Gitee files invalidate the lightweight receipt.
            publisher.attachments.return_value[0]["id"] = 50
            relay(source.client, directory, publisher=publisher)
            self.assertEqual(publisher.publish.call_count, 2)
            self.assertEqual(len(source.requests), 7)  # verified local cache reused

    def test_failed_publish_has_no_success_receipt_and_retry_reuses_verified_files(self):
        source = Source()
        publisher = self.publisher(source)
        publisher.publish.side_effect = [OSError("interrupted"), None]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(OSError):
                relay(source.client, directory, publisher=publisher)
            self.assertFalse((directory / "verified.json").exists())
            relay(source.client, directory, publisher=publisher)
            self.assertTrue((directory / "verified.json").exists())
            self.assertEqual(len(source.requests), 6)

    def test_draft_preview_and_invalid_version_never_download_or_publish(self):
        for field, value in (("draft", True), ("prerelease", True), ("tag_name", "../outside")):
            source = Source()
            source.release[field] = value
            publisher = self.publisher(source)
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                relay(source.client, Path(tmp), publisher=publisher)
            publisher.publish.assert_not_called()
            self.assertEqual(len(source.requests), 1)

    def test_forged_manifest_or_payload_never_publishes(self):
        for part in (ASSET_MANIFEST, "bilingual-sora-2nd-1.0.0-app-windows-x64.zip"):
            source = Source()
            source.payloads[part] = b"x" * len(source.payloads[part])
            publisher = self.publisher(source)
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                relay(source.client, Path(tmp), publisher=publisher)
            publisher.publish.assert_not_called()

    def test_manifest_paths_rejected_before_any_component_download(self):
        source = Source()
        changed = copy.deepcopy(source.meta)
        changed["installer"]["asset"] = "../outside.exe"
        raw = json.dumps(changed).encode()
        source.payloads[ASSET_MANIFEST] = raw
        manifest = next(a for a in source.release["assets"] if a["name"] == ASSET_MANIFEST)
        manifest.update(size=len(raw), digest="sha256:" + sha256(raw))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            relay(source.client, Path(tmp))
        self.assertEqual(len(source.requests), 2)

    def test_download_only_does_not_record_published_success(self):
        source = Source()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.assertEqual(relay(source.client, directory), "v1.0.0")
            self.assertFalse((directory / "verified.json").exists())

    def test_concurrent_invocation_cannot_publish_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            with exclusive_directory(Path(tmp)), self.assertRaises(OSError):
                with exclusive_directory(Path(tmp)):
                    self.fail("second relay should not acquire the cache")
            with exclusive_directory(Path(tmp)):
                pass  # exiting the failed first attempt must release the lock


if __name__ == "__main__":
    unittest.main()
