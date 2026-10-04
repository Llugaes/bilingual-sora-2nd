"""Check the full production model in shipped Frida V8 and profile cold rendering.

Only a self-created hidden host is attached. Installed game files are read;
user configuration and live game/tool processes are left untouched.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import frida

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.model_wire import indexed_model
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.menu_text import plain


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
const previous=new Old(data.model),runtime=new RuntimeText(data.model);
result.negatives=data.negatives.map(row=>{
 const expected=previous.translate(row.source,'secondary'),render=previous.render(row.source);
 if(runtime.translate(row.source,'secondary')!==expected)throw Error('negative translation '+row.name);
 if(JSON.stringify(runtime.render(row.source))!==JSON.stringify(render))throw Error('negative render '+row.name);
 if(runtime.details.detailJoinPair(row.fragment)!==null)throw Error('negative admission '+row.name);
 return {...row,expected,render};
});
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
run(cases,negatives,blocked) {
 const runtime=globalThis.effectRuntime,rows=[];
 for(const row of cases) {
  const start=Date.now(),plan=runtime.render(row.source),ms=Date.now()-start;
  if(runtime.translate(row.source,'primary')!==row.source)throw Error('primary changed: '+row.name);
  if(runtime.translate(row.source,'secondary')!==row.expected)throw Error('translation: '+row.name);
  const visible=(plan.text+plan.layers.map(l=>l.text).join(''))
   .replace(/<\/R([^<>]*)>/g,'$1').replace(/<[^<>]*>/g,'');
  for(const reading of row.readings)if(!visible.includes(reading.replace(/<[^<>]*>/g,'')))throw Error('reading: '+row.name);
  rows.push({name:row.name,kind:plan.kind,ms});
 }
 for(const row of negatives) {
  if(runtime.translate(row.source,'secondary')!==row.expected)throw Error('negative translation '+row.name);
  if(JSON.stringify(runtime.render(row.source))!==JSON.stringify(row.render))throw Error('negative render '+row.name);
  if(runtime.details.detailJoinPair(row.fragment)!==null)throw Error('negative admission '+row.name);
 }
 for(const row of blocked) {
  if(runtime.details.detailJoinPair(row.fragment)!==null)throw Error('blocked admission '+row.name);
  if(runtime.translate(row.source,'secondary')!==row.expected)throw Error('blocked translation '+row.name);
 }
 return {passed:true,game_attached:false,rows,negative_cases:negatives.length,blocked_cases:blocked.length};
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
    grammar = build_item_help_grammar(game, entries, "en", languages=("en", "ja"))
    for family in ("revive_recovery", "turn_stat_inline_icon", "turn_stat_group", "chance_group"):
        row = next(
            row
            for row in grammar["detail_entries"]
            if row.get("item_help_contract", {}).get("family") == family
        )
        values = {
            language: plain(row["texts"][language]).replace("%d", "30").replace("%%", "%")
            for language in ("en", "ja")
        }
        for length in (2, 3, 5):
            texts = {}
            for language in ("en", "ja"):
                separator = catalog["table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"][language]
                members = [values[language]] + [
                    catalog[KEYS[index % 3]][language] for index in range(length - 1)
                ]
                texts[language] = (
                    "<c698>"
                    + separator
                    + separator.join(members)
                    + "</C>\n<C0>"
                    + catalog[DESCRIPTION][language]
                )
            cases.append(
                {
                    "name": family + ":" + str(length),
                    "source": texts["en"],
                    "expected": texts["ja"],
                    "readings": [values["ja"]],
                }
            )
    negatives = []
    for fragment in (
        ", UNKNOWN, Side Attack Bonus",
        ", , Side Attack Bonus",
        ",",
        ", STR<I999> (30 turns), Side Attack Bonus",
        ", UNKNOWN, STR<I270> (30 turns), Side Attack Bonus",
        ", STR<I270> (30 turns), UNKNOWN, Side Attack Bonus",
    ):
        negatives.append(
            {
                "name": "unknown:" + str(len(negatives)),
                "fragment": fragment,
                "source": "<c698>" + fragment + "</C>\n<C0><C9>" + catalog[DESCRIPTION]["en"],
            }
        )
    blocked = []
    patterns = [re.compile(pattern) for pattern in model["details"]["detail_join_blocked_numeric"]]
    for row in entries + grammar["detail_entries"]:
        template = row["texts"].get("en", "")
        if "%d" not in template or "%s" in template:
            continue
        instance = plain(template).replace("%d", "30").replace("%%", "%")
        if not any(pattern.fullmatch(instance) for pattern in patterns):
            continue
        fragment = ", " + instance + ", Side Attack Bonus"
        blocked.append(
            {
                "name": row["key"],
                "fragment": fragment,
                "source": "<c698>" + fragment + "</C>\n<C0>" + catalog[DESCRIPTION]["en"],
                "expected": "<c698>" + fragment + "</C>\n<C0>" + catalog[DESCRIPTION]["ja"],
            }
        )
        break
    assert blocked, "production model has no exercised blocked numeric instance"
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
            input=json.dumps(
                {"model": model, "cases": cases, "negatives": negatives, "baseline": str(baseline)}
            ),
            text=True,
            encoding="utf8",
            capture_output=True,
            check=True,
        )
        result["cold_profile"] = json.loads(profile.stdout)
        negatives = result["cold_profile"].pop("negatives")
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
            result["native_replay"] = script.exports_sync.run(cases, negatives, blocked)
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
