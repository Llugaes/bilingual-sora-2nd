"""Seal an isolated dirty-source r32 candidate with five verified warm models."""

import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/comprehensive-1.0.0-dev5-r32-coverage-local1"
    )
    parser.add_argument(
        "--compiler-cache",
        type=Path,
        help="Exact isolated compiler directory; all receipt and checksum gates still apply",
    )
    args = parser.parse_args()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    prefix = "r32-coverage"
    output = args.output.resolve()
    if output.exists():
        raise ValueError("candidate must use a new isolated directory")
    freeze = json.loads((ROOT / f"generated/{prefix}-source-freeze.json").read_text("utf8"))

    def verify_source():
        for name, digest in freeze["files"].items():
            assert sha((ROOT / name).read_bytes()) == digest, name

    verify_source()
    matrix = json.loads((ROOT / f"generated/{prefix}-matrix-receipt.json").read_text("utf8"))
    files = {}
    caches = []
    for receipt in matrix:
        seeded, cache = compiled_cache(
            ROOT / f"generated/{prefix}-{receipt['label']}-production-receipt.json",
            Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter"),
            cache_root=args.compiler_cache,
        )
        for name, path in seeded.items():
            if name in files:
                assert sha(files[name].read_bytes()) == sha(path.read_bytes()), name
            files[name] = path
        caches.append(cache)
    cache = {
        **caches[0],
        "files": {name: sha(path.read_bytes()) for name, path in files.items()},
        "config_matrix": [
            {k: c[k] for k in ("config", "model_name", "wire_name", "wire_sha256")} for c in caches
        ],
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "source_dirty": True,
        "source_head": freeze["source_head"],
    }
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
    distribution = json.loads((ROOT / "distribution.json").read_text("utf8"))
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
        "display_version": "1.0.0-dev5-r32",
        "source_head": freeze["source_head"],
        "source_dirty": True,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "source_files": freeze["files"],
        "staged_diff_sha256": freeze["staged_diff_sha256"],
        "validation": "independent candidate; exact complete producers and callbacks verified offline; real-game receipt separate",
        "normal_languages": ["en", "ja", "zh-Hans", "zh-Hant"],
        "experimental_primary": "default off; when enabled, manual primary persists through game source changes",
        "unresolved": [
            "actual game text/geometry/performance validation remains separate from offline checks",
            "other four source languages are outside current four-source acceptance; prior failure evidence retained",
            "normal English annotation retains native source punctuation frame; all fields separately audited",
        ],
    }
    with zipfile.ZipFile(package, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dev-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("candidate-cache.json", json.dumps(cache, ensure_ascii=False, indent=2))
        archive.writestr("generated/development-version.txt", distribution["version"] + "\n")
        for name, path in files.items():
            archive.write(path, name)
    packages = output / "packages"
    packages.mkdir()
    final = packages / "bilingual-sora-2nd-1.0.0-dev5-r32-windows-x64.zip"
    package.rename(final)
    destination = output / "DEV"
    destination.mkdir()
    with zipfile.ZipFile(final) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        archive.extractall(destination)
    from sora_bilingual.localization.model_wire import prepare_wire

    for seeded in caches:
        name = "generated/" + seeded["model_name"]
        shutil.copystat(files[name], destination / name)
        prepare_wire(destination / name)
    for name, digest in {**installed["files"], **cache["files"]}.items():
        assert sha((destination / name).read_bytes()) == digest, name
    verify_source()
    result = {
        "root": str(destination),
        "package": str(final),
        "package_sha256": sha(final.read_bytes()),
        "package_bytes": final.stat().st_size,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "wire_sha256": cache["wire_sha256"],
        "wire_matrix": cache["config_matrix"],
        "managed_files": len(installed["files"]),
        "cache_files": len(files),
        "runtime_files": len(extra),
        "runtime_sha256": runtime_digest,
        "source_dirty": True,
        "user_index_preserved": True,
        "copied_user_state": False,
        "game_attached": False,
        "deployed": False,
        "published": False,
    }
    (packages / "candidate-package.json").write_text(json.dumps(result, indent=2), "utf8")
    disposable = (output / "build-components").resolve()
    assert disposable.is_relative_to(output.resolve()) and disposable.name == "build-components"
    shutil.rmtree(disposable)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
