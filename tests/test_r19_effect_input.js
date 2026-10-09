'use strict';
const assert=require('node:assert/strict'),test=require('node:test');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const model=()=>({pairs:{},plain_pairs:{},numeric:[],raw_numeric:[],
  detail_sources:['Official description'],details:{
    pairs:{'Official description':['説明','说明']},plain_pairs:{'Official description':['説明','说明']},
    detail_join:[', ','／','／'],condition_lists:[{id:98,
      templates:['Resist %s','状態耐性%s','状态抗性%s'],links:['/','･','･'],percent:['%d%%','%d％','%d％'],
      names:{Burn:['炎傷','炎伤'],Confuse:['混乱','混乱'],Deathblow:['即死','即死'],Mute:['封魔','封魔'],Freeze:['凍結','冻结']}}],
    detail_effect_units:[
      {pattern:'STR<I270> \\(([+-]?\\d+) turns\\)',pair:['%dターンSTR<I270>','%d回合STR<I270>'],ids:['typed/turn_stat_inline_icon/80']},
      {pattern:'HP Regen',pair:['HP徐々回復','逐渐回复HP'],ids:['effect/hp/name']},
      {pattern:'CP Regen',pair:['CP徐々上昇','CP逐渐上升'],ids:['effect/cp/name']},
      {pattern:'Cure Stat Debuff',pair:['能力低下解除','解除能力降低'],ids:['effect/debuff/name']},
    ]}});
const body='\n<C0>Official description';
test('native color-wrapped FORMAT8 preserves three independent effect roles',()=>{
  const tr=new RuntimeText(model()),head='<c698>STR<I270> (5 turns)</C><c698>, </C><c698>CP Regen</C><c698>, </C><c698>Cure Stat Debuff</C>';
  const plan=tr.render(head+body),layers=plan.layers.filter(l=>l.semantic_ids?.length);
  assert.equal(layers.length,3);
  assert.deepEqual(layers.map(l=>l.text),['<c698>5回合STR<I270></C>','<c698>CP逐渐上升</C>','<c698>解除能力降低</C>']);
  assert.ok(!plan.text.includes('CP Regen'));
  assert.ok(plan.text.includes('<c698>／</C>'));
  assert.equal(tr.effectDetailPlan(head),null,'unanchored fragments cannot grant detail roles');
  for(const suffix of [', UNKNOWN','<K3>'])assert.equal(tr.details.effectUnits(head+suffix),null);
});
test('complete condition-mask arguments survive final detail annotation',()=>{
  const tr=new RuntimeText(model());
  for(const names of ['Burn/Confuse/Deathblow','Mute/Freeze']) {
    const source='<c698>Resist '+names+' 100%</C>'+body,plan=tr.render(source);
    assert.ok(!(plan.text+plan.layers.map(l=>l.text).join('')).includes(names));
    assert.equal(plan.layers.filter(l=>l.semantic_ids?.length).length,1);
    assert.ok(plan.layers[0].text.includes(names.startsWith('Burn')?'炎伤･混乱･即死':'封魔･冻结'));
  }
  for(const names of ['Burn/Burn','Burn/UNKNOWN','Burn 101%'])
    assert.equal(tr.details.conditionListPair('<c698>Resist '+names+(names.endsWith('%')?'':' 100%')+'</C>'),null);
});
test('colored FORMAT8 does not split unrelated comma prose or resolve conflicts',()=>{
  const tr=new RuntimeText(model());
  assert.equal(tr.details.effectUnits('<c698>Unknown, text</C>'),null);
  assert.equal(tr.details.effectUnits('<c698>HP Regen</C><c698>, <K3></C><c698>CP Regen</C>'),null,'unknown separator control stays opaque');
  const m=model();m.details.detail_effect_units.push({pattern:'CP Regen',pair:['別効果','另一效果'],ids:['conflicting']});
  assert.equal(new RuntimeText(m).details.effectUnits('<c698>HP Regen</C><c698>, </C><c698>CP Regen</C>'),null);
});
