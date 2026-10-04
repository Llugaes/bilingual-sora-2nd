"""Read-only nested-ruby audit in a self-created hidden Frida host.

This script never opens or starts the game.  It copies the verified
ruby_context_init bytes from the on-disk PE into the disposable host and drives
them through the production native parser/measurement bridges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import frida
import pefile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_EXE_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
EXPECTED_INIT_SHA256 = "172b31a07764174aa4b5697328f1e5ef742b5dc43cc4a394349dc8cee1ac45ee"
EXPECTED_NEWLINE_SHA256 = "9ca28babc6bcfa22843a612f47900a5d4fdfa3c7452c5632fe03a888d5bfc026"
OUT = ROOT / "generated/diagnostic-130-native-ruby-chain.json"
MD = ROOT / "generated/diagnostic-130-native-ruby-chain.md"
AGENT = Path(
    os.environ.get("NATIVE_AGENT_SOURCE", ROOT / "sora_bilingual/game/scripts/native_agent.js")
).read_text("utf-8")
PARSER = (ROOT / "sora_bilingual/game/scripts/native_parser.js").read_text("utf-8")
MEASURE = (ROOT / "sora_bilingual/game/scripts/native_measure.js").read_text("utf-8")
CALLBACK_START = AGENT.index("const rubyContextCallbacks={")
CALLBACK_END = AGENT.index("\nif(typeof createNativeMeasure", CALLBACK_START)
CALLBACK = AGENT[CALLBACK_START:CALLBACK_END]
COMP_START = AGENT.index("if(REPORT.native.ruby_compensate)")
COMP_END = AGENT.index("\nif(REPORT.native.ruby_end)", COMP_START)
COMPENSATE = AGENT[COMP_START:COMP_END]
if "scope?.metrics&&scope.readingDepth===0" not in COMPENSATE:
    raise RuntimeError("native_agent.js no longer contains the bounded nested-ruby metric hook")


def init_bytes(exe: Path) -> bytes:
    pe = pefile.PE(str(exe), fast_load=True)
    return pe.get_data(0x5830F0, 0x10F)  # through RET at 0x5831fe


def js_source(code: bytes) -> str:
    blob = ",".join(str(v) for v in code)
    newline = bytes.fromhex((ROOT / "tests/fixtures/text_newline_advance.hex").read_text("ascii"))
    if hashlib.sha256(newline).hexdigest() != EXPECTED_NEWLINE_SHA256:
        raise RuntimeError("newline fixture SHA-256 mismatch")
    # Preserve the nonvolatile registers around the relocation-free native
    # newline block. Windows x64 arguments: parser, label, previous bottom.
    newline_wrapper = (
        bytes.fromhex("56 41 55 41 54 48 8b f1 4c 8b ea 45 8b e0")
        + newline
        + bytes.fromhex("41 5c 41 5d 5e c3")
    )
    newline_blob = ",".join(str(v) for v in newline_wrapper)
    return (
        PARSER
        + "\n"
        + MEASURE
        + "\n"
        + f"""
