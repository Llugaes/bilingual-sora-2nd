'use strict';
const crypto=require('node:crypto');
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?
    Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
function snapshot(failures) {
    const ordered=[...failures];
    return {count:ordered.length,sha256:crypto.createHash('sha256').update(JSON.stringify(canonical(ordered))).digest('hex'),
        edges:ordered.length<8?ordered:ordered.slice(0,3).concat(ordered.slice(-3))};
}
function evaluate(RuntimeText,input) {
    return input.cases.map(c=>{
        const outer=new RuntimeText(input.model),r=outer.details;
        for(const [key,value] of c.seed_before||[])r.effectUnitFailures.set(key,value);
        for(let i=0;i<(c.seed_count||0);i++)r.effectUnitFailures.set('seed/'+i,'unassociated_effect_unit');
        for(const [key,value] of c.seed||[])r.effectUnitFailures.set(key,value);
        const calls=[],method=typeof r.effectUnitResult==='function'?'effectUnitResult':'effectUnit',original=r[method].bind(r);
        r[method]=(source,coalesced=false)=>{calls.push([source,coalesced]);return original(source,coalesced);};
        return {name:c.name,events:c.steps.map(([action,source,...args])=>{
            calls.length=0;
            const value=action==='atom'?r.effectUnit(source):action==='units'?r.effectUnits(source,...args):
                action==='rejected'?r.effectRejected(source):action==='translate'?outer.translate(source,...args):outer.render(source,...args);
            return {value,failures:snapshot(r.effectUnitFailures),calls:calls.slice()};
        })};
    });
}
module.exports={evaluate};
if(require.main===module) {
    const fs=require('node:fs'),path=require('node:path'),input=JSON.parse(fs.readFileSync(0,'utf8'));
    const {RuntimeText}=require(path.resolve(process.argv[2]||'sora_bilingual/game/scripts/runtime_text.js'));
    process.stdout.write(JSON.stringify(evaluate(RuntimeText,input)));
}
