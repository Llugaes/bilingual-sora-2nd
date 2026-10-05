"""Prepare a local stable index after artifact validation; never publish it here."""

import argparse
import json
from pathlib import Path

from sora_bilingual.updates.release_client import ASSET_MANIFEST, sha256, version_tuple
from sora_bilingual.updates.static_gitee_updates import MAX_HISTORY, parse_index
from sora_bilingual.updates.update_installer import atomic_bytes
from tools.publish_gitee import validated_files


def prepare(repository, directory, previous=None):
    directory = Path(directory)
    raw = (directory / ASSET_MANIFEST).read_bytes()
    version = json.loads(raw)["version"]
    validated_files("v" + version, repository, directory)
    entry = {
        "version": version,
        "tag": "v" + version,
        "manifest": {"asset": ASSET_MANIFEST, "size": len(raw), "sha256": sha256(raw)},
    }
    old = parse_index(previous, repository) if previous is not None else None
    entries = {item["version"]: item for item in old["releases"]} if old else {}
    if old and (
        version_tuple(version) < version_tuple(old["latest"])
        or (version in entries and entries[version] != entry)
    ):
        raise ValueError("拒绝回退索引或改写同版本清单摘要")
    entries[version] = entry
    index = {
        "schema": 1,
        "application": "sora-bilingual",
        "repository": repository,
        "platform": "windows-x64",
        "channel": "stable",
        "latest": version,
        "releases": sorted(
            entries.values(), key=lambda item: version_tuple(item["version"]), reverse=True
        )[:MAX_HISTORY],
    }
    result = json.dumps(index, indent=2).encode("utf-8")
    parse_index(result, repository)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(
        args.repository, args.directory, args.previous.read_bytes() if args.previous else None
    )
    atomic_bytes(args.output, result)
    print(f"Prepared local index: {args.output}; public assets and branch are NOT changed")


if __name__ == "__main__":
    main()
