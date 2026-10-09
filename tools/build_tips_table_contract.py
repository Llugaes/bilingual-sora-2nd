"""Generate the narrow, disk-only Tips post-load capability from reviewed samples."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import pprint
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import capstone
from sora_bilingual.game.native_contract_data import CONTRACT
from sora_bilingual.game.native_contracts import resolve_native_contracts

spec = importlib.util.spec_from_file_location(
    "existing_contract_builder", ROOT / "tools/build_native_contracts.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def build(path):
    image = builder.Image(path)
    resolved = resolve_native_contracts(image.pe)
    matches = []
    for start, end in image.functions:
        if end - start != 426:
            continue
        instructions = list(image.md.disasm(image.pe.get_data(start, end - start), start))
        if any(i.mnemonic == "mov" and i.op_str == "eax, 0x1ce8" for i in instructions):
            matches.append((start, end, instructions))
    if len(matches) != 1:
        raise ValueError("Tips loader is not unique")
    start, end, instructions = matches[0]
    required = {
        "add ax, word ptr [rbx + 2]",
        "mov word ptr [rbx + 2], ax",
        "mov ebp, 0x1e77",
        "cmp ax, bp",
        "mov word ptr [rbx + 2], bp",
        "mov qword ptr [rbx + 0x28], rax",
        "mov qword ptr [rbx + 0x30], rax",
        "mov dword ptr [rbx + 0x18], eax",
    }
    if not required <= {i.mnemonic + " " + i.op_str for i in instructions}:
        raise ValueError("Tips loader field/width/cap contract differs")
    calls = [i for i in instructions if i.mnemonic == "call"]
    if len(calls) != 2 or calls[1].operands[0].imm != resolved["functions"]["diagnostic_report"]:
        raise ValueError("Tips loader CALL contract differs")
    strcmp = image.owner(calls[0].operands[0].imm)
    if not strcmp or strcmp[1] - strcmp[0] != 103:
        raise ValueError("Tips descriptor strcmp extent differs")
    functions = {name: image.owner(address) for name, address in resolved["functions"].items()}
    functions = {k: v for k, v in functions.items() if v}
    functions.update(tips_table_load=(start, end), tips_descriptor_compare=strcmp)
    rip = []
    for ins in instructions:
        for operand in ins.operands:
            if (
                operand.type == capstone.x86.X86_OP_MEM
                and operand.mem.base == capstone.x86.X86_REG_RIP
            ):
                rip.append((ins, ins.address + ins.size + operand.mem.disp))
    if len(rip) != 4:
        raise ValueError("Tips loader data dependencies differ")
    vtable = rip[0][1]
    variant = image.template(
        (start, end), {"tips_table_load": start}, functions, {"tips_table_vtable": vtable}
    )
    # The generic builder excludes diagnostic CALLs outside its source-line
    # family. This loader needs an explicit callee constraint, even though
    # that path only reports/clamps an out-of-range flag.
    for call, function in zip(calls, ("tips_descriptor_compare", "diagnostic_report")):
        link = {
            "displacement": [call.address - start + call.imm_offset, call.imm_size],
            "next": call.address - start + call.size,
            "function": function,
            "addend": 0,
        }
        if link not in variant["links"]:
            variant["links"].append(link)
    refs = []
    for ins, target in rip[1:]:
        data = image.pe.get_data(target, 256).split(b"\0")[0] + b"\0"
        refs.append(
            {
                "displacement": [ins.address - start + ins.disp_offset, ins.disp_size],
                "next": ins.address - start + ins.size,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    if image.pe.get_data(rip[1][1], 14) != b"TipsTableData\0":
        raise ValueError("Wrong table descriptor")
    variant["data_refs"] = refs
    compare = image.template(strcmp, {}, functions, {})
    if compare["masks"]:
        raise ValueError("Unexpected descriptor compare dependency")
    return {
        "sha256": image.digest,
        "functions": {
            "tips_table_load": {"leaf": False, "variants": [variant]},
            "tips_descriptor_compare": {"leaf": False, "variants": [compare]},
        },
        "loader": [start, end],
        "descriptor_compare": list(strcmp),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, action="append", required=True)
    args = parser.parse_args()
    rows = [build(path) for path in args.sample]
    functions = {}
    for row in rows:
        for name, spec in row["functions"].items():
            merged = functions.setdefault(name, {"leaf": spec["leaf"], "variants": []})
            for variant in spec["variants"]:
                if variant not in merged["variants"]:
                    merged["variants"].append(variant)
    globals_ = {
        "tips_table_vtable": {
            "alignment": 8,
            "writable": False,
            "rtti": ".?AVTipsTable@datatable@sora@@",
        }
    }
    output = ROOT / "sora_bilingual/game/tips_contract_data.py"
    output.write_text(
        '"""Reviewed Tips post-load record capability; adds no hook."""\n\n'
        + "TIPS_FUNCTIONS = "
        + pprint.pformat(functions, width=100, sort_dicts=False)
        + "\n\nTIPS_GLOBAL_SPECS = "
        + pprint.pformat(globals_, width=100)
        + "\n",
        "utf-8",
    )
    (ROOT / "generated/r19-tips-contract-generation.json").write_text(
        json.dumps(rows, indent=2), "utf-8"
    )
    print(
        json.dumps(
            {
                "samples": len(rows),
                "functions": list(functions),
                "variants": {k: len(v["variants"]) for k, v in functions.items()},
            }
        )
    )


if __name__ == "__main__":
    main()
