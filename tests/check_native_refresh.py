"""Exercise production Update refresh decisions in a self-created Frida host.

The CModule contains only a controllable Update/setter/measure/draw model. It
does not load a game executable or reproduce its renderer.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
AGENT_SOURCE = (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")
DESTINATION = ROOT / "generated/diagnostic-094-native-refresh.json"


def update_callback_source() -> str:
    start = AGENT_SOURCE.index(
        "Interceptor.attach(base.add(REPORT.native.update.rva), {onEnter(args) {"
    )
    return AGENT_SOURCE[start : AGENT_SOURCE.index("\nrpc.exports = {", start)]


def script_source() -> str:
    update_callbacks = update_callback_source()
    return r"""
const native=new CModule(`
int measure(char *label) {
    int contribution=0;
    if (label[0x6b0] & 1) contribution += 12; /* ruby initializer */
    if (label[0x6b0] & 2) contribution += 3;  /* newline correction */
    if (label[0x6b0] & 4) contribution += 5;  /* layered correction */
    *(int *)(label + 0x6d0) = contribution;
    (*(int *)(label + 0x6d4))++;
    if (label[0x6e0]) {
        (*(int *)(label + 0x6e4))++;
        *(int *)(label + 0x6ec) = contribution;
        *(int *)(label + 0x6f8) = *(int *)(label + 0x334);
    } else {
        (*(int *)(label + 0x6e8))++;
        *(int *)(label + 0x6f0) = contribution;
        *(int *)(label + 0x6f4) = *(int *)(label + 0x334);
    }
    label[0x6b0] = 0;
    return contribution;
}
void draw(char *label) { (*(int *)(label + 0x6d8))++; }
void setter(char *label, char *text) {
    *(char **)(label + 0x318) = text;
    if (label[0x6b1]) *(unsigned int *)(label + 0x334) = 180;
    /* Model a setter's nested native measuring work. It deliberately does
       not mark 0x689: Update itself must request the later outer pass. */
    label[0x6e0] = 1; measure(label); label[0x6e0] = 0;
}
void reset_text(char *label) { *(float *)(label + 0x378) = 0.0f; (*(int *)(label + 0x6dc))++; }
int update(char *label) {
    if (label[0x689]) { label[0x689] = 0; measure(label); }
    if (label[0x688]) { label[0x688] = 0; draw(label); }
    return *(int *)(label + 0x6d0);
}
`);
const label=Memory.alloc(0x800),errors=[],labels=new Map();
const base=ptr(0),REPORT={native:{update:{rva:native.update}},diagnostics:false};
let epoch=100,replayEpoch=-1,updates=0,failed=false,writes=0,immediateWrites=0,wanted='';
let setterEnters=0,setterLeaves=0,measureEnters=0,measureLeaves=0,drawEnters=0,drawLeaves=0;
const setter=new NativeFunction(native.setter,'void',['pointer','pointer']);
const resetText=new NativeFunction(native.reset_text,'void',['pointer']);
const update=new NativeFunction(native.update,'int',['pointer']);
function activeRewrite(){return false;}
function isLabel(p){return p.equals(label);}
function enterLabel(p){return p.equals(label)?{pointer:p}:null;}
function leaveLabel(){ }
function readText(p){return p.add(0x318).readPointer().readUtf8String();}
function remember(p,text){const row={pointer:p,original:text,displayed:text,epoch:-1,plan:{kind:'plain'}};labels.set(String(p),row);return row;}
function wantedText(){return wanted;}
function copyOwnedText(row,text){
  setter(row.pointer,Memory.allocUtf8String(text));
  if(readText(row.pointer)!==text)throw Error('fixture setter did not retain text');
  row.displayed=text;writes++;
}
function captureMetadata(row){row.renderSize=row.pointer.add(0x304).readU32();row.metadata={flags:row.pointer.add(0x2e8).readU32()};}
function fail(error){failed=true;errors.push(String(error));}
const dictionary=Object.create(null);
const attach=Interceptor.attach.bind(Interceptor);
attach(native.setter,{onEnter(){setterEnters++;},onLeave(){setterLeaves++;}});
attach(native.measure,{onEnter(args){measureEnters++;args[0].add(0x6b0).writeU8(7);},onLeave(){measureLeaves++;}});
attach(native.draw,{onEnter(){drawEnters++;},onLeave(){drawLeaves++;}});
(function(Interceptor){
__UPDATE_CALLBACKS__
})(Interceptor);
Interceptor.flush();
function check(value,message){if(!value)throw new Error(message);}
function counters(){return {setter:{enter:setterEnters,leave:setterLeaves},measure:{enter:measureEnters,leave:measureLeaves,body:label.add(0x6d4).readS32(),setterPass:label.add(0x6e4).readS32(),formalPass:label.add(0x6e8).readS32(),setterContribution:label.add(0x6ec).readS32(),formalContribution:label.add(0x6f0).readS32(),formalTotal:label.add(0x6f4).readS32(),setterTotal:label.add(0x6f8).readS32()},draw:{enter:drawEnters,leave:drawLeaves,body:label.add(0x6d8).readS32()},reset:label.add(0x6dc).readS32()};}
function zero(){setterEnters=setterLeaves=measureEnters=measureLeaves=drawEnters=drawLeaves=0;}
function prepare(config){
  zero();labels.clear();Object.keys(dictionary).forEach(key=>delete dictionary[key]);
  epoch=100;replayEpoch=-1;wanted=config.wanted;writes=0;immediateWrites=0;errors.length=0;failed=false;
  label.add(0x318).writePointer(Memory.allocUtf8String(config.current));
  label.add(0x304).writeU32(22);label.add(0x2e8).writeU32(config.flags||0);
  label.add(0x334).writeU32(config.total||90);label.add(0x378).writeFloat(config.progress||0);
  label.add(0x688).writeU8(0);label.add(0x689).writeU8(0);label.add(0x6b0).writeU8(0);label.add(0x6b1).writeU8(config.expandTotal?1:0);label.add(0x6d0).writeS32(-1);
  label.add(0x6d4).writeS32(0);label.add(0x6d8).writeS32(0);label.add(0x6dc).writeS32(0);
  label.add(0x6e0).writeU8(0);label.add(0x6e4).writeS32(0);label.add(0x6e8).writeS32(0);
  for(const off of [0x6ec,0x6f0,0x6f4,0x6f8])label.add(off).writeS32(-1);
  const row={pointer:label,original:config.original||'source',displayed:config.displayed??config.current,epoch:-1,plan:{kind:config.kind||'plain'}};
  labels.set(String(label),row);
  if(config.replay){dictionary[row.original]=[row.original,wanted];replayEpoch=epoch;}
  return row;
}
function runCase(config){
  const row=prepare(config),beforeProgress=label.add(0x378).readFloat();
  const first=update(label),afterFirst=counters(),firstText=readText(label),firstProgress=label.add(0x378).readFloat(),firstFlags=label.add(0x2e8).readU32(),dirtyAfterFirst=[label.add(0x688).readU8(),label.add(0x689).readU8()];
  const second=update(label),afterSecond=counters();
  return {name:config.name,kind:row.plan.kind,replay:!!config.replay,first,second,firstText,firstProgress,beforeProgress,firstFlags,
    dirtyAfterFirst,contribution:label.add(0x6d0).readS32(),totalAfterFirst:label.add(0x334).readU32(),afterFirst,afterSecond,
    row:{epoch:row.epoch,renderSize:row.renderSize,metadataFlags:row.metadata?.flags},errors:[...errors]};
}
function runCold(){
  prepare({name:'cold',current:'old',displayed:'old',wanted:'new',kind:'ruby'});
  setter(label,Memory.allocUtf8String('new'));new NativeFunction(native.draw,'void',['pointer'])(label);
  return {finalContribution:label.add(0x6d0).readS32(),counters:counters(),text:readText(label)};
}
function contract(caseResult,needsSetter,failures){
  const c=caseResult.afterFirst,n=caseResult.afterSecond;
  if(c.measure.enter!==1||c.measure.leave!==1||c.measure.body!==(needsSetter?2:1)||c.draw.enter!==1||c.draw.leave!==1||c.draw.body!==1)
    failures.push({case:caseResult.name,assertion:'exactly_one_outer_measure_and_draw_after_update',actual:c,needsSetter});
  if(n.measure.enter!==c.measure.enter||n.draw.enter!==c.draw.enter||n.setter.enter!==c.setter.enter)
    failures.push({case:caseResult.name,assertion:'next_frame_does_not_repeat_refresh',first:c,second:n});
  if(needsSetter&&(c.setter.enter!==0||c.setter.leave!==0))
    failures.push({case:caseResult.name,assertion:'nested_setter_hook_suppressed',actual:c.setter});
  if(c.measure.setterPass!==(needsSetter?1:0)||c.measure.formalPass!==1||c.measure.formalContribution!==20||c.measure.setterContribution!==(needsSetter?0:-1))
    failures.push({case:caseResult.name,assertion:'setter_and_formal_measure_contributions_are_separate',actual:c.measure,needsSetter});
  if(caseResult.dirtyAfterFirst[0]!==0||caseResult.dirtyAfterFirst[1]!==0)
    failures.push({case:caseResult.name,assertion:'native_update_consumes_dirty_flags',actual:caseResult.dirtyAfterFirst});
  if(caseResult.errors.length)failures.push({case:caseResult.name,assertion:'callback_error',errors:caseResult.errors});
}
rpc.exports={run(){
  const cases=[
    runCase({name:'changed',current:'old',displayed:'old',wanted:'new',kind:'ruby'}),
    runCase({name:'replay',current:'translated',displayed:'translated',wanted:'translated',replay:true,kind:'ruby'}),
    runCase({name:'geometry-ruby',current:'translated',displayed:'translated',wanted:'translated',kind:'ruby'}),
    runCase({name:'geometry-layered',current:'translated',displayed:'translated',wanted:'translated',kind:'layered'}),
    runCase({name:'changed-animated-paused',current:'old',displayed:'old',wanted:'new',kind:'ruby',flags:0x14,total:90,progress:45,expandTotal:true})
  ],cold=runCold(),failures=[];
  contract(cases[0],true,failures);contract(cases[1],true,failures);contract(cases[2],false,failures);contract(cases[3],false,failures);contract(cases[4],true,failures);
  const animated=cases[4];
  if(animated.firstProgress!==90||animated.totalAfterFirst!==180||animated.firstProgress/animated.totalAfterFirst!==animated.beforeProgress/90||(animated.firstFlags&0x10)===0||animated.afterFirst.measure.formalTotal!==180)
    failures.push({case:animated.name,assertion:'paused_animation_fraction_restored_after_synthetic_total_growth',before:animated.beforeProgress,beforeTotal:90,after:animated.firstProgress,afterTotal:animated.totalAfterFirst,flags:animated.firstFlags,measure:animated.afterFirst.measure});
  if(cold.text!=='new'||cold.finalContribution!==20||cold.counters.setter.enter!==1||cold.counters.measure.enter!==1||cold.counters.draw.enter!==1||cold.counters.measure.setterPass!==1||cold.counters.measure.formalPass!==0||cold.counters.measure.setterContribution!==20)
    failures.push({case:'cold',assertion:'cold_fixture_measure_and_draw',cold});
  for(const result of cases)if(result.contribution!==cold.finalContribution)
    failures.push({case:result.name,assertion:'cold_hot_final_geometry_equal_in_fixture',cold:cold.finalContribution,hot:result.contribution});
  return {frida:Frida.version,host:'self-created-hidden-python',game_attached:false,game_started:false,
    source:'production Update onEnter/onLeave callbacks extracted verbatim',
    fixture_boundary:'CModule models a dirty-gated outer measure/draw and configurable ruby/newline/layered contribution; it is not a game renderer.',
    cold,cases,contract_failures:failures,all_passed:failures.length===0};
}};
""".replace("__UPDATE_CALLBACKS__", update_callbacks)


def main() -> None:
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
        DESTINATION.write_text(json.dumps(report, indent=2) + "\n", "utf-8")
        print(json.dumps(report, indent=2), flush=True)
        assert report["all_passed"], f"contract failures recorded in {DESTINATION}"
    finally:
        if session is not None:
            session.detach()
        host.terminate()
        host.wait(timeout=5)


if __name__ == "__main__":
    main()
