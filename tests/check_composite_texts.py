"""Audit lists against full production models, without attaching to the game.

Raw table fields are the denominator. Missing/ambiguous atoms remain explicit
findings; constructed probes test resolver closure, not native scene coverage.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator

RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const d=JSON.parse(fs.readFileSync(0,'utf8'));
const r=new RuntimeText(d.model||JSON.parse(fs.readFileSync(d.path,'utf8')));
const stats={atoms:0,ambiguous_or_missing_atoms:[],pairs:0,lists:0,failures:[],raw_composites:0,raw_gaps:[]};
const strip=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
function check(source,expected,label) {
 const body=source.replace(/^<c698>/,'').replace(/<\/C>$/,'').slice(1,-1);
 const complete=r.model.plain_pairs[body];
 if(complete)expected=source.replace(body,complete[1]);
 const value=r.translate(source,'secondary'),plan=r.render(source);
 if(value!==expected)stats.failures.push({label,source,expected,actual:value});
 const payload=plan.layers.map(l=>l.text).join('')+
  [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 if(strip(r.translate(source,'primary'))!==strip(expected)&&plan.kind==='plain')
  stats.failures.push({label,source,reason:'missing_annotation'});
 return payload;
}
const start=performance.now();
for(const [family,records] of Object.entries(d.families)) {
 const accepted=[];
 for(const row of records) {
  stats.atoms++;
  if((r.model.pairs[row.source]||r.model.plain_pairs[row.source])&&r.translate(row.source,'secondary')===row.target)accepted.push(row);
  else stats.ambiguous_or_missing_atoms.push({family,...row,actual:r.translate(row.source,'secondary'),
    classification:r.details?.translate(row.source,'secondary')===row.target?'resolved_in_detail_context':
     row.source===row.target?'unchanged_literal_without_global_pair':'requires_resource_identity_or_missing_pair'});
 }
 // Every ordered pair; the list parser also sees each member at every offset
 // in three-, four-, five- and full-family lists, in both directions.
 const seen=new Set();
 for(const a of accepted)for(const b of accepted) {
  const source=a.source+'·'+b.source;
  if(seen.has(source))continue;seen.add(source);
  check('「'+source+'」','「'+a.target+'·'+b.target+'」',family);stats.pairs++;
 }
 for(const count of new Set([3,4,5,accepted.length,32])) {
  if(!accepted.length)continue;
  for(let offset=0;offset<accepted.length;offset++)for(const reverse of [false,true]) {
   const members=Array.from({length:count},(_,i)=>accepted[(offset+i)%accepted.length]);
   if(reverse)members.reverse();
   for(const sep of ['·','・','･','/','／']) {
    const source='<c698>「'+members.map(x=>x.source).join(sep)+'」</C>';
    const expected='<c698>「'+members.map(x=>x.target).join(sep)+'」</C>';
    const payload=check(source,expected,family);stats.lists++;
    for(const member of members)if(strip(r.translate(member.source,'primary'))!==strip(member.target)&&!strip(payload).includes(strip(member.target)))
     stats.failures.push({family,source,reason:'missing_secondary_member',member});
   }
  }
 }
}
for(const row of d.raw) {
 stats.raw_composites++;
 const actual=r.translate(row.source,'secondary');
 if(actual!==row.target)stats.raw_gaps.push({...row,actual,
   classification:r.details?.translate(row.source,'secondary')===row.target?'resolved_in_detail_context':
    actual.normalize('NFKC')===row.target.normalize('NFKC')?'presentation_width_only':'requires_resource_identity_or_missing_pair'});
}
stats.elapsed_ms=performance.now()-start;
process.stdout.write(JSON.stringify(stats));
"""


def family(key):
    if key.startswith("table/t_itemhelp.tbl/") and key.endswith("/condition"):
        return "condition"
    if key.startswith("table/t_itemhelp.tbl/SkillEffectHelpData/") and key.endswith("/stat"):
        return "effect_stat"
    if key.startswith("table/t_itemhelp.tbl/SkillItemStatusData/") and key.endswith("/name"):
        return "status_name"
    if key.startswith("table/t_itemhelp.tbl/SkillRangeHelpData/") and key.endswith("/label"):
        return "range_label"
    return None


def inputs(entries, source, target):
    families, raw, excluded = {}, [], []
    for entry in entries:
        key, texts = entry["key"], entry["texts"]
        group = family(key)
        a, b = texts.get(source, ""), texts.get(target, "")
        if group:
            if not a or not b or "%" in a + b or "<" in a + b:
                excluded.append({"key": key, "reason": "missing_locale_or_parameterized_field"})
            elif re.search(r"[·・･/／]| - ", a):
                excluded.append(
                    {"key": key, "reason": "already_composite_tested_as_complete_resource"}
                )
            else:
                row = {"key": key, "source": a, "target": b}
                bucket = families.setdefault(group, [])
                if not any(r["source"] == a and r["target"] == b for r in bucket):
                    bucket.append(row)
        if key.startswith("table/") and re.search(r"[·・･]", a) and b and "%" not in a + b:
            raw.append({"key": key, "source": a, "target": b})
    return families, raw, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "generated/catalog.json")
    parser.add_argument("--status-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads(args.catalog.read_text("utf-8"))["entries"]
    tables = [e for e in entries if e["key"].startswith("table/")]
    modes = []
    if args.status_audit:
        modes = [
            dict(source=m["source"], target=m["secondary"], path=m["model"], scope="full_catalog")
            for m in json.loads(args.status_audit.read_text("utf-8"))["modes"]
        ]
    modes += [
        dict(source=source, target="ja" if source != "ja" else "en", scope="all_tables")
        for source in LANGUAGES
    ]
    reports = []
    for mode in modes:
        families, raw, excluded = inputs(tables, mode["source"], mode["target"])
        data = {"families": families, "raw": raw}
        if "path" in mode:
            data["path"] = mode["path"]
        else:
            data["model"] = MenuTranslator(
                tables, mode["source"], mode["target"], mode["source"]
            ).runtime_model()
        result = subprocess.run(
            ["node", "-e", RUNNER],
            input=json.dumps(data, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=ROOT,
            check=True,
        )
        report = {**mode, **json.loads(result.stdout), "excluded_fields": excluded}
        reports.append(report)
        print(
            mode["scope"],
            mode["source"],
            mode["target"],
            {
                k: len(report[k]) if isinstance(report[k], list) else report[k]
                for k in (
                    "atoms",
                    "pairs",
                    "lists",
                    "failures",
                    "raw_gaps",
                    "ambiguous_or_missing_atoms",
                    "elapsed_ms",
                )
            },
            flush=True,
        )
        args.output.write_text(
            json.dumps({"game_attached": False, "reports": reports}, ensure_ascii=False, indent=2),
            "utf-8",
        )
    if any(r["failures"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
