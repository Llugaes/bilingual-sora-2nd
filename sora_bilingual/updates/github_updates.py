"""Public GitHub Releases client. No accounts, tokens, telemetry or game access."""

import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ASSET_PREFIX = "bilingual-sora-2nd"
ASSET_MANIFEST = ASSET_PREFIX + "-update.json"
LEGACY_PREFIX = "sora-bilingual"
LEGACY_MANIFEST = LEGACY_PREFIX + "-update.json"
API_VERSION = "2026-03-10"
MAX_PACKAGE = 768 * 1024 * 1024  # Includes the private CPython/Qt runtime, never game data.


def version_tuple(value):
    match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", str(value))
    if not match:
        raise ValueError("不支持的稳定版版本号：" + str(value))
    return tuple(map(int, match.groups()))


def repository_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("尚未配置有效的 GitHub 发布仓库")
    if any(v in (".", "..") for v in value.split("/")):
        raise ValueError("无效仓库")
    return value


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def allowed_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("更新只允许 GitHub HTTPS 下载")
    if parsed.hostname not in (
        "api.github.com",
        "github.com",
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    ):
        raise ValueError("更新下载地址不属于 GitHub")
    return url


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GitHubClient:
    def __init__(self, repository, opener=None):
        self.repository = repository_name(repository)
        self.opener = opener or urllib.request.build_opener(GitHubRedirect())

    def _open(self, url, headers=None):
        request = urllib.request.Request(
            allowed_url(url),
            headers={
                "User-Agent": "Sora-Bilingual-Updater/1",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                **(headers or {}),
            },
        )
        return self.opener.open(request, timeout=20)

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

    def _asset(self, release, name):
        assets = [
            a
            for a in release.get("assets", [])
            if a.get("name") == name and a.get("state") == "uploaded"
        ]
        if len(assets) != 1:
            raise ValueError("此版本缺少唯一的更新资源：" + name)
        asset = assets[0]
        url = asset.get("browser_download_url", "")
        prefix = f"https://github.com/{self.repository}/releases/download/"
        if not url.startswith(prefix):
            raise ValueError("更新资源不属于配置的仓库")
        allowed_url(url)
        return asset

    def metadata(self, release):
        modern = any(a.get("name") == ASSET_MANIFEST for a in release.get("assets", []))
        asset = self._asset(release, ASSET_MANIFEST if modern else LEGACY_MANIFEST)
        with self._open(
            asset["browser_download_url"], {"Accept": "application/octet-stream"}
        ) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("更新清单过大")
        if asset.get("digest") and asset["digest"] != "sha256:" + sha256(raw):
            raise ValueError("更新清单摘要不匹配")
        meta = json.loads(raw)
        if (
            not isinstance(meta, dict)
            or meta.get("schema") != 1
            or meta.get("application") != "sora-bilingual"
            or meta.get("platform") != "windows-x64"
        ):
            raise ValueError("更新包类型不兼容")
        if version_tuple(meta.get("version")) != version_tuple(release["tag_name"]):
            raise ValueError("发布标签与包版本不一致")
        if meta.get("repository") != self.repository:
            raise ValueError("更新包仓库不匹配")
        if not isinstance(meta.get("size"), int) or not 0 < meta["size"] <= MAX_PACKAGE:
            raise ValueError("更新包大小不合法")
        if not re.fullmatch("[0-9a-f]{64}", str(meta.get("sha256"))):
            raise ValueError("更新包没有有效摘要")
        prefix = ASSET_PREFIX if modern else LEGACY_PREFIX
        expected = f"{prefix}-{meta['version']}-windows-x64.zip"
        if meta.get("asset") != expected:
            raise ValueError("更新文件名不匹配")
        package = self._asset(release, expected)
        if package.get("size") != meta["size"]:
            raise ValueError("GitHub 与清单中的包大小不一致")
        if package.get("digest") and package["digest"] != "sha256:" + meta["sha256"]:
            raise ValueError("GitHub 与清单中的摘要不一致")
        if "components" in meta:
            components = meta["components"]
            if (
                not isinstance(components, dict)
                or components.get("schema") != 1
                or not re.fullmatch("[0-9a-f]{16}", str(components.get("runtime_id")))
            ):
                raise ValueError("不支持的组件更新格式")
            runtime_id = components["runtime_id"]
            for kind, expected_name in [
                ("application", f"{ASSET_PREFIX}-{meta['version']}-app-windows-x64.zip"),
                ("runtime", f"{ASSET_PREFIX}-runtime-{runtime_id}-windows-x64.zip"),
            ]:
                descriptor = components.get(kind)
                if (
                    not isinstance(descriptor, dict)
                    or descriptor.get("asset") != expected_name
                    or type(descriptor.get("size")) is not int
                    or not 0 < descriptor["size"] <= MAX_PACKAGE
                    or not re.fullmatch("[0-9a-f]{64}", str(descriptor.get("sha256")))
                ):
                    raise ValueError("组件更新清单无效")
                self.component_asset(release, descriptor)
        if "installer" in meta:
            descriptor = meta["installer"]
            if (
                not isinstance(descriptor, dict)
                or descriptor.get("asset")
                != f"{ASSET_PREFIX}-{meta['version']}-windows-x64-setup.exe"
                or type(descriptor.get("size")) is not int
                or not 0 < descriptor["size"] <= MAX_PACKAGE
                or not re.fullmatch("[0-9a-f]{64}", str(descriptor.get("sha256")))
            ):
                raise ValueError("安装程序清单无效")
            self.component_asset(release, descriptor)
        return meta, package

    def component_asset(self, release, descriptor):
        asset = self._asset(release, descriptor["asset"])
        if asset.get("size") != descriptor["size"] or (
            asset.get("digest") and asset["digest"] != "sha256:" + descriptor["sha256"]
        ):
            raise ValueError("组件大小或摘要与 GitHub 不一致")
        return asset

    def download(self, asset, meta, path, progress=lambda _: None):
        path = Path(path)
        # A failed installation/retry must not redownload an already verified ZIP.
        if path.is_file() and path.stat().st_size == meta["size"]:
            if sha256(path.read_bytes()) == meta["sha256"]:
                progress(1)
                return
        temporary = path.with_suffix(path.suffix + ".part")
        digest = hashlib.sha256()
        size = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                self._open(
                    asset["browser_download_url"], {"Accept": "application/octet-stream"}
                ) as response,
                temporary.open("wb") as out,
            ):
                while chunk := response.read(256 * 1024):
                    size += len(chunk)
                    if size > meta["size"]:
                        raise ValueError("下载超过声明大小")
                    digest.update(chunk)
                    out.write(chunk)
                    progress(size / meta["size"])
            if size != meta["size"] or digest.hexdigest() != meta["sha256"]:
                raise ValueError("下载不完整或摘要校验失败")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
