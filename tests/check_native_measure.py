"""Offline validation for createNativeMeasure's C/Gum fast predicate and slow bridge."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "sora_bilingual/game/scripts/native_measure.js").read_text("utf-8")
OUTPUT = ROOT / "generated/diagnostic-091-native-measure.json"


def script_source() -> str:
    return (
        SOURCE
        + r"""
const fixture=new CModule(`
#include <stdint.h>
int ruby_context_init_fixture(void *target, int first, int second) { return first*31+second*17+19; }
void measurement_return(void) {}
void base_measurement_return(void) {}
`,{});
const driver=new CModule(`
#include <stdint.h>
extern int ruby_context_init_fixture(void *,int,int);
uint64_t run(void *target, uint32_t count) { uint64_t sum=0;uint32_t i;for(i=0;i<count;i++)sum+=(uint32_t)ruby_context_init_fixture(target,2,3);return sum; }
uint64_t run_measure(void *target, uint32_t count) { uint64_t sum=0;uint32_t i;for(i=0;i<count;i++){*((float *)((uint8_t *)target+0x158))=1.234567f;*((float *)((uint8_t *)target+0x15c))=7.654321f;sum+=(uint32_t)ruby_context_init_fixture(target,2,3);}return sum; }
uint64_t run_base(void *target, uint32_t count) { uint64_t sum=0;uint32_t i;for(i=0;i<count;i++){*((float *)((uint8_t *)target+0x158))=1.234567f;*((float *)((uint8_t *)target+0x15c))=7.654321f;sum+=(uint32_t)ruby_context_init_fixture(target,2,3);}return sum; }
`,{ruby_context_init_fixture:fixture.ruby_context_init_fixture});
const capturedCaller=Memory.alloc(8),prepareLabel=Memory.alloc(Process.pointerSize),prepareParser=Memory.alloc(Process.pointerSize),prepareRestored=Memory.alloc(8);
const capture=new CModule(`
#include <stdint.h>
#include <gum/guminterceptor.h>
extern uint64_t captured_caller;
void capture_on_enter(GumInvocationContext *ic) { captured_caller=(uint64_t)(uintptr_t)gum_invocation_context_get_return_address(ic); }
`,{captured_caller:capturedCaller});
const prepare=new CModule(`
#include <stdint.h>
#include <gum/guminterceptor.h>
typedef struct { uint64_t r15,rbx; } Saved;
extern void *prepare_label; extern void *prepare_parser; extern uint64_t prepare_restored;
void prepare_on_enter(GumInvocationContext *ic) { Saved *saved=GUM_IC_GET_INVOCATION_DATA(ic,Saved); GumCpuContext *cpu=ic->cpu_context;saved->r15=cpu->r15;saved->rbx=cpu->rbx;cpu->r15=(uint64_t)(uintptr_t)prepare_label;cpu->rbx=(uint64_t)(uintptr_t)prepare_parser; }
void prepare_on_leave(GumInvocationContext *ic) { Saved *saved=GUM_IC_GET_INVOCATION_DATA(ic,Saved); GumCpuContext *cpu=ic->cpu_context;cpu->r15=saved->r15;cpu->rbx=saved->rbx;prepare_restored++; }
`,{prepare_label:prepareLabel,prepare_parser:prepareParser,prepare_restored:prepareRestored});
const kernel=Process.getModuleByName('kernel32.dll'),tick=Memory.alloc(8),frequency=Memory.alloc(8);
const qpc=new NativeFunction(kernel.getExportByName('QueryPerformanceCounter'),'int',['pointer']);
const qpf=new NativeFunction(kernel.getExportByName('QueryPerformanceFrequency'),'int',['pointer']);qpf(frequency);
function now(){qpc(tick);return tick.readU64().toNumber()*1000/frequency.readU64().toNumber();}
function check(value,message){if(!value)throw Error(message);}
function fbits(pointer){return pointer.readU32();}
function productBits(value,factor){const scratch=Memory.alloc(4);scratch.writeFloat(Math.fround(Math.fround(value)*factor));return scratch.readU32();}
const invoke=new NativeFunction(fixture.ruby_context_init_fixture,'int',['pointer','int','int']);
const run=new NativeFunction(driver.run,'uint64',['pointer','uint']);
const runMeasure=new NativeFunction(driver.run_measure,'uint64',['pointer','uint']);
const runBase=new NativeFunction(driver.run_base,'uint64',['pointer','uint']);
const errors=[],contexts=[];
const callbacks={
 onEnter(args){
   check(this.returnAddress&&!this.returnAddress.isNull(),'slow listener missing returnAddress');
   check(this.context.r15&&this.context.rbx&&this.context.rbp,'slow listener context incomplete');
   this.target=args[0];this.before=[args[1].toInt32(),args[2].toInt32()];this.marker=String(this.returnAddress);contexts.push(this);
   args[1]=ptr(this.before[0]+7);args[2]=ptr(this.before[1]+11);
 },
 onLeave(value){
   check(this.target&&this.marker,'slow listener lost this object');
   const target=this.target,sx=target.add(0x158).readFloat(),sy=target.add(0x15c).readFloat();
   target.add(0x158).writeFloat(Math.fround(sx*0.375));target.add(0x15c).writeFloat(Math.fround(sy*0.375));
   value.replace(ptr(value.toInt32()+1000));
 }
};
const addresses={measurement:fixture.measurement_return,baseMeasurement:fixture.base_measurement_return};
function makeMeasure(errorSink=errors,points=addresses){return createNativeMeasure(callbacks,points,error=>errorSink.push(String(error)));}
function labelAndParser(){const label=Memory.alloc(0x500),parser=Memory.alloc(0x300),owned=Memory.allocUtf8String('owned');label.add(0x318).writePointer(owned);parser.add(0x1ab).writeU8(1);return {label,parser,owned};}
function target(){const p=Memory.alloc(0x200);p.writeFloat(13.25);p.add(0x158).writeFloat(1.234567);p.add(0x15c).writeFloat(7.654321);return p;}
function resetTarget(p){p.writeFloat(13.25);p.add(0x158).writeFloat(1.234567);p.add(0x15c).writeFloat(7.654321);}
const COUNT=12000,EXPECTED=1536;
let active=null;function detach(){if(active){active.detach();active=null;}Interceptor.flush();}
function attachNative(measure){active=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:measure.onEnter,onLeave:measure.onLeave});Interceptor.flush();}
function attachJs(){let enters=0,leaves=0,scopes=new Map();active=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter(args){this.target=args[0];this.key=String(++enters);this.returnAddress=String(this.returnAddress);scopes.set(this.key,this);args[1]=ptr(args[1].toInt32()+7);args[2]=ptr(args[2].toInt32()+11);},onLeave(value){const self=scopes.get(this.key);check(self===this,'direct JS this mismatch');scopes.delete(this.key);leaves++;const sx=this.target.add(0x158).readFloat(),sy=this.target.add(0x15c).readFloat();this.target.add(0x158).writeFloat(Math.fround(sx*.375));this.target.add(0x15c).writeFloat(Math.fround(sy*.375));value.replace(ptr(value.toInt32()+1000));}});Interceptor.flush();return {get enters(){return enters;},get leaves(){return leaves;},scopes};}
function bench(p){const start=now(),sum=run(p,COUNT).toNumber(),elapsed=now()-start;check(sum===COUNT*EXPECTED,'bench result '+sum);return elapsed;}
function tokenOK(token){return token.toString()!=='0';}
rpc.exports={run(){
 const report={prototype:'native-measure-c-gum-scope-v1',host:'self-created-hidden-python',game_attached:false,game_started:false,calls:COUNT,test_abi:'fixture ruby_context_init only; real Gum capture/prepare/measure listener chain uses a controlled driver and does not claim the game ABI'};
 const measure=makeMeasure(),first=labelAndParser(),second=labelAndParser();
 const one=measure.push(11,first.label,first.owned,.375);check(tokenOK(one),'first push');
 check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===1,'measure fast predicate');
 check(measure.evaluate(11,addresses.baseMeasurement,first.label,first.parser,true)===2,'base fast predicate');
 const nested=measure.push(11,first.label,first.owned,.5);check(tokenOK(nested),'nested push');check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===1,'nested scope');check(measure.pop(11,nested),'nested pop');
 const other=measure.push(22,second.label,second.owned,.25);check(tokenOK(other),'second thread push');check(measure.evaluate(22,addresses.measurement,second.label,second.parser,true)===1,'second thread isolated');check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===1,'first thread survived second');
 first.label.add(0x318).writePointer(Memory.allocUtf8String('changed'));check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===0,'owned pointer mutation must slow');first.label.add(0x318).writePointer(first.owned);first.parser.add(0x1ab).writeU8(0);check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===0,'non-measuring parser must slow');first.parser.add(0x1ab).writeU8(1);check(measure.evaluate(11,fixture.ruby_context_init_fixture,first.label,first.parser,true)===0,'wrong caller must slow');
 const fastTarget=target();check(measure.apply(fastTarget,.375),'fast apply');check(fbits(fastTarget.add(0x158))===productBits(1.234567,.375)&&fbits(fastTarget.add(0x15c))===productBits(7.654321,.375),'fast float bits');
 try { check(measure.evaluate(11,addresses.measurement,first.label,first.parser,true)===1,'finally scope active'); } finally { check(measure.pop(22,other),'second pop');check(measure.pop(11,one),'first pop'); }
 const jsTarget=target(),js=attachJs();const jsOne=invoke(jsTarget,2,3);check(jsOne===EXPECTED,'direct JS result');check(fbits(jsTarget.add(0x158))===productBits(1.234567,.375)&&fbits(jsTarget.add(0x15c))===productBits(7.654321,.375),'direct JS float bits');resetTarget(jsTarget);const jsMs=bench(jsTarget);check(js.enters===COUNT+1&&js.leaves===COUNT+1&&js.scopes.size===0,'direct JS scope cleanup');detach();
 const slowTarget=target();attachNative(measure);const slowOne=invoke(slowTarget,2,3);check(slowOne===EXPECTED,'native slow result');check(fbits(slowTarget.add(0x158))===productBits(1.234567,.375)&&fbits(slowTarget.add(0x15c))===productBits(7.654321,.375),'slow bridge float bits');resetTarget(slowTarget);const slowMs=bench(slowTarget);detach();const status=measure.status();check(status.slow===COUNT+1&&status.bridgeScopes===0,'native slow bridge cleanup');
 const captureHook=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:capture.capture_on_enter});const captureTarget=target();capturedCaller.writePointer(ptr(0));runMeasure(captureTarget,1);const measuredCaller=capturedCaller.readPointer();capturedCaller.writePointer(ptr(0));runBase(captureTarget,1);const baseCaller=capturedCaller.readPointer();captureHook.detach();Interceptor.flush();check(!measuredCaller.isNull()&&!baseCaller.isNull()&&!measuredCaller.equals(baseCaller),'capture real driver caller returns');
 const integratedErrors=[],integrated=makeMeasure(integratedErrors,{measurement:measuredCaller,baseMeasurement:baseCaller}),integratedScope=labelAndParser(),integratedTarget=target(),thread=Process.getCurrentThreadId();prepareLabel.writePointer(integratedScope.label);prepareParser.writePointer(integratedScope.parser);prepareRestored.writeU64(0);const integratedToken=integrated.push(thread,integratedScope.label,integratedScope.owned,.375);check(tokenOK(integratedToken),'integrated scope push');const prepareHook=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:prepare.prepare_on_enter,onLeave:prepare.prepare_on_leave}),integratedHook=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:integrated.onEnter,onLeave:integrated.onLeave});Interceptor.flush();check(runMeasure(integratedTarget,1).toNumber()===132,'integrated fast return');let integratedStatus=integrated.status();check(integratedStatus.fastMeasure===1&&integratedStatus.slow===0,'integrated fast measure path');check(fbits(integratedTarget.add(0x158))===productBits(1.234567,.375)&&fbits(integratedTarget.add(0x15c))===productBits(7.654321,.375),'integrated fast float bits');check(runBase(integratedTarget,1).toNumber()===132,'integrated base return');integratedStatus=integrated.status();check(integratedStatus.fastBase===1&&integratedStatus.slow===0,'integrated fast base path');check(fbits(integratedTarget.add(0x158))===productBits(1.234567,1)&&fbits(integratedTarget.add(0x15c))===productBits(7.654321,1),'integrated base must not scale');check(prepareRestored.readU64().toNumber()===2,'prepare listener did not restore register context');integratedHook.detach();prepareHook.detach();Interceptor.flush();check(integrated.pop(thread,integratedToken),'integrated scope finally pop');integratedStatus=integrated.status();check(integratedStatus.pops===1,'integrated scope cleanup');check(integratedErrors.length===0,'integrated errors '+integratedErrors);
 const guardToken=integrated.push(thread,integratedScope.label,integratedScope.owned,.375),wrongScope=labelAndParser(),guardTarget=target();check(tokenOK(guardToken),'guard scope push');prepareLabel.writePointer(wrongScope.label);prepareParser.writePointer(integratedScope.parser);prepareRestored.writeU64(0);const guardPrepare=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:prepare.prepare_on_enter,onLeave:prepare.prepare_on_leave}),guardMeasure=Interceptor.attach(fixture.ruby_context_init_fixture,{onEnter:integrated.onEnter,onLeave:integrated.onLeave});Interceptor.flush();const guardContexts=contexts.length;check(runMeasure(guardTarget,1).toNumber()===EXPECTED,'wrong label slow callback return');check(fbits(guardTarget.add(0x158))===productBits(1.234567,.375)&&fbits(guardTarget.add(0x15c))===productBits(7.654321,.375),'wrong label slow callback floats');prepareLabel.writePointer(integratedScope.label);integratedScope.label.add(0x318).writePointer(Memory.allocUtf8String('changed owned'));check(runMeasure(guardTarget,1).toNumber()===EXPECTED,'changed owned slow callback return');check(fbits(guardTarget.add(0x158))===productBits(1.234567,.375)&&fbits(guardTarget.add(0x15c))===productBits(7.654321,.375),'changed owned slow callback floats');integratedScope.label.add(0x318).writePointer(integratedScope.owned);integratedScope.parser.add(0x1ab).writeU8(0);check(runMeasure(guardTarget,1).toNumber()===EXPECTED,'parser flag slow callback return');check(fbits(guardTarget.add(0x158))===productBits(1.234567,.375)&&fbits(guardTarget.add(0x15c))===productBits(7.654321,.375),'parser flag slow callback floats');integratedScope.parser.add(0x1ab).writeU8(1);let guardStatus=integrated.status();check(guardStatus.slow===3&&guardStatus.bridgeScopes===0&&contexts.length===guardContexts+3,'guard slow bridge cleanup');check(prepareRestored.readU64().toNumber()===3,'guard register restore');guardMeasure.detach();guardPrepare.detach();Interceptor.flush();check(integrated.pop(thread,guardToken),'guard scope finally pop');guardStatus=integrated.status();check(guardStatus.pops===2&&integratedErrors.length===0,'guard scope cleanup');
 const failedErrors=[],failed=makeMeasure(failedErrors),bad=target();bad.writeFloat(NaN);check(!failed.apply(bad,.375),'nonfinite fast target must fail');check(failed.status().disabled&&failed.status().applyFailures===1&&failedErrors.length===1,'fast failure must sticky disable');
 const mismatchErrors=[],mismatch=makeMeasure(mismatchErrors),mismatchScope=labelAndParser(),mismatchToken=mismatch.push(77,mismatchScope.label,mismatchScope.owned,.375);check(tokenOK(mismatchToken),'mismatch setup');check(!mismatch.pop(77,999),'mismatched pop must fail');check(mismatch.status().disabled&&mismatch.status().mismatches===1&&mismatchErrors.length===0,'mismatched pop fail closed');
 const overflowErrors=[],overflow=makeMeasure(overflowErrors),overflowScope=labelAndParser();for(let depth=0;depth<16;depth++)check(tokenOK(overflow.push(88,overflowScope.label,overflowScope.owned,.375)),'overflow depth '+depth);check(!tokenOK(overflow.push(88,overflowScope.label,overflowScope.owned,.375)),'scope overflow must reject');check(overflow.status().disabled&&overflow.status().overflows===1&&overflowErrors.length===0,'scope overflow fail closed');
 check(errors.length===0,errors.join('; '));
 report.measurements={direct_js_ms:jsMs,c_listener_slow_bridge_ms:slowMs,slow_relative_to_js:slowMs/jsMs,slow_minus_js_ms:slowMs-jsMs};
 report.validation={fast_status:status,fast_predicate:{measurement:1,base:2,owned_pointer_change:0,measuring_false:0,wrong_caller:0},float_bits:{x:productBits(1.234567,.375),y:productBits(7.654321,.375)},args_and_return:EXPECTED,direct_js:{enters:js.enters,leaves:js.leaves},slow_bridge:{slow:status.slow,scopes:status.bridgeScopes},integrated_fast:{measured_caller:String(measuredCaller),base_caller:String(baseCaller),status:integratedStatus,prepare_restores:2},integrated_guards:{wrong_label:'slow legacy callback',changed_owned_pointer:'slow legacy callback',parser_measuring_flag:false,status:guardStatus,prepare_restores:3},nested_and_thread_scope:'controlled thread IDs 11 and 22 plus nested stack',fail_closed:{nonfinite:true,mismatched_pop:true,scope_overflow:true}};
 report.production_boundary='Offline mechanism fixture only. Root integration decides which verified MessageLog measurement scopes call push/pop; this module never identifies or invokes a game ABI itself.';report.all_passed=true;return report;
}};
"""
    )


def main() -> None:
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(script_source(), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        assert report["all_passed"]
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
