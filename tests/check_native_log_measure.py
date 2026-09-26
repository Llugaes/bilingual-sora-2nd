"""Execute the production MessageLog measurement hooks against a relocated offline clone.

The only attached process is a hidden Python helper created by this test.  The
fixture copies the verified 0x362BD0..0x362ECF function from the installed PE,
relocates its RIP data and external calls, and lets Frida invoke the current
native_agent.js log-measure interceptors at their original RVA offsets.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import json
from pathlib import Path
import struct
import subprocess
import sys

import capstone
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
import frida
import pefile


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "sora_bilingual/game/scripts/native_agent.js"
EXE: Path | None = None
OUTPUT = ROOT / "generated/diagnostic-086-native-log.json"
START = 0x362BD0
END = 0x362ECF
POINTS = {
    "log_measure": START,
    "log_measure_row": 0x362D7B,
    "log_measure_body": 0x362D8F,
    "log_measure_calculate": 0x362D9B,
    "log_measure_row_end": 0x362E40,
    "font_reset": 0x5BF8F0,
    "font_load": 0x5BF350,
}


def rva_offset(pe: pefile.PE, rva: int) -> int:
    for section in pe.sections:
        size = max(section.Misc_VirtualSize, section.SizeOfRawData)
        if section.VirtualAddress <= rva < section.VirtualAddress + size:
            return section.PointerToRawData + rva - section.VirtualAddress
    raise ValueError(f"RVA outside image: {rva:#x}")


def c_string(data: bytes, offset: int, limit: int = 96) -> bytes:
    value = data[offset : offset + limit]
    return value[: value.find(b"\0") + 1] if b"\0" in value else value


def clone_spec() -> dict:
    pe = pefile.PE(str(EXE), fast_load=True)
    try:
        image = EXE.read_bytes()
        base = pe.OPTIONAL_HEADER.ImageBase
        code = image[rva_offset(pe, START) : rva_offset(pe, END)]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        data_chunks: list[bytes] = []
        data_index: dict[int, int] = {}

        def copied_data(target: int) -> int:
            if target in data_index:
                return data_index[target]
            # The first five RIP references are scalar float constants; the
            # final three are the window/name/text lookup keys.
            if target in (0xAEABE0, 0xAE9F44, 0xAE6AE8):
                offset = rva_offset(pe, target)
                value = c_string(image, offset)
            else:
                value = image[rva_offset(pe, target) : rva_offset(pe, target) + 4]
            data_index[target] = len(data_chunks)
            data_chunks.append(value)
            return data_index[target]

        rip, calls = [], []
        expected_calls = {0x5814B0: "lookup", 0x588A40: "set_text", 0x37F40: "destroy"}
        for instruction in md.disasm(code, base + START):
            local = instruction.address - base - START
            for operand in instruction.operands:
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                    target = instruction.address + instruction.size + operand.mem.disp - base
                    rip.append(
                        {
                            "offset": local + instruction.disp_offset,
                            "next": local + instruction.size,
                            "data": copied_data(target),
                            "target_rva": target,
                        }
                    )
                if instruction.mnemonic == "call" and operand.type == X86_OP_IMM:
                    target = operand.imm - base
                    if target not in expected_calls:
                        raise RuntimeError(f"unexpected external clone call {target:#x}")
                    calls.append(
                        {
                            "offset": local + instruction.imm_offset,
                            "next": local + instruction.size,
                            "stub": expected_calls[target],
                            "target_rva": target,
                        }
                    )
        if len(calls) != 7 or len(rip) != 8:
            raise RuntimeError(
                f"unexpected clone relocation shape calls={len(calls)} rip={len(rip)}"
            )
        return {
            "bytes": list(code),
            "rip": rip,
            "calls": calls,
            "data": [list(chunk) for chunk in data_chunks],
            "sha256": hashlib.sha256(EXE.read_bytes()).hexdigest(),
        }
    finally:
        pe.close()


def production_hook_source() -> str:
    source = AGENT.read_text("utf-8")
    start = source.index("function logMeasureKey(")
    end = source.index("Interceptor.attach(base.add(REPORT.native.set_text.rva)", start)
    block = source[start:end]
    required = (
        "log_measure_row",
        "log_measure_body",
        "log_measure_calculate",
        "log_measure_row_end",
    )
    missing = [name for name in required if name not in block]
    if missing:
        raise RuntimeError("current production hook is incomplete: " + ", ".join(missing))
    # The production block is evaluated as a string in the isolated fixture.
    # Export only its gate object so this host can detach its own listener after
    # every behavioural case; the resident production listener is never detached.
    return block + "\nglobalThis.__fixtureLogMeasureGate=logMeasureGate;\n"


def agent_source(spec: dict, hooks: str) -> str:
    c_source = r"""
