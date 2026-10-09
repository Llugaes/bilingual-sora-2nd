"""Independent physical item descriptions and installed printf consumer proof.

No catalog/translator supplies expected text. Output is an offline formatter
contract replay, not a claim about the user's actual input buffer/hook.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


def inspect_printf(exe):
    import capstone
    import pefile

    from sora_bilingual.game.native_contracts import (
        _exception_entries,
        _reference_target,
        _variant_matches,
    )

    contract = json.loads(
        (ROOT / "tests/fixtures/item_description_printf_contract.json").read_text("utf-8")
    )
    with pefile.PE(str(exe), fast_load=True) as pe:
        entries = _exception_entries(pe)
        templates = contract["functions"]
        matches = {
            name: [
                start
                for start, end, _ in entries
                if end - start >= template["size"] and _variant_matches(pe, start, template)
            ]
            for name, template in templates.items()
        }
        assert all(len(rows) == 1 for rows in matches.values()), (
            "No unique reviewed printf consumer",
            matches,
        )
        starts = {name: rows[0] for name, rows in matches.items()}
        for name, template in templates.items():
            for link in template["links"]:
                assert _reference_target(pe, starts[name], link) == starts[
                    link["function"]
                ] + link.get("addend", 0), ("Printf consumer link differs", name, link)
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        rows = {}
        image_base = pe.OPTIONAL_HEADER.ImageBase
        builder, formatter, crt = (
            starts[name] for name in ("item_description", "bounded_printf", "crt_printf")
        )
        for start, length in (
            (builder, templates["item_description"]["size"]),
            (formatter, templates["bounded_printf"]["size"]),
        ):
            rows.update(
                {
                    address - image_base: (mnemonic, operand)
                    for address, _, mnemonic, operand in decoder.disasm_lite(
                        pe.get_data(start, length), image_base + start
                    )
                }
            )
        expected = {
            builder + 0x3C: ("mov", "rsi, rdx"),
            builder + 0x42A: ("mov", "rdx, qword ptr [rsi + 0xe8]"),
            builder + 0x438: ("call", hex(image_base + formatter)),
            formatter + 0x42: ("mov", "r8d, 0x800"),
            formatter + 0x4B: ("mov", "qword ptr [rsp + 0x20], rbx"),
            formatter + 0x53: ("call", hex(image_base + crt)),
        }
        assert all(rows.get(rva) == value for rva, value in expected.items()), rows
        return {
            "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
            "instructions": {hex(rva): value for rva, value in expected.items()},
            "resolved_functions": starts,
            "fixture_sha256": hashlib.sha256(
                (ROOT / "tests/fixtures/item_description_printf_contract.json").read_bytes()
            ).hexdigest(),
            "consumer": "ItemTableData description -> bounded native printf",
            "actual_scene_raw_or_literal_copy_branch": "pending",
        }


def raw_descriptions(game):
    values, receipts = {}, []
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_item.tbl"])
        assert data[:4] == b"#TBL"
        for index in range(struct.unpack_from("<I", data, 4)[0]):
            descriptor = 8 + index * 80
            if data[descriptor : descriptor + 64].split(b"\0")[0] != b"ItemTableData":
                continue
            start, stride, count = struct.unpack_from("<III", data, descriptor + 68)
            assert stride == 256
            rows = {}
            for physical in range(count):
                at = start + physical * stride
                ident = struct.unpack_from("<I", data, at)[0]
                pointer = struct.unpack_from("<Q", data, at + 232)[0]
                text = data[pointer : data.index(b"\0", pointer)].decode("utf-8") if pointer else ""
                assert ident not in rows
                rows[ident] = {"text": text, "physical": physical, "offset": at}
            values[locale] = rows
        receipts.append(
            {
                "locale": locale,
                "path": "table/t_item.tbl",
                "records": len(rows),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return values, receipts


RUNNER = r"""
const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8')),{RuntimeText}=require(d.renderer);
const m=JSON.parse(fs.readFileSync(d.model,'utf8')),t=new RuntimeText(m);
const rows=d.cases.map(c=>{const source=c.texts[d.base],expected=[c.texts[d.primary],c.texts[d.secondary]],
primary=t.translate(source,'primary'),secondary=t.translate(source,'secondary'),plan=t.render(source,'annotation');
return {...c,source,expected,primary,secondary,pass:primary===expected[0]&&secondary===expected[1],
render_kind:plan.kind,layers:plan.layers,actual_display_entrance:'pending',reason:
(m.ambiguous_display||[]).includes(source)?'ambiguous_display':'exact_or_unassociated_resource'};});
process.stdout.write(JSON.stringify(rows));
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--game", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--base", default="en")
    p.add_argument("--primary", default="ja")
    p.add_argument("--secondary", default="zh-Hans")
    a = p.parse_args()
    raw, receipts = raw_descriptions(a.game)
    cases, refused = [], []
    for ident in sorted(set().union(*(rows.keys() for rows in raw.values()))):
        texts = {locale: rows.get(ident, {}).get("text", "") for locale, rows in raw.items()}
        if not any("%%" in text for text in texts.values()):
            continue
        selected = (a.base, a.primary, a.secondary)
        if any(not texts[l] or "%" in texts[l].replace("%%", "") for l in selected):
            refused.append(
                {"id": ident, "reason": "missing_locale_or_dynamic_printf", "texts": texts}
            )
            continue
        cases.append(
            {
                "id": ident,
                "raw_texts": texts,
                "texts": {l: text.replace("%%", "%") for l, text in texts.items()},
            }
        )
    renderer = (a.package / "sora_bilingual/game/scripts/runtime_text.js").resolve()
    result = subprocess.run(
        ["node", "--max-old-space-size=6144", "-e", RUNNER],
        input=json.dumps(
            {
                "cases": cases,
                "renderer": str(renderer),
                "model": str(a.model.resolve()),
                "base": a.base,
                "primary": a.primary,
                "secondary": a.secondary,
            },
            ensure_ascii=False,
        ),
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    rows = json.loads(result.stdout)
    report = {
        "raw_inventory": raw,
        "receipts": receipts,
        "cases": rows,
        "raw_refusals": refused,
        "base": a.base,
        "primary": a.primary,
        "secondary": a.secondary,
        "native_proof": inspect_printf(a.game / "sora_2nd.exe"),
        "model_sha256": hashlib.sha256(a.model.read_bytes()).hexdigest(),
        "renderer_sha256": hashlib.sha256(renderer.read_bytes()).hexdigest(),
        "oracle": "physical PAC description pointers + proven zero-argument printf semantics",
        "passed": sum(row["pass"] for row in rows),
        "total": len(rows),
    }
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "total": report["total"],
                "passed": report["passed"],
                "refused": len(refused),
                "mixed_case_4304": next((r["pass"] for r in rows if r["id"] == 4304), None),
            }
        )
    )


if __name__ == "__main__":
    main()
