"""Bounded public raw index; no release API or publishing credentials in this client."""

import json
import math
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from sora_bilingual.updates.release_client import (
    ASSET_MANIFEST,
    GITEE_HOSTS,
    ReleaseClient,
    allowed_url,
    repository_name,
    sha256,
    version_tuple,
)
from sora_bilingual.updates.update_installer import write_json

MAX_INDEX = 64 * 1024
MAX_HISTORY = 3
INDEX_INTERVAL = 60
RAW_HOSTS = ("gitee.com", "raw.giteeusercontent.com")
DEFAULT_INDEX = {"ref": "release-index", "path": "stable.json"}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("更新 JSON 含重复字段")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("更新 JSON 含无效数字")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def index_url(repository, location):
    repository_name(repository)
    if (
        not isinstance(location, dict)
        or set(location) != {"ref", "path"}
        or not isinstance(location["ref"], str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", location["ref"])
        or location["ref"] in (".", "..")
        or location["path"] != "stable.json"
    ):
        raise ValueError("国内更新索引位置无效")
    return f"https://gitee.com/{repository}/raw/{location['ref']}/{location['path']}"


def parse_index(raw, repository):
    if len(raw) > MAX_INDEX:
        raise ValueError("国内更新索引过大")
    index = strict_json(raw)
    expected = {
        "schema": 1,
        "application": "sora-bilingual",
        "repository": repository,
        "platform": "windows-x64",
        "channel": "stable",
    }
    if (
        not isinstance(index, dict)
        or set(index) != set(expected) | {"latest", "releases"}
        or type(index.get("schema")) is not int
        or any(index.get(key) != value for key, value in expected.items())
        or not isinstance(index["releases"], list)
        or not 1 <= len(index["releases"]) <= MAX_HISTORY
    ):
        raise ValueError("国内更新索引身份或格式无效")
    entries = {}
    for entry in index["releases"]:
        if not isinstance(entry, dict) or set(entry) != {"version", "tag", "manifest"}:
            raise ValueError("国内更新索引版本格式无效")
        version = ".".join(map(str, version_tuple(entry["version"])))
        manifest = entry["manifest"]
        if (
            entry["version"] != version
            or entry["tag"] != "v" + version
            or version in entries
            or not isinstance(manifest, dict)
            or set(manifest) != {"asset", "size", "sha256"}
            or manifest["asset"] != ASSET_MANIFEST
            or type(manifest["size"]) is not int
            or not 0 < manifest["size"] <= 1024 * 1024
            or not re.fullmatch(r"[a-f0-9]{64}", str(manifest["sha256"]))
        ):
            raise ValueError("国内更新索引版本或清单摘要无效")
        entries[version] = entry
    if index["latest"] != max(entries, key=version_tuple):
        raise ValueError("国内更新索引 latest 不是最高稳定版")
    return index


class RawRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 2
    max_repeats = 1

    def __init__(self, url):
        self.path = urllib.parse.urlsplit(url).path

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, RAW_HOSTS)
        parsed = urllib.parse.urlsplit(newurl)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        # These two server-generated parameters were observed on anonymous raw
        # redirects. They are ephemeral; no credential or URL is persisted.
        if (
            parsed.path != self.path
            or parsed.fragment
            or len(query) != len({key for key, _ in query})
            or any(key not in ("metadata", "signature") or not value for key, value in query)
        ):
            raise ValueError("国内更新索引重定向越界")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class StaticGiteeClient(ReleaseClient):
    host = "gitee.com"
    hosts = GITEE_HOSTS
    headers = {"Accept": "application/json"}
    component_only = True

    def __init__(
        self,
        repository,
        location,
        *,
        directory=None,
        current_version="0.0.0",
        opener=None,
        index_opener=None,
        clock=time.time,
    ):
        super().__init__(repository, opener)
        self.index_url = index_url(repository, location)
        self.index_opener = index_opener or urllib.request.build_opener(RawRedirect(self.index_url))
        self.directory = Path(directory) if directory is not None else None
        self.clock = clock
        self.current_version = version_tuple(current_version)
        self._lock = threading.Lock()
        self._cache = self._read_cache()

    def _read_cache(self):
        if self.directory is None:
            return {}
        try:
            cache = json.loads((self.directory / "gitee-static-cache.json").read_text("utf-8"))
            if isinstance(cache, dict) and cache.get("url") == self.index_url:
                for key in ("checked_at", "failure_until", "failures"):
                    value = cache.get(key, 0)
                    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                        cache[key] = 0
                cache["failure_until"] = min(cache.get("failure_until", 0), self.clock() + 86400)
                return cache
        except OSError, ValueError:
            pass
        return {}

    def _save(self):
        if self.directory is not None:
            write_json(self.directory / "gitee-static-cache.json", self._cache)

    @property
    def highest_version(self):
        try:
            return max(self.current_version, version_tuple(self._cache.get("highest")))
        except ValueError:
            return self.current_version

    def _cached_index(self):
        raw = self._cache.get("raw")
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_INDEX:
            return None
        try:
            if sha256(raw.encode("utf-8")) == self._cache.get("digest"):
                return parse_index(raw.encode("utf-8"), self.repository)
        except ValueError:
            pass
        return None

    def _validate_history(self, index):
        if version_tuple(index["latest"]) < self.highest_version:
            raise ValueError("国内更新索引发生版本回退")
        known = self._cache.get("manifests", {})
        if not isinstance(known, dict):
            raise ValueError("本地更新摘要记录无效")
        for entry in index["releases"]:
            digest = known.get(entry["version"])
            if digest is not None and digest != entry["manifest"]["sha256"]:
                raise ValueError("同版本更新清单摘要发生变化")

    def _index(self):
        with self._lock:
            now = self.clock()
            failure_until = self._cache.get("failure_until", 0)
            if isinstance(failure_until, (int, float)) and now < failure_until:
                raise RuntimeError("国内更新索引暂不可用，已延后重试；可使用国内发行页手动下载")
            cached = self._cached_index()
            checked = self._cache.get("checked_at", 0)
            if (
                cached is not None
                and isinstance(checked, (int, float))
                and 0 <= now - checked < INDEX_INTERVAL
            ):
                self._validate_history(cached)
                return cached
            headers = {"User-Agent": "Sora-Bilingual-Updater/1", "Accept": "application/json"}
            if cached is not None and isinstance(self._cache.get("etag"), str):
                headers["If-None-Match"] = self._cache["etag"]
            retry_after = 0
            try:
                try:
                    with self.index_opener.open(
                        urllib.request.Request(self.index_url, headers=headers), timeout=20
                    ) as response:
                        raw = response.read(MAX_INDEX + 1)
                        if "html" in response.headers.get("Content-Type", "").lower():
                            raise ValueError("国内更新索引返回网页，未取得 JSON")
                        index = parse_index(raw, self.repository)
                        etag = response.headers.get("ETag")
                except urllib.error.HTTPError as exc:
                    try:
                        if exc.code == 304 and cached is not None:
                            index, raw, etag = (
                                cached,
                                self._cache["raw"].encode("utf-8"),
                                self._cache.get("etag"),
                            )
                        else:
                            value = exc.headers.get("Retry-After", "")
                            if value.isdecimal():
                                retry_after = min(int(value), 24 * 3600)
                            else:
                                try:
                                    retry_after = max(
                                        0,
                                        min(parsedate_to_datetime(value).timestamp() - now, 86400),
                                    )
                                except ValueError, TypeError, OverflowError:
                                    pass
                            raise RuntimeError(f"国内更新索引检查未完成：HTTP {exc.code}") from None
                    finally:
                        exc.close()
                self._validate_history(index)
                known = dict(self._cache.get("manifests", {}))
                known.update(
                    {entry["version"]: entry["manifest"]["sha256"] for entry in index["releases"]}
                )
                self._cache = {
                    "url": self.index_url,
                    "raw": raw.decode("utf-8"),
                    "digest": sha256(raw),
                    "etag": etag,
                    "checked_at": now,
                    "highest": index["latest"],
                    "manifests": known,
                    "failure_until": 0,
                    "failures": 0,
                }
                self._save()
                return index
            except (OSError, ValueError, RuntimeError) as exc:
                failures = min(int(self._cache.get("failures", 0)) + 1, 5)
                self._cache.update(
                    url=self.index_url,
                    failures=failures,
                    failure_until=now + max(retry_after, min(900 * 2 ** (failures - 1), 21600)),
                )
                try:
                    self._save()
                except OSError:
                    pass
                if isinstance(exc, (ValueError, RuntimeError)):
                    raise
                raise RuntimeError("国内更新索引检查未完成；可使用国内发行页手动下载") from None

    def _entry(self, tag):
        version_tuple(tag)
        for entry in self._index()["releases"]:
            if entry["tag"] == tag:
                return entry
        raise ValueError("所选版本未列入国内稳定索引")

    def _asset_from_descriptor(self, tag, descriptor):
        return {
            "name": descriptor.get("asset"),
            "size": descriptor.get("size"),
            "state": "uploaded",
            "digest": "sha256:" + str(descriptor.get("sha256")),
            "browser_download_url": f"https://gitee.com/{self.repository}/releases/download/{tag}/{descriptor.get('asset')}",
        }

    def _release(self, entry):
        return {
            "tag_name": entry["tag"],
            "prerelease": False,
            "draft": False,
            "name": "Bilingual Sora 2nd " + entry["tag"],
            "assets": [self._asset_from_descriptor(entry["tag"], entry["manifest"])],
        }

    def latest(self, cache=None):
        index = self._index()
        return self._release(
            next(entry for entry in index["releases"] if entry["version"] == index["latest"])
        ), {}

    def history(self):
        return [
            self._release(entry)
            for entry in sorted(
                self._index()["releases"], key=lambda e: version_tuple(e["version"]), reverse=True
            )
        ]

    def release(self, tag):
        return self._release(self._entry(tag))

    def metadata(self, release):
        entry = self._entry(release["tag_name"])
        descriptor = entry["manifest"]
        path = (
            self.directory / "manifests" / (descriptor["sha256"] + ".json")
            if self.directory
            else None
        )
        raw = None
        if path is not None and path.is_file() and path.stat().st_size == descriptor["size"]:
            raw = path.read_bytes()
            if sha256(raw) != descriptor["sha256"]:
                raw = None
        if raw is None:
            asset = self._asset_from_descriptor(entry["tag"], descriptor)
            with self._open(
                asset["browser_download_url"], {"Accept": "application/octet-stream"}
            ) as response:
                raw = response.read(descriptor["size"] + 1)
        if len(raw) != descriptor["size"] or sha256(raw) != descriptor["sha256"]:
            raise ValueError("国内版本清单大小或摘要不匹配")
        meta = strict_json(raw)
        if (
            not isinstance(meta, dict)
            or type(meta.get("schema")) is not int
            or not isinstance(meta.get("components"), dict)
            or type(meta["components"].get("schema")) is not int
            or not isinstance(meta.get("installer"), dict)
        ):
            raise ValueError("国内稳定版本必须提供完整组件与安装器清单")
        descriptors = [
            descriptor,
            meta["installer"],
            meta["components"].get("application"),
            meta["components"].get("runtime"),
        ]
        if any(not isinstance(item, dict) for item in descriptors):
            raise ValueError("国内版本组件清单不完整")
        resolved = {
            **release,
            "assets": [self._asset_from_descriptor(entry["tag"], item) for item in descriptors],
        }
        result = self._metadata(raw, resolved, True)
        release["assets"] = resolved["assets"]
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(raw)
            temporary.replace(path)
        return result
