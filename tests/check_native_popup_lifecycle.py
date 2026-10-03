"""Cold popup sizing, before Update, in a disposable hidden native host.

Runs the supported EXE's 0x536c50 flag-finalization bytes and production reset
bridge/preparation. The measurement fixture is intentionally small; it proves
callback ordering and the consumer boundary, not font rasterization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pefile

from check_native_nested_ruby import run_host


ROOT = Path(__file__).resolve().parents[1]
AGENT = Path(
    os.environ.get("NATIVE_AGENT_SOURCE", ROOT / "sora_bilingual/game/scripts/native_agent.js")
).read_text("utf-8")
BRIDGE = (ROOT / "sora_bilingual/game/scripts/native_measure.js").read_text("utf-8")


def bootstrap_source() -> str:
    resolver = (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf-8")
    return (
        BRIDGE
        + "\n"
        + resolver
        + "\n"
        + r"""
const retained=[],messages=[];
const boot=new Function('Process','REPORT','RuntimeText','scriptSha256','createNativeTextReset','send',__AGENT__+'\nreturn rpc.exports;');
function start(corrupt){
  const base=Memory.alloc(4096);retained.push(base);Memory.protect(base,4096,'rwx');
  const report={vtable:0x800,native:{}};
  ['set_text','reset_text','measure_text','update','destroy','ruby_context_init','ruby_measure_return','ruby_base_measure_return','ruby_place_return'].forEach((key,i)=>{
    const rva=i*64;base.add(rva).writeByteArray(Array(32).fill(0x90));base.add(rva+32).writeU8(0xc3);
    report.native[key]={rva,bytes:'90'.repeat(16)};
  });
  if(corrupt)base.add(report.native.ruby_place_return.rva).writeU8(0xcc);
  let status=null,error=null;
  try{
    const api=boot({getModuleByName(){return {base};},getCurrentThreadId(){return Process.getCurrentThreadId();}},
      report,RuntimeText,()=>'',createNativeTextReset,m=>messages.push(m));
    status=api.status();
    const label=Memory.alloc(0x700);label.add(0x689).writeU8(1);
    new NativeFunction(base.add(report.native.reset_text.rva),'void',['pointer'])(label);
  }catch(e){error=String(e);}
  Interceptor.flush();
  const resetPatched=base.add(report.native.reset_text.rva).readU8()!==0x90;
  return {error,status,resetPatched};
}
const clean=start(false),foreign=start(true);
rpc.exports.run=()=>({clean,foreign,messages,ok:!clean.error&&!clean.status.failed&&clean.resetPatched&&!!foreign.error&&!foreign.resetPatched});
""".replace("__AGENT__", json.dumps(AGENT))
    )


def source(code: bytes, install: bool, listener: bool = False) -> str:
    begin = AGENT.find("function textLayoutChanged(")
    end = AGENT.find("\nconst nativeTextReset=", begin)
    prepare = (
        AGENT[begin:end] if begin >= 0 and end >= 0 else "function prepareTextReset(){return 0;}"
    )
    return (
        BRIDGE
        + "\n"
        + r"""
