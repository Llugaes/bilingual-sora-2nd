"""Verify the exact r32 package and its unchanged native identity contracts."""

import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--language-follow", action="store_true")
    args = parser.parse_args()
    root, repo = args.root.resolve(), args.repo.resolve()
    sys.path.insert(0, str(root))
    receipt = json.loads((root.parent / "packages/candidate-package.json").read_text("utf8"))
    freeze = json.loads(
        (args.freeze or repo / "generated/r32-coverage-source-freeze.json").read_text("utf8")
    )
    manifest = json.loads((root / "dev-manifest.json").read_text("utf8"))
    cache = json.loads((root / "candidate-cache.json").read_text("utf8"))
    assert (
        receipt["source_snapshot_sha256"]
        == manifest["source_snapshot_sha256"]
        == freeze["snapshot_sha256"]
    )
    assert manifest["source_dirty"] is True
    if args.language_follow:
        assert manifest["experimental_primary"].startswith("default off;")
        assert cache["config"]["experimental_primary"] is False
        assert cache["config"]["primary"] == cache["config"]["game_language"]
        assert cache["config"]["secondary"] != cache["config"]["primary"]
    else:
        assert manifest["normal_languages"] == ["en", "ja", "zh-Hans", "zh-Hant"]
    package = Path(receipt["package"])
    assert sha(package.read_bytes()) == receipt["package_sha256"]
    with zipfile.ZipFile(package) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for name, digest in {**manifest["files"], **cache["files"]}.items():
            assert sha(archive.read(name)) == digest, name
            assert sha((root / name).read_bytes()) == digest, name
        assert not any(
            "item_help_identity.py" in name or "item_help_contract_data.py" in name
            for name in archive.namelist()
        )
    code = [name for name in freeze["files"] if name.endswith((".py", ".js"))]
    for name in code:
        assert sha((root / name).read_bytes()) == freeze["files"][name], name
    with zipfile.ZipFile(
        repo
        / "dist/comprehensive-1.0.0-dev5-r25/packages/bilingual-sora-2nd-1.0.0-dev5-r25-windows-x64.zip"
    ) as old:
        for name in (
            "sora_bilingual/game/scripts/runtime_identity.js",
            "sora_bilingual/game/native_contract_data.py",
        ):
            assert (root / name).read_bytes() == old.read(name), name
    from sora_bilingual.game.native_runtime import NativeLabels, native_revision

    parsed = ast.parse(textwrap.dedent(inspect.getsource(NativeLabels.attach)))
    assignment = next(
        n
        for n in ast.walk(parsed)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "source" for t in n.targets)
    )
    files = ast.literal_eval(assignment.value.args[0].generators[0].iter)
    revision = native_revision("\n".join((root / name).read_text("utf8") for name in files))
    from sora_bilingual.localization import native_catalog, model_wire, model_worker
    from sora_bilingual.paths import ROOT, build_label

    assert ROOT == root
    assert build_label() == "DEV " + manifest["display_version"]

    def cold(*args, **kwargs):
        raise AssertionError("packaged warm entry attempted cold catalogue/model/wire compilation")

    native_catalog.load_entries = native_catalog.load_model = native_catalog._load_model = cold
    model_wire.publish_indexed = model_wire.indexed_model = cold
    warm_models = []
    for entry in cache["config_matrix"]:
        wire = root / "generated" / entry["wire_name"]
        before = (wire.stat().st_mtime_ns, sha(wire.read_bytes()))
        prepared = model_worker.prepare_request(
            {
                "game": r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter",
                "config": entry["config"],
            }
        )
        assert Path(prepared["path"]) == root / "generated" / entry["model_name"]
        assert before == (wire.stat().st_mtime_ns, sha(wire.read_bytes()))
        assert before[1] == entry["wire_sha256"]
        warm_models.append({"config": entry["config"], "wire_sha256": before[1]})
    result = {
        "package_sha256": receipt["package_sha256"],
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "managed_files_verified": len(manifest["files"]),
        "cache_files_verified": len(cache["files"]),
        "source_code_files_match_frozen_bytes": len(code),
        "native_identity_and_contract_files_exact_r25": True,
        "native_agent_matches_frozen_bytes": True,
        "build_label": build_label(),
        "native_revision": revision,
        "warm_entry_without_cold_compile": True,
        "warm_models": warm_models,
        "wire_bytes_and_mtime_unchanged": True,
        "actual_attach_called": False,
        "game_attached": False,
        "deployed": False,
    }
    (args.out or repo / "generated/r26-p0-local-package-audit.json").write_text(
        json.dumps(result, indent=2), "utf8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
