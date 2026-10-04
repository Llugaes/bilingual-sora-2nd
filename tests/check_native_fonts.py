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
VOICE_EXE_SHA = "b9bfd04877277ea0a4512da2e5fd7d7ec6d8e7c86227e5c16c2c12c3a7b13414"
# Read from the known voice 1.0.7 image. Keep the actual relative instructions
# and image-base calculations: the host maps these snippets at their real RVAs.
# Only the helper CALL destinations are replaced by bounded fixture callbacks.
VOICE_CODE = {
    "image_call": [0x5C5DB3, "e8f8e40800e903947200909090"],
    "reader_entry": [0x6542B0, "e97baf6900"],
    "post_call": [
        0xCEF1C0,
        "4883ec3089442428488d0d31feffff4881e900f0ce004889ea4189c0e88b120000"
        "8b4424284883c43085c0741c488d45d04c8d1d08feffff4981eb00f0ce00"
        "4981c3c05d5c0041ffe34c8d1df0fdffff4981eb00f0ce004981c3085e5c0041ffe3",
    ],
    "reader_wrapper": [
        0xCEF230,
        "4883ec5848894c242848895424304c894424384c894c2440488d0db1fdffff"
        "4881e900f0ce00488b542430e81f1300004989c3488b4c2428488b542430"
        "4c8b4424384c8b4c24404d85db490f45d34883c45848895c24204c8d1d72fdffff"
        "4981eb00f0ce004981c3b542650041ffe3",
    ],
    "absolute_path": [
        0xCEF36B,
        "31c04885ff742d8a1784d2742780fa2f741d80fa5c741883e2df83ea41"
        "80fa190f96c231c0807f013a0f94c021d0c3b801000000c3",
    ],
}


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


def voice_disk_contract(exe):
    assert hashlib.sha256(exe.read_bytes()).hexdigest() == VOICE_EXE_SHA
    pe = pefile.PE(str(exe), fast_load=True)
    try:
        for name, (rva, hexadecimal) in VOICE_CODE.items():
            expected = bytes.fromhex(hexadecimal)
            assert pe.get_data(rva, len(expected)) == expected, name
    finally:
        pe.close()


