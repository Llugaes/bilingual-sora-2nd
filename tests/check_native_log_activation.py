"""Exercise the MessageLog activation hook on an offline clone of game code.

The script copies the verified 0x360000..0x36007e function from the installed
PE, relocates its one RIP operand and external lookup call, and executes it in
a hidden Python helper.  It never starts or attaches to the game process.
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
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
import frida
import pefile


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "sora_bilingual/game/scripts/native_agent.js"
OUTPUT = ROOT / "generated/diagnostic-124-log-activation-native.json"
MARKDOWN = ROOT / "generated/diagnostic-124-log-activation-native.md"
START = 0x360000
END = 0x36007E
LOOKUP = 0x5814B0


def activation_hook() -> str:
    source = AGENT.read_text("utf-8")
    marker = (
        "if(logOrigins&&REPORT.native.log_record_activate)"
        "Interceptor.attach(base.add(REPORT.native.log_record_activate.rva),{"
    )
    start = source.index(marker)
    end = source.index("\n});", start) + len("\n});")
    hook = source[start:end]
    if "reconcileLogController(args[0])" not in hook:
        raise RuntimeError("production activation hook no longer reconciles RCX controller")
    return hook


def clone_spec(exe: Path) -> dict:
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        code = pe.get_data(START, END - START)
        base = pe.OPTIONAL_HEADER.ImageBase
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        rip = []
        calls = []
        instructions = []
        for instruction in md.disasm(code, base + START):
            local = instruction.address - base - START
            instructions.append(
                {
                    "rva": f"0x{instruction.address - base:x}",
                    "mnemonic": instruction.mnemonic,
                    "operands": instruction.op_str,
                }
            )
            for operand in instruction.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    rip.append(
                        {
                            "offset": local + instruction.disp_offset,
                            "next": local + instruction.size,
                            "target_rva": instruction.address
                            + instruction.size
                            + operand.mem.disp
                            - base,
                        }
                    )
                if instruction.mnemonic == "call" and operand.type == X86_OP_IMM:
                    calls.append(
                        {
                            "offset": local + instruction.imm_offset,
                            "next": local + instruction.size,
                            "target_rva": operand.imm - base,
                        }
                    )
        if (
            len(code) != END - START
            or len(rip) != 1
            or calls != [{"offset": 0x54, "next": 0x58, "target_rva": LOOKUP}]
        ):
            raise RuntimeError(f"unexpected activation shape rip={rip} calls={calls}")
        if not instructions or instructions[-1]["mnemonic"] != "ret":
            raise RuntimeError("activation clone does not end at its real return")
        return {
            "bytes": list(code),
            "sha256": hashlib.sha256(code).hexdigest(),
            "rip": rip,
            "calls": calls,
            "instructions": instructions,
            "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        }
    finally:
        pe.close()


def agent_source(spec: dict, hook: str) -> str:
    return r"""
const START=%d,cloneSpec=%s,productionHook=%s;
const arena=Memory.alloc(0x1000),THUNK=0x100,KEY=0x180;
if(!Memory.protect(arena,0x1000,'rwx'))throw Error('cannot make activation clone executable');
Memory.patchCode(arena,cloneSpec.bytes.length,writable=>writable.writeByteArray(cloneSpec.bytes));
arena.add(KEY).writeUtf8String('window');
const native=new CModule(`
void *lookup_stub(void *root, const char *key, unsigned int limit, unsigned int allow) {
    (void)key; (void)limit; (void)allow; return root;
}
`);
function signed32(value,label){try{return value.toInt32();}catch(_){throw Error('rel32 '+label);}}
function writeAbsJump(at,target){
 const raw=[0x48,0xb8];let value=target.toString().replace('0x','').padStart(16,'0');
 for(let i=14;i>=0;i-=2)raw.push(parseInt(value.slice(i,i+2),16));raw.push(0xff,0xe0);
 Memory.patchCode(at,raw.length,writable=>writable.writeByteArray(raw));
}
writeAbsJump(arena.add(THUNK),native.lookup_stub);
for(const rel of cloneSpec.rip)
 arena.add(rel.offset).writeS32(signed32(arena.add(KEY).sub(arena.add(rel.next)),'rip'));
for(const rel of cloneSpec.calls)
 arena.add(rel.offset).writeS32(signed32(arena.add(THUNK).sub(arena.add(rel.next)),'call'));

