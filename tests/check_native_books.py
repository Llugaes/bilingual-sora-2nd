"""Validate book query ABI and production adapter in a self-created hidden host.

When the installed EXE is available, execute its actual leaf count/page queries
on synthetic table records. CI uses the same verified layout in a tiny C host.
Never opens, attaches to, or modifies the game.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import frida
import pefile

from check_native_dynamic_identity import decoded, require, direct_target

ROOT = Path(__file__).resolve().parents[1]


def bootstrap_source():
    """Replay the production prologue with real Frida patches and CNG calls."""
    scripts = ROOT / "sora_bilingual/game/scripts"
    agent_path = Path(os.environ.get("NATIVE_AGENT_SOURCE", scripts / "native_agent.js"))
    prefix, marker, _ = agent_path.read_text("utf-8").partition(
        "let fontGeneration=0,fontsWereReady=!REPORT.runtime_fonts;"
    )
    if not marker:
        raise AssertionError("Production startup boundary changed; update the integration fixture")
    dependencies = "\n".join(
        (scripts / name).read_text("utf-8")
        for name in ("runtime_text.js", "runtime_books.js", "native_books.js", "native_hash.js")
    )
    return (
        dependencies
        + "\n"
        + r"""
const bootstrap = new Function('Process','REPORT','RuntimeText','RuntimeBooks',
    'createNativeBooks','createNativeSha256',__PREFIX__+'\nreturn nativeBooks;');
const retained=[];
function runBootstrap(corrupt) {
    const base=Memory.alloc(Process.pageSize);retained.push(base);
    const names=['book_count','book_page','book_update','book_open_return','book_saved_page','book_text_return'];
    const report={native:{}};
    names.forEach((name,i)=>{
        const rva=i*64;report.native[name]={rva,bytes:'90'.repeat(16)};
        base.add(rva).writeByteArray(Array(32).fill(0x90));base.add(rva+32).writeU8(0xc3);
    });
    if(corrupt)base.add(report.native.book_text_return.rva).writeU8(0xcc);
    Memory.protect(base,Process.pageSize,'r-x');
    let factories=0,hashes=0,adapter=null,error=null;
    try {
        adapter=bootstrap({getModuleByName(name){if(name!=='sora_2nd.exe')throw Error(name);return {base};}},
            report,RuntimeText,RuntimeBooks,(...args)=>{factories++;return createNativeBooks(...args);},
            ()=>{hashes++;return createNativeSha256();});
    }catch(e){error=String(e);}
    Interceptor.flush();
    const patched=names.filter(name=>Array.from(new Uint8Array(base.add(report.native[name].rva).readByteArray(16)))
        .map(v=>v.toString(16).padStart(2,'0')).join('')!==report.native[name].bytes);
    return {corrupt,factories,hashes,error,patched,adapter_created:!!adapter};
}
rpc.exports.run=()=>({clean:runBootstrap(false),foreign:runBootstrap(true),game_attached:false});
""".replace("__PREFIX__", json.dumps(prefix))
    )


def inspect(exe):
    with pefile.PE(str(exe), fast_load=True) as pe:
        code = decoded(pe, 0x23C1E0, 0x120)
        require(code, 0x23C1E9, "movzx", "esi, dx")
        require(code, 0x23C23A, "cmp", "word ptr [rcx + rbx], si")
        require(code, 0x23C240, "movzx", "edx, word ptr [rcx + rbx + 2]")
        require(code, 0x23C248, "cmova", "r9d, edx")
        require(code, 0x23C28A, "movzx", "edi, dx")
        require(code, 0x23C2CC, "cmp", "word ptr [rax], di")
        require(code, 0x23C2D1, "cmp", "word ptr [rax + 2], r8w")
        require(code, 0x23C2E0, "xor", "eax, eax")
        reader = decoded(pe, 0x4079C0, 0x590)
        require(reader, 0x4079E6, "mov", "rsi, rcx")
        require(reader, 0x4079E3, "mov", "r14d, edx")
        require(reader, 0x407AAA, "cmovb", "eax, r14d")
        require(reader, 0x407AB5, "mov", "dword ptr [rsi + 0x1a4], eax")
        require(reader, 0x407D65, "movzx", "r8d, word ptr [rsi + 0x1a4]")
        require(reader, 0x407D6D, "movzx", "edx, word ptr [rsi + 0x1a8]")
        assert direct_target(reader[0x407D74]) == 0x23C270
        require(reader, 0x407D7C, "mov", "rdx, qword ptr [rax + 8]")
        assert direct_target(reader[0x407D80]) == 0x588A40
        image = decoded(pe, 0x407432, 0x22)
        assert direct_target(image[0x407444]) == 0x23C270
        require(image, 0x407449, "mov", "rbx, qword ptr [rax + 0x10]")
        save = decoded(pe, 0x40714C, 0x22)
        require(save, 0x407153, "movzx", "eax, byte ptr [rsi + 0x1a4]")
        require(save, 0x40715A, "mov", "byte ptr [rcx + 0x20b388], al")
        opening = decoded(pe, 0x406C0F, 0x65)
        require(opening, 0x406C16, "movzx", "eax, byte ptr [rdx + 0x20b388]")
        require(opening, 0x406C65, "mov", "edx, r14d")
        assert direct_target(opening[0x406C6B]) == 0x4079C0
        return {
            "count": pe.get_data(0x23C1E0, 0x83).hex(),
            "page": pe.get_data(0x23C270, 0x82).hex(),
        }


def source(machine):
    scripts = "\n".join(
        (ROOT / "sora_bilingual/game/scripts" / n).read_text("utf-8")
        for n in ("runtime_text.js", "runtime_books.js", "native_books.js")
    )
    return (
        scripts
        + "\nconst machine="
        + json.dumps(machine)
        + ";\n"
        + r"""
