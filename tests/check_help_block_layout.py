"""Project captured final glyphs with native CAB anchor/matrix instructions.

The production final-position callback is tested after all text layout paths.
Captured r4 quads are inputs, never presented as predicted r5 game output.
"""

import argparse
import json
from pathlib import Path

from check_native_log_inset import script_source
from check_owned_title_layout import ROOT, run_host


def source():
    fixture = json.loads((ROOT / "tests/fixtures/help-block-layout.json").read_text("utf-8"))
    agent = (ROOT / "sora_bilingual/game/scripts/native_agent.js").read_text("utf-8")
    start = (
        "function helpTextFrame("
        if "function helpTextFrame(" in agent
        else "function offsetTextProjection("
    )
    methods = agent[agent.index(start) : agent.index("\nfunction newLogContributions(")]
    native = script_source(fixture["native"], "")
    helpers = native[native.index("function check(") : native.index("function setup(")]
    helpers = helpers.replace("0x589130", fixture["native"]["anchor_rva"])
    return (
        "const INPUT="
        + json.dumps(fixture, ensure_ascii=False)
        + ";const SPEC=INPUT.native;\n"
        + "const layoutKinds=new Map(),insetRoots=new Map(),logTextGroups=new Map(),labelCallbacks=new Map(),labels=new Map();\n"
        + "let enabled=true,failed=false,renderMode='annotation',epoch=7,bilingualOffsetY=0;\n"
        + helpers
        + methods
        + r"""
function setup(sample){
    const label=Memory.alloc(0x900),frame=Memory.alloc(0x700),parent=Memory.alloc(0x300),children=Memory.alloc(16);
    const names=['text','base','help'].map(name=>Memory.allocUtf8String(name));
    label.add(0x80).writePointer(parent);frame.add(0x80).writePointer(parent);
    label.add(0x88).writePointer(names[0]);frame.add(0x88).writePointer(names[1]);parent.add(0x88).writePointer(names[2]);
    parent.add(0x228).writePointer(children);parent.add(0x230).writeU32(2);
    children.writePointer(frame);children.add(8).writePointer(label);
    for(const [p,m,size,anchor] of [[label,sample.label_matrix,sample.label_size,sample.label_anchor],
            [frame,sample.frame_matrix,sample.frame_size,sample.frame_anchor]]){
        m.forEach((v,i)=>p.add(8+i*4).writeFloat(v));
        p.add(0x2d8).writeFloat(size[0]);p.add(0x2dc).writeFloat(size[1]);p.add(0x2e0).writeU32(anchor);
    }
    const array=Memory.alloc(sample.glyphs.length*8),manager=Memory.alloc(0x28),records=[];
    label.add(0x330).writeU32(sample.glyphs.length);label.add(0x680).writePointer(manager);manager.add(0x20).writePointer(array);
    sample.glyphs.forEach(([x,y,w,h,kind],i)=>{
        const p=Memory.alloc(0xc4);array.add(i*8).writePointer(p);records.push(p);
        for(const [o,v] of [[0x38,x],[0x3c,y],[8,w],[0x1c,h]])p.add(o).writeFloat(v);p.add(0xc0).writeU32(kind);
    });
    const row={pointer:label,epoch,plan:{kind:sample.kind},surface:'help',helpFrame:helpTextFrame(label),glyphLanes:[{}]};
    labels.set(String(label),row);const lease={depth:1,projection:null};labelCallbacks.set(String(label),lease);
    return {label,frame,parent,children,row,lease,records,array,manager,names};
}
function center(state,native){
    const glyphs=state.records.map(p=>[p.add(0x3c).readFloat(),Math.abs(p.add(0x1c).readFloat())]);
    const mid=(Math.min(...glyphs.map(([y,h])=>y-h/2))+Math.max(...glyphs.map(([y,h])=>y+h/2)))/2;
    const anchor=Memory.alloc(0x40),point=Memory.alloc(16);
    native.anchor(anchor,state.label.add(0x2e0).readU32(),state.label.add(0x2d8));
    point.writeFloat(anchor.add(0x30).readFloat()+state.label.add(0x2d8).readFloat()/2);
    point.add(4).writeFloat(anchor.add(0x34).readFloat()+mid);point.add(12).writeFloat(1);
    const actual=project(state.label,point,native);
    native.anchor(anchor,state.label.add(0x2e0).readU32(),state.label.add(0x2d8));
    point.writeFloat(anchor.add(0x30).readFloat()+state.label.add(0x2d8).readFloat()/2);
    point.add(4).writeFloat(anchor.add(0x34).readFloat()+state.label.add(0x2dc).readFloat()/2);
    const target=project(state.label,point,native);
    return {actual:actual[1],target:target[1]+bilingualOffsetY*state.label.add(0x1c).readFloat()};
}
rpc.exports.run=()=>{
    const native=nativeFunctions(),results=[];
    // Execute CAB62's actual equal-text early return, not a setter model
    // that always copies and redraws (which hid the menu-entry regression).
    const setterCode=Memory.alloc(0x1000);
    setterCode.writeByteArray(INPUT.native.setter_noop.bytes);Memory.protect(setterCode,0x1000,'r-x');
    const unchangedSetter=new NativeFunction(setterCode,'void',['pointer','pointer']);
    const setterNoop=[];
    for(const samePointer of [true,false]) {
        const p=Memory.alloc(0x700),text=Memory.allocUtf8String('<R>说明</R説明>');
        const incoming=samePointer?text:Memory.allocUtf8String(text.readUtf8String());
        p.add(0x318).writePointer(text);p.add(0x330).writeU32(7);
        // Unequal strings would call unrelocated external routines: never
        // enter those paths in this exact-byte equal-text fixture.
        check(incoming.readUtf8String()===text.readUtf8String(),'setter fixture requires equal bytes');
        const before=Array.from(new Uint8Array(p.readByteArray(0x700)));
        unchangedSetter(p,incoming);
        const unchanged=JSON.stringify(before)===JSON.stringify(Array.from(new Uint8Array(p.readByteArray(0x700))));
        check(unchanged,'native equal-text setter modified label or dirtied draw');
        setterNoop.push({samePointer,all_label_bytes_unchanged:unchanged});
    }
    for(const sample of INPUT.cases)for(const mode of ['annotation','bilingual','primary','secondary'])
    for(const active of [true,false])for(const kind of [sample.kind,'plain']){
        const state=setup({...sample,kind});renderMode=mode;enabled=active;bilingualOffsetY=0;
        const before=center(state,native),matrixBefore=Array.from(new Uint8Array(state.label.add(8).readByteArray(64)));
        const glyphsBefore=state.records.map(p=>Array.from(new Uint8Array(p.readByteArray(0xc4))));
        const ys=[];
        for(let pass=0;pass<3;pass++){
            offsetTextProjection(state.label);ys.push(center(state,native).actual);restoreTextProjection(state.lease);
            check(JSON.stringify(Array.from(new Uint8Array(state.label.add(8).readByteArray(64))))===JSON.stringify(matrixBefore),'matrix restore');
        }
        check(JSON.stringify(state.records.map(p=>Array.from(new Uint8Array(p.readByteArray(0xc4)))))===JSON.stringify(glyphsBefore),'projection changed glyphs');
        const expected=active&&['annotation','bilingual'].includes(mode)&&kind!=='plain'?before.target:before.actual;
        results.push({case:sample.case,kind,mode,active,before,ys,expected});
    }
    // Boundary variants use the same captured glyphs; only rectangle geometry
    // changes. Native anchor instructions supply the independent expectation.
    for(const sample of INPUT.cases)for(let anchor=0;anchor<9;anchor++)for(const scale of [.65,1.5])for(const offset of [-9,0,7]){
        const state=setup(sample);enabled=true;renderMode='annotation';bilingualOffsetY=offset;
        state.label.add(0x2e0).writeU32(anchor);state.frame.add(0x2e0).writeU32(8-anchor);
        for(const p of [state.label,state.frame]){p.add(8).writeFloat(scale);p.add(0x1c).writeFloat(scale);}
        const before=center(state,native);offsetTextProjection(state.label);
        results.push({case:sample.case,anchor,scale,offset,ys:[center(state,native).actual],expected:before.target});
        restoreTextProjection(state.lease);
    }
    for(const sample of INPUT.cases)for(const invalid of ['missing-frame','no-lanes','stale-epoch','invalid-size','failed','nested']){
        const state=setup(sample);enabled=true;renderMode='annotation';bilingualOffsetY=0;failed=false;
        if(invalid==='missing-frame')state.row.helpFrame=null;
        if(invalid==='no-lanes')state.row.glyphLanes=[];
        if(invalid==='stale-epoch')state.row.epoch--;
                if(invalid==='invalid-size')state.label.add(0x2dc).writeFloat(0);
        if(invalid==='failed')failed=true;
        if(invalid==='nested')state.lease.depth=2;
        const before=center(state,native).actual;offsetTextProjection(state.label);
        results.push({case:sample.case,invalid,ys:[center(state,native).actual],expected:before});
        check(!state.lease.projection,'invalid geometry/ownership wrote matrix');
    }
    failed=false;
    return {results,setter_noop:setterNoop,game_attached:false,host:'self-created-hidden-python',
        contract:'actual native anchor and matrix projection; complete live font parse and GPU pending'};
};
"""
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/help-block-layout.json")
    args = parser.parse_args()
    report = run_host(source())
    report["failures"] = [
        r for r in report["results"] if any(abs(v - r["expected"]) > 0.001 for v in r["ys"])
    ]
    report["passed"] = not report["failures"]
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "cases": len(report["results"]),
                "failures": report["failures"][:4],
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
