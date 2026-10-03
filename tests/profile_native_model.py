"""Natural allocation at native hook boundaries, in an owned hidden host only.

The fixture reproduces callback allocation/locking, not game rendering. It loads
all production resolvers and the complete model, never forces GC, and optionally
captures V8 CPU samples to attribute waits. Use the same model and duration for
before/after comparisons; an empty model is a separate control.
"""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import frida

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--seconds", type=int, default=90)
p.add_argument("--empty", action="store_true")
p.add_argument("--wire", type=Path)
p.add_argument("--profile", action="store_true")
p.add_argument("--max-wait-ms", type=float, default=100)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
if not args.empty and args.wire is None:
    p.error("--wire is required unless --empty")
out = args.output.resolve()
out.parent.mkdir(parents=True, exist_ok=True)
host = subprocess.Popen(
    [sys.executable, "-c", "import sys;sys.stdin.read()"],
    stdin=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS,
)
session = None
profile = None
try:
    session = frida.attach(host.pid)
    source = "\n".join(
        (ROOT / "sora_bilingual/game/scripts" / f"{name}.js").read_text("utf-8")
        for name in ("runtime_text", "runtime_identity", "runtime_paragraph", "native_timing")
    )
    source += """
let resident=null;
rpc.exports.load=model=>{resident={model,tr:new RuntimeText(model),scripts:new ScriptIdentities(model.script_identities),tables:new TableIdentities(model.table_identities),paragraphs:new RuntimeParagraphs(model,RuntimeText)};return true;};
"""
    source += (ROOT / "sora_bilingual/game/scripts/native_transport.js").read_text("utf-8")
    source += """
const kernel=Process.getModuleByName('kernel32.dll');
const native=new CModule(`
extern void Sleep(unsigned int);
int update(char *p){return p[0];}
unsigned int run(volatile int *state){
  char p[2048]={0};state[1]=1;
  while(!state[0]){for(int j=0;j<32;j++)update(p);Sleep(8);}
  state[1]=0;return 0;
}
`,{Sleep:kernel.getExportByName('Sleep')});
const timing=createNativeLabelTiming({setter:ptr(0),update:native.update});
const callbacks=new Map(),rewrites=new Map(),threads=new Set();let calls=0;
timing.attach(native.update,{onEnter(args){
 const p=args[0],thread=Process.getCurrentThreadId(),stack=rewrites.get(thread)||[];
 for(let i=stack.length-1;i>=0;i--)if(stack[i].pointer.equals(p))return;
 threads.add(thread);const key=String(p),previous=callbacks.get(key);
 this.lease=previous||{key,thread,depth:0};this.lease.depth++;callbacks.set(key,this.lease);
 const row={pointer:p,key,metadata:{size:p.add(0x304).readU32(),flags:p.add(0x2e8).readU32()}};
 if(row.metadata.size!==0)throw Error('fixture');calls++;
},onLeave(){const lease=this.lease;if(lease&&--lease.depth===0&&callbacks.get(lease.key)===lease)callbacks.delete(lease.key);}});
const createThread=new NativeFunction(kernel.getExportByName('CreateThread'),'pointer',['pointer','uint64','pointer','pointer','uint','pointer']);
const close=new NativeFunction(kernel.getExportByName('CloseHandle'),'int',['pointer']);
const control=Memory.alloc(16);control.writeByteArray(new Uint8Array(16));let thread=null;
rpc.exports.start=()=>{thread=createThread(ptr(0),0,native.run,control,0,ptr(0));return !thread.isNull();};
rpc.exports.stats=()=>({calls,timing:timing.status(),heap:Frida.heapSize});
rpc.exports.stop=()=>{control.writeS32(1);return true;};
rpc.exports.stopped=()=>control.add(4).readS32()===0;
rpc.exports.close=()=>{close(thread);thread=null;return true;};
Interceptor.flush();
"""
    agent = session.create_script(source, runtime="v8")
    agent.on(
        "message", lambda m, d: print("agent", m, flush=True) if m["type"] == "error" else None
    )
    agent.load()
    begin = time.perf_counter()
    if args.empty:
        agent.exports_sync.load({"pairs": {}, "plain_pairs": {}})
    else:
        agent.exports_sync.modelpackedfile(str(args.wire.resolve()), "annotation", True, 0.9, {})
    load_seconds = time.perf_counter() - begin
    print(
        json.dumps({"host_pid": host.pid, "load_seconds": load_seconds, "empty": args.empty}),
        flush=True,
    )
    profile_path = out.with_suffix(".cpuprofile")
    ready = Path(str(profile_path) + ".ready")
    ready.unlink(missing_ok=True)
    if args.profile:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        agent.enable_debugger(port)
        profile = subprocess.Popen(
            [
                "node",
                str(ROOT / "tests/profile_native_model_cdp.js"),
                str(port),
                str(profile_path),
                str(args.seconds + 2),
            ],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS,
        )
        deadline = time.monotonic() + 15
        while not ready.exists():
            if profile.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Profiler did not start")
            time.sleep(0.1)
    assert agent.exports_sync.start()
    samples = []
    events = []
    began = time.monotonic()
    sequence = 0
    while time.monotonic() - began < args.seconds:
        time.sleep(1)
        s = agent.exports_sync.stats()
        s["at"] = time.time()
        samples.append(s)
        if s["timing"]["sequence"] > sequence:
            fresh = [e for e in s["timing"]["recent"] if e["sequence"] > sequence]
            events.extend(fresh)
            sequence = s["timing"]["sequence"]
            print(
                json.dumps({"seconds": round(time.monotonic() - began, 1), "events": fresh}),
                flush=True,
            )
    agent.exports_sync.stop()
    deadline = time.monotonic() + 10
    while not agent.exports_sync.stopped():
        if time.monotonic() > deadline:
            raise RuntimeError("Owned worker did not stop")
        time.sleep(0.05)
    agent.exports_sync.close()
    if profile:
        profile.wait(timeout=15)
        if profile.returncode:
            raise RuntimeError("Profiler failed")
    maximum = max((sum(e[k] for k in ("enterMs", "bodyMs", "leaveMs")) for e in events), default=0)
    report = {
        "empty": args.empty,
        "seconds": args.seconds,
        "load_seconds": load_seconds,
        "max_observed_ms": maximum,
        "samples": samples,
        "game_attached": False,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "calls": samples[-1]["calls"],
                "slow_calls": sequence,
                "max_observed_ms": maximum,
                "output": str(out),
            }
        ),
        flush=True,
    )
    if maximum >= args.max_wait_ms:
        raise SystemExit(1)
finally:
    if profile and profile.poll() is None:
        profile.terminate()
        profile.wait(timeout=5)
    if session:
        session.detach()
    try:
        host.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        host.kill()  # Only this Popen-owned hidden fixture, never a game process.
        host.communicate(timeout=5)
    Path(str(out.with_suffix(".cpuprofile")) + ".ready").unlink(missing_ok=True)
