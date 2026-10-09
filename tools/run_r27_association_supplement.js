'use strict';
// Read-only actual wire -> actual renderer. No key, scope or native owner is invented.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),audit=path.join(root,'generated/r27-association-audit');
const language=process.argv[2];
const readJson=name=>JSON.parse(fs.readFileSync(name,'utf8'));
const shaBytes=value=>crypto.createHash('sha256').update(value).digest('hex');
function shaFile(name) {
 const fd=fs.openSync(name,'r'),hash=crypto.createHash('sha256'),buffer=Buffer.alloc(1024*1024);
 try{let count;while((count=fs.readSync(fd,buffer,0,buffer.length,null)))hash.update(buffer.subarray(0,count));}finally{fs.closeSync(fd);}
 return hash.digest('hex');
}
function pythonJson(value) {
 if(Array.isArray(value))return '['+value.map(pythonJson).join(', ')+']';
 if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+': '+pythonJson(value[key])).join(', ')+'}';
 return JSON.stringify(value);
}
const freeze=readJson(path.join(root,'generated/r26-p0-local-source-freeze.json'));
const packetPath=process.argv[4]||path.join(audit,'inputs.json');
const packet=readJson(packetPath);
const receipts=readJson(path.join(audit,'builds/build001/receipts.json'));
const receipt=receipts.find(row=>row.source_language===language);
assert(receipt,'source language receipt missing');
const out=path.join(audit,process.argv[3]||'replay001',language);fs.mkdirSync(out,{recursive:true});
assert(!fs.existsSync(path.join(out,'summary.json')),'preserve prior replay artifacts; use new replay ID');
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const transport=fs.readFileSync(path.join(root,'sora_bilingual/game/scripts/native_transport.js'),'utf8');
const decode=new Function('rpc',transport+';return readIndexedModel;')({exports:{}});
const decodeWire=name=>{const bytes=fs.readFileSync(name);return decode(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));};
const stable=value=>JSON.stringify(value);
function content(value) {
 // Content comparison removes controls but does not fold glyph width, spaces or newlines.
 return value.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1').replace(/<[^<>]*>/g,'');
}
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
const modes=['primary','secondary','annotation'];
function evaluate(plans,source,texts) {
 const expected={primary:content(texts.ja),secondary:content(texts['zh-Hans']),annotation:content(texts.ja)};
 const results={};
 for(const mode of modes) {
  const actual=content(plans[mode].text),required=expected[mode];
  let result=actual===required?'associated':actual===content(source)?'source_only':'partial_or_wrong';
  const detail={status:result,visible_actual:actual,visible_expected:required};
  if(mode==='annotation') {
   // Same-language official content is a valid identity result; annotation is unnecessary.
   const needed=RuntimeText.needsAnnotation(texts.ja,texts['zh-Hans']);
   const rendered=needed?secondary(plans[mode]):plans[mode].text;
   detail.secondary_visible=rendered===null?null:content(rendered);
   detail.secondary_expected=expected.secondary;
   detail.secondary_required=needed;
   if(needed&&detail.secondary_visible!==expected.secondary) {
    detail.status=actual===content(source)&&!plans[mode].layers.length?'source_only':'partial_or_wrong';
    detail.annotation_secondary_mismatch=true;
   }
  }
  results[mode]=detail;
 }
 return results;
}
function reason(tr,source,plans,results) {
 if(tr.wholeConflict(source))return 'whole_source_conflict_requires_proven_context';
 const rejection=tr.effectUnitFailures.get(source)||tr.details?.effectUnitFailures.get(source);
 if(rejection)return rejection;
 if(results.annotation?.annotation_secondary_mismatch&&results.primary?.status==='associated'&&results.secondary?.status==='associated')return 'annotation_plan_secondary_incomplete';
 if(Object.values(plans).every(plan=>plan.text===source&&!plan.layers.length))return 'no_empty_context_full_input_association';
 return 'fallback_or_target_reconstruction_difference';
}
let binding;
try {
 assert.equal(receipt.config.game_language,language);
 assert.deepEqual(receipt.config,{primary:'ja',secondary:'zh-Hans',game_language:language,scope:'all',sources:[]});
 assert.equal(shaBytes(pythonJson(receipt.config)),receipt.config_sha256);
 assert.equal(receipt.source_snapshot_sha256,freeze.snapshot_sha256);
 assert.equal(packet.provenance.source_snapshot_sha256,freeze.snapshot_sha256);
 for(const [file,hash]of Object.entries(freeze.files))assert.equal(shaFile(path.join(root,file)),hash,file);
 assert.equal(shaFile(receipt.model_path),receipt.model_sha256,'actual model bytes');
 assert.equal(shaFile(receipt.wire_path),receipt.wire_sha256,'actual wire bytes');
 assert.equal(path.basename(receipt.model_path).replace(/\.json$/,'.wire.bin'),path.basename(receipt.wire_path));
 if(language==='en') {
  const cache=readJson(path.join(root,'dist/comprehensive-1.0.0-dev5-r26-p0-local3/DEV/candidate-cache.json'));
  assert.deepEqual(receipt.config,cache.config);assert.equal(receipt.wire_sha256,cache.wire_sha256);
 }else assert.deepEqual(receipt.signature,packet.provenance.signature);
 binding={status:'bound',source_language:language,config:receipt.config,config_sha256:receipt.config_sha256,model_sha256:receipt.model_sha256,
  wire_sha256:receipt.wire_sha256,source_snapshot_sha256:freeze.snapshot_sha256,build_id:packet.build_id,
  inputs_sha256:shaFile(packetPath),runtime_text_sha256:shaFile(path.join(root,'sora_bilingual/game/scripts/runtime_text.js')),
  native_transport_sha256:shaFile(path.join(root,'sora_bilingual/game/scripts/native_transport.js')),source_config_wire_build_gate:true,
  source_language_evidence:'prepare_request config/signature/unique model+wire cache ID+content SHA and audited language-specific full-producer inputs; model format has no standalone source-language field'};
}catch(error) {
 fs.writeFileSync(path.join(out,'binding-failure.json'),JSON.stringify({status:'build_binding_failed',message:error.message,receipt},null,2));throw error;
}
const model=decodeWire(receipt.wire_path),tr=new RuntimeText(model);
assert(!model.item_help_identities,'retired native identity revived');
let oldTr=null,oldBinding=null;
if(language==='en'&&process.env.R27_COMPARE_R25==='true') {
 const prior=readJson(path.join(root,'generated/r25-production-receipt.json'));
 assert.equal(shaFile(prior.wire_path),prior.wire_sha256);
 const oldScript=path.join(root,'generated/r26-p0-validation-r25/runtime_text.js');
 assert.equal(shaFile(oldScript),prior.runtime_js_sha256);
 const OldRuntime=require(oldScript).RuntimeText;oldTr=new OldRuntime(decodeWire(prior.wire_path));
 oldBinding={wire_sha256:prior.wire_sha256,runtime_text_sha256:prior.runtime_js_sha256,comparison:'actual r25 full English wire and byte-exact r25 renderer'};
}
const cache=new Map(),oldCache=new Map();
function renderAll(runtime,input,memo) {
 if(memo.has(input))return memo.get(input);
 const plans=Object.fromEntries(modes.map(mode=>[mode,runtime.render(input,mode,'','')]));memo.set(input,plans);return plans;
}
const sanity=packet.records.filter(row=>row.layer==='proven_complete_p0_producer').map(row=>{
 const source=row.texts[language],plans=renderAll(tr,source,cache);
 return {id:row.id,source,texts:row.texts,plans,results:evaluate(plans,source,row.texts)};
});
// A bound true-input failure is a real product miss, not an excuse to discard or rebuild it.
fs.writeFileSync(path.join(out,'entry-sanity.json'),JSON.stringify({binding,producer_results:sanity,
 failed_modes:sanity.reduce((total,row)=>total+Object.values(row.results).filter(mode=>mode.status!=='associated').length,0)},null,2));
