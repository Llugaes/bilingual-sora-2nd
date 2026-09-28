"""Prove dynamic item identity inputs without attaching to the game.

The static half decodes the installed PE and interprets only the installed
SCP helper's verified slot-copy program. The behavioural half attaches only
to a Python process it creates and exercises the same Win64 argument order,
VM fields, stack direction, and builder-output-to-label lifetime. Together
they prove the raw command-8 inputs; they do not attach to the game.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
import os
from pathlib import Path
import subprocess
import struct
import sys

import capstone
from capstone.x86_const import X86_OP_IMM
import frida
import pefile

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import (
    FpacArchive,
    _FUNCTION,
    _SCP_HEADER,
    _logical_script_entries,
    _parse_code,
    _string_value,
)


ROOT = Path(__file__).resolve().parents[1]
IMAGE_BASE = 0x140000000
BUILDER = 0x4AD670
SET_TEXT = 0x588A40
HANDLERS = (
    ("dialogue_popup", 0x4AE4CF, 0x4AE4DB, 0x4AE569),
    ("dialogue_message", 0x4AEC1F, 0x4AEC2A, 0x4AECA4),
)


def decoded(pe: pefile.PE, start: int, length: int) -> dict[int, capstone.CsInsn]:
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    engine.detail = True
    return {
        item.address - IMAGE_BASE: item
        for item in engine.disasm(pe.get_data(start, length), IMAGE_BASE + start)
    }


def require(
    instructions: dict[int, capstone.CsInsn], rva: int, mnemonic: str, operand: str
) -> None:
    item = instructions.get(rva)
    if (
        item is None
        or item.mnemonic != mnemonic
        or item.op_str.replace(" ", "") != operand.replace(" ", "")
    ):
        actual = "<missing>" if item is None else item.mnemonic + " " + item.op_str
        raise AssertionError(
            f"unexpected instruction at {rva:#x}: {actual}; expected {mnemonic} {operand}"
        )


def direct_target(item: capstone.CsInsn) -> int:
    if item.mnemonic != "call" or len(item.operands) != 1 or item.operands[0].type != X86_OP_IMM:
        raise AssertionError(f"expected direct call, got {item.mnemonic} {item.op_str}")
    return item.operands[0].imm - IMAGE_BASE


def inspect_exe(exe: Path) -> dict[str, object]:
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        builder = decoded(pe, BUILDER, 0x800)
        # The resident hook receives args[1] and args[3].  These instructions
        # are the actual function's ABI copies, not a guessed VM layout.
        require(builder, 0x4AD6A9, "mov", "rdi, r9")
        require(builder, 0x4AD6B1, "mov", "rsi, rdx")
        require(builder, 0x4AD6CC, "mov", "eax, dword ptr [r9 + 0x70]")
        # Its loop begins at argument one and reads stack + top - (i + 1) * 4.
        require(builder, 0x4AD72B, "lea", "r9, [rdi + 0x64]")
        require(builder, 0x4AD72F, "lea", "r10, [rdi + 0x58]")
        require(builder, 0x4AD73B, "movsxd", "rcx, dword ptr [r9]")
        require(builder, 0x4AD741, "mov", "rax, qword ptr [r10]")
        require(builder, 0x4AD744, "mov", "eax, dword ptr [rcx + rax]")
        # The opcode-17 branch resolves the following raw item word only
        # after the builder has selected operation 17.
        require(builder, 0x4AD8B2, "cmp", "edi, 0x11")
        if direct_target(builder[0x4AD8D5]) != 0x23EF20:
            raise AssertionError("opcode-17 no longer enters the item resolver")

        # Opcode 2 copies stack[top + signedOffset] and moves top.  The
        # helper's slot(2,5) is therefore a dynamic offset after prior pushes.
        slot = decoded(pe, 0x5E653F, 0x130)
        require(slot, 0x5E6542, "movsxd", "rdx, dword ptr [rdi + 0x64]")
        require(slot, 0x5E6546, "movsxd", "r10, dword ptr [r8 + rax]")
        require(slot, 0x5E6562, "mov", "r9, qword ptr [rdi + 0x58]")
        require(slot, 0x5E665D, "mov", "eax, dword ptr [rcx]")
        require(slot, 0x5E665F, "mov", "dword ptr [r10 + r8], eax")
        require(slot, 0x5E6663, "add", "dword ptr [rdi + 0x64], 4")

        # Opcode 36 writes its group, command and argc into the same VM before
        # dispatching its vtable handler; its post-operand PC is vm+0x10.
        command = decoded(pe, 0x5E7749, 0x55)
        require(command, 0x5E7760, "mov", "dword ptr [rdi + 0x68], edx")
        require(command, 0x5E776F, "mov", "dword ptr [rdi + 0x6c], r8d")
        require(command, 0x5E777F, "mov", "dword ptr [rdi + 0x10], eax")
        require(command, 0x5E7785, "mov", "dword ptr [rdi + 0x70], r9d")

        paths: dict[str, dict[str, int]] = {}
        for name, setup_rva, builder_call, setter_rva in HANDLERS:
            instructions = decoded(pe, setup_rva, setter_rva + 16 - setup_rva)
            require(
                instructions, setup_rva, "mov", "r9, rsi" if name == "dialogue_popup" else "r9, rbx"
            )
            output = "[rbp - 0x60]" if name == "dialogue_popup" else "[rbp - 0x20]"
            require(instructions, setup_rva + 3, "lea", "rdx, " + output)
            require(
                instructions,
                setup_rva + 7,
                "lea",
                "rcx, [rsp + 0x50]" if name == "dialogue_popup" else "rcx, [rbp - 0x70]",
            )
            if direct_target(instructions[builder_call]) != BUILDER:
                raise AssertionError(f"{name} no longer calls dialogue builder")
            require(instructions, setter_rva, "lea", "rdx, " + output)
            require(instructions, setter_rva + 4, "mov", "rcx, qword ptr [rdi + 0xc8]")
            if direct_target(instructions[setter_rva + 11]) != SET_TEXT:
                raise AssertionError(f"{name} no longer sends builder output to SetText")
            paths[name] = {"builder_call": builder_call, "set_text_call": setter_rva + 11}
        return {"builder": BUILDER, "set_text": SET_TEXT, "handlers": paths}
    finally:
        pe.close()


def _script_code(
    data: bytes, function_name: str
) -> tuple[list[int], list[tuple[object, ...]], tuple[str, ...]]:
    _magic, start, count, global_start, global_count, _reserved = _SCP_HEADER.unpack_from(data)
    names = tuple(_string_value(data, start + number * 32 + 28) for number in range(count))
    globals_ = tuple(
        _string_value(data, global_start + number * 8) for number in range(global_count)
    )
    number = names.index(function_name)
    code_at = _FUNCTION.unpack_from(data, start + number * 32)[0]
    starts = sorted(_FUNCTION.unpack_from(data, start + index * 32)[0] for index in range(count))
    end = next(value for value in starts if value > code_at)
    positions: list[int] = []
    code, _strings = _parse_code(data, code_at, end, number, names, globals_, None, positions)
    return positions, list(code), names


def _push_token(data: bytes, position: int) -> int:
    if data[position : position + 2] != b"\0\x04":
        raise AssertionError(f"not a 32-bit SCP push at {position:#x}")
    return struct.unpack_from("<I", data, position + 2)[0]


def actual_id220_command8(game_dir: Path) -> list[dict[str, object]]:
    """Derive builder tokens by executing only the verified slot-copy shape."""
    archive_path = game_dir / "pac" / "steam" / archive_names("script")["zh-Hans"]
    with FpacArchive(archive_path) as archive:
        data = archive.read(_logical_script_entries(archive)["script/scena/mp3000_ev.dat"])
    helper_positions, helper_code, _ = _script_code(data, "ITEM_ADD_MESSAGE2_EV")
    system_index = helper_code.index(("system-call", 5, 8, 6))
    expected_helper = [
        ("slot", 2, 3),
        ("slot", 2, 2),
        ("push", "int", 17),
        ("slot", 2, 5),
        ("push", "int", 16),
        ("push", "int", 65535),
        ("system-call", 5, 8, 6),
    ]
    if helper_code[system_index - 6 : system_index + 1] != expected_helper:
        raise AssertionError("ITEM_ADD_MESSAGE2_EV command-8 stack program changed")
    pc = helper_positions[system_index] + 4  # opcode 36 plus group/command/argc
    results: list[dict[str, object]] = []
    for function_name, expected_call in (("EV_02_28_00", 488), ("EV_02_28_00_END", 0)):
        positions, code, _ = _script_code(data, function_name)
        index = code.index(("local-call", "ITEM_ADD_MESSAGE2_EV"))
        outer = code[index - 5 : index + 1]
        if outer[:1] != [("prepare-local", outer[0][1])] or outer[-1] != (
            "local-call",
            "ITEM_ADD_MESSAGE2_EV",
        ):
            raise AssertionError(f"missing local-call frame for {function_name}")
        if [item[:2] for item in outer[1:5]] != [
            ("push", "int"),
            ("push", "string"),
            ("push", "string"),
            ("push", "int"),
        ]:
            raise AssertionError(f"unexpected outer parameter types for {function_name}")
        # The caller pushes style, suffix, prefix, then item.  Opcode 2 copies
        # stack[top - slot*4] and increments top by four.  Simulate only those
        # three verified copies; no parent-frame inference is involved.
        stack = [_push_token(data, positions[index - offset]) for offset in (4, 3, 2, 1)]
        top = len(stack)

        def slot(slot_number: int) -> None:
            nonlocal top
            source = top - slot_number
            if source < 0 or source >= len(stack):
                raise AssertionError("slot copy escaped local call frame")
            stack.append(stack[source])
            top += 1

        slot(3)
        slot(2)
        stack.append(0x40000011)
        top += 1
        slot(5)
        stack.extend((0x40000010, 0x4000FFFF))
        top += 2
        # System call argc is six. The builder reads top-(i+1)*4, yielding its
        # complete raw token stream in reverse push order.
        tokens = [stack[top - (index + 1)] for index in range(6)]
        style, suffix, prefix, item = (
            _push_token(data, positions[index - 4]),
            _push_token(data, positions[index - 3]),
            _push_token(data, positions[index - 2]),
            _push_token(data, positions[index - 1]),
        )
        expected = [0x4000FFFF, 0x40000010, prefix, 0x40000011, item, suffix]
        if tokens != expected or item != 0x400000DC or style != 0x40000009:
            raise AssertionError(
                f"unexpected resolved command-8 tokens for {function_name}: {tokens!r}"
            )
        results.append(
            {"function": function_name, "called": expected_call, "pc": pc, "tokens": tokens}
        )
    return results


def fixture_source(cases: list[dict[str, object]]) -> str:
    """Return a self-hosted ABI fixture for the statically derived VM tokens."""
    encoded_cases = json.dumps(cases, separators=(",", ":"))
    return rf"""
