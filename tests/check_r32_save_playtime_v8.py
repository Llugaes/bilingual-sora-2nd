"""Scoped captured nine-line save plans in actual current indexed wires, Frida V8."""

import json
from pathlib import Path
import subprocess
import sys
import frida
import argparse

ROOT = Path(__file__).resolve().parents[1]
NATIVE = r"""
rpc.exports={load(model){globalThis.tr=new RuntimeText(model);return Script.runtime;},
run(row){let checks=0;for(const mode of ['primary','secondary','annotation']){
const actual=tr.render(row.source,mode,'',row.scope);
if(JSON.stringify(actual)!==JSON.stringify(row.modes[mode]))throw Error('save full plan differs: '+row.label+'/'+mode);
checks++;}return checks;}};
"""


def main():
    import hashlib

    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, default=ROOT)
    parser.add_argument(
        "--fixture", type=Path, default=ROOT / "generated/r32-local3-save-playtime-wire.json"
    )
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "generated/r32-coverage-source-freeze.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r32-local3-save-playtime-v8.json"
    )
    args = parser.parse_args()
    product = args.product.resolve()
    fixture_path = args.fixture.resolve()
    fixture = json.loads(fixture_path.read_text("utf8"))
    freeze = json.loads(args.freeze.read_text("utf8"))
    assert (
        fixture["source_snapshot_sha256"] == freeze["snapshot_sha256"]
        and fixture["failure_count"] == 0
    )
    cache = (
        json.loads((product / "candidate-cache.json").read_text("utf8"))
        if product != ROOT
        else None
    )
    if cache:
        assert cache["source_snapshot_sha256"] == freeze["snapshot_sha256"]
    for name in ("runtime_text.js", "native_transport.js"):
        assert (
            digest(product / "sora_bilingual/game/scripts" / name)
            == freeze["files"]["sora_bilingual/game/scripts/" + name]
        )
    records = []
    for row in fixture["cases"]:
        wire = Path(row["wire_path"])
        if cache:
            receipt = json.loads(
                (ROOT / f"generated/r32-coverage-{row['label']}-production-receipt.json").read_text(
                    "utf8"
                )
            )
            (selected,) = [
                item for item in cache["config_matrix"] if item["config"] == receipt["config"]
            ]
            wire = product / "generated" / selected["wire_name"]
            assert selected["wire_sha256"] == receipt["wire_sha256"] == row["wire_sha256"]
        assert digest(wire) == row["wire_sha256"]
        wire_before = wire.stat()
        assert row["scope"] == fixture["observed_scope"] == "save_summary"
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
            assert script.exports_sync.modelpackedfile(str(wire)) == "V8"
            checks = script.exports_sync.run(row)
            assert checks == 3
            assert (
                wire.stat().st_mtime_ns == wire_before.st_mtime_ns
                and wire.stat().st_size == wire_before.st_size
            )
            records.append(
                {
                    "label": row["label"],
                    "wire_path": str(wire),
                    "wire_sha256": row["wire_sha256"],
                    "wire_size_and_mtime_unchanged": True,
                    "complete_mode_plans": checks,
                    "parity_failure_count": 0,
                    "host_pid": host.pid,
                }
            )
            print(json.dumps(records[-1]), flush=True)
        finally:
            if session is not None:
                session.detach()
            host.stdin.close()
            host.wait(timeout=5)
    output = args.output.resolve()
    assert not output.exists(), "never overwrite previous save V8 evidence"
    output.write_text(
        json.dumps(
            {
                "source_snapshot_sha256": fixture["source_snapshot_sha256"],
                "product_root": str(product),
                "fixture_sha256": digest(fixture_path),
                "runtime_text_sha256": digest(
                    product / "sora_bilingual/game/scripts/runtime_text.js"
                ),
                "complete_mode_plans": sum(row["complete_mode_plans"] for row in records),
                "parity_failure_count": 0,
                "scope_source": "original captured layout/path; no supplied record identity",
                "host_kind": "self-created hidden Python",
                "game_attached": False,
                "records": records,
            },
            indent=2,
        ),
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
