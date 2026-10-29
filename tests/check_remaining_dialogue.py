"""Replay remaining raw VM operands through production callbacks and full models.

The callback harness uses pointer fixtures, not a running game. Actual machine
code semantics are checked separately by check_nested_return_native.py.
"""

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
from sora_bilingual.localization.dynamic_identity import _count_panel_site, _function_code
from sora_bilingual.localization.resources import FpacArchive, _logical_script_entries
from sora_bilingual.localization.runtime_identity import script_signature


RUNNER = r"""
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(input.model,'utf8'));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities}=require('../sora_bilingual/game/scripts/runtime_identity.js');
let cases=0;const failures=[];
const visible=s=>RuntimeText.visualSecondary(s).replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const row of input.rows)try {
  const r=makeRuntime(),label=r.label(0xa000,''),history=r.label(0xb000,'');
  const data=Buffer.from(row.blob,'base64'),ids=new ScriptIdentities(model.script_identities);
  const identity=ids.capture(row.signature,n=>data.subarray(0,n),row.fn,row.token,row.site,row.source);
  assert.equal(identity?.recordKey,row.key,'physical identity');
  const pair=ids.lookup(identity,row.source),tr=new RuntimeText(pair.model);
  assert.equal(tr.translate(row.source,'secondary'),row.texts.ja);
  // Capture before any local resolver exists, then reload the complete model.
  const manifest={source_language:model.script_identities.source_language,manifest:model.script_identities.manifest};
  r.api.load({pairs:{},plain_pairs:{},numeric:[],script_identities:manifest},'primary',true,1);
  r.dialogueSet(label,row.source,data,row.fn,row.token.split(',').map(Number),undefined,row.site);
  r.api.load(model,'secondary',true,1);r.update(label);
  assert.equal(label.text(),row.texts.ja,'retained identity after model reload');cases++;
  for(const mode of ['primary','secondary','annotation']) {
    r.api.select(mode,true);
    // Panels do not enter the talk log. Dialogue records use the actual writer.
    const slot=row.panel?undefined:3;
    r.dialogueSet(label,row.source,data,row.fn,row.token.split(',').map(Number),slot,row.site);
    if(mode==='primary')assert.equal(label.text(),row.texts['zh-Hans']);
    if(mode==='secondary')assert.equal(label.text(),row.texts.ja);
    if(mode==='annotation') {
      const snapshot=r.api.snapshot().find(v=>v.original===row.source);
      const payload=snapshot.layers.map(v=>v.text).join('')+[...label.text().matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(v=>v[1]==='_'?'':v[1]).join('');
      assert.equal(visible(payload),visible(row.texts.ja),'full visible secondary');
    }
    if(slot!==undefined) {
      r.logShow(history,slot,row.source);
      assert.equal(history.text(),label.text(),'stored history display');
      const measurement=r.logMeasure([['',row.source,slot]]);
      // Cached heights skip setter calls; first use checks its rendered body.
      if(measurement.setters)assert.equal(measurement.bodies[0],label.text(),'stored history measurement');
      assert.ok(measurement.heights[0]>0,'stored history height');
      cases+=2;
    }
    cases++;
  }
  r.api.disable();r.update(label);assert.equal(label.text(),row.source);cases++;
  if(row.panel)for(const probe of row.bad) {
    assert.notEqual(ids.capture(row.signature,n=>data.subarray(0,n),row.fn,probe.token,row.site,probe.source)?.recordKey,row.key,'unproved count source');cases++;
  }
  assert.equal(r.api.status().failed,false);
} catch(error) {failures.push({key:row.key,reason:error.message,stack:error.stack});}
process.stdout.write(JSON.stringify({rows:input.rows.length,cases,failures,passed:!failures.length,game_attached:false}));
"""


def panel_rows(game, directory):
    entries = json.loads((directory / "catalog.json").read_bytes())["entries"]
    selected = [
        e for e in entries if e.get("dynamic_producer", {}).get("family") == "item_count_panel"
    ]
    result = []
    with FpacArchive(game / "pac/steam/script_sc.pac") as archive:
        paths = _logical_script_entries(archive)
        for entry in selected:
            origin = entry["producer_origin"]["signature"]
            data = archive.read(paths[origin["path"]])
            fn, called = origin["function"], entry["called_ids"]["zh-Hans"]
            tokens, slots, pc = _count_panel_site(data, fn, called, _function_code(data, fn)[0])
            for counts in ([0] * 7, [1, 2, 10, 99, 999, 9999, 99999], [999999] * 7):
                values = tuple(v for i, n in enumerate(counts) for v in (110 + i, n))
                raw = list(tokens)
                for slot, number in zip(slots, counts, strict=True):
                    raw[slot["slot"]] = str(0x40000000 + number)
                source = entry["texts"]["zh-Hans"] % values
                bad = []
                for slot in slots:
                    for change in (1, -0x40000000, 0x40000000):
                        changed = list(raw)
                        changed[slot["slot"]] = str(int(changed[slot["slot"]]) + change)
                        bad.append({"source": source, "token": ",".join(changed)})
                result.append(
                    {
                        "key": entry["key"],
                        "fn": fn,
                        "panel": True,
                        "blob": base64.b64encode(data).decode(),
                        "signature": script_signature(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                        "token": ",".join(raw),
                        "site": {"pc": pc, "group": 5, "command": 8},
                        "source": source,
                        "texts": {lang: text % values for lang, text in entry["texts"].items()},
                        "bad": bad,
                    }
                )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    directory = args.model_dir
    specs = json.loads((directory / "full-model-builds.json").read_text("utf-8"))
    rows = json.loads((directory / "control-dialogue-raw-cases.json").read_text("utf-8"))
    selected = []
    # A raw metadata tag 1 distinguishes nested helper operands from variables.
    for row in rows:
        raw = base64.b64decode(row["blob"])
        start, count = struct.unpack_from("<II", raw, 4)
        for number in range(count):
            at = start + number * 32
            name = struct.unpack_from("<I", raw, at + 28)[0] & 0x3FFFFFFF
            if raw[name : raw.index(b"\0", name)].decode() != row["fn"]:
                continue
            calls = struct.unpack_from("<I", raw, at + 20)[0]
            argc, arguments = struct.unpack_from("<HI", raw, calls + row["called"] * 12 + 6)
            if any(
                struct.unpack_from("<I", raw, arguments + i * 8 + 4)[0] == 1 for i in range(argc)
            ):
                selected.append(row)
            break
    selected += panel_rows(args.game_dir, directory)
    assert len({r["key"] for r in selected}) == 14
    (directory / "remaining-dialogue-input.json").write_text(
        json.dumps(selected, ensure_ascii=False), "utf-8"
    )
    harness = (ROOT / "tests/test_native_agent.js").read_text("utf-8").split("\ntest(", 1)[0]
    script = directory / "remaining-dialogue-callbacks.cjs"
    script.write_text(harness + RUNNER, "utf-8")
    process = subprocess.run(
        [
            "node",
            "--max-old-space-size=4096",
            "-e",
            "eval(require('node:fs').readFileSync(process.argv[1],'utf8'))",
            str(script.resolve()),
        ],
        cwd=ROOT / "tests",
        input=json.dumps({"model": specs[0]["path"], "rows": selected}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    report = json.loads(process.stdout)
    (directory / "remaining-dialogue-callbacks.json").write_text(
        json.dumps(report, indent=2), "utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
