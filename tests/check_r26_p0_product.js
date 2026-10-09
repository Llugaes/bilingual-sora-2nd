'use strict';
// Exact wire and actual product renderer. Positive inputs never receive owners.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const product=path.resolve(process.argv[2]||'.'),prefix=process.argv[3]||'r26-p0-local';
const receipt=JSON.parse(fs.readFileSync(process.argv[5]||'generated/r26-p0-local-production-receipt.json','utf8'));
const wirePath=process.argv[4]||receipt.wire_path;
const bytes=fs.readFileSync(wirePath),hash=crypto.createHash('sha256').update(bytes).digest('hex');
assert.equal(hash,receipt.wire_sha256);
const read=new Function('rpc',fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
const model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
assert(!model.item_help_identities,'retired native identities emitted');
const {RuntimeText}=require(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'));
const tr=new RuntimeText(model),modes=['primary','secondary','annotation'],failures=[],rows=[];
const normal=value=>value.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'');
function secondary(plan) {
 if(!plan.layers.length)return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_m,base,reading)=>base?reading:'');
 let text=plan.text,at=0;
 for(const layer of plan.layers) {
  const anchor=text.indexOf('<R></R_>',at);
  if(anchor<0||!text.startsWith(layer.primary,anchor+8))return null;
  text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);at=anchor+layer.text.length;
 }
 return text;
}
function same(actual,expected,name) {
 try{assert.deepEqual(actual,expected);}catch{failures.push({name,actual,expected});}
}
const old=JSON.parse(fs.readFileSync('generated/r25-stage5-qualified-original-producers-final.json','utf8'));
let oldChecks=0;
for(const row of old.rows) {
 const plans={};
 for(const mode of modes){const plan=tr.render(row.source,mode,'','');same(plan,row.modes[mode].plan,row.id+'/'+mode);oldChecks++;plans[mode]=plan;}
 rows.push({name:row.id,source:row.source,modes:plans});
}
const newInputs=JSON.parse(fs.readFileSync('generated/r26-p0-producers-after.json','utf8')).cases.filter(r=>r.locale==='en');
const tools=JSON.parse(fs.readFileSync('generated/r26-tools-real-producer-fixtures.json','utf8')).rows.filter(r=>r.locale==='en');
let newChecks=0,toolsChecks=0,guards=0;
for(const row of [...tools.map(r=>({...r,name:'Tools/'+r.physical,source:r.texts.en})),...newInputs]) {
 const plans={};
 for(const mode of modes) {
  const plan=tr.render(row.source,mode,'','');
  same(normal(plan.text),normal(row.texts[mode==='secondary'?'zh-Hans':'ja']),row.name+'/'+mode+'/primary');
  if(mode==='annotation'&&RuntimeText.needsAnnotation(row.texts.ja,row.texts['zh-Hans']))same(normal(secondary(plan)||''),normal(row.texts['zh-Hans']),row.name+'/secondary');
  if(row.name.startsWith('Tools/'))toolsChecks++;else newChecks++;
  plans[mode]=plan;
 }
 rows.push({name:row.name,source:row.source,modes:plans});
}
for(const row of newInputs) {
 const conflict=new RuntimeText({...model,ambiguous_display:[...(model.ambiguous_display||[]),row.source]});
 for(const mode of modes){same(conflict.render(row.source,mode),{text:row.source,layers:[],kind:'plain'},row.name+'/conflict/'+mode);guards++;}
 if(!row.name.startsWith('junior/')) {
  const broken=row.name==='all_ep'?row.source.replace('<I352>','<I351>'):row.source.replace('STR+1','STR+2147483648');
  for(const mode of modes){const plan=tr.render(broken,mode);same(plan.text.startsWith(broken.split('\n')[0]+'\n'),true,row.name+'/refusal/'+mode);same(plan.layers.some(l=>l.semantic_ids?.length),false,row.name+'/refusal-role/'+mode);guards++;}
 }
}
const result={source_snapshot_sha256:receipt.source_snapshot_sha256,wire_sha256:hash,wire_bytes:bytes.length,
 runtime_text_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'))).digest('hex'),
 old_full_mode_plans:oldChecks,new_producer_plans:newChecks,tools_mode_plans:toolsChecks,refusal_checks:guards,
 failure_count:failures.length,failures,rows,product,game_attached:false,actual_setter_captured:false};
fs.writeFileSync('generated/'+prefix+'-product-replay.json',JSON.stringify(result,null,2));
console.log(JSON.stringify({...result,failures:failures.slice(0,3),rows:undefined}));
process.exitCode=failures.length?1:0;
