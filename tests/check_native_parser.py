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
const run=new NativeFunction(driver.run,'uint64',['pointer','pointer','int']);
const label=Memory.alloc(0x800),outer=label.add(0x400),inner=Memory.alloc(0x300);
let inBody=null;
Interceptor.attach(marker.middle,{onEnter(args){if(inBody)inBody(args[0]);}});
let hook=null;
function useNative(){hook=Interceptor.attach(fixture.parse,{onEnter:listener.onEnter,onLeave:listener.onLeave});Interceptor.flush();}
function detach(){if(hook){hook.detach();hook=null;}Interceptor.flush();}
function check(value,message){if(!value)throw Error(message);}
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
        const p=Memory.alloc(0x300);payload.push(p);listener.set(p,{factor:.9,placement:!!(i%2)});
    }
    check(listener.status().fallback&&listener.status().overflows===1,'registry did not fall back on overflow');
    for(let i=0;i<payload.length;i++) {
        check(parse(label,payload[i],0)===(i%2?123:124),'overflow changed native parser permission');
    }
    check(contexts.size===0,'overflow cleanup lost JS entries');
    check(listener.status().active===0,'overflow cleanup leaked native entries');
    check(errors.length===0,errors.join('; '));
    const report={all_passed:true,game_attached:false,host:'self-created-hidden-python',
        original_ms:baseline,js_listener_ms:js,native_listener_ms:native,calls:12000,
        native_relative_to_js:native/js,ordinary_js_callbacks:0,
        cases:['outer/nested timing','native return and permission','parent inherits until return',
            'same pointer generation replacement','two native threads','1025-entry overflow fallback'],
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
