"""Verify log-row inset projection in a self-created host, never a game process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import capstone
from capstone.x86_const import X86_OP_MEM, X86_REG_RIP
import frida
import pefile


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "sora_bilingual/game/scripts/native_agent.js"
OUTPUT = ROOT / "generated/diagnostic-132-log-inset.json"
EXPECTED_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
UPDATE_START, UPDATE_END = 0x584CF4, 0x584D1E
ANCHOR_START, ANCHOR_END = 0x589130, 0x5892FC
MULTIPLY_START, MULTIPLY_END = 0x5B3F0, 0x5B514
ANCHOR_TABLE = 0x5892D8
ANCHOR_TARGETS = [
    0x58923F,
    0x589160,
    0x58917C,
    0x589198,
    0x5891B6,
    0x5891CF,
    0x5891EC,
    0x589205,
    0x589222,
]
Y_FACTORS = [0, 0, -1, -1, -0.5, -0.5, 0, -1, -0.5]


def extract_function(name: str) -> str:
    source = AGENT.read_text("utf-8")
    marker = f"function {name}("
    start = source.index(marker)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated production function: {name}")


def decoded(pe: pefile.PE, start: int, end: int) -> list[capstone.CsInsn]:
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    engine.detail = True
    return list(engine.disasm(pe.get_data(start, end - start), start))


def update_contract(pe: pefile.PE) -> list[dict[str, str]]:
    rows = decoded(pe, UPDATE_START, UPDATE_END)
    actual = [f"{row.address:x}: {row.mnemonic} {row.op_str}" for row in rows]
    required = [
        "584cf4: mov edx, dword ptr [rsi + 0x2e0]",
        "584cfa: lea r8, [rsi + 0x2d8]",
        "584d06: call 0x589130",
        "584d10: lea rcx, [rsi + 8]",
        "584d19: call 0x5b3f0",
    ]
    for instruction in required:
        assert instruction in actual, (instruction, actual)
    return [
        {"address": f"0x{row.address:x}", "instruction": f"{row.mnemonic} {row.op_str}"}
        for row in rows
    ]


def active_voice_contract(pe: pefile.PE) -> list[dict[str, str]]:
    """Verify the resource-independent native surface discriminator."""
    required = {
        0x26402: "mov edx, 0x20",
        0x26414: "call 0x58fc80",
    }
    result = []
    for address, expected in required.items():
        item = decoded(pe, address, address + 16)[0]
        actual = f"{item.mnemonic} {item.op_str}"
        assert actual == expected, (hex(address), actual, expected)
        result.append({"address": hex(address), "instruction": actual})
    for address, name in ((0x26459, b"items"), (0x264A9, b"item"), (0x25B29, b"text")):
        item = decoded(pe, address, address + 16)[0]
        operand = item.operands[1]
        assert item.mnemonic == "lea" and operand.type == X86_OP_MEM
        assert operand.mem.base == X86_REG_RIP
        actual = pe.get_data(item.address + item.size + operand.mem.disp, len(name) + 1)
        assert actual == name + b"\0", (hex(address), actual, name)
        result.append({"address": hex(address), "node": name.decode("ascii")})
    return result


def anchor_spec(pe: pefile.PE) -> dict[str, object]:
    code = pe.get_data(ANCHOR_START, ANCHOR_END - ANCHOR_START)
    assert len(code) == ANCHOR_END - ANCHOR_START
    table = [
        struct.unpack_from("<I", code, ANCHOR_TABLE - ANCHOR_START + index * 4)[0]
        for index in range(9)
    ]
    assert table == ANCHOR_TARGETS, table
    refs = []
    for row in decoded(pe, ANCHOR_START, 0x5892D8):
        for operand in row.operands:
            if operand.type != X86_OP_MEM or operand.mem.base != X86_REG_RIP:
                continue
            # Each x64 RIP load in this verified function carries its disp32
            # in the final four bytes. Keep the instruction itself unchanged.
            if row.address == 0x58914C:
                refs.append(
                    {
                        "offset": row.address - ANCHOR_START + row.size - 4,
                        "next": row.address - ANCHOR_START + row.size,
                        "anchor_base": True,
                    }
                )
                continue
            target = row.address + row.size + operand.mem.disp
            refs.append(
                {
                    "offset": row.address - ANCHOR_START + row.size - 4,
                    "next": row.address - ANCHOR_START + row.size,
                    "target": target,
                    "bytes": list(pe.get_data(target, 16)),
                }
            )
    assert refs, "no anchor RIP globals found"
    return {"bytes": list(code), "refs": refs, "table": table, "y_factors": Y_FACTORS}


def multiply_bytes(pe: pefile.PE) -> list[int]:
    data = pe.get_data(MULTIPLY_START, MULTIPLY_END - MULTIPLY_START)
    rows = decoded(pe, MULTIPLY_START, MULTIPLY_END)
    assert rows[-1].address == 0x5B513 and rows[-1].mnemonic == "ret"
    assert not any(
        operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
        for row in rows
        for operand in row.operands
    )
    return list(data)


def script_source(spec: dict[str, object], methods: str) -> str:
    return r"""
