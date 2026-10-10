"""Replay an observed small title through production callbacks in a hidden host.

The scale seam executes the verified native constructor and S/s arithmetic.
The origin seam executes the CAB first-line origin leaf with production hooks.
Captured glyph positions remain observations, not a model of native layout.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import frida

from check_native_geometry import C_SOURCE, production_helpers
from check_native_size_metrics import agent_source, extracted_absolute_factor

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/owned-small-title-layout.json"
AGENT = (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")


def section(start, end):
    offset = AGENT.index(start)
    return AGENT[offset : AGENT.index(end, offset)]


def source(fixture):
    initializer = bytes.fromhex((ROOT / "tests/fixtures/ruby_context_init.hex").read_text("ascii"))
    assert hashlib.sha256(initializer).hexdigest() == fixture["initializer_sha256"]
    formula = bytes.fromhex(fixture["size_formula_hex"])
    metric_source = agent_source(formula, extracted_absolute_factor())
    formula_helpers = metric_source[
        metric_source.index("function check(") : metric_source.index("function commandRow(")
    ]
    pieces = [
        (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf-8"),
        (ROOT / "sora_bilingual/game/scripts/native_parser.js").read_text("utf-8"),
        (ROOT / "sora_bilingual/game/scripts/native_measure.js").read_text("utf-8"),
        "const INPUT=" + json.dumps(fixture, ensure_ascii=False) + ";",
        "const FORMULA=" + json.dumps(list(formula)) + ";",
        formula_helpers,
        "const INIT=" + json.dumps(list(initializer)) + ";",
        "const GEOMETRY=" + json.dumps(C_SOURCE) + ";",
        r"""
const errors=[],auxiliaryContexts=new Map(),annotationMetrics=new Map(),compensation=new Map();
const nativeParser=createNativeParser(auxiliaryContexts,e=>errors.push(String(e)));
const formula=createFormula();formula.face0.add(0x28).writeU32(48);formula.faceLabel.add(0x28).writeU32(48);
const base=formula.arena,REPORT={text_table_global:0x180,font_manager_global:0x188,native:{},diagnostics:false};
const init=Memory.alloc(Process.pageSize);Memory.protect(init,Process.pageSize,'rwx');init.writeByteArray(INIT);
const initialScale=Memory.alloc(4);initialScale.writeFloat(.375);
const driver=new CModule(`
#include <stdint.h>
extern float initial_scale;
extern void ruby_init(void *,const char *,uint32_t,float,float,float,float);
void outer_measure(void *p,const char *s,uint32_t n){ruby_init(p,s,n,initial_scale,initial_scale,0.f,0.f);((uint8_t*)p)[0x1a5]=1;((uint8_t*)p)[0x1a9]=0;}
void outer_place(void *p,const char *s,uint32_t n){ruby_init(p,s,n,initial_scale,initial_scale,0.f,0.f);((uint8_t*)p)[0x1a9]=1;}
void base_measure(void *p,const char *s,uint32_t n){ruby_init(p,s,n,.375f,.375f,0.f,0.f);((uint8_t*)p)[0x1a5]=1;}
void measure_entry(void *label,void *p,const char *s,uint32_t n){outer_measure(p,s,n);}
void update_entry(void *label){}
`,{ruby_init:init,initial_scale:initialScale});
const measures={measure:new NativeFunction(driver.outer_measure,'void',['pointer','pointer','uint']),
    place:new NativeFunction(driver.outer_place,'void',['pointer','pointer','uint']),
    primary:new NativeFunction(driver.base_measure,'void',['pointer','pointer','uint'])};
function caller(fn){let address=null;const h=Interceptor.attach(init,{onEnter(){address=this.returnAddress;}});
    Interceptor.flush();fn(Memory.alloc(0x500),Memory.allocUtf8String('x'),1);h.detach();Interceptor.flush();return address;}