const errors=[],events=[];
function check(v,m){{if(!v)throw Error(m);}}
function close(a,b,e=1e-6){{return Math.abs(a-b)<=e;}}
const initCode=Memory.alloc({len(code)});Memory.protect(initCode,{len(code)},'rwx');
initCode.writeByteArray([{blob}]);
const newlineCode=Memory.alloc({len(newline_wrapper)});Memory.protect(newlineCode,{len(newline_wrapper)},'rwx');
newlineCode.writeByteArray([{newline_blob}]);
const nativeNewline=new NativeFunction(newlineCode,'void',['pointer','pointer','int']);
const driver=new CModule(`
#include <stdint.h>
extern void ruby_init(void *,const char *,uint32_t,float,float,float,float);
void outer_measure(void *p,const char *s,uint32_t n){{ruby_init(p,s,n,.375f,.375f,10.f,20.f);((uint8_t*)p)[0x1a5]=1;((uint8_t*)p)[0x1a9]=0;((uint8_t*)p)[0x1ab]=1;}}
void outer_place(void *p,const char *s,uint32_t n){{ruby_init(p,s,n,.375f,.375f,10.f,20.f);((uint8_t*)p)[0x1a9]=1;}}
void nested_measure(void *p,const char *s,uint32_t n){{ruby_init(p,s,n,.375f,.375f,10.f,20.f);((uint8_t*)p)[0x1a5]=1;}}
void nested_place(void *p,const char *s,uint32_t n){{ruby_init(p,s,n,.375f,.375f,10.f,20.f);}}
void ruby_compensate_marker(void *parent,void *frame,void *label){{}}
void child_parse(uint8_t *label,uint8_t *p,uint8_t *parent,uint32_t *glyph,float *bounds){{
  if(!p[0x1a5]){{float h=*(float *)(p+0x15c)*10.f;*bounds+=h;*(int32_t*)(p+0x1bc)=10;*(int32_t*)(p+0x1c4)=10+(int32_t)(h+.999f);if(p[0x1a9])(*glyph)++;}}
  ruby_compensate_marker(parent,p+0x40,label);
}}
void parse_pair(uint8_t *label,uint8_t *parent,void *m,void *d,const char *s,uint32_t *glyph,float *bounds,uint32_t force,uint32_t *flags){{
  flags[0]=parent[0x1a5];flags[1]=parent[0x1a9];flags[2]=parent[0x1ab];
  if(force) parent[0x1a5]=0;
  if(parent[0x1a5])return;
  outer_measure(m,s,6);child_parse(label,m,parent,glyph,bounds);
  outer_place(d,s,6);child_parse(label,d,parent,glyph,bounds);
}}
void marker(void){{}}
void line_parse(uint8_t *label,uint8_t *p,int height,float origin){{
  /* 0x587824/0x58782e seed both bounds with zero. This intentionally
     retains the paragraph origin in the positioned pass's envelope. */
  *(int32_t*)(p+0x1bc)=0;*(int32_t*)(p+0x1c4)=(int32_t)origin+height;
}}
void layout_line(uint8_t *label,uint8_t *parent,uint8_t *primary,uint8_t *child,const char *s,int height){{
  nested_measure(primary,s,6);line_parse(label,primary,0,0.f);
  outer_measure(child,s,6);line_parse(label,child,height,0.f);
  outer_place(child,s,6);line_parse(label,child,height,*(float*)(parent+4));
  ruby_compensate_marker(parent,child+0x40,label);
}}
`,{{ruby_init:initCode}});
const outerMeasure=new NativeFunction(driver.outer_measure,'void',['pointer','pointer','uint']);
const outerPlace=new NativeFunction(driver.outer_place,'void',['pointer','pointer','uint']);
const parsePair=new NativeFunction(driver.parse_pair,'void',['pointer','pointer','pointer','pointer','pointer','pointer','pointer','uint','pointer']);
const nestedPlace=new NativeFunction(driver.nested_place,'void',['pointer','pointer','uint']);
function captureCaller(fn){{let v=null;const h=Interceptor.attach(initCode,{{onEnter(){{v=this.returnAddress;}}}});Interceptor.flush();fn();h.detach();Interceptor.flush();return v;}}
const dummy=Memory.alloc(0x300),text=Memory.allocUtf8String('nested');
const cOuterMeasure=captureCaller(()=>outerMeasure(dummy,text,6));
const cOuterPlace=captureCaller(()=>outerPlace(dummy,text,6));
const cNestedMeasure=captureCaller(()=>new NativeFunction(driver.nested_measure,'void',['pointer','pointer','uint'])(dummy,text,6));
const cNestedPlace=captureCaller(()=>nestedPlace(dummy,text,6));
const base=cOuterMeasure;
const REPORT={{native:{{ruby_measure_return:{{rva:cOuterMeasure.sub(base).toInt32()}},ruby_base_measure_return:{{rva:cNestedMeasure.sub(base).toInt32()}},ruby_place_return:{{rva:cNestedPlace.sub(base).toInt32()}},ruby_compensate:{{rva:driver.ruby_compensate_marker.sub(base).toInt32()}}}},diagnostics:false}};
// The production callback treats our outer placement caller as the placement return.
REPORT.native.ruby_place_return.rva=cOuterPlace.sub(base).toInt32();
const auxiliaryContexts=new Map();
const nativeParser=createNativeParser(auxiliaryContexts,e=>errors.push(String(e)));
const rubyScale=.8,rubyOffsetX=0,annotationScale=.85,annotationMetrics=new Map(),compensation=new Map();
const label=Memory.alloc(0x900),rootParser=label.add(0x400),frame=Memory.alloc(0x500);
const row={{pointer:label,original:'source',plan:{{kind:'layered'}},glyphLanes:[]}};
const layerText=Memory.allocUtf8String('<R>x</Ry>secondary'),primaryText=Memory.allocUtf8String('<R>p</Rq>primary');
const layer={{row,parser:rootParser,layer:{{text:'<R>x</Ry>secondary',primary:'<R>p</Rq>primary'}},buffer:layerText,primaryBuffer:primaryText}};
function fail(e){{errors.push(String(e));}}
function ownedRow(p){{return p.equals(label)?row:null;}}
function auxiliaryLayer(p,parser,r){{return p.equals(label)&&parser.equals(rootParser)?layer:null;}}
function beginAnnotationLane(){{}}
function inheritAuxiliaryIcons(){{}}
{CALLBACK}
const nativeMeasure=createNativeMeasure(rubyContextCallbacks,{{measurement:cOuterMeasure,baseMeasurement:cNestedMeasure,placement:cOuterPlace}},fail,nativeParser);
const prepareLabel=Memory.alloc(Process.pointerSize),prepareParent=Memory.alloc(Process.pointerSize),prepareFrame=Memory.alloc(Process.pointerSize);
prepareLabel.writePointer(label);prepareParent.writePointer(rootParser);prepareFrame.writePointer(frame);
const prepare=new CModule(`
#include <stdint.h>
#include <gum/guminterceptor.h>
typedef struct{{uint64_t r15,rbx,rbp;}}Saved;
extern void *pl,*pp,*pf;
void enter(GumInvocationContext *ic){{Saved*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved);GumCpuContext*c=ic->cpu_context;s->r15=c->r15;s->rbx=c->rbx;s->rbp=c->rbp;c->r15=(uint64_t)(uintptr_t)pl;c->rbx=(uint64_t)(uintptr_t)pp;c->rbp=(uint64_t)(uintptr_t)pf;}}
void leave(GumInvocationContext *ic){{Saved*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved);GumCpuContext*c=ic->cpu_context;c->r15=s->r15;c->rbx=s->rbx;c->rbp=s->rbp;}}
`,{{pl:prepareLabel,pp:prepareParent,pf:prepareFrame}});
const hPrepare=Interceptor.attach(initCode,{{onEnter:prepare.enter,onLeave:prepare.leave}});
const hMeasure=Interceptor.attach(initCode,{{onEnter:nativeMeasure.onEnter,onLeave:nativeMeasure.onLeave}});
const hParsePair=Interceptor.attach(driver.parse_pair,{{onEnter:nativeParser.onEnter,onLeave:nativeParser.onLeave}});
const hChild=Interceptor.attach(driver.child_parse,{{onEnter:nativeParser.onEnter,onLeave:nativeParser.onLeave}});
const compPrepare=new CModule(`
#include <stdint.h>
#include <gum/guminterceptor.h>
typedef struct{{uint64_t r15,rbx,rbp;}}Saved2;
void enter2(GumInvocationContext *ic){{Saved2*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved2);GumCpuContext*c=ic->cpu_context;s->r15=c->r15;s->rbx=c->rbx;s->rbp=c->rbp;c->rbx=(uint64_t)(uintptr_t)gum_invocation_context_get_nth_argument(ic,0);c->rbp=(uint64_t)(uintptr_t)gum_invocation_context_get_nth_argument(ic,1);c->r15=(uint64_t)(uintptr_t)gum_invocation_context_get_nth_argument(ic,2);}}
void leave2(GumInvocationContext *ic){{Saved2*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved2);GumCpuContext*c=ic->cpu_context;c->r15=s->r15;c->rbx=s->rbx;c->rbp=s->rbp;}}
`);
const hCompPrepare=Interceptor.attach(driver.ruby_compensate_marker,{{onEnter:compPrepare.enter2,onLeave:compPrepare.leave2}});
{COMPENSATE}
Interceptor.flush();
function u32(){{const p=Memory.alloc(4);p.writeU32(0);return p;}}function f32(){{const p=Memory.alloc(4);p.writeFloat(0);return p;}}
function fresh(){{return Memory.alloc(0x300);}}
const baseMeasure=new NativeFunction(driver.nested_measure,'void',['pointer','pointer','uint']);
const childParse=new NativeFunction(driver.child_parse,'void',['pointer','pointer','pointer','pointer','pointer']);
function outer(call,target){{prepareParent.writePointer(rootParser);const b=fresh(),g=u32(),v=f32();baseMeasure(b,text,6);childParse(label,b,b,g,v);call(target,text,6);}}
function outerWithoutMetrics(call,target){{annotationMetrics.clear();prepareParent.writePointer(rootParser);call(target,text,6);}}
// Draw: normal native C call chain, production slow bridge and production callbacks.
const drawParent=fresh();outer(outerPlace,drawParent);check(close(drawParent.add(0x15c).readFloat(),.3),'outer draw scale');
const drawM=fresh(),drawD=fresh(),drawGlyph=u32(),drawBounds=f32(),drawFlags=Memory.alloc(12);prepareParent.writePointer(drawParent);
parsePair(label,drawParent,drawM,drawD,text,drawGlyph,drawBounds,0,drawFlags);
const draw={{outer_scale:drawParent.add(0x15c).readFloat(),nested_measure_scale:drawM.add(0x15c).readFloat(),nested_place_scale:drawD.add(0x15c).readFloat(),glyphs:drawGlyph.readU32(),bounds:drawBounds.readFloat()}};
// Measurement: current production parser sets placement=false contexts to 1a5=1.
const measureParent=fresh();outer(outerMeasure,measureParent);check(close(measureParent.add(0x15c).readFloat(),.3),'outer measure scale');
const callsiteFlags=[measureParent.add(0x1a5).readU8(),measureParent.add(0x1a9).readU8(),measureParent.add(0x1ab).readU8()];
const mm=fresh(),md=fresh(),mg=u32(),mb=f32(),mf=Memory.alloc(12);prepareParent.writePointer(measureParent);
parsePair(label,measureParent,mm,md,text,mg,mb,0,mf);
const measurementCurrent={{callsite_flags_1a5_1a9_1ab:callsiteFlags,parse_entry_flags_1a5_1a9_1ab:[mf.readU32(),mf.add(4).readU32(),mf.add(8).readU32()],parent_1a5:measureParent.add(0x1a5).readU8(),glyphs:mg.readU32(),bounds:mb.readFloat(),nested_init_seen:mm.add(0x15c).readFloat()!==0}};
measurementCurrent.metrics={{...annotationMetrics.get(String(rootParser))}};
// Red-capable negative: the same production path without the explicit owned metrics scope.
const negativeParent=fresh();outerWithoutMetrics(outerMeasure,negativeParent);const nm=fresh(),nd=fresh(),ng=u32(),nb=f32(),nf=Memory.alloc(12);prepareParent.writePointer(negativeParent);
parsePair(label,negativeParent,nm,nd,text,ng,nb,0,nf);
const withoutAllowReadings={{parent_1a5:negativeParent.add(0x1a5).readU8(),glyphs:ng.readU32(),bounds:nb.readFloat(),nested_init_seen:nm.add(0x15c).readFloat()!==0}};
// Bounded candidate field contract: force only this known measuring parent to read R.
const candidateParent=fresh();outer(outerMeasure,candidateParent);const cm=fresh(),cd=fresh(),cg=u32(),cb=f32(),cf=Memory.alloc(12);prepareParent.writePointer(candidateParent);
parsePair(label,candidateParent,cm,cd,text,cg,cb,1,cf);
const candidate={{parent_1a5:candidateParent.add(0x1a5).readU8(),glyphs:cg.readU32(),bounds:cb.readFloat(),nested_measure_scale:cm.add(0x15c).readFloat(),nested_place_scale:cd.add(0x15c).readFloat()}};
// Explicit suppression control: a NativeFunction invoked from JS Interceptor does not re-enter init hooks.
let suppressedTarget=fresh();prepareParent.writePointer(drawParent);const before=nativeMeasure.status().slow;
const markerHook=Interceptor.attach(driver.marker,{{onEnter(){{outerPlace(suppressedTarget,text,6);}}}});Interceptor.flush();
new NativeFunction(driver.marker,'void',[])();markerHook.detach();Interceptor.flush();
const suppression={{slow_callbacks_before:before,slow_callbacks_after:nativeMeasure.status().slow,scale:suppressedTarget.add(0x15c).readFloat()}};
// Both passes reuse the SAME child and execute the exact resetting initializer.
// Child font-cell bounds do not authorize moving the outer line.
// This boundary only rejects accidental extra reserve; it is not a font layout test.
const hLine=Interceptor.attach(driver.line_parse,{{onEnter:nativeParser.onEnter,onLeave:nativeParser.onLeave}});
const layoutLine=new NativeFunction(driver.layout_line,'void',['pointer','pointer','pointer','pointer','pointer','int']);
const multiline=[];
row.preservePrimaryLayout=false;
const rubyGap=0;
for(const measuring of [false,true])for(const initial of [0,200])for(const height of [18,22,40])for(const count of [1,2,5,20])for(const leading of [-1,0,15,24,40]){{
  rootParser.add(4).writeFloat(initial);rootParser.add(0x1ab).writeU8(measuring?1:0);
  rootParser.add(0x16c).writeU32(0);label.add(0x2f4).writeS32(leading);
  prepareParent.writePointer(rootParser);
  const primary=fresh(),child=fresh();let good=true,expectedAdvance=0;
  for(let i=0;i<count;i++){{
    const origin=rootParser.add(4).readFloat();
    layoutLine(label,rootParser,primary,child,text,height);
    const delta=rootParser.add(4).readFloat()-origin;
    const expected=0;
    good=good&&close(delta,expected);
    // Exact 0x587966..0x5879a1 instructions: signed native leading and
    // first/subsequent-line identity come from the real parser, not a mock.
    nativeNewline(rootParser,label,rootParser.add(4).readFloat()+34+6);
    good=good&&rootParser.add(0x16c).readU32()===i+1;
    expectedAdvance+=expected+34+6+leading;
  }}
  const advance=rootParser.add(4).readFloat()-initial;
  multiline.push({{measuring,initial,height,count,leading,advance,ok:good&&close(advance,expectedAdvance)}});
}}
rootParser.add(4).writeFloat(200);layoutLine(label,rootParser,fresh(),fresh(),text,40);
const singleLineUnchanged=close(rootParser.add(4).readFloat(),200);
hLine.detach();
hCompPrepare.detach();hChild.detach();hParsePair.detach();hMeasure.detach();hPrepare.detach();Interceptor.flush();
const required={{draw_nested_scale:close(draw.nested_place_scale,.1125),callsite_overwrites_then_parse_repairs:JSON.stringify(measurementCurrent.callsite_flags_1a5_1a9_1ab)==='[1,0,1]'&&JSON.stringify(measurementCurrent.parse_entry_flags_1a5_1a9_1ab)==='[0,0,1]',measuring_glyph_count_unchanged:measurementCurrent.glyphs===0,measuring_bounds_include_native_r:measurementCurrent.bounds>0,production_metric_primary_nonzero:measurementCurrent.metrics.primary>0,production_metric_secondary_nonzero:measurementCurrent.metrics.secondary>0,negative_without_allow_readings_is_red:withoutAllowReadings.bounds===0&&!withoutAllowReadings.nested_init_seen,normal_chain_not_suppressed:nativeMeasure.status().slow>0,suppression_control_observed:suppression.slow_callbacks_after===suppression.slow_callbacks_before&&close(suppression.scale,.375),no_ordinary_auxiliary_reserve:multiline.every(v=>v.ok),single_line_unchanged:singleLineUnchanged}};
rpc.exports.run=()=>({{host:'self-created-hidden-python',game_attached:false,game_started:false,exact_initializer_bytes:true,callers:{{outer_measure:String(cOuterMeasure),outer_place:String(cOuterPlace),nested_measure:String(cNestedMeasure),nested_place:String(cNestedPlace)}},draw,measurement_current:measurementCurrent,negative_without_allow_readings:withoutAllowReadings,candidate,suppression,multiline,required,native_measure_status:nativeMeasure.status(),native_parser_status:nativeParser.status(),errors}});
"""
    )


def run_host(source: str) -> dict:
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"], creationflags=0x08000000
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(source, runtime="v8")
        messages: list[dict] = []
        script.on("message", lambda message, data: messages.append(message))
        script.load()
        if messages:
            raise RuntimeError(json.dumps(messages, indent=2))
        return script.exports_sync.run()
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


def main(exe: Path | None = None) -> None:
    environment = os.environ.get("SORA_GAME_EXE")
    exe = exe or (Path(environment) if environment else None)
    # CI must exercise this boundary without having the copyrighted game.
    # The 271-byte constructor fixture is verified against the supported PE
    # locally; it has no game data or direct calls to game code.
    code = bytes.fromhex((ROOT / "tests/fixtures/ruby_context_init.hex").read_text("ascii"))
    exe_hash = None
    if exe is not None:
        if not exe.is_file():
            raise SystemExit(f"missing verified executable: {exe}")
        exe_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
        if exe_hash != EXPECTED_EXE_SHA256:
            raise SystemExit(f"unsupported sora_2nd.exe SHA-256: {exe_hash}")
        if init_bytes(exe) != code:
            raise SystemExit("initializer fixture differs from the supported game")
        pe = pefile.PE(str(exe), fast_load=True)
        try:
            newline = bytes.fromhex(
                (ROOT / "tests/fixtures/text_newline_advance.hex").read_text("ascii")
            )
            if pe.get_data(0x587966, 0x3B) != newline:
                raise SystemExit("newline fixture differs from the supported game")
        finally:
            pe.close()
    if hashlib.sha256(code).hexdigest() != EXPECTED_INIT_SHA256:
        raise SystemExit("initializer fixture SHA-256 mismatch")
    host = run_host(js_source(code))
    agent_hash = hashlib.sha256(AGENT.encode()).hexdigest()
    report = {
        "scope": "static on-disk PE plus self-created hidden Python host; no game process opened, attached, injected, or started",
        "exe_sha256": exe_hash,
        "initializer_sha256": EXPECTED_INIT_SHA256,
        "newline_sha256": EXPECTED_NEWLINE_SHA256,
        "native_agent_sha256": agent_hash,
        "production_callback_sha256": hashlib.sha256(CALLBACK.encode()).hexdigest(),
        "production_compensate_sha256": hashlib.sha256(COMPENSATE.encode()).hexdigest(),
        "static_contract": {
            "parent_register": "0x58675e mov rbx,rdx; all three initializer callbacks therefore see the current parent parser in context.rbx",
            "measurement_gate": "0x586f3c skips the complete native-R reading branch when parent+0x1a5 != 0",
            "measurement_child": "0x587084 sets child+0x1a5=1, 0x58708b copies parent+0x1ab, then 0x58709f parses it",
            "drawing_child": "0x58714f begins placement setup, 0x587210 copies parent+0x1ab, then 0x587224 parses it",
            "glyph_gate": "glyph bounds are accumulated before 0x5881e5 tests child+0x1a9; 1a9=0 skips the output block while preserving measurement work",
            "line_origin": "0x588570 immediately returns for parser+0x1ab; draw first-line subtracts label+0x2fc/global+0x6a4 and later lines add label+0x2f8",
            "local_height": "0x58709f parses the child at zero origin; capture its bounds on entry to 0x58714a before the resetting constructor; parse_text 0x587824/0x58782e zero-seeds the later positioned envelope",
            "native_leading": "0x587966..0x5879a1 adds signed label+0x2f4 to the previous bottom and increments parser+0x16c; auxiliary font-cell height must not add another reserve to native advances",
        },
        "host": host,
        "decision": {
            "nested_draw_callback": "passes in the hidden host; this does not explain the screenshot by itself",
            "current_measurement": "the extracted production sources pass the bounded host: explicit owned metrics scope sets allowReadings while keeping output disabled; the no-scope negative remains red",
            "bounded_permission": "supported only for an owned layered measurement context with 1a9=0, 1ab=1 and explicit allowReadings; do not clear 1a5 globally",
            "suppression": "real and red-capable when the initializer is invoked synchronously inside a JS Interceptor callback; the normal C recursive chain is not suppressed",
        },
        "limits": [
            "The host executes the exact initializer and production callback/parser/measurement bridges, but its child_parse is a field-level fixture backed by static instructions rather than a clone of parse_text.",
            "It proves the scale/lifetime/suppression and absence of extra auxiliary reserve, not the required visible inter-line gap. The unresolved tutorial gap remains a failing Node check.",
            "The current normal draw path passing means a live failure still needs candidate restart evidence; it must not be declared fixed from this host.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    req = host["required"]
    MD.write_text(
        f"""# Diagnostic 130: native nested ruby chain

