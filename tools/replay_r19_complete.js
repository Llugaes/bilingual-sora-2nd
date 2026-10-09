'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const sourceRoot=require('node:path').resolve(__dirname,'..');
const baseline=process.argv.includes('--baseline');
const production=process.argv.includes('--production');
const {RuntimeText}=require(baseline?sourceRoot+'/sora_bilingual/game/scripts/runtime_text.js':'../sora_bilingual/game/scripts/runtime_text.js');
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const receipt=production?JSON.parse(fs.readFileSync('generated/r19-production-receipt.json','utf8')):null;
const bytes=fs.readFileSync(production?receipt.wire_path:sourceRoot+'/dist/comprehensive-1.0.0-dev5-r18/DEV/generated/runtime-cfc71a4c822cbac5a77b.wire.bin');
const originalModel=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const delta=baseline||production?null:JSON.parse(fs.readFileSync('generated/r19-effect-contract-delta.json','utf8'));
const patterns=new Set(delta?.units.map(r=>r.pattern)),sources=new Set(delta?.units.map(r=>r.source));
const model=baseline||production?originalModel:{...originalModel,
  skill_help_headers:JSON.parse(fs.readFileSync('generated/r19-skill-header-contract.json','utf8')),
  details:{...originalModel.details,
    detail_effect_units:[...originalModel.details.detail_effect_units,...delta.units],
    detail_effect_blocked_numeric:originalModel.details.detail_effect_blocked_numeric.filter(p=>!patterns.has(p)),
    detail_effect_rejections:originalModel.details.detail_effect_rejections.filter(r=>!sources.has(r.source))}};
const tr=new RuntimeText(model),snapshot=JSON.parse(fs.readFileSync('generated/r19-existing-owner-snapshot.json','utf8'));
const cases=snapshot.rows.map(r=>({name:'actual_Physical_Impede_Back',level:'resident original',source:r.original,
  key:r.text_key||'',scope:r.scope||'',forbidden:['Physical','Impede','Back Attack Bonus'],minimumRoles:3}));
const desc=model.detail_sources.find(s=>s.length>40&&!s.includes('%')&&model.details.pairs[s]);
cases.push({name:'CP_color_FORMAT8',level:'resource constructor fixture',source:'<c698>STR<I270> (5 turns)</C><c698>, </C><c698>CP Regen</C><c698>, </C><c698>Cure Stat Debuff</C>\n<C0>'+desc,forbidden:['CP Regen'],minimumRoles:3});
for(const names of ['Burn/Confuse/Deathblow','Mute/Freeze'])cases.push({name:'condition_'+names,level:'resource constructor fixture',
  source:'<c698>Resist '+names+' 100%</C>\n<C0>'+desc,forbidden:[names],minimumRoles:1});
