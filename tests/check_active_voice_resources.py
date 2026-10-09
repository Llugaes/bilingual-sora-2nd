"""Audit every installed ActiveVoice row and replay real table-pointer models.

Reads PAC/EXE inputs only. All output stays under the caller's project folder.
The JS memory relocation checks the production identity/render path, not a
live game process or the user's original screenshot configuration.
"""

from collections import Counter
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_tables import SCHEMAS, sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive, LANGUAGES
from sora_bilingual.localization.runtime_identity import compile_table_identities
from sora_bilingual.localization.table_alignment import align_record_sections
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

RUNNER = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {TableIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),model=input.model||JSON.parse(fs.readFileSync(input.model_path,'utf8'));
const ids=new TableIdentities(model.table_identities),files=new Map();
const base=0x100000,counts={cases:0,pointer_selected:0,global_selected:0,annotated:0,equal_pair:0};
const globalRuntime=new RuntimeText(model);
for(const [hash,raw] of Object.entries(input.files))files.set(hash,Buffer.from(raw,'base64'));
for(const candidates of Object.values(model.table_identities.sources))for(const c of candidates){
 const data=files.get(c.file);if(data)data.writeBigUInt64LE(BigInt(base+c.offset),c.record_at+c.field_at);
}
class Pointer {
 constructor(data,address){this.data=data;this.address=address;}
 add(n){return new Pointer(this.data,this.address+n);}
 equals(p){return this.data===p.data&&this.address===p.address;}
 toString(){return this.address.toString(16);}
 readByteArray(n){const at=this.address-base;if(at<0||at+n>this.data.length)throw Error('unmapped');return Uint8Array.from(this.data.subarray(at,at+n)).buffer;}
 readPointer(){return new Pointer(this.data,Number(this.data.readBigUInt64LE(this.address-base)));}
}
const targeted=[],failures=[];
for(const c of input.cases){
 counts.cases++;
 try {
  const candidate=(model.table_identities.sources[c.source]||[]).find(x=>x.key===c.key);
  let rt;
  if(input.complete_model&&globalRuntime.translate(c.source,'primary')===c.primary&&globalRuntime.translate(c.source,'secondary')===c.secondary) {
   rt=globalRuntime;counts.global_selected++;
  } else {
   assert.ok(candidate,'missing physical source identity');
   const selected=ids.select(new Pointer(files.get(candidate.file),base+candidate.offset),c.source);
   assert.ok(selected,'pointer rejected');counts.pointer_selected++;
   rt=new RuntimeText(selected.model);
  }
  for(const mode of ['primary','secondary'])assert.equal(rt.translate(c.source,mode),c[mode],mode);
  const plan=rt.render(c.source);
  if(c.primary===c.secondary)counts.equal_pair++;
  else {assert.ok(plan.kind==='ruby'||plan.layers.length,'missing secondary annotation');counts.annotated++;}
  if(c.key.includes('/group:540/')||c.key.includes('/group:541/'))
   targeted.push({key:c.key,source:c.source,route:rt===globalRuntime?'global':'table_pointer',identity:candidate?{file:candidate.file,record_at:candidate.record_at,field_at:candidate.field_at}:null,plan});
 } catch(error) {failures.push({key:c.key,source:c.source,reason:error.message});}
}
process.stdout.write(JSON.stringify({counts,failures,targeted}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--complete-model", type=Path, help="Fresh all-scope zh-Hans/ja/zh-Hans production model"
    )
    parser.add_argument("--dev-dir", type=Path, default=ROOT)
    parser.add_argument("--source-language", default="zh-Hans", choices=LANGUAGES)
    parser.add_argument("--primary", default="ja", choices=LANGUAGES)
    parser.add_argument("--secondary", default=None, choices=LANGUAGES)
    parser.add_argument("--only-complete", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("evidence output must be inside the project")
    files, census = {}, {}
    for language in LANGUAGES:
        with FpacArchive(args.game_dir / "pac/steam" / _TABLE_ARCHIVES[language]) as archive:
            data = archive.read(_logical_tables(archive)["table/t_active_voice.tbl"])
        files[language] = data
        _, start, stride, count = sections(data)[0]
        groups = Counter(
            struct.unpack_from("<I", data, start + row * stride)[0] for row in range(count)
        )
        # This denominator comes from raw descriptors/rows, independently of
        # discovery/alignment output, and includes blank or rejected rows.
        census[language] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "physical_rows": count,
            "groups": len(groups),
            "group_540": groups[540],
            "group_541": groups[541],
        }
    audit = {"counters": Counter(), "diagnostics": []}
    entries = align_record_sections(
        files,
        {l: sections(d) for l, d in files.items()},
        SCHEMAS["ActiveVoiceTableData"],
        path="table/t_active_voice.tbl",
        prefix="table/t_active_voice.tbl",
        kind="ActiveVoiceTableData",
        occurrence=0,
        audit=audit,
    )
    assert all(set(e["texts"]) == set(LANGUAGES) for e in entries)
    assert all(len(entries) == c["physical_rows"] for c in census.values())
    assert len([e for e in entries if "/group:541/" in e["key"]]) == 4
    assert len([e for e in entries if "/group:540/" in e["key"]]) == 4
    results = []
    for source in () if args.only_complete else LANGUAGES:
        tr = MenuTranslator(entries, "ja", "zh-Hans", source)
        model = tr.runtime_model()
        # Force every row through the real identity seam, even where global
        # text happens to be unique and would otherwise hide a broken pointer.
        model["table_identities"] = compile_table_identities(
            args.game_dir, entries, "ja", "zh-Hans", source, resolved_pairs={}
        )
        cases = [
            dict(
                key=e["key"],
                source=e["texts"][source],
                primary=e["texts"]["ja"],
                secondary=e["texts"]["zh-Hans"],
            )
            for e in entries
        ]
        run = subprocess.run(
            ["node", "--max-old-space-size=6144", "-e", RUNNER],
            cwd=args.dev_dir.resolve(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            input=json.dumps(
                {
                    "model": model,
                    "cases": cases,
                    "files": {
                        hashlib.sha256(files[source]).hexdigest(): base64.b64encode(
                            files[source]
                        ).decode()
                    },
                }
            ),
        )
        results.append(
            {
                "source_language": source,
                "primary": "ja",
                "secondary": "zh-Hans",
                **json.loads(run.stdout),
            }
        )
    report = {
        "evidence_kind": "offline_real_pac_pointer_and_renderer_replay",
        "live_game_verified": False,
        "raw_census": census,
        "aligned_records": len(entries),
        "audit": {**audit, "counters": dict(audit["counters"])},
        "results": results,
    }
    if args.complete_model:
        source = args.source_language
        primary, secondary = args.primary, args.secondary or source
        run = subprocess.run(
            ["node", "--max-old-space-size=6144", "-e", RUNNER],
            cwd=args.dev_dir.resolve(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            input=json.dumps(
                {
                    "complete_model": True,
                    "model_path": str(args.complete_model.resolve()),
                    "cases": [
                        dict(
                            key=e["key"],
                            source=e["texts"][source],
                            primary=e["texts"][primary],
                            secondary=e["texts"][secondary],
                        )
                        for e in entries
                    ],
                    "files": {
                        hashlib.sha256(files[source]).hexdigest(): base64.b64encode(
                            files[source]
                        ).decode()
                    },
                }
            ),
        )
        report["complete_model"] = {
            "path": str(args.complete_model.resolve()),
            "sha256": hashlib.sha256(args.complete_model.read_bytes()).hexdigest(),
            "source_language": source,
            "primary": primary,
            "secondary": secondary,
            **json.loads(run.stdout),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "aligned": len(entries),
                "raw_rows": sum(c["physical_rows"] for c in census.values()),
                "cases": sum(r["counts"]["cases"] for r in results),
                "failures": sum(len(r["failures"]) for r in results),
                "complete_model_failures": len(
                    report.get("complete_model", {}).get("failures", [])
                ),
            },
            ensure_ascii=False,
        )
    )
    return int(
        any(r["failures"] for r in results)
        or bool(report.get("complete_model", {}).get("failures"))
    )


if __name__ == "__main__":
    raise SystemExit(main())
