"""Full current product replay in Frida V8 on a self-created hidden host."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]
NATIVE = r"""
rpc.exports={load(model){globalThis.tr=new RuntimeText(model);return {runtime:Script.runtime,retiredIdentityEmitted:!!model.item_help_identities};},
run(rows){let checks=0;for(const row of rows)for(const mode of ['primary','secondary','annotation']){
 const actual=tr.render(row.source,mode,'','');
 if(JSON.stringify(actual)!==JSON.stringify(row.modes[mode]))throw Error('V8 plan differs: '+row.name+'/'+mode);
 checks++;
}return checks;}};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, default=ROOT)
    parser.add_argument(
        "--receipt", type=Path, default=ROOT / "generated/r26-p0-local-production-receipt.json"
    )
    parser.add_argument(
        "--replay", type=Path, default=ROOT / "generated/r26-p0-local-product-replay.json"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r26-p0-local-production-frida.json"
    )
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text("utf8"))
    replay = json.loads(args.replay.read_text("utf8"))
    assert replay["failure_count"] == 0
    product = args.product.resolve()
    wire = Path(receipt["wire_path"])
    if product != ROOT:
        wire = (
            product
            / "generated"
            / json.loads((product / "candidate-cache.json").read_text("utf8"))["wire_name"]
        )
    digest = hashlib.sha256(wire.read_bytes()).hexdigest()
    assert digest == receipt["wire_sha256"] == replay["wire_sha256"]
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
        assert loaded == {"runtime": "V8", "retiredIdentityEmitted": False}
        checks = 0
        for start in range(0, len(replay["rows"]), 128):
            checks += script.exports_sync.run(replay["rows"][start : start + 128])
        result = {
            "wire_sha256": digest,
            "runtime_text_sha256": hashlib.sha256(
                (product / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
            ).hexdigest(),
            "source_snapshot_sha256": receipt["source_snapshot_sha256"],
            "complete_mode_plans": checks,
            "product_root": str(product),
            "loaded": loaded,
            "host_kind": "self-created hidden Python",
            "game_attached": False,
            "candidate_live_verified": False,
        }
        args.output.write_text(json.dumps(result, indent=2), "utf8")
        print(json.dumps(result))
    finally:
        if session is not None:
            session.detach()
        host.stdin.close()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
