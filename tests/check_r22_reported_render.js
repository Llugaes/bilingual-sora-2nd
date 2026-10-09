'use strict';
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const receipt=JSON.parse(fs.readFileSync('generated/r22-production-receipt.json','utf8'));
const bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const fixture=JSON.parse(fs.readFileSync('tests/fixtures/r22-actual-cloak-source.json','utf8'));
const actual={original:fixture.source,text_key:fixture.key,scope:fixture.scope};
assert.equal(actual.text_key,null);assert.equal(actual.scope,null);
const header='[Support - <I277><C3>Ally - Target - Circle (L)</C>] ',color=s=>'<c698>'+s+'</C>',join='<c698>, </C>';
const inputs=[
 {name:'actual cloak null identity',source:actual.original,level:'actual resident original; snapshot after translation disable',forbidden:['Resist','Stat Debuff','Sleep'],body:true},
 {name:'CP strength2',source:header+['STR<I271> (5 turns)','CP Regen','Cure Stat Debuff'].map(color).join(join)+'\n<C9>Grants allies within range fiery protection and vitality.',level:'resource constructor and pixel transcription; setter not captured',forbidden:['turns','CP Regen','Cure Stat Debuff'],body:true},
 {name:'reflect and shield',source:header+['Physical Reflect (1 attacks)','Shield (M)'].map(color).join(join)+'\n<C9>Create an earth shield that reflects one physical hit.',level:'resource constructor and pixel transcription; setter not captured',forbidden:['Support','Ally','Target','Circle','Physical Reflect','attacks','Shield','Create'],body:true},
 {name:'single HP percent',source:header.replace('Support','Recovery').replace('Target - ','')+['Recover 30% HP','Cure Stat Debuff'].map(color).join(join)+'\n<C9>Dispel debuffs on allies in range using purifying water.',level:'resource constructor and pixel transcription; setter not captured',forbidden:['Recover','Cure Stat Debuff'],body:true}
];
const reports=[];
for(const row of inputs){
 const modes={};
 for(const mode of ['primary','secondary','annotation']){
  const tr=new RuntimeText(model),plan=tr.render(row.source,mode,'',''),output=plan.text+' '+plan.layers.map(l=>l.text).join(' ');
  for(const word of row.forbidden)assert.ok(!output.includes(word),row.name+' / '+mode+' / '+word+'\n'+JSON.stringify(plan));
  if(mode==='annotation'){
   assert.equal(plan.kind,'layered');assert.ok(plan.layers.some(l=>l.primary.includes('<C9>')||l.primary.includes('マント')),'complete body has an owned lane');
   assert.ok(plan.text.split('\n').every(line=>line.includes('<R></R_>')),'every translated line uses the same native lane protocol');
   assert.ok(!/<R>[^<>]+<\/R[^<>]*>/.test(plan.text),'no unowned inline ruby inside layered row');
   assert.ok(!plan.layers.some(l=>l.primary.includes(' - ')&&l.primary.includes('CRT')),'no whole equipment header annotation');
   if(row.name.startsWith('CP'))assert.equal(plan.layers.filter(l=>l.semantic_ids?.some(i=>i.includes('/SkillEffectHelpData/')||i.includes('/turn_stat_'))).length,3);
  }
  modes[mode]=plan;
 }
 reports.push({...row,modes});
}
// Freeze the three captured r20 successes, including its styled Arts Delay.
const english=p=>new Set((p.text+' '+p.layers.map(l=>l.text).join(' ')).replace(/<[^<>]*>/g,'').match(/[A-Za-z]+/g)||[]);
for(const row of JSON.parse(fs.readFileSync('tests/fixtures/r21-r20-captured-baseline.json','utf8')).cases)
 for(const mode of ['primary','secondary','annotation']){
  const p=new RuntimeText(model).render(row.source,mode),old=english(row.baseline_modes[mode]);
  for(const word of english(p))assert.ok(old.has(word),'r20 success gained EN: '+row.name+'/'+mode+'/'+word);
 }
const report={source_receipt:receipt.wire_path,wire_sha256:receipt.wire_sha256,reports,game_attached:false,pixels_verified:false};
fs.writeFileSync('generated/r22-reported-final-render.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({reported_inputs:reports.length,three_final_modes:true,pixels_verified:false}));
