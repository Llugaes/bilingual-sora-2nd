"""Disk-only shop ABI/callee/data mutation checks on reviewed executable samples."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import capstone
import pefile


def check(path, temporary):
    from sora_bilingual.game.native_contracts import resolve_native_contracts
    from sora_bilingual.game.native_runtime import native_report
    from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError

    report = native_report(path)
    raw = path.read_bytes()
    with pefile.PE(data=raw, fast_load=True) as pe:
        resolved = resolve_native_contracts(pe)
        functions = resolved["functions"]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        caller = functions["shop_action_copy"]
        instructions = list(md.disasm(pe.get_data(caller, 596), caller))
        alterations = []

        def byte(name, rva):
            changed = bytearray(raw)
            changed[pe.get_offset_from_rva(rva)] ^= 1
            alterations.append((name, changed))

        def target(name, ins, destination):
            changed = bytearray(raw)
            struct.pack_into(
                "<i",
                changed,
                pe.get_offset_from_rva(ins.address + ins.imm_offset),
                destination - ins.address - ins.size,
            )
            alterations.append((name, changed))

        for offset, name in (
            (384, "YES lookup manager address"),
            (454, "NO lookup manager address"),
        ):
            byte(name, caller + offset)

        for name in ("shop_yes_copy_return", "shop_no_copy_return"):
            point = resolved["points"][name]
            copy = next(i for i in instructions if i.address + i.size == point)
            assert copy.mnemonic == "call" and copy.operands[0].imm == functions["set_text"]
            target(name + " wrong setter addend", copy, functions["set_text"] + 1)
        key = next(i for i in instructions if i.mnemonic == "mov" and i.op_str == "edx, esi")
        byte("YES key register", key.address + 1)
        owner = next(
            i
            for i in instructions
            if i.mnemonic == "mov" and i.op_str == "rdi, qword ptr [rbx + 0xb0]"
        )
        byte("YES label field", owner.address + owner.disp_offset)
        owner = next(
            i
            for i in instructions
            if i.mnemonic == "mov" and i.op_str == "rdi, qword ptr [rbx + 0xb8]"
        )
        byte("NO label field", owner.address + owner.disp_offset)
        branch = next(i for i in instructions if i.mnemonic == "jne")
        byte("internal mode branch", branch.address + branch.imm_offset)
        constant = next(i for i in instructions if i.mnemonic == "mov" and "0xcb26b9de" in i.op_str)
        byte("mode resource hash", constant.address + constant.imm_offset)
        for function in (
            "shop_text_lookup",
            "shop_printf",
            "shop_key_hash",
            "shop_trade_mode",
            "shop_create_mode",
        ):
            ins = next(
                i
                for i in instructions
                if i.mnemonic == "call"
                and i.operands[0].type == capstone.x86.X86_OP_IMM
                and i.operands[0].imm == functions[function]
            )
            target("wrong " + function + " callee", ins, functions[function] + 1)
        string = next(
            i for i in instructions if i.mnemonic == "lea" and i.op_str.startswith("rcx, [rip")
        )
        address = string.address + string.size + string.operands[1].mem.disp
        byte("input key literal", address)
        formatter = functions["shop_printf"]
        fmt = list(md.disasm(pe.get_data(formatter, 179), formatter))
        byte("printf strlen call target", formatter + 51)
        for name in ("shop_printf_length", "shop_printf_copy", "shop_printf_options"):
            ins = next(
                i
                for i in fmt
                if i.mnemonic == "call"
                and i.operands[0].type == capstone.x86.X86_OP_IMM
                and i.operands[0].imm == functions[name]
            )
            target(name + " wrong callee", ins, functions[name] + 1)
            byte(name + " body", functions[name])
            from sora_bilingual.game.shop_contract_data import SHOP_FUNCTIONS

            size = SHOP_FUNCTIONS[name]["variants"][0]["size"]
            for dependency in md.disasm(pe.get_data(functions[name], size), functions[name]):
                if any(
                    op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP
                    for op in dependency.operands
                ):
                    byte(
                        name + " RIP dependency " + str(dependency.address - functions[name]),
                        dependency.address + dependency.disp_offset,
                    )
        capacity = next(i for i in fmt if i.mnemonic == "mov" and i.op_str == "r8d, 0x100")
        byte("printf capacity", capacity.address + capacity.imm_offset)
        call = next(
            i
            for i in fmt
            if i.mnemonic == "call"
            and i.operands[0].type == capstone.x86.X86_OP_IMM
            and i.operands[0].imm == functions["shop_printf_engine"]
        )
        target("printf engine call", call, functions["shop_printf_engine"] + 1)
        byte("printf engine body", functions["shop_printf_engine"] + 4)
        for name in ("shop_text_lookup", "shop_key_hash", "shop_trade_mode", "shop_create_mode"):
            byte(name + " body", functions[name] + 4)
        hash_code = list(
            md.disasm(pe.get_data(functions["shop_key_hash"], 41), functions["shop_key_hash"])
        )
        table = next(
            i
            for i in hash_code
            if i.mnemonic == "lea" and i.operands[1].mem.base == capstone.x86.X86_REG_RIP
        )
        byte("resource CRC table", table.address + table.size + table.operands[1].mem.disp + 8)
        results = []
        for name, changed in alterations:
            temporary.write_bytes(changed)
            try:
                native_report(temporary)
            except ExecutableCompatibilityError as error:
                results.append({"case": name, "accepted": False, "detail": str(error)})
            else:
                raise AssertionError("dangerous mutation accepted: " + name)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "points": {
            k: resolved["points"][k] for k in ("shop_yes_copy_return", "shop_no_copy_return")
        },
        "rejected": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--package", type=Path, help="Use this independent candidate's production native resolver"
    )
    a = parser.parse_args()
    if a.package:
        sys.path.insert(0, str(a.package.resolve()))
        from sora_bilingual.game import native_runtime

        assert Path(native_runtime.__file__).resolve().is_relative_to(a.package.resolve())
    with tempfile.TemporaryDirectory(prefix="sora-shop-contract-") as tmp:
        rows = [check(path, Path(tmp) / "mutated.exe") for path in a.sample]
    a.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {"samples": len(rows), "dangerous_rejections": sum(len(r["rejected"]) for r in rows)}
        )
    )