REPORT.native.ruby_measure_return={rva:caller(measures.measure).sub(base).toInt32()};
REPORT.native.ruby_place_return={rva:caller(measures.place).sub(base).toInt32()};
REPORT.native.ruby_base_measure_return={rva:caller(measures.primary).sub(base).toInt32()};
let annotationScale=.85,rubyScale=1,rubyGap=0,rubyOffsetX=0,rubyLineGap=6,bilingualOffsetY=0;
let secondaryColor=[1,1,1],secondaryOpacity=1,enabled=true,failed=false,renderMode='annotation',row=null;
const runtimeFonts=null,nativeBooks=null,scriptIdentities=null,tableIdentities=null,paragraphs=null,fcParagraphs=null;
const TextFactory=RuntimeText,nativeSizeFallbacks=new Map(),inputIdentityDiagnostics=new Map(),dictionary={};
let resolver=null;
let epoch=0,fontGeneration=0,updates=0,writes=0,replayEpoch=-1;
const labels=new Map(),labelCallbacks=new Map();
function translationKey(value){return value.original;}
function recordTiming(){}
function fail(e){errors.push(String(e));}
function ownedRow(p){return row&&row.pointer.equals(p)?row:null;}
function auxiliaryLayer(){return null;}
function inheritAuxiliaryIcons(){}
function activeRewrite(){return null;}
function isLabel(p){return row?.pointer.equals(p);}
function readText(p){return p.add(0x318).readPointer().readUtf8String();}
function enterLabel(p){return {pointer:p};}
function leaveLabel(){}
function restoreTextProjection(){}
function layoutOwnershipChanged(){return false;}
function copyOwnedText(){throw Error('Unexpected changed text during equal-text invalidation');}
""",
        section("function wantedText(", "\nfunction captureMetadata("),
        section("function captureMetadata(", "\nconst nativeTextReset="),
        section("function beginAnnotationLane(", "\nif(REPORT.native.ruby_begin)"),
        section("const rubyContextCallbacks={", "\nif(typeof createNativeMeasure"),
        production_helpers(),
        r"""
function cloneLeaf(fixture) {
    const arena=Memory.alloc(Process.pageSize),code=arena.add(0x100),bytes=new Uint8Array(fixture.bytes);
    let constantOffset=0x800;
    for(const relocation of fixture.relocations){
        let target;
        if(relocation.kind==='table')target=formula.arena.add(0x180);
        else {target=arena.add(constantOffset);target.writeByteArray(relocation.data);constantOffset+=32;}
        new DataView(bytes.buffer).setInt32(relocation.displacement_offset,target.sub(code.add(relocation.instruction_end)).toInt32(),true);
    }
    code.writeByteArray(bytes.buffer);code.add(bytes.length).writeU8(0xc3);Memory.protect(arena,Process.pageSize,'rwx');
    return {arena,code};
}
const originLeaf=cloneLeaf(INPUT.native_origin);
REPORT.native.line_ruby_origin={rva:originLeaf.code.sub(base).toInt32()};
const nativeOrigin=new NativeFunction(originLeaf.code,'void',['pointer','pointer']);
""",
        section("if(REPORT.native.line_ruby_origin)", "\nif(REPORT.native.newline_prepare)"),
        r"""
const nativeGeometry=new CModule(GEOMETRY),nativeAdjust=new NativeFunction(nativeGeometry.adjust_static_ruby,
    'int',['pointer','uint','pointer','uint','pointer'],{scheduling:'exclusive'});
