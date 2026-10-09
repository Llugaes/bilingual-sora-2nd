"""Disk-only rejection checks for the reviewed Tips loader on all three samples."""

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
from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
from sora_bilingual.game.native_runtime import native_report


def check(path, temporary):
    raw = path.read_bytes()
    report = native_report(path)
    with pefile.PE(data=raw, fast_load=True) as pe:
        start = report["native"]["tips_table_load"]["rva"]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        instructions = list(md.disasm(pe.get_data(start, 426), start))
        changes = []

        def change(name, address, value=None):
            altered = bytearray(raw)
            off = pe.get_offset_from_rva(address)
            if value is None:
                altered[off] ^= 1
            else:
                altered[off] = value
            changes.append((name, altered))

        for text, label in [
            ("eax, 0x1ce8", "field addend"),
            ("ebp, 0x1e77", "maximum"),
        ]:
            ins = next(i for i in instructions if i.mnemonic == "mov" and i.op_str == text)
            change(label, ins.address + ins.imm_offset)
        for mnemonic, text, label in [
            ("add", "ax, word ptr [rbx + 2]", "read field offset"),
            ("mov", "word ptr [rbx + 2], ax", "write field offset"),
            ("mov", "word ptr [rbx + 2], bp", "cap field offset"),
            ("imul", "eax, dword ptr [rdx + 0x48]", "record stride"),
            ("mov", "esi, dword ptr [rsi + rcx*8 + 0x4c]", "record count"),
            ("mov", "rcx, qword ptr [rbx + 0x18]", "resource selector field"),
        ]:
            ins = next(i for i in instructions if i.mnemonic == mnemonic and i.op_str == text)
            change(label, ins.address + ins.disp_offset)
        add = next(i for i in instructions if i.mnemonic == "add" and i.op_str.startswith("ax,"))
        change("16-bit arithmetic width", add.address, 0x90)
        branch = next(i for i in instructions if i.mnemonic == "jbe")
        change("unsigned cap branch", branch.address, 0x76 ^ 1)
        compare = next(i for i in instructions if i.mnemonic == "cmp" and i.op_str == "ax, bp")
        change("cap register", compare.address + compare.size - 1)
        for i in instructions:
            if i.mnemonic == "call":
                change("CALL target " + i.op_str, i.address + i.imm_offset)
            for operand in i.operands:
                if (
                    operand.type == capstone.x86.X86_OP_MEM
                    and operand.mem.base == capstone.x86.X86_REG_RIP
                ):
                    change("RIP dependency " + i.op_str, i.address + i.disp_offset)
                    if i.op_str.startswith("rdx,") or i.op_str.startswith("r9,"):
                        target = i.address + i.size + operand.mem.disp
                        change("descriptor/diagnostic data " + hex(target), target)
        results = []
        for name, changed in changes:
            temporary.write_bytes(changed)
            try:
                native_report(temporary)
            except ExecutableCompatibilityError as error:
                results.append({"case": name, "rejected": True, "detail": str(error)})
            else:
                raise AssertionError("dangerous Tips mutation accepted: " + name)
    return {
        "sample": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "loader": start,
        "cases": results,
    }


if __name__ == "__main__":
    samples = json.loads((ROOT / "generated/r19-tips-load-three-samples.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="sora-tips-contract-") as directory:
        results = [check(Path(row["path"]), Path(directory) / "mutated.exe") for row in samples]
    (ROOT / "generated/r19-tips-contract-mutations.json").write_text(
        json.dumps(results, indent=2), "utf-8"
    )
    print(
        json.dumps(
            {"samples": len(results), "dangerous_rejections": sum(len(r["cases"]) for r in results)}
        )
    )
