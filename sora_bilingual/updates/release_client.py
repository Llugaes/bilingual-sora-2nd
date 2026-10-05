"""Shared release schema, verified downloads and provider-scoped HTTPS transport."""

import hashlib
import json
from pathlib import Path
import re
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


def stable_releases(releases):
    """Normalize discovery without admitting previews or arbitrary tags."""
    if not isinstance(releases, list):
        raise ValueError("发行列表无效")
    result = {}
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        try:
            version = version_tuple(release.get("tag_name"))
        except ValueError:
            continue
        result.setdefault(version, release)
    return [result[v] for v in sorted(result, reverse=True)]


def repository_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("尚未配置有效的 GitHub 发布仓库")
    if any(v in (".", "..") for v in value.split("/")):
        raise ValueError("无效仓库")
    return value


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def metadata_identity(meta):
    """Pin the complete validated metadata across confirmation/provider refresh."""
    return sha256(json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8"))


GITHUB_HOSTS = (
    "api.github.com",
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)
GITEE_HOSTS = ("gitee.com", "foruda.gitee.com")


def allowed_url(url, hosts=GITHUB_HOSTS):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname not in hosts
    ):
        raise ValueError("更新下载地址不属于配置的 HTTPS 来源")
    return url


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ReleaseClient:
    host = "github.com"
    hosts = GITHUB_HOSTS
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION}
    component_only = False

    def history(self):
        releases = []
        for page in range(1, 11):
            rows = self._json(self.releases_url + f"?direction=desc&per_page=100&page={page}")
            if not isinstance(rows, list):
                raise ValueError("发行列表无效")
            releases.extend(rows)
            if len(rows) < 100:
                return stable_releases(releases)
        raise ValueError("发行列表超过上限，请从发行页面选择版本")

    def release(self, tag):
        version_tuple(tag)
        release = self._json(self.releases_url + "/tags/" + tag)
        if not stable_releases([release]) or release["tag_name"] != tag:
            raise ValueError("所选版本不是公开稳定版")
        return release

    def __init__(self, repository, opener=None):
        self.repository = repository_name(repository)
        self.opener = opener or urllib.request.build_opener(ReleaseRedirect(self.hosts))

    def _open(self, url, headers=None):
        request = urllib.request.Request(
            allowed_url(url, self.hosts),
            headers={"User-Agent": "Sora-Bilingual-Updater/1", **self.headers, **(headers or {})},
        )
        return self.opener.open(request, timeout=20)

    def _json(self, url):
        with self._open(url) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("版本信息超过大小限制")
        return json.loads(raw)

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
        prefix = f"https://{self.host}/{self.repository}/releases/download/"
        if not url.startswith(prefix):
            raise ValueError("更新资源不属于配置的仓库")
        allowed_url(url, self.hosts)
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
        return self._metadata(raw, release, modern)

    def _metadata(self, raw, release, modern):
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
        if type(meta.get("size")) is not int or not 0 < meta["size"] <= MAX_PACKAGE:
            raise ValueError("更新包大小不合法")
        if not re.fullmatch("[0-9a-f]{64}", str(meta.get("sha256"))):
            raise ValueError("更新包没有有效摘要")
        prefix = ASSET_PREFIX if modern else LEGACY_PREFIX
        expected = f"{prefix}-{meta['version']}-windows-x64.zip"
        if meta.get("asset") != expected:
            raise ValueError("更新文件名不匹配")
        has_package = any(a.get("name") == expected for a in release.get("assets", []))
        package = (
            None
            if self.component_only and "components" in meta and not has_package
            else self._asset(release, expected)
        )
        if package and package.get("size") != meta["size"]:
            raise ValueError("发行附件与清单中的包大小不一致")
        if package and package.get("digest") and package["digest"] != "sha256:" + meta["sha256"]:
            raise ValueError("发行附件与清单中的摘要不一致")
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
            raise ValueError("组件大小或摘要与发行附件不一致")
        return asset

    def download(self, asset, meta, path, progress=lambda _: None):
        path = Path(path)
        # A failed installation/retry must not redownload an already verified ZIP.
        if path.is_file() and path.stat().st_size == meta["size"]:
            if file_sha256(path) == meta["sha256"]:
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


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
