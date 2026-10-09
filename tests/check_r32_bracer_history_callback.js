'use strict';
// Whole physical constructors through the actual agent's existing pointer harness.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=process.cwd(),options={input:'generated/r32-bracer-history-component-input.json',
 output:'generated/r32-bracer-history-component-callback.json',
 baselineProduct:process.env.SORA_BASELINE_PRODUCT||'dist/r32-coverage-local3/DEV',fullWire:false,label:null,exportReplay:false};
for(let i=2;i<process.argv.length;i++){const key=process.argv[i];
 if(key==='--input')options.input=process.argv[++i];
 else if(key==='--output')options.output=process.argv[++i];
 else if(key==='--baseline-product')options.baselineProduct=process.argv[++i];
 else if(key==='--label')options.label=process.argv[++i];
 else if(key==='--full-wire')options.fullWire=true;
 else if(key==='--export-replay')options.exportReplay=true;
 else throw Error('unknown argument '+key);}
if(fs.existsSync(options.output))throw Error('never overwrite previous component evidence');
const json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const hash=p=>{const h=crypto.createHash('sha256'),fd=fs.openSync(p,'r'),chunk=Buffer.alloc(1<<20);
 try{let n;while((n=fs.readSync(fd,chunk,0,chunk.length,null)))h.update(chunk.subarray(0,n));}finally{fs.closeSync(fd);}return h.digest('hex');};
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const mapHash=v=>crypto.createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');
const input=json(options.input),freeze=json('generated/r32-coverage-source-freeze.json');
if(input.source_snapshot_sha256!==freeze.snapshot_sha256)throw Error('stale component input');
for(const [name,value] of Object.entries(input.production_source_sha256))
 if(hash(name)!==value||freeze.files[name]!==value)throw Error('source differs from component freeze: '+name);
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const directory=path.join(root,'tests'),harnessPath=path.join(directory,'test_native_agent.js');
const scriptNames=['native_agent.js','runtime_text.js','runtime_paragraph.js','runtime_identity.js'];
function makeHarness(product){
 let core=fs.readFileSync(harnessPath,'utf8');core=core.slice(0,core.indexOf('\ntest('));
 for(const [variable,file] of [['AGENT',scriptNames[0]],['RESOLVER',scriptNames[1]],['PARAGRAPHS',scriptNames[2]],['IDENTITIES',scriptNames[3]]])
  core=core.replace(new RegExp('const '+variable+' = [^\\n]+'),()=>`const ${variable} = ${JSON.stringify(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts',file),'utf8'))};`);
 // Count the existing fixture's label ancestry dependencies as well as owned text.
 // This adds counters to test doubles; it adds no read to production callbacks.
 core=core.replace('const memoryCost={scalarReads:0,blockReads:0,scalarWrites:0,blockWrites:0,textReads:0};',
  'const memoryCost={scalarReads:0,blockReads:0,scalarWrites:0,blockWrites:0,textReads:0,nodePointerReads:0,nodeStringReads:0};');
 core=core.replace('readPointer() {\n            if(this.offset===0x680)',
  'readPointer() {\n            memoryCost.nodePointerReads++;\n            if(this.offset===0x680)');
 core=core.replace('readPointer() { return this.vtable; }','readPointer() { memoryCost.nodePointerReads++;return this.vtable; }');
 core=core.replace('readUtf8String() { return this.text; }','readUtf8String() { memoryCost.nodeStringReads++;return this.text; }');
 core=core.replace('readU32() {\n            if (this.offset === 0x2f4)',
  'readU32() {\n            memoryCost.scalarReads++;\n            if (this.offset === 0x2f4)');
 core=core.replace('readByteArray(size) {\n            const data=new ArrayBuffer(size)',
  'readByteArray(size) {\n            memoryCost.blockReads++;\n            const data=new ArrayBuffer(size)');
 core=core.replace('readFloat() {if(this.label.matrix.has(this.offset))',
  'readFloat() {memoryCost.scalarReads++;if(this.label.matrix.has(this.offset))');
 core=core.replace('return {\n        api: sandbox.rpc.exports,',
  `return {\n        heldResolver(){return vm.runInContext('resolver',context);},\n        heldPlan(label){sandbox.readbackPointer=String(label);const result=vm.runInContext('labels.get(readbackPointer)?.plan',context);delete sandbox.readbackPointer;return result;},\n        api: sandbox.rpc.exports,`);
 for(const marker of ['memoryCost.nodePointerReads++;','memoryCost.nodeStringReads++;','heldPlan(label)'])
  if(!core.includes(marker))throw Error('fixture instrumentation anchor absent: '+marker);
 const moduleOut={exports:{}};
 new Function('require','__dirname','module',core+'\nmodule.exports={makeRuntime};')(require,directory,moduleOut);
 return moduleOut.exports.makeRuntime;
}
const makeCurrent=makeHarness(root),makeOld=makeHarness(options.baselineProduct);
const oldHashes=Object.fromEntries(scriptNames.map(name=>[name,hash(path.join(options.baselineProduct,'sora_bilingual/game/scripts',name))]));
const red=json(input.prior_failure_receipt);
for(const [name,value] of Object.entries(red.current_source_sha256))
 if(oldHashes[name]!==value)throw Error('sealed old package code is not the preserved red baseline: '+name);
