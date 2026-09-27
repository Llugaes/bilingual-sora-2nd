"""Exercise the production parser listener in a self-created Frida host only."""

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "sora_bilingual/game/scripts/native_parser.js").read_text("utf-8")


def script_source():
    return (
        SOURCE
        + r"""
const contexts=new Map(),errors=[];
const listener=createNativeParser(contexts,error=>errors.push(String(error)));
const marker=new CModule('int middle(void *p) { return p!=0; }');
const fixture=new CModule(`
extern int middle(void *);
int size_end(unsigned char *parser, float scale) {
    *(float *)(parser+0x158)=scale;
    *(float *)(parser+0x15c)=scale;
    return 1;
}
int parse(unsigned char *label, unsigned char *parser, int event) {
    if (event) middle(parser);
    return parser[0x1a5]+123;
}
` ,{middle:marker.middle});
const driver=new CModule(`
#include <stdint.h>
extern int parse(unsigned char *, unsigned char *, int);
uint64_t run(unsigned char *label, unsigned char *parser, int count) {
    uint64_t sum=0; int i;
    for (i=0;i<count;i++) sum+=parse(label,parser,0);
    return sum;
}
uint32_t thread_run(void **arg) {
    run(arg[0],arg[1],4000); return 0;
}
`,{parse:fixture.parse});
const parse=new NativeFunction(fixture.parse,'int',['pointer','pointer','int']);
const sizeEnd=new NativeFunction(fixture.size_end,'int',['pointer','float']);
const run=new NativeFunction(driver.run,'uint64',['pointer','pointer','int']);
const label=Memory.alloc(0x800),outer=label.add(0x400),inner=Memory.alloc(0x300);
let inBody=null;
Interceptor.attach(marker.middle,{onEnter(args){if(inBody)inBody(args[0]);}});
let hook=null;
function useNative(){hook=Interceptor.attach(fixture.parse,{onEnter:listener.onEnter,onLeave:listener.onLeave});Interceptor.flush();}
function detach(){if(hook){hook.detach();hook=null;}Interceptor.flush();}
function check(value,message){if(!value)throw Error(message);}
function productBits(value,factor){const scratch=Memory.alloc(4);scratch.writeFloat(Math.fround(Math.fround(value)*factor));return scratch.readU32();}
const kernel=Process.getModuleByName('kernel32.dll'),tick=Memory.alloc(8),frequency=Memory.alloc(8);
const qpc=new NativeFunction(kernel.getExportByName('QueryPerformanceCounter'),'int',['pointer']);
new NativeFunction(kernel.getExportByName('QueryPerformanceFrequency'),'int',['pointer'])(frequency);
function now(){qpc(tick);return tick.readU64().toNumber()*1000/frequency.readU64().toNumber();}
function bench(){const start=now();const sum=run(label,outer,12000).toNumber();check(sum===1476000,'native return value changed');return now()-start;}
rpc.exports={run(){
    const baseline=bench();
    let jsCalls=0;
    const jsTiming={count:0,totalMs:0};
    hook=Interceptor.attach(fixture.parse,{
        onEnter(args){
            jsCalls++;this.key=String(args[1]);this.aux=contexts.has(this.key);
            if(args[1].equals(args[0].add(0x400)))this.started=Date.now();
            if(this.aux)args[1].add(0x1a5).writeU8(contexts.get(this.key).placement?0:1);
        },
        onLeave(){if(this.aux)contexts.delete(this.key);if(this.started!==undefined){jsTiming.count++;jsTiming.totalMs+=Date.now()-this.started;}}
    });
    Interceptor.flush();const js=bench();detach();
    check(jsCalls===12000&&jsTiming.count===12000,'JS baseline did not exercise every parser call');
    useNative();const native=bench();
    let status=listener.status();
    check(status.bridgeCalls===0&&status.count===12000,'ordinary parse must not enter JS');
    const before=status.count;parse(label,inner,0);status=listener.status();
    check(status.count===before&&status.allCalls===12001,'inner parser counted as outer');
    for(const placement of [false,true]) {
        listener.set(inner,{factor:.45,placement});
        inBody=p=>{
            const parent=contexts.get(String(p));
            check(parent?.factor===.45&&parent.placement===placement,'parent inheritance unavailable during parse');
        };
        const result=parse(label,inner,1);
        check(result===(placement?123:124),'annotation permission changed');
        check(!contexts.has(String(inner))&&listener.status().active===0,'auxiliary context not cleaned');
    }
    listener.set(inner,{factor:.5,placement:false});
    inBody=p=>listener.set(p,{factor:.8,placement:true});
    parse(label,inner,1);
    check(contexts.get(String(inner))?.factor===.8,'old invocation deleted new generation');
    check(listener.status().active===1,'new native generation lost');
    inBody=null;parse(label,inner,0);
    check(!contexts.has(String(inner))&&listener.status().active===0,'replacement generation leaked');
    for (const measurementOnly of [false,true]) {
        listener.set(inner,{factor:.3,placement:false,allowReadings:true,measureOnly:measurementOnly});
        // The native caller overwrites 1ab after init; the permission must be
        // applied at parser entry, independently of placement mode.
        inner.add(0x1a5).writeU8(1);inner.add(0x1a9).writeU8(1);inner.add(0x1ab).writeU8(0);
        check(parse(label,inner,0)===123,'owned measurement reading permission was lost');
        check(inner.add(0x1a9).readU8()===(measurementOnly?0:1),'measurement changed the wrong output gate');
        check(inner.add(0x1ab).readU8()===(measurementOnly?1:0),'measurement flag was overwritten');
        check(!contexts.has(String(inner))&&listener.status().active===0,'reading measurement scope leaked');
    }
    // The verified S/s command tail resets both fields to an absolute label
    // size. Restore the saved native-ruby factor inside C before glyph
    // emission; normal, emphasized and nested contexts stay independent.
    const sizeScratch=Memory.alloc(0x300),independentSize=Memory.alloc(0x300),unownedSize=Memory.alloc(0x300);
    listener.trackScale(sizeScratch,.45);
    sizeScratch.add(0x158).writeFloat(.45);sizeScratch.add(0x15c).writeFloat(.45);
    check(Math.fround(sizeScratch.add(0x15c).readFloat())===Math.fround(.45),'normal ruby scale changed');
    sizeEnd(sizeScratch,1.5);
    check(listener.applySize(sizeScratch),'S5 factor was not restored');
    check(sizeScratch.add(0x158).readU32()===productBits(1.5,.45)&&sizeScratch.add(0x15c).readU32()===productBits(1.5,.45),'S5 ratio differs from normal ruby');
    sizeEnd(sizeScratch,.8);check(listener.applySize(sizeScratch),'sN factor was not restored');
    check(sizeScratch.add(0x158).readU32()===productBits(.8,.45)&&sizeScratch.add(0x15c).readU32()===productBits(.8,.45),'sN ratio differs from normal ruby');
    sizeEnd(unownedSize,1.5);check(!listener.applySize(unownedSize),'unowned primary size was intercepted');
    check(unownedSize.add(0x15c).readU32()===productBits(1.5,1),'unowned primary size changed');
    // A separately owned ruby context keeps an independent S/s factor. This
    // is deliberately not a C/B style model: verified C/c tags share a
    // parser exit and are exercised by check_native_size_hook.py.
    listener.trackScale(independentSize,.3);sizeEnd(independentSize,1.5);check(listener.applySize(independentSize),'independent ruby factor missing');
    check(independentSize.add(0x15c).readU32()===productBits(1.5,.3),'independent ruby factor leaked');
    // Entering the parser retires the test-only scale records exactly like a
    // production parse, so no pointer-derived state survives its invocation.
    parse(label,sizeScratch,0);parse(label,independentSize,0);
    check(listener.status().active===0,'size records leaked after parser return');
    // Independent native threads exercise lock and invocation-local timing.
    const startThread=new NativeFunction(kernel.getExportByName('CreateThread'),'pointer',
        ['pointer','uint64','pointer','pointer','uint','pointer']);
    const wait=new NativeFunction(kernel.getExportByName('WaitForMultipleObjects'),'uint',
        ['uint','pointer','int','uint']);
    const close=new NativeFunction(kernel.getExportByName('CloseHandle'),'int',['pointer']);
    const handles=Memory.alloc(16),threadData=[];
    const threadBefore=listener.status();
    for(let i=0;i<2;i++) {
        const l=Memory.alloc(0x800),data=Memory.alloc(16);
        data.writePointer(l);data.add(8).writePointer(l.add(0x400));threadData.push({l,data});
        const h=startThread(ptr(0),0,driver.thread_run,data,0,ptr(0));
        check(!h.isNull(),'thread creation failed');handles.add(i*8).writePointer(h);
    }
    check(wait(2,handles,1,10000)===0,'native threads failed');
    for(let i=0;i<2;i++)close(handles.add(i*8).readPointer());
    check(listener.status().count-threadBefore.count===8000,'concurrent counters lost updates');
    // A full registry falls back to the complete JS map, never drops text.
    const payload=[];
    for(let i=0;i<1025;i++) {
        const p=Memory.alloc(0x300);payload.push(p);listener.set(p,{factor:.45,placement:!!(i%2)});
    }
    check(listener.status().fallback&&listener.status().overflows===1,'registry did not fall back on overflow');
    sizeEnd(payload[0],1.5);check(listener.applySize(payload[0]),'overflow lost an existing size record');
    check(payload[0].add(0x15c).readU32()===productBits(1.5,.45),'overflow changed emphasized ruby ratio');
    // payload[1024] was never admitted to a C slot. Its S5 factor must come
    // from the complete JS context map after the registry has overflowed.
    sizeEnd(payload[1024],1.5);check(listener.applySize(payload[1024]),'overflow lost a new auxiliary S5 factor');
    check(payload[1024].add(0x15c).readU32()===productBits(1.5,.45),'new overflow auxiliary S5 ratio changed');
    // A newly-created simple ruby has no auxiliary JS row at all. It must
    // register only on the overflow bridge and be retired by its parser leave.
    const overflowSimple=Memory.alloc(0x300);listener.trackScale(overflowSimple,.4);sizeEnd(overflowSimple,1.5);
    check(listener.applySize(overflowSimple)&&overflowSimple.add(0x15c).readU32()===productBits(1.5,.4),'new overflow simple S5 factor lost');
    check(parse(label,overflowSimple,0)===123,'overflow simple parser permission changed');
    check(!listener.applySize(overflowSimple),'overflow simple factor leaked after parser leave');
    const primaryAfterOverflow=Memory.alloc(0x300);sizeEnd(primaryAfterOverflow,1.5);
    check(!listener.applySize(primaryAfterOverflow)&&primaryAfterOverflow.add(0x15c).readU32()===productBits(1.5,1),'overflow touched unowned primary');
    // The old fallback leave must retire its matching native slot without
    // deleting a reentrant JS generation at the same parser address.
    inBody=p=>{if(p.equals(payload[0]))listener.set(p,{factor:.3,placement:true});};
    check(parse(label,payload[0],1)===124,'overflow reentry changed old parser permission');
    check(contexts.get(String(payload[0]))?.factor===.3,'overflow leave removed replacement generation');
    sizeEnd(payload[0],1.5);check(listener.applySize(payload[0])&&payload[0].add(0x15c).readU32()===productBits(1.5,.3),'overflow reentry did not use replacement factor');
    inBody=null;check(parse(label,payload[0],0)===123,'overflow replacement permission changed');
    for(let i=1;i<payload.length;i++) {
        check(parse(label,payload[i],0)===(i%2?123:124),'overflow changed native parser permission');
    }
    check(contexts.size===0,'overflow cleanup lost JS entries');
    check(listener.status().active===0,'overflow cleanup leaked native entries');
    check(errors.length===0,errors.join('; '));
    const report={all_passed:true,game_attached:false,host:'self-created-hidden-python',
        original_ms:baseline,js_listener_ms:js,native_listener_ms:native,calls:12000,
        native_relative_to_js:native/js,ordinary_js_callbacks:0,
        cases:['outer/nested timing','native return and permission','parent inherits until return',
            'owned reading measurement permission with output disabled',
            'same pointer generation replacement','S5/sN ruby-scale restoration and unowned isolation',
            'two native threads','1025-entry overflow fallback with size record and same-address reentry'],
        final_status:listener.status()};
    detach();return report;
}};
"""
    )


def main():
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        agent = session.create_script(script_source(), runtime="v8")
        agent.on("message", lambda message, _: print(json.dumps(message), flush=True))
        agent.load()
        report = agent.exports_sync.run()
        assert report["all_passed"]
        destination = ROOT / "generated/diagnostic-089-native-parser.json"
        destination.write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
