'use strict';
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {RuntimeText}=require(path.join(process.cwd(),'sora_bilingual/game/scripts/runtime_text.js'));
const model=JSON.parse(fs.readFileSync('generated/r26-p0-python-isolation-model.json','utf8'));
const cases=JSON.parse(fs.readFileSync('generated/r26-p0-python-body-isolation.json','utf8')).cases;
let checks=0;
for(const row of cases) {
 const source=row.source,head=source.slice(0,source.indexOf('\n')),tr=new RuntimeText(model);
 for(const mode of ['primary','secondary','annotation']) {
  const plan=tr.render(source,mode);assert.deepEqual(plan,row.modes[mode]);assert.equal(tr.translate(source,mode),plan.text);checks++;
  for(const bad of [head,head+'\nUnowned resource body']) {
   assert.deepEqual(tr.render(bad,mode),{text:bad,layers:[],kind:'plain'});assert.equal(tr.translate(bad,mode),bad);checks++;
  }
 }
 const pair=['完全な優先翻訳','完整优先译文'];
 const authoritative={...model,pairs:{...model.pairs,[source]:pair}},complete=new RuntimeText(authoritative),baseline=new RuntimeText({...authoritative,item_help_headers:null});
 const keyedModel={...model,keyed:{...model.keyed,actual_field:{source,model:{pairs:{[source]:pair},plain_pairs:{[source]:pair}}}}};
 const keyed=new RuntimeText(keyedModel),keyBase=new RuntimeText({...keyedModel,item_help_headers:null});
 for(const mode of ['primary','secondary','annotation']) {
  assert.deepEqual(complete.render(source,mode),baseline.render(source,mode));assert.equal(complete.translate(source,mode),baseline.translate(source,mode));checks++;
  assert.deepEqual(keyed.render(source,mode,'actual_field'),keyBase.render(source,mode,'actual_field'));checks++;
 }
 const conflict=new RuntimeText({...authoritative,ambiguous_display:[...(model.ambiguous_display||[]),source]});
 for(const mode of ['primary','secondary','annotation']) {
  assert.deepEqual(conflict.render(source,mode),{text:source,layers:[],kind:'plain'});assert.equal(conflict.translate(source,mode),source);checks++;
 }
}
const receipt={js_checks:checks,body_refusal_render_translate_equal:true,unowned_body_refused:true,complete_and_keyed_authority_not_bypassed:true,whole_conflict_not_bypassed:true,game_attached:false};
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