if(hash(input.prior_failure_receipt)!==input.prior_failure_receipt_sha256)throw Error('prior failure receipt changed');
const report={schema:1,kind:'bracer_history_component_and_actual_callback',source_snapshot_sha256:input.source_snapshot_sha256,
 input_path:path.resolve(options.input),input_sha256:hash(options.input),production_source_sha256:input.production_source_sha256,
 checker_path:__filename,checker_sha256:hash(__filename),
 harness_source_sha256:hash(harnessPath),baseline_product:path.resolve(options.baselineProduct),baseline_package_script_sha256:oldHashes,
 prior_failure_receipt:input.prior_failure_receipt,prior_failure_receipt_sha256:input.prior_failure_receipt_sha256,
 original_capture_sha256:input.capture_sha256,static_builder_sha256:input.static_builder_sha256,
 physical_constructor_count:1023,configuration_count:options.label?1:input.models.length,three_mode_plan_count:0,
 callback_mode_plan_count:0,counts:{},failures:[],complete_samples:[],negative_cases:[],wrong_scope_cases:[],read_budgets:[],
 scope:'actual production callbacks with existing simulated native pointers; no new attach, native identity or game pixels',
 component_model_only:!options.fullWire,actual_production_indexed_wire:options.fullWire,formal_wire_records:[],
 production_model_compiled:false,build_run:false,game_attached:false};
function check(ok,name,actual,expected){const group=name.split('/')[0];report.counts[group]=(report.counts[group]||0)+1;
 if(!ok)report.failures.push({name,actual,expected});}
function same(actual,expected,name){check(JSON.stringify(actual)===JSON.stringify(expected),name,actual,expected);}
function ordinals(mask){const flags=new Set(input.flags.filter((_,bit)=>mask&(1<<bit)));
 return input.physical_rows.filter(row=>flags.has(row.condition_u16)).map(row=>row.ordinal);}
function frame(i,sourceLocale,targetLocale){const row=input.physical_rows[i],source=row.texts[sourceLocale],target=row.texts[targetLocale];
 if(sourceLocale===targetLocale)return source;
 const left=source.split('\n'),right=target.split('\n');
 if(i===0){const starts=sourceLocale==='en'?[0,2]:[0,1],targetStarts=targetLocale==='en'?[0,2]:[0,1];
  const out=Array(left.length).fill('');for(let n=0;n<2;n++)out[starts[n]]=right.slice(targetStarts[n],targetStarts[n+1]??right.length).join(' ').trim();
  return out.join('\n');}
 return right.filter(Boolean).join(' ').trim()+'\n'.repeat(left.length-1);}
function body(indices,sourceLocale,targetLocale){return indices.map(i=>frame(i,sourceLocale,targetLocale)+'\n').join('');}
function oracle(a,b,mode){if(mode!=='annotation')return{text:mode==='primary'?a:b,layers:[],kind:'plain'};
 const left=a.split('\n'),right=b.split('\n');if(left.length!==right.length)throw Error('oracle frame length mismatch');
 let text='';const layers=[];left.forEach((line,i)=>{if(i)text+='\n';if(line&&right[i]&&line!==right[i]){
  layers.push({offset:Buffer.byteLength(text)+6,text:right[i],primary:line,protected:false});text+='<R></R_>';}
  text+=line;});return{text,layers,kind:'layered'};}