## 结论

隐藏宿主确认正常原生 C 调用链会进入生产 `rubyContextCallbacks`：外层副文倍率为 `{host["draw"]["outer_scale"]:.6f}`，内层 native R placement 为 `{host["draw"]["nested_place_scale"]:.6f}`（固定 0.375 × 外层 0.3 = 0.1125）。因此现有 draw 回调链在该 seam 通过，不能单凭这个结果宣称已修复截图中的“第二层未缩小”。

红灯对照仍可复现：没有显式 `allowReadings` 的同一路径把 `+0x1a5` 设为 1，机器码在 0x586f3c 跳过整段 native R，bounds 为 `{host["negative_without_allow_readings"]["bounds"]}`。提取的生产代码只对已登记的 owned layered measurement scope 允许 readings，并保持 `+0x1a9=0,+0x1ab=1`；此时 glyph count 仍为 `{host["measurement_current"]["glyphs"]}`，bounds 增为 `{host["measurement_current"]["bounds"]:.6f}`，生产 `ruby_compensate` 回调实际写得 `metrics.primary={host["measurement_current"]["metrics"]["primary"]}`、`metrics.secondary={host["measurement_current"]["metrics"]["secondary"]}`，两个 nested context 都得到 `{host["candidate"]["nested_place_scale"]:.6f}`。

