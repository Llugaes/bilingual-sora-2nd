"""Static discovery exercises the production router with both release APIs blocked."""

import json
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

from sora_bilingual.updates.release_client import ASSET_MANIFEST, metadata_identity, sha256
from sora_bilingual.updates.update_service import UpdateService
from sora_bilingual.updates.release_sources import ReleaseSources
from sora_bilingual.updates.github_updates import GitHubClient
from sora_bilingual.updates.static_gitee_updates import StaticGiteeClient, RawRedirect, parse_index
from tests.test_gitee_updates import fixture
from tests.test_updates import Response
from tests.test_portable_updates import payload
from tools.build_release import build
from tools.build_update_index import prepare

INDEX_LOCATION = {"ref": "release-index", "path": "stable.json"}
INDEX_URL = "https://gitee.com/a/b/raw/release-index/stable.json"


def index_for(version, raw):
    return {
        "schema": 1,
        "application": "sora-bilingual",
        "repository": "a/b",
        "platform": "windows-x64",
        "channel": "stable",
        "latest": version,
        "releases": [
            {
                "version": version,
                "tag": "v" + version,
                "manifest": {"asset": ASSET_MANIFEST, "size": len(raw), "sha256": sha256(raw)},
            }
        ],
    }


class StaticRouter:
    def __init__(self, files):
        self.files = files
        self.requests = []
        self.content_types = {}

    def open(self, request, timeout):
        self.requests.append(request)
        if "/api/v5/" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 403, "Rate Limit Exceeded", {}, None)
        if "github" in request.full_url:
            raise OSError("GitHub unreachable")
        result = self.files[request.full_url]
        if isinstance(result, Exception):
            raise result
        response = Response(result)
        if request.full_url in self.content_types:
            response.headers["Content-Type"] = self.content_types[request.full_url]
        return response