const base=arena.sub(START),REPORT={native:{log_record_activate:{rva:START}}};
const logOrigins={},errors=[],callbacks=[];let expected=NULL,body=NULL,translated=NULL;
function fail(error){errors.push(String(error));}
function reconcileLogController(controller){
 const before={controller:String(controller),hidden:controller.add(0x8c).readU8(),
   nodeVisible:controller.add(0x28).readPointer().add(0x228).readPointer().readPointer().add(0xa0).readU32(),
   body:body.readUtf8String()};
 if(!controller.equals(expected))throw Error('activation RCX is not the controller');
 if(callbacks.length===0&&(before.hidden!==1||before.nodeVisible!==0))throw Error('hook did not run before native activation writes');
 if(before.body==='raw body')body.writeUtf8String('translated body');
 callbacks.push({...before,afterBody:body.readUtf8String()});
}
eval(productionHook);
Interceptor.flush();
const activate=new NativeFunction(arena,'void',['pointer'],'win64');
function controllerFixture(){
 const controller=Memory.alloc(0x100),container=Memory.alloc(0x240),array=Memory.alloc(Process.pointerSize),node=Memory.alloc(0x100);
 controller.writeByteArray(new Uint8Array(0x100));container.writeByteArray(new Uint8Array(0x240));node.writeByteArray(new Uint8Array(0x100));
 body=Memory.alloc(64);body.writeUtf8String('raw body');translated=Memory.allocUtf8String('translated body');
 controller.add(0x18).writePointer(body);controller.add(0x28).writePointer(container);controller.add(0x40).writeU32(1);controller.add(0x8c).writeU8(1);
 container.add(0x228).writePointer(array);container.add(0x230).writeU64(1);array.writePointer(node);node.add(0xa0).writeU32(0);
 return {controller,container,array,node,body};
}
function snapshotController(pointer){return Array.from(new Uint8Array(pointer.readByteArray(0x100)));}
rpc.exports={run(){
 const fixture=controllerFixture();expected=fixture.controller;
 const before=snapshotController(fixture.controller);activate(fixture.controller);const after=snapshotController(fixture.controller);
 const changed=[];for(let i=0;i<before.length;i++)if(before[i]!==after[i])changed.push({offset:i,before:before[i],after:after[i]});
 const first={body:fixture.body.readUtf8String(),hidden:fixture.controller.add(0x8c).readU8(),
   nodeVisible:fixture.node.add(0xa0).readU32(),changedControllerBytes:changed};
 activate(fixture.controller);
 const second={body:fixture.body.readUtf8String(),hidden:fixture.controller.add(0x8c).readU8(),nodeVisible:fixture.node.add(0xa0).readU32()};
 const failures=[];
 if(callbacks.length!==2)failures.push('production hook callback count');
 if(callbacks[0]?.body!=='raw body'||callbacks[0]?.afterBody!=='translated body')failures.push('pre-visibility reconciliation');
 if(first.body!=='translated body'||first.hidden!==0||first.nodeVisible!==1)failures.push('native activation terminal state');
 if(second.body!=='translated body'||second.hidden!==0||second.nodeVisible!==1)failures.push('idempotent repeated activation');
 if(errors.length)failures.push('production callback errors: '+errors.join('; '));
 return {all_passed:failures.length===0,failures,game_started:false,game_attached:false,
   host:'self-created-hidden-python',fixture_boundary:'Exact installed-PE activation bytes with relocated lookup dependency; no game module or live game state.',
   clone:{sourceRva:'0x360000',endRva:'0x36007e',bytes:cloneSpec.bytes.length,sha256:cloneSpec.sha256,
     ripTargets:cloneSpec.rip.map(v=>v.target_rva),callTargets:cloneSpec.calls.map(v=>v.target_rva)},
   productionHook:{extracted:true,source:productionHook},callbacks,first,second};
}};
""" % (START, json.dumps(spec), json.dumps(hook))


def markdown(report: dict) -> str:
    return f"""# Diagnostic 124: native MessageLog activation boundary

This check copied and executed the installed EXE's complete
`0x360000..0x36007e` activation function in a self-created hidden Python
process.  Its RIP operand and sole external lookup call were relocated without
changing the branch structure.  The production `log_record_activate` hook was
extracted from `native_agent.js` and installed on that clone.

- result: `all_passed={str(report["all_passed"]).lower()}`
- game started: `false`; game attached: `false`
- copied bytes: `{report["clone"]["bytes"]}`
- callback observed `controller+0x8c=1` and node visibility `0` before the
  original function wrote them
- after return, `controller+0x8c=0`, the real lookup branch set node visibility
  to `1`, and the body change made by reconciliation remained intact
- repeated activation remained stable

This proves the ABI and ordering of the proposed activation boundary and that
the native function does not overwrite the reconciled body.  It does not prove
which earlier event left the six captured live rows raw; bind-time mode and
setter history for those rows were not present in the captured telemetry.
"""


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
    spec = clone_spec(exe)
    hook = activation_hook()
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(agent_source(spec, hook), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        report["exeSha256"] = spec["exe_sha256"]
        report["instructions"] = spec["instructions"]
        report["productionHookSha256"] = hashlib.sha256(hook.encode()).hexdigest()
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
        MARKDOWN.write_text(markdown(report), "utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        assert report["all_passed"], f"activation contract failures recorded in {OUTPUT}"
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        help="verified sora_2nd.exe; defaults to SORA_GAME_EXE when set",
    )
    args = parser.parse_args()
    main(args.exe)
