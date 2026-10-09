"""Real PAC field census and complete-model effect/description ownership.

Numeric combinations are constructor-contract probes, not evidence that all
combinations occur on screen. Visual/native-width acceptance remains separate.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from check_detail_effect_lists import raw_resource_audit
from sora_bilingual.localization.item_help_composition import build_item_help_grammar

RUNNER = r"""
const fs=require('node:fs'),assert=require('node:assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const d=JSON.parse(fs.readFileSync(0,'utf8')),model=JSON.parse(fs.readFileSync(d.path,'utf8')),rt=new RuntimeText(model);
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
const descriptions=[],excluded=[];
for(const row of d.descriptions) {
 const a=row.texts.en,b=row.texts.ja,p=model.details.pairs[a];
 if(!p||p[0]!==a||p[1]!==b)excluded.push({key:row.key,reason:!b?'missing_language':'ambiguous_or_not_admitted'});
 else if(!descriptions.some(r=>r.texts.en.split(/\n/).length===a.split(/\n/).length&&r.texts.ja.split(/\n/).length===b.split(/\n/).length))descriptions.push(row);
}
assert.ok(descriptions.length,'no complete real description');
let tested=0,negativeCases=0,maxCold=0;const failed=[],examples=[];
for(const entry of d.inline)for(const value of [1,4,30])for(const joined of [false,true])for(const desc of descriptions) {
 const original=entry.texts.en.replace(/%d/g,String(value)),target=entry.texts.ja.replace(/%d/g,String(value));
 const tail=joined?'<c698>'+d.separator.en+d.hp.en+d.separator.en+d.cp.en+'</C>':'';
 const targetTail=joined?'<c698>'+d.separator.ja+d.hp.ja+d.separator.ja+d.cp.ja+'</C>':'';
 const header=original+tail,expectedHeader=target+targetTail,source=header+'\n<C0>'+desc.texts.en;
 const expected=expectedHeader+'\n<C0>'+desc.texts.ja;
 tested++;
 try {
  assert.equal(rt.translate(source,'primary'),source);assert.equal(rt.translate(source,'secondary'),expected);
  const start=performance.now(),plan=rt.render(source);maxCold=Math.max(maxCold,performance.now()-start);
  assert.equal(plan.text.replace(/<R><\/R_>/g,''),source,'primary bytes');
  assert.ok(plan.layers.length,'whole coloured/icon header must retain native lane');
  const effects=plan.layers.filter(l=>l.semantic_ids);
  assert.equal(effects.length,joined?3:1,'independent effects must own independent anchors');
  assert.equal(visible(effects.map(l=>l.text).join('')),visible(expectedHeader.split(d.separator.ja).join('')));
  const body=plan.layers.filter(l=>!l.semantic_ids).map(l=>l.text).join('');
  // Raw placeholder rows such as --- are part of the denominator, but
  // punctuation-only width variants intentionally receive no annotation.
  assert.equal(visible(body),/\p{L}/u.test(visible(desc.texts.ja))?visible(desc.texts.ja):'');
  assert.ok(plan.layers.filter(l=>!l.semantic_ids).every(l=>!l.text.includes(d.cp.ja)||desc.texts.ja.includes(d.cp.ja)),'effect leaked to description');
  assert.deepEqual(rt.render(source),plan,'repeat rendering stable');
  if(examples.length<5)examples.push({key:entry.key,description_key:desc.key,source,expected,plan});
 } catch(error) {failed.push({key:entry.key,description_key:desc.key,source,expected,reason:error.message});}
}
const known=descriptions[0];
for(const member of [', UNKNOWN, HP Regen',', STR<I999> (4 turns), HP Regen']) {
 const source='<c698>'+member+'</C>\n<C0>'+known.texts.en;negativeCases++;
 assert.equal(rt.translate(source,'secondary').split('\n')[0],source.split('\n')[0],'unknown list cannot borrow scope');
}
const naked=rt.translate(d.hp.en,'secondary');assert.equal(naked,d.hp.en,'global HP conflict remains denied');negativeCases++;
console.log(JSON.stringify({tested,negative_cases:negativeCases,max_cold_render_ms:maxCold,real_mismatched_description_available:descriptions.some(r=>r.texts.en.split('\n').length!==r.texts.ja.split('\n').length),description_shapes:descriptions.map(r=>({key:r.key,en_lines:r.texts.en.split('\n').length,ja_lines:r.texts.ja.split('\n').length})),excluded_descriptions:excluded,examples,failures:failed,passed:!failed.length}));
"""


def check(game, directory):
    entries = json.loads((directory / "full/catalog.json").read_text("utf-8"))["entries"]
    catalog = {e["key"]: e["texts"] for e in entries}
    census = raw_resource_audit(game, catalog)
    grammar = build_item_help_grammar(game, entries, "en", languages=("en", "ja"))
    inline = [e for e in grammar["detail_entries"] if e.get("detail_inline_icon")]
    assert inline

    def label(value):
        rows = [
            e
            for e in entries
            if e["key"].startswith("table/t_itemhelp.tbl/SkillEffectHelpData/")
            and e["key"].endswith("/name")
            and e["texts"].get("en") == value
        ]
        assert rows and len({e["texts"]["ja"] for e in rows}) == 1
        return rows[0]["texts"]

    path = next(
        r["path"]
        for r in json.loads((directory / "full-model-builds.json").read_text("utf-8"))
        if r["config"]
        == {"game_language": "en", "primary": "en", "secondary": "ja", "scope": "all"}
    )
    descriptions = [
        e
        for e in entries
        if e["key"].startswith("table/t_skill.tbl/")
        and e["key"].endswith("/description")
        and e["texts"].get("en")
        and e["texts"].get("ja")
        and "%" not in e["texts"]["en"] + e["texts"]["ja"]
    ]
    data = {
        "path": path,
        "inline": inline,
        "descriptions": descriptions,
        "hp": label("HP Regen"),
        "cp": label("CP Regen"),
        "separator": catalog["table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"],
    }
    result = subprocess.run(
        ["node", "-e", RUNNER],
        cwd=ROOT,
        input=json.dumps(data),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    replay = json.loads(result.stdout)
    report = {
        "game_attached": False,
        "raw_resource_audit": census,
        "constructor_audit": grammar["audit"],
        "real_descriptions_in_denominator": len(descriptions),
        "inline_templates": len(inline),
        "combinations_are_contract_probes": True,
        "replay": replay,
    }
    (directory / "effect-layout-resources.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    print(
        json.dumps(
            {
                "templates": len(inline),
                "cases": replay["tested"],
                "failures": len(replay["failures"]),
                "max_cold_render_ms": replay["max_cold_render_ms"],
            }
        ),
        flush=True,
    )
    assert replay["passed"], str(directory / "effect-layout-resources.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.evidence_dir.resolve()
    if not directory.is_relative_to(ROOT) or directory == ROOT:
        raise ValueError("evidence must stay inside project")
    check(args.game_dir, directory)
