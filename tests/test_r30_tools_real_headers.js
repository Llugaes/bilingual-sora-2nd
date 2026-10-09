'use strict';
// Complete captured English headers, independently reconstructed resource body.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(process.argv[2]||'dist/comprehensive-1.0.0-dev5-r28-header-local1/DEV');
const fixture=process.argv[3]||'generated/r30-tools-real-failure-native-oracle.json';
const out=process.argv[4]||'generated/r29-tools-real-before.json';
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
let model,hash=null;
if(process.argv[5])model=JSON.parse(fs.readFileSync(process.argv[5],'utf8'));
else {
 const c=JSON.parse(fs.readFileSync(path.join(root,'candidate-cache.json'),'utf8'));
 const bytes=fs.readFileSync(path.join(root,'generated',c.wire_name));
 hash=crypto.createHash('sha256').update(bytes).digest('hex');
 if(hash!==c.wire_sha256)throw Error('actual wire hash differs from candidate');
 const read=new Function('rpc',fs.readFileSync(path.join(root,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
 model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
}
const tr=new RuntimeText(model);
const visible=text=>text.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'');
function secondary(p){
 let text=p.text,at=0;
 for(const layer of p.layers){
  const index=text.indexOf('<R></R_>',at);
  if(index<0||!text.startsWith(layer.primary,index+8))return null;
  text=text.slice(0,index)+layer.text+text.slice(index+8+layer.primary.length);
  at=index+layer.text.length;
 }
 return text;
}
const controls=text=>text.match(/<I\d+>|<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g)||[];
const failures=[],rows=[];let guards=0;
function equal(actual,expected,name){if(JSON.stringify(actual)!==JSON.stringify(expected))failures.push({name,actual,expected});}
for(const row of JSON.parse(fs.readFileSync(fixture,'utf8')).cases){
 const plans={};
 for(const mode of ['primary','secondary','annotation']){
  const p=tr.render(row.source,mode,'','');plans[mode]=p;
  const expected=row.texts[mode==='secondary'?'zh-Hans':'ja'];
  equal(visible(p.text),visible(expected),row.name+'/'+mode+'/complete-primary');
  equal(controls(p.text),controls(expected),row.name+'/'+mode+'/icons-colours');
  if(mode==='annotation'){
   const reading=secondary(p);equal(visible(reading||''),visible(row.texts['zh-Hans']),row.name+'/complete-secondary');
   equal(controls(reading||''),controls(row.texts['zh-Hans']),row.name+'/secondary-icons-colours');
  }else equal(p.text,expected,row.name+'/'+mode+'/exact-text-and-controls');
 }
 for(const broken of [row.source.replace('<I347>','<I999>'),row.source.replace('<I351>','<I351><Q>'),row.source.replace('CP+200','CP+2147483648'),row.source.replace('Revive','Re<C9>vive'),row.source.replace('<I351>','<I999>'),row.source.replace('75%','2147483648%'),row.source.replace('Recover','Re<C9>cover')]){
  if(broken===row.source)continue;
  for(const mode of ['primary','secondary','annotation']){
   const p=tr.render(broken,mode,'','');equal(p.text.split('\n')[0],broken.split('\n')[0],row.name+'/'+mode+'/unproved-header');guards++;
  }
 }
 const conflict=new RuntimeText({...model,ambiguous_display:[...(model.ambiguous_display||[]),row.source]});
 for(const mode of ['primary','secondary','annotation']){equal(conflict.render(row.source,mode),{text:row.source,layers:[],kind:'plain'},row.name+'/'+mode+'/whole-conflict');guards++;}
 rows.push({...row,plans});
}
const result={wire_sha256:hash,actual_wire_loaded:hash!==null,product_root:root,complete_mode_plans:rows.length*3,refusal_checks:guards,failure_count:failures.length,failures,rows,game_attached:false};
fs.writeFileSync(out,JSON.stringify(result,null,2));
process.stdout.write(JSON.stringify({checks:result.complete_mode_plans,failures:failures.length,wire_sha256:hash})+'\n');
process.exitCode=failures.length?1:0;
