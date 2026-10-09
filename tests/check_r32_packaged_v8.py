"""Receipt-verified explicit package wire replay in a self-created Frida V8 host.

Plan parity is separate from semantic admission. Normal EN's 674 intentional
strict frame differences remain in the receipt and are never called zero.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]
NATIVE = r"""
rpc.exports={
load(model){globalThis.tr=new RuntimeText(model);return {runtime:Script.runtime,retiredIdentityEmitted:!!model.item_help_identities};},
run(rows){let checks=0;const failures=[];
 for(const row of rows)for(const mode of ['primary','secondary','annotation']){
  const actual=tr.render(row.source,mode,'',''),expected=row.modes[mode];checks++;
  if(JSON.stringify(actual)!==JSON.stringify(expected))failures.push({name:row.name,mode,source:row.source,expected,actual});
 }
 return {checks,failures};
}};
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument(
        "--wire",
        type=Path,
        required=True,
        help="Explicit wire under this package/generated; never default to first cached config",
    )
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "generated/r32-coverage-source-freeze.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    product, wire = args.product.resolve(), args.wire.resolve()
    receipt = json.loads(args.receipt.read_text("utf8"))
    replay = json.loads(args.replay.read_text("utf8"))
    freeze = json.loads(args.freeze.read_text("utf8"))
    cache_path = product / "candidate-cache.json"
    cache = json.loads(cache_path.read_text("utf8"))
    assert wire.is_relative_to(product / "generated"), "wire must be inside actual package"
    selected = [row for row in cache["config_matrix"] if row["config"] == receipt["config"]]
    assert len(selected) == 1 and wire.name == selected[0]["wire_name"], (
        "explicit config/wire differs from package matrix"
    )
    assert (
        receipt["source_snapshot_sha256"]
        == cache["source_snapshot_sha256"]
        == freeze["snapshot_sha256"]
    )
    wire_sha = digest(wire)
    assert wire_sha == receipt["wire_sha256"] == replay["wire_sha256"] == selected[0]["wire_sha256"]
    assert replay["failure_count"] == 0, "Node baseline has parity failures"
    assert len(replay["rows"]) == 699, "complete physical producer denominator changed"
    package_model = product / "generated" / selected[0]["model_name"]
    assert digest(package_model) == receipt["model_sha256"]
    source_files, missing_or_changed = {}, []
    for name, expected in freeze["files"].items():
        source = product / name
        actual = digest(source) if source.is_file() else None
        source_files[name] = actual
        if actual != expected:
            missing_or_changed.append({"file": name, "expected": expected, "actual": actual})
    source_code = {
        name: value for name, value in source_files.items() if Path(name).suffix in (".py", ".js")
    }
    code_changed = [row for row in missing_or_changed if row["file"] in source_code]
    assert not code_changed, f"package source code differs from frozen manifest: {code_changed}"
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(
            (product / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf8")
            + NATIVE
            + (product / "sora_bilingual/game/scripts/native_transport.js").read_text("utf8"),
            runtime="v8",
        )
        script.load()
        loaded = script.exports_sync.modelpackedfile(str(wire))
        assert loaded == {"runtime": "V8", "retiredIdentityEmitted": False}, loaded
        checks, failures = 0, []
        for start in range(0, len(replay["rows"]), 128):
            chunk = script.exports_sync.run(replay["rows"][start : start + 128])
            checks += chunk["checks"]
            failures.extend(chunk["failures"])
        assert checks == 2097
        result = {
            "label": receipt["label"],
            "purpose": "packaged Frida V8 versus saved Node complete plan parity",
            "product_root": str(product),
            "wire_path": str(wire),
            "wire_sha256": wire_sha,
            "model_sha256": digest(package_model),
            "candidate_cache_sha256": digest(cache_path),
            "receipt_path": str(args.receipt.resolve()),
            "receipt_sha256": digest(args.receipt),
            "replay_path": str(args.replay.resolve()),
            "replay_sha256": digest(args.replay),
            "source_snapshot_sha256": receipt["source_snapshot_sha256"],
            "package_source_files_checked": len(source_files),
            "package_source_sha256": source_files,
            "package_source_code_files_checked": len(source_code),
            "package_source_code_matches_freeze": True,
            "non_code_package_manifest_differences": missing_or_changed,
            "runtime_text_sha256": source_files["sora_bilingual/game/scripts/runtime_text.js"],
            "native_transport_sha256": source_files[
                "sora_bilingual/game/scripts/native_transport.js"
            ],
            "complete_mode_plans": checks,
            "parity_failure_count": len(failures),
            "failures": failures,
            "retained_strict_frame_differences": replay["retained_strict_frame_differences"],
            "semantic_admission_revalidated": False,
            "loaded": loaded,
            "host_kind": "self-created hidden Python",
            "host_pid": host.pid,
            "game_attached": False,
            "candidate_live_verified": False,
        }
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8")
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key not in ("package_source_sha256", "failures")
                }
            )
        )
        return bool(failures)
    finally:
        if session is not None:
            session.detach()
        host.stdin.close()
        host.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
