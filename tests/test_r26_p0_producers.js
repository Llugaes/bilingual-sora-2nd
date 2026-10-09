'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const product=path.resolve(process.argv[2]||'.');
const input=process.argv[3]||'generated/r26-p0-producers-after.json';
const {RuntimeText}=require(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'));
const receipt=JSON.parse(fs.readFileSync(input,'utf8'));
const visible=value=>value.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'');
function secondary(plan) {
 if(!plan.layers.length)return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_m,base,reading)=>base?reading:'');
 let text=plan.text,at=0;
 for(const layer of plan.layers) {
  const anchor=text.indexOf('<R></R_>',at);
  assert(anchor>=0&&text.startsWith(layer.primary,anchor+8),'secondary anchor lost');
  text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);at=anchor+layer.text.length;
 }
 return text;
}
let checks=0,guards=0;
const runtimes=new Map();
for(const row of receipt.cases) {
 if(!runtimes.has(row.locale))runtimes.set(row.locale,new RuntimeText(JSON.parse(fs.readFileSync(input.replace(/\.json$/,`-${row.locale}-model.json`),'utf8'))));
 const tr=runtimes.get(row.locale);
 for(const mode of ['primary','secondary','annotation']) {
  const plan=tr.render(row.source,mode);
  assert.deepEqual(plan,row.modes[mode],row.locale+'/'+row.name+'/'+mode);
  assert.equal(visible(plan.text),visible(row.texts[mode==='secondary'?'zh-Hans':'ja']));
  if(mode==='annotation'&&RuntimeText.needsAnnotation(row.texts.ja,row.texts['zh-Hans']))assert.equal(visible(secondary(plan)),visible(row.texts['zh-Hans']),row.name+' complete secondary');
  checks++;
 }
 const conflict=new RuntimeText({...tr.model,ambiguous_display:[...(tr.model.ambiguous_display||[]),row.source]});
 for(const mode of ['primary','secondary','annotation']) {
  assert.deepEqual(conflict.render(row.source,mode),{text:row.source,layers:[],kind:'plain'});
  assert.equal(conflict.translate(row.source,mode),row.source);guards++;
 }
 if(row.locale==='en'&&!row.name.startsWith('junior/')) {
  const broken=row.name==='all_ep'?row.source.replace('<I352>','<I351>'):row.source.replace('STR+1','STR+2147483648');
  for(const mode of ['primary','secondary','annotation']) {
   const plan=tr.render(broken,mode),head=broken.split('\n')[0];
   assert(plan.text.startsWith(head+'\n'),'unproved effect granted header translation');
   assert(!plan.layers.some(l=>l.semantic_ids?.length),'unproved header granted effect role');guards++;
  }
 }
}
const output={python_js_complete_plans:checks,complete_secondary_verified:true,refusal_checks:guards,game_attached:false,actual_setter_captured:false};
if(process.argv[4])fs.writeFileSync(process.argv[4],JSON.stringify(output,null,2));
console.log(JSON.stringify(output));