const files={misses:fs.openSync(path.join(out,'unassociated.jsonl'),'wx'),unknown:fs.openSync(path.join(out,'unpaired-or-template.jsonl'),'wx'),differences:fs.openSync(path.join(out,'r25-differences.jsonl'),'wx')};
const counts={},reasonCounts={},differenceCounts={},modeChecks={primary:0,secondary:0,annotation:0};
const distinct={};const add=(object,key,n=1)=>object[key]=(object[key]||0)+n;
const emit=(key,row)=>fs.writeSync(files[key],JSON.stringify(row)+'\n');
let completed=0;const replayStart=Date.now();
try {
 for(const row of packet.records.filter(row=>!row.sanity_only)) {
  completed++;
  if(completed<=3||completed%500===0)console.log(JSON.stringify({phase:'replaying',language,completed,total:packet.records.length,seconds:(Date.now()-replayStart)/1000}));
  const source=row.texts[language],group=counts[row.layer]||(counts[row.layer]={records:0,blank:0,source_absent:0,template:0,unpaired:0,comparable:0,associated_all_modes:0,unassociated_any_mode:0,modes:{}});
  group.records++;
  if(typeof source!=='string'){group.source_absent++;continue;}
  if(!source.trim()){group.blank++;continue;}
  if(row.input_class==='template_resource') {group.template++;emit('unknown',{...row,source_language:language,source,reason:'format_resource_not_a_complete_runtime_input'});continue;}
  const plans=renderAll(tr,source,cache);
  if(typeof row.texts.ja!=='string'||typeof row.texts['zh-Hans']!=='string'||!row.texts.ja.trim()||!row.texts['zh-Hans'].trim()||row.ambiguous_locales?.ja||row.ambiguous_locales?.['zh-Hans']) {
   group.unpaired++;emit('unknown',{...row,source_language:language,source,plans,reason:'official_target_pairing_missing_or_ambiguous'});continue;
  }
  group.comparable++;
  const results=evaluate(plans,source,row.texts),failed=Object.values(results).some(result=>result.status!=='associated');
  const layerDistinct=distinct[row.layer]||(distinct[row.layer]={comparable:new Set(),unassociated:new Set()});layerDistinct.comparable.add(source);
  for(const mode of modes) {
   const bucket=group.modes[mode]||(group.modes[mode]={});add(bucket,results[mode].status);modeChecks[mode]++;
  }
  if(failed) {
   group.unassociated_any_mode++;layerDistinct.unassociated.add(source);
   const why=reason(tr,source,plans,results);add(reasonCounts,row.layer+'/'+why);
   emit('misses',{...row,source_language:language,source,official_primary:row.texts.ja,official_secondary:row.texts['zh-Hans'],plans,results,reason:why,
    evidence_boundary:'Actual product wire/render with empty runtime context; does not prove on-screen reachability, missing native owner or original SetText controls.'});
  }else group.associated_all_modes++;
  if(oldTr) {
   const priorPlans=renderAll(oldTr,source,oldCache);
   if(stable(plans)!==stable(priorPlans)) {
    const oldResults=evaluate(priorPlans,source,row.texts),oldFailed=Object.values(oldResults).some(result=>result.status!=='associated');
    const direction=oldFailed&&!failed?'improved':!oldFailed&&failed?'regressed':'changed_same_association_status';
    add(differenceCounts,row.layer+'/'+row.category+'/'+direction);
    emit('differences',{id:row.id,resource_key:row.resource_key,physical:row.physical,layer:row.layer,category:row.category,source,texts:row.texts,prior_plans:priorPlans,current_plans:plans,prior_results:oldResults,current_results:results,direction});
   }
  }
 }
}finally{for(const fd of Object.values(files))fs.closeSync(fd);}
const distinctCounts=Object.fromEntries(Object.entries(distinct).map(([layer,value])=>[layer,{comparable_sources:value.comparable.size,unassociated_sources:value.unassociated.size}]));
const summary={binding,source_language:language,primary:'ja',secondary:'zh-Hans',modes,counts,distinct_counts:distinctCounts,mode_checks:modeChecks,reason_counts:reasonCounts,
 sanity_failed_modes:sanity.reduce((total,row)=>total+Object.values(row.results).filter(mode=>mode.status!=='associated').length,0),
 r25_binding:oldBinding,r25_difference_counts:differenceCounts,r25_comparison_limit:oldTr?null:'Full source-language r25 wire is not available. No eight-language r25 parity is claimed.',
 game_attached:false,actual_setter_captured:false,performance_claim:null};
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify({language,counts,distinct_counts:distinctCounts,sanity_failed_modes:summary.sanity_failed_modes,r25_difference_counts:differenceCounts}));