class StaticDiscoveryTests(unittest.TestCase):
    def client(self, router, **kwargs):
        return StaticGiteeClient(
            "a/b", INDEX_LOCATION, opener=router, index_opener=router, **kwargs
        )

    def test_api_limited_github_offline_static_index_still_discovers_update(self):
        release, _, files = fixture("0.4.4")
        raw = files[ASSET_MANIFEST]
        router = StaticRouter(
            {INDEX_URL: json.dumps(index_for("0.4.4", raw)).encode()}
            | {asset["browser_download_url"]: files[asset["name"]] for asset in release["assets"]}
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps(
                    {
                        "version": "0.4.3",
                        "repository": "a/b",
                        "gitee_mirror": True,
                        "gitee_index": INDEX_LOCATION,
                    }
                )
            )
            with patch("urllib.request.build_opener", return_value=router):
                service = UpdateService(root)
                service._check()
            self.assertEqual(service.available, "v0.4.4")
            self.assertEqual(len(router.requests), 2)
            self.assertFalse(any("/api/" in req.full_url for req in router.requests))

    def test_identity_schema_versions_bounds_and_duplicate_json_are_rejected(self):
        raw = fixture("0.4.4")[2][ASSET_MANIFEST]
        good = index_for("0.4.4", raw)
        variants = []
        for key, value in (
            ("schema", True),
            ("schema", 2),
            ("repository", "other/repo"),
            ("platform", "linux"),
            ("channel", "preview"),
            ("latest", "0.4.3"),
        ):
            item = copy.deepcopy(good)
            item[key] = value
            variants.append(item)
        for key, value in (("tag", "v0.4.5"), ("version", "v0.4.4"), ("version", "0.4.4-beta")):
            item = copy.deepcopy(good)
            item["releases"][0][key] = value
            variants.append(item)
        for key, value in (
            ("asset", "../escape"),
            ("size", True),
            ("size", 1048577),
            ("sha256", "bad"),
        ):
            item = copy.deepcopy(good)
            item["releases"][0]["manifest"][key] = value
            variants.append(item)
        item = copy.deepcopy(good)
        item["releases"] *= 2
        variants.append(item)
        item = copy.deepcopy(good)
        item["command"] = "anything"
        variants.append(item)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_index(json.dumps(value).encode(), "a/b")
        for value in (
            b"<html>login</html>",
            b" " * 65537,
            json.dumps(good).replace('"schema": 1', '"schema": 1, "schema": 1').encode(),
        ):
            with self.assertRaises(ValueError):
                parse_index(value, "a/b")

    def test_concurrent_checks_share_one_request_and_html_mime_is_rejected(self):
        raw = fixture("0.4.4")[2][ASSET_MANIFEST]
        router = StaticRouter({INDEX_URL: json.dumps(index_for("0.4.4", raw)).encode()})
        client = self.client(router)
        with ThreadPoolExecutor(max_workers=4) as executor:
            tags = list(executor.map(lambda _: client.latest()[0]["tag_name"], range(4)))
        self.assertEqual(tags, ["v0.4.4"] * 4)
        self.assertEqual(len(router.requests), 1)
        router.content_types[INDEX_URL] = "text/html; charset=utf-8"
        with self.assertRaises(ValueError):
            self.client(router).latest()

    def test_retry_after_seconds_and_http_date_defer_requests(self):
        from email.utils import formatdate

        for value in ("3600", formatdate(4600, usegmt=True)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                router = StaticRouter(
                    {
                        INDEX_URL: urllib.error.HTTPError(
                            "url", 429, "limited", {"Retry-After": value}, None
                        )
                    }
                )
                client = self.client(router, directory=temporary, clock=lambda: 1000)
                with self.assertRaises(RuntimeError):
                    client.latest()
                self.assertEqual(client._cache["failure_until"], 4600)
                with self.assertRaises(RuntimeError):
                    self.client(router, directory=temporary, clock=lambda: 1901).latest()
                self.assertEqual(len(router.requests), 1)

    def test_mirror_lag_still_checks_github_but_rollback_cannot_hide_seen_newer_version(self):
        from unittest.mock import Mock

        raw = fixture("0.4.3")[2][ASSET_MANIFEST]
        router = StaticRouter({INDEX_URL: json.dumps(index_for("0.4.3", raw)).encode()})
        github = Mock()
        release, meta, _ = fixture("0.4.4", host="github.com")
        github.latest.return_value = release, {}
        github.metadata.return_value = meta, None
        sources = ReleaseSources("a/b", "0.4.3", gitee=self.client(router), github=github)
        chosen, cache = sources.latest()
        self.assertEqual(chosen["_source"], "github")
        github.latest.assert_called_once()
        old, old_meta, _ = fixture("0.4.3", host="github.com")
        github.latest.return_value = old, {}
        github.metadata.return_value = old_meta, None
        with self.assertRaises(RuntimeError):
            sources.latest(cache)

    def test_explicit_historical_tag_is_allowed_without_lowering_latest(self):
        old, _, old_files = fixture("0.4.3")
        new_raw = fixture("0.4.4")[2][ASSET_MANIFEST]
        index = index_for("0.4.4", new_raw)
        index["releases"] += index_for("0.4.3", old_files[ASSET_MANIFEST])["releases"]
        files = {INDEX_URL: json.dumps(index).encode()} | {
            asset["browser_download_url"]: old_files[asset["name"]] for asset in old["assets"]
        }
        client = self.client(StaticRouter(files), current_version="0.4.4")
        selected = client.release("v0.4.3")
        self.assertEqual(client.metadata(selected)[0]["version"], "0.4.3")
        self.assertEqual(client.latest()[0]["tag_name"], "v0.4.4")

    def test_conditional_cache_survives_restart_and_304_requires_valid_cache(self):
        now = [1000]
        raw = fixture("0.4.4")[2][ASSET_MANIFEST]
        router = StaticRouter({INDEX_URL: json.dumps(index_for("0.4.4", raw)).encode()})
        with tempfile.TemporaryDirectory() as temporary:
            first = self.client(router, directory=temporary, clock=lambda: now[0])
            self.assertEqual(first.latest()[0]["tag_name"], "v0.4.4")
            first.history()
            first.release("v0.4.4")
            self.assertEqual(len(router.requests), 1)
            second = self.client(router, directory=temporary, clock=lambda: now[0])
            second.latest()
            self.assertEqual(len(router.requests), 1)
            now[0] += 61
            router.files[INDEX_URL] = urllib.error.HTTPError("url", 304, "unchanged", {}, None)
            self.assertEqual(second.latest()[0]["tag_name"], "v0.4.4")
            self.assertEqual(router.requests[-1].get_header("If-none-match"), '"one"')
        router = StaticRouter(
            {INDEX_URL: urllib.error.HTTPError("url", 304, "unchanged", {}, None)}
        )
        with self.assertRaises(RuntimeError):
            self.client(router).latest()

    def test_replayed_index_or_same_version_digest_change_is_rejected_after_restart(self):
        for variant in ("older", "changed"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                now = [1000]
                raw = fixture("0.4.5")[2][ASSET_MANIFEST]
                index = index_for("0.4.5", raw)
                router = StaticRouter({INDEX_URL: json.dumps(index).encode()})
                self.client(router, directory=temporary, clock=lambda: now[0]).latest()
                if variant == "older":
                    index = index_for("0.4.4", fixture("0.4.4")[2][ASSET_MANIFEST])
                else:
                    index["releases"][0]["manifest"]["sha256"] = "0" * 64
                router.files[INDEX_URL] = json.dumps(index).encode()
                now[0] += 61
                with self.assertRaises(ValueError):
                    self.client(router, directory=temporary, clock=lambda: now[0]).latest()

    def test_stale_cache_failure_does_not_claim_latest_and_backoff_survives_restart(self):
        now = [1000]
        raw = fixture("0.4.4")[2][ASSET_MANIFEST]
        router = StaticRouter({INDEX_URL: json.dumps(index_for("0.4.4", raw)).encode()})
        with tempfile.TemporaryDirectory() as temporary:
            client = self.client(router, directory=temporary, clock=lambda: now[0])
            client.latest()
            now[0] += 61
            router.files[INDEX_URL] = OSError("unreachable")
            with self.assertRaises(RuntimeError):
                client.latest()
            count = len(router.requests)
            with self.assertRaises(RuntimeError):
                self.client(router, directory=temporary, clock=lambda: now[0]).history()
            self.assertEqual(len(router.requests), count)

    def test_raw_redirect_is_scoped_and_temporary_query_is_not_a_new_trust_source(self):
        redirect = RawRedirect(INDEX_URL)
        request = urllib.request.Request(INDEX_URL)
        target = INDEX_URL.replace("gitee.com", "raw.giteeusercontent.com")
        self.assertEqual(
            redirect.redirect_request(
                request, None, 302, "", {}, target + "?metadata=x&signature=y"
            ).full_url,
            target + "?metadata=x&signature=y",
        )
        for url in (
            target.replace("a/b/", "other/repo/"),
            target + "?access_token=x",
            target + "?signature=x&signature=y",
            target.replace("https:", "http:"),
            target.replace("raw.giteeusercontent.com", "evil.test"),
            target + "#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                redirect.redirect_request(request, None, 302, "", {}, url)

    def test_manifest_sha_and_component_contract_remain_required(self):
        for variant in ("bytes", "version", "runtime", "installer"):
            release, meta, files = fixture("0.4.4")
            original = files[ASSET_MANIFEST]
            if variant == "version":
                meta["version"] = "0.4.5"
            elif variant == "runtime":
                meta["components"]["runtime"]["asset"] = "../escape.zip"
            elif variant == "installer":
                meta.pop("installer")
            raw = json.dumps(meta).encode()
            index = index_for("0.4.4", original if variant == "bytes" else raw)
            manifest_url = next(
                a["browser_download_url"] for a in release["assets"] if a["name"] == ASSET_MANIFEST
            )
            router = StaticRouter(
                {
                    INDEX_URL: json.dumps(index).encode(),
                    manifest_url: b"broken" if variant == "bytes" else raw,
                }
            )
            client = self.client(router)
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                client.metadata(client.latest()[0])

    def test_all_static_operations_install_components_preserve_config_and_never_use_apis(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            old, _ = build(
                "0.4.3", "a/b", base / "old", extra=payload("a" * 16), runtime_id="a" * 16
            )
            new, meta = build(
                "0.4.4", "a/b", base / "new", extra=payload("a" * 16), runtime_id="a" * 16
            )
            setup = b"fixture installer, never executed"
            meta["installer"] = {
                "asset": "bilingual-sora-2nd-0.4.4-windows-x64-setup.exe",
                "size": len(setup),
                "sha256": sha256(setup),
            }
            raw = json.dumps(meta).encode()
            files = {INDEX_URL: json.dumps(index_for("0.4.4", raw)).encode()}
            prefix = "https://gitee.com/a/b/releases/download/v0.4.4/"
            files[prefix + ASSET_MANIFEST] = raw
            for kind in ("application", "runtime"):
                descriptor = meta["components"][kind]
                files[prefix + descriptor["asset"]] = (
                    new.parent / descriptor["asset"]
                ).read_bytes()
            router = StaticRouter(files)
            root = base / "installed"
            with zipfile.ZipFile(old) as archive:
                archive.extractall(root)
            (root / "generated").mkdir()
            config = root / "generated/native-control.json"
            config.write_bytes(b'{"primary":"en"}')
            runtime = root / ("runtime/" + "a" * 16 + "/python314.dll")
            runtime_time = runtime.stat().st_mtime_ns
            client = self.client(
                router, directory=root / "generated/updates", current_version="0.4.3"
            )
            sources = ReleaseSources(
                "a/b", "0.4.3", gitee=client, github=GitHubClient("a/b", router)
            )
            service = UpdateService(root, client=sources)
            with (
                patch.object(sources.clients["github"], "latest", side_effect=OSError("offline")),
                patch.object(sources.clients["github"], "history", side_effect=OSError("offline")),
            ):
                service._check()
                service._load_history()
                service._install(service.release)
            self.assertEqual(
                json.loads((root / "distribution.json").read_bytes())["version"], "0.4.4"
            )
            self.assertEqual(config.read_bytes(), b'{"primary":"en"}')
            self.assertEqual(runtime.stat().st_mtime_ns, runtime_time)
            self.assertEqual(
                len(router.requests), 3
            )  # index, manifest, app; unchanged runtime reused
            self.assertFalse(any("/api/" in req.full_url for req in router.requests))

    def test_both_discovery_sources_unavailable_shows_domestic_manual_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.4", "repository": "a/b", "gitee_mirror": True})
            )
            router = StaticRouter({INDEX_URL: OSError("static unavailable")})
            with patch("urllib.request.build_opener", return_value=router):
                service = UpdateService(root)
                service._run(service._check)
            self.assertTrue(service.failed)
            self.assertIn("重新安装", service.message)
            self.assertEqual(service.download_url, "https://gitee.com/a/b/releases")
            self.assertEqual(len(router.requests), 2)


class PersistentServiceTests(unittest.TestCase):
    def test_history_failure_cooldown_cannot_be_bypassed_by_clicks_or_restart(self):
        from unittest.mock import Mock

        now = [1000]
        client = Mock()
        client.history.side_effect = OSError("offline")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.4", "repository": "a/b"})
            )
            first = UpdateService(root, client=client, clock=lambda: now[0])
            first._run(first._load_history)
            second = UpdateService(root, client=client, clock=lambda: now[0])
            for service in (first, second):
                with patch.object(service, "_start") as start:
                    for _ in range(3):
                        service.load_history()
                    start.assert_not_called()
            self.assertEqual(client.history.call_count, 1)
            now[0] += 901
            with patch.object(second, "_start") as start:
                second.load_history()
                start.assert_called_once()

    def test_check_state_write_failure_keeps_cooldown_and_recovery_without_request(self):
        import errno
        from unittest.mock import Mock

        for failure in (PermissionError(errno.EACCES, "read only"), OSError(errno.ENOSPC, "full")):
            with (
                self.subTest(error=type(failure).__name__),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                (root / "distribution.json").write_text(
                    json.dumps({"version": "0.4.4", "repository": "a/b"})
                )
                client = Mock()
                service = UpdateService(root, client=client, clock=lambda: 1000)
                with (
                    patch("sora_bilingual.updates.update_service.write_json", side_effect=failure),
                    patch.object(service, "_start") as start,
                ):
                    service.tick(manual=True)
                    service.tick(manual=True)
                    start.assert_not_called()
                client.latest.assert_not_called()
                self.assertTrue(service.failed)
                self.assertIn("重新安装", service.message)
                self.assertGreater(service.manual_after, 1000)
                self.assertGreater(service.failure_until, 1000)
                self.assertFalse(service.can_check)

    def test_confirmed_metadata_change_is_rejected_before_any_download(self):
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.3", "repository": "a/b"})
            )
            (root / "installed-manifest.json").write_text("{}")
            release, meta, _ = fixture("0.4.4")
            selected = {**release, "_manifest_identity": metadata_identity(meta)}
            changed = copy.deepcopy(meta)
            changed["components"]["application"]["sha256"] = "0" * 64
            client = Mock()
            client.release.return_value = release
            client.metadata.return_value = changed, None
            service = UpdateService(root, client=client)
            with self.assertRaisesRegex(ValueError, "清单发生变化"):
                service._install(selected)
            client.download.assert_not_called()

    def test_success_restart_manual_cooldown_and_history_reuse(self):
        from unittest.mock import Mock

        now = [1000]
        client = Mock()
        client.latest.return_value = {"tag_name": "v0.4.5"}, {}
        client.history.return_value = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.4", "repository": "a/b"})
            )
            first = UpdateService(root, client=client, clock=lambda: now[0])
            first._check()
            second = UpdateService(root, client=client, clock=lambda: now[0])
            self.assertEqual(second.available, "v0.4.5")
            with patch.object(second, "_start") as start:
                second.tick()
                second.tick(manual=True)
                start.assert_not_called()
                now[0] += 61
                second.tick(manual=True)
                second.tick(manual=True)
                self.assertEqual(start.call_count, 1)
            second._load_history()
            with patch.object(second, "_start") as start:
                second.load_history()
                start.assert_not_called()

    def test_failure_restart_backoff_does_not_reset(self):
        from unittest.mock import Mock

        now = [1000]
        client = Mock()
        client.latest.side_effect = OSError("offline")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.4", "repository": "a/b"})
            )
            first = UpdateService(root, client=client, clock=lambda: now[0])
            first._run(first._check)
            second = UpdateService(root, client=client, clock=lambda: now[0])
            with patch.object(second, "_start") as start:
                second.tick(manual=True)
                now[0] += 901
                second.tick(manual=True)
                self.assertEqual(start.call_count, 1)


class IndexPreparationTests(unittest.TestCase):
    def test_local_preparation_validates_assets_and_rejects_half_written_or_rollback(self):
        _, _, files = fixture("0.4.4")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, data in files.items():
                (directory / name).write_bytes(data)
            prepared = prepare("a/b", directory)
            self.assertEqual(parse_index(prepared, "a/b")["latest"], "0.4.4")
            latest = index_for("0.4.5", fixture("0.4.5")[2][ASSET_MANIFEST])
            with self.assertRaises(ValueError):
                prepare("a/b", directory, json.dumps(latest).encode())
            (directory / "bilingual-sora-2nd-0.4.4-windows-x64-setup.exe").write_bytes(b"partial")
            with self.assertRaises(ValueError):
                prepare("a/b", directory)


if __name__ == "__main__":
    unittest.main()
