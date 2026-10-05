"""Execute the installed log-writer copy commits in a private Frida host.

The test deliberately clones only the two complete payload-copy branches from
``sora_2nd.exe``.  A small owned ABI thunk supplies the writer's live register
and stack state; the copied instructions themselves select the destination and
copy all 0x18c bytes.  No game process is started or attached.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import capstone
import frida
import pefile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.game.native_runtime import native_report

RECORD_BASE = 0x1604EC
RECORD_FLAGS = 0x160674
RECORD_SIZE = 0x18C
PAYLOAD_SIZE = 0x188
SLOT_COUNT = 1600


def _instructions(code: bytes, start: int) -> list[dict[str, object]]:
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    return [
        {
            "rva": f"0x{item.address:x}",
            "bytes": item.bytes.hex(),
            "mnemonic": item.mnemonic,
            "op_str": item.op_str,
        }
        for item in decoder.disasm(code, start)
    ]


def clone_spec(executable: Path) -> dict[str, object]:
    """Read both branch bodies after production contract resolution."""
    assert executable.is_file(), f"missing game executable: {executable}"
    report = native_report(executable)
    native = {name: row["rva"] for name, row in report["native"].items()}
    normal_commit, append_commit = native["log_write_commit"], native["log_write_append_commit"]
    normal_start, normal_end = normal_commit - 0x72, normal_commit + 0xB
    append_start, append_end = normal_end, append_commit + 0x18
    present_start = native["log_present_append"] - 0x2D
    measure_start = native["log_row_append"] - 0x17
    pe = pefile.PE(str(executable), fast_load=True)
    try:
        normal = pe.get_data(normal_start, normal_end - normal_start)
        append = pe.get_data(append_start, append_end - append_start)
        present = _instructions(pe.get_data(present_start, 0x6E), present_start)
        measure = _instructions(pe.get_data(measure_start, 0x1C), measure_start)
    finally:
        pe.close()
    assert len(normal) == normal_end - normal_start
    assert len(append) == append_end - append_start
    normal_rows = _instructions(normal, normal_start)
    append_rows = _instructions(append, append_start)

    def local_text(rows, start):
        return {int(row["rva"], 16) - start: f"{row['mnemonic']} {row['op_str']}" for row in rows}

    normal_text = local_text(normal_rows, normal_start)
    append_text = local_text(append_rows, append_start)
    present_text = local_text(present, present_start)
    measure_text = local_text(measure, measure_start)
    # The visible append loop's RBX is a relative counter, unlike the hidden
    # builder's RBX. Both supply the actual ring-body pointer in RDX.
    assert present_text.get(5) == "sub ecx, ebx"
    assert present_text.get(0x18) == "imul rdx, rax, 0x18c"
    assert present_text.get(0x1F) == "add r10, 0x160550"
    assert present_text.get(0x26) == "add rdx, r10"
    assert present_text.get(0x2D, "").startswith("call ")
    assert measure_text.get(0) == "mov eax, ebx"
    assert measure_text.get(2) == "imul rcx, rax, 0x18c"
    assert measure_text.get(9) == "add rcx, 0x160550"
    assert measure_text.get(0x10) == "add rdx, rcx"
    assert measure_text.get(0x17) == present_text[0x2D]
    assert normal_text.get(0) == "lea rcx, [r8 + 0x1604ec]"
    assert normal_text.get(normal_commit - normal_start) == "mov eax, dword ptr [rdx + 8]"
    assert append_text.get(0) == "lea eax, [rdx + 1]"
    assert append_text.get(0x13) == "imul rcx, rax, 0x18c"
    assert append_text.get(append_commit - append_start) == "mov eax, dword ptr [rdx + 8]"
    # The normal branch ends at its common-loop jump; the append branch ends
    # at its corresponding common-loop jump.  The hidden host replaces only
    # those exits with RET, never changes the copied payload instructions.
    assert normal[-5:] == bytes.fromhex("e9cb000000")
    assert append[-2:] == bytes.fromhex("eb1e")
    return {
        "exe_sha256": report["sha256"],
        "ring_body_inputs": {"visible_append": present, "measuring_append": measure},
        "normal": {
            "start": normal_start,
            "commit_offset": normal_commit - normal_start,
            "bytes": list(normal),
            "sha256": hashlib.sha256(normal).hexdigest(),
            "instructions": normal_rows,
        },
        "append": {
            "start": append_start,
            "commit_offset": append_commit - append_start,
            "bytes": list(append),
            "sha256": hashlib.sha256(append).hexdigest(),
            "instructions": append_rows,
        },
    }


def agent_source(spec: dict[str, object]) -> str:
    return r"""
