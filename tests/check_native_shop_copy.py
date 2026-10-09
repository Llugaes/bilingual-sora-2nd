"""Production post-copy callbacks in real Frida, attached only to a new hidden helper.

Executes bounded native printf/copy and actual Win64 RDI/ESI/R15D register
shapes. Node tests separately cover the complete production setter/Update.
This is not a game renderer or a game attachment.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import frida

ROOT = Path(__file__).resolve().parents[1]


def source(root=ROOT):
    agent = (root / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")
    start = agent.index("for(const [name,register] of [['shop_yes_copy_return'")
    hooks = agent[
        start : agent.index("labelHooks.attach(base.add(REPORT.native.update.rva)", start)
    ]
    runtime = (root / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf-8")
    fixture = r"""
const crt=Module.load('msvcrt.dll');
const native=new CModule(`
extern int snprintf(char *, unsigned long long, const char *, ...);
void format_copy(void *label, const char *format) {
  char temporary[256];
  snprintf(temporary,256,format);
  char *owned=*(char **)((char *)label+0x318);
  unsigned int n=0;while(temporary[n]&&n<255){owned[n]=temporary[n];n++;}owned[n]=0;
}
`,{snprintf:crt.getExportByName('_snprintf')});
const labels=new Map(),textKeys=new Map(),inputIdentityDiagnostics=new Map(),errors=[];
const base=ptr(0),REPORT={diagnostics:false,native:{}};
function activeRewrite(){return false;}
function isLabel(p){return p.readPointer().equals(ptr(0x1234));}
function readText(p){return p.add(0x318).readPointer().readUtf8String();}
function remember(p,text){const row={pointer:p,original:text,displayed:text,epoch:-1};labels.set(String(p),row);return row;}
function fail(e){errors.push(String(e));}
const functions=[],codeAllocations=[];
for(const [name,register] of [['shop_yes_copy_return','esi'],['shop_no_copy_return','r15d']]){
  const code=Memory.alloc(Process.pageSize);Memory.protect(code,Process.pageSize,'rwx');let boundary;
  codeAllocations.push(code);
  Memory.patchCode(code,Process.pageSize,p=>{
    const w=new X86Writer(p,{pc:code});
    w.putPushReg('rdi');w.putPushReg('rsi');w.putPushReg('r15');w.putSubRegImm('rsp',0x20);
    w.putMovRegReg('rdi','rcx');
    // MOV ESI,EDX / MOV R15D,EDX and zero the other hash register.
    // Gum's writer does not expose the extended 32-bit register aliases.
    w.putBytes(register==='esi'?[0x89,0xd6,0x45,0x31,0xff]:[0x41,0x89,0xd7,0x31,0xf6]);
    w.putMovRegReg('rdx','r8');w.putCallAddress(native.format_copy);
    boundary=code.add(w.offset);for(let i=0;i<16;i++)w.putNop();
    w.putAddRegImm('rsp',0x20);w.putPopReg('r15');w.putPopReg('rsi');w.putPopReg('rdi');w.putRet();w.flush();w.dispose();
  });
  REPORT.native[name]={rva:boundary};functions.push(new NativeFunction(code,'void',['pointer','uint','pointer']));
}
__HOOKS__
Interceptor.flush();
const label=Memory.alloc(0x700),owned=Memory.alloc(256);label.writePointer(ptr(0x1234));label.add(0x318).writePointer(owned);
textKeys.set(1,{key:'TXT_CUSTOMIZE',source:'Enhance'});
textKeys.set(2,{key:'TXT_CREATE',source:'Synthesize'});
textKeys.set(3,{key:'TXT_GENERATE',source:'Synthesize'});
textKeys.set(4,{key:'TXT_NO',source:'Cancel'});
textKeys.set(5,{key:'TXT_FORMAT',source:'%s'});
const keyed=Object.fromEntries([['TXT_CUSTOMIZE','Enhance',['强化','強化する']],
  ['TXT_CREATE','Synthesize',['制作','作成する']],['TXT_GENERATE','Synthesize',['合成','合成する']],
  ['TXT_NO','Cancel',['取消','やめる']]].map(([key,source,pair])=>[key,{source,model:{pairs:{[source]:pair},plain_pairs:{}}}]));
const tr=new RuntimeText({pairs:{},plain_pairs:{},keyed});
const results=[];let total=0;
rpc.exports={run(){
  for(const [side,hash,input,key] of [[0,1,'Enhance','TXT_CUSTOMIZE'],[0,2,'Synthesize','TXT_CREATE'],
      [0,3,'Synthesize','TXT_GENERATE'],[1,4,'Cancel','TXT_NO']]){
    functions[side](label,hash,Memory.allocUtf8String(input));
    const row=labels.get(String(label));if(row?.nativeTextKey!==key||readText(label)!==input)throw Error('native key/copy mismatch');
    const plan=tr.render(row.original,'annotation',row.nativeTextKey),primary=tr.translate(row.original,'primary',row.nativeTextKey),secondary=tr.translate(row.original,'secondary',row.nativeTextKey);
    const expected=keyed[key].model.pairs[input];
    const payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
    if(primary!==expected[0]||secondary!==expected[1]||!payload.includes(expected[1]))throw Error('renderer mismatch');
    results.push({key,source:row.original,primary,secondary,kind:plan.kind});total++;
  }
  // Wrong hash, unsupported format and mismatched current text revoke the old
  // owner even when the buffer/object address and source bytes are reused.
  for(const [hash,input] of [[99,'Cancel'],[5,'Cancel'],[1,'Cancel']]){
    functions[0](label,hash,Memory.allocUtf8String(input));
    if(labels.get(String(label))?.nativeTextKey)throw Error('stale owner retained');total++;
  }
  label.writePointer(ptr(0x9999));functions[0](label,1,Memory.allocUtf8String('Enhance'));
  label.writePointer(ptr(0x1234));labels.delete(String(label));
  if(errors.length)throw Error(errors.join(';'));
  return {total,results,errors,limits:['Actual callback register/printf/copy and renderer execution in an isolated helper; full setter/Update lifecycle uses separate production VM tests.','No game process, native controller or game rendering executed.']};
}};
"""
    return runtime + "\n" + fixture.replace("__HOOKS__", hooks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/native-shop-copy-regression.json"
    )
    parser.add_argument(
        "--package", type=Path, help="Read the production scripts from this independent candidate"
    )
    a = parser.parse_args()
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        session = frida.attach(process.pid)
        try:
            script = session.create_script(
                source(a.package.resolve() if a.package else ROOT), runtime="v8"
            )
            messages = []
            script.on("message", lambda message, _data: messages.append(message))
            script.load()
            if any(m.get("type") == "error" for m in messages):
                raise RuntimeError(json.dumps(messages, ensure_ascii=False))
            result = script.exports_sync.run()
        finally:
            process.terminate()
            process.wait(timeout=5)
            session.detach()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"total": result["total"], "failures": len(result["errors"])}))
