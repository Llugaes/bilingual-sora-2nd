"""Mirror original GitHub artifacts; expose stable releases only after verification."""

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from sora_bilingual.updates.gitee_updates import GiteeClient
from sora_bilingual.updates.release_client import (
    ASSET_MANIFEST,
    ASSET_PREFIX,
    file_sha256,
    repository_name,
    version_tuple,
)

MAX_ATTACHMENT = 100 * 1024 * 1024
MAX_REPOSITORY = 1024 * 1024 * 1024
MARKER = "<!-- sora-bilingual-mirror:1 -->"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Refusing to redirect a publishing credential")


class GiteePublisher:
    def __init__(self, repository, token):
        if not token:
            raise ValueError("GITEE_RELEASE_TOKEN is required")
        self.repository = repository_name(repository)
        self.token = token
        self.base = f"https://gitee.com/api/v5/repos/{self.repository}/releases"
        self.opener = urllib.request.build_opener(NoRedirect())
        self.reader = GiteeClient(repository)

    def request(self, suffix="", *, method="GET", fields=None, file=None):
        data = None
        headers = {"User-Agent": "Sora-Bilingual-Release/1", "Accept": "application/json"}
        if method != "GET":
            fields = {**(fields or {}), "access_token": self.token}
            if method == "DELETE":
                # The documented DELETE contract requires a query parameter.
                # Error reporting below deliberately never includes request URLs.
                suffix += "?" + urllib.parse.urlencode(fields)
            elif file:
                boundary = uuid.uuid4().hex
                parts = []
                for name, value in fields.items():
                    parts.append(
                        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
                    )
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                )
                prefix = b"".join(parts)
                suffix_bytes = f"\r\n--{boundary}--\r\n".encode()
                headers["Content-Length"] = str(
                    len(prefix) + file.stat().st_size + len(suffix_bytes)
                )
                data = multipart_stream(file, prefix, suffix_bytes)
                headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
            else:
                data = urllib.parse.urlencode(fields).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            self.base + suffix, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("Oversized publisher response")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 404 and method == "GET" and suffix.startswith("/tags/"):
                return None
            # Never include a credential, signed URL or server-reflected request.
            raise RuntimeError(f"Gitee {method} failed: HTTP {code}") from None

    def attachments(self, release_id):
        result = self.request(f"/{release_id}/attach_files?per_page=100")
        if not isinstance(result, list) or len(result) >= 100:
            raise ValueError("Incomplete attachment inventory")
        return result

    def releases(self):
        result = []
        for page in range(1, 11):
            batch = self.request(f"?direction=desc&per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ValueError("Invalid release inventory")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise ValueError("Release inventory exceeds safety bound")

    def publish(self, tag, directory):
        directory = Path(directory)
        meta, files = validated_files(tag, self.repository, directory)
        release = self.request("/tags/" + tag)
        existing = self.attachments(release["id"]) if release else []
        names = {a["name"] for a in existing}
        missing = [name for name in files if name not in names]
        if release and not release.get("prerelease") and missing:
            raise ValueError("Refusing to mutate an incomplete stable mirror")
        occupied = sum(a["size"] for r in self.releases() for a in self.attachments(r["id"]))
        if occupied + sum(files[name]["size"] for name in missing) > MAX_REPOSITORY:
            raise ValueError("Gitee 1 GiB quota would be exceeded; existing releases are unchanged")
        fields = {
            "tag_name": tag,
            "name": f"Bilingual Sora 2nd {tag}",
            "body": (
                f"{MARKER}\n\nGitHub 正式发行版的原始附件镜像，大小及 SHA-256 已校验。\n\n"
                f"[版本说明与完整便携包](https://github.com/{self.repository}/releases/tag/{tag})\n\n"
                "首次使用请下载 setup.exe；app 和 runtime ZIP 是工具自动更新使用的组件。"
            ),
        }
        if release is None:
            # The mirror repository stores release records, not a second source tree.
            release = self.request(
                method="POST", fields={**fields, "target_commitish": "master", "prerelease": "true"}
            )
        release_id = release["id"]
        for name in missing:  # manifest is inserted last
            print("Uploading " + name, flush=True)
            self.request(f"/{release_id}/attach_files", method="POST", file=directory / name)
        uploaded = self.attachments(release_id)
        by_name = {}
        for item in uploaded:
            if item["name"] in by_name:
                raise ValueError("Duplicate remote attachment")
            by_name[item["name"]] = item
        with tempfile.TemporaryDirectory(prefix="gitee-verify-") as verify:
            for name, descriptor in files.items():
                asset = by_name.get(name)
                if not asset or asset.get("size") != descriptor["size"]:
                    raise ValueError("Remote attachment size mismatch: " + name)
                # Enforce the repository path before following any redirect.
                checked = self.reader._asset({"assets": [{**asset, "state": "uploaded"}]}, name)
                self.reader.download(checked, descriptor, Path(verify) / name)
                print("Anonymous SHA-256 verified: " + name, flush=True)
        if release.get("prerelease"):
            promoted = self.request(
                f"/{release_id}", method="PATCH", fields={**fields, "prerelease": "false"}
            )
            if promoted.get("prerelease") is not False:
                raise ValueError("Stable promotion was not confirmed")
        self.prune()
        print(
            f"Verified stable mirror: https://gitee.com/{self.repository}/releases/tag/{tag}",
            flush=True,
        )
        return meta

    def prune(self):
        managed = []
        for release in self.releases():
            if release.get("prerelease") or MARKER not in release.get("body", ""):
                continue
            try:
                version = version_tuple(release["tag_name"])
            except ValueError:
                continue
            managed.append((version, release))
        # Only our managed stable mirrors are eligible. Preview failures and
        # unrelated/manual releases are retained for diagnosis, never swept.
        for _, release in sorted(managed, key=lambda pair: pair[0], reverse=True)[3:]:
            self.request(f"/{release['id']}", method="DELETE")
            print("Removed old Gitee mirror: " + release["tag_name"], flush=True)


def multipart_stream(path, prefix, suffix, *, clock=time.monotonic):
    # A single SSL sendall for ~100 MB applies its timeout to the entire body.
    # Send bounded pieces with Content-Length, without chunked transfer encoding.
    started = clock()
    yield prefix
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if clock() - started > 600:
                raise TimeoutError("Gitee upload exceeded ten minutes")
            yield chunk
            count += len(chunk)
            if count % (16 * 1024 * 1024) == 0:
                print(f"Upload sent {count // (1024 * 1024)} MiB: {path.name}", flush=True)
    yield suffix


def validated_files(tag, repository, directory):
    version = ".".join(map(str, version_tuple(tag)))
    raw = (directory / ASSET_MANIFEST).read_bytes()
    meta = json.loads(raw)
    if any(
        meta.get(k) != v
        for k, v in {
            "schema": 1,
            "application": "sora-bilingual",
            "platform": "windows-x64",
            "repository": repository,
            "version": version,
        }.items()
    ):
        raise ValueError("Source manifest identity mismatch")
    components = meta.get("components", {})
    runtime_id = components.get("runtime_id", "")
    if components.get("schema") != 1 or not re.fullmatch(r"[a-f0-9]{16}", runtime_id):
        raise ValueError("A component release is required")
    files = {}
    for descriptor, expected in [
        (meta.get("installer", {}), f"{ASSET_PREFIX}-{version}-windows-x64-setup.exe"),
        (components.get("application", {}), f"{ASSET_PREFIX}-{version}-app-windows-x64.zip"),
        (components.get("runtime", {}), f"{ASSET_PREFIX}-runtime-{runtime_id}-windows-x64.zip"),
    ]:
        if (
            descriptor.get("asset") != expected
            or type(descriptor.get("size")) is not int
            or not 0 < descriptor["size"] <= MAX_ATTACHMENT
            or not re.fullmatch(r"[a-f0-9]{64}", str(descriptor.get("sha256")))
        ):
            raise ValueError("Invalid or oversized mirror component: " + expected)
        path = directory / expected
        if path.stat().st_size != descriptor["size"] or file_sha256(path) != descriptor["sha256"]:
            raise ValueError("Source artifact integrity failed: " + expected)
        files[expected] = descriptor
    files[ASSET_MANIFEST] = {"size": len(raw), "sha256": file_sha256(directory / ASSET_MANIFEST)}
    return meta, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        GiteePublisher(args.repository, os.environ.get("GITEE_RELEASE_TOKEN")).publish(
            args.tag, args.directory
        )
    except Exception as exc:
        # HTTP handling above deliberately avoids bodies and credential URLs.
        raise SystemExit(f"Mirror failed ({type(exc).__name__}): {exc}") from None


if __name__ == "__main__":
    main()
