"""Run the new identities on the real lazy wire reader in an owned Frida V8 host."""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
let model;
rpc.exports={load(value){model=value;return true;},run(row,blob){
 const bytes=new Uint8Array(blob),ids=new ScriptIdentities(model.script_identities);
 const identity=ids.capture(row.signature,n=>bytes.subarray(0,n),row.fn,row.token,row.site,row.source);
 if(identity?.recordKey!==row.key)throw Error('indexed identity '+row.key);
 const tr=new RuntimeText(ids.lookup(identity,row.source).model);
 if(tr.translate(row.source,'primary')!==row.texts['zh-Hans'])throw Error('indexed primary');
 if(tr.translate(row.source,'secondary')!==row.texts.ja)throw Error('indexed secondary');
 const plan=tr.render(row.source,'annotation');
 const visible=s=>RuntimeText.visualSecondary(s).replace(/<[^<>]*>/g,'').replace(/\s/g,'');
 const payload=plan.layers.map(v=>v.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(v=>v[1]==='_'?'':v[1]).join('');
 if(visible(payload)!==visible(row.texts.ja))throw Error('incomplete indexed annotation');
 let checks=4;
 for(const bad of row.bad||[]) {
  if(ids.capture(row.signature,n=>bytes.subarray(0,n),row.fn,bad.token,row.site,bad.source)?.recordKey===row.key)throw Error('indexed unsafe count accepted');
  checks++;
 }
 return checks;
}};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, default=ROOT)
    args = parser.parse_args()
    rows = json.loads((args.model_dir / "remaining-dialogue-input.json").read_bytes())
    model = Path(json.loads((args.model_dir / "full-model-builds.json").read_bytes())[0]["path"])
    scripts = args.code_root / "sora_bilingual/game/scripts"
    source = "\n".join(
        (scripts / name).read_text("utf-8") for name in ("runtime_text.js", "runtime_identity.js")
    )
    source += RUNNER + "\n" + (scripts / "native_transport.js").read_text("utf-8")
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(source, runtime="v8")
        script.load()
        script.exports_sync.modelpackedfile(str(model.with_suffix(".wire.bin").resolve()))
        checks = 0
        for row in rows:
            blob = base64.b64decode(row.pop("blob"))
            checks += script.exports_sync.run(row, blob)
        report = {
            "rows": len(rows),
            "checks": checks,
            "passed": True,
            "game_started": False,
            "game_attached": False,
            "scope": "owned Frida V8 host, complete wire model and actual SCP bytes; no hash substitute",
            "code_root": str(args.code_root.resolve()),
        }
        (args.model_dir / "remaining-indexed.json").write_text(
            json.dumps(report, indent=2), "utf-8"
        )
        print(json.dumps(report))
    finally:
        if session:
            session.detach()
        host.terminate()
        host.wait(10)
        host.stdin.close()


if __name__ == "__main__":
    main()
