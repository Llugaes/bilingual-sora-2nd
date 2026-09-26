"""Regression for production ruby compensation under Frida nested calls.

The C fixture implements the verified one-shot parser+0x1a7 compensation
branch, including its persistent native flag. It is not the game renderer:
the only attached target is a hidden Python helper created by this script.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import frida


ROOT = Path(__file__).resolve().parents[1]
AGENT_SOURCE = (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")
DESTINATION = ROOT / "generated/diagnostic-093-reentry-regression.json"


def hook_source(name: str, following: str) -> str:
    start = AGENT_SOURCE.index(f"if(REPORT.native.{name}) Interceptor.attach(")
    return AGENT_SOURCE[start : AGENT_SOURCE.index(following, start)]


def script_source() -> str:
    hooks = "".join(
        (
            hook_source("ruby_begin", "// Update rebuilds"),
            hook_source("ruby_compensate", "if(REPORT.native.ruby_end)"),
            hook_source("ruby_end", "if(REPORT.native.parse_text)"),
        )
    )
    return r"""
const markers=new CModule(`
int begin_marker(char *label, char *parser) { return label[0] + parser[0] + 7; }
int compensate_marker(char *label, char *parser) { return label[1] + parser[1] + 13; }
int end_marker(char *label, char *parser) { return label[2] + parser[2] + 17; }
int update_marker(int x) { return x + 19; }
`);
const native=new CModule(`
extern int begin_marker(char *, char *);
extern int compensate_marker(char *, char *);
extern int end_marker(char *, char *);
float layout(char *label, char *parser) {
    int ignored = begin_marker(label, parser);
    /* 0x586f49: bit 8 permits only the primary body. */
    parser[0x1ac] = (char)!(*(unsigned int *)(label + 0x2e8) & 8);
    ignored += compensate_marker(label, parser);
    /* 0x587253: compensation is consumed once and stays set until newline. */
    if (!parser[0x1a7]) {
        *(float *)(parser + 4) -= 6.0f;
        *(float *)(parser + 0x1b8) += 12.0f;
        *(float *)(parser + 0x1bc) += 12.0f;
        *(float *)(parser + 0x1c0) += 12.0f;
        *(float *)(parser + 0x1c4) += 12.0f;
        parser[0x1a7] = 1;
    }
    ignored += end_marker(label, parser);
    return *(float *)(parser + 0x1c4) + (ignored == -123456 ? 1.0f : 0.0f);
}
`,{begin_marker:markers.begin_marker,compensate_marker:markers.compensate_marker,end_marker:markers.end_marker});
const label=Memory.alloc(0x700),parser=Memory.alloc(0x300),errors=[];
let row={plan:{kind:'ruby'},reserveRubyHeight:true};
let rubyBeginCalls=0,compensateCalls=0,nestedResult=null;
const attach=Interceptor.attach.bind(Interceptor);
const base=ptr(0),REPORT={native:{
  ruby_begin:{rva:markers.begin_marker},ruby_compensate:{rva:markers.compensate_marker},ruby_end:{rva:markers.end_marker}
}};
const rubyPermissions=new Map(),compensation=new Map();
function ownedRow(p){return p.equals(label)?row:null;}
function beginAnnotationLane(_label,_parser,phase){if(phase==='open')rubyBeginCalls++;else if(phase==='end')compensateCalls++;}
function auxiliaryLayer(){return row?.plan.kind==='layered'?{row}:null;}
function fail(error){errors.push(String(error));}
// Actual production callbacks; only R15/RBX are bridged to fixture arguments.
const bridge={attach(address,callback){return attach(address,{
  onEnter(args){callback.onEnter.call({context:{r15:args[0],rbx:args[1]}});}
});}};
(function(Interceptor){
__PRODUCTION_HOOKS__
})(bridge);
const layout=new NativeFunction(native.layout,'float',['pointer','pointer']);
const update=new NativeFunction(markers.update_marker,'int',['int']);
attach(markers.update_marker,{onEnter(){nestedResult=layout(label,parser);}});
Interceptor.flush();
function check(value,message){if(!value)throw new Error(message);}
function seed(flags,measuring){
  label.add(0x2e8).writeU32(flags);parser.add(4).writeFloat(0);
  for(const off of [0x1b8,0x1bc,0x1c0])parser.add(off).writeFloat(0);
  parser.add(0x1c4).writeFloat(84);
  parser.add(0x1a7).writeU8(0);parser.add(0x1ab).writeU8(measuring?1:0);parser.add(0x1ac).writeU8(0);
}
function sample(flags,measuring,nested){
  seed(flags,measuring);const beginBefore=rubyBeginCalls,compensateBefore=compensateCalls;
  const bottom=nested?(update(1),nestedResult):layout(label,parser);
  const result={bottom,y:parser.add(4).readFloat(),ruby:!!parser.add(0x1ac).readU8(),
    compensationFlag:parser.add(0x1a7).readU8(),flags:label.add(0x2e8).readU32(),
    rubyBeginCallbacks:rubyBeginCalls-beginBefore,compensationCallbacks:compensateCalls-compensateBefore};
  check(rubyPermissions.size===0,'permission scope leaked');check(compensation.size===0,'compensation scope leaked');
  return result;
}
function sameMeasurement(a,b){return a.bottom===b.bottom&&a.y===b.y&&a.ruby===b.ruby&&a.compensationFlag===b.compensationFlag&&a.flags===b.flags;}
function legacyPermission(flags,cold,hot,draw,failures,caseName){
  const measuredAllowed=(flags&8)===0;
  for(const [phase,value,expected] of [['cold',cold,measuredAllowed],['hot',hot,measuredAllowed],['draw',draw,true]]) {
    if(value.ruby!==expected)failures.push({case:caseName,assertion:'legacy_flag_8_permission',phase,expected,actual:value.ruby});
    if(value.flags!==flags)failures.push({case:caseName,assertion:'flags_restored',phase,expected:flags,actual:value.flags});
  }
}
rpc.exports={run(){
  const result={frida:Frida.version,game_attached:false,game_started:false,host:'self-created-hidden-python',
    source:'production ruby_begin/ruby_compensate/ruby_end callbacks; CModule models native 0x587253 one-shot parser+0x1a7 compensation',
    fixture_boundary:'Synthetic CModule validates callback reentry and state restoration only; it does not load or call a game module.',
    cases:[],contract_failures:[]};
  for(const config of [{kind:'ruby',reserveRubyHeight:true},{kind:'ruby',reserveRubyHeight:false},{kind:'layered',reserveRubyHeight:false}]) {
    for(const flags of [0,8,12,72]) {
      row={plan:{kind:config.kind},reserveRubyHeight:config.reserveRubyHeight};
      const cold=sample(flags,true,false),hot=sample(flags,true,true),draw=sample(flags,false,false);
      const name=`${config.kind}/reserve=${config.reserveRubyHeight}/flags=${flags}`;
      result.cases.push({kind:config.kind,reserveRubyHeight:config.reserveRubyHeight,flags,cold,hot,draw});
      if(cold.rubyBeginCallbacks!==1||cold.compensationCallbacks!==1||hot.rubyBeginCallbacks!==0||hot.compensationCallbacks!==0)
        result.contract_failures.push({case:name,assertion:'fixture_exercises_nested_suppression',cold,hot});
      legacyPermission(flags,cold,hot,draw,result.contract_failures,name);
      if(!sameMeasurement(cold,hot))result.contract_failures.push({case:name,assertion:'measurement_source_independent_compensation',cold,hot});
      if(draw.bottom!==84||draw.y!==0||draw.compensationFlag!==0)
        result.contract_failures.push({case:name,assertion:'draw_suppresses_and_restores_compensation',draw});
      for(let i=0;i<3;i++) {
        const repeat=sample(flags,true,false);
        if(!sameMeasurement(cold,repeat))result.contract_failures.push({case:name,assertion:'cold_measurement_does_not_accumulate',cold,repeat});
      }
    }
  }
  row=null;const unowned=sample(0,false,false);result.unowned=unowned;
  // Hooks still record their parser phase for every label, but no unowned
  // state is changed: this is the native branch's untouched result.
  if(unowned.bottom!==96||unowned.y!==-6||!unowned.ruby||unowned.compensationFlag!==1||unowned.flags!==0)
    result.contract_failures.push({case:'unowned',assertion:'ordinary_text_unchanged',unowned});
  if(errors.length)result.contract_failures.push({case:'callback',assertion:'production_callback_error',errors});
  result.all_passed=result.contract_failures.length===0;
  return result;
}};
""".replace("__PRODUCTION_HOOKS__", hooks)


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
