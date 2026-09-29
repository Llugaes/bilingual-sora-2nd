"""Replay ordered table fields through full models and real table-pointer data.

Reads installed PAC bytes only. Never attaches to or starts the game. Native
pointer reads are emulated after relocating the actual table field pointers;
this validates the production JS selector, not the game's UI lifecycle.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables


RUNNER = r"""
const fs=require('fs');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {TableIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(input.model,'utf8'));
const global=new RuntimeText(model),ids=new TableIdentities(model.table_identities);
const memory=new Map(),base=0x100000;
for(const [file,raw] of Object.entries(input.files))memory.set(file,Buffer.from(raw,'base64'));
for(const candidates of Object.values(model.table_identities.sources))for(const c of candidates){
 const d=memory.get(c.file);if(d)d.writeBigUInt64LE(BigInt(base+c.offset),c.record_at+c.field_at);
}
class Pointer {
 constructor(data,address){this.data=data;this.address=address;}
 add(n){return new Pointer(this.data,this.address+n);}
 equals(other){return this.data===other.data&&this.address===other.address;}
 toString(){return this.address.toString(16);}
 readByteArray(n){const at=this.address-base;if(at<0||at+n>this.data.length)throw Error('unmapped');return Uint8Array.from(this.data.subarray(at,at+n)).buffer;}
 readPointer(){return new Pointer(this.data,Number(this.data.readBigUInt64LE(this.address-base)));}
}
const width=t=>t.replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0));
const equal=(a,b)=>a===b||width(a)===width(b);
const failures=[],counts={cases:0,global:0,table_pointer:0,ascii_width_only:0},timings=[];
for(const c of input.cases){
 const start=performance.now();let runtime=global,route='global';
 if(['primary','secondary'].some(mode=>!equal(global.translate(c.source,mode),c[mode]))){
  const candidate=(model.table_identities.sources[c.source]||[]).find(r=>r.key===c.key);
  const data=candidate&&memory.get(candidate.file);
  const selected=data&&ids.select(new Pointer(data,base+candidate.offset),c.source);
  if(selected){runtime=new RuntimeText(selected.model);route='table_pointer';}
 }
 counts.cases++;counts[route]++;
 for(const mode of ['primary','secondary']){
  const actual=runtime.translate(c.source,mode);
  if(!equal(actual,c[mode]))failures.push({key:c.key,source:c.source,mode,route,expected:c[mode],actual});
  else if(actual!==c[mode])counts.ascii_width_only++;
 }
 timings.push(performance.now()-start);
}
timings.sort((a,b)=>a-b);
process.stdout.write(JSON.stringify({counts,failures,ms:{p95:timings[Math.floor(timings.length*.95)],max:timings.at(-1)}}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads((ROOT / "generated/catalog.json").read_text("utf-8"))["entries"]
    entries = [e for e in entries if "table_rows" in e]
    files = {}
    with FpacArchive(args.game_dir / "pac/steam" / _TABLE_ARCHIVES["zh-Hans"]) as archive:
        wanted = {e["key"].split(".tbl", 1)[0] + ".tbl" for e in entries}
        for logical, path in _logical_tables(archive).items():
            if logical in wanted:
                data = archive.read(path)
                files[hashlib.sha256(data).hexdigest()] = base64.b64encode(data).decode()
    reports = []
    for config in json.loads(args.models.read_text("utf-8")):
        cases = [
            dict(
                key=e["key"],
                source=e["texts"]["zh-Hans"],
                primary=e["texts"][config["primary"]],
                secondary=e["texts"][config["secondary"]],
            )
            for e in entries
            if len(e["table_rows"].get("zh-Hans", [])) == 1
            and config["primary"] in e["texts"]
            and config["secondary"] in e["texts"]
        ]
        run = subprocess.run(
            ["node", "-e", RUNNER],
            input=json.dumps(dict(model=config["path"], cases=cases, files=files)),
            text=True,
            encoding="utf-8",
            capture_output=True,
            cwd=ROOT,
            check=True,
        )
        reports.append(dict(config=config, **json.loads(run.stdout)))
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            [
                dict(
                    config=r["config"], counts=r["counts"], failures=len(r["failures"]), ms=r["ms"]
                )
                for r in reports
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return int(any(r["failures"] for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
