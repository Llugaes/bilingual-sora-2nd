"""Replay the captured detail through the resolver and real CAB origin leaf.

The reused host executes production callbacks; it never attaches to the game.
This checks the paragraph origin, not the game's complete glyph placement.
"""

import argparse
import hashlib
import json
from pathlib import Path

from check_owned_title_layout import FIXTURE, ROOT, run_host, source


def check_code():
    captured = json.loads((ROOT / "tests/fixtures/detail-first-line.json").read_text("utf-8"))
    code = source(json.loads(FIXTURE.read_text("utf-8")))
    code += "\nconst DETAIL=" + json.dumps(captured, ensure_ascii=False) + ";\n"
    layered = json.loads((ROOT / "tests/fixtures/r22-native-ruby-detail.json").read_text("utf-8"))
    code += "const LAYERED=" + json.dumps(layered, ensure_ascii=False) + ";\n"
    code += r"""
rpc.exports.run=()=>{
    const results=[],body=DETAIL.source.split('\n')[1];
    const samples=[
        {name:'captured-stat-prefix',text:DETAIL.source,flag:1},
        {name:'body-only-ruby',text:'【 STR+800 】\n'+body,flag:0},
        {name:'translated-first',text:'必杀率+10％\n'+body,flag:1},
        {name:'single-detail',text:body,flag:1},
        {name:'layered-header',text:'<c698>HP Regen</C>\nSkill description',flag:1,model:LAYERED.model},
        {name:'unknown-detail',text:DETAIL.source,flag:1,model:{pairs:DETAIL.model.pairs,plain_pairs:DETAIL.model.plain_pairs},excluded:true},
        {name:'log',text:DETAIL.source,flag:1,scope:{logKind:'body'},excluded:true},
        {name:'speaker',text:DETAIL.source,flag:1,scope:{dialogueSpeaker:true},excluded:true},
        {name:'save',text:DETAIL.source,flag:1,scope:{scope:'save_summary'},excluded:true},
    ];
    for(const sample of samples)for(const mode of ['annotation','bilingual','primary','secondary'])
    for(const active of [true,false])for(const measuring of [false,true])for(const line of [0,1]){
        const state=fresh(32,mode,active),p=state.parent;
        resolver=new RuntimeText(sample.model||DETAIL.model);state.row.original=sample.text;
        Object.assign(state.row,sample.scope||{});
        state.row.displayed=wantedText(state.row);state.label.add(0x318).writePointer(Memory.allocUtf8String(state.row.displayed));
        const raw=new RuntimeText(DETAIL.model).render(sample.text,'annotation');
        if(sample.name==='captured-stat-prefix'&&raw.text!==DETAIL.shown)throw Error('captured display changed');
        state.label.add(0x2e8).writeU32(0);state.label.add(0x2f8).writeFloat(7);state.label.add(0x2fc).writeFloat(0);
        const lineInfo=Memory.alloc(24);lineInfo.add(line*12+8).writeU8(sample.flag);
        state.label.add(0x660).writePointer(lineInfo);state.label.add(0x668).writeU32(2);
        p.add(0x16c).writeU32(line);p.add(0x1ab).writeU8(measuring?1:0);
        formula.table.add(0x6a4).writeFloat(-12);
        const bilingual=active&&['annotation','bilingual'].includes(mode);
        // Native monolingual layout has no owned ruby flag. Ordinary second
        // lines retain their existing leading; only the first origin changes.
        if(!bilingual)lineInfo.add(line*12+8).writeU8(0);
        const ys=[];
        for(let pass=0;pass<3;pass++){
            p.add(4).writeFloat(100);p.add(0x1a7).writeU8(0);
            nativeOrigin(state.label,p);ys.push(p.add(4).readFloat());
        }
        results.push({name:sample.name,mode,active,measuring,line,kind:state.row.plan.kind,
            mixed:state.row.preservePrimaryLayout,ys,
            expected:measuring||!bilingual?100:line===0?(sample.excluded?100:112):
                state.row.preservePrimaryLayout||!sample.flag?100:107});
    }
    // All eight source languages and all primary/secondary choices consume
    // the same native origin rule. Resource strings stay verbatim; these
    // combinations are layout-contract probes, not game scene observations.
    for(const [language,description] of Object.entries(DETAIL.description_texts))
    for(const [primary,a] of Object.entries(DETAIL.description_texts))
    for(const [secondary,b] of Object.entries(DETAIL.description_texts)){
        const pairs={[description]:[a,b]},model={pairs,plain_pairs:pairs,detail_sources:[description],
            details:{pairs,plain_pairs:pairs},same_language:primary===secondary};
        const text=DETAIL.format_texts[language].replace('%s','STR+800')+
            DETAIL.close_texts[language].replace('%s','').replace('%s',description);
        const state=fresh(32),p=state.parent;resolver=new RuntimeText(model);state.row.original=text;
        const lineInfo=Memory.alloc(12);state.label.add(0x660).writePointer(lineInfo);state.label.add(0x668).writeU32(1);
        // This first line contains no annotation. Previously the body alone
        // could not request the same top reserve as a translated header.
        lineInfo.add(8).writeU8(0);p.add(0x16c).writeU32(0);p.add(0x1ab).writeU8(0);
        state.label.add(0x2e8).writeU32(0);state.label.add(0x2fc).writeFloat(0);
        formula.table.add(0x6a4).writeFloat(-12);
        for(const [mode,active] of [['annotation',true],['primary',true],['secondary',true],
                ['annotation',false],['bilingual',true],['annotation',true]]){
            renderMode=mode;enabled=active;state.row.displayed=wantedText(state.row);
            state.label.add(0x318).writePointer(Memory.allocUtf8String(state.row.displayed));
            p.add(4).writeFloat(100);p.add(0x1a7).writeU8(0);nativeOrigin(state.label,p);
            const annotated=['ruby','layered'].includes(state.row.plan.kind);
            results.push({name:'language-switch',language,primary,secondary,mode,active,
                ys:[p.add(4).readFloat()],expected:annotated?112:100});
        }
    }
    return {results,errors,game_attached:false,host:'self-created-hidden-python'};
};
"""
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/detail-first-line.json")
    args = parser.parse_args()
    report = run_host(check_code())
    report["native_agent_sha256"] = hashlib.sha256(
        (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_bytes()
    ).hexdigest()
    report["failures"] = [r for r in report["results"] if any(y != r["expected"] for y in r["ys"])]
    report["passed"] = not report["failures"] and not report["errors"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "cases": len(report["results"]),
                "failures": report["failures"][:6],
                "errors": report["errors"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
