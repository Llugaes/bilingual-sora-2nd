"""Replay captured history and raw producer families through complete JS models.

Read-only, offline game-resource check. A runtime pass is not a live game pass.
"""

import argparse
from collections import defaultdict
import gc
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.localization.speaker_context import read_speaker_names

HISTORY = {
    738: ("mp3010_01.dat/QS212_00_00/called/91", 2, "<#E[1]#M_2#B_0>不过现在先谈工作要紧。"),
    739: ("mp3010_01.dat/QS212_00_00/called/94", 0, "<#E[1118]#M_0#B[#60s7]>啊，说的也是呢。"),
    910: (
        "mp3010_01.dat/QS210_04_00/called/131",
        2,
        "<#E[9]#M_2#B_0><K4>上面说的好像就是\n这个地方……可是有些部分\n不知道是什么意思。",
    ),
    911: (
        "mp3010_01.dat/QS210_04_00/called/133",
        2,
        "<#E_0#M_0#B_0><K4>我们猜你或许会知道，\n所以才来向你请教。",
    ),
    964: ("mp3000_ev.dat/QS210_05_00/called/150", 2, "<#E_0#M_0#B_0>嗯，了解了。"),
}
REPORTED = {
    865: "要支付１００米拉休息吗？",
    1021: "获得了<C0><I110></C><C5>命中３</C>的结晶回路。",
    1030: "BP上升了<C2>2<C0>点。",
    1033: "记住了<C0><I12></C><C5>山珍《粹》</C>的食谱！",
    1034: "记住了<C0><I12></C><C5>热情煎蛋卷</C>的食谱！",
    1035: "记住了<C0><I12></C><C5>好宝宝奶昔</C>的食谱！",
}
RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8')),model=JSON.parse(fs.readFileSync(data.model,'utf8'));
const global=new RuntimeText(model),rows=[];
const calls=new Map();
for(const bucket of Object.values(model.script_identities?.scripts||{}))for(const script of bucket)
 for(const path of script.paths)for(const [fn,context] of Object.entries(script.functions))
  for(const call of Object.values(context.calls||{}))for(const record of call.records) {
   const key=path+'/'+fn+'/called/'+record;
   if(!calls.has(key))calls.set(key,[]);calls.get(key).push(call.model);
  }
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const c of data.cases) {
 const contextual=c.speaker&&global.speakerContext(c.speaker,c.source),r=contextual?.tr||global;
 const primary=r.translate(c.source,'primary'),secondary=r.translate(c.source,'secondary');
 const plan=r.render(c.source,'annotation');
 const payload=plan.layers.map(l=>l.text).join('')+
  [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 // Preserved ambiguous history has no selected translation to annotate.
 const annotationNeeded=!c.unresolved&&!model.same_language&&RuntimeText.needsAnnotation(c.primary,c.secondary);
 const translated=primary===c.primary&&secondary===c.secondary;
 const annotated=annotationNeeded?plan.kind!=='plain'&&visible(payload)===visible(c.secondary):
  plan.kind==='plain'&&plan.text===c.primary;
 const owned=c.singleLane&&annotationNeeded?plan.layers.length===1:true;
 let contextualPass=true;
 if(c.unresolved) {
  const contexts=calls.get(c.callKey)||[];
  contextualPass=contexts.length>0&&contexts.every(m=>{
   const t=new RuntimeText(m);
   return t.translate(c.source,'primary')===c.withIdentity[0]&&t.translate(c.source,'secondary')===c.withIdentity[1];
  });
 }
 rows.push({name:c.name,pass:translated&&annotated&&owned&&contextualPass,
  translated:c.unresolved?false:translated,annotated,owned,
  ...(c.unresolved?{unresolved:c.unresolved,fresh_call_identity_pass:contextualPass,old_history_preserved:translated}:{}),
  context:contextual?'retained_speaker':'global',
  ...(!translated||!annotated||!owned||!contextualPass?{source:c.source,primary,secondary,expected:[c.primary,c.secondary],plan}:{} )});
}
process.stdout.write(JSON.stringify(rows));
"""


def number_text(entry, locale, value):
    style = entry["dynamic_producer"]["numbers"][locale][0]
    digits = str(value)
    if style == "fullwidth":
        digits = digits.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    return entry["texts"][locale].replace("%d", digits)


def replay_cases(entries, names, primary, secondary):
    by_key = {entry["key"]: entry for entry in entries}
    rows, excluded = [], []
    for slot, (path, actor, source) in HISTORY.items():
        entry = by_key["script/scena/" + path + "/assembled_dialogue"]
        # Runtime emotion heads may change; they are preserved on translated text.
        head = re.match(r"^(?:<#[^<>]*>)+", source).group()
        translated = {
            locale: head + re.sub(r"^(?:<#[^<>]*>)+", "", entry["texts"][locale])
            for locale in (primary, secondary)
        }
        same_actor = {
            (
                re.sub(r"^(?:<#[^<>]*>)+", "", e["texts"][primary]),
                re.sub(r"^(?:<#[^<>]*>)+", "", e["texts"][secondary]),
            )
            for e in entries
            if e.get("display_role") == "dialogue"
            and e.get("speaker_ids", {}).get("zh-Hans") == actor
            and all(e["texts"].get(locale) for locale in ("zh-Hans", primary, secondary))
            and re.sub(r"^(?:<#[^<>]*>)+", "", e["texts"]["zh-Hans"])
            == re.sub(r"^(?:<#[^<>]*>)+", "", source)
        }
        unresolved = len(same_actor) > 1
        rows.append(
            {
                "name": f"history/{slot}",
                "source": source,
                "speaker": names[actor],
                "primary": source if unresolved else translated[primary],
                "secondary": source if unresolved else translated[secondary],
                **(
                    {
                        "unresolved": "same_speaker_different_wording_without_saved_call_identity",
                        "callKey": "script/scena/" + path,
                        "withIdentity": [translated[primary], translated[secondary]],
                    }
                    if unresolved
                    else {}
                ),
            }
        )
    producers = [e for e in entries if e.get("producer_origin") or e.get("dynamic_producer")]
    claims = defaultdict(set)
    for entry in producers:
        if entry.get("dynamic_producer"):
            continue
        if all(locale in entry["texts"] for locale in ("zh-Hans", primary, secondary)):
            claims[entry["texts"]["zh-Hans"]].add(
                (entry["texts"][primary], entry["texts"][secondary])
            )
    captured = set()
    for entry in producers:
        if not all(locale in entry["texts"] for locale in ("zh-Hans", primary, secondary)):
            excluded.append({"key": entry["key"], "reason": "missing_selected_locale"})
            continue
        numeric = bool(entry.get("dynamic_producer"))
        # Icons are opaque runtime arguments, not fixed item-table values.
        # Include the captured icon numbers as well as numeric boundaries so
        # the REPORTED guard continues to replay the original full inputs.
        values = (0, 2, 100, 200, 2147483647) if numeric else (None,)
        if entry.get("dynamic_producer", {}).get("dynamic_icon"):
            values = (0, 5, 10, 12, 110, 2147483647)
        for value in values:
            source, a, b = (
                number_text(entry, locale, value) if numeric else entry["texts"][locale]
                for locale in ("zh-Hans", primary, secondary)
            )
            if not numeric and len(claims[source]) != 1:
                excluded.append(
                    {"key": entry["key"], "reason": "selected_source_conflict", "source": source}
                )
                continue
            captured.update(slot for slot, text in REPORTED.items() if source == text)
            rows.append(
                {
                    "name": entry["key"] + (f"/{value}" if numeric else ""),
                    "source": source,
                    "primary": a,
                    "secondary": b,
                    "singleLane": "<" in source and "\n" not in source,
                }
            )
    missing = set(REPORTED) - captured
    if missing:
        raise AssertionError(f"Reported dynamic inputs not admitted: {sorted(missing)}")
    return rows, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--targets", nargs="+", choices=LANGUAGES, default=LANGUAGES)
    parser.add_argument("--primary", choices=LANGUAGES, default="zh-Hans")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/dynamic-history-check.json"
    )
    args = parser.parse_args()
    entries, signature = load_entries(args.game_dir)
    names = read_speaker_names(args.game_dir, "zh-Hans")
    report = {
        "game_attached": False,
        "scope": "complete production catalog; captured input and retained speaker; raw dynamic producer families",
        "signature": json.loads(signature),
        "primary": args.primary,
        "targets": [],
        "all_passed": True,
    }
    for secondary in args.targets:
        config = {
            "game_language": "zh-Hans",
            "primary": args.primary,
            "secondary": secondary,
            "scope": "all",
        }
        model = load_model(entries, signature, config, game=args.game_dir)
        del model
        gc.collect()
        cases, excluded = replay_cases(entries, names, args.primary, secondary)
        completed = subprocess.run(
            ["node", "-e", RUNNER],
            cwd=ROOT,
            input=json.dumps(
                {"model": str(model_path(signature, config)), "cases": cases}, ensure_ascii=False
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        rows = json.loads(completed.stdout)
        passed = all(row["pass"] for row in rows)
        report["targets"].append(
            {"secondary": secondary, "rows": rows, "excluded": excluded, "passed": passed}
        )
        report["all_passed"] &= passed
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(secondary, "PASS" if passed else "FAIL", len(rows), flush=True)
    if not report["all_passed"]:
        raise AssertionError(f"Runtime failures remain: {args.output}")


if __name__ == "__main__":
    main()