const SPEC=%s,RECORD_BASE=%d,RECORD_FLAGS=%d,RECORD_SIZE=%d,PAYLOAD_SIZE=%d,SLOT_COUNT=%d;
function check(value,message){if(!value)throw Error(message);}
function hex(pointer,length){return Array.from(new Uint8Array(pointer.readByteArray(length))).map(v=>v.toString(16).padStart(2,'0')).join('');}
function signed32(value,label){try{return value.toInt32();}catch(_){throw Error('rel32 '+label+' out of range');}}
function rel32(raw,offset,from,target){new DataView(raw.buffer).setInt32(offset,signed32(target.sub(from),'branch'),true);}
function wrapperBytes(append,callOffset,callFrom,callTarget){
 // win64 args: RCX=owner, RDX=previous/current slot, R8=payload.  Preserve
 // the needed values, put the real 0x188-byte temporary record at [rsp+0x30]
 // as observed by the copied code after CALL has pushed its return address,
 // then rebuild exactly the registers live at the installed branch entrance.
 const prefix=Uint8Array.from([
  0x55,0x53,0x48,0x81,0xec,0xc8,0x01,0x00,0x00,
  0x49,0x89,0xcb,0x49,0x89,0xd2,0x4c,0x89,0xc6,
  0x48,0x8d,0x7c,0x24,0x28,0xb9,0x31,0x00,0x00,0x00,0xf3,0x48,0xa5,
  0x4c,0x89,0xdd,0x41,0x8b,0xc2,0x48,0x69,0xc0,0x8c,0x01,0x00,0x00,
  0x4c,0x01,0xd8,0x49,0x89,0xc0
 ]),appendSetup=append?Uint8Array.from([0xbb,1,0,0,0,0x44,0x89,0xd2]):new Uint8Array();
 const call=prefix.length+appendSetup.length;const result=new Uint8Array(call+5+10);
 result.set(prefix);result.set(appendSetup,prefix.length);result[call]=0xe8;rel32(result,call+1,callFrom.add(call+5),callTarget);
 result.set([0x48,0x81,0xc4,0xc8,0x01,0x00,0x00,0x5b,0x5d,0xc3],call+5);
 check(call===callOffset,'wrapper call layout changed');return result;
}
function createClone(){
 const page=Memory.alloc(Process.pageSize),normalAt=page.add(0x200),appendAt=page.add(0x500),normalWrap=page,appendWrap=page.add(0x80);
 const normal=Uint8Array.from(SPEC.normal.bytes),append=Uint8Array.from(SPEC.append.bytes);
 // The installed branches otherwise jump back into log_write's loop.  The
 // test owns that continuation, so only replace the terminal jump by RET.
 normal.set([0xc3,0x90,0x90,0x90,0x90],normal.length-5);append.set([0xc3,0x90],append.length-2);
 const normalWrapper=wrapperBytes(false,50,normalWrap,normalAt),appendWrapper=wrapperBytes(true,58,appendWrap,appendAt);
 const bytes=new Uint8Array(appendAt.add(append.length).sub(page).toInt32()+1).fill(0x90);
 bytes.set(normalWrapper,0);bytes.set(appendWrapper,0x80);bytes.set(normal,0x200);bytes.set(append,0x500);
 Memory.patchCode(page,bytes.length,writable=>writable.writeByteArray(bytes.buffer));
 check(Memory.protect(page,Process.pageSize,'r-x'),'could not protect cloned log writer');
 return {page,normalAt,appendAt,normalCommit:normalAt.add(SPEC.normal.commit_offset),appendCommit:appendAt.add(SPEC.append.commit_offset),normal:new NativeFunction(normalWrap,'void',['pointer','uint','pointer'],'win64'),append:new NativeFunction(appendWrap,'void',['pointer','uint','pointer'],'win64')};
}
function payload(seed,flags){const out=new Uint8Array(RECORD_SIZE);for(let i=0;i<PAYLOAD_SIZE;i++)out[i]=(seed+i*17)&255;new DataView(out.buffer).setUint32(PAYLOAD_SIZE,flags,true);return out;}
function createOwner(){const owner=Memory.alloc(RECORD_BASE+RECORD_SIZE*SLOT_COUNT+0x100);owner.writeByteArray(new Uint8Array(RECORD_BASE+RECORD_SIZE*SLOT_COUNT+0x100));return owner;}
function record(owner,slot){return owner.add(RECORD_BASE+slot*RECORD_SIZE);}
function occupancy(owner,slot){return owner.add(RECORD_FLAGS+slot*RECORD_SIZE);}
function capture(kind,owner,expected,source,expectedFlags){
 const rows=[];return {rows,listener:Interceptor.attach(kind,{onEnter(){
  const actual=this.context.rcx.sub(0x180),legacy=this.context.r8.add(RECORD_BASE);
  rows.push({actual:String(actual),legacy:String(legacy),expected:String(expected),
   payload:hex(actual,PAYLOAD_SIZE),preFlags:actual.add(PAYLOAD_SIZE).readU32(),
   rcx:String(this.context.rcx),r8:String(this.context.r8),source:hex(source,PAYLOAD_SIZE),expectedFlags});
 }})};
}
function execute(clone,isNormal,owner,previous,actualSlot,seed,flags){
 const source=Memory.alloc(RECORD_SIZE),bytes=payload(seed,flags),expected=record(owner,actualSlot);
 // The append branch rejects a destination whose flags have bit 1 set.  Keep
 // the pre-commit sentinel distinct while satisfying that real branch guard.
 const preFlags=(0xdec00000+(actualSlot<<4))>>>0;
 source.writeByteArray(bytes);expected.add(PAYLOAD_SIZE).writeU32(preFlags);
 const observation=capture(isNormal?clone.normalCommit:clone.appendCommit,owner,expected,source,flags);Interceptor.flush();
 if(isNormal)clone.normal(owner,previous,source);else clone.append(owner,previous,source);
 observation.listener.detach();Interceptor.flush();check(observation.rows.length===1,'commit hook count '+(isNormal?'normal':'append')+' '+observation.rows.length);
 const row=observation.rows[0];row.finalPayload=hex(expected,PAYLOAD_SIZE);
 row.green={rcxRecord:row.actual===row.expected,payloadBeforeFlags:row.payload===row.source,
   flagsExcludedAtCommit:row.preFlags===preFlags,finalPayload:row.finalPayload===row.source};
 row.red={legacyR8Record:row.legacy===row.expected};row.stampBytes=PAYLOAD_SIZE;
 delete row.payload;delete row.source;delete row.finalPayload;delete row.expectedFlags;return row;
}
rpc.exports={run(){
 const clone=createClone(),owner=createOwner();
 const normal=execute(clone,true,owner,5,5,0x11,0x11111111);
 // Append starts with the preceding occupied slot.  The copied installed
 // branch selects slot+1 itself, so R8 remains a proof of the old bug.
 occupancy(owner,5).writeU32(1);
 const append=execute(clone,false,owner,5,6,0x22,0x22222222);
 occupancy(owner,1599).writeU32(1);
 const wrap=execute(clone,false,owner,1599,0,0x33,0x33333333);
 for(const row of [normal,append,wrap])for(const [name,value] of Object.entries(row.green))check(value,'green '+name);
 check(normal.red.legacyR8Record,'normal branch legacy R8 baseline');
 check(!append.red.legacyR8Record,'red append R8 incorrectly selected actual record');
 check(!wrap.red.legacyR8Record,'red wrap R8 incorrectly selected actual record');
 return {all_passed:true,game_started:false,game_attached:false,host:'self-created-hidden-python',
  contract:{recordBase:'0x'+RECORD_BASE.toString(16),recordSize:'0x'+RECORD_SIZE.toString(16),payloadSize:'0x'+PAYLOAD_SIZE.toString(16),
   commitRegisters:'RCX is destination + 0x180; the last flags DWORD at +0x188 has not executed'},
  normal,append,wrap};
}};
""" % (json.dumps(spec), RECORD_BASE, RECORD_FLAGS, RECORD_SIZE, PAYLOAD_SIZE, SLOT_COUNT)


def main(executable: Path | None = None) -> None:
    environment = os.environ.get("SORA_GAME_EXE")
    executable = executable or (Path(environment) if environment else None)
    if executable is None:
        print(
            json.dumps(
                {
                    "skipped": True,
                    "reason": "pass --exe or set SORA_GAME_EXE",
                    "game_started": False,
                    "game_attached": False,
                },
                indent=2,
            )
        )
        return
    spec = clone_spec(executable)
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(agent_source(spec), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        report["clone"] = {
            name: {
                "sha256": branch["sha256"],
                "bytes": len(branch["bytes"]),
                "commit": hex(branch["start"] + branch["commit_offset"]),
            }
            for name, branch in (("normal", spec["normal"]), ("append", spec["append"]))
        }
        report["exe_sha256"] = spec["exe_sha256"]
        print(json.dumps(report, indent=2), flush=True)
        assert report["all_passed"]
    finally:
        if session is not None:
            try:
                session.detach()
            except frida.InvalidOperationError:
                pass
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, help="verified sora_2nd.exe; defaults to SORA_GAME_EXE")
    arguments = parser.parse_args()
    main(arguments.exe)