const base=Memory.alloc(0x409100);
const fixture=new CModule(`
typedef unsigned int u32; typedef unsigned short u16;
u32 count(char *t,u16 id) {char *d=*(char **)(t+0x10);u32 n=*(u32 *)(*(char **)(t+0x20)+0x4c),v=0,i;
 for(i=0;i<n;i++){char *r=d+i*24;if(*(u16 *)r==id&&*(u16 *)(r+2)>v)v=*(u16 *)(r+2);}return v;}
void *page(char *t,u16 id,u16 page){char *d=*(char **)(t+0x10);u32 n=*(u32 *)(*(char **)(t+0x20)+0x4c),i;
 for(i=0;i<n;i++){char *r=d+i*24;if(*(u16 *)r==id&&*(u16 *)(r+2)==page)return r;}return 0;}
void update(char *controller) {*(u32 *)(controller+0x1b0)=*(u32 *)(controller+0x1a4);(*(u32 *)(controller+0x1b4))++;}
`);
function code(at,bytes){const p=base.add(at);Memory.protect(p,bytes.length,'rw-');p.writeByteArray(bytes);Memory.protect(p,bytes.length,'r-x');return p;}
function unhex(s){return s.match(/../g).map(v=>parseInt(v,16));}
const count=machine?code(0x23c1e0,unhex(machine.count)):fixture.count;
const page=machine?code(0x23c270,unhex(machine.page)):fixture.page;
const returns=new Map();
function caller(at,target){const p=base.add(at);Memory.protect(p,128,'rw-');const w=new X86Writer(p,{pc:p});w.putSubRegImm('rsp',40);w.putMovRegAddress('rax',target);w.putCallReg('rax');returns.set(at,p.add(w.offset).sub(base).toString());w.putAddRegImm('rsp',40);w.putRet();w.flush();w.dispose();Memory.protect(p,128,'r-x');return p;}
const openCaller=caller(0x406c40,fixture.update);
const countCaller=caller(0x407c00,count),pageCaller=caller(0x407d00,page);
const saveStart=base.add(0x407130);Memory.protect(saveStart,128,'rw-');const sw=new X86Writer(saveStart,{pc:saveStart});sw.putPushReg('rsi');sw.putMovRegReg('rsi','rcx');sw.putMovRegReg('rcx','rdx');sw.putBytes([0x0f,0xb6,0x86,0xa4,0x01,0,0]);while(sw.offset<0x2a)sw.putNop();sw.putBytes([0x88,0x81,0x88,0xb3,0x20,0]);sw.putPopReg('rsi');sw.putRet();sw.flush();sw.dispose();Memory.protect(saveStart,128,'r-x');
const report={native:{book_count:{rva:count.sub(base).toString()},book_page:{rva:page.sub(base).toString()},book_update:{rva:fixture.update.sub(base).toString()},book_open_return:{rva:returns.get(0x406c40)},book_saved_page:{rva:0x40715a},book_text_return:{rva:0x407d85}}};
const raw=Memory.alloc(48),header=Memory.alloc(80),table=Memory.alloc(64),kept=[];
for(let i=0;i<2;i++){const r=raw.add(i*24),s=Memory.allocUtf8String('source-'+(i+1)),image=Memory.allocUtf8String('newspaper17');kept.push(s,image);r.writeU16(116);r.add(2).writeU16(i+1);r.add(8).writePointer(s);r.add(16).writePointer(image);}
header.add(0x44).writeU32(0);header.add(0x48).writeU32(24);header.add(0x4c).writeU32(2);table.add(0x10).writePointer(raw);table.add(0x20).writePointer(header);table.add(0x2c).writeU32(0);
const foreign=Array.from({length:80},(_,i)=>'foreign line '+i).join('\n'),primary=Array.from({length:50},(_,i)=>'primary line '+i).join('\n');
let active=true,mode='annotation';const books=new RuntimeBooks({116:{source:[['newspaper17','source-1'],['newspaper17','source-2']],primary:[['newspaper17',primary]],secondary:[['newspaper17',foreign]]}},RuntimeText);
const adapter=createNativeBooks(base,report,()=>({active,mode,books,style:{}}));
const getCount=new NativeFunction(countCaller,'uint',['pointer','uint16']),getPage=new NativeFunction(pageCaller,'pointer',['pointer','uint16','uint16']),originalCount=new NativeFunction(count,'uint',['pointer','uint16']),originalPage=new NativeFunction(page,'pointer',['pointer','uint16','uint16']);
const update=new NativeFunction(fixture.update,'void',['pointer']);
function check(v,m){if(!v)throw Error(m);}
rpc.exports={run(){Interceptor.flush();
 check(originalCount(table,116)===2,'outside reader count changed');check(originalPage(table,116,3).isNull(),'outside reader lookup changed');
 const count=getCount(table,116);check(count>2,'translated book did not expand');const bodies=[],secondaries=[];
 for(let p=1;p<=count;p++){const r=getPage(table,116,p);check(!r.isNull(),'missing virtual page');check(r.readU16()===116&&r.add(2).readU16()===p,'wrong book/page identity');
  check(r.add(16).readPointer().readUtf8String()==='newspaper17','image changed');const ptr=r.add(8).readPointer(),s=ptr.readUtf8String(),origin=adapter.input(ptr,s,base.add(0x407d85)),ctx=adapter.context(origin,s);check(ctx&&ctx.strict,'lost pointer provenance');const tr=new RuntimeText(ctx.model);bodies.push(tr.translate(s,'primary'));secondaries.push(tr.translate(s,'secondary'));check(tr.render(s,'annotation').kind!=='plain','missing final annotation');}
 check(bodies.join('\n')===primary&&secondaries.join('\n')===foreign,'whole document lost/repeated/reordered');
 const controller=Memory.alloc(0x200);controller.add(0x1a8).writeU32(116);controller.add(0x1a4).writeU32(count);
 const open=new NativeFunction(openCaller,'void',['pointer','uint']);open(controller,2);check(controller.add(0x1a4).readU32()===9,'physical bookmark was not restored to the matching document page');controller.add(0x1a4).writeU32(count);controller.add(0x1b4).writeU32(0);
 const saved=Memory.alloc(0x20b400),save=new NativeFunction(saveStart,'void',['pointer','pointer']);save(controller,saved);check(saved.add(0x20b388).readU8()===2,'virtual page leaked into native bookmark');check(controller.add(0x1a4).readU32()===count,'saving mutated visible page');
 const label=Memory.alloc(8);adapter.bind(label,{controller,id:116,page:count,nativePage:2,pageCount:count});
 active=false;adapter.refresh(label);check(controller.add(0x1b4).readU32()===1,'mode change did not refresh live reader');adapter.refresh(label);check(controller.add(0x1b4).readU32()===1,'unchanged reader refreshed every frame');adapter.forget(label);
 check(getCount(table,116)===2,'disable did not restore count');check(!getPage(table,116,count).isNull(),'disable transition dereferenced a null page');update(controller);check(controller.add(0x1a4).readU32()===2,'disable did not clamp current page');
 check(getPage(table,116,2).equals(raw.add(24)),'disable did not return original record');
 active=true;mode='primary';check(getCount(table,116)===1,'single-language native pagination changed');update(controller);check(controller.add(0x1a4).readU32()===1,'mode switch failed to clamp');
 const reused=getPage(table,116,1);mode='secondary';getCount(table,116);getPage(table,116,1);mode='annotation';check(getCount(table,116)===count,'reenable page count changed');
 return {game_attached:false,actual_machine_queries:!!machine,bilingual_pages:count,raw_pages:2,all_passed:true};}};
