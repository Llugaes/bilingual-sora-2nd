'use strict';
// Final renderer replay over an independent raw denominator; never model-filter
// cases or supply a positive owner. No Frida/game attachment is involved.
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto');
const product=path.resolve(process.argv[2]||'dist/comprehensive-1.0.0-dev5-r24/DEV');
const prefix=process.argv[3]||'r25-r24-producers';
const wirePath=process.argv[4]||path.join(product,'generated',JSON.parse(fs.readFileSync(path.join(product,'candidate-cache.json'))).wire_name);
const packetPath=process.argv[5]||'generated/r25-producer-denominator.json';
const packet=JSON.parse(fs.readFileSync(packetPath,'utf8'));
const {RuntimeText}=require(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'));
const wire=fs.readFileSync(wirePath),context={rpc:{exports:{}},File:{readAllBytes:()=>wire.buffer.slice(wire.byteOffset,wire.byteOffset+wire.byteLength)}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/native_transport.js'),'utf8'),context);
context.rpc.exports.load=model=>{context.model=model;return true;};context.rpc.exports.modelpackedfile('raw-producers.wire.bin');
const runtime=new RuntimeText(context.model),memo=new Map(),rows=[],totals={},bySurface={},gaps=[];
const normal=value=>value.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'').replace(/\r\n/g,'\n');
const fold=value=>normal(value).replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0));
function secondary(plan) {
 if(!plan.layers.length)return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_m,base,reading)=>base?reading:'');
 let text=plan.text,at=0;
 for(const layer of plan.layers) {
  const anchor=text.indexOf('<R></R_>',at);
  if(anchor<0||typeof layer.primary!=='string'||!text.startsWith(layer.primary,anchor+8))return null;
  text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);at=anchor+layer.text.length;
 }
 return text;
}
for(const row of packet.cases) {
 const source=row.texts.en,key=JSON.stringify([source,row.texts.ja,row.texts['zh-Hans']]);let result=memo.get(key);
 if(!result) {
  const modes={};
  for(const mode of ['primary','secondary','annotation']) {
   const plan=runtime.render(source,mode,'',''),expected=row.texts[mode==='secondary'?'zh-Hans':'ja'];
   const visible=normal(plan.text),match=visible===normal(expected),sameWidth=fold(plan.text)===fold(expected);
   const reading=mode==='annotation'?secondary(plan):null;
   const secondaryMatch=mode!=='annotation'||!RuntimeText.needsAnnotation(row.texts.ja,row.texts['zh-Hans'])||reading!==null&&normal(reading)===normal(row.texts['zh-Hans']);
   const roles=plan.layers.filter(l=>l.semantic_ids?.length).map(l=>({ids:l.semantic_ids,parameters:l.parameters,text:l.text,primary:l.primary}));
   modes[mode]={plan,primary_matches:match,width_equivalent:sameWidth,secondary_matches:secondaryMatch,
    reconstructed_secondary:reading,semantic_roles:roles};
  }
  let status=Object.values(modes).every(m=>m.primary_matches&&m.secondary_matches)?'passed':
   Object.values(modes).every(m=>m.width_equivalent&&(m.secondary_matches||m.reconstructed_secondary!==null&&fold(m.reconstructed_secondary)===fold(row.texts['zh-Hans'])))?'width_equivalent':'difference';
  if(status==='difference'&&Object.values(modes).every(m=>normal(m.plan.text)===normal(source)))status='source_retained';
  result={modes,status};memo.set(key,result);
 }
 const record={id:row.id,surface:row.surface,source,texts:row.texts,level:row.level,resource_key:row.resource_key,entity_id:row.entity?.id,...result};
 if(row.expected_effect_units&&result.status==='passed'&&result.modes.annotation.plan.kind!=='plain'&&!result.modes.annotation.semantic_roles.length)record.role_status='translated_but_effect_role_not_proven';
 else if(row.expected_effect_units)record.role_status=result.status==='passed'?'semantic_roles_present':'complete_effect_output_not_matching';
 rows.push(record);totals[record.status]=(totals[record.status]||0)+1;
 bySurface[row.surface]??={};bySurface[row.surface][record.status]=(bySurface[row.surface][record.status]||0)+1;
 if(!['passed','width_equivalent'].includes(record.status)||record.role_status==='translated_but_effect_role_not_proven')gaps.push(record);
}
const result={scope:'physical raw entity and reachable known producer input probes; missing contracts and unverified entrances remain explicit',product,wire_path:path.resolve(wirePath),wire_sha256:crypto.createHash('sha256').update(wire).digest('hex'),runtime_text_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'))).digest('hex'),denominator_summary:packet.summary,classification:packet.classification,physical_cases:rows.length,unique_final_inputs:memo.size,totals,by_surface:bySurface,rows,contract_gaps:packet.gaps,game_attached:false,live_verified:false,owner_key_scope_supplied:false};
fs.writeFileSync('generated/'+prefix+'-final.json',JSON.stringify(result,null,2));
fs.writeFileSync('generated/'+prefix+'-gaps.json',JSON.stringify({totals,by_surface:bySurface,rows:gaps,contract_gaps:packet.gaps},null,2));
console.log(JSON.stringify({physical_cases:rows.length,unique_final_inputs:memo.size,totals,by_surface:bySurface,render_gaps:gaps.length,retained_contract_gaps:packet.gaps.length,game_attached:false}));
