"""Installed-PE contracts and copied callback execution in an owned hidden host.

No game process is started or attached. The native executions copy the actual
complete functions and take paths with no external calls or RIP data reads.
"""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import capstone
from capstone.x86_const import X86_OP_MEM
import pefile


def inspect(exe):
    pe = pefile.PE(str(exe), fast_load=True)
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    engine.detail = True
    regions = {
        "builder": (0x4ADEF0, 0x4AE6CF),
        "talk_callback": (0x4B0B50, 0x4B0C6B),
        "flag": (0x4C3180, 0x4C3242),
        "item_count": (0x49B7F0, 0x49B8BC),
        "action": (0x467FC0, 0x4681D7),
        "dispatch": (0x5E6C90, 0x5E6CE1),
        "ruby_opening": (0x58700A, 0x587024),
    }
    instructions, hashes = {}, {}
    for name, (start, end) in regions.items():
        raw = pe.get_data(start, end - start)
        hashes[name] = {"start": start, "end": end, "sha256": hashlib.sha256(raw).hexdigest()}
        instructions.update({op.address: op for op in engine.disasm(raw, start)})

    def require(at, mnemonic, operands):
        op = instructions.get(at)
        assert op is not None and (op.mnemonic, op.op_str) == (mnemonic, operands), (hex(at), op)

    # Special zero has type 0 and exits before integer command dispatch.
    require(0x4ADFCF, "shr", "ecx, 0x1e")
    require(0x4ADFD2, "cmp", "ecx, 3")
    require(0x4AE06C, "cmp", "ecx, 1")
    require(0x4AE06F, "jne", "0x4ae687")
    # The flag command returns exactly encoded false/true, and writes reg 0
    # only while syscall dispatch is active.
    require(0x4C31FD, "bts", "eax, 0x1e")
    require(0x4C320A, "mov", "dword ptr [rbx + 0x14], eax")
    require(0x4C3237, "mov", "eax, 0")
    require(0x4C323C, "setne", "al")
    # Sepith IDs 310..317 are int32 counters, unlike ordinary uint16 items.
    require(0x49B873, "lea", "ecx, [rax - 0x136]")
    require(0x49B879, "cmp", "ecx, 7")
    require(0x49B885, "mov", "eax, dword ptr [rax + rcx*4 + 0x20b628]")
    require(0x49B8A1, "and", "eax, 0x3fffffff")
    require(0x49B8A6, "bts", "eax, 0x1e")
    require(0x49B8B3, "mov", "dword ptr [rbx + 0x14], eax")
    # Action calls animation with the resolved character, not the VM. No
    # instruction in this handler stores into the VM return register.
    require(0x4681A2, "mov", "r8, rdi")
    require(0x4681A5, "mov", "edx, ebp")
    require(0x4681A7, "mov", "rcx, r10")
    require(0x4681AA, "call", "0x215bc0")
    require(0x58700A, "cmp", "al, 0x52")
    require(0x587012, "mov", "qword ptr [rdx + 8], rax")
    require(0x587019, "mov", "dword ptr [rdx + 0x168], eax")
    require(0x58701F, "jmp", "0x587ceb")
    for op in instructions.values():
        if regions["action"][0] <= op.address < regions["action"][1]:
            assert not any(
                x.type == X86_OP_MEM and x.access & 2 and x.mem.disp == 0x14 for x in op.operands
            ), ("return register write", op.address)
    pe.close()
    return hashes


def owned(exe):
    pe = pefile.PE(str(exe), fast_load=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.VirtualAlloc.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    kernel.VirtualAlloc.restype = ctypes.c_void_p
    kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
    allocations = []

    def owned_code(raw, restype, args):
        length = len(raw)
        address = kernel.VirtualAlloc(None, length, 0x3000, 0x40)
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        allocations.append(address)
        ctypes.memmove(address, raw, len(raw))
        return ctypes.WINFUNCTYPE(restype, *args)(address)

    def native(start, length, restype, args):
        return owned_code(pe.get_data(start, length), restype, args)

    try:
        callback = native(0x4B0B50, 0x11B, ctypes.c_uint32, [ctypes.c_void_p] * 4)
        checks = 0
        for value in (0, 1):
            for index in (1, 2, 7, 255):
                command, current = ctypes.c_uint32(value), ctypes.c_uint32(index)
                assert callback(None, ctypes.byref(command), None, ctypes.byref(current)) == index
                assert command.value == value and current.value == index
                checks += 1
        flag = native(0x4C3180, 0xC2, None, [ctypes.c_void_p, ctypes.c_void_p])
        vm = ctypes.create_string_buffer(512)
        for active in (0, 1):
            ctypes.c_uint32.from_buffer(vm, 0x14).value = 0x12345678
            ctypes.c_uint32.from_buffer(
                vm, 0x70
            ).value = 0  # Default flag ID zero: no global access.
            ctypes.c_uint8.from_buffer(vm, 0x80).value = active
            flag(None, ctypes.byref(vm))
            assert ctypes.c_uint32.from_buffer(vm, 0x14).value == (
                0x40000000 if active else 0x12345678
            )
            checks += 1
        # The R opening marks a base position and advances the cursor. It
        # neither creates a reading child nor changes any other parser field.
        # Adapt (parser, cursor, index) to RDX/RDI/ECX and replace the common
        # parser continuation jump with RET in this bounded block fixture.
        opening = owned_code(
            bytes.fromhex("57 48 89 d7 48 89 ca 44 89 c1")
            + pe.get_data(0x58700E, 0x11)
            + bytes.fromhex("5f c3"),
            None,
            [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32],
        )
        text = ctypes.create_string_buffer(b">official trailing text")
        for index in (0, 7, 4096):
            parser = ctypes.create_string_buffer(b"\xa5" * 512, 512)
            expected = bytearray(parser.raw)
            expected[8:16] = (ctypes.addressof(text) + 1).to_bytes(8, "little")
            expected[0x168:0x16C] = (index + 2).to_bytes(4, "little")
            opening(ctypes.byref(parser), ctypes.byref(text), index)
            assert parser.raw == expected
            checks += 1
        return {
            "checks": checks,
            "original_callback_executed": True,
            "original_flag_executed": True,
            "original_ruby_opening_block_executed": True,
        }
    finally:
        for address in allocations:
            kernel.VirtualFree(address, 0, 0x8000)
        pe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--owned", action="store_true")
    args = parser.parse_args()
    if args.owned:
        print(json.dumps(owned(args.exe)))
        return
    hashes = inspect(args.exe)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", __file__, "--exe", str(args.exe), "--owned"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=30,
    )
    report = {
        "game_started": False,
        "game_attached": False,
        "contracts": hashes,
        "native": json.loads(result.stdout),
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
