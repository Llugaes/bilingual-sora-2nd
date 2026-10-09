'use strict';
const fs=require('fs'),assert=require('node:assert/strict');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const fixture=JSON.parse(fs.readFileSync('tests/fixtures/r22-native-ruby-detail.json','utf8')),
 independent=JSON.parse(fs.readFileSync('generated/r22-rev3-native-ruby-fixture.json','utf8'));
const reports=[];
for(const [name,row] of [['readable',fixture],['independent compiler',independent]]){
 const ranges=RuntimeText.rubyRanges(row.source),original=row.source.slice(...ranges[0]),modes={};
 for(const mode of ['primary','secondary','annotation']){
  const tr=new RuntimeText(row.model),plan=tr.render(row.source,mode),outside=plan.text.replace(original,'');
  assert.ok(plan.text.includes(original),'original R retained byte for byte');
  assert.ok(!outside.includes('CP Regen'),'external CP role resolved in '+name+'/'+mode);
  if(mode==='annotation'){
   assert.equal(plan.kind,'layered');assert.equal(plan.layers.length,2,'external effect and body own separate lanes');
   assert.ok(plan.layers.every(l=>!l.primary.includes('<R>')&&!l.text.includes('<R>')),'original R never copied into auxiliary payload');
  }
  assert.ok(tr.effectDetailPlan(row.source),'same scoped effect parser');modes[mode]=plan;
 }
 reports.push({name,source:row.source,modes,level:row.level});
}
for(const source of [fixture.source.replace('</RCP Regen>',''),fixture.source.replace('<R>','<R><R>')])
 assert.equal(new RuntimeText(fixture.model).effectDetailPlan(source),null,'malformed/nested R grants no effect plan');
for(const atom of ['Blind 2147483648%','<X999>HP Regen</X>']){
 const source=fixture.native_ruby+atom+'\n<C0><C9>Skill description';
 for(const mode of ['primary','secondary','annotation']){
  const p=new RuntimeText(fixture.model).render(source,mode);assert.equal(p.text,source);assert.equal(p.layers.length,0);
 }
}
assert.equal(new RuntimeText(fixture.model).render(fixture.native_ruby+'<c698>CP Regen</C>\nOther description','primary').text,
 fixture.native_ruby+'<c698>CP Regen</C>\nOther description','wrong description cannot grant CP');
fs.writeFileSync('generated/r22-rev3-native-ruby-final.json',JSON.stringify({reports,original_R_preserved:true,game_attached:false,pixels_verified:false},null,2));
console.log(JSON.stringify({fixtures:reports.length,three_final_modes:true,native_R_preserved:true}));
