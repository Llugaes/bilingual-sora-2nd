"""Raw ActiveVoice peer oracle without align_record_sections or MenuTranslator.

Expected bodies come from unique raw actor/condition/voice metadata peers. The
separately proved localized replay +80 array is retained in evidence and is not
part of display peer identity. No unknown/multiple peer is guessed. Pointer
replay is a contract probe, not evidence of a live widget's input carrier.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


def text(data, pointer):
    if not pointer:
        return ""
    assert 0 <= pointer < len(data)
    return data[pointer : data.index(b"\0", pointer)].decode("utf-8")


def collect(game):
    peers, receipts, files, denominators = defaultdict(dict), [], {}, {}
    for locale, name in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / name) as archive:
            data = archive.read(_logical_tables(archive)["table/t_active_voice.tbl"])
        assert data[:4] == b"#TBL"
        signature = hashlib.sha256(data).hexdigest()
        files[signature] = data
        count = 0
        for descriptor in range(struct.unpack_from("<I", data, 4)[0]):
            at = 8 + descriptor * 80
            if data[at : at + 64].split(b"\0")[0] != b"ActiveVoiceTableData":
                continue
            start, stride, length = struct.unpack_from("<III", data, at + 68)
            assert stride == 128 and start + stride * length <= len(data)
            for ordinal in range(length):
                row = start + stride * ordinal
                arrays = {}
                for offset, width in ((8, 2), (48, 2), (64, 2), (80, 2), (96, 4)):
                    pointer, size = struct.unpack_from("<QQ", data, row + offset)
                    assert size <= 4096 and (
                        not size or start + stride * length <= pointer <= len(data) - size * width
                    )
                    arrays[offset] = data[pointer : pointer + size * width].hex()
                strings = {
                    offset: text(data, struct.unpack_from("<Q", data, row + offset)[0])
                    for offset in (24, 40, 112)
                }
                identity = {
                    "scalars": [
                        data[row : row + 8].hex(),
                        data[row + 32 : row + 40].hex(),
                        data[row + 120 : row + 128].hex(),
                    ],
                    "strings": [strings[24], strings[40]],
                    "actor_condition_voice_arrays": {str(k): arrays[k] for k in (8, 48, 64, 96)},
                }
                key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                peers[key].setdefault(locale, []).append(
                    {
                        "body": strings[112],
                        "identity": identity,
                        "group": struct.unpack_from("<I", data, row)[0],
                        "record_at": row,
                        "physical": ordinal,
                        "string_offset": struct.unpack_from("<Q", data, row + 112)[0],
                        "file_sha256": signature,
                        "replay_array_80_retained": arrays[80],
                    }
                )
                count += 1
        denominators[locale] = count
        receipts.append({"locale": locale, "sha256": signature, "physical_records": count})
    return peers, files, receipts, denominators


RUNNER = r"""
const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8')),
{RuntimeText}=require(d.dev+'/sora_bilingual/game/scripts/runtime_text.js'),
{TableIdentities}=require(d.dev+'/sora_bilingual/game/scripts/runtime_identity.js');
const model=JSON.parse(fs.readFileSync(d.model.path,'utf8')),t=new RuntimeText(model),ids=new TableIdentities(model.table_identities);
const base=0x100000,files=new Map(Object.entries(d.files).map(([sha,path])=>[sha,fs.readFileSync(path)]));
for(const candidates of Object.values(model.table_identities.sources))for(const c of candidates) {
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
const rows=[],failures=[],counts={pass:0,equal:0,global:0,pointer:0,refused:0};
for(const c of d.cases) {
 const source=c.source.body,expected=c.expected;
 const pair=[t.translate(source,'primary'),t.translate(source,'secondary')],globalPass=JSON.stringify(pair)===JSON.stringify(expected);
 const candidates=(model.table_identities.sources[source]||[]).filter(x=>x.file===c.source.file_sha256&&x.record_at===c.source.record_at&&x.field_at===112);
 let selected=null,localPair=null;
 if(candidates.length)selected=ids.select(new Pointer(files.get(c.source.file_sha256),base+c.source.string_offset),source);
 if(selected){const tr=new RuntimeText(selected.model);localPair=[tr.translate(source,'primary'),tr.translate(source,'secondary')];}
 const pointerPass=localPair&&JSON.stringify(localPair)===JSON.stringify(expected);
 if(selected&&!pointerPass)failures.push({id:c.id,source,expected,actual:localPair,reason:'wrong independent pointer targets'});
 if(pair.some((value,side)=>value!==source&&value!==expected[side]))failures.push({id:c.id,source,expected,actual:pair,reason:'wrong independent global targets'});
 const pass=globalPass||pointerPass;if(pass)counts.pass++;else counts.refused++;
 if(expected.every(v=>v===source))counts.equal++;
 if(globalPass)counts.global++;if(pointerPass)counts.pointer++;
 if(c.source.group===540||c.source.group===541||!pass)rows.push({...c,source_text:source,global_pair:pair,pointer_pair:localPair,
  pointer_candidate_keys:candidates.map(v=>v.key),pass:!!pass,actual_pointer_carrier:'pending',reason:pass?'raw_metadata_peers_match':'unassociated_or_shared_pool_conflict'});
}
process.stdout.write(JSON.stringify({counts,rows,failures,passed:failures.length===0}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    out = a.out.resolve()
    assert out.is_relative_to(PROJECT) and out != PROJECT
    peers, files, receipts, denominators = collect(a.game)
    blobs = out / "independent-active-voice-blobs"
    assert not blobs.exists()
    blobs.mkdir()
    paths = {}
    for sha, data in files.items():
        path = blobs / (sha + ".bin")
        path.write_bytes(data)
        paths[sha] = str(path)
    models = json.loads((out / "full-model-builds.json").read_text("utf-8"))
    summaries = []
    for model in models:
        cfg = model["config"]
        langs = [cfg[k] for k in ("game_language", "primary", "secondary")]
        cases, raw_refusals = [], []
        for key, locales in peers.items():
            if any(len(locales.get(locale, ())) != 1 for locale in langs):
                raw_refusals.append(
                    {
                        "id": key,
                        "reason": "missing_or_multiple_raw_metadata_peer",
                        "locale_counts": {l: len(v) for l, v in locales.items()},
                    }
                )
                continue
            source = locales[langs[0]][0]
            cases.append(
                {
                    "id": f"table/t_active_voice.tbl/raw:{key}/group:{source['group']}",
                    "source": source,
                    "expected": [locales[l][0]["body"] for l in langs[1:]],
                }
            )
        result = subprocess.run(
            ["node", "--max-old-space-size=6144", "-e", RUNNER],
            cwd=a.dev,
            input=json.dumps(
                {"model": model, "files": paths, "cases": cases, "dev": str(a.dev.resolve())},
                ensure_ascii=False,
            ),
            capture_output=True,
            encoding="utf-8",
            check=True,
        )
        report = json.loads(result.stdout)
        report.update(
            config=cfg,
            model_sha256=model["sha256"],
            physical_denominators=denominators,
            eligible=len(cases),
            raw_refusals=raw_refusals,
            raw_receipts=receipts,
            oracle="unique raw scalar/string/actor/condition/voice metadata; no production pairing for expected",
            actual_live_control_or_game_validation="pending",
        )
        name = "voice-independent-" + "-".join(langs) + ".json"
        (out / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        summaries.append(
            {
                "config": cfg,
                "eligible": len(cases),
                "raw_refused": len(raw_refusals),
                "counts": report["counts"],
                "failures": report["failures"],
                "report": name,
            }
        )
        print(json.dumps(summaries[-1], ensure_ascii=False), flush=True)
    (out / "voice-independent-summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), "utf-8"
    )
    assert all(not row["failures"] for row in summaries), "Wrong independent active voice pairing"


if __name__ == "__main__":
    main()