def check(exe=None, voice_exe=None):
    if exe:
        disk_contract(exe)
    if voice_exe:
        voice_disk_contract(voice_exe)
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
const state=Memory.alloc(4096);
state.add(1048).writeU64(uint64('0x1234567812345678'));
const native=new CModule(`
    #include <stdint.h>
    #include <string.h>
    extern char path[1024];
    extern uintptr_t reader;
    extern uint32_t first,second;
    extern uint16_t language;
    extern uint64_t read_result;
    extern uintptr_t absolute_predicate, replacement, post_frame;
    extern uint32_t filter_calls, absolute, post_calls, post_status;
    extern char filter_path[1024];
    int64_t original_read(void *r,const char *p,uint32_t a,uint32_t b,uint16_t l) {
        reader=(uintptr_t)r; first=a;second=b;language=l;
        unsigned int i=0;if(p)for(;i<1023&&p[i];i++)path[i]=p[i];path[i]=0;
        return read_result;
    }
    const char *filter_read(void *base,const char *p) {
        filter_calls++;
        unsigned int i=0;if(p)for(;i<1023&&p[i];i++)filter_path[i]=p[i];filter_path[i]=0;
        absolute=((int (*)(void *,const char *))absolute_predicate)(base,p);
        return (!p||absolute)?0:(const char *)replacement;
    }
    uint32_t report_read(void *base,void *frame,uint32_t status) {
        post_calls++;post_frame=(uintptr_t)frame;post_status=status;
        return 0xdeadbeef; /* The real wrapper must restore EAX after this CALL. */
    }
    char *last_path(void){return path;}
    uintptr_t last_reader(void){return reader;}
    uint32_t last_first(void){return first;}
    uint32_t last_second(void){return second;}
    uint32_t last_language(void){return language;}
`,{path:state,reader:state.add(1024),first:state.add(1032),second:state.add(1036),language:state.add(1040),
    read_result:state.add(1048),absolute_predicate:state.add(1056),replacement:state.add(1064),
    filter_calls:state.add(1072),absolute:state.add(1076),post_calls:state.add(1080),
    post_status:state.add(1084),post_frame:state.add(1088),filter_path:state.add(2048)});
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
        source += "\nconst voiceCode=" + json.dumps(VOICE_CODE) + ";\n"
        source += r"""
// The copied code derives its image base from RIP and resumes at fixed RVAs.
// A sparse owned allocation preserves that geometry without loading the EXE.
const voice=Memory.alloc(0xcf1000,{near:native.original_read,maxDistance:0x7fffffff});
const voiceEntry=voice.add(0x5c5d70),voiceCall=voice.add(0x5c5db3),voiceReader=voice.add(0x6542b0);
function emit(at,callback){
    const w=new X86Writer(at,{pc:at});callback(w);w.flush();w.dispose();
}
function nearCall(at,target){emit(at,w=>{w.putCallAddress(target);check(w.offset===5,'voice helper CALL must be near');});}
for(const [rva,hexadecimal] of Object.values(voiceCode))
    voice.add(rva).writeByteArray(hexadecimal.match(/../g).map(value=>parseInt(value,16)));
nearCall(voice.add(0xcef1dc),native.report_read);
nearCall(voice.add(0xcef25b),native.filter_read);
// The production reader continues after the displaced MOV [rsp+20],rbx.
// Its fixture continuation records all five arguments and returns a sentinel.
emit(voice.add(0x6542b5),w=>w.putJmpAddress(native.original_read));
// Caller scaffold only: save RBP and forward the fifth Win64 argument. The
// copied post-call wrapper uses RBP to identify the frame and the error path.
voiceEntry.writeByteArray([0x55,0x48,0x83,0xec,0x30,0x48,0x89,0xe5,
    0x66,0x8b,0x44,0x24,0x60,0x66,0x89,0x44,0x24,0x20]);
emit(voiceEntry.add(18),w=>w.putJmpAddress(voiceCall));
// Real post-call targets: success keeps EAX=0; error carries &frame[-0x30]
// into the game's logger. Record that value before our common test epilogue.
for(const [rva,branch] of [[0x5c5dc0,2],[0x5c5e08,1]])emit(voice.add(rva),w=>{
    w.putMovRegAddress('r11',state.add(1120));
    w.putBytes([0x41,0xc7,0x03,branch,0,0,0,0x49,0x89,0x43,0x08,
        0x48,0x83,0xc4,0x30,0x5d,0xc3]);
});
// The MOD predicate takes its string in RDI, not a Windows argument register.
// Preserve RDI and call the exact copied predicate, instead of mirroring it in C.
const absoluteThunk=voice.add(0x1000);
absoluteThunk.writeByteArray([0x57,0x48,0x89,0xd7,0x48,0x83,0xec,0x20]);
nearCall(absoluteThunk.add(8),voice.add(0xcef36b));
absoluteThunk.add(13).writeByteArray([0x48,0x83,0xc4,0x20,0x5f,0xc3]);
state.add(1056).writePointer(absoluteThunk);
Memory.protect(voice,0xcf1000,'r-x');
const voiceRead=new NativeFunction(voiceEntry,'uint64',['pointer','pointer','uint','uint','uint16']);
const directVoiceRead=new NativeFunction(voiceReader,'uint64',['pointer','pointer','uint','uint','uint16']);
const loose=Memory.allocUtf8String('C:/voice-mod/loose-resource.dds');
let voiceBridge=null;
rpc.exports.voice=()=>{
    let checks=0;
    function runVoice(input,wanted,{direct=false,result='0',absolute=false,filterInput=input,replacement=loose}={}){
        state.add(1048).writeU64(uint64(result));state.add(1064).writePointer(replacement);
        state.add(1072).writeU32(0);state.add(1080).writeU32(0);state.add(1120).writeU32(0);
        const returned=(direct?directVoiceRead:voiceRead)(ptr(0x12345678),
            input===null?ptr(0):Memory.allocUtf8String(input),0x87654321,0x76543212,0xabcd);
        check(reader().equals(ptr(0x12345678))&&first()===0x87654321&&second()===0x76543212&&language()===0xabcd,
            'voice argument corruption: '+input);
        check(path().readUtf8String()===wanted,'voice wrong final path: '+path().readUtf8String());
        check(state.add(1072).readU32()===1,'reader entry detour did not execute exactly once');
        check(state.add(1076).readU32()===(absolute?1:0),'MOD absolute-path predicate: '+input);
        check(state.add(2048).readUtf8String()===(filterInput??''),'CALL bridge/reader detour order: '+input);
        if(direct){
            check(returned.compare(uint64(result))===0,'reader-entry detour truncated the 64-bit result');
            check(state.add(1080).readU32()===0&&state.add(1120).readU32()===0,'direct reader reached image post-call');
        }else{
            const status=uint64(result).and(uint64('0xffffffff')).toNumber();
            check(state.add(1080).readU32()===1&&state.add(1084).readU32()===status,'post-call status/visit mismatch');
            check(state.add(1120).readU32()===(status===0?1:2),'post-call success/failure branch differs');
            const expected=status===0?ptr(0):state.add(1088).readPointer().sub(0x30);
            check(state.add(1128).readPointer().equals(expected),'post-call continuation RAX differs');
            check(returned.toString()===uint64(expected.toString()).toString(),'post-call return/stack corrupted');
        }
        checks++;
    }
    const resource='asset/dx11/image/'+alias+'.dds';
    runVoice(resource,loose.readUtf8String()); // Red control: unhooked MOD remaps the alias.
    voiceBridge=installFontImageBridge(voiceCall,voiceReader,[{alias,path:destination}]);
    runVoice(resource,destination,{absolute:true,filterInput:destination});
    runVoice('asset_sc\\dx11\\image\\'+alias+'.dds',destination,{absolute:true,filterInput:destination});
    runVoice('C:/voice-mod/'+alias+'.dds',destination,{absolute:true,filterInput:destination});
    runVoice('asset/dx11/image/font_0.dds',loose.readUtf8String());
    runVoice(resource+'.bak',loose.readUtf8String());
    runVoice('asset/dx11/image/font_0.dds','asset/dx11/image/font_0.dds',{replacement:ptr(0)});
    runVoice('D:/prepared/font_0.fnt','D:/prepared/font_0.fnt',{absolute:true});
    runVoice('\\\\server\\prepared\\font_0.dds','\\\\server\\prepared\\font_0.dds',{absolute:true});
    runVoice(null,'');
    for(const result of ['1','0xffffffff','0x1234567812345678','0x1234567800000000'])
        runVoice(resource,destination,{result,absolute:true,filterInput:destination});
    // Direct reader entry retains the full RAX return and bypasses our CALL hook.
    runVoice(resource,loose.readUtf8String(),{direct:true,result:'0x1234567812345678'});
    runVoice('D:/prepared/font_0.fnt','D:/prepared/font_0.fnt',{direct:true,absolute:true,result:'0x1234567812345678'});
    runVoice('\\\\server\\prepared\\font_0.fnt','\\\\server\\prepared\\font_0.fnt',
        {direct:true,absolute:true,result:'0x1234567812345678'});
    let rejected=false;
    try{installFontImageBridge(voiceCall,voiceReader,[{alias,path:destination}]);}catch(_){rejected=true;}
    check(rejected,'voice bridge accepted an already changed CALL');checks++;
    return {passed:true,checks,shape:'E8 + post-call E9; reader-entry E9',
        return_contract:'reader preserves RAX; real post-call wrapper restores EAX only',
        scope:'owned host, copied detours/predicate; IO helpers stubbed, no GPU/cache or voice resource-pack acceptance'};
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
        result["voice"] = script.exports_sync.voice()
        result["checks"] += result["voice"]["checks"]
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
    parser.add_argument("--voice-exe", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.exe, args.voice_exe), ensure_ascii=False))
