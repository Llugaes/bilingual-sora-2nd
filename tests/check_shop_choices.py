"""Native selector keys -> original eight-locale resource -> keyed render oracle."""

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capstone
import pefile

from sora_bilingual.config.locales import archive_names
from sora_bilingual.game.native_contracts import resolve_native_contracts
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables
from tools.audit_title_name_families import raw_sections, raw_text


def check(game, catalog):
    with pefile.PE(str(game / "sora_2nd.exe"), fast_load=True) as pe:
        resolved = resolve_native_contracts(pe)
        start = resolved["functions"]["shop_action_copy"]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        instructions = list(md.disasm(pe.get_data(start, 596), start))
        hashes = {
            i.operands[1].imm & 0xFFFFFFFF
            for i in instructions
            if i.mnemonic == "mov"
            and i.op_str.startswith("dword ptr [rsp +")
            and i.operands[1].type == capstone.x86.X86_OP_IMM
            and i.operands[1].imm > 0xFF
        }
        for ins in instructions:
            if ins.mnemonic == "lea" and ins.op_str.startswith("rcx, [rip"):
                tail = pe.get_string_at_rva(
                    ins.address + ins.size + ins.operands[1].mem.disp
                ).decode("ascii")
                assert tail.startswith("XT_SHOP_")
                hashes.add(zlib.crc32(("T" + tail).encode()) ^ 0xFFFFFFFF)
    raw = {}
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_text.tbl"])
        headers = raw_sections(data)
        floor = max(s + z * n for _, s, z, n in headers)
        rows = {}
        for _, start, stride, count in headers:
            assert stride == 16
            for n in range(count):
                key = raw_text(data, struct.unpack_from("<Q", data, start + n * stride)[0], floor)
                if zlib.crc32(key.encode()) ^ 0xFFFFFFFF in hashes:
                    assert key not in rows
                    rows[key] = raw_text(
                        data, struct.unpack_from("<Q", data, start + n * stride + 8)[0], floor
                    )
        assert len(rows) == len(hashes), "native selected hash must have exactly one resource key"
        raw[locale] = rows
    assert all(set(r) == set(raw["en"]) for r in raw.values())
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    selected = [e for e in entries if e["key"].removeprefix("table/t_text.tbl/") in raw["en"]]
    assert Counter(tuple(raw[l][key] for l in raw) for key in raw["en"]) == Counter(
        tuple(e["texts"].get(l) for l in raw) for e in selected
    )
    # Keep all original source homonyms, including ItemKind and script Cancel.
    values = {v for r in raw.values() for v in r.values()}
    related = [e for e in entries if any(v in values for v in e["texts"].values())]
    configs = [(s, s, t) for s in raw for t in raw] + [("en", "zh-Hans", "ja")]
    payload = []
    for source, primary, secondary in configs:
        tr = MenuTranslator(related, primary, secondary, source)
        cases = [
            {"key": key, "source": text, "pair": [raw[primary][key], raw[secondary][key]]}
            for key, text in raw[source].items()
        ]
        payload.append({"model": tr.runtime_model(), "cases": cases})
    runner = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));const failures=[];let checked=0;
for(const row of rows){const tr=new RuntimeText(row.model);for(const c of row.cases){
 const p=tr.translate(c.source,'primary',c.key),s=tr.translate(c.source,'secondary',c.key),plan=tr.render(c.source,'annotation',c.key);
 const payload=plan.layers.map(v=>v.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 if(p!==c.pair[0]||s!==c.pair[1]||!row.model.same_language&&RuntimeText.needsAnnotation(...c.pair)&&!payload.includes(c.pair[1]))failures.push({...c,p,s,plan});checked++;
}}
process.stdout.write(JSON.stringify({checked,failures}));
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        check=True,
    )
    rendered = json.loads(result.stdout)
    assert not rendered["failures"], rendered["failures"][:2]
    return {
        "resource_keys": sorted(raw["en"]),
        "locale_configs": len(configs),
        "render": rendered,
        "observed_keys": {
            key: {l: raw[l][key] for l in ("en", "zh-Hans", "ja")} for key in raw["en"]
        },
        "limits": [
            "Physical denominator derives from the verified native selector constants and key literal CRC, not a screenshot word whitelist.",
            "Keyed model/render is separate from actual register/copy callback execution and live game acceptance.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    report = check(a.game, a.catalog)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "keys": len(report["resource_keys"]),
                "configs": report["locale_configs"],
                **report["render"],
            }
        )
    )
