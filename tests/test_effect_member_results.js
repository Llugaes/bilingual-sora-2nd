'use strict';
const assert=require('node:assert/strict'),test=require('node:test');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
function model() {
    const rows=[['A',['JA','ZA']],['B',['JB','ZB']],['C',['JC','ZC']],['A, B, C',['JABC','ZABC']]];
    return {pairs:{},plain_pairs:{},detail_join:[', ','、','，'],
        detail_effect_units:[...rows.map(([pattern,pair],i)=>({pattern,pair,ids:['effect/'+i+'/name']})),
            {source:'Blind %d%',pattern:'Blind ([+-]?[0-9]+)%',pair:['暗闇%d%','黑暗%d%'],parameter_kinds:['d'],ids:['effect/blind']}],
        detail_effect_constructor_ids:['effect/blind']};
}
test('member decision and historical refusal are separate fields',()=>{
    const r=new RuntimeText(model());
    assert.equal(r.effectUnits('A, B, C'),null);
    const matched=r.effectUnitResult('A, B, C');
    assert.equal(matched.scope,'effect_member');assert.equal(matched.status,'Match');assert.equal(matched.reason,null);
    assert.equal(matched.compatFailureAfter,'different_partition_targets');
    assert.deepEqual(matched.unit,r.effectUnit('A, B, C'));assert.equal(r.effectRejected('A, B, C'),true);
    r.effectUnitFailures.set('Unknown','invalid_effect_parameter');
    const absent=r.effectUnitResult('Unknown');
    assert.equal(absent.status,'NoMatch');assert.equal(absent.unit,null);assert.equal(absent.reason,null);
    assert.equal(absent.compatFailureAfter,'invalid_effect_parameter');
    const rejected=r.effectUnitResult('Blind 2147483648%');
    assert.equal(rejected.status,'Reject');assert.equal(rejected.unit,null);
    assert.equal(rejected.reason,'invalid_effect_parameter');assert.equal(rejected.compatFailureAfter,rejected.reason);
});
test('coalesced successful role precedes historical hard refusal',()=>{
    const r=new RuntimeText(model()),joined='<c698>A</C>';
    r.effectUnitFailures.set(joined,'conflicting_effect_member');
    const result=r.effectUnitResult('<c698></C><c698>A</C>');
    assert.equal(result.status,'Match');assert.equal(result.reason,null);
    assert.equal(result.compatFailureAfter,undefined);assert.equal(r.effectUnitFailures.get(joined),'conflicting_effect_member');
});
test('frame direction history is checked even after a successful stripped role',()=>{
    const r=new RuntimeText(model());r.frameOwner={rawPair:()=>['<C2>暗闇30%</C>','<C2>黑暗30%</C>']};
    r.effectUnitFailures.set('Blind 30%','unproven_direction_parameter');
    assert.equal(r.effectUnitResult('Blind 30%',true).status,'Match');
    const result=r.effectUnitResult('<C2>Blind 30%</C>');
    assert.equal(result.status,'Reject');assert.equal(result.reason,'unproven_direction_parameter');
});
test('composers use decisions, and owned units bypass member parsing',()=>{
    const r=new RuntimeText(model());r.effectUnit=()=>{throw Error('compatibility wrapper called');};
    assert.ok(r.effectUnits('A, B'));assert.ok(r.effectLineUnits('[A] - B',true));
    r.effectUnitResult=()=>{throw Error('owned member reparsed');};
    const owned={source:'Owned',pair:['J','Z'],semantic_ids:['owned']};
    assert.deepEqual(r.effectUnits('Owned',false,'',null,{Owned:owned}),[owned]);
});
test('atomic decisions keep capacity and order; only list refusal clears at 20000',()=>{
    const r=new RuntimeText(model());r.effectUnitFailures.set('Blind 2147483648%','prior_reason');
    for(let i=0;i<19999;i++)r.effectUnitFailures.set('seed/'+i,'unassociated_effect_unit');
    assert.equal(r.effectUnitResult('Blind 2147483648%').status,'Reject');
    assert.equal(r.effectUnitFailures.size,20000);
    assert.equal(r.effectUnitFailures.keys().next().value,'Blind 2147483648%');
    assert.equal(r.effectUnitResult('A').status,'Match');assert.equal(r.effectUnitResult('Unknown').status,'NoMatch');
    assert.equal(r.effectUnitFailures.size,20000);assert.equal(r.effectUnits('Bad\nLine'),null);
    assert.deepEqual([...r.effectUnitFailures],[['Bad\nLine','hard_line_or_native_ruby']]);
});
