"""Physical SCP menu/item-panel census and full shipped renderer replay.

This deliberately does not use parse_scp/align_functions/dynamic_producers to
make the denominator or localized expected text. Refused/unpaired physical
calls stay in the report; a resource pass is not a live display-entrance pass.
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
from sora_bilingual.localization.resources import FpacArchive, _logical_script_entries
from sora_bilingual.localization.tables import _logical_tables


def z(data, pointer):
    assert 0 <= pointer < len(data)
    return data[pointer : data.index(b"\0", pointer)].decode("utf-8")


def item_names(game):
    result = {}
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_item.tbl"])
        assert data[:4] == b"#TBL"
        for i in range(struct.unpack_from("<I", data, 4)[0]):
            at = 8 + i * 80
            if z(data, at) != "ItemTableData":
                continue
            start, stride, count = struct.unpack_from("<III", data, at + 68)
            assert stride == 256
            result[locale] = {
                struct.unpack_from("<I", data, start + j * stride)[0]: z(
                    data, struct.unpack_from("<Q", data, start + j * stride + 224)[0]
                )
                for j in range(count)
            }
    return result


def physical_calls(data):
    assert data[:4] == b"#scp"
    start, count = struct.unpack_from("<II", data, 4)
    assert start + count * 32 <= len(data)
    names = [
        z(data, struct.unpack_from("<I", data, start + i * 32 + 28)[0] & 0x3FFFFFFF)
        for i in range(count)
    ]
    for i, name in enumerate(names):
        n, calls_at = struct.unpack_from("<II", data, start + i * 32 + 16)
        assert calls_at + n * 12 <= len(data)
        for called in range(n):
            at = calls_at + called * 12
            target, kind, argc, args_at = struct.unpack_from("<IHHI", data, at)
            assert args_at + argc * 8 <= len(data)
            raw = [struct.unpack_from("<II", data, args_at + j * 8) for j in range(argc)]
            args = []
            for value, tag in raw:
                if tag:
                    args.append(("dynamic", [value, tag]))
                elif value >> 30 == 3:
                    args.append(("string", z(data, value & 0x3FFFFFFF)))
                elif value >> 30 == 1:
                    v = value & 0x3FFFFFFF
                    args.append(("int", v if v < 1 << 29 else v - (1 << 30)))
                else:
                    args.append(("other", value))
            yield name, called, kind, None if target == 0xFFFFFFFF else names[target], args, at, raw


def decode(kind, target, args, names):
    if kind == 0 and target == "menu_additem":
        if len(args) == 3 and [k for k, _ in args] == ["int", "string", "int"]:
            return {
                "family": "script_menu",
                "text": args[1][1],
                "shape": [target, args[0], args[2]],
            }
        return {"family": "script_menu", "reason": "unknown_menu_slot_or_arity"}
    if kind != 3 or args[:2] != [("int", 5), ("int", 8)]:
        return None
    if not any(v == ("int", 17) for v in args[3:]):
        return None
    parts, shape, count = [], list(args[:3]), 0
    i = 3
    while i < len(args):
        k, v = args[i]
        if k == "string":
            parts.append(v)
        elif (k, v) == ("int", 10):
            parts.append("\n")
        elif k == "int" and v in (11, 12, 17):
            if i + 1 >= len(args) or args[i + 1][0] != "int":
                return {"family": "item_panel", "reason": "dynamic_or_unknown_operand"}
            operand = args[i + 1][1]
            shape.extend([args[i], args[i + 1]])
            if v == 17:
                if operand not in names:
                    return {"family": "item_panel", "reason": "missing_item_id"}
                parts.append("<C0><I12></C><C5>" + names[operand] + "</C>")
                count += 1
            i += 1
        elif k == "int" and v in (7, 8, 9, 13, 14, 15, 16, 19, 20, 22, 24, 26, 28):
            shape.append(args[i])
        else:
            return {"family": "item_panel", "reason": "unsupported_panel_operation"}
        i += 1
    return {"family": "item_panel", "text": "".join(parts), "shape": shape, "icon_slots": count}


RUNNER = r"""
const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8')), {RuntimeText}=require(d.renderer);
const model=JSON.parse(fs.readFileSync(d.model,'utf8')), t=new RuntimeText(model);
let rows=[],pass=0;
for(const c of d.cases) {
 const source=c.texts[d.base],expected=[c.texts[d.primary],c.texts[d.secondary]];
 const a=t.translate(source,'primary'),b=t.translate(source,'secondary'),plan=t.render(source,'annotation');
 const ok=a===expected[0]&&b===expected[1];if(ok)pass++;
 const pointers=(model.script_identities||{}).pointers||{},models=(model.script_identities||{}).pointer_models||{};
 const identity=c.source_identity, candidates=identity?(pointers[source]||[]).filter(p=>
   p.sha256===identity.sha256&&p.offset===identity.string_offset):[];
 const pointerPairs=candidates.map(p=>{const row=models[p.key];if(!row||row.source!==source)return null;
   const r=new RuntimeText(row.model);return {key:p.key,pair:[r.translate(source,'primary'),r.translate(source,'secondary')]};}).filter(Boolean);
 const pointerPass=pointerPairs.length>0&&pointerPairs.every(p=>JSON.stringify(p.pair)===JSON.stringify(expected));
 rows.push({id:c.id,family:c.family,pass:ok,source,expected,primary:a,secondary:b,
   resource_pointer_contract:{pass:pointerPass,identity,candidates:pointerPairs,actual_pointer_carrier:'pending'},
   render_kind:plan.kind,layers:plan.layers.length,reason:ok?'admitted_complete_resource':
   (model.ambiguous_display||[]).includes(source)?'ambiguous_display':'unassociated_or_fallback',
   actual_control_hook:'pending',...(ok?{}:{plan})});
}
process.stdout.write(JSON.stringify({cases:rows,pass,total:rows.length}));
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--game", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--base", default="en")
    p.add_argument("--primary", default="ja")
    p.add_argument("--secondary", default="zh-Hans")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    items = item_names(a.game)
    inventory, counters, receipts = defaultdict(dict), Counter(), []
    for locale, filename in archive_names("script").items():
        with FpacArchive(a.game / "pac/steam" / filename) as archive:
            paths = _logical_script_entries(archive)
            for path, actual in paths.items():
                if not path.endswith(".dat"):
                    continue
                data = archive.read(actual)
                counters[locale + "/scripts"] += 1
                for function, called, kind, target, args, offset, raw in physical_calls(data):
                    row = decode(kind, target, args, items[locale])
                    if not row:
                        continue
                    ident = f"{path}/{function}/called/{called}"
                    row.update(
                        offset=offset, raw=raw, args=args, sha256=hashlib.sha256(data).hexdigest()
                    )
                    inventory[ident][locale] = row
                    counters[locale + "/" + row["family"]] += 1
        receipts.append({"locale": locale, "archive": filename})
    cases, refusals = [], []
    for ident, locales in sorted(inventory.items()):
        required = [locales.get(l) for l in (a.base, a.primary, a.secondary)]
        if any(not r or r.get("reason") for r in required):
            refusals.append(
                {"id": ident, "reason": "missing_or_unsupported_raw_contract", "locales": locales}
            )
            continue
        if len({json.dumps(r["shape"], ensure_ascii=False) for r in required}) != 1:
            refusals.append(
                {"id": ident, "reason": "different_raw_call_identity", "locales": locales}
            )
            continue
        base = required[0]
        pointer = base["raw"][1][0] & 0x3FFFFFFF if base["family"] == "script_menu" else None
        cases.append(
            {
                "id": ident,
                "family": base["family"],
                "texts": {l: r.get("text") for l, r in locales.items()},
                "source_identity": {"sha256": base["sha256"], "string_offset": pointer}
                if pointer is not None
                else None,
            }
        )
    renderer = a.package / "sora_bilingual/game/scripts/runtime_text.js"
    result = subprocess.run(
        ["node", "--max-old-space-size=6144", "-e", RUNNER],
        cwd=PROJECT,
        input=json.dumps(
            {
                "cases": cases,
                "renderer": str(renderer.resolve()),
                "model": str(a.model.resolve()),
                "base": a.base,
                "primary": a.primary,
                "secondary": a.secondary,
            },
            ensure_ascii=False,
        ),
        capture_output=True,
        check=True,
        encoding="utf-8",
    )
    report = json.loads(result.stdout)
    report.update(
        raw_inventory=inventory,
        raw_refusals=refusals,
        counters=counters,
        receipts=receipts,
        base=a.base,
        primary=a.primary,
        secondary=a.secondary,
        model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        renderer_sha256=hashlib.sha256(renderer.read_bytes()).hexdigest(),
        denominator="all physical SCP called descriptors in all eight PACs",
        oracle="raw integer/string descriptors, item IDs, physical table names, documented builder grammar",
        pointer_contract_pass=sum(r["resource_pointer_contract"]["pass"] for r in report["cases"]),
        global_or_pointer_pass=sum(
            r["pass"] or r["resource_pointer_contract"]["pass"] for r in report["cases"]
        ),
        actual_display_entrance="pending; I12 is an opaque probe parameter, not the captured scene value",
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "raw_unique_calls": len(inventory),
                "replay_total": report["total"],
                "pass": report["pass"],
                "raw_refusals": len(refusals),
                "counters": counters,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
