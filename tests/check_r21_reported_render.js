'use strict';
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const receipt=JSON.parse(fs.readFileSync(process.env.R21_MODEL_RECEIPT||'generated/r20-production-receipt.json','utf8'));
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const cases=[];
const english=plan=>new Set((plan.text+' '+plan.layers.map(l=>l.text).join(' ')).replace(/<[^<>]*>/g,'').match(/[A-Za-z]+/g)||[]);
const captured=JSON.parse(fs.readFileSync('tests/fixtures/r21-r20-captured-baseline.json','utf8'));
for(const row of captured.cases){
 const modes={},baselineEnglish={};
 for(const mode of ['annotation','primary','secondary']){
  const plan=new RuntimeText(model).render(row.source,mode),allowed=english(row.baseline_modes[mode]);
  for(const word of english(plan))assert.ok(allowed.has(word),'Previously translated captured original gained EN: '+row.name+' / '+mode+' / '+word);
  if(row.source.includes('Delay')){
   assert.ok(!plan.text.includes('Delay'));
   if(mode!=='secondary')assert.ok(plan.text.includes('遅延'));
   if(mode!=='primary')assert.ok((plan.text+plan.layers.map(l=>l.text).join('')).includes('延迟'));
  }
  modes[mode]=plan;baselineEnglish[mode]=[...allowed];
 }
 cases.push({name:row.name,source:row.source,level:row.evidence_level,plan:modes.annotation,modes,baselineEnglish});
}
const inline='<c698>STR<I270> (5 turns)</C><c698>, </C><c698>CP Regen</C><c698>, </C><c698>Cure Stat Debuff</C>',
 body="\n<C0>'Lake bottom hooligans,' as some call them, that live in mud.";
