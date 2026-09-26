"""Compile and differentially check static-ruby C geometry in an offline Frida host."""

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
C_SOURCE = (
    (ROOT / "sora_bilingual/game/scripts/native_geometry.js")
    .read_text("utf-8")
    .split("String.raw`", 1)[1]
    .rsplit("`;", 1)[0]
)
AGENT_SOURCE = (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")
REPORT_PATH = ROOT / "generated/diagnostic-082-native-geometry.json"


def production_helpers():
    start = AGENT_SOURCE.index("function finishStaticRuby(")
    end = AGENT_SOURCE.index("\nfunction copyOwnedText", start)
    helpers = AGENT_SOURCE[start:end]
    if "function finishAnnotationLanes(" not in helpers:
        raise RuntimeError("native_agent.js no longer contains the production geometry helpers")
    return helpers


def production_harness():
    return (
        """return (function(){
let adjustStaticRuby=nativeAdjust,geometryStyle=styleMemory;
let annotationScale=1,rubyGap=3,rubyOffsetX=0,secondaryColor=[.9,.9,.9],secondaryOpacity=1,bilingualOffsetY=0;
const timings={geometry:{count:0,totalMs:0,maxMs:0,over8Ms:0},geometryNative:{count:0,totalMs:0,maxMs:0,over8Ms:0}};
function recordTiming(stage,start){if(start===undefined)return;const row=timings[stage],ms=Date.now()-start;row.count++;row.totalMs+=ms;row.maxMs=Math.max(row.maxMs,ms);if(ms>=8)row.over8Ms++;}
"""
        + production_helpers()
        + """
return {
  finishStaticRuby,finishAnnotationLanes,
  setFastPath(enabled){adjustStaticRuby=enabled?nativeAdjust:null;},
  setStyle(style){rubyGap=style[0];rubyOffsetX=style[1];secondaryColor=[style[2],style[3],style[4]];secondaryOpacity=style[5];bilingualOffsetY=style[6];}
};
})();"""
    )


def script_source():
    return """
const geometrySource=%s;
const productionHarnessSource=%s;
const module=new CModule(geometrySource);
const adjust=new NativeFunction(module.adjust_static_ruby,'int',['pointer','uint','pointer','uint','pointer'],{scheduling:'exclusive'});
const production=Function('nativeAdjust','styleMemory',productionHarnessSource)(adjust,Memory.alloc(7*4));
const kernel=Process.getModuleByName('kernel32.dll');
const counter=Memory.alloc(8),frequency=Memory.alloc(8);
const queryCounter=new NativeFunction(kernel.getExportByName('QueryPerformanceCounter'),'int',['pointer'],{scheduling:'exclusive'});
new NativeFunction(kernel.getExportByName('QueryPerformanceFrequency'),'int',['pointer'])(frequency);
function nowMs(){queryCounter(counter);return counter.readU64().toNumber()*1000/frequency.readU64().toNumber();}
function f32(value){return new Float32Array([value])[0];}
function fail(message){throw Error(message);}
function approxEqual(a,b){return Object.is(a,b)||(Number.isNaN(a)&&Number.isNaN(b));}
function makeGlyph(data){
  const block=Memory.alloc(0xd4),bytes=new Uint8Array(0xd4);bytes.fill(0xa5);block.writeByteArray(bytes);
  const glyph=block.add(8);glyph.add(0x38).writeFloat(data.x);glyph.add(0x3c).writeFloat(data.y);
  glyph.add(0x08).writeFloat(data.w);glyph.add(0x1c).writeFloat(data.h);glyph.add(0xc0).writeU32(data.kind);
  glyph.add(0x98).writeFloat(data.r);glyph.add(0x9c).writeFloat(data.g);glyph.add(0xa0).writeFloat(data.b);glyph.add(0xa4).writeFloat(data.a);
  return {block,glyph};
}
function bytes(pointer,length){return Array.from(new Uint8Array(pointer.readByteArray(length)));}
function build(input){
  const records=input.glyphs.map(makeGlyph),array=Memory.alloc(Math.max(1,input.glyphs.length)*Process.pointerSize);
  records.forEach((record,index)=>array.add(index*Process.pointerSize).writePointer(record.glyph));
  const ranges=Memory.alloc(Math.max(1,input.ranges.length)*4),style=Memory.alloc(7*4);
  input.ranges.forEach((value,index)=>ranges.add(index*4).writeU32(value));
  input.style.forEach((value,index)=>style.add(index*4).writeFloat(value));
  return {records,array,ranges,style};
}
function snapshot(records){return records.map(record=>bytes(record.block,0xd4));}
function fieldValues(records){return records.map(({glyph})=>({
  x:glyph.add(0x38).readFloat(),y:glyph.add(0x3c).readFloat(),w:glyph.add(0x08).readFloat(),h:glyph.add(0x1c).readFloat(),
  r:glyph.add(0x98).readFloat(),g:glyph.add(0x9c).readFloat(),b:glyph.add(0xa0).readFloat(),a:glyph.add(0xa4).readFloat(),kind:glyph.add(0xc0).readU32()
}));}
function reference(input){
  const out=input.glyphs.map(g=>({
    ...g,x:f32(g.x),y:f32(g.y),w:f32(g.w),h:f32(g.h),
    r:f32(g.r),g:f32(g.g),b:f32(g.b),a:f32(g.a)
  })),style=input.style;
  for(let lane=0;lane<input.ranges.length;lane+=3){
    const primaryStart=input.ranges[lane],secondaryStart=input.ranges[lane+1],secondaryEnd=input.ranges[lane+2];
    const havePrimary=primaryStart<secondaryStart;
    let primary=null;
    if(havePrimary){
      for(let i=primaryStart;i<secondaryStart;i++){
        const g=out[i];if(g.kind===1)continue;
        const width=Math.abs(g.w),height=Math.abs(g.h),edge={left:g.x-width/2,top:g.y-height/2};
        primary=primary?{left:Math.min(primary.left,edge.left),top:Math.min(primary.top,edge.top)}:edge;
      }
      if(!primary)continue;
    }
    let secondary={left:Infinity,bottom:-Infinity};
    for(let i=secondaryStart;i<secondaryEnd;i++){
      const g=out[i],width=Math.abs(g.w),height=Math.abs(g.h);
      secondary.left=Math.min(secondary.left,g.x-width/2);secondary.bottom=Math.max(secondary.bottom,g.y+height/2);
    }
    const dx=primary?primary.left+style[1]-secondary.left:0,dy=primary?primary.top-style[0]-secondary.bottom:0;
    for(let i=secondaryStart;i<secondaryEnd;i++){
      const g=out[i];
      if(primary){g.x=f32(g.x+dx);g.y=f32(g.y+dy);}
      g.r=f32(g.r*style[2]);g.g=f32(g.g*style[3]);g.b=f32(g.b*style[4]);g.a=f32(g.a*style[5]);
    }
  }
  if(style[6]!==0)for(const g of out)g.y=f32(g.y+style[6]);
  return out;
}
function compare(actual,expected,label){
  if(actual.length!==expected.length)fail(label+': glyph count');
  for(let i=0;i<actual.length;i++)for(const key of ['x','y','w','h','r','g','b','a','kind']){
    if(!approxEqual(actual[i][key],expected[i][key]))fail(label+': glyph '+i+' '+key+' expected '+expected[i][key]+' got '+actual[i][key]);
  }
}
function checkCanaries(before,after,label){
  const allowed=new Set();for(let i=0x38+8;i<0x40+8;i++)allowed.add(i);for(let i=0x98+8;i<0xa8+8;i++)allowed.add(i);
  for(let glyph=0;glyph<before.length;glyph++)for(let i=0;i<before[glyph].length;i++){
    if(before[glyph][i]!==after[glyph][i]&&!allowed.has(i))fail(label+': modified byte '+i+' outside x/y/RGBA');
    if((i<8||i>=0xcc)&&after[glyph][i]!==0xa5)fail(label+': guard canary '+i);
  }
}
function runCase(label,input){
  const native=build(input),before=snapshot(native.records),expected=reference(input);
  const status=adjust(native.array,input.glyphs.length,native.ranges,input.ranges.length/3,native.style);
  if(status!==0)fail(label+': native status '+status);
  const actual=fieldValues(native.records);compare(actual,expected,label);checkCanaries(before,snapshot(native.records),label);
  return actual;
}
function checkRejected(label,input,mutate){
  const native=build(input);mutate(native);const before=snapshot(native.records);
  const status=adjust(native.array,input.glyphs.length,native.ranges,input.ranges.length/3,native.style);
  if(status===0)fail(label+': accepted invalid input');
  const after=snapshot(native.records);for(let i=0;i<before.length;i++)for(let j=0;j<before[i].length;j++)if(before[i][j]!==after[i][j])fail(label+': partial write');
  return status;
}
function checkRejectedCall(label,input,count,laneCount){
  const native=build(input),before=snapshot(native.records);
  const status=adjust(native.array,count,native.ranges,laneCount,native.style);
  if(status===0)fail(label+': accepted invalid ABI boundary');
  const after=snapshot(native.records);for(let i=0;i<before.length;i++)for(let j=0;j<before[i].length;j++)if(before[i][j]!==after[i][j])fail(label+': partial write');
  return status;
}
function setProductionStyle(style){
  production.setStyle(style);
}
function productionState(input){
  const native=build(input),label=Memory.alloc(0x700),layout=Memory.alloc(0x28);
  label.add(0x330).writeU32(input.glyphs.length);label.add(0x680).writePointer(layout);layout.add(0x20).writePointer(native.array);
  const glyphLanes=[];for(let i=0;i<input.ranges.length;i+=3)glyphLanes.push({primaryStart:input.ranges[i],start:input.ranges[i+1],end:input.ranges[i+2]});
  return {native,label,layout,row:{pointer:label,plan:{kind:'ruby'},glyphLanes,laneCount:-1,laneUnits:-1,lanesDirty:true}};
}
function sameBytes(left,right,label){
  for(let i=0;i<left.length;i++)for(let j=0;j<left[i].length;j++)if(left[i][j]!==right[i][j])fail(label+': byte '+i+'/'+j);
}
function runProduction(label,input,useNative){
  setProductionStyle(input.style);production.setFastPath(useNative);
  const state=productionState(input),before=snapshot(state.native.records);
  production.finishAnnotationLanes(state.row);
  const first=snapshot(state.native.records);checkCanaries(before,first,label+' first');
  production.finishAnnotationLanes(state.row);
  const second=snapshot(state.native.records);sameBytes(first,second,label+' same generation');
  return {fields:fieldValues(state.native.records),bytes:first};
}
function runNewParseGeneration(label,input){
  setProductionStyle(input.style);production.setFastPath(true);
  const state=productionState(input);production.finishAnnotationLanes(state.row);
  const parsed=productionState(input),before=snapshot(parsed.native.records);
  state.layout.add(0x20).writePointer(parsed.native.array);
  state.row.glyphLanes=parsed.row.glyphLanes;state.row.laneCount=-1;state.row.laneUnits=-1;state.row.lanesDirty=true;
  production.finishAnnotationLanes(state.row);
  const result=snapshot(parsed.native.records);checkCanaries(before,result,label);
  return {fields:fieldValues(parsed.native.records),bytes:result};
}
function verifyProductionGates(input){
  const gates=[['animated',row=>row.animated=true],['preserve-primary',row=>row.preservePrimaryLayout=true],['layered',row=>row.glyphLanes[0].layer=true]];
  const statuses={};production.setFastPath(true);setProductionStyle(input.style);
  for(const [label,configure] of gates){
    const state=productionState(input),before=snapshot(state.native.records);configure(state.row);
    if(production.finishStaticRuby(state.row,state.native.array,input.glyphs.length))fail('fast path accepted '+label);
    sameBytes(before,snapshot(state.native.records),'gate '+label);statuses[label]='fallback';
  }
  return statuses;
}
function productionBatch(input,useNative,rounds){
  setProductionStyle(input.style);production.setFastPath(useNative);
  const states=[];for(let i=0;i<rounds;i++)states.push(productionState(input));
  const start=nowMs();for(const state of states)production.finishAnnotationLanes(state.row);return nowMs()-start;
}
rpc.exports={run(){
  const base={glyphs:[
    {x:10.25,y:20.5,w:-6.5,h:8.25,kind:0,r:.8,g:.6,b:.4,a:.9},
    {x:18.5,y:20,w:4,h:7,kind:1,r:.7,g:.5,b:.3,a:.8},
    {x:101,y:80,w:-5,h:6,kind:0,r:.9,g:.8,b:.7,a:.6},
    {x:110,y:78,w:9,h:5,kind:1,r:.4,g:.3,b:.2,a:.5},
    {x:66,y:42,w:3,h:4,kind:0,r:.2,g:.4,b:.6,a:.8},
    {x:-12,y:8,w:-2,h:-3,kind:0,r:.25,g:.5,b:.75,a:1},
    {x:88,y:-5,w:7,h:2,kind:0,r:.1,g:.2,b:.3,a:.4}
  ],ranges:[0,2,4,5,5,6],style:[3.25,-1.5,.5,.25,1,.75,2.5]};
  runCase('multiple-lane-negative-width-and-unowned',base);
  const hdrOwnership={...base,glyphs:base.glyphs.map(g=>({...g}))};
  hdrOwnership.glyphs[0].r=1.25;hdrOwnership.glyphs[0].g=1.5;hdrOwnership.glyphs[6].b=1.75;hdrOwnership.glyphs[6].a=1.25;
  runCase('primary-and-unowned-hdr-colours-with-group-offset',hdrOwnership);
  runCase('style-extremes',{...base,style:[0,4,0,1,.125,0,-3]});
  runCase('primary-icons-have-no-bounds',{glyphs:base.glyphs.slice(0,4),ranges:[0,2,4],style:base.style});
  const invalidRange=checkRejected('invalid-range',base,native=>native.ranges.add(8).writeU32(1));
  const invalidColor=checkRejected('invalid-color',base,native=>native.style.add(8).writeFloat(1.25));
  const invalidSecondaryColor=checkRejected('invalid-secondary-color',base,native=>native.records[2].glyph.add(0x98).writeFloat(1.25));
  const nullGlyph=checkRejected('null-glyph',base,native=>native.array.add(Process.pointerSize).writePointer(ptr(0)));
  const oversizeCount=checkRejectedCall('oversize-count',base,32769,base.ranges.length/3);
  const oversizeLanes=checkRejectedCall('oversize-lanes',base,base.glyphs.length,base.glyphs.length+1);
  const productionBlockRead=runProduction('production-block-read',hdrOwnership,false);
  const productionNative=runProduction('production-cmodule',hdrOwnership,true);
  compare(productionNative.fields,productionBlockRead.fields,'production helper C versus block read');
  sameBytes(productionNative.bytes,productionBlockRead.bytes,'production helper C versus block read');
  const nextParse=runNewParseGeneration('production-new-parse',hdrOwnership);
  sameBytes(nextParse.bytes,productionNative.bytes,'production new parse generation');
  const fastPathGates=verifyProductionGates(base);
  const benchGlyphs=[],benchRanges=[];for(let lane=0;lane<12;lane++){const start=benchGlyphs.length;for(let i=0;i<16;i++)benchGlyphs.push({x:i*7,y:30,w:i%%3===0?-6:6,h:8,kind:i===3?1:0,r:.8,g:.7,b:.6,a:.9});for(let i=0;i<16;i++)benchGlyphs.push({x:120+i*5,y:60,w:5,h:4,kind:i===2?1:0,r:.7,g:.6,b:.5,a:.8});benchRanges.push(start,start+16,start+32);}
  const benchmark={glyphs:benchGlyphs,ranges:benchRanges,style:[3,1,.8,.6,.4,.75,0]},rounds=120;
  const nativeMs=productionBatch(benchmark,true,rounds),blockReadMs=productionBatch(benchmark,false,rounds);
  return {all_passed:true,differential_cases:4,ownership:{primary_and_unowned_hdr_colours:'accepted and unchanged while groupOffsetY changes y',invalid_secondary_colour:'rejected before any glyph write'},production_helper:{source:'current native_agent.js finishStaticRuby + finishAnnotationLanes',same_generation_guard:true,new_parse_generation:true,fast_path_gates:fastPathGates},rejected_statuses:{invalid_range:invalidRange,invalid_color:invalidColor,invalid_secondary_color:invalidSecondaryColor,null_glyph:nullGlyph,oversize_count:oversizeCount,oversize_lanes:oversizeLanes},benchmark:{comparison:'same production helper; CModule fast path enabled versus production JS block-read fallback',scheduling:'exclusive',glyphs:benchGlyphs.length,lanes:benchRanges.length/3,rounds,native_cmodule_ms:nativeMs,production_js_block_read_ms:blockReadMs,native_cmodule_per_batch_ms:nativeMs/rounds,production_js_block_read_per_batch_ms:blockReadMs/rounds},game_started:false,game_attached:false,host:'self-created-hidden-python',runtime:'frida-v8-cmodule'};
}};
""" % (json.dumps(C_SOURCE), json.dumps(production_harness()))


def main():
    host = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        agent = session.create_script(script_source(), runtime="v8")
        agent.load()
        report = agent.exports_sync.run()
        assert report["all_passed"]
        REPORT_PATH.parent.mkdir(exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
