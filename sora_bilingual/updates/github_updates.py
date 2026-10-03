"""Public GitHub stable-release discovery."""

import json
import urllib.error
from sora_bilingual.updates.release_client import (
    ReleaseClient,
    ASSET_PREFIX as ASSET_PREFIX,
    ASSET_MANIFEST as ASSET_MANIFEST,
    MAX_PACKAGE as MAX_PACKAGE,
    repository_name as repository_name,
    version_tuple as version_tuple,
    allowed_url as allowed_url,
    sha256 as sha256,
)


class GitHubClient(ReleaseClient):
    def latest(self, cache=None):
        cache = cache or {}
        headers = {}
        if cache.get("repository") == self.repository and cache.get("etag"):
            headers["If-None-Match"] = cache["etag"]
        try:
            with self._open(
                f"https://api.github.com/repos/{self.repository}/releases/latest", headers
            ) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("版本信息超过大小限制")
                release = json.loads(raw)
                updated = {
                    "repository": self.repository,
                    "etag": response.headers.get("ETag"),
                    "release": release,
                }
        except urllib.error.HTTPError as exc:
            try:
                if (
                    exc.code == 304
                    and cache.get("repository") == self.repository
                    and isinstance(cache.get("release"), dict)
                ):
                    release = cache["release"]
                    updated = cache
                elif exc.code == 404:
                    return None, {}
                elif exc.code in (403, 429):
                    raise RuntimeError("GitHub 暂时限制检查频率，请稍后重试") from exc
                else:
                    raise
            finally:
                exc.close()
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            raise ValueError("发布内容不是公开稳定版")
        version_tuple(release.get("tag_name"))
        return release, updated