const review=[
 {name:'CP_unknown_neighbor',original:inline+'<c698>, </C><c698>UnprovenEffect</C>'+body,evidence_level:'controlled one-member resource fixture variation'},
 {name:'CP_bare_header',original:'[Enhance] '+inline+body,evidence_level:'controlled bare-header fixture variation'},
 {name:'HP_bare_header',original:'<C3></C>[Enhance] <c698>HP Regen</C>',evidence_level:'controlled bare-header fixture'},
 {name:'bare_Physical',original:'[Physical]',evidence_level:'parent pixel transcription; setter original not captured'}
];
for(const row of review) {
 const plan=new RuntimeText(model).render(row.original),units=plan.layers.filter(l=>l.semantic_ids?.some(id=>id.includes('/SkillEffectHelpData/')||id.includes('/generated/typed/turn_stat_')));
 cases.push({name:row.name,source:row.original,level:row.evidence_level,plan});
 if(row.name.startsWith('CP_'))assert.equal(units.length,3,'CP exact review fixture needs independent units: '+row.name);
 assert.ok(!plan.text.includes('CP Regen')&&!plan.text.includes('HP Regen')&&!plan.text.includes('[Physical]'),JSON.stringify({name:row.name,plan}));
 if(row.name==='CP_unknown_neighbor')assert.ok(plan.text.includes('<c698>UnprovenEffect</C>'));
}
const prefix='[Support - Ally - Single] ',tail='<c698>STR↑ (5 turns)</C><c698>, </C><c698>CP Regen</C><c698>, </C><c698>Cure Stat Debuff</C>';
for(const header of [prefix,'[Support] '])for(const unknown of ['',', Arseille',', Arseille - Factory']){
 const source=header+tail+unknown,tr=new RuntimeText(model),plan=tr.render(source),units=plan.layers.filter(l=>l.semantic_ids?.some(id=>id.includes('/SkillEffectHelpData/')||id.includes('/generated/typed/turn_stat_')));
 cases.push({name:'CP independent members',source,level:'offline resource-constructor fixture',plan});
 assert.equal(units.length,3,'Three admitted CP members must retain separate semantic layers: '+source);
 assert.ok(units.some(l=>l.text.includes('CP逐渐上升')));
 if(unknown){assert.ok(plan.text.includes(unknown.slice(2)));assert.ok(!plan.layers.some(l=>l.text.includes('アルセイユ')),'Unknown effect must not borrow global name translation');}
 assert.ok(!plan.text.includes('CP Regen'));
}
for(const source of ['[Physical]','[Support] HP Regen, Arseille','[Physical] Damage dealt to enemies with Seal +50%']){
 const plan=new RuntimeText(model).render(source);cases.push({name:'compact header and bound role',source,level:'offline resource-constructor fixture',plan});
 assert.ok(plan.layers.some(l=>l.semantic_ids?.length),'Complete compact header must authorize its family');
 assert.ok(!plan.text.includes('[Physical]'));
 if(source.includes('HP Regen')){assert.ok(!plan.text.includes('HP Regen'));assert.ok(plan.layers.some(l=>l.text.includes('逐渐回复HP')));assert.ok(plan.text.includes('Arseille'));}
 if(source.includes('Seal'))assert.ok(plan.layers.some(l=>l.text.includes('封技')&&l.semantic_ids?.some(id=>id.includes('/condition_parameter/'))));
}
const snap=JSON.parse(fs.readFileSync('generated/r21-existing-owner-snapshot-20261006T093452637602Z.json','utf8'));
const actual=snap.all_rows.find(r=>r.original==='<c990>Arseille - Factory</c>');assert.equal(actual.text_key,null);assert.equal(actual.scope,null);
const facility=new RuntimeText(model).render(actual.original,'annotation',actual.text_key||'',actual.scope||'');
cases.push({name:'actual NPC facility original',source:actual.original,level:'actual-original/null-identity replay',plan:facility});
assert.ok(!facility.text.includes('Factory'));assert.ok(facility.text.includes('工房'));
for(const word of ['Seal','Heal','Mute','Confuse','Physical','Factory'])assert.equal(new RuntimeText(model).translate(word,'primary'),word,'No global homograph exception: '+word);
for(const source of ['<c990>Factory</c>','<c990>Arseille - Factory Annex</c>','[PhysicalXYZ] HP Regen']){
 const tr=new RuntimeText(model),plan=tr.render(source);cases.push({name:'domain negative',source,level:'offline adjacent negative',plan});
 assert.equal(tr.ownerPair(source),null);assert.equal(tr.skillHeader(source),null);
 assert.ok(!plan.layers.some(l=>l.semantic_ids?.length));assert.ok(plan.text.includes(source.includes('Factory')?'Factory':'HP Regen'));
}
const mixed='「Seal」状態の敵に与えるダメージ+50％';
assert.deepEqual(new RuntimeText(model).render(mixed),{text:mixed,layers:[],kind:'plain'});
for(const source of ['[Support] HP Regen, <X999>Arseille</X>','[Support] HP Regen, <R>Arseille</Rforeign>',
 '[Support] HP Regen, , CP Regen','[Support] '+Array(33).fill('HP Regen').join(', '),
 '[Support] HP Regen'+('<C1>'.repeat(17))+', '+('</C>'.repeat(17))+'CP Regen']){
 for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]) {
  const tr=new RuntimeText(model);
  // Begin at final render: do not seed failure caches via a parser probe.
  for(const mode of order){assert.deepEqual(tr.render(source,mode),{text:source,layers:[],kind:'plain'});assert.equal(tr.translate(source,mode),source);}
 }
 cases.push({name:'hard effect refusal final propagation',source,level:'controlled rejection boundary',plan:{text:source,layers:[],kind:'plain'}});
}
const facilityConflict=new RuntimeText({...model,ambiguous_display:[...model.ambiguous_display,actual.original]});
assert.deepEqual(facilityConflict.render(actual.original),{text:actual.original,layers:[],kind:'plain'});
const conflict=new RuntimeText({...model,ambiguous_display:[...model.ambiguous_display,prefix+tail+', Arseille']});assert.deepEqual(conflict.render(prefix+tail+', Arseille'),{text:prefix+tail+', Arseille',layers:[],kind:'plain'});
const invalid='Damage dealt to enemies with Seal +2147483648%';assert.deepEqual(new RuntimeText(model).render(invalid),{text:invalid,layers:[],kind:'plain'});
for(const suffix of ['Blind 2147483648%','STR↑ (2147483648 turns)','Damage dealt to enemies with Seal +2147483648%']) {
 const source='[Physical] '+suffix;assert.deepEqual(new RuntimeText(model).render(source),{text:source,layers:[],kind:'plain'},'Compact header cannot revive a rejected native parameter');
}
fs.writeFileSync('generated/r21-reported-final-render.json',JSON.stringify({wire_path:receipt.wire_path,cases,whole_conflict_refused:true,type17_overflow_refused:true,game_attached:false,pixels_verified:false},null,2));
fs.writeFileSync('generated/r21-complete-production.json',JSON.stringify({wire_sha256:receipt.wire_sha256,rows:cases.map(c=>{
 const tr=new RuntimeText(model);return {...c,primary:tr.translate(c.source,'primary'),secondary:tr.translate(c.source,'secondary')};
}),game_attached:false,pixels_verified:false},null,2));
console.log(JSON.stringify({final_render_cases:cases.length,passed:true,pixels_verified:false}));
