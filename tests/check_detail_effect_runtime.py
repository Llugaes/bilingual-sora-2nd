"""Check the full production model in shipped Frida V8 and profile cold rendering.

Only a self-created hidden host is attached. Installed game files are read;
user configuration and live game/tool processes are left untouched.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import frida

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.model_wire import indexed_model
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path


KEYS = (
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:bda826b2cd19d0af6871e541bf57ccc31fb10c06e5d90d36fe35d0594beedd94/name",
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:229a07d0f14a217050055a3c2b79630b96f8642a7822de1ffb0595bf5cf07c21/name",
    "table/t_text.tbl/TXT_ITEM_HELP_HITTING",
)
DESCRIPTION = "table/t_skill.tbl/sha256:220b336432dab4bc8c7095fff8a9d47a4ea4ff384694b824b5a6928eec8b973e/description"
PROFILE = r"""
const fs=require('node:fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8')),{RuntimeText:Old}=require(data.baseline);
const result={};
for(const [name,Type] of [['baseline_0_4_2',Old],['candidate',RuntimeText]]) {
 result[name]=data.cases.map(row=>{
  const times=[];let plan;
  for(let i=0;i<8;i++) {
   const runtime=new Type(data.model),start=performance.now();
   plan=runtime.render(row.source);times.push(performance.now()-start);
  }
  times.sort((a,b)=>a-b);
  return {name:row.name,median_ms:times[4],max_ms:times[7],kind:plan.kind};
 });
}
console.log(JSON.stringify(result));
"""
NATIVE = r"""
rpc.exports={load(model) {globalThis.effectRuntime=new RuntimeText(model);
 return {runtime:Script.runtime,indexed:true,join:model.details.detail_join};},
run(cases) {
 const runtime=globalThis.effectRuntime,rows=[];
 for(const row of cases) {
  const start=Date.now(),plan=runtime.render(row.source),ms=Date.now()-start;
  if(runtime.translate(row.source,'primary')!==row.source)throw Error('primary changed: '+row.name);
  if(runtime.translate(row.source,'secondary')!==row.expected)throw Error('translation: '+row.name);
  const visible=(plan.text+plan.layers.map(l=>l.text).join(''))
   .replace(/<\/R([^<>]*)>/g,'$1').replace(/<[^<>]*>/g,'');
  for(const reading of row.readings)if(!visible.includes(reading))throw Error('reading: '+row.name);
  rows.push({name:row.name,kind:plan.kind,ms});
 }
 return {passed:true,game_attached:false,rows};
}};
"""


def check(game, output):
    entries, signature = load_entries(game)
    catalog = {row["key"]: row["texts"] for row in entries}
    config = {
        "primary": "en",
        "secondary": "ja",
        "game_language": "en",
        "scope": "all",
        "sources": [],
    }
    start = time.perf_counter()
    model = load_model(entries, signature, config, game=game)
    path = model_path(signature, config)
    print(
        json.dumps({"production_model": path.name, "compile_seconds": time.perf_counter() - start}),
        flush=True,
    )
    cases = []
    for members in ((0,), (1,), (2,), (0, 1), (2, 0, 1), (1, 2, 0, 2, 1)):
        for tail in (False, True):
            texts = {}
            for language in ("en", "ja"):
                separator = catalog["table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"][language]
                fragment = separator + separator.join(
                    catalog[KEYS[index]][language] for index in members
                )
                if tail:
                    fragment += separator.rstrip()
                texts[language] = (
                    "<c698>" + fragment + "</C>\n<C0>" + catalog[DESCRIPTION][language]
                )
            cases.append(
                {
                    "name": str(members) + ":" + str(tail),
                    "source": texts["en"],
                    "expected": texts["ja"],
                    "readings": [catalog[KEYS[index]]["ja"] for index in members],
                }
            )
    result = {
        "model": path.name,
        "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "config": config,
        "game_started": False,
        "game_attached": False,
        "cases": len(cases),
    }
    with tempfile.TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        baseline = temporary / "runtime_text.js"
        baseline.write_bytes(
            subprocess.check_output(
                ["git", "show", "v0.4.2:sora_bilingual/game/scripts/runtime_text.js"], cwd=ROOT
            )
        )
        profile = subprocess.run(
            ["node", "-e", PROFILE],
            cwd=ROOT,
            input=json.dumps({"model": model, "cases": cases, "baseline": str(baseline)}),
            text=True,
            encoding="utf8",
            capture_output=True,
            check=True,
        )
        result["cold_profile"] = json.loads(profile.stdout)
        wire = temporary / "effect-model.wire.bin"
        wire.write_bytes(indexed_model(model))
        result["wire_bytes"] = wire.stat().st_size
        host = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(240)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        session = None
        try:
            session = frida.attach(host.pid)
            script = session.create_script(
                (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf8")
                + NATIVE
                + (ROOT / "sora_bilingual/game/scripts/native_transport.js").read_text("utf8"),
                runtime="v8",
            )
            script.load()
            result["native_load"] = script.exports_sync.modelpackedfile(str(wire))
            result["native_replay"] = script.exports_sync.run(cases)
        finally:
            if session is not None:
                session.detach()
            host.terminate()
            host.wait(timeout=5)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(
        json.dumps(
            {
                "passed": True,
                "model": path.name,
                "wire_bytes": result["wire_bytes"],
                "native_cases": len(result["native_replay"]["rows"]),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.game, args.output)
