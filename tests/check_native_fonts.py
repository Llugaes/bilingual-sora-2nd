"""Font resource bridge contracts in our own hidden process, never the game."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import frida
import pefile

ROOT = Path(__file__).resolve().parents[1]
EXE_SHA = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"


def disk_contract(exe):
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == EXE_SHA
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        code = pe.get_data(0x5C6103, 5)
        assert code[0] == 0xE8
        assert 0x5C6108 + int.from_bytes(code[1:], "little", signed=True) == 0x654640
        # FNT reader stores the real allocation, glyph base and count-derived
        # search stride. The adapter delegates this to the native reader.
        assert pe.get_data(0x5BFB22, 15).hex() == "488b1748895708488d422848894710"
    finally:
        pe.close()


def check(exe=None):
    if exe:
        disk_contract(exe)
    host = subprocess.Popen(
        [sys.executable, "-c", "import os,sys;print(os.getpid(),flush=True);sys.stdin.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(int(host.stdout.readline()))
        source = "\n".join(
            (ROOT / "sora_bilingual/game/scripts" / name).read_text("utf-8")
            for name in ("native_hash.js", "runtime_fonts.js", "native_fonts.js")
        )
        source += r"""
function check(v,m){if(!v)throw Error(m);}
const state=Memory.alloc(1100);
const native=new CModule(`
    #include <stdint.h>
    #include <string.h>
    extern char path[1024];
    extern uintptr_t reader;
    extern uint32_t first,second;
    extern uint16_t language;
    int64_t original_read(void *r,const char *p,uint32_t a,uint32_t b,uint16_t l) {
        reader=(uintptr_t)r; first=a;second=b;language=l;
        unsigned int i=0;if(p)for(;i<1023&&p[i];i++)path[i]=p[i];path[i]=0;
        return 0x1234567812345678LL;
    }
    char *last_path(void){return path;}
    uintptr_t last_reader(void){return reader;}
    uint32_t last_first(void){return first;}
    uint32_t last_second(void){return second;}
    uint32_t last_language(void){return language;}
`,{path:state,reader:state.add(1024),first:state.add(1032),second:state.add(1036),language:state.add(1040)});
const code=Memory.alloc(Process.pageSize,{near:native.original_read,maxDistance:0x7fffffff});
// Win64 forwarding wrapper: preserve argument 5 in its outgoing stack slot.
Memory.patchCode(code,64,writable=>{
    writable.writeByteArray([0x48,0x83,0xec,0x28,0x66,0x8b,0x44,0x24,0x50,0x66,0x89,0x44,0x24,0x20]);
    const w=new X86Writer(writable.add(14),{pc:code.add(14)});
    w.putCallAddress(native.original_read);check(w.offset===5,'fixture CALL must be near');w.flush();w.dispose();
    writable.add(19).writeByteArray([0x48,0x83,0xc4,0x28,0xc3]);
});
Memory.protect(code,Process.pageSize,'r-x');
const read=new NativeFunction(code,'int64',['pointer','pointer','uint','uint','uint16']);
const path=new NativeFunction(native.last_path,'pointer',[]);
const reader=new NativeFunction(native.last_reader,'pointer',[]);
const first=new NativeFunction(native.last_first,'uint',[]),second=new NativeFunction(native.last_second,'uint',[]);
const language=new NativeFunction(native.last_language,'uint',[]);
const alias='sora_font_'+'a'.repeat(64),destination='C:/prepared/fonts/'+alias+'.dds';
function run(input,wanted){
    const result=read(ptr(0x1234),input===null?ptr(0):Memory.allocUtf8String(input),0x87654321,2,0x1234);
    check(result.toString()==='1311768465173141112','return value truncated');
    check(reader().equals(ptr(0x1234))&&first()===0x87654321&&second()===2&&language()===0x1234,'argument corruption');
    check(path().readUtf8String()===wanted,'wrong resource path: '+path().readUtf8String());
}
rpc.exports.check=()=>{
    run('asset/dx11/image/'+alias+'.dds','asset/dx11/image/'+alias+'.dds');
    const bridge=installFontImageBridge(code.add(14),native.original_read,[{alias,path:destination}]);
    run('asset/dx11/image/'+alias+'.dds',destination);
    run('asset_sc\\dx11\\image\\'+alias+'.dds',destination);
    run('asset/dx11/image/font_0.dds','asset/dx11/image/font_0.dds');
    run('asset/dx11/image/'+alias+'.dds.bak','asset/dx11/image/'+alias+'.dds.bak');
    run(null,'');
    // A direct call bypassing this image-cache site must not be redirected.
    new NativeFunction(native.original_read,'int64',['pointer','pointer','uint','uint','uint16'])(
        ptr(0),Memory.allocUtf8String(alias+'.dds'),0,2,0);
    check(path().readUtf8String()===alias+'.dds','CALL hook followed the global reader');
    let rejected=false;
    try{installFontImageBridge(code.add(14),native.original_read,[{alias,path:destination}]);}catch(_){rejected=true;}
    check(rejected,'must not patch an already changed call site');
    return {passed:true,checks:8,scope:'owned hidden process; no GPU upload or game mutation'};
};
"""
        source += (ROOT / "tests/native_fonts_adapter.js").read_text("utf-8")
        script = session.create_script(source, runtime="v8")
        errors = []
        script.on(
            "message",
            lambda message, _data: errors.append(message) if message["type"] == "error" else None,
        )
        script.load()
        assert not errors, errors
        result = script.exports_sync.check()
        from test_font_delivery import _candidate, _fnt

        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp)
            _candidate(candidate, 0x42)
            from sora_bilingual.fonts.runtime_fonts import runtime_manifest
            from unittest.mock import patch

            with patch("sora_bilingual.fonts.runtime_fonts.FpacArchive") as archive:
                archive.return_value.read.return_value = _fnt(0x41)
                manifest = runtime_manifest(candidate, candidate)
            result["adapter"] = script.exports_sync.adapter(manifest, list(_fnt(0x41)))
            result["failed_upload"] = script.exports_sync.adapter(manifest, list(_fnt(0x41)), True)
        return result
    finally:
        if session:
            session.detach()
        host.communicate(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.exe), ensure_ascii=False))
