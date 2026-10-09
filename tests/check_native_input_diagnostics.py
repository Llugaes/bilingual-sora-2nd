"""Exercise production diagnostics in Frida V8 in an owned hidden host only."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import frida

ROOT = Path(__file__).resolve().parents[1]


def main():
    scripts = ROOT / "sora_bilingual/game/scripts"
    agent = (scripts / "native_agent.js").read_text("utf-8")
    status = agent[
        agent.index("function inputDiagnosticStatus()") : agent.index("const dialogueFrames=")
    ]
    snapshot = agent[
        agent.index("    snapshot(identityOnly=") : agent.index(
            "    status() {", agent.index("    snapshot(identityOnly=")
        )
    ]
    snapshot = snapshot.rstrip().removesuffix(",")
    source = (scripts / "runtime_identity.js").read_text("utf-8")
    source += "\nnew Function(" + json.dumps(agent) + ");\n"
    data = bytes(range(96))
    source += "\nconst expectedHash=" + json.dumps(hashlib.sha256(data).hexdigest()) + ";\n"
    source += (
        r"""
const base=ptr('0x10000000'),gameModule={size:0x2000000},REPORT={diagnostics:true};
const activeModel={},modelProvenance={format:'json-rpc'},scriptIdentities={sourceLanguage:'en'};
const epoch=2,renderMode='annotation',labels=new Map(),inputIdentityDiagnostics=new Map();
"""
        + status
        + "\nconst captured={"
        + snapshot
        + "};\n"
        + r"""
rpc.exports={run(){
    const require=(value,message)=>{if(!value)throw Error(message);};
    const blob=Memory.alloc(96);blob.writeByteArray(Uint8Array.from({length:96},(_,i)=>i));
    const header=Array.from(new Uint8Array(blob.readByteArray(24))).map(v=>v.toString(16).padStart(2,'0')).join('');
    const candidate={size:96,offset:48,sha256:expectedHash,header,key:'menu/1'};
    const model={pairs:{text:['text','translated']}};
    const ids=new ScriptIdentities({pointers:{text:[candidate]},pointer_models:{'menu/1':{source:'text',model}}});
    const events=[];require(ids.pointerSelect(blob.add(48),'text',e=>events.push(e)).key==='menu/1','native pointer identity');
    require(events.at(-1).stage==='selected','selected stage');
    require(ids.pointerSelect(blob.add(48),'text',()=>{throw Error('diagnostic consumer');}).key==='menu/1','throwing trace cannot reject valid identity');
    const diagnostic={table:[],table_events_total:0,table_events_dropped:0};
    collectInputIdentityTrace(diagnostic,'table',{stage:'x'.repeat(150000),key:42,file:'f'.repeat(150000),
        sha256:'s'.repeat(150000),offset:{bad:true},record_at:Infinity,field_at:-1,secret:'private'.repeat(25000)});
    const safe=diagnostic.table[0];
    require(safe.key===null&&safe.file.length===256&&safe.sha256.length===64&&safe.stage.length===64,'typed field budgets');
    require(safe.offset===null&&safe.record_at===null&&safe.field_at===null&&!Object.hasOwn(safe,'secret'),'scalar whitelist');
    require(safe.file_truncated&&safe.sha256_truncated&&JSON.stringify(diagnostic).length<2000,'bounded diagnostic serialization');
    collectInputIdentityTrace(diagnostic,'table',{get key(){throw Error('metadata getter');}});
    require(diagnostic.table_trace_error&&diagnostic.table.length===1,'metadata getter isolated');
    blob.add(60).writeU8(0);events.length=0;
    require(ids.pointerSelect(blob.add(48),'text',e=>events.push(e))===null,'changed script rejected');
    require(events[0].stage==='script_hash_mismatch','first failed script stage');
    for(let i=0;i<64;i++){
        const pointer='0x'+i.toString(16),original='x'.repeat(3000);
        labels.set(pointer,{original,displayed:original,epoch:2,plan:{kind:'plain'}});
        inputIdentityDiagnostics.set(pointer,{source:original.slice(0,2048),truncated:true,script_final_stage:'script_hash_mismatch'});
    }
    const actual=captured.snapshot(true);
    require(actual.schema===2&&actual.rows.length===64,'bounded snapshot');
    require(actual.rows[0].original.length===2048&&actual.rows[0].source_matches_diagnostic===null,'truncated source is not exact');
    require(actual.diagnostics.source_language==='en'&&actual.diagnostics.model_loaded,'actual model state');
    REPORT.diagnostics=false;require(captured.snapshot(true).rows.length===0,'disabled diagnostics');
    return {full_agent_syntax:true,native_pointer_trace:true,throwing_trace_isolated:true,typed_field_budgets:true,
        metadata_getter_isolated:true,bounded_snapshot:true,disabled_snapshot:true,game_attached:false};
}};
"""
    )
    host = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        session = frida.attach(host.pid)
        script = session.create_script(source, runtime="v8")
        script.load()
        print(json.dumps(script.exports_sync.run()), flush=True)
    finally:
        if session is not None:
            session.detach()
        host.stdin.close()
        host.wait(timeout=10)


if __name__ == "__main__":
    main()