const SPEC=__SPEC__;
const activeVoiceRoots=new Set(['voice-root']),logTextGroups=new Map(),labelCallbacks=new Map(),labels=new Map(),labelSet=new Set(),errors=[];
let enabled=true,failed=false,renderMode='annotation',epoch=7,bilingualOffsetY=0;
function isLabel(pointer){return labelSet.has(String(pointer));}
function fail(error){errors.push(String(error));}
__METHODS__
function check(value,message){if(!value)throw Error(message);}
function close(a,b){return Math.abs(a-b)<0.00001;}
function patchRel32(bytes,offset,next,target){new DataView(bytes.buffer).setInt32(offset,target.sub(next).toInt32(),true);}
function nativeFunctions(){
  const arena=Memory.alloc(Process.pageSize*3),anchorCode=arena,constant=arena.add(Process.pageSize),multiplyCode=arena.add(Process.pageSize*2);
  const anchor=new Uint8Array(SPEC.bytes),multiply=Uint8Array.from(SPEC.multiply),refs=SPEC.refs;
  let constantIndex=0;refs.forEach(ref=>{const target=ref.anchor_base?anchorCode.sub(0x589130):constant.add(constantIndex++*16);if(!ref.anchor_base)target.writeByteArray(ref.bytes);patchRel32(anchor,ref.offset,anchorCode.add(ref.next),target);});
  Memory.patchCode(anchorCode,anchor.length,w=>w.writeByteArray(anchor.buffer));
  Memory.patchCode(multiplyCode,multiply.length,w=>w.writeByteArray(multiply.buffer));
  check(Memory.protect(anchorCode,Process.pageSize,'r-x'),'anchor code protect failed');
  check(Memory.protect(multiplyCode,Process.pageSize,'r-x'),'multiply code protect failed');
  return {arena,anchor:new NativeFunction(anchorCode,'void',['pointer','uint','pointer']),multiply:new NativeFunction(multiplyCode,'pointer',['pointer','pointer','pointer'])};
}
function matrix(out,anchor,style,native){native.anchor(out,anchor,style);return out;}
function project(label,glyph,native){const out=Memory.alloc(16);native.multiply(label.add(8),out,glyph);return [out.readFloat(),out.add(4).readFloat(),out.add(8).readFloat(),out.add(12).readFloat()];}
function writeIdentity(pointer){for(let i=0;i<16;i++)pointer.add(i*4).writeFloat(i%5===0?1:0);}
function setup(anchor){
  const controller=Memory.alloc(0xa0),frame=Memory.alloc(0x300),parent=Memory.alloc(0x60),name=Memory.alloc(0x400),body=Memory.alloc(0x400),glyph=Memory.alloc(16);
  labelSet.add(String(name));labelSet.add(String(body));
  controller.add(8).writePointer(frame);controller.add(0x10).writePointer(name);controller.add(0x18).writePointer(body);controller.add(0x88).writeU32(0);
  frame.add(0x80).writePointer(parent);frame.add(0x2dc).writeFloat(100);frame.add(0x2e0).writeU32(anchor);frame.add(0xf4).writeFloat(0);
  for(const label of [name,body]){label.add(0x80).writePointer(parent);label.add(0x334).writeU32(1);label.add(0xf4).writeFloat(0);label.add(0x374).writeS32(20);writeIdentity(label.add(8));}
  // Body's local Y axis intentionally disagrees with its shared parent axis.
  // Production must choose parent+1c so both labels translate by exactly 8.
  parent.add(0x18).writeFloat(0);parent.add(0x1c).writeFloat(1);parent.add(0x20).writeFloat(0);
  body.add(0x18).writeFloat(0);body.add(0x1c).writeFloat(5);body.add(0x20).writeFloat(0);
  body.add(0x38).writeFloat(10);body.add(0x3c).writeFloat(20);body.add(0x40).writeFloat(30);
  name.add(0x38).writeFloat(40);name.add(0x3c).writeFloat(50);name.add(0x40).writeFloat(60);
  glyph.writeFloat(3);glyph.add(4).writeFloat(7);glyph.add(8).writeFloat(0);glyph.add(12).writeFloat(1);
  const lease={depth:1,projection:null};labelCallbacks.set(String(body),lease);
  labels.set(String(name),{epoch,plan:{kind:'ruby'}});labels.set(String(body),{epoch,plan:{kind:'layered'}});
  return {controller,frame,parent,name,body,glyph,lease};
}
function floats(pointer,offsets){return offsets.map(offset=>pointer.add(offset).readFloat());}
rpc.exports={run(){
  const native=nativeFunctions(),anchorCases=[];
  // This executes the full copied 0x589130 selector/function, including its
  // real nine-entry relative jump table and fixture-relocated RIP constants.
  for(let anchor=0;anchor<9;anchor++){
    const out=Memory.alloc(0x40),style=Memory.alloc(0x20);style.writeFloat(1);style.add(4).writeFloat(1);matrix(out,anchor,style,native);
    const actual=out.add(0x34).readFloat(),expected=SPEC.y_factors[anchor];
    check(close(actual,expected),'native anchor '+anchor+' y factor '+actual+' != '+expected);anchorCases.push({anchor,actual,expected});
  }
  const state=setup(0);rememberLogTextGroup(state.controller);
  const group=logTextGroups.get(String(state.body));check(group&&group.parent.equals(state.parent),'production group did not retain shared parent');
  check(close(group.room,76),'unexpected bounded room '+group.room);
  const offsets=[0x38,0x3c,0x40],before=floats(state.body,offsets),nameBefore=floats(state.name,offsets),glyphBefore=project(state.body,state.glyph,native),glyphLocal=Array.from(new Uint8Array(state.glyph.readByteArray(16)));
  offsetLogProjection(state.body);const during=floats(state.body,offsets),projected=project(state.body,state.glyph,native);
  check(close(during[1],before[1]+8),'parent-axis inset was not 8');check(close(projected[1],glyphBefore[1]+8),'actual label+08 projection did not move by 8');
  check(JSON.stringify(floats(state.name,offsets))===JSON.stringify(nameBefore),'name local matrix changed');
  check(JSON.stringify(Array.from(new Uint8Array(state.glyph.readByteArray(16))))===JSON.stringify(glyphLocal),'glyph-local coordinates changed');
  restoreTextProjection(state.lease);const restored=floats(state.body,offsets),restoredProjection=project(state.body,state.glyph,native);
  check(JSON.stringify(restored)===JSON.stringify(before),'body local matrix did not restore');check(close(restoredProjection[1],glyphBefore[1]),'restored final projection changed');
  offsetLogProjection(state.body);const repeat=floats(state.body,offsets),repeatProjection=project(state.body,state.glyph,native);restoreTextProjection(state.lease);
  check(close(repeat[1],before[1]+8)&&close(repeatProjection[1],glyphBefore[1]+8),'repeat projection accumulated or lost inset');
  check(close(state.frame.add(0xf4).readFloat(),0),'frame local Y was written');
  const voice=setup(0);Object.assign(labels.get(String(voice.body)),{surface:'active_voice',surfaceRoot:'voice-root'});
  const voiceBefore=project(voice.body,voice.glyph,native);
  for(let repeat=0;repeat<3;repeat++) {
    offsetTextProjection(voice.body);
    check(close(project(voice.body,voice.glyph,native)[1],voiceBefore[1]+8),'active voice native projection did not move by 8');
    restoreTextProjection(voice.lease);
    check(close(project(voice.body,voice.glyph,native)[1],voiceBefore[1]),'active voice native projection did not restore');
  }
  renderMode='primary';offsetTextProjection(voice.body);
  check(close(project(voice.body,voice.glyph,native)[1],voiceBefore[1]),'single language voice moved');
  renderMode='annotation';
  check(!errors.length,'production callback errors: '+errors.join(';'));
  return {all_passed:true,game_attached:false,game_started:false,host:'self-created-hidden-python',anchor_cases:anchorCases,
    active_voice_projection:true,projection:{room:group.room,before,during,projected_y:projected[1],restored,restored_y:restoredProjection[1],repeat,repeat_y:repeatProjection[1]}};
}};
""".replace("__SPEC__", json.dumps(spec)).replace("__METHODS__", methods)


def main(exe: Path | None = None) -> None:
    environment = os.environ.get("SORA_GAME_EXE")
    exe = exe or (Path(environment) if environment else None)
    if exe is None:
        print(
            json.dumps(
                {
                    "skipped": True,
                    "reason": "pass --exe or set SORA_GAME_EXE to the verified sora_2nd.exe",
                    "game_started": False,
                    "game_attached": False,
                },
                indent=2,
            )
        )
        return
    if not exe.is_file():
        raise SystemExit(f"missing verified executable: {exe}")
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"unsupported sora_2nd.exe SHA-256: {digest}")
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        spec = anchor_spec(pe)
        spec["multiply"] = multiply_bytes(pe)
        update = update_contract(pe)
        voice_contract = active_voice_contract(pe)
    finally:
        pe.close()
    names = (
        "rememberLogTextGroup",
        "offsetTextProjection",
        "offsetLogProjection",
        "projectTextInset",
        "restoreTextProjection",
    )
    methods = "\n".join(extract_function(name) for name in names)
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(script_source(spec, methods), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        assert report["all_passed"]
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)
    report["disk"] = {
        "exe": str(exe),
        "sha256": digest,
        "update_projection": update,
        "active_voice_surface": voice_contract,
        "anchor_table": spec["table"],
        "y_factors": Y_FACTORS,
    }
    report["production"] = {
        "native_agent_sha256": hashlib.sha256(AGENT.read_bytes()).hexdigest(),
        "methods": names,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe", type=Path, help="verified sora_2nd.exe; defaults to SORA_GAME_EXE when set"
    )
    main(parser.parse_args().exe)
