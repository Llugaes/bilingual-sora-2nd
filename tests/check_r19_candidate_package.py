"""Audit one private r19 package and execute its real warm preparation path."""

import argparse
import ast
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import time
import zipfile

REPO = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def revision(root):
    from sora_bilingual.game.native_runtime import NativeLabels, native_revision

    parsed = ast.parse(textwrap.dedent(inspect.getsource(NativeLabels.attach)))
    assignment = next(
        n
        for n in ast.walk(parsed)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "source" for t in n.targets)
    )
    files = ast.literal_eval(assignment.value.args[0].generators[0].iter)
    return native_revision("\n".join((root / name).read_text("utf-8") for name in files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--revision-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    if args.revision_only:
        print(json.dumps({"root": str(root), "native_revision": revision(root)}))
        return
    receipt_path = root.parent / "packages/candidate-package.json"
    receipt = json.loads(receipt_path.read_text("utf-8"))
    manifest = json.loads((root / "dev-manifest.json").read_text("utf-8"))
    cache = json.loads((root / "candidate-cache.json").read_text("utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    assert head == manifest["source_head"] == receipt["source_head"] == cache["source_head"]
    package = Path(receipt["package"])
    assert digest(package) == receipt["package_sha256"]
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
    for name, sha in {**manifest["files"], **cache["files"]}.items():
        assert digest(root / name) == sha, name
    code = sorted(
        name
        for name in manifest["files"]
        if name.startswith("sora_bilingual/") and name.endswith((".py", ".js"))
    )
    for name in code:
        blob = subprocess.check_output(["git", "show", head + ":" + name], cwd=REPO)
        assert (root / name).read_bytes().replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n"), (
            name
        )
    from sora_bilingual.paths import ROOT, build_label
    from sora_bilingual.game.native_runtime import native_report
    from sora_bilingual.localization import native_catalog, model_wire, model_worker

    assert ROOT == root and build_label() == "DEV " + manifest["display_version"]
    assert digest(root / "sora_bilingual/game/scripts/runtime_text.js") == cache["renderer_sha256"]
    assert model_wire.wire_ready(root / "generated" / cache["model_name"])
    samples = json.loads((REPO / "generated/r19-tips-load-three-samples.json").read_text("utf-8"))
    positives = []
    for sample in samples:
        report = native_report(Path(sample["path"]))
        assert report["sha256"] == sample["sha256"] and "tips_table_load" in report["native"]
        positives.append(
            {
                "sha256": report["sha256"],
                "tips_table_load": report["native"]["tips_table_load"]["rva"],
            }
        )

    def cold(*_args, **_kwargs):
        raise AssertionError("Packaged warm path attempted cold catalogue/model/wire preparation")

    native_catalog.load_entries = native_catalog.load_model = native_catalog._load_model = cold
    model_wire.publish_indexed = model_wire.indexed_model = cold
    model = root / "generated" / cache["model_name"]
    wire = root / "generated" / cache["wire_name"]
    before = (model.stat().st_mtime_ns, wire.stat().st_mtime_ns, digest(wire))
    start = time.perf_counter()
    prepared = model_worker.prepare_request(
        {"game": str(Path(samples[0]["path"]).parent), "config": cache["config"]}
    )
    seconds = time.perf_counter() - start
    assert Path(prepared["path"]) == model
    assert before == (model.stat().st_mtime_ns, wire.stat().st_mtime_ns, digest(wire))
    assert before[2] == cache["wire_sha256"]
    record = {
        "source_head": head,
        "package_sha256": receipt["package_sha256"],
        "package_bytes": package.stat().st_size,
        "build_label": build_label(),
        "managed_files": len(manifest["files"]),
        "code_files_match_git": len(code),
        "cache_files_verified": len(cache["files"]),
        "compatible_facts": cache["compatible_language_facts"],
        "config": cache["config"],
        "warm_model_worker_seconds": seconds,
        "cold_catalogue_model_and_wire_generation_forbidden": True,
        "wire_bytes_and_mtime_unchanged": True,
        "wire_sha256": before[2],
        "native_revision": revision(root),
        "r18_resident_revision": "789ae56bd79a9cff6e73ae668dea6b8e14f458f980e1b021dc1505d79ebbe0c2",
        "native_exe_samples": positives,
        "candidate_live_verified": False,
        "game_attached": False,
        "copied_user_tokens_or_font_receipts": False,
    }
    record["native_revision_changed"] = record["native_revision"] != record["r18_resident_revision"]
    output = root.parent / "packages/candidate-final-verification.json"
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