typedef unsigned int u32;
typedef unsigned long long uptr;
static int length_of(const char *s) { int n=0; while(s && s[n]) n++; return n; }
static int lines_of(const char *s) { int n=0, lines=0; if(!s || !s[0]) return 0; lines=1; while(s[n]) { if(s[n]=='\n') lines++; n++; } return lines; }
void *lookup_stub(void *root, const char *key, u32 max_value, u32 allow) {
    (void)max_value; (void)allow;
    if(key && key[0]=='w' && key[1]=='i') return *(void **)((char *)root+0x00);
    if(key && key[0]=='n' && key[1]=='a') return *(void **)((char *)root+0x08);
    if(key && key[0]=='t' && key[1]=='e') return *(void **)((char *)root+0x10);
    return 0;
}
void set_text_stub(void *label, const char *source) {
    int width=length_of(source), lines=lines_of(source);
    *(const char **)((char *)label+0x318)=source;
    *(u32 *)((char *)label+0x334)=(u32)(width!=0);
    *(u32 *)((char *)label+0x668)=(u32)lines;
    *(u32 *)((char *)label+0x36c)=0;
    *(u32 *)((char *)label+0x374)=(u32)(width*7);
    (*(u32 *)((char *)label+0x7f0))++;
}
void destroy_stub(void *slot) { *(void **)slot=0; *(u32 *)((char *)slot+8)=0xd35d0001; }
"""

    return r"""
