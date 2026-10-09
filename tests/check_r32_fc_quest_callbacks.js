'use strict';
// Independent official-record oracle, existing simulated-pointer harness,
// and the current production callbacks. No game attach or producer build.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p)),json=p=>JSON.parse(read(p));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
function option(name){const at=process.argv.indexOf(name);if(at<0)return null;assert(process.argv[at+1]&&!process.argv[at+1].startsWith('--'),`missing value for ${name}`);return process.argv[at+1];}
function fileSha(p){const h=crypto.createHash('sha256'),fd=fs.openSync(p,'r'),buffer=Buffer.alloc(1024*1024);try{let n;while((n=fs.readSync(fd,buffer,0,buffer.length,null)))h.update(buffer.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');}
const productArg=option('--product'),product=productArg?path.resolve(productArg):null,runtimeRoot=product||root;
const readRuntime=p=>fs.readFileSync(path.join(runtimeRoot,p));
const freeze=json('generated/r32-coverage-source-freeze.json');
const scriptNames=['native_agent.js','native_transport.js','runtime_text.js','runtime_paragraph.js','runtime_identity.js'];
const scripts='sora_bilingual/game/scripts/';
const sourceHashes=Object.fromEntries(scriptNames.map(f=>[scripts+f,sha(readRuntime(scripts+f))]));
let cache=null,cacheSha=null,packageAudit=null,packageAuditPath=null,packageAuditSha=null;
if(product){
 for(const [p,digest] of Object.entries(sourceHashes))assert.equal(digest,freeze.files[p],`packaged source differs from current freeze: ${p}`);
 cache=JSON.parse(fs.readFileSync(path.join(product,'candidate-cache.json'),'utf8'));cacheSha=fileSha(path.join(product,'candidate-cache.json'));
 assert.equal(cache.source_snapshot_sha256,freeze.snapshot_sha256);assert.equal(cache.config_matrix.length,5);
 packageAuditPath=path.resolve(option('--package-audit')||path.join(root,'generated/r32-local8-package-audit.json'));
 packageAudit=JSON.parse(fs.readFileSync(packageAuditPath,'utf8'));packageAuditSha=fileSha(packageAuditPath);
 assert.equal(packageAudit.source_snapshot_sha256,freeze.snapshot_sha256);
 assert.equal(packageAudit.native_agent_matches_frozen_bytes,true);assert.equal(packageAudit.native_identity_and_contract_files_exact_r25,true);
 assert.equal(packageAudit.warm_entry_without_cold_compile,true);assert.equal(packageAudit.wire_bytes_and_mtime_unchanged,true);
 assert.equal(packageAudit.warm_models.length,5);
 const archiveSha=option('--archive-sha256');if(archiveSha)assert.equal(packageAudit.package_sha256,archiveSha);
}
const fixture=json('tests/fixtures/r32-fc-quest-complete-physical-records.json');
const components=json('generated/r32-local8-fc-component-models.json');
let core=read('tests/test_native_agent.js').toString('utf8');core=core.slice(0,core.indexOf('\ntest('));
if(product){const prefix="process.env.NATIVE_AGENT_SOURCE||";assert(core.includes(prefix));core=core.replace(prefix,'');}
const zeros='00000000000000000000000000000000';
core=core.replace('            quest_builder:',`            fc_quest_builder:{rva:0x7100,bytes:'${zeros}'},\n            fc_quest_paragraph_ready:{rva:0x7200,bytes:'${zeros}'},\n            fc_quest_line_return:{rva:0x7300,bytes:'${zeros}'},\n            quest_builder:`);
const block=core.match(/        questBegin\(currentThread=1\) \{[\s\S]*?        questEnd\(call,currentThread=1\) \{[\s\S]*?\n        \},/)[0];
const fcblock=block.replaceAll('questBegin','fcQuestBegin').replaceAll('questParagraph','fcQuestParagraph').replaceAll('questLine','fcQuestLine').replaceAll('questEnd','fcQuestEnd').replaceAll('REPORT.native.quest_','REPORT.native.fc_quest_');
core=core.replace(block,fcblock+'\n'+block);
const moduleOut={exports:{}};new Function('require','__dirname','module',core+'\nmodule.exports={makeRuntime};')(require,product?path.join(product,'tests'):__dirname,moduleOut);
const actualWire=process.argv.includes('--actual-wire')||Boolean(product);
const readIndexed=actualWire?new Function('rpc',readRuntime(scripts+'native_transport.js').toString('utf8')+';return readIndexedModel;')({exports:{}}):null;
const split=s=>s.split(/\r\n|\n|\\n/),norm=s=>String(s).replace(/<[^<>]*>/g,'').replace(/\s/gu,'');
function secondary(plan){
 if(plan.kind==='layered')return (plan.layers||[]).map(x=>x.text).join('\n');
 if(plan.kind!=='ruby')return plan.text;
 let out='',at=0;for(;;){const begin=plan.text.indexOf('<R>',at);if(begin<0)break;out+=plan.text.slice(at,begin);const close=plan.text.indexOf('</R',begin+3),end=plan.text.indexOf('>',close+3);assert(close>=0&&end>=0);out+=plan.text.slice(close+3,end);at=end+1;}return out+plan.text.slice(at);
}
const report={source_snapshot_sha256:freeze.snapshot_sha256,scope:'component fixture compiler and actual current callbacks with simulated pointers; not game rendering or a complete production model',source_sha256:sourceHashes,fixture_sha256:sha(read('tests/fixtures/r32-fc-quest-complete-physical-records.json')),harness_sha256:sha(read('tests/test_native_agent.js')),component_models_sha256:sha(read('generated/r32-local8-fc-component-models.json')),cases:[],failures:[],game_attached:false,production_written:false};
report.actual_complete_wire=actualWire;report.actual_wire_provenance=[];
report.actual_packaged_wire=Boolean(product);report.runtime_source_root=runtimeRoot;
if(product)report.package={product_root:product,package_audit_path:packageAuditPath,package_audit_sha256:packageAuditSha,archive_sha256_verified_by_root:packageAudit.package_sha256,archive_rehashed_by_this_check:false,candidate_cache_sha256_before:cacheSha,source_sha256_before:sourceHashes,product_written:false};
let checks=0,address=0xf00000;function check(name,fn){try{fn();checks++;}catch(e){report.failures.push({name,message:e.message,actual:e.actual,expected:e.expected});}}
function frame(r,source,thread=51){const f=r.fcQuestBegin(thread);r.fcQuestParagraph(source,thread);return f;}
function emit(r,source,thread=51,caller){return split(source).slice(0,-1).map(line=>{const label=r.label(address+=0x1000,'');r.fcQuestLine(label,line,thread,caller);return label;});}
function snapshot(r,label){const id=r.api.snapshot(true).rows.find(x=>x.pointer===String(label));assert(id,'identity snapshot lacks fixture pointer');return r.api.snapshot().find(x=>x.original===id.original&&x.displayed===id.displayed&&x.input_identity_diagnostic?.input===id.input_identity_diagnostic?.input);}
for(const config of components.configs){
 if(actualWire){
  const receipt=json(`generated/r32-coverage-${config.label}-production-receipt.json`);assert.equal(receipt.source_snapshot_sha256,freeze.snapshot_sha256);
  assert.equal(receipt.config.game_language,config.source);assert.equal(receipt.config.primary,config.primary);assert.equal(receipt.config.secondary,config.secondary);
  let wirePath=receipt.wire_path,modelPath=null,selected=null;
  if(product){
   const rows=cache.config_matrix.filter(x=>{try{assert.deepEqual(x.config,receipt.config);return true;}catch{return false;}});assert.equal(rows.length,1,'require one exact candidate-cache config');selected=rows[0];
   assert.equal(path.basename(selected.wire_name),selected.wire_name);assert.equal(path.basename(selected.model_name),selected.model_name);
   wirePath=path.join(product,'generated',selected.wire_name);modelPath=path.join(product,'generated',selected.model_name);
   assert.equal(selected.wire_sha256,receipt.wire_sha256);assert.equal(cache.files['generated/'+selected.wire_name],receipt.wire_sha256);
   assert.equal(fileSha(modelPath),receipt.model_sha256);assert.equal(cache.files['generated/'+selected.model_name],receipt.model_sha256);
   const audited=packageAudit.warm_models.filter(x=>{try{assert.deepEqual(x.config,receipt.config);return true;}catch{return false;}});assert.equal(audited.length,1);assert.equal(audited[0].wire_sha256,receipt.wire_sha256);
  }
  const bytes=fs.readFileSync(wirePath),before=fs.statSync(wirePath);assert.equal(sha(bytes),receipt.wire_sha256);config.model=readIndexed(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length));assert(config.model.scoped?.fc_quest_notes);
  report.actual_wire_provenance.push({label:config.label,config:receipt.config,source_snapshot_sha256:receipt.source_snapshot_sha256,receipt_sha256:sha(read(`generated/r32-coverage-${config.label}-production-receipt.json`)),wire_path:wirePath,wire_sha256:receipt.wire_sha256,model_path:modelPath,model_sha256:receipt.model_sha256,wire_size_before:before.size,wire_mtime_ms_before:before.mtimeMs});
 }
 const r=moduleOut.exports.makeRuntime(null,true),entries=[193,195,197].map(n=>fixture.entries.find(x=>x.ordinal===n));assert(entries.every(Boolean));
 const source=entries.map(x=>x.texts[config.source]+'\n').join(''),sourceLines=split(source).slice(0,-1);
 const expected=language=>entries.flatMap(x=>{const a=split(x.texts[config.source]),b=split(x.texts[language]);assert(b.length<=a.length,'selected independent official hard-line frame must fit');return b.concat(Array(a.length-b.length).fill(''));});
 r.api.load(config.model,'secondary',true,1);const f=frame(r,source);const labels=emit(r,source);r.fcQuestEnd(f,51);
 const sec=labels.map(x=>x.text());check(config.label+'/secondary-official-full-lines',()=>assert.deepEqual(sec,expected(config.secondary)));
 r.api.select('primary',true);labels.forEach(x=>r.update(x));check(config.label+'/primary-official-full-lines',()=>assert.deepEqual(labels.map(x=>x.text()),expected(config.primary)));
 r.api.select('annotation',true);labels.forEach(x=>r.update(x));const plans=labels.map(x=>{const row=snapshot(r,x);return {text:x.text(),kind:row.presentation,layers:row.layers||[],diagnostic:row.input_identity_diagnostic};});
 check(config.label+'/annotation-complete-official',()=>assert.equal(norm(plans.map((plan,i)=>norm(sec[i])?secondary(plan):'').join('\n')),norm(entries.map(x=>x.texts[config.secondary]).join('\n'))));
 check(config.label+'/scope',()=>assert(plans.every(x=>x.diagnostic.paragraph_scope==='fc_quest_notes')));
 check(config.label+'/primary-source-exact',()=>{if(config.primary===config.source)assert.deepEqual(labels.map((x,i)=>snapshot(r,x).original),sourceLines);});
 r.api.disable();labels.forEach(x=>r.update(x));check(config.label+'/disable-restores-source',()=>assert.deepEqual(labels.map(x=>x.text()),sourceLines));
 r.api.select('secondary',true);labels.forEach(x=>r.update(x));check(config.label+'/reenable-complete',()=>assert.deepEqual(labels.map(x=>x.text()),sec));
 labels.forEach(x=>r.destroy(x));
 const one=entries[0].texts[config.source]+'\n';
 let negative=frame(r,one,52),bad=r.label(address+=0x1000,'');r.fcQuestLine(bad,split(one)[0],52,null);check(config.label+'/wrong-caller',()=>assert(!snapshot(r,bad).input_identity_diagnostic.paragraph_scope));r.fcQuestEnd(negative,52);r.destroy(bad);
 negative=frame(r,one,53);r.fcQuestEnd(negative,53);bad=r.label(address+=0x1000,'');r.fcQuestLine(bad,split(one)[0],53);check(config.label+'/expired-frame',()=>assert(!snapshot(r,bad).input_identity_diagnostic.paragraph_scope));r.destroy(bad);
 negative=frame(r,one,54);r.api.configure({},true,1);bad=r.label(address+=0x1000,'');r.fcQuestLine(bad,split(one)[0],54);check(config.label+'/configure-clears-frame',()=>assert(!snapshot(r,bad).input_identity_diagnostic.paragraph_scope));r.fcQuestEnd(negative,54);r.destroy(bad);r.api.load(config.model,'secondary',true,1);
 for(const [kind,oversize] of [['bytes','字'.repeat(3000)+'\n'],['slots','x\n'.repeat(257)]]){negative=frame(r,oversize,55);bad=r.label(address+=0x1000,'');r.fcQuestLine(bad,split(one)[0],55);check(config.label+'/budget-'+kind,()=>assert(!snapshot(r,bad).input_identity_diagnostic.paragraph_scope));r.fcQuestEnd(negative,55);r.destroy(bad);}
 const unknownSource=entries[0].texts[config.source]+'<Q>',unknownModel={pairs:{},plain_pairs:{},scoped:{fc_quest_notes:{pairs:{[unknownSource]:[entries[0].texts[config.primary],entries[0].texts[config.secondary]]}}}};
 r.api.load(unknownModel,'secondary',true,1);negative=frame(r,unknownSource+'\n',56);const u=emit(r,unknownSource+'\n',56);r.fcQuestEnd(negative,56);check(config.label+'/unknown-control-source-refused',()=>assert.deepEqual(u.map(x=>x.text()),split(unknownSource)));u.forEach(x=>r.destroy(x));
 for(const side of [0,1]){const clean=entries[0].texts[config.source],pair=[entries[0].texts[config.primary],entries[0].texts[config.secondary]];pair[side]+='<Q>';r.api.load({pairs:{},plain_pairs:{},scoped:{fc_quest_notes:{pairs:{[clean]:pair}}}},'secondary',true,1);negative=frame(r,clean+'\n',59);const v=emit(r,clean+'\n',59);r.fcQuestEnd(negative,59);check(config.label+'/unknown-control-target-'+side,()=>assert.deepEqual(v.map(x=>x.text()),split(clean)));v.forEach(x=>r.destroy(x));}
 r.api.load(config.model,'secondary',true,1);
 if(config.source==='en'){
  const fc=fixture.entries.find(x=>x.ordinal===197),sc=components.sc_engine,full=fc.texts.en+'\n';assert.equal(fc.texts.en,sc.texts.en);
  const outside=r.label(address+=0x1000,'');r.externalSet(outside,fc.texts.en);check(config.label+'/global-FC-SC-conflict-quarantined',()=>assert.equal(outside.text(),fc.texts.en));r.destroy(outside);
  const outer=frame(r,full,57),inner=r.questBegin(57);r.questParagraph(full,57);const scLabels=split(full).slice(0,-1).map(line=>{const label=r.label(address+=0x1000,'');r.questLine(label,line,57);return label;});r.questEnd(inner,57);
  const fcLabels=emit(r,full,57);r.fcQuestEnd(outer,57);
  check(config.label+'/nested-SC-FC-owner-isolation',()=>{assert.equal(norm(scLabels.map(x=>x.text()).join('\n')),norm(sc.texts[config.secondary]));assert.equal(norm(fcLabels.map(x=>x.text()).join('\n')),norm(fc.texts[config.secondary]));assert.notEqual(norm(scLabels.map(x=>x.text()).join('\n')),norm(fcLabels.map(x=>x.text()).join('\n')));});[...scLabels,...fcLabels].forEach(x=>r.destroy(x));
 }
 check(config.label+'/native-failed-false',()=>assert.equal(r.api.status().failed,false));
 report.cases.push({label:config.label,source,record_keys:entries.map(x=>x.key),actual_secondary:sec,expected_secondary:expected(config.secondary),annotation_plans:plans,three_modes:true});
 if(product){const row=report.actual_wire_provenance.at(-1),after=fs.statSync(row.wire_path);assert.equal(after.size,row.wire_size_before);assert.equal(after.mtimeMs,row.wire_mtime_ms_before);assert.equal(fileSha(row.wire_path),row.wire_sha256);assert.equal(fileSha(row.model_path),row.model_sha256);row.wire_and_model_bytes_unchanged=true;}
}
report.check_count=checks;report.failure_count=report.failures.length;
if(actualWire)report.scope='Five actual complete indexed wires, independent official FC record oracle and current production callbacks with simulated pointers; not game rendering';
if(product){report.scope='Five actual sealed-package indexed wires, exact candidate-cache configurations, package JS callbacks and independent unchanged official FC record oracle with simulated pointers; not game rendering';report.package.candidate_cache_sha256_after=fileSha(path.join(product,'candidate-cache.json'));assert.equal(report.package.candidate_cache_sha256_after,cacheSha);report.package.source_sha256_after=Object.fromEntries(scriptNames.map(f=>[scripts+f,sha(readRuntime(scripts+f))]));assert.deepEqual(report.package.source_sha256_after,sourceHashes);report.package.package_audit_sha256_after=fileSha(packageAuditPath);assert.equal(report.package.package_audit_sha256_after,packageAuditSha);report.package.bytes_unchanged=true;}
const out=path.resolve(option('--out')||path.join(root,`generated/r32-local8-fc-callback-${product?'packaged':actualWire?'wire':'component'}.json`));if(product)assert(!fs.existsSync(out),'refuse to overwrite previous packaged FC evidence');fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({out,sha256:sha(fs.readFileSync(out)),check_count:checks,failure_count:report.failure_count,failures:report.failures}));process.exitCode=report.failure_count?1:0;