let address=0xa00000;
function tree(runtime,source,layout=61,leafToRoot=['history','top_page_contents','note_base','root']){
 const names=[...leafToRoot].reverse(),nodes=names.map((name,i)=>{const p=runtime.label(address+=0x1000,i===names.length-1?source:'');p.name=name;return p;});
 nodes.forEach((p,i)=>{if(i)p.parent=nodes[i-1];});if(layout!==null)runtime.registerLayout(nodes[0],layout);
 return{nodes,leaf:nodes.at(-1),root:nodes[0]};}
const delta=(after,before)=>Object.fromEntries(Object.keys(after).map(k=>[k,after[k]-before[k]]));
const readKeys=['scalarReads','blockReads','textReads','nodePointerReads','nodeStringReads'];
const modes=['primary','secondary','annotation'];
const selectedModels=input.models.filter(row=>!options.label||row.label===options.label);
if(selectedModels.length!==report.configuration_count)throw Error('unknown requested configuration');
for(const row of selectedModels){const label=row.label,r=makeCurrent(null,true);let model=row.model,wireRecord=null;
 if(options.fullWire){const receiptPath=`generated/r32-coverage-${label}-production-receipt.json`,receipt=json(receiptPath);
  if(receipt.source_snapshot_sha256!==freeze.snapshot_sha256)throw Error('stale full wire receipt '+label);
  for(const key of ['primary','secondary'])if(receipt.config[key]!==row[key])throw Error('wrong full wire target '+label+'/'+key);
  if(receipt.config.game_language!==row.game_language)throw Error('wrong source wire '+label);
  if(hash(receipt.wire_path)!==receipt.wire_sha256||hash(receipt.model_path)!==receipt.model_sha256)throw Error('formal model/wire SHA differs '+label);
  const before=fs.statSync(receipt.wire_path,{bigint:true}),transportPath='sora_bilingual/game/scripts/native_transport.js';
  if(hash(transportPath)!==freeze.files[transportPath])throw Error('transport differs from freeze');
  const read=new Function('rpc',fs.readFileSync(transportPath,'utf8')+';return readIndexedModel;')({exports:{}});
  const bytes=fs.readFileSync(receipt.wire_path),buffer=bytes.byteOffset===0&&bytes.byteLength===bytes.buffer.byteLength?bytes.buffer:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length);
  model=read(buffer);
  const actualScope=model.scoped?.bracer_history,expectedScope=row.model.scoped.bracer_history;
  check(Boolean(actualScope),`wire/${label}/serialized_scope_present`,Boolean(actualScope),true);
  check(actualScope?.bracer_history_frame===true,`wire/${label}/serialized_strict_frame_flag`,actualScope?.bracer_history_frame,true);
  same(canonical(actualScope?.pairs),canonical(expectedScope.pairs),`wire/${label}/serialized_complete_pairs`);
  check(Object.keys(actualScope?.pairs||{}).length===1023,`wire/${label}/serialized_pair_count`,Object.keys(actualScope?.pairs||{}).length,1023);
  wireRecord={label,config:receipt.config,receipt_path:path.resolve(receiptPath),receipt_sha256:hash(receiptPath),model_path:receipt.model_path,model_sha256:receipt.model_sha256,
   wire_path:receipt.wire_path,wire_sha256:receipt.wire_sha256,wire_size:String(before.size),wire_mtime_ns_before:String(before.mtimeNs),
   native_transport_sha256:hash(transportPath),bracer_history_frame:actualScope?.bracer_history_frame??null,
   scope_pairs_count:Object.keys(actualScope?.pairs||{}).length,scope_map_sha256_canonical:mapHash(actualScope),scope_pairs_sha256_canonical:mapHash(actualScope?.pairs),
   expected_component_pairs_sha256_canonical:mapHash(expectedScope.pairs)};
 }
 r.api.load(model,'primary',true,1);const tr=r.heldResolver(),live=tree(r,'');
 if(options.exportReplay){
  if(!options.fullWire)throw Error('replay export requires actual full wire');
  report.replay_rows=[];
  for(const mask of [1,512,1023]){const indices=ordinals(mask),source=body(indices,row.game_language,row.game_language),
   a=body(indices,row.game_language,row.primary),b=body(indices,row.game_language,row.secondary),saved={};
   for(const mode of modes){const actual=tr.render(source,mode,'','bracer_history');same(actual,oracle(a,b,mode),`js/${label}/${mask}/${mode}/export_complete_plan`);saved[mode]=actual;report.three_mode_plan_count++;}
   report.replay_rows.push({label,mask,ordinals:indices,source,modes:saved});
  }
  const after=fs.statSync(wireRecord.wire_path,{bigint:true});wireRecord.wire_mtime_ns_after=String(after.mtimeNs);
  wireRecord.wire_size_and_mtime_unchanged=String(after.size)===wireRecord.wire_size&&String(after.mtimeNs)===wireRecord.wire_mtime_ns_before;
  check(wireRecord.wire_size_and_mtime_unchanged,`wire/${label}/unchanged_export_wire`);report.formal_wire_records.push(wireRecord);
  r.api.disable();r.destroy(live.leaf);continue;
 }
 for(let mask=1;mask<1024;mask++){const indices=ordinals(mask),source=body(indices,row.game_language,row.game_language);
  const a=body(indices,row.game_language,row.primary),b=body(indices,row.game_language,row.secondary);
  for(const mode of modes){const expected=oracle(a,b,mode),actual=tr.render(source,mode,'','bracer_history');
   same(actual,expected,`js/${label}/${mask}/${mode}/complete_plan`);report.three_mode_plan_count++;
   check(actual.text.split('\n').length===a.split('\n').length,`frame/${label}/${mask}/${mode}/native_hard_slots`,actual.text.split('\n').length,a.split('\n').length);
   if(!options.fullWire||[1,512,1023].includes(mask)){
    r.api.select(mode,true);live.leaf.owned.text=source;live.leaf.dirty[0x688]=1;r.update(live.leaf);
    check(live.leaf.text()===expected.text,`callback/${label}/${mask}/${mode}/complete_text`,live.leaf.text(),expected.text);
    same(r.heldPlan(live.leaf),expected,`callback/${label}/${mask}/${mode}/complete_layers`);report.callback_mode_plan_count++;
   }
   if(mask===1023){const snap=r.api.snapshot(true).rows.find(v=>v.pointer===String(live.leaf));
    check(snap?.scope==='bracer_history',`identity/${label}/${mode}/scope`,snap?.scope,'bracer_history');
    check(snap?.input_identity_diagnostic?.phase==='owned_update',`identity/${label}/${mode}/phase`,snap?.input_identity_diagnostic?.phase,'owned_update');
    check(snap?.input_identity_diagnostic?.caller_rva===null,`identity/${label}/${mode}/no_invented_setter`,snap?.input_identity_diagnostic?.caller_rva,null);
    check(snap?.original===source,`identity/${label}/${mode}/original_exact`,snap?.original,source);
    check(snap?.input_identity_diagnostic?.layout_id===61,`identity/${label}/${mode}/layout61`,snap?.input_identity_diagnostic?.layout_id,61);
    same(snap?.input_identity_diagnostic?.node_path,['history','top_page_contents','note_base','root'],`identity/${label}/${mode}/exact_ancestry`);
    report.complete_samples.push({label,mask,source,mode,expected,actual,callback_text:live.leaf.text(),callback_plan:r.heldPlan(live.leaf),diagnostic:snap?.input_identity_diagnostic});}
  }
 }
 const full=body(ordinals(1023),row.game_language,row.game_language),a=body(ordinals(1023),row.game_language,row.primary),b=body(ordinals(1023),row.game_language,row.secondary);
 // Preserve the full original across mode changes and production disable.
 for(const mode of ['primary','secondary','annotation']){r.api.select(mode,true);r.update(live.leaf);
  same(r.heldPlan(live.leaf),oracle(a,b,mode),`lifecycle/${label}/${mode}/hot_switch_full_plan`);}
 const writes=r.api.status().writes,beforeClean={...r.memoryCost};live.leaf.dirty[0x688]=0;r.update(live.leaf);
 check(r.api.status().writes===writes,`lifecycle/${label}/unchanged_no_write`,r.api.status().writes,writes);
 check(r.memoryCost.textReads===beforeClean.textReads,`budget/${label}/clean_no_owned_decode`,r.memoryCost.textReads-beforeClean.textReads,0);
 r.api.disable();r.update(live.leaf);check(live.leaf.text()===full,`lifecycle/${label}/disable_restores_original`,live.leaf.text(),full);
 r.api.select('annotation',true);r.update(live.leaf);same(r.heldPlan(live.leaf),oracle(a,b,'annotation'),`lifecycle/${label}/reenable_full_layers`);
 const physical=input.physical_rows;
 const negative=[['unknown_suffix',full+'UNREGISTERED'],['unknown_control',full+'<Q>'],['known_control_not_in_builder',full+'<K>'],
  ['missing_final_LF',full.slice(0,-1)],['bare_initial_complete_body',physical[0].texts[row.game_language]],
  ['recommendation_fragment',physical[1].texts[row.game_language].split('\n')[0]],
  ['reordered_initial',body([1,0,2,3,4,5,6,7,8,9,10],row.game_language,row.game_language)],
  ['same_flag_ordinal9_alone',body([9],row.game_language,row.game_language)],
  ['same_flag_ordinal10_alone',body([10],row.game_language,row.game_language)],
  ['duplicate_initial',body([0,0],row.game_language,row.game_language)],['wrong_CRLF',full.replace(/\n/g,'\r\n')]];
 for(const [kind,source] of negative){const refused={text:source,layers:[],kind:'plain'};
  for(const mode of modes){same(tr.render(source,mode,'','bracer_history'),refused,`refusal/${label}/${kind}/${mode}/strict_whole`);
   r.api.select(mode,true);live.leaf.owned.text=source;live.leaf.dirty[0x688]=1;r.update(live.leaf);
   same(r.heldPlan(live.leaf),refused,`refusal/${label}/${kind}/${mode}/actual_callback_plan`);
   check(live.leaf.text()===source,`refusal/${label}/${kind}/${mode}/actual_original`,live.leaf.text(),source);}
  report.negative_cases.push({label,kind,source,expected:refused});}
 const wrong=[['wrong_layout60',60,['history','top_page_contents','note_base','root']],
  ['wrong_layout62',62,['history','top_page_contents','note_base','root']],
  ['unregistered_layout',null,['history','top_page_contents','note_base','root']],
  ['wrong_leaf',61,['text','top_page_contents','note_base','root']],
  ['wrong_parent',61,['history','other_contents','note_base','root']],
  ['wrong_note_base',61,['history','top_page_contents','other_base','root']],
  ['wrong_root',61,['history','top_page_contents','note_base','other_root']],
  ['missing_ancestor',61,['history','top_page_contents','root']],
  ['extra_ancestor',61,['history','top_page_contents','note_base','root','unregistered']]];
 for(const [kind,id,names] of wrong){const target=tree(r,full,id,names);
  for(const mode of modes){r.api.select(mode,true);target.leaf.owned.text=full;target.leaf.dirty[0x688]=1;r.update(target.leaf);
   const snap=r.api.snapshot(true).rows.find(v=>v.pointer===String(target.leaf));
   check(Boolean(snap),`scope/${label}/${kind}/${mode}/captured_owned_input_exists`,Boolean(snap),true);
   check(snap?.original===full,`scope/${label}/${kind}/${mode}/captured_original_exact`,snap?.original,full);
   check(snap?.scope!=='bracer_history',`scope/${label}/${kind}/${mode}/no_grant`,snap?.scope,'not bracer_history');
   same(r.heldPlan(target.leaf),tr.render(full,mode),`scope/${label}/${kind}/${mode}/existing_global_behavior`);}
  report.wrong_scope_cases.push({label,kind,layout_id:id,leaf_to_root:names});r.destroy(target.leaf);}
 // An actual new copy on reused controls must resolve the current layout again.
 r.registerLayout(live.root,60);r.api.select('annotation',true);live.leaf.owned.text=full;live.leaf.dirty[0x688]=1;r.update(live.leaf);
 check(r.api.snapshot(true).rows.find(v=>v.pointer===String(live.leaf))?.scope!=='bracer_history',`scope/${label}/dirty_layout_reuse_revokes`);
 check(r.api.status().failed===false,`native/${label}/failed`,r.api.status().failed,false);
 r.api.disable();r.destroy(live.leaf);
 // Same physical owned-update dependencies as the actual sealed pre-fix agent.
 if(!options.fullWire)for(const mode of modes){const old=makeOld(),now=makeCurrent();old.api.load(row.model,mode,true,1);now.api.load(row.model,mode,true,1);
  const oldTree=tree(old,full),nowTree=tree(now,full),oldBefore={...old.memoryCost},nowBefore={...now.memoryCost};
  old.update(oldTree.leaf);now.update(nowTree.leaf);const oldCost=delta(old.memoryCost,oldBefore),newCost=delta(now.memoryCost,nowBefore);
  for(const key of readKeys)check(newCost[key]<=oldCost[key],`budget/${label}/${mode}/${key}/no_new_cold_read`,newCost[key],oldCost[key]);
  oldTree.leaf.dirty[0x688]=0;nowTree.leaf.dirty[0x688]=0;const oldWarm={...old.memoryCost},nowWarm={...now.memoryCost};
  old.update(oldTree.leaf);now.update(nowTree.leaf);const oldWarmCost=delta(old.memoryCost,oldWarm),newWarmCost=delta(now.memoryCost,nowWarm);
  for(const key of readKeys)check(newWarmCost[key]<=oldWarmCost[key],`budget/${label}/${mode}/${key}/no_new_clean_read`,newWarmCost[key],oldWarmCost[key]);
  report.read_budgets.push({label,mode,old:oldCost,current:newCost,old_clean:oldWarmCost,current_clean:newWarmCost,
   old_small_component_text:oldTree.leaf.text(),current_complete_text:nowTree.leaf.text(),
   old_small_component_matches_live_capture:label==='en'&&mode==='annotation'?oldTree.leaf.text()===input.observed_displayed_before:null});
  old.api.disable();now.api.disable();old.destroy(oldTree.leaf);now.destroy(nowTree.leaf);}
 if(wireRecord){const after=fs.statSync(wireRecord.wire_path,{bigint:true});wireRecord.wire_mtime_ns_after=String(after.mtimeNs);
  wireRecord.wire_size_and_mtime_unchanged=String(after.size)===wireRecord.wire_size&&String(after.mtimeNs)===wireRecord.wire_mtime_ns_before;
  check(wireRecord.wire_size_and_mtime_unchanged,`wire/${label}/unchanged_actual_wire`);report.formal_wire_records.push(wireRecord);}
 console.log(JSON.stringify({label,complete_modes:1023*3,actual_callback_modes:options.fullWire?9:1023*3,failures_so_far:report.failures.length}));
 if(global.gc)global.gc();
}
for(const [name,value] of Object.entries(input.production_source_sha256))check(hash(name)===value,'source/unchanged/'+name,hash(name),value);
check(hash(input.prior_failure_receipt)===input.prior_failure_receipt_sha256,'source/prior_failure_unchanged');
report.failure_count=report.failures.length;
report.existing_native_dependency_read_budget_no_increase=options.fullWire?null:!report.failures.some(f=>f.name.startsWith('budget/'));
report.limitations=['Read budgets describe the existing pointer fixture, including name/parent reads; they are not Frida latency or gameplay FPS.',
 'Old read-budget comparison uses actual sealed old scripts with the same small catalog component; preserved original red receipt covers the old full production wire.',
 'Dirty native copied-string reuse and wrong initial ancestry are covered. Native story reachability and glyph layout require separate acceptance.'];
fs.writeFileSync(options.output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({output:options.output,source_snapshot_sha256:report.source_snapshot_sha256,three_mode_plan_count:report.three_mode_plan_count,
 callback_mode_plan_count:report.callback_mode_plan_count,counts:report.counts,failure_count:report.failure_count,
 first_failure_names:report.failures.slice(0,8).map(f=>f.name),existing_native_dependency_read_budget_no_increase:report.existing_native_dependency_read_budget_no_increase}));
process.exitCode=report.failure_count?1:0;