let adjustStaticRuby=nativeAdjust;const geometryStyle=Memory.alloc(28);
const labelSlot=Memory.alloc(Process.pointerSize),parserSlot=Memory.alloc(Process.pointerSize),frameSlot=Memory.alloc(Process.pointerSize);
const registerBridge=new CModule(`
#include <stdint.h>
#include <gum/guminterceptor.h>
typedef struct {uint64_t r15,rbx,rbp;} Saved;
extern void *label_slot,*parser_slot,*frame_slot;
void enter(GumInvocationContext *ic){Saved*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved);GumCpuContext*c=ic->cpu_context;
s->r15=c->r15;s->rbx=c->rbx;s->rbp=c->rbp;c->r15=(uint64_t)(uintptr_t)label_slot;c->rbx=(uint64_t)(uintptr_t)parser_slot;c->rbp=(uint64_t)(uintptr_t)frame_slot;}
void leave(GumInvocationContext *ic){Saved*s=GUM_IC_GET_INVOCATION_DATA(ic,Saved);GumCpuContext*c=ic->cpu_context;c->r15=s->r15;c->rbx=s->rbx;c->rbp=s->rbp;}
`,{label_slot:labelSlot,parser_slot:parserSlot,frame_slot:frameSlot});
const prepare=Interceptor.attach(init,{onEnter:registerBridge.enter,onLeave:registerBridge.leave});
const measure=createNativeMeasure(rubyContextCallbacks,{measurement:base.add(REPORT.native.ruby_measure_return.rva),
    baseMeasurement:base.add(REPORT.native.ruby_base_measure_return.rva),placement:base.add(REPORT.native.ruby_place_return.rva)},fail,nativeParser);
const measureHook=Interceptor.attach(init,{onEnter:measure.onEnter,onLeave:measure.onLeave});Interceptor.flush();
const nativeMeasure=measure,logMeasureFrames=new Map();function observeNativeText(){}
REPORT.native.measure_text={rva:driver.measure_entry.sub(base).toInt32()};
const logMeasure=new NativeFunction(driver.measure_entry,'void',['pointer','pointer','pointer','uint']);
REPORT.native.update={rva:driver.update_entry.sub(base).toInt32()};const labelHooks=Interceptor;
const updateLabel=new NativeFunction(driver.update_entry,'void',['pointer']);
""",
        section("if(REPORT.native.measure_text)", "\nfunction beginAnnotationLane("),
        section("labelHooks.attach(base.add(REPORT.native.update.rva)", "\nrpc.exports ="),
        r"""
