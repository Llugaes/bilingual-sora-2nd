"""Bounded, native-only timing of the real Interceptor callback boundary.

The test owns a hidden host. It does not attach to or start a game.
"""

from pathlib import Path
import json
import subprocess
import sys

import frida
from check_native_refresh import script_source

ROOT = Path(__file__).resolve().parents[1]


def source():
    return (
        (ROOT / "sora_bilingual/game/scripts/native_timing.js").read_text("utf-8")
        + r"""
const kernel=Process.getModuleByName('kernel32.dll');
const sleep=new NativeFunction(kernel.getExportByName('Sleep'),'void',['uint']);
const native=new CModule(`
extern void Sleep(unsigned int);
int setter(void *p,int ms) { if(ms)Sleep(ms);return 17; }
int ordinary(void *p,int ms) { return 23; }
int update(void *p,int depth) { if(depth) return update(p,depth-1);return 23; }
extern int QueryPerformanceCounter(long long *);
extern int QueryPerformanceFrequency(long long *);
double loop(int n,int which) {
    long long begin,end,freq;QueryPerformanceFrequency(&freq);QueryPerformanceCounter(&begin);
    for(int i=0;i<n;i++)if(which)ordinary((void*)0x1234,0);else setter((void*)0x1234,0);
    QueryPerformanceCounter(&end);return (end-begin)*1000.0/freq;
}
`,{Sleep:kernel.getExportByName('Sleep'),
QueryPerformanceCounter:kernel.getExportByName('QueryPerformanceCounter'),
QueryPerformanceFrequency:kernel.getExportByName('QueryPerformanceFrequency')});
const timing=createNativeLabelTiming({setter:native.setter,update:native.update});
let enter=0,leave=0,enters=0,leaves=0,insideMs=0;
timing.attach(native.setter,{onEnter(args){
    const start=Date.now();this.p=args[0];enters++;
    if(enter)sleep(enter);
    insideMs=Date.now()-start;
},onLeave(ret){
    if(!this.p.equals(ptr(0x1234)))throw Error('invocation state changed');
    leaves++;if(leave)sleep(leave);ret.replace(19);
}});
const call=new NativeFunction(native.setter,'int',['pointer','int']);
const update=new NativeFunction(native.update,'int',['pointer','int']);
const loop=new NativeFunction(native.loop,'double',['int','int']);
const ordinary=Interceptor.attach(native.ordinary,{onEnter(args){this.p=args[0];},onLeave(){
    if(!this.p.equals(ptr(0x1234)))throw Error('ordinary invocation changed');
}});
timing.attach(native.update,{onEnter(args){this.p=args[0];},onLeave(){check(this.p.equals(ptr(0x1234)),'nested invocation changed');}});
const worker=new CModule(`
extern int target(void *,int);extern void Sleep(unsigned int);
int run(volatile int *done) { done[2]=1;done[1]=target((void*)0x1234,0);done[0]=1;return 0; }
`,{target:native.setter,Sleep:kernel.getExportByName('Sleep')});
const startThread=new NativeFunction(kernel.getExportByName('CreateThread'),'pointer',
    ['pointer','uint64','pointer','pointer','uint','pointer']);
const close=new NativeFunction(kernel.getExportByName('CloseHandle'),'int',['pointer']);
function check(value,message){if(!value)throw Error(message);}
rpc.exports.run=()=>{
    enter=40;leave=60;
    check(call(ptr(0x1234),80)===19,'return replacement lost');
    let report=timing.status(),event=report.recent.at(-1);
    check(report.dropped===0,'listener order or stack invalid');
    check(event.enterMs>=30&&event.bodyMs>=70&&event.leaveMs>=50,'callback phases not enclosed');
    check(event.at<=Date.now()&&Date.now()-event.at<10000,'event timestamp is not wall time');
    const first=event;
    enter=0;leave=0;
    for(let i=0;i<40;i++)call(ptr(0x1234),9);
    report=timing.status();
    check(report.recent.length===32&&report.sequence===41,'event storage is not bounded');
    check(report.recent[0].sequence===10,'ring retained oldest entries');
    check(enters===41&&leaves===41,'extra or lost JS callback');
    check(report.stages.setter.enter.count===41,'lost invocation');
    // Same listener body, with/without the two native observers. Report the
    // cost instead of pretending a host benchmark is a game-frame result.
    const samples=Array.from({length:5},()=>({ordinaryMs:loop(10000,1),timedMs:loop(10000,0)}));
    check(update(ptr(0x1234),5)===23,'recursive native body changed');
    check(timing.status().stages.update.enter.count===6,'recursive scopes lost: '+JSON.stringify(timing.status().stages.update));
    check(timing.status().dropped===0,'recursive scopes mismatched');
    return {first,sequence:report.sequence,retained:report.recent.length,samples,nested:6};
};
rpc.exports.blocked=()=>{
    const done=Memory.alloc(16);done.writeByteArray(new Uint8Array(16));
    const thread=startThread(ptr(0),0,worker.run,done,0,ptr(0));
    check(!thread.isNull(),'thread creation failed');
    // Deliberately hold the script lock in this owned test host while a
    // different native thread waits to enter its SetText callback.
    const deadline=Date.now()+5000;
    while(!done.add(8).readS32()&&Date.now()<deadline){}
    check(done.add(8).readS32()===1,'worker did not start');
    const until=Date.now()+200;while(Date.now()<until){}
    return new Promise(resolve=>{
        const timer=setInterval(()=>{
            if(!done.readS32())return;
            clearInterval(timer);close(thread);
            const report=timing.status(),event=report.recent.at(-1);
            check(done.add(4).readS32()===19,'thread return changed');
            check(event.enterMs>=100&&insideMs<30,'script lock wait not observed outside JS');
            check(report.dropped===0,'concurrent scopes mismatched');
            resolve({event,oldInsideMs:insideMs});
        },10);
    });
};
"""
    )


def main():
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        agent = session.create_script(source(), runtime="v8")
        agent.load()
        report = {"contracts": agent.exports_sync.run(), "lock_wait": agent.exports_sync.blocked()}
        refresh = session.create_script(script_source(timed=True), runtime="v8")
        refresh.load()
        production = refresh.exports_sync.run()
        assert production["all_passed"], production["contract_failures"]
        report["production_update_contracts"] = len(production["cases"])
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        if session:
            session.detach()
        host.communicate(timeout=5)


if __name__ == "__main__":
    main()