const cases={encoded_cases};
const fixtures=new CModule(`
typedef unsigned int u32;
__attribute__((noinline)) void fixture_builder(void *context,char *out,void *unknown,void *vm) {{
    char *stack=*(char **)((char *)vm+0x58);
    int top=*(int *)((char *)vm+0x64),argc=*(int *)((char *)vm+0x70);
    // Match the real builder's reverse read for six command-8 raw words.
    u32 window=0,prefix=0,opcode=0,item=0,suffix=0;
    if(argc==6) {{
        window=*(u32 *)(stack+top-1*4);
        prefix=*(u32 *)(stack+top-3*4);
        opcode=*(u32 *)(stack+top-4*4);
        item=*(u32 *)(stack+top-5*4);
        suffix=*(u32 *)(stack+top-6*4);
    }}
    const char *text=(window==0x4000ffff && prefix!=0 && opcode==0x40000011 && item==0x400000dc && suffix!=0) ? "same-byte-notification" : "rejected";
    int i=0; do {{ out[i]=text[i]; }} while(text[i++]);
}}
__attribute__((noinline)) void fixture_set_text(void *label,char *text) {{ *(char **)label=text; }}
__attribute__((noinline)) void fixture_command8(void *label,void *vm) {{
    char output[0x800]; fixture_builder(0,output,0,vm); fixture_set_text(label,output);
}}
`);
function check(value,message){{if(!value)throw Error(message);}}
function capture(vm){{
    const argc=vm.add(0x70).readU32(),top=vm.add(0x64).readS32(),stack=vm.add(0x58).readPointer();
    if(argc>512||top<argc*4||top>16*1024*1024||stack.isNull())return null;
    const name=vm.add(0x88).readPointer().readUtf8String();
    if(name.length>256)return null;
    const values=[];for(let i=0;i<argc;i++)values.push(stack.add(top-(i+1)*4).readU32());
    return {{functionName:name,values,site:{{pc:vm.add(0x10).readU32(),group:vm.add(0x68).readU32(),command:vm.add(0x6c).readU32()}}}};
}}
function vm(spec){{
    const tokens=spec.tokens,value=Memory.alloc(0x100),stack=Memory.alloc(tokens.length*4),name=Memory.allocUtf8String('ITEM_ADD_MESSAGE2_EV');
    const top=tokens.length*4;
    tokens.forEach((token,index)=>stack.add(top-(index+1)*4).writeU32(token));
    value.add(0x58).writePointer(stack);value.add(0x64).writeS32(top);value.add(0x70).writeU32(tokens.length);
    value.add(0x88).writePointer(name);value.add(0x10).writeU32(spec.pc);value.add(0x68).writeU32(5);value.add(0x6c).writeU32(8);
    return value;
}}
rpc.exports={{run(){{
    const pending=new Map(),deliveries=[];
    const builder=Interceptor.attach(fixtures.fixture_builder,{{onEnter(args){{this.output=args[1];this.candidate=capture(args[3]);}},onLeave(){{
        check(this.candidate!==null,'fixture candidate rejected');
        const source=this.output.readUtf8String();check(source==='same-byte-notification','builder did not consume resolved command-8 tokens');
        pending.set(String(this.output),{{source,candidate:this.candidate}});
    }}}});
    const setter=Interceptor.attach(fixtures.fixture_set_text,{{onEnter(args){{const origin=pending.get(String(args[1]));check(origin!==undefined,'output pointer did not reach label setter');deliveries.push({{label:String(args[0]),source:args[1].readUtf8String(),candidate:origin.candidate}});}}}});
    Interceptor.flush();
    const call=new NativeFunction(fixtures.fixture_command8,'void',['pointer','pointer']);
    for(const spec of cases)call(Memory.alloc(8),vm(spec));
    builder.detach();setter.detach();Interceptor.flush();
    check(deliveries.length===cases.length,'expected every derived command-8 delivery');
    for(const [index,spec] of cases.entries()){{
        const got=deliveries[index].candidate;
        check(got.functionName==='ITEM_ADD_MESSAGE2_EV','helper function name changed');
        check(JSON.stringify(got.values)===JSON.stringify(spec.tokens),'VM stack order changed');
        check(got.site.pc===spec.pc&&got.site.group===5&&got.site.command===8,'VM site contract changed');
    }}
    check(deliveries[0].source===deliveries[1].source,'fixture must preserve same visible source');
    check(deliveries[0].candidate.values[2]!==deliveries[1].candidate.values[2]&&deliveries[0].candidate.values[5]!==deliveries[1].candidate.values[5],
        'same source incorrectly collapsed independent resolved token streams');
    const bad=vm(cases[0]);bad.add(0x64).writeS32(4);check(capture(bad)===null,'invalid VM bounds accepted');
    return {{game_attached:false,host:'self-created-hidden-python',deliveries}};
}}}};
"""


def run_fixture(cases: list[dict[str, object]]) -> dict[str, object]:
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        agent = session.create_script(fixture_source(cases), runtime="v8")
        agent.load()
        return agent.exports_sync.run()
    finally:
        if session is not None:
            try:
                session.detach()
            except frida.InvalidOperationError:
                pass
        if host.poll() is None:
            host.terminate()
        host.wait(timeout=5)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, help="verified sora_2nd.exe; defaults to SORA_GAME_EXE")
    args = parser.parse_args(argv)
    environment = os.environ.get("SORA_GAME_EXE")
    executable = args.exe or (Path(environment) if environment else None)
    if executable is None:
        print(
            json.dumps(
                {
                    "skipped": True,
                    "reason": "pass --exe or set SORA_GAME_EXE",
                    "game_started": False,
                    "game_attached": False,
                }
            )
        )
        return
    if not executable.is_file():
        raise SystemExit(f"missing game executable: {executable}")
    static = inspect_exe(executable)
    actual_command8 = actual_id220_command8(executable.parent)
    fixture = run_fixture(actual_command8)
    assert fixture["game_attached"] is False
    print({"static": static, "actual_command8": actual_command8, "fixture": fixture})


if __name__ == "__main__":
    main()