if(production) {
  cases.push({name:'HP_regen_complete_header',level:'resource constructor fixture',
    source:'<C3></C>[Enhance - <I299><C3>Self</C>] <c698>HP Regen</C>',
    forbidden:['HP Regen'],minimumRoles:1});
  cases.push({name:'observed_Debilitate_Mute200',level:'observed owned buffer; original identity not captured',
    source:'<C3></C>[Debilitate - <I298><C3>All</C>] <c698>Impede</C><c698>, </C><c698>Mute 200%</C><c698>, </C><c698>Remove Buffs</C>',
    forbidden:['Debilitate','All','Impede','Mute','Remove Buffs'],minimumRoles:1});
  const atomic=model.details.detail_effect_units.find(r=>r.atomic);
  cases.push({name:'native_atomic_recovery',level:'resource constructor fixture',
    source:atomic.source.replace(/%d/g,'25').replace(/%%/g,'%')+'\n<C0>'+desc,
    forbidden:[],minimumRoles:1,maximumRoles:1});
}
const rows=cases.map(row=>{
  const primary=tr.translate(row.source,'primary',row.key||'',row.scope||''),secondary=tr.translate(row.source,'secondary',row.key||'',row.scope||'');
  const plan=tr.render(row.source,'annotation',row.key||'',row.scope||''),visible=plan.text+plan.layers.map(l=>l.text).join('');
  const failures=[];
  for(const word of row.forbidden)if(visible.includes(word))failures.push('final EN: '+word);
  if(plan.layers.filter(l=>l.semantic_ids?.length).length<row.minimumRoles)failures.push('semantic roles');
  if(row.maximumRoles&&plan.layers.filter(l=>l.semantic_ids?.length).length>row.maximumRoles)failures.push('native aggregate split');
  const header=tr.skillHeader?.(row.source);
  const tail=header?row.source.slice(header.end):null;
  const units=tail?tr.details.effectUnits(tail):null;
  return {...row,primary,secondary,plan,failures,header,tail,units,unitFailure:tail?tr.details.effectUnitFailures.get(tail):null};
});
const result={baseline,production,wire_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
  owner_injected:false,model_modified:!baseline&&!production,
  header_metadata:production?'complete production compiler + indexed wire':baseline?'actual r18 wire':'candidate compiler from actual full catalogue',
  rows,failures:rows.filter(r=>r.failures.length).length,live_candidate_verified:false,
  effect_probe:['Impede','Blind 30%','Back Attack Bonus','Side Attack Bonus'].map(s=>({source:s,unit:tr.details.effectUnit(s),
    blocked:tr.details.detailEffectBlockedLiterals.has(s),rejections:model.details.detail_effect_rejections?.filter(r=>r.source===s),
    rows:model.details.detail_effect_units.filter(r=>r.source===s||r.source==='Blind %d%%'),
    rejected:model.details.detail_effect_rejections?.filter(r=>s.startsWith('Blind')&&r.source==='Blind %d%%'),
    numeric:s.startsWith('Blind')?model.details.numeric.filter(r=>r[0].includes('Blind')).slice(0,8):undefined}))};
if(production) {
  const actual=cases[0].source,conflict=new RuntimeText({...model,
    ambiguous_display:[...model.ambiguous_display,actual,actual.replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,'')]});
  assert.equal(conflict.effectDetailPlan(actual),null);
  assert.deepEqual(conflict.render(actual),{text:actual,layers:[],kind:'plain'});
  result.conflict={rejected:true,owner:null};
  result.integer_boundaries=['-2147483648','2147483647','101','-2147483649','2147483648','9'.repeat(100)].map(value=>{
    const input=actual.replace('Blind 30%','Blind '+value+'%'),accepted=Number(value)>=-2147483648&&Number(value)<=2147483647;
    assert.equal(!!tr.details.effectUnit('Blind '+value+'%'),accepted);
    if(!accepted)assert.deepEqual(tr.render(input),{text:input,layers:[],kind:'plain'});
    return {value,accepted};
  });
  result.unresolvedTips=['Orbments','Tactical Bonus','Stealing AT Bonuses','Overdrive','Changing Battle Difficulty'].map(source=>({source,
    global:tr.render(source),list:tr.render(source,'annotation','','note_help_title'),
    details_simulated:tr.render(source,'annotation','','tips_title'),
    actual_input_captured:false,actual_scope_captured:false,live_verified:false}));
  result.unresolvedTerminal=['[Check new recipes]','[Verify Crystals]','[Quit using terminal]','[Yes]','[No]'].map(source=>({source,plan:tr.render(source),
    actual_input_captured:false,live_verified:false}));
}
fs.writeFileSync('generated/r19-complete-'+(production?'production':baseline?'baseline':'candidate')+'.json',JSON.stringify(result,null,2));
console.log(JSON.stringify({baseline,rows:rows.map(r=>({name:r.name,level:r.level,failures:r.failures,roles:r.plan.layers.filter(l=>l.semantic_ids).length})),failures:result.failures}));
assert.equal(result.failures,0,'full original → final annotation still fails');
