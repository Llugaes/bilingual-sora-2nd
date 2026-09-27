"""Replay reported omissions through full catalog models and production JS.

Requires locally installed game resources. No game process is started or
attached; configuration is read but never changed. Reduced fixtures cannot
replace this check: cross-domain collisions only appear in the full catalog.
"""

import argparse
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.config.native_config import read_config
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
import test_itemhelp_composition as keys

NOTE = "script/scena/mp3010_01.dat/LP_Capel/called/131/assembled_dialogue"
KEY_HINT = "script/scena/mp3010_01.dat/LP_Capel/called/133/assembled_dialogue"
RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(data.model,'utf8')),runtime=new RuntimeText(model);
const identities=new ScriptIdentities(model.script_identities),contexts=new Map();
for(const [signature,bucket] of Object.entries(model.script_identities?.scripts||{}))
 for(const script of bucket) for(const path of script.paths)
  for(const [functionName,fn] of Object.entries(script.functions))
   for(const [argumentsToken,call] of Object.entries(fn.calls)) for(const record of call.records) {
    const key=path+'/'+functionName+'/called/'+record+'/assembled_dialogue';
    if(!contexts.has(key))contexts.set(key,[]);
    contexts.get(key).push({signature,sha256:script.sha256,functionName,argumentsToken});
   }
const rows=[];
const padding=t=>t.split('\n').map(line=>line
 .replace(/^((?:<[^<>]*>)*)([ \t\u3000]+)/,'$1')
 .replace(/[ \t\u3000]+(?=(?:<[^<>]*>)*$)/,'')).join('\n');
const words=t=>/[\p{L}\p{N}]/u.test(t.replace(/<[^<>]*>/g,''));
for(const c of data.cases) for(const mode of ['primary','secondary']) {
 const actual=runtime.translate(c.source,mode),expected=c[mode];
 const verdict=actual===expected?'exact':
  !words(actual)&&!words(expected)?'nonlinguistic_decoration':
  padding(actual)===padding(expected)?'line_padding_only':'failed';
 const row={name:c.name,mode,pass:verdict!=='failed',verdict,
  ...(verdict==='failed'?{actual,expected}:{})};
 if(verdict==='failed'&&c.name.startsWith('panel:')) {
  // A separate result: copied log text may lack this resource identity.
  // Never turn a global miss into a pass based on offline context availability.
  const candidates=contexts.get(c.name.slice(6))||[];
  const values=candidates.map(id=>{
   const selected=identities.lookup(id);
   return selected?new RuntimeText(selected.model).translate(c.source,mode):null;
  });
  row.context_candidates=values.length;
  row.context_pass=values.length>0&&values.every(value=>value===expected);
 }
 rows.push(row);
}
process.stdout.write(JSON.stringify(rows));
"""


def cases(catalog, language, panel_keys=()):
    def text(key):
        return catalog[key][language]

    def modifier(name):
        return text("table/t_text.tbl/TXT_ITEM_HELP_" + name)

    result = {
        "full_screen_note": text(NOTE),
        "centered_key_hint_with_repeated_controls": text(KEY_HINT),
        "static_reward_after_dynamic_items": text(
            "script/scena/mp6010_01.dat/EV_00_06_00/called/93/assembled_dialogue"
        ),
        "colored_skill_header": (
            f"<C3></C>【{text(keys.ARTS_ATTACK)}<I278>／<I295><C3>"
            f"{text(keys.TARGET_RANGE)}{modifier('RANGE_S')}</C>】<c698>"
            f"{text(keys.DELAY).removesuffix('%s')}<c698>{modifier('MIDDLE')}</C></C>"
            f"<c698>／</C><c698>{text(keys.FREEZE).replace('%d', '40').replace('%%', '%')}</C>\n"
            f"<C0>{text(keys.SKILL_DESCRIPTION)}"
        ),
        "self_range": (
            f"<C3>{text(keys.SELF_RANGE)}{modifier('RANGE_L')}</C>\n<C0>{text(keys.SKILL_DESCRIPTION)}"
        ),
        "item_enhance": (
            f"{text(keys.ITEM_KIND_HELP)}【<I299>{text(keys.SINGLE_RANGE)}："
            f"<c698>{text(keys.STATUS_BASE + '/stat')}</C> - <I378><c698>"
            f"{text(keys.STATUS_BASE + '/format').replace('%d', '20')}</C>】\n"
            f"{text(keys.ITEM_DESCRIPTION)}"
        ),
    }
    result.update({"panel:" + key: text(key) for key in panel_keys})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", default=os.environ.get("SORA_GAME_DIR"), type=Path)
    parser.add_argument("--source", choices=LANGUAGES, default="zh-Hans")
    parser.add_argument("--secondary", choices=LANGUAGES, default="ja")
    parser.add_argument("--targets", nargs="+", choices=LANGUAGES, default=LANGUAGES)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/reported-texts-check.json")
    parser.add_argument(
        "--panel-audit", type=Path, help="replay every verified key from audit_static_panels"
    )
    args = parser.parse_args()
    if args.game_dir is None:
        parser.error("provide --game-dir or SORA_GAME_DIR")
    entries, signature = load_entries(args.game_dir)
    catalog = {entry["key"]: entry["texts"] for entry in entries}
    panel_keys = ()
    if args.panel_audit:
        panel_report = json.loads(args.panel_audit.read_text(encoding="utf-8"))
        if panel_report.get("source_language") != args.source:
            parser.error("panel audit source does not match --source")
        panel_keys = panel_report["verified_keys"]
        if not panel_keys:
            parser.error("panel audit contains no verified keys")
    source, secondary = (
        cases(catalog, args.source, panel_keys),
        cases(catalog, args.secondary, panel_keys),
    )
    config = {
        **read_config(),
        "game_language": args.source,
        "secondary": args.secondary,
        "scope": "all",
    }
    report = {
        "scope": "full production catalog and JS; exact resource-derived expected text",
        "game_attached": False,
        "signature": json.loads(signature),
        "source": args.source,
        "secondary": args.secondary,
        "entries": len(entries),
        "panel_cases": len(panel_keys),
        "targets": [],
        "all_passed": True,
        "context_scope": "compiled resource identity only; availability in live controls/logs is not proven",
        "all_resolvable_with_compiled_context": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for target in args.targets:
        start = time.monotonic()
        config["primary"] = target
        model = load_model(entries, signature, config, game=args.game_dir)
        coverage = model.get("coverage")
        del model
        gc.collect()
        primary = cases(catalog, target, panel_keys)
        data = {
            "model": str(model_path(signature, config)),
            "cases": [
                {
                    "name": name,
                    "source": value,
                    "primary": primary[name],
                    "secondary": secondary[name],
                }
                for name, value in source.items()
            ],
        }
        result = subprocess.run(
            ["node", "-e", RUNNER],
            cwd=ROOT,
            input=json.dumps(data, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        rows = json.loads(result.stdout)
        passed = all(row["pass"] for row in rows)
        with_context = all(row["pass"] or row.get("context_pass", False) for row in rows)
        report["targets"].append(
            {
                "target": target,
                "seconds": round(time.monotonic() - start, 3),
                "coverage": coverage,
                "rows": rows,
                "all_passed": passed,
                "all_resolvable_with_compiled_context": with_context,
            }
        )
        report["all_passed"] &= passed
        report["all_resolvable_with_compiled_context"] &= with_context
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(target, "PASS" if passed else "FAIL", flush=True)
    if not report["all_passed"]:
        raise AssertionError(f"Full-model omissions remain; see {args.output}")


if __name__ == "__main__":
    main()
