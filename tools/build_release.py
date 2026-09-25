"""Build only redistributable source assets, never game resources or local state."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import re
import tomllib
from sora_bilingual.updates.tool_updates import GROUPS
from sora_bilingual.updates.github_updates import version_tuple, repository_name
from sora_bilingual.updates.update_installer import validate_manifest

from sora_bilingual.paths import ROOT

# Explicit allowlist: adding files to the workspace cannot publish them.
FILES = json.loads((ROOT / "release-files.json").read_text("utf-8"))


def build(version, repository, output, root=ROOT):
    version = ".".join(map(str, version_tuple(version)))
    repository_name(repository)
    contents = {name: (root / name).read_bytes() for name in FILES}
    project = tomllib.loads(contents["pyproject.toml"].decode("utf-8"))["project"]
    distribution = json.loads(contents["distribution.json"])
    if project["version"] != distribution["version"]:
        raise ValueError("pyproject.toml 与 distribution.json 版本不一致")
    contents["pyproject.toml"] = re.sub(
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
        contents["pyproject.toml"].decode("utf-8"),
    ).encode("utf-8")
    contents["distribution.json"] = json.dumps(
        {"schema": 1, "version": version, "repository": repository, "platform": "windows-x64"},
        indent=2,
    ).encode()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    groups = {k: sha(b"".join(contents[n] for n in names)) for k, names in GROUPS.items()}
    hot = {"groups": groups, "version": sha(json.dumps(groups, sort_keys=True).encode())[:16]}
    manifest = {
        "schema": 1,
        "application": "sora-bilingual",
        "version": version,
        "repository": repository,
        "python": [3, 14],
        "requirements_sha256": sha(contents["requirements.txt"]),
        "files": {name: sha(data) for name, data in contents.items()},
        "hot_release": hot,
    }
    validate_manifest(manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    name = f"sora-bilingual-{version}-windows-x64.zip"
    package = output / name
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for key, data in sorted(contents.items()):
            archive.writestr(key, data)
        archive.writestr(
            "installed-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
    meta = {
        "schema": 1,
        "application": "sora-bilingual",
        "platform": "windows-x64",
        "version": version,
        "repository": repository,
        "asset": name,
        "sha256": sha(package.read_bytes()),
        "size": package.stat().st_size,
    }
    (output / "sora-bilingual-update.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return package, meta


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--output", default="dist")
    a = p.parse_args()
    path, meta = build(a.version, a.repository, a.output)
    print(json.dumps(meta, indent=2))
