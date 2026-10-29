"""Exercise official trailing-R history through the production log callbacks.

Use the complete contexts saved by the independent raw-resource history audit.
Only records fitting one native history slot are replayed here; the full
resource audit covers long bodies separately.
"""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNNER = r"""
const model={pairs:{},plain_pairs:{},numeric:[],...JSON.parse(fs.readFileSync(process.argv[2],'utf8'))};
const h=model.history_contexts,cases=[];let oversized=0,checks=0;const failures=[];
for(const [source,id] of Object.entries(h.texts)) {
 const chosen=id>=0?id:h.fallback_texts[source];
 if(!Number.isInteger(chosen)||chosen<0)continue;
 const pair=h.pairs[chosen];
 if(!source.includes('<R>')||source.includes('</R')||!pair[1].includes('<R>')||pair[1].includes('</R'))continue;
 if(Buffer.byteLength(source)>280){oversized++;continue;}
 cases.push({source,pair});
}
assert.ok(cases.length>0,'raw official trailing-R cases missing');
const visible=s=>s.replace(/<[^<>]*>|\s/g,'');
for(const row of cases)try {
 const r=makeRuntime(),label=r.label(0xa000,'');r.api.load(model,'annotation',true,1);
 r.logRestore(row.source,7,'');
 for(const mode of ['primary','secondary','annotation']) {
  r.api.select(mode,true);r.logShow(label,7,row.source);
  if(mode!=='annotation')assert.equal(label.text(),row.pair[mode==='primary'?0:1]);
  else {
   const snapshot=r.api.snapshot().find(v=>v.original===row.source);
   // Readings already present in the primary official text belong to that
   // original lane, not to the newly added secondary annotation.
   const native=[...row.pair[0].matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(v=>v[1]),added=[];
   for(const match of label.text().matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)) {
    const at=native.indexOf(match[1]);
    if(at>=0)native.splice(at,1);else if(match[1]!=='_')added.push(match[1]);
   }
   const payload=snapshot.layers.map(v=>v.text).join('')+added.join('');
   assert.equal(visible(payload),visible(row.pair[1]));
  }
  const measurement=r.logMeasure([['',row.source,7]]);
  if(measurement.setters)assert.equal(measurement.bodies[0],label.text());
  assert.ok(measurement.heights[0]>0);checks+=2;
 }
 r.api.disable();r.update(label);assert.equal(label.text(),row.source);checks++;
}catch(error){failures.push({source:row.source,reason:error.message,stack:error.stack});}
process.stdout.write(JSON.stringify({rows:cases.length,oversized_raw_bodies:oversized,checks,failures,passed:!failures.length,game_attached:false}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    harness = (ROOT / "tests/test_native_agent.js").read_text("utf-8").split("\ntest(", 1)[0]
    script = args.output.with_suffix(".cjs")
    script.write_text(harness + RUNNER, "utf-8")
    result = subprocess.run(
        [
            "node",
            "--max-old-space-size=4096",
            "-e",
            "eval(require('node:fs').readFileSync(process.argv[1],'utf8'))",
            str(script.resolve()),
            str(args.contexts.resolve()),
        ],
        cwd=ROOT / "tests",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    report = json.loads(result.stdout)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
