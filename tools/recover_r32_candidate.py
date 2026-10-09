"""Finish verified ZIP extraction on an independent volume after staging ran out of space."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.model_wire import prepare_wire


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists(), "output must be a fresh isolated directory"
    source = (
        ROOT
        / "dist/comprehensive-1.0.0-dev5-r32-coverage-local2/packages/bilingual-sora-2nd-1.0.0-dev5-r32-windows-x64.zip"
    )
    sha = lambda data: hashlib.sha256(data).hexdigest()
    freeze = json.loads((ROOT / "generated/r32-coverage-source-freeze.json").read_text("utf8"))
    with zipfile.ZipFile(source) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        manifest = json.loads(archive.read("dev-manifest.json"))
        cache = json.loads(archive.read("candidate-cache.json"))
        assert (
            manifest["source_snapshot_sha256"]
            == cache["source_snapshot_sha256"]
            == freeze["snapshot_sha256"]
        )
        assert manifest["source_files"] == freeze["files"]
        for name, digest in {**manifest["files"], **cache["files"]}.items():
            assert sha(archive.read(name)) == digest, name
        output.mkdir(parents=True)
        packages = output / "packages"
        packages.mkdir()
        package = packages / source.name
        shutil.copy2(source, package)
        assert sha(package.read_bytes()) == sha(source.read_bytes())
        destination = output / "DEV"
        destination.mkdir()
        archive.extractall(destination)
    matrix = json.loads((ROOT / "generated/r32-coverage-matrix-receipt.json").read_text("utf8"))
    for receipt in matrix:
        original = Path(receipt["model_path"])
        model = destination / "generated" / original.name
        shutil.copystat(original, model)
        prepare_wire(model)
    for name, digest in {**manifest["files"], **cache["files"]}.items():
        assert sha((destination / name).read_bytes()) == digest, name
    for name, digest in freeze["files"].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    result = {
        "root": str(destination),
        "package": str(package),
        "package_sha256": sha(package.read_bytes()),
        "package_bytes": package.stat().st_size,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "wire_sha256": cache["wire_sha256"],
        "wire_matrix": cache["config_matrix"],
        "managed_files": len(manifest["files"]),
        "cache_files": len(cache["files"]),
        "source_dirty": True,
        "game_attached": False,
        "deployed": False,
        "published": False,
        "recovered_from_complete_verified_zip": str(source),
        "original_extraction_error": "OSError Errno 28; C volume full; partial DEV and disposable build-components removed",
        "protected_baseline_and_prior_candidates_preserved": True,
    }
    (packages / "candidate-package.json").write_text(json.dumps(result, indent=2), "utf8")
    (ROOT / "generated/r32-final-candidate-extraction.json").write_text(
        json.dumps(result, indent=2), "utf8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