function fresh(labelPixels,mode='annotation',active=true,original=INPUT.original,targets=[INPUT.original,INPUT.original]){
    const label=Memory.alloc(0x900),parent=Memory.alloc(0x500),frame=Memory.alloc(0x500);
    label.add(0x300).writeU32(0);label.add(0x304).writeU32(labelPixels);parent.add(0x1c).writeU32(4);
    frame.add(0x3c8).writeS32(0);frame.add(0x3d0).writeS32(labelPixels*4);parent.writeFloat(labelPixels*4);
    labelSlot.writePointer(label);parserSlot.writePointer(parent);frameSlot.writePointer(frame);
    renderMode=mode;enabled=active;resolver=new RuntimeText({pairs:{[original]:targets},plain_pairs:{[original]:targets}});
    row={pointer:label,original,displayed:original,epoch,fontGeneration};const wanted=wantedText(row);row.displayed=wanted;
    label.add(0x318).writePointer(Memory.allocUtf8String(wanted));captureMetadata(row);labels.set(String(label),row);
    return {label,parent,frame,wanted,row};
}
function labelFontPixels(state){return (state.label.add(0x300).readU32()===0?formula.face0:formula.faceLabel).add(0x28).readU32();}
function nativeRubyInput(){initialScale.writeFloat(formula.table.add(0x6a8).readU32()/formula.face0.add(0x28).readU32());}
function primaryMetric(state,pixels){
    formula.table.add(0x578).writeU32(pixels);const p=Memory.alloc(0x500);writeScales(p,state.row.renderSize/labelFontPixels(state));
    formula.run(p,state.label,0);return p.add(0x15c).readFloat()*labelFontPixels(state);
}
function secondaryMetric(state){
    nativeRubyInput();
    const target=Memory.alloc(0x500),text=Memory.allocUtf8String(INPUT.original);
    measures.measure(target,text,4);const measured=target.add(0x15c).readFloat()*labelFontPixels(state);
    state.label.add(0x330).writeU32(0);beginAnnotationLane(state.label,state.parent,'open');
    state.label.add(0x330).writeU32(4);measures.place(target,text,4);
    const placed=target.add(0x15c).readFloat()*labelFontPixels(state);
    state.label.add(0x330).writeU32(8);beginAnnotationLane(state.label,state.parent,'end');
    return {measured,placed};
}
function logMetric(size,scale){
    rubyScale=scale;const state=fresh(size),target=Memory.alloc(0x500),text=Memory.allocUtf8String(INPUT.original);
    nativeRubyInput();
    state.parent.add(0x1ab).writeU8(1);const thread=Process.getCurrentThreadId();
    logMeasureFrames.set(thread,[{pending:true,measuringLabels:[state.label]}]);
    const before=measure.status();logMeasure(state.label,target,text,4);const after=measure.status();logMeasureFrames.delete(thread);
    rubyScale=1;
    return {size,scale,pixels:target.add(0x15c).readFloat()*48,
        fast:after.fastMeasure-before.fastMeasure,slow:after.slow-before.slow,pushes:after.pushes-before.pushes,pops:after.pops-before.pops};
}
function delayedInputs(){
    const out=[];
    function refresh(state,via,expected){
        state.label.add(0x688).writeU8(0);state.label.add(0x689).writeU8(0);
        const changed=textLayoutChanged(state.row,state.label);
        const resetResult=via==='reset'?prepareTextReset(state.label):null;
        if(via==='update')updateLabel(state.label);
        out.push({size:state.row.renderSize,index:state.label.add(0x300).readU32(),ruby:formula.table.add(0x6a8).readU32(),
            via,changed:!!changed,resetResult,dirty:state.label.add(0x689).readU8(),expected,...secondaryMetric(state)});
    }
    for(const via of ['update','reset']){
        formula.faceLabel.add(0x28).writeU32(96);
        for(const size of [18,24]){
            const state=fresh(size);state.label.add(0x300).writeU32(1);refresh(state,via,size===18?14:19);
            state.label.add(0x300).writeU32(0);refresh(state,via,size===18?14:18);
            state.label.add(0x300).writeU32(1);refresh(state,via,size===18?14:19);
        }
        formula.faceLabel.add(0x28).writeU32(24);const state=fresh(18);
        state.label.add(0x300).writeU32(1);refresh(state,via,9);
        state.label.add(0x300).writeU32(0);refresh(state,via,14);
        for(const size of [18,24]){
            formula.table.add(0x6a8).writeU32(18);const state=fresh(size);
            for(const ruby of [9,30,18]){formula.table.add(0x6a8).writeU32(ruby);refresh(state,via,ruby===9?9:size===18?14:ruby===30?19:18);}
        }
    }
    formula.table.add(0x6a8).writeU32(18);formula.faceLabel.add(0x28).writeU32(48);return out;
}
function modeSequence(){
    const state=fresh(18),out=[];
    for(const [mode,active,scale] of [['annotation',true,1],['annotation',true,.5],['primary',true,1],
            ['secondary',true,1],['annotation',false,1],['annotation',true,1],['annotation',true,1]]){
        renderMode=mode;enabled=active;rubyScale=scale;
        state.wanted=wantedText(state.row);state.label.add(0x318).writePointer(Memory.allocUtf8String(state.wanted));
        const metrics=state.row.plan.kind==='ruby'?secondaryMetric(state):null;
        out.push({mode,active,scale,wanted:state.wanted,kind:state.row.plan.kind,small:!!state.row.rubySizing,input_scope:!!state.row.rubySizingInputs,metrics});
    }
    rubyScale=1;return out;
}
function sizingBoundaries(){
    const out=[];
    for(const [size,requested] of [[24,20],[48,41]]){
        formula.table.add(0x6a8).writeU32(requested);
        const state=fresh(size),actual=primaryMetric(state,requested);
        out.push({size,requested,actual,limit:state.row.rubySizing?.limit});
    }
    for(const requested of [19,20,21]){
        annotationScale=requested/24;formula.table.add(0x6a8).writeU32(22);const state=fresh(24);
        out.push({size:24,requested,actual:primaryMetric(state,requested),limit:state.row.rubySizing?.limit});
    }
    annotationScale=.85;formula.table.add(0x6a8).writeU32(18);return out;
}
function excludedScopes(){
    const out=[];
    for(const original of ['<R>成功料理</Rせいこうりょうり>','<S5>成功料理','<s18>成功料理']){
        const state=fresh(18,'annotation',true,original,[original,original]);
        out.push({original,kind:state.row.plan.kind,small:!!state.row.rubySizing});
    }
    const state=fresh(18);state.row.preservePrimaryLayout=true;
    out.push({original:INPUT.original,kind:'mixed',small:!!rubyContextCallbacks.sizing(state.row)});
    return out;
}
function installCapturedGlyphs(state,records,primaryPixels,secondaryPixels){
    const array=Memory.alloc(records.length*Process.pointerSize),manager=Memory.alloc(0x30);
    manager.add(0x20).writePointer(array);state.label.add(0x680).writePointer(manager);state.label.add(0x330).writeU32(records.length);
    for(let i=0;i<records.length;i++){
        const g=records[i],p=Memory.alloc(0xc8);array.add(i*8).writePointer(p);
        // Font quad shape comes from the identical-character capture. The
        // emitted dimensions follow the actual production parser scales;
        // an updated callback therefore changes this seam's visible size.
        const ratio=i<4?primaryPixels/INPUT.provenance.observed_main_pixels:secondaryPixels/INPUT.provenance.observed_secondary_pixels;
        for(const [offset,key] of [[8,'w_0x08'],[0x1c,'h_0x1c'],[0x38,'x_0x38'],[0x3c,'y_0x3c']])
            p.add(offset).writeFloat(g.geometry[key]*(offset===8||offset===0x1c?ratio:1));
        p.add(0xc0).writeU32(g.kind_0xc0);g.color_0x98_0xa4.forEach((v,j)=>p.add(0x98+j*4).writeFloat(v));
    }
    return array;
}
function readGlyphs(array,count){return Array.from({length:count},(_,i)=>{
    const p=array.add(i*8).readPointer();return {x:p.add(0x38).readFloat(),y:p.add(0x3c).readFloat(),w:p.add(8).readFloat(),h:p.add(0x1c).readFloat()};});}
