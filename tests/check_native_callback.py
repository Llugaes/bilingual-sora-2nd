"""Check callback ABI and bounded native heap in an owned hidden V8 host."""

import json
import subprocess
import sys
import time

import frida


def check():
    host = subprocess.Popen(
        [sys.executable, "-c", "import os,sys;print(os.getpid(),flush=True);sys.stdin.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    pid = int(host.stdout.readline())
    try:
        session = frida.attach(pid)
        script = session.create_script(
            r"""
let calls=0;
const pointer=new NativeCallback(value=>{calls++;return value;},'pointer',['pointer']);
const serial=new NativeCallback((p,n)=>n,'uint64',['pointer','uint64']);
const factor=new NativeCallback((p,n)=>n*2,'double',['pointer','double']);
const integer=new NativeCallback(n=>n-1,'int',['int']);
const finish=new NativeCallback((p,n)=>{calls++;},'void',['pointer','uint64']);
const driver=new CModule(`
#include <stdint.h>
extern void *pointer(void *);
extern uint64_t serial(void *, uint64_t);
extern double factor(void *, double);
extern int integer(int);
extern void finish(void *, uint64_t);
int abi(void) {
    void *p=(void *)(uintptr_t)0x12345678;
    if(pointer(p)!=p)return 1;
    if(serial(p,0xf123456789abcdefULL)!=0xf123456789abcdefULL)return 2;
    if(factor(p,0.375)!=0.75)return 3;
    if(integer(-31)!=-32)return 4;
    finish(p,42);return 0;
}
int run(unsigned int n) {
    for(unsigned int i=0;i<n;i++)if(pointer((void *)(uintptr_t)i)!=(void *)(uintptr_t)i)return 1;
    return 0;
}`,{pointer,serial,factor,integer,finish});
const abi=new NativeFunction(driver.abi,'int',[]);
const run=new NativeFunction(driver.run,'int',['uint']);
rpc.exports={
  abi(){return {result:abi(),calls};},
  run(n){const before=calls;if(run(n)!==0||calls-before!==n)throw Error('callback result or call count changed');return Frida.heapSize;},
  collect(){gc();return Frida.heapSize;},
  status(){return Frida.heapSize;}
};
""",
            runtime="v8",
        )
        script.on("message", lambda message, _: print(json.dumps(message), flush=True))
        script.load()
        abi = script.exports_sync.abi()
        assert abi == {"result": 0, "calls": 2}, abi
        samples = []
        for _ in range(4):
            before_gc = script.exports_sync.run(100000)
            # Diagnostic only: proves unreachable native allocations are
            # reclaimed. Production never invokes GC or a memory timer.
            script.exports_sync.collect()
            time.sleep(0.05)
            samples.append({"before_gc": before_gc, "after_gc": script.exports_sync.status()})
        growth = samples[-1]["after_gc"] - samples[0]["after_gc"]
        result = {
            "frida": frida.__version__,
            "calls": 400000,
            "samples": samples,
            "retained_growth": growth,
            "game_attached": False,
        }
        print(json.dumps(result), flush=True)
        assert growth < 512 * 1024, f"Native callback heap grows after collection: {growth} bytes"
        session.detach()
    finally:
        host.stdin.close()
        host.wait(timeout=10)
        host.stdout.close()


if __name__ == "__main__":
    check()
