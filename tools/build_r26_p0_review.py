"""Build a private review snapshot while preserving the user's staged index."""

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


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="r26-p0-local")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/comprehensive-1.0.0-dev5-r26-p0-local3"
    )
    parser.add_argument("--display-version", default="1.0.0-dev5-r27")
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(ROOT / "dist")
    if output.exists():
        raise ValueError("review candidate must use a new independent directory")
    freeze = json.loads(
        (ROOT / ("generated/" + args.prefix + "-source-freeze.json")).read_text("utf8")
    )
    for name, digest in freeze["files"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    r25 = (
        ROOT
        / "dist/comprehensive-1.0.0-dev5-r25/packages/bilingual-sora-2nd-1.0.0-dev5-r25-windows-x64.zip"
    )
    extra = {}
    with zipfile.ZipFile(r25) as archive:
        original = json.loads(archive.read("dev-manifest.json"))
        for name, digest in original["files"].items():
            if name == "BilingualSora2nd.exe" or name.startswith("runtime/"):
                data = archive.read(name)
                assert sha(data) == digest, name
                extra[name] = data
    runtime_id = original["runtime_id"]
    runtime_digest = sha(
        json.dumps({n: sha(v) for n, v in sorted(extra.items())}, sort_keys=True).encode()
    )
    assert (
        len(extra) == 552
        and runtime_digest == "abf98b97e7ae210ea8f930cb7727caca4e7aaa0cfb8987e9b3b227d1e09d2f55"
    )
    files, cache = compiled_cache(
        ROOT / ("generated/" + args.prefix + "-production-receipt.json"),
        Path(r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter"),
    )
    distribution = json.loads((ROOT / "distribution.json").read_text("utf8"))
    package, _ = build(
        distribution["version"],
        distribution["repository"],
        output / "build-components",
        extra=extra,
        runtime_id=runtime_id,
    )
    with zipfile.ZipFile(package) as archive:
        installed = json.loads(archive.read("installed-manifest.json"))
    display = args.display_version
    manifest = {
        **installed,
        "display_version": display,
        "source_head": freeze["source_head"],
        "source_dirty": True,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "source_files": freeze["files"],
        "staged_diff_sha256": freeze["staged_diff_sha256"],
        "validation": "local review candidate; r26 gameplay rejection and r27 real English first-line failure preserved; this changed candidate has no real-machine acceptance",
        "unresolved": [
            "dynamic style setter/current save rank not captured",
            "gameplay performance not verified",
            "pre-existing Node complete-effect semantic-layer test failure retained",
            "Python translate(annotation) differs from render(annotation) with Tools disabled",
            "Python full suite: 776 run, 4 failures/7 errors/9 skipped initially; affected 11 rechecked: 2 failures/6 errors remain, also reproduced before producer changes; no full-suite green claim",
        ],
        "broad_python_recheck": json.loads(
            (ROOT / "generated/r26-p0-local-broad-after-retirement.json").read_text("utf8")
        ),
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
    final = packages / f"bilingual-sora-2nd-{display}-windows-x64.zip"
    package.rename(final)
    destination = output / "DEV"
    destination.mkdir()
    with zipfile.ZipFile(final) as archive:
        assert archive.testzip() is None
        archive.extractall(destination)
    from sora_bilingual.localization.model_wire import prepare_wire

    # The stamp proves this model's exact mtime as well as its bytes. Preserve
    # that real source metadata locally; do not rewrite checksum expectations.
    # An independent future ZIP extraction may serialize the wire once.
    model_name = "generated/" + cache["model_name"]
    shutil.copystat(files[model_name], destination / model_name)
    prepare_wire(destination / "generated" / cache["model_name"])
    for name, digest in {**installed["files"], **cache["files"]}.items():
        assert sha((destination / name).read_bytes()) == digest, name
    result = {
        "root": str(destination),
        "package": str(final),
        "package_sha256": sha(final.read_bytes()),
        "package_bytes": final.stat().st_size,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "wire_sha256": cache["wire_sha256"],
        "display_version": display,
        "managed_files": len(installed["files"]),
        "cache_files": len(cache["files"]),
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
    # These files were created only by this invocation inside its new output.
    disposable = (output / "build-components").resolve()
    assert disposable.is_relative_to(output.resolve()) and disposable.name == "build-components"
    shutil.rmtree(disposable)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
