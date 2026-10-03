"""Relay verified GitHub releases through this machine without rebuilding them.

Run once, or invoke periodically from a local scheduler. No game/runtime process
or player configuration is touched. Credentials belong only to the publisher.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re

from sora_bilingual.updates.github_updates import GitHubClient
from sora_bilingual.updates.release_client import ASSET_MANIFEST, version_tuple
from tools.publish_gitee import GiteePublisher, manifest_files, validated_files


@contextmanager
def exclusive_directory(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "relay.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Closing the descriptor releases the OS lock, even after termination.
        yield


def remote_receipt(publisher, tag):
    release = publisher.request("/tags/" + tag)
    if not release or release.get("prerelease") is not False:
        return None
    assets = publisher.attachments(release["id"])
    return {
        "release": release["id"],
        "assets": sorted([[a["id"], a["name"], a["size"]] for a in assets], key=lambda a: a[1]),
    }


def relay(source, directory, *, tag=None, publisher=None):
    """Download-only when publisher is None; retry reuses verified local files."""
    directory = Path(directory)
    with exclusive_directory(directory):
        if tag:
            version_tuple(tag)
            release = source._json(
                f"https://api.github.com/repos/{source.repository}/releases/tags/{tag}"
            )
        else:
            release, _ = source.latest()
        if (
            not isinstance(release, dict)
            or release.get("draft") is not False
            or release.get("prerelease") is not False
        ):
            raise ValueError("Only a published GitHub stable release can be relayed")
        version_tuple(release.get("tag_name"))
        if tag and release["tag_name"] != tag:
            raise ValueError("GitHub returned a different tag")
        tag = release["tag_name"]
        manifest = source._asset(release, ASSET_MANIFEST)
        digest = manifest.get("digest", "")
        if (
            not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            or type(manifest.get("size")) is not int
            or not 0 < manifest["size"] <= 1024 * 1024
        ):
            raise ValueError("GitHub must attest the original manifest size and SHA-256")
        receipt_path = directory / "verified.json"
        identity = {
            "repository": source.repository,
            "tag": tag,
            "release": release["id"],
            "manifest": digest,
            "assets": sorted(
                [[a["id"], a["name"], a["size"], a.get("digest")] for a in release["assets"]],
                key=lambda a: a[1],
            ),
        }
        try:
            receipt = json.loads(receipt_path.read_bytes())
        except OSError, ValueError:
            receipt = {}
        if publisher and receipt.get("source") == identity:
            remote = remote_receipt(publisher, tag)
            if remote is not None and receipt.get("destination") == remote:
                print(f"Already verified on Gitee: {tag}; no packages transferred", flush=True)
                return tag
        # One cache directory also reuses the unchanged runtime between versions.
        packages = directory / "packages"
        source.download(
            manifest,
            {"size": manifest["size"], "sha256": digest.removeprefix("sha256:")},
            packages / ASSET_MANIFEST,
        )
        _, files = manifest_files(tag, source.repository, (packages / ASSET_MANIFEST).read_bytes())
        assets = {name: source.component_asset(release, desc) for name, desc in files.items()}
        # Reject every malformed descriptor/asset before downloading large files.
        for name, descriptor in files.items():
            print("Checking/downloading original GitHub asset: " + name, flush=True)
            source.download(assets[name], descriptor, packages / name)
        validated_files(tag, source.repository, packages)
        print(f"Original GitHub files verified: {tag}", flush=True)
        if publisher:
            publisher.publish(tag, packages)
            remote = remote_receipt(publisher, tag)
            if remote is None:
                raise ValueError("Stable mirror confirmation disappeared")
            temporary = receipt_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"source": identity, "destination": remote}, indent=2), encoding="utf-8"
            )
            temporary.replace(receipt_path)
            # Only prune recognized previous app/setup files in our private cache.
            # Unchanged runtime stays cached; unknown files are never removed.
            for path in packages.iterdir():
                if path.name not in files and re.fullmatch(
                    r"bilingual-sora-2nd-(?:\d+\.\d+\.\d+-(?:app-windows-x64\.zip|"
                    r"windows-x64-setup\.exe)|runtime-[a-f0-9]{16}-windows-x64\.zip)",
                    path.name,
                ):
                    path.unlink()
        return tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--directory", type=Path, default=Path(".local/gitee-relay"))
    parser.add_argument("--tag", help="Default: latest public stable GitHub release")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    try:
        source = GitHubClient(args.repository)
        publisher = (
            None
            if args.download_only
            else GiteePublisher(args.repository, os.environ.get("GITEE_RELEASE_TOKEN"))
        )
        relay(source, args.directory, tag=args.tag, publisher=publisher)
    except Exception as exc:
        # Never print HTTP URLs or bodies: publishing requests can carry tokens.
        print(
            f"Relay failed: {type(exc).__name__}; retry with the same cache directory", flush=True
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