const START=%d, END=%d, ARENA_SIZE=0x280000;
const cloneSpec=%s, productionHooks=%s;
const arena=Memory.alloc(ARENA_SIZE);
if(!Memory.protect(arena,ARENA_SIZE,'rwx'))throw Error('cannot make clone arena executable');
const base=arena.sub(START), DATA_OFFSET=0x800, THUNK_OFFSET=0x500;
const REPORT={vtable:START+0x1000,native:%s};
const stubModule=new CModule(%s);
const stub={lookup:stubModule.lookup_stub,setText:stubModule.set_text_stub,destroy:stubModule.destroy_stub};
function signed32(value,label){try{return value.toInt32();}catch(_){throw Error('rel32 out of range '+label);}}
function writeAbsJump(at,target){
 const raw=[0x48,0xb8];let value=target.toString().replace('0x','').padStart(16,'0');
 for(let i=14;i>=0;i-=2)raw.push(parseInt(value.slice(i,i+2),16));raw.push(0xff,0xe0);Memory.patchCode(at,raw.length,writable=>writable.writeByteArray(raw));
}
Memory.patchCode(arena,cloneSpec.bytes.length,writable=>writable.writeByteArray(cloneSpec.bytes));
const dataOffsets=[];let cursor=DATA_OFFSET;
for(const bytes of cloneSpec.data){dataOffsets.push(cursor);arena.add(cursor).writeByteArray(bytes);cursor=(cursor+bytes.length+7)&~7;}
const thunks={};let thunkCursor=THUNK_OFFSET;
for(const name of ['lookup','set_text','destroy']){thunks[name]=arena.add(thunkCursor);writeAbsJump(thunks[name],name==='lookup'?stub.lookup:name==='set_text'?stub.setText:stub.destroy);thunkCursor+=16;}
for(const rel of cloneSpec.rip){arena.add(rel.offset).writeS32(signed32(arena.add(dataOffsets[rel.data]).sub(arena.add(rel.next)),'rip '+rel.target_rva.toString(16)));}
for(const rel of cloneSpec.calls){arena.add(rel.offset).writeS32(signed32(thunks[rel.stub].sub(arena.add(rel.next)),'call '+rel.stub));}
for(const rva of [REPORT.native.font_reset.rva,REPORT.native.font_load.rva])Memory.patchCode(arena.add(rva-START),16,writable=>writable.writeByteArray([0x48,0x83,0xec,0x28,0x90,0x90,0x90,0x90,0x48,0x83,0xc4,0x28,0xc3,0x90,0x90,0x90]));
const cloneMeasure=new NativeFunction(arena,'void',['pointer'],'win64');
let enabled=true,failed=false,epoch=1,logFontGeneration=0,logCacheBytes=0,layerVersion=0,translationEnabled=true,setTextCallbacks=0;
let annotationScale=.85,rubyScale=.9,rubyLineGap=6;
const labels=new Map(),logMeasureFrames=new Map(),logHeightCache=new Map(),logNameCache=new Map();
const logMeasureStats={runs:0,totalMs:0,hits:0,misses:0,nameHits:0,fixedRows:0,fallbacks:0,lastFallback:null};
const fixture={name:NULL,body:NULL,window:NULL};
function isLabel(p){return p.readPointer().equals(base.add(REPORT.vtable));}
function readText(p){const value=p.add(0x318).readPointer();return value.isNull()?'':value.readUtf8String();}
function roleFor(p){return p.equals(fixture.name)?'name':'body';}
function planFor(role,original){return {kind:'ruby',layers:role==='body'&&original==='layers'?['ruby',layerVersion]:[]};}
function identifyInput(row,input){row.role=roleFor(row.pointer);row.plan=planFor(row.role,row.original);row.reserveRubyHeight=false;row.preservePrimaryLayout=false;row.extendLineSpacing=false;}
const translatedInputs=new Map();
function translatedText(original){return translationEnabled&&original==='fixture source'?'fixture translated body with a materially longer measured extent':original;}
function wantedText(row){return translatedText(row.original);}
function translatedPointer(value){let pointer=translatedInputs.get(value);if(!pointer){pointer=Memory.allocUtf8String(value);translatedInputs.set(value,pointer);}return pointer;}
Interceptor.attach(stub.setText,{onEnter(args){this.label=args[0];this.original=args[1].isNull()?'':args[1].readUtf8String();this.displayed=translatedText(this.original);if(this.displayed!==this.original)args[1]=translatedPointer(this.displayed);setTextCallbacks++;},onLeave(){const role=roleFor(this.label),row={pointer:this.label,original:this.original,displayed:readText(this.label),plan:planFor(role,this.original),reserveRubyHeight:false,preservePrimaryLayout:false,extendLineSpacing:false};labels.set(String(this.label),row);}});
eval(productionHooks);
function fail(message){throw Error(message);}
function fbits(pointer){return pointer.readU32();}
function makeLabel(){const p=Memory.alloc(0x800);p.writeByteArray(new Uint8Array(0x800));p.writePointer(base.add(REPORT.vtable));p.add(0x7f0).writeU32(0);const style=new Uint8Array(0x40);style[0]=0x71;style[0x28]=0;p.add(0x2d8).writeByteArray(style);return p;}
function alloc(s){return Memory.allocUtf8String(s);}
function ownerFor(rows,mode,width){
 const owner=Memory.alloc(0x220),template=Memory.alloc(0x240),array=Memory.alloc(Process.pointerSize),records=Memory.alloc(Math.max(1,rows.length)*0x38),descriptors=Memory.alloc(Math.max(1,rows.length)*0x1c),keep=[owner,template,array,records,descriptors];
 template.writePointer(fixture.window);template.add(8).writePointer(fixture.name);template.add(0x10).writePointer(fixture.body);array.writePointer(template);template.add(0x228).writePointer(array);template.add(0x230).writeU64(1);
 owner.add(0xa0).writePointer(template);owner.add(0xd0).writePointer(records);owner.add(0xd8).writeU32(rows.length);owner.add(0xe8).writePointer(descriptors);owner.add(0xf0).writeU32(rows.length);owner.add(0x1d4).writeU32(mode);fixture.window.add(0x2d8).writeS32(width);
 for(let i=0;i<rows.length;i++){
   const [name,body]=rows[i],record=records.add(i*0x38),desc=descriptors.add(i*0x1c),nameIn=alloc(name),bodyIn=alloc(body);keep.push(nameIn,bodyIn);record.writeU32(100+i);record.add(8).writePointer(bodyIn);record.add(0x20).writePointer(nameIn);desc.writeU32(0xdead0000+i);
 }
 return {owner,template,array,records,descriptors,rows,keep};
}
function setterCount(){return fixture.name.add(0x7f0).readU32()+fixture.body.add(0x7f0).readU32();}
function destroyCount(run){let total=0;for(let i=0;i<run.rows.length;i++){const r=run.records.add(i*0x38);if(r.add(0x10).readU32()===0xd35d0001)total++;if(r.add(0x28).readU32()===0xd35d0001)total++;}return total;}
function callRows(rows,{mode=0,width=900}={}){
 fixture.name=makeLabel();fixture.body=makeLabel();fixture.window=Memory.alloc(0x400);const run=ownerFor(rows,mode,width),callbackStart=setTextCallbacks;cloneMeasure(run.owner);
 const heights=[],widths=[],ids=[];for(let i=0;i<rows.length;i++){const d=run.descriptors.add(i*0x1c);heights.push(fbits(d.add(0x18)));widths.push(d.add(0x14).readS32());ids.push(d.readU32());}
 const result={setters:setterCount(),setTextCallbacks:setTextCallbacks-callbackStart,destroys:destroyCount(run),heights,widths,ids,labelTexts:{name:readText(fixture.name),body:readText(fixture.body)},ownerCount:run.owner.add(0xd8).readU32(),recordPointers:rows.map((_,i)=>[run.records.add(i*0x38+8).readPointer().isNull(),run.records.add(i*0x38+0x20).readPointer().isNull()])};
 if(result.setTextCallbacks!==result.setters)fail('SetText callback mismatch '+result.setTextCallbacks+'/'+result.setters);
 if(result.destroys!==2*rows.length)fail('cleanup count '+result.destroys);if(result.ownerCount!==0)fail('owner D8 not cleared');if(result.recordPointers.some(pair=>!pair[0]||!pair[1]))fail('record input not destroyed');return result;
}
function same(left,right,label){if(left.length!==right.length)fail(label+' length');for(let i=0;i<left.length;i++)if(left[i]!==right[i])fail(label+' '+i+' '+left[i]+' '+right[i]);}
function resetCaches(){logHeightCache.clear();logNameCache.clear();logCacheBytes=0;}
// 362C68..87 writes descriptor r12 from record (owner.D8 - 1 - r12).
function expectedIds(rows){return rows.map((_,i)=>100+rows.length-1-i);}
function verifyNativeTail(result,rows,width,label){
 same(result.ids,expectedIds(rows),label+' IDs');
 if(result.widths.some(value=>value!==width))fail(label+' current width '+result.widths);
 if(result.destroys!==2*rows.length)fail(label+' destructors '+result.destroys);
 if(result.ownerCount!==0)fail(label+' owner count '+result.ownerCount);
}
function nativeBaseline(rows,options={}){
 const previous=enabled;enabled=false;
 try{return callRows(rows,options);}finally{enabled=previous;}
}
function nativeWithoutTranslation(rows,options={}){
 const previous=translationEnabled;translationEnabled=false;
 try{return nativeBaseline(rows,options);}finally{translationEnabled=previous;}
}
const resetFont=new NativeFunction(base.add(REPORT.native.font_reset.rva),'void',[]);
rpc.exports={run(){
 const rows=[['',''],['Ann','short'],['Name','line one\nline two'],['Long','x'.repeat(4096)],['Layer','layers']];
 resetCaches();const nativeCold=nativeBaseline(rows);verifyNativeTail(nativeCold,rows,900,'native cold');if(nativeCold.setters!==rows.length*2)fail('native cold setters '+nativeCold.setters);
 const cold=callRows(rows);same(nativeCold.heights,cold.heights,'cold native height bits');verifyNativeTail(cold,rows,900,'cold');if(cold.setters!==rows.length*2)fail('cold setters '+cold.setters);
 const warm=callRows(rows);same(cold.heights,warm.heights,'full-cache height bits');verifyNativeTail(warm,rows,900,'warm');if(warm.setters!==0)fail('warm setters '+warm.setters);
 layerVersion++;const layerBaseline=nativeBaseline(rows),layerMiss=callRows(rows);same(layerBaseline.heights,layerMiss.heights,'layer native height bits');verifyNativeTail(layerMiss,rows,900,'layer miss');if(layerMiss.setters!==1)fail('layer body-only setter '+layerMiss.setters);
 function nameOnlyCase(label,name,seed,body){
   const oldRows=[[name,seed]],newRows=[[name,body]];resetCaches();const seedResult=callRows(oldRows);if(seedResult.setters!==2)fail(label+' seed setters '+seedResult.setters);const baseline=nativeBaseline(newRows),nameHits=logMeasureStats.nameHits,actual=callRows(newRows);same(baseline.heights,actual.heights,label+' native height bits');verifyNativeTail(actual,newRows,900,label);if(actual.setters!==1)fail(label+' name-only setter '+actual.setters);if(logMeasureStats.nameHits!==nameHits+1)fail(label+' name hit count');return {seed:seedResult,baseline,actual};
 }
 const nameOnly={normal:nameOnlyCase('normal name','Ann','seed normal','new normal'),empty:nameOnlyCase('empty name','','seed empty','new empty'),multiline:nameOnlyCase('multiline name','Alpha\nBeta','seed multiline','new multiline')};
 const translatedRows=[['Translated header','fixture source']],translatedWanted=translatedText(translatedRows[0][1]);if(translatedWanted===translatedRows[0][1]||translatedWanted.length<translatedRows[0][1].length+16)fail('fixture translation is not material');const untranslatedBaseline=nativeWithoutTranslation(translatedRows),translatedBaseline=nativeBaseline(translatedRows);if(untranslatedBaseline.heights[0]===translatedBaseline.heights[0])fail('translated native height did not differ');if(translatedBaseline.setTextCallbacks!==2||translatedBaseline.labelTexts.body!==translatedWanted)fail('translated native setter evidence');resetCaches();const translatedCold=callRows(translatedRows);same(translatedBaseline.heights,translatedCold.heights,'translated cold native height bits');verifyNativeTail(translatedCold,translatedRows,900,'translated cold');if(translatedCold.setters!==2||translatedCold.setTextCallbacks!==2||translatedCold.labelTexts.body!==translatedWanted)fail('translated miss setter callback');const translatedWarm=callRows(translatedRows);same(translatedCold.heights,translatedWarm.heights,'translated warm height bits');if(translatedWarm.setters!==0||translatedWarm.setTextCallbacks!==0)fail('translated warm setter callback');
 const fixed=callRows(rows,{mode:1});verifyNativeTail(fixed,rows,900,'mode1');if(fixed.setters!==0)fail('mode1 setters');if(fixed.heights.some(bits=>new Float32Array(new Uint32Array([bits]).buffer)[0]!==148))fail('mode1 height');
 const nativeFallback=callRows(rows,{mode:2});verifyNativeTail(nativeFallback,rows,900,'mode2');if(nativeFallback.setters!==rows.length*2)fail('mode2 did not retain native setters');
 callRows(rows);epoch++;const epochReuse=callRows(rows);verifyNativeTail(epochReuse,rows,900,'epoch');if(epochReuse.setters!==0)fail('display epoch discarded valid metrics');
 annotationScale=.8;const scaleMiss=callRows(rows);if(scaleMiss.setters!==rows.length*2)fail('parser size did not invalidate metrics');
 const fontWarm=callRows(rows);verifyNativeTail(fontWarm,rows,900,'font warm');if(fontWarm.setters!==0)fail('font warm');resetFont();const fontMiss=callRows(rows);verifyNativeTail(fontMiss,rows,900,'font reset');if(fontMiss.setters!==rows.length*2)fail('font reset did not clear');
 const repeated=callRows(rows);verifyNativeTail(repeated,rows,900,'repeated');if(repeated.setters!==0)fail('repeated frame setters');
 const selfHostGate=globalThis.__fixtureLogMeasureGate;if(!selfHostGate||!selfHostGate.gate||selfHostGate.gate.isNull()||!selfHostGate.listener)fail('missing self-host gate listener');selfHostGate.listener.detach();Interceptor.flush();const detachedFallback=callRows(rows);same(nativeCold.heights,detachedFallback.heights,'detached xor native height bits');verifyNativeTail(detachedFallback,rows,900,'detached xor fallback');if(detachedFallback.setters!==rows.length*2||detachedFallback.setTextCallbacks!==rows.length*2)fail('detached xor fallback setters');
 return {all_passed:true,host:'self-created-hidden-python',game_started:false,game_attached:false,clone:{source_rva:'0x362BD0',end_rva:'0x362ECF',base:String(base),entry:String(arena),bytes:cloneSpec.bytes.length,rip_relocations:cloneSpec.rip.map(v=>v.target_rva),external_calls:cloneSpec.calls.map(v=>v.target_rva)},production_hook:{extracted:true,requires_log_measure_body:true,gate_detached_in_self_host:true},cases:{rows:rows.length,native_cold:nativeCold,cold,warm,layer_miss:layerMiss,name_only:nameOnly,translated:{wanted:translatedWanted,untranslated_native:untranslatedBaseline,translated_native:translatedBaseline,cold:translatedCold,warm:translatedWarm},fixed,native_fallback:nativeFallback,epoch_reuse:epochReuse,scale_miss:scaleMiss,font_miss:fontMiss,repeated,detached_xor_fallback:detachedFallback},stats:logMeasureStats};
}};
""" % (
        START,
        END,
        json.dumps(spec),
        json.dumps(hooks),
        json.dumps({name: {"rva": rva} for name, rva in POINTS.items()}),
        json.dumps(c_source),
    )


def production_hook_source_placeholder(hooks: str) -> str:
    # Keep the extracted production source physically distinct from the
    # fixture. It is evaluated after the fixture globals and real Interceptor
    # have been installed.
    return "\n/* extracted production log measurement hooks */\n" + hooks + "\n"


def main(exe: Path | None = None, output: Path = OUTPUT) -> None:
    global EXE
    environment = os.environ.get("SORA_GAME_EXE")
    EXE = exe or (Path(environment) if environment else None)
    if EXE is None:
        raise SystemExit("pass --exe or set SORA_GAME_EXE to the verified sora_2nd.exe")
    if not EXE.is_file():
        raise SystemExit(f"missing verified executable: {EXE}")
    spec = clone_spec()
    hooks = production_hook_source()
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(agent_source(spec, hooks), runtime="v8")
        script.load()
        report = script.exports_sync.run()
        assert report["all_passed"]
        report["production_hook_sha256"] = hashlib.sha256(hooks.encode("utf-8")).hexdigest()
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=Path,
        help="verified sora_2nd.exe; defaults to SORA_GAME_EXE when set",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    main(args.exe, args.output)