"""
    )


def main():
    exe = Path(
        os.environ.get(
            "SORA_GAME_EXE", r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter\sora_2nd.exe"
        )
    )
    machine = inspect(exe) if exe.is_file() else None
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        startup = session.create_script(bootstrap_source(), runtime="v8")
        startup.load()
        startup_result = startup.exports_sync.run()
        print(json.dumps({"production_bootstrap": startup_result}), flush=True)
        clean, foreign = startup_result["clean"], startup_result["foreign"]
        assert clean["error"] is None and clean["adapter_created"], clean
        assert clean["factories"] == 1 and clean["hashes"] == 1, clean
        assert {"book_count", "book_page", "book_update"} <= set(clean["patched"]), clean
        assert "book_text_return" in (foreign["error"] or ""), foreign
        assert foreign["factories"] == 0 and foreign["hashes"] == 0, foreign
        assert foreign["patched"] == ["book_text_return"], foreign
        startup.unload()  # Only our self-created hidden host, never the game.
        agent = session.create_script(source(machine), runtime="v8")
        agent.on(
            "message",
            lambda message, _data: (
                print(json.dumps(message)) if message.get("type") == "error" else None
            ),
        )
        agent.load()
        result = agent.exports_sync.run()
        path = ROOT / "generated/todo-native-books.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result, indent=2), "utf-8")
        print(json.dumps(result))
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
