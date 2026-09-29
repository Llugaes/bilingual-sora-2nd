"""Replay every complete physical speaker setter against full production models.

Reads installed script bytes; never attaches to the game. The voice-family
subset is reported separately, not used as an admission whitelist.
"""

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
import pefile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import archive_names
from sora_bilingual.game.hooks import verify_target
from sora_bilingual.localization.resources import FpacArchive, _logical_script_entries, _utf8z
from sora_bilingual.localization.runtime_identity import _speaker_setter_catalog_records

RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const data=JSON.parse(fs.readFileSync(0,'utf8')),model=JSON.parse(fs.readFileSync(data.model,'utf8'));
const global=new RuntimeText(model),ids=new ScriptIdentities(model.script_identities);
const blobs=Object.fromEntries(Object.entries(data.blobs).map(([k,v])=>[k,Buffer.from(v,'base64')]));
class Pointer {
 constructor(path,at){this.path=path;this.at=at;}
 add(n){return new Pointer(this.path,this.at+n);}
 toString(){return this.path+':'+this.at;}
 readByteArray(n){const b=blobs[this.path];if(this.at<0||this.at+n>b.length)throw Error('bounds');return b.subarray(this.at,this.at+n);}
}
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
const results=data.cases.map(c=>{
 const local=ids.pointerSelect(new Pointer(c.path,c.offset),c.source),r=local?new RuntimeText(local.model):global;
 const primary=r.translate(c.source,'primary'),secondary=r.translate(c.source,'secondary');
 const plan=r.render(c.source,'annotation'),payload=plan.layers.map(l=>l.text).join('')+
  [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 const pass=primary===c.pair[0]&&secondary===c.pair[1]&&
  (!RuntimeText.needsAnnotation(...c.pair)||visible(payload)===visible(RuntimeText.visualSecondary(c.pair[1])));
 return {...c,path:undefined,offset:undefined,route:local?'script_pointer':'global',pass,...(!pass?{primary,secondary,plan}:{})};
});
process.stdout.write(JSON.stringify(results));
"""


def native_name_contract(exe):
    verify_target(exe)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    # These UI sites pass actor_name_get's original owned pointer directly to
    # SetText. No reconstructed name or global-current-actor assumption.
    expected = {
        0x217ED6: "cmp dword ptr [rcx + 0x2cc], 0",
        0x217EE2: "mov rax, qword ptr [rcx + 0x2c0]",
        0x217FD6: "mov rcx, qword ptr [rdi + 0x2c0]",
        0x217FE5: "mov rdx, rsi",
        0x217FE8: "call 0x87a700",
        0x544AD4: "call 0x217ed0",
        0x544AD9: "mov rsi, rax",
        0x544C51: "mov rdx, rsi",
        0x544C54: "call 0x588a40",
        0x53974F: "call 0x217ed0",
        0x539754: "mov rdx, rax",
        0x53975A: "call 0x588a40",
        0x54C535: "call 0x217ed0",
        0x54C53A: "mov rdx, rax",
        0x54C540: "call 0x588a40",
        0x54C895: "call 0x217ed0",
        0x54C89A: "mov rdx, rax",
        0x54C8A0: "call 0x588a40",
    }
    with pefile.PE(str(exe), fast_load=True) as pe:
        for rva, instruction in expected.items():
            item = next(decoder.disasm(pe.get_data(rva, 16), rva))
            assert item.mnemonic + " " + item.op_str == instruction, hex(rva)
    return {hex(rva): instruction for rva, instruction in expected.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--status-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads((ROOT / "generated/catalog.json").read_text("utf-8"))["entries"]
    native_contract = native_name_contract(args.game_dir / "sora_2nd.exe")
    modes = json.loads(args.status_audit.read_text("utf-8"))["modes"]
    reports = []
    for mode in modes:
        records = _speaker_setter_catalog_records(entries, mode["primary"], mode["secondary"])
        source_records = _speaker_setter_catalog_records(entries, mode["source"], mode["source"])
        unpaired = [
            {"key": f"{path}/{function}/called/{call}/arg/1", "source": value[0]}
            for physical, value in source_records.items()
            for locale, path, function, call in [physical]
            if locale == mode["source"] and physical not in records
        ]
        cases, blobs = [], {}
        with FpacArchive(
            args.game_dir / "pac/steam" / archive_names("script")[mode["source"]]
        ) as archive:
            logical = _logical_script_entries(archive)
            for (locale, path, function, call), (source, pair) in records.items():
                if locale != mode["source"]:
                    continue
                if path not in blobs:
                    blobs[path] = archive.read(logical[path])
                data = blobs[path]
                start, count = struct.unpack_from("<II", data, 4)
                at = next(
                    start + i * 32
                    for i in range(count)
                    if _utf8z(
                        data, struct.unpack_from("<I", data, start + i * 32 + 28)[0] & 0x3FFFFFFF
                    )
                    == function
                )
                call_count, calls_at = struct.unpack_from("<II", data, at + 16)
                assert call < call_count
                argc, argv = struct.unpack_from("<HI", data, calls_at + call * 12 + 6)
                value, kind = struct.unpack_from("<II", data, argv + 8)
                assert argc >= 2 and kind == 0 and value >> 30 == 3
                offset = value & 0x3FFFFFFF
                assert _utf8z(data, offset) == source
                cases.append(
                    dict(
                        key=f"{path}/{function}/called/{call}/arg/1",
                        path=path,
                        offset=offset,
                        source=source,
                        pair=pair,
                    )
                )
        result = subprocess.run(
            ["node", "-e", RUNNER],
            input=json.dumps(
                dict(
                    model=mode["model"],
                    cases=cases,
                    blobs={k: base64.b64encode(v).decode() for k, v in blobs.items()},
                )
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
            check=True,
        )
        rows = json.loads(result.stdout)
        voices = [r for r in rows if "声音" in r["source"]]
        report = dict(
            source=mode["source"],
            primary=mode["primary"],
            secondary=mode["secondary"],
            total=len(rows),
            routes=dict(Counter(r["route"] for r in rows)),
            voice_setters=len(voices),
            voice_labels=sorted({r["source"] for r in voices}),
            failures=[r for r in rows if not r["pass"]],
            unpaired_resource_setters=unpaired,
        )
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    args.output.write_text(
        json.dumps(
            dict(
                game_attached=False,
                native_contract=native_contract,
                scope="complete physical setters; incomplete or conflicting resource pairs are not certified",
                reports=reports,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    if any(r["failures"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