function replayGeometry(fast){
    adjustStaticRuby=fast?nativeAdjust:null;const state=fresh(18);const pixels=primaryMetric(state,15),secondary=secondaryMetric(state);
    const array=installCapturedGlyphs(state,INPUT.bilingual_glyphs,pixels,secondary.placed);finishAnnotationLanes(state.row);
    const once=readGlyphs(array,8);finishAnnotationLanes(state.row);const twice=readGlyphs(array,8);
    return {native_main_pixels:pixels,native_secondary_pixels:secondary,wanted:state.wanted,plan_kind:state.row.plan.kind,
        glyphs:once,same_generation_stable:JSON.stringify(once)===JSON.stringify(twice)};
}
function originCase({size=18,scale=1,margin=INPUT.native_origin.observed_margin,measuring=false,line=0,flags=0,scope='ordinary',labelLeading=7,labelMargin=0}={}){
    rubyScale=scale;
    const state=fresh(size),p=state.parent;
    if(scope==='speaker')state.row.dialogueSpeaker=true;
    if(scope==='mixed')state.row.preservePrimaryLayout=true;
    if(scope==='native_reading')state.row.original='<R>字</Rじ>';
    formula.table.add(0x6a4).writeFloat(margin);
    state.label.add(0x2e8).writeU32(flags);state.label.add(0x2f8).writeFloat(labelLeading);state.label.add(0x2fc).writeFloat(labelMargin);
    const lineInfo=Memory.alloc(24);lineInfo.add(line*12+8).writeU8(1);
    state.label.add(0x660).writePointer(lineInfo);state.label.add(0x668).writeU32(2);
    p.add(0x16c).writeU32(line);p.add(0x1ab).writeU8(measuring?1:0);p.add(4).writeFloat(100);
    nativeOrigin(state.label,p);
    rubyScale=1;
    return {size,scale,margin,measuring,line,flags,scope,labelLeading,labelMargin,origin_before:100,
        origin_after:p.add(4).readFloat(),compensated:p.add(0x1a7).readU8()};
}
rpc.exports.run=()=>{
    const fast=replayGeometry(true),slow=replayGeometry(false),controls=[];
    for(const size of [18,21,24,32,48]){
        const state=fresh(size),s=secondaryMetric(state),match=/<s(\d+)>/.exec(state.wanted),main=primaryMetric(state,match?Number(match[1]):size);
        controls.push({label_size:size,wanted:state.wanted,main_pixels:main,secondary_pixels:s.placed,secondary_main_ratio:s.placed/main});
    }
    const noAnnotation=[];for(const [mode,active] of [['primary',true],['secondary',true],['annotation',false]]){
        const state=fresh(18,mode,active);noAnnotation.push({mode,active,wanted:state.wanted,kind:state.row.plan.kind});
    }
    const originCases=[];
    for(const margin of [-12,-7,0,9])for(const size of [18,21,24,32])for(const measuring of [false,true])
        for(const line of [0,1])originCases.push(originCase({size,margin,measuring,line}));
    for(const scope of ['speaker','mixed','native_reading'])for(const line of [0,1])originCases.push(originCase({scope,line}));
    for(const flags of [8,256])originCases.push(originCase({flags}));
    for(const scale of [.5,.75,1,1.25])originCases.push(originCase({scale}));
    const log=[],draw=[];for(const size of [18,21,24,32])for(const scale of [.5,.75,.9,1,1.25,2]){
        log.push(logMetric(size,scale));rubyScale=scale;draw.push({size,scale,...secondaryMetric(fresh(size))});
    }
    rubyScale=1;
    return {fast,slow,controls,no_annotation:noAnnotation,geometry_paths_equal:JSON.stringify(fast.glyphs)===JSON.stringify(slow.glyphs),
        native_origin:originCases,log_measurement:log,draw_scales:draw,mode_sequence:modeSequence(),sizing_boundaries:sizingBoundaries(),excluded_scopes:excludedScopes(),delayed_inputs:delayedInputs(),
        native_measure:measure.status(),native_parser:nativeParser.status(),errors,
        host:'self-created-hidden-python',game_started:false,game_attached:false};
};
""",
    ]
    return "\n".join(pieces)


def run_host(code):
    host = subprocess.Popen(
        [sys.executable, "-B", "-c", "import time; time.sleep(90)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(code, runtime="v8")
        script.load()
        return script.exports_sync.run()
    finally:
        if session:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/owned-title-layout.json")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text("utf-8"))
    report = run_host(source(fixture))
    report["source_sha256"] = hashlib.sha256(
        (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_bytes()
    ).hexdigest()
    report["fixture_sha256"] = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    report["native_origin_sha256"] = hashlib.sha256(
        bytes(fixture["native_origin"]["bytes"])
    ).hexdigest()
    report["observed"] = fixture["provenance"]
    old = fixture["single_glyphs"]
    main = report["fast"]["glyphs"][: len(old)]
    report["baseline_scale_reproduced"] = (
        report["fast"]["native_main_pixels"] == fixture["provenance"]["observed_main_pixels"]
        and report["fast"]["native_secondary_pixels"]["placed"]
        == fixture["provenance"]["observed_secondary_pixels"]
    )
    report["contracts"] = {
        "no_callback_errors": not report["errors"],
        "secondary_smaller_than_main": all(
            abs(a["h"]) > abs(b["h"]) for a, b in zip(main, report["fast"]["glyphs"][4:])
        ),
        "geometry_paths_equal": report["geometry_paths_equal"],
        "same_generation_stable": report["fast"]["same_generation_stable"]
        and report["slow"]["same_generation_stable"],
        "native_small_first_origin": all(
            item["origin_after"] == 100
            for item in report["native_origin"]
            if item["size"] in (18, 21) and item["scope"] == "ordinary" and item["line"] == 0
        ),
        "native_normal_origin_preserved": all(
            item["origin_after"]
            == (100 if item["measuring"] else 107 if item["line"] else 100 - item["margin"])
            for item in report["native_origin"]
            if item["size"] in (24, 32)
        ),
        "native_later_line_preserved": all(
            item["origin_after"] == (100 if item["measuring"] else 107)
            for item in report["native_origin"]
            if item["scope"] == "ordinary" and item["line"] == 1
        ),
        "log_measurement_matches_draw": all(
            abs(
                item["pixels"]
                - min(
                    18 * item["scale"],
                    14 if item["size"] == 18 else 17 if item["size"] == 21 else 1000,
                )
            )
            < 0.00001
            for item in report["log_measurement"]
        ),
        "normal_log_fast_path_preserved": all(
            item["fast"] == item["pushes"] == item["pops"] == 1 and item["slow"] == 0
            for item in report["log_measurement"]
            if item["size"] in (24, 32)
        ),
        "small_log_uses_owned_callback": all(
            item["fast"] == item["pushes"] == item["pops"] == 0 and item["slow"] == 1
            for item in report["log_measurement"]
            if item["size"] in (18, 21)
        ),
        "measure_place_scale_parity": all(
            abs(draw["measured"] - draw["placed"]) < 0.00001
            and abs(draw["placed"] - log["pixels"]) < 0.00001
            for draw, log in zip(report["draw_scales"], report["log_measurement"])
        ),
        "existing_low_scale_preserved": all(
            abs(item["placed"] - 18 * item["scale"]) < 0.00001
            for item in report["draw_scales"]
            if item["scale"] in (0.5, 0.75)
        ),
        "scales_monotonic": all(
            left["placed"] <= right["placed"]
            for left, right in zip(report["draw_scales"], report["draw_scales"][1:])
            if left["size"] == right["size"]
        ),
        "mode_switch_retires_small_scope": all(
            not item["small"] and not item["input_scope"] and item["kind"] == "plain"
            for item in report["mode_sequence"]
            if not item["active"] or item["mode"] != "annotation"
        ),
        "cold_hot_scale_equal": report["mode_sequence"][0]
        == report["mode_sequence"][-2]
        == report["mode_sequence"][-1],
        "requested_integer_size_is_stable": all(
            item["limit"] == item["requested"] - 1 for item in report["sizing_boundaries"]
        ),
        "existing_origin_scopes_preserved": all(
            item["origin_after"]
            == (100 if item["scope"] in ("speaker", "mixed") else 107 if item["line"] else 112)
            for item in report["native_origin"]
            if item["scope"] != "ordinary"
        ),
        "mixed_reading_and_emphasis_excluded": all(
            not item["small"] for item in report["excluded_scopes"]
        ),
        "delayed_font_and_ruby_inputs": all(
            item["changed"]
            and abs(item["measured"] - item["expected"]) < 0.00001
            and abs(item["placed"] - item["expected"]) < 0.00001
            and (item["dirty"] == 1 if item["via"] == "update" else item["resetResult"] == 1)
            for item in report["delayed_inputs"]
        ),
    }
    report["observed_primary_bottom"] = {
        "single": max(g["geometry"]["y_0x3c"] + abs(g["geometry"]["h_0x1c"]) / 2 for g in old),
        "bilingual": max(g["y"] + abs(g["h"]) / 2 for g in main),
        "diagnostic_only": "Captured final coordinates cannot turn green after an upstream origin repair.",
    }
    report["limits"] = [
        "Native initializer and size arithmetic plus production V8 callbacks execute in a normal C call chain.",
        "Glyph positions are observed engine output replayed through production geometry; complete native measure_text/font parsing is not cloned.",
        "The CAB line_ruby_origin leaf executes against native-shaped fields and observed margin; full measure_text/font placement is not cloned.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "contracts": report["contracts"],
                "controls": report["controls"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not all(report["contracts"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
