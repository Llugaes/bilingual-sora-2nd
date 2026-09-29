"""Replay ordinary parser bursts through the production C/Gum listener, outside the game."""

import json
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]


def check():
    source = (ROOT / "sora_bilingual/game/scripts/native_measure.js").read_text("utf-8")
    source += r"""
const target=new CModule('int initialize(void *p,int x,int y){return x*31+y*17+19;}');
const driver=new CModule(`
    extern int initialize(void *,int,int);
    int ordinary(void *p,int n){int sum=0;for(int i=0;i<n;i++)sum+=initialize(p,2,3);return sum;}
    int reading(void *p){return initialize(p,2,3);}
    int base(void *p){return initialize(p,2,3);}
    int placement(void *p){return initialize(p,2,3);}
`,{initialize:target.initialize});
const ordinary=new NativeFunction(driver.ordinary,'int',['pointer','int']);
const callbacks=Object.fromEntries(['reading','base','placement'].map(k=>[k,new NativeFunction(driver[k],'int',['pointer'])]));
const data=Memory.alloc(0x800),callers={};let seen;
const capture=Interceptor.attach(target.initialize,{onEnter(){seen=this.returnAddress;}});
Interceptor.flush();for(const [name,call] of Object.entries(callbacks)){call(data);callers[name]=seen;}capture.detach();Interceptor.flush();
const addresses={measurement:callers.reading,baseMeasurement:callers.base,placement:callers.placement};
const kernel=Process.getModuleByName('kernel32.dll'),value=Memory.alloc(8),frequency=Memory.alloc(8);
const qpc=new NativeFunction(kernel.getExportByName('QueryPerformanceCounter'),'int',['pointer']);
new NativeFunction(kernel.getExportByName('QueryPerformanceFrequency'),'int',['pointer'])(frequency);
const hz=frequency.readU64().toNumber(),now=()=>{qpc(value);return value.readU64().toNumber()*1000/hz;};
let enters=0,leaves=0;const errors=[];
// Same entry contract as rubyContextCallbacks: only three verified returns
// do annotation work. Ordinary init calls return before touching any label.
const bridge={onEnter(){enters++;this.owned=Object.values(addresses).some(p=>p.equals(this.returnAddress));},onLeave(){leaves++;}};
rpc.exports.check=()=>{
    const count=12000,bareStart=now(),bareResult=ordinary(data,count),bareMs=now()-bareStart;
    const measure=createNativeMeasure(bridge,addresses,e=>errors.push(String(e)));
    const hook=Interceptor.attach(target.initialize,{onEnter:measure.onEnter,onLeave:measure.onLeave});Interceptor.flush();
    const start=now(),result=ordinary(data,count),milliseconds=now()-start;
    const ordinaryBridges=enters,ordinaryLeaves=leaves;
    for(const call of Object.values(callbacks))if(call(data)!==132)throw Error('annotation native result changed');
    hook.detach();Interceptor.flush();
    return {count,bareMs,milliseconds,ordinaryBridges,ordinaryLeaves,annotationBridges:enters-ordinaryBridges,
        nativeResultsUnchanged:result===bareResult&&result===count*132,errors,status:measure.status(),game_attached:false};
};
"""
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys;sys.stdin.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(source, runtime="v8")
        script.load()
        report = script.exports_sync.check()
        print(json.dumps(report, indent=2), flush=True)
        assert report["ordinaryBridges"] == report["ordinaryLeaves"] == 0, (
            "ordinary parser entered JS bridge"
        )
        assert (
            report["annotationBridges"] == 3
            and report["nativeResultsUnchanged"]
            and not report["errors"]
        )
        return report
    finally:
        if session:
            session.detach()
        host.communicate(timeout=5)


if __name__ == "__main__":
    check()
