'use strict';
// Empty key/scope/owner throughout; fixture provenance remains explicit.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const product=path.resolve(process.argv[2]||'.'),input=process.argv[3]||'generated/r30-tools-producers-eight-languages.json',prefix=process.argv[4]||'r30-tools-producers-eight-languages';
const {RuntimeText}=require(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'));
const priorRoot=path.resolve('dist/comprehensive-1.0.0-dev5-r29-tools-local1/DEV');
const {RuntimeText:Prior}=require(path.join(priorRoot,'sora_bilingual/game/scripts/runtime_text.js'));
const modes=['primary','secondary','annotation'],data=JSON.parse(fs.readFileSync(input,'utf8')),runtimes=new Map(),priors=new Map(),failures=[],before=[],bodyDiffs=[],rows=[];
const wireReceipt=process.argv[5]?JSON.parse(fs.readFileSync(process.argv[5],'utf8')):null;
let completeModel=null,priorModel=null,wireHash=null;
function readWire(root,file,expected){
 const bytes=fs.readFileSync(file),hash=crypto.createHash('sha256').update(bytes).digest('hex');assert.equal(hash,expected);
 const read=new Function('rpc',fs.readFileSync(path.join(root,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
 return read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
}
if(wireReceipt){
 const cachePath=path.join(product,'candidate-cache.json');
 const file=fs.existsSync(cachePath)?path.join(product,'generated',JSON.parse(fs.readFileSync(cachePath,'utf8')).wire_name):wireReceipt.wire_path;
 completeModel=readWire(product,file,wireReceipt.wire_sha256);wireHash=wireReceipt.wire_sha256;
 const oldCache=JSON.parse(fs.readFileSync(path.join(priorRoot,'candidate-cache.json'),'utf8'));
 priorModel=readWire(priorRoot,path.join(priorRoot,'generated',oldCache.wire_name),oldCache.wire_sha256);
}
const controls=text=>text.match(/<I\d+>|<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g)||[];
const visible=text=>text.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'');
function secondary(plan){
 if(!plan.layers.length)return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_m,base,reading)=>base?reading:'');
 let text=plan.text,at=0;
 for(const layer of plan.layers){const anchor=text.indexOf('<R></R_>',at);if(anchor<0||!text.startsWith(layer.primary,anchor+8))return null;text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);at=anchor+layer.text.length;}
 return text;
}
const same=(a,b,name)=>{try{assert.deepEqual(a,b);}catch{failures.push({name,actual:a,expected:b});}};
let checks=0,guards=0,bodyChecks=0;
for(const row of data.cases){
 if(wireReceipt&&row.locale!=='en')continue;
 if(!runtimes.has(row.locale)){
  runtimes.set(row.locale,new RuntimeText(completeModel||JSON.parse(fs.readFileSync(input.replace(/\.json$/,`-${row.locale}-model.json`),'utf8'))));
  priors.set(row.locale,new Prior(priorModel||JSON.parse(fs.readFileSync(`generated/r29-tools-producers-eight-languages-${row.locale}-model.json`,'utf8'))));
 }
 const tr=runtimes.get(row.locale),old=priors.get(row.locale),plans={};
 for(const mode of modes){
  const plan=tr.render(row.source,mode,'','');
  same(plan,row.modes[mode],row.locale+'/'+row.name+'/'+mode+'/python-js');
  same(visible(plan.text),visible(row.texts[mode==='secondary'?'zh-Hans':'ja']),row.name+'/'+mode+'/primary');
  if(mode==='annotation'&&RuntimeText.needsAnnotation(row.texts.ja,row.texts['zh-Hans']))same(visible(secondary(plan)||''),visible(row.texts['zh-Hans']),row.name+'/complete-secondary');
  same(controls(plan.text),controls(row.texts[mode==='secondary'?'zh-Hans':'ja']),row.name+'/complete-controls');
   if(mode==='annotation')same(controls(secondary(plan)||''),controls(row.texts['zh-Hans']),row.name+'/secondary-controls');
  const oldPlan=old.render(row.source,mode,'','');
  if(visible(oldPlan.text)!==visible(row.texts[mode==='secondary'?'zh-Hans':'ja']))before.push({name:row.name,locale:row.locale,mode,plan:oldPlan});
  const body=row.source.slice(row.source.indexOf('\n')+1),a=tr.render(body,mode,'',''),b=old.render(body,mode,'','');
  if(JSON.stringify(a)!==JSON.stringify(b))bodyDiffs.push({name:row.name,locale:row.locale,mode,current:a,r29:b});
  bodyChecks++;checks++;plans[mode]=plan;
 }
 if(row.locale==='en'){
  const conflict=new RuntimeText({...tr.model,ambiguous_display:[...(tr.model.ambiguous_display||[]),row.source]});
  for(const mode of modes){same(conflict.render(row.source,mode),{text:row.source,layers:[],kind:'plain'},row.name+'/whole-conflict/'+mode);guards++;}
  for(const broken of [row.source.replace(/<I(?:351|352|347|348|378|379|380|381|382)>/,'<I999>'),
      row.source.replace(/(<I(?:351|352|347|348|378|379|380|381|382)>)/,'$1<Q>'),
      row.source.replace(/(?:6000|1500|1800|MAX HP\+20|ADF\+5)/,m=>m.replace(/\d+/, '2147483648'))]){
   if(broken===row.source)continue;
   for(const mode of modes){const p=tr.render(broken,mode);same(p.text.startsWith(broken.split('\n')[0]+'\n'),true,row.name+'/unproved-header/'+mode);same(p.layers.some(l=>l.semantic_ids?.length),false,row.name+'/unproved-role/'+mode);guards++;}
  }
 }
 rows.push({...row,modes:plans});
}
same(bodyDiffs,[],'standalone body plans unchanged from r29');
const result={complete_mode_plans:checks,body_plans_compared_to_r29:bodyChecks,body_differences:bodyDiffs,refusal_checks:guards,
 r29_red_plan_count:before.length,r29_red_plans:before,failure_count:failures.length,failures,rows,
 wire_sha256:wireHash,actual_wire_loaded:!!wireReceipt,source_snapshot_sha256:wireReceipt?.source_snapshot_sha256,
 runtime_text_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'))).digest('hex'),
 full_original_setter_captured:false,actual_english_header_captured:false,positive_identity_supplied:false,game_attached:false};
fs.writeFileSync('generated/'+prefix+'-js.json',JSON.stringify(result,null,2));
console.log(JSON.stringify({...result,rows:undefined,r29_red_plans:undefined,failures:failures.slice(0,3)}));
process.exitCode=failures.length?1:0;
