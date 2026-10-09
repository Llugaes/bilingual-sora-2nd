'use strict';
const fs=require('fs'),assert=require('node:assert/strict');
const receipt=JSON.parse(fs.readFileSync('generated/r22-production-receipt.json','utf8'));
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+';return readIndexedModel;')({exports:{}});
const bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const role=model.details.detail_effect_units.find(r=>r.atomic&&r.source==='Recover %d%% HP/EP, Cure Status Ailments, Cure Stat Debuff');
assert.ok(role,'reuse the independent valid composite role, not an invalid placeholder probe');
const member=role.source.replace(/%d/g,'30').replace(/%%/g,'%'),source='[Support] '+member;
assert.ok(new RuntimeText(model).render(source).text!==source,'valid compound remains admitted');
const results=[];
for(const kind of ['duplicate_valid_unit','compiler_style_blocked_template']){
 const details={...model.details};
 if(kind==='duplicate_valid_unit')details.detail_effect_units=[...details.detail_effect_units,{...role,pair:['veto%d','conflict%d']}];
 else{details.detail_effect_units=details.detail_effect_units.filter(r=>r.source!==role.source);details.detail_effect_blocked_numeric=[...details.detail_effect_blocked_numeric,role.pattern];}
 const negative={...model,details};
 for(const mode of ['annotation','primary','secondary']){
  const fresh=new RuntimeText(negative),plan=fresh.render(source,mode);
  assert.equal(plan.text,source,kind+'/'+mode);assert.equal(plan.layers.length,0);assert.equal(fresh.ownerPair(source),null);
 }
 results.push({kind,passed:true,source,negative_model_perturbation:true});
}
const unknown='[Support] HP Regen, UnprovenEffect 30%';
for(const mode of ['annotation','primary','secondary']){
 const plan=new RuntimeText(model).render(unknown,mode),output=plan.text+' '+plan.layers.map(l=>l.text).join(' ');
 assert.ok(plan.text.includes('UnprovenEffect 30%'),'unknown pure text remains literal');
 assert.ok(!output.includes('HP Regen'),'independent known role remains admitted');
}
fs.writeFileSync('generated/r22-rev2-shared-refusal.json',JSON.stringify({wire:receipt.wire_sha256,results,
 unknown_partial_preserved:true,positive_model_modified:false,game_attached:false},null,2));
console.log(JSON.stringify({negative_guards:results.length,three_final_modes:true,unknown_partial_preserved:true}));