真实 Frida 抑制边界也被触发：在 JS Interceptor 回调内同步调用 initializer 时，slow callback 计数不变，scale 保持 `{host["suppression"]["scale"]:.6f}`；正常 C 递归链不会触发该抑制。这个对照能让未来测试在调用位置变化时变红。

## 推荐决策

保留有界合同：`allowReadings` 默认关闭，只给 owned layered anchor 的已登记预测量 context；measurement 保持 `1a9=0,1ab=1`。不要全局清 `1a5`。嵌套 R 的额外行高必须来自测量 child bounds，并分别覆盖首行与后续行；0x588570 在 measurement (`1ab=1`) 下立即返回，不能拿 draw-only 的 first-line origin 分支证明测量已留高。

## 证据边界

宿主执行了磁盘 EXE 0x5830f0–0x5831fe 的原字节、生产 native C slow bridge、生产 parser registry 和生产 callback 源码。`child_parse` 是依据 0x586f3c、0x587e77/0x58814f 与 0x5881e5 构造的字段级 seam，没有克隆字体与 renderer 依赖很重的完整 `parse_text`。最终仍需新候选进程验证 secondary native R 字形尺寸及首行/换行高度。

断言：`{json.dumps(req, ensure_ascii=False)}`。
""",
        "utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not host["errors"], f"nested-ruby bridge errors recorded in {OUT}"
    assert all(host["required"].values()), f"nested-ruby contract failures recorded in {OUT}"
    assert host["native_parser_status"]["active"] == 0, (
        f"nested-ruby parser scope leaked; see {OUT}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        help="verified sora_2nd.exe; defaults to SORA_GAME_EXE when set",
    )
    args = parser.parse_args()
    main(args.exe)
