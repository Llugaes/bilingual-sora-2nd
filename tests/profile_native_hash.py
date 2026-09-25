import os

"""Measure actual Frida runtime in an owned idle Python host, never the game."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import hashlib
import json
import subprocess
import time
import frida
from sora_bilingual.localization.native_catalog import ready_model
from sora_bilingual.config.native_config import read_config
from sora_bilingual.localization.resources import FpacArchive, _ARCHIVES, _logical_script_entries

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(os.environ["SORA_GAME_DIR"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    model, _, _ = ready_model(GAME, read_config())
    scripts = [s for bucket in model["script_identities"]["scripts"].values() for s in bucket]
    script = sorted(scripts, key=lambda s: s["size"])[len(scripts) * 95 // 100]
    largest = max(scripts, key=lambda s: s["size"])
    with FpacArchive(GAME / "pac/steam" / _ARCHIVES["zh-Hans"]) as archive:
        paths = _logical_script_entries(archive)
        samples = [archive.read(paths[s["paths"][0]]) for s in (script, largest)]
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        source = (ROOT / "sora_bilingual/game/scripts/runtime_identity.js").read_text("utf-8")
        if args.native:
            source += "\n" + (ROOT / "sora_bilingual/game/scripts/native_hash.js").read_text(
                "utf-8"
            )
        source += (
            "\nconst digest=" + ("createNativeSha256()" if args.native else "scriptSha256") + ";"
        )
        source += "\nrpc.exports={bench(data){return digest(data);}};"
        if args.native:
            source += """
rpc.exports.verify=function(expected,data){
  const p=Memory.alloc(Math.max(1,data.byteLength));p.writeByteArray(data);
  const model={pairs:{ok:['ok','yes']},plain_pairs:{ok:['ok','yes']}};
  const ids=new ScriptIdentities({scripts:{h:[{size:data.byteLength,sha256:expected,functions:{Talk:{model,calls:{}}}}]}},digest);
  const select=()=>ids.select('h',n=>({pointer:p,byteLength:n}),'Talk','1');
  const first=select();p.writeU8(p.readU8()^1);const second=select();
  return {matched:first?.model.pairs.ok[1]==='yes',changedBytesRejected:second===null};
};
"""
        agent = session.create_script(source)
        agent.load()
        result = []
        for data in samples:
            times = []
            for _ in range(5):
                start = time.perf_counter()
                digest = agent.exports_sync.bench(data)
                times.append((time.perf_counter() - start) * 1000)
                assert digest == hashlib.sha256(data).hexdigest()
            result.append(
                {
                    "bytes": len(data),
                    "min_ms": min(times),
                    "median_ms": sorted(times)[2],
                    "max_ms": max(times),
                }
            )
            if args.native:
                checks = agent.exports_sync.verify(hashlib.sha256(data).hexdigest(), data)
                assert checks == {"matched": True, "changedBytesRejected": True}, checks
        output = {
            "backend": "windows-cng" if args.native else "pure-js",
            "frida_default_runtime": True,
            "includes_rpc_transport": True,
            "samples": result,
            "native_pointer_identity_verified": args.native,
            "game_started": False,
            "game_attached": False,
        }
        path = (
            ROOT
            / "generated"
            / ("hash-performance-after.json" if args.native else "hash-performance-before.json")
        )
        path.write_text(json.dumps(output, indent=2), "utf-8")
        print(json.dumps(output, indent=2))
    finally:
        # Only our disposable test host can be detached/terminated here.
        if session is not None:
            session.detach()
        host.communicate(timeout=5)


if __name__ == "__main__":
    main()