const code=Memory.alloc(4096);Memory.protect(code,4096,'rwx');code.writeByteArray(__CODE__);
const native=new CModule(`
#include <stdint.h>
void *label_get(unsigned char *owner){return *(void **)(owner+0xc8);}
void measure(unsigned char *p){
  int kind=**(unsigned char **)(p+0x318);
  /* The hook contributes a controlled 23 units. A setter inside an
     Interceptor listener loses it; the production replacement must not. */
  *(int *)(p+0x374)=(kind=='L'?595:kind=='R'?450:300)-p[0x6a0];
  p[0x6a0]=0;p[0x689]=0;(*(int *)(p+0x6a4))++;
}
void setter(unsigned char *p,void *text){*(void **)(p+0x318)=text;measure(p);}
void reset_text(unsigned char *p){
  *(float *)(p+0x378)=0;*(void **)(p+0x408)=*(void **)(p+0x318);
  (*(int *)(p+0x6a8))++;
}
extern void finalize_flags(void *);
int open_popup(unsigned char *owner,int instant){
  unsigned char *p=label_get(owner);
  *(int *)(owner+8)=instant;finalize_flags(owner);reset_text(p);
  /* 0x533f42 reads label+374 minus +36c, then adds native padding 60.
     No Update runs between flag finalization, reset and this consumption. */
  return *(int *)(p+0x374)-*(int *)(p+0x36c)+60;
}
`,{finalize_flags:code});
const p=Memory.alloc(0x800),owner=Memory.alloc(0x120),vtable=Memory.alloc(0xa0);
vtable.add(0x58).writePointer(native.label_get);owner.writePointer(vtable);owner.add(0xc8).writePointer(p);
const labels=new Map(),labelCallbacks=new Map(),errors=[];
let epoch=1,mode='annotation',row,writes=0,hookMeasures=0,prepareCalls=0;
function isLabel(label){return label.equals(p);}
function activeRewrite(){return false;}
function enterLabel(label){const key=String(label),lease={key};labelCallbacks.set(key,lease);return lease;}
function leaveLabel(lease){labelCallbacks.delete(lease.key);}
function readText(label){return label.add(0x318).readPointer().readUtf8String();}
const setter=new NativeFunction(native.setter,'void',['pointer','pointer']);
function copyOwnedText(row,text){setter(p,Memory.allocUtf8String(text));row.displayed=text;writes++;}
function captureMetadata(row){row.metadata={flags:p.add(0x2e8).readU32()};}
function wantedText(row){
  row.renderSize=p.add(0x304).readU32();
  row.plan={kind:mode==='annotation'?(p.add(0x2e8).readU32()&4?'layered':'ruby'):'plain'};
  return row.plan.kind==='layered'?'L':row.plan.kind==='ruby'?'R':'P';
}
function fail(e){errors.push(String(e));}
__PREPARE__
Interceptor.attach(native.measure,{onEnter(args){hookMeasures++;if(readText(args[0])==='R')args[0].add(0x6a0).writeU8(23);}});
const bridge=__INSTALL__?createNativeTextReset(native.reset_text,native.measure,label=>{prepareCalls++;return prepareTextReset(label);}):null;
if(__LISTENER__)Interceptor.attach(native.reset_text,{onEnter(args){prepareTextReset(args[0]);}});
const open=new NativeFunction(native.open_popup,'int',['pointer','int']);
const reset=new NativeFunction(native.reset_text,'void',['pointer']);
Interceptor.flush();
function seed(kind,flags){
  p.writeByteArray(new Uint8Array(0x800));p.add(0x318).writePointer(Memory.allocUtf8String(kind));
  p.add(0x304).writeU32(33);p.add(0x2e8).writeU32(flags);p.add(0x374).writeS32(kind==='L'?595:kind==='R'?427:300);
  row={pointer:p,original:'P',displayed:kind,renderSize:33,metadata:{flags},epoch,
    plan:{kind:kind==='L'?'layered':kind==='R'?'ruby':'plain'}};
  labels.clear();labels.set(String(p),row);mode='annotation';writes=hookMeasures=prepareCalls=0;
}
const cases=[];
for(const [kind,flags,instant,expected] of [['L',0x365,1,487],['R',0x361,0,655]]){
  seed(kind,flags);const height=open(owner,instant),first={writes,hookMeasures,prepareCalls};
  reset(p);const stable={writes,hookMeasures,prepareCalls};
  cases.push({kind,height,expected,first,stable,text:readText(p),flags:p.add(0x2e8).readU32(),
    parser_owns_final_buffer:p.add(0x408).readPointer().equals(p.add(0x318).readPointer()),
    ok:height===expected&&hookMeasures===1&&writes===1&&JSON.stringify(first)===JSON.stringify(stable)});
}
seed('L',0x365);mode='primary';epoch++;const primary=open(owner,1);
const singleLanguage={height:primary,ok:primary===360&&readText(p)==='P'};
seed('P',0x365);mode='primary';const unowned=open(owner,1);
const plain={height:unowned,writes,hookMeasures,ok:unowned===360&&writes===0&&hookMeasures===0};
seed('L',0x365);labelCallbacks.set(String(p),{key:String(p)});p.add(0x689).writeU8(1);reset(p);
const nestedUpdate={writes,hookMeasures,ok:writes===0&&hookMeasures===0};labelCallbacks.clear();
rpc.exports.run=()=>({cases,singleLanguage,plain,nestedUpdate,errors,
  all_passed:cases.every(v=>v.ok)&&singleLanguage.ok&&plain.ok&&nestedUpdate.ok&&!errors.length});
""".replace("__CODE__", json.dumps(list(code)))
        .replace("__PREPARE__", prepare)
        .replace("__INSTALL__", "true" if install else "false")
        .replace("__LISTENER__", "true" if listener else "false")
    )


def main(exe: Path | None) -> None:
    code = bytes.fromhex((ROOT / "tests/fixtures/popup_label_flags.hex").read_text("ascii"))
    assert (
        hashlib.sha256(code).hexdigest()
        == "1d29517ec48823ce09373583ac55632195a4a5841a612dbac69312c47c3ad12a"
    )
    if exe:
        pe = pefile.PE(str(exe), fast_load=True)
        assert pe.get_data(0x536C50, 0x57) == code, "late-flag fixture differs from game"
    negative = run_host(source(code, False))
    suppressed = run_host(source(code, False, True))
    candidate = run_host(source(code, True))
    startup = run_host(bootstrap_source())
    report = {
        "game_attached": False,
        "game_started": False,
        "fixture_sha256": hashlib.sha256(code).hexdigest(),
        "native_agent_sha256": hashlib.sha256(AGENT.encode()).hexdigest(),
        "negative_without_boundary": negative,
        "negative_listener_suppression": suppressed,
        "candidate": candidate,
        "production_agent_startup": startup,
        "limits": "Exact native flag finalization plus production reset; font metrics and parent padding are a bounded consumer fixture, not the complete renderer.",
    }
    (ROOT / "generated/popup-lifecycle-regression.json").write_text(
        json.dumps(report, indent=2) + "\n", "utf-8"
    )
    print(json.dumps(report, indent=2))
    assert not negative["all_passed"], "negative control unexpectedly passed"
    assert not suppressed["all_passed"], "listener suppression control unexpectedly passed"
    assert candidate["all_passed"], "popup consumer did not receive finalized bounds"
    assert startup["ok"], "production agent startup/preflight failed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path)
    main(parser.parse_args().exe)
