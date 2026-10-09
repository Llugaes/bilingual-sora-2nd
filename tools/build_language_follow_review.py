"""Seal a private language-policy review snapshot without changing Git state."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_dev_candidate import compiled_cache
from tools.build_release import build


def main():
    sha = lambda data: hashlib.sha256(data).hexdigest()
    prefix = "r31-language-follow-after"
    output = ROOT / "dist/comprehensive-1.0.0-dev5-r31-language-follow-local1"
    if output.exists():
        raise ValueError("candidate requires a new independent output directory")
    freeze = json.loads((ROOT / f"generated/{prefix}-source-freeze.json").read_text("utf-8"))
    for name, digest in freeze["files"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    extra = {}
    baseline = (
        ROOT
        / "dist/comprehensive-1.0.0-dev5-r25/packages/bilingual-sora-2nd-1.0.0-dev5-r25-windows-x64.zip"
    )
    with zipfile.ZipFile(baseline) as archive:
        original = json.loads(archive.read("dev-manifest.json"))
        for name, digest in original["files"].items():
            if name == "BilingualSora2nd.exe" or name.startswith("runtime/"):
                data = archive.read(name)
                assert sha(data) == digest, name
                extra[name] = data
    runtime_digest = sha(
        json.dumps({n: sha(v) for n, v in sorted(extra.items())}, sort_keys=True).encode()
    )
    assert (
        len(extra) == 552
        and runtime_digest == "abf98b97e7ae210ea8f930cb7727caca4e7aaa0cfb8987e9b3b227d1e09d2f55"
    )
    files, cache = compiled_cache(
        ROOT / f"generated/{prefix}-production-receipt.json",
        Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter"),
    )
    distribution = json.loads((ROOT / "distribution.json").read_text("utf-8"))
    package, _ = build(
        distribution["version"],
        distribution["repository"],
        output / "build-components",
        extra=extra,
        runtime_id=original["runtime_id"],
    )
    with zipfile.ZipFile(package) as archive:
        installed = json.loads(archive.read("installed-manifest.json"))
    manifest = {
        **installed,
        "display_version": "1.0.0-dev5-r31",
        "source_head": freeze["source_head"],
        "source_dirty": True,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "source_files": freeze["files"],
        "staged_diff_sha256": freeze["staged_diff_sha256"],
        "language_follow": {
            "default_experimental_primary": False,
            "normal_primary": "confirmed game source",
            "collision": "swap",
            "third_source": "keep secondary",
            "offline_tests": 150,
        },
        "validation": "private review candidate; exact-source offline checks; real game validation remains separate",
        "unresolved": [
            "Experimental-on game source change semantics awaiting user answer; existing manual behavior retained provisionally",
            "four earlier notebook/item failure families remain open",
            "gameplay performance and full-game acceptance unverified",
        ],
    }
    cache.update(
        source_head=freeze["source_head"],
        source_dirty=True,
        source_snapshot_sha256=freeze["snapshot_sha256"],
    )
    with zipfile.ZipFile(package, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dev-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("candidate-cache.json", json.dumps(cache, ensure_ascii=False, indent=2))
        archive.writestr("generated/development-version.txt", distribution["version"] + "\n")
        for name, path in files.items():
            archive.write(path, name)
    packages = output / "packages"
    packages.mkdir()
    final = packages / "bilingual-sora-2nd-1.0.0-dev5-r31-windows-x64.zip"
    package.rename(final)
    destination = output / "DEV"
    destination.mkdir()
    with zipfile.ZipFile(final) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        archive.extractall(destination)
    from sora_bilingual.localization.model_wire import prepare_wire

    model_name = "generated/" + cache["model_name"]
    shutil.copystat(files[model_name], destination / model_name)
    prepare_wire(destination / model_name)
    for name, digest in {**installed["files"], **cache["files"]}.items():
        assert sha((destination / name).read_bytes()) == digest, name
    result = {
        "root": str(destination),
        "package": str(final),
        "package_sha256": sha(final.read_bytes()),
        "package_bytes": final.stat().st_size,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "wire_sha256": cache["wire_sha256"],
        "display_version": manifest["display_version"],
        "managed_files": len(installed["files"]),
        "cache_files": len(cache["files"]),
        "runtime_files": len(extra),
        "runtime_sha256": runtime_digest,
        "source_dirty": True,
        "copied_user_state": False,
        "game_attached": False,
        "deployed": False,
        "published": False,
    }
    (packages / "candidate-package.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
