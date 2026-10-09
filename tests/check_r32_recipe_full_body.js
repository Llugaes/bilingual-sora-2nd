'use strict';
// Exact saved compact constructor + matching official body, actual indexed wire.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),options={runtimeRoot:root};
for(let i=2;i<process.argv.length;i++){
 if(process.argv[i]==='--callbacks'){options.callbacks=true;continue;}
 if(process.argv[i]==='--callbacks-only'){options.callbacks=true;options.callbacksOnly=true;continue;}
 if(process.argv[i]==='--negative-only'){options.negativeOnly=true;continue;}
 const key=process.argv[i],fields={'--input':'input','--wire':'wire','--wire-sha256':'wireSha','--runtime-root':'runtimeRoot','--label':'label','--output':'output','--only-item-ids':'onlyItemIds'};
 if(!fields[key])throw Error('unknown argument '+key);options[fields[key]]=process.argv[++i];
}
for(const key of ['input','wire','wireSha','label','output'])assert(options[key],key+' required');
assert(!fs.existsSync(options.output),'never overwrite prior evidence');
const configMap={en:['en','en','zh-Hans'],ja:['ja','ja','zh-Hans'],'zh-Hans':['zh-Hans','zh-Hans','ja'],'zh-Hant':['zh-Hant','zh-Hant','ja'],'en-manual':['en','ja','zh-Hans']};
assert(configMap[options.label]);const [sourceLocale,primary,secondary]=configMap[options.label];
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex'),json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const input=json(options.input),bytes=fs.readFileSync(options.wire),before=fs.statSync(options.wire).mtimeMs;
assert.equal(sha(bytes),options.wireSha);const scripts=path.join(path.resolve(options.runtimeRoot),'sora_bilingual/game/scripts');
const scriptPaths={runtime_text:path.join(scripts,'runtime_text.js'),native_transport:path.join(scripts,'native_transport.js')};
const scriptHashes=Object.fromEntries(Object.entries(scriptPaths).map(([k,v])=>[k,sha(fs.readFileSync(v))]));
const read=new Function('rpc',fs.readFileSync(scriptPaths.native_transport,'utf8')+';return readIndexedModel;')({exports:{}});
const model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require(scriptPaths.runtime_text),tr=new RuntimeText(model);
const primaryText=text=>text.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1');
function secondaryText(plan){if(!plan.layers.length)return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_m,a,b)=>a?b:'');
 let text=plan.text,at=0;for(const layer of plan.layers){const anchor=text.indexOf('<R></R_>',at);assert(anchor>=0&&text.startsWith(layer.primary,anchor+8),'layer anchor/primary mismatch');
  text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);at=anchor+layer.text.length;}return primaryText(text);}
function semantics(text){const parts=text.normalize('NFKC').split(/(\r\n|\n|\\n)/);parts[0]=parts[0].replace(/\s+-\s+/g,'').replace(/[\[\]()【】:：/・･、]/g,'');
 return parts.join('').replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,'').replace(/\s/gu,'');}
function compare(plan,mode,expected){const a=primaryText(plan.text),b=mode==='annotation'?secondaryText(plan):null,pairs=[[a,mode==='secondary'?expected.secondary:expected.primary]];
 if(b!==null)pairs.push([b,expected.secondary]);const strict=pairs.every(([x,y])=>x===y),semantic=pairs.every(([x,y])=>semantics(x)===semantics(y));
 return{strict_equal:strict,complete_semantics_equal:semantic,classification:strict?'exact':semantic?'retained_native_frame':'semantic_or_field_mismatch',actual_primary:a,actual_secondary:b,expected_primary:expected.primary,expected_secondary:expected.secondary};}
const report={schema:1,label:options.label,wire_path:path.resolve(options.wire),wire_sha256:options.wireSha,wire_bytes:bytes.length,
 runtime_root:path.resolve(options.runtimeRoot),script_sha256:scriptHashes,input_path:path.resolve(options.input),input_sha256:sha(fs.readFileSync(options.input)),
 preserved_red_sha256:input.preserved_red_sha256,mode_plan_count:0,strict_failure_count:0,semantic_failure_count:0,
 normal_primary_source_failure_count:0,cases:[],failures:[],negative_cases:[],actual_capture_checks:[],production_compiled:false,build_run:false,game_attached:false};
const selected=input.cases.filter(c=>c.locale===sourceLocale);assert.equal(selected.length,314);
const focus=options.onlyItemIds?options.onlyItemIds.split(',').map(v=>{assert(/^\d+$/.test(v));return Number(v);}):null;
const positives=focus?selected.filter(c=>focus.includes(c.item_id)):selected;
report.original_source_case_denominator=selected.length;report.selected_source_case_denominator=positives.length;report.focus_item_ids=focus;
for(const c of options.callbacksOnly||options.negativeOnly?[]:positives){const expected={primary:c.texts[primary],secondary:c.texts[secondary]},record={item_id:c.item_id,join:c.join,source:c.source,modes:{}};
 for(const mode of ['primary','secondary','annotation']){const plan=tr.render(c.source,mode),comparison=compare(plan,mode,expected);record.modes[mode]={plan,comparison};report.mode_plan_count++;
  if(!comparison.strict_equal){report.strict_failure_count++;report.failures.push({item_id:c.item_id,join:c.join,source:c.source,mode,actual:plan,...comparison});}
  if(!comparison.complete_semantics_equal)report.semantic_failure_count++;
  if(options.label!=='en-manual'&&mode!=='secondary'&&primaryText(plan.text)!==c.source)report.normal_primary_source_failure_count++;
 }
 report.cases.push(record);
 if(options.label==='ja'&&c.source===input.actual_ja_75_units.original){for(const mode of ['primary','secondary','annotation'])report.actual_capture_checks.push({mode,source_code_units:c.source.length,actual_plan:record.modes[mode].plan,comparison:record.modes[mode].comparison,old_actual_displayed:input.actual_ja_75_units.displayed});}
}
const seed=selected.find(c=>c.item_id===2300&&c.join===' '),at=seed.source.indexOf('\n'),head=seed.source.slice(0,at),body=seed.source.slice(at+1);
const negatives=[['unknown_body',head+'\n'+body+' R32_UNKNOWN_BODY'],['unknown_header_control',head.replace('<C9>','<X998><C9>')+'\n'+body],['wrong_prefix','R32_WRONG_PREFIX'+head+'\n'+body]];
for(const [kind,source] of negatives)for(const mode of ['primary','secondary','annotation']){const plan=tr.render(source,mode),value=mode==='annotation'?secondaryText(plan):plan.text;
 report.negative_cases.push({kind,mode,source,actual:plan,header_remains_exact:value.split('\n')[0]===source.split('\n')[0],body_translation_permitted_only_if_whole_official_body:kind!=='unknown_body'});}
tr.ambiguousDisplay.add(seed.source);tr.planCache.clear();for(const mode of ['primary','secondary','annotation']){const plan=tr.render(seed.source,mode);
 report.negative_cases.push({kind:'whole_conflict_runtime_guard',mode,source:seed.source,actual:plan,header_remains_exact:plan.text===seed.source&&!plan.layers.length,guard_fixture:'test-only ambiguous display set; actual wire unchanged'});}
report.negative_failure_count=report.negative_cases.filter(c=>!c.header_remains_exact).length;
report.unknown_header_known_body_contract_assertions=report.negative_cases.filter(c=>c.kind==='wrong_prefix').map(c=>{
 const visible=c.mode==='annotation'?secondaryText(c.actual):c.actual.text,cut=visible.indexOf('\n'),sourceCut=c.source.indexOf('\n');
 const expectedBody=seed.body_texts[c.mode==='primary'?primary:secondary],parsed=tr.itemHelpHeader(c.source);
 return{mode:c.mode,source:c.source,source_header:c.source.slice(0,sourceCut),actual_header:visible.slice(0,cut),
  actual_body:visible.slice(cut+1),expected_complete_official_body:expectedBody,
  header_byte_exact:visible.slice(0,cut)===c.source.slice(0,sourceCut),complete_official_body_equal:visible.slice(cut+1)===expectedBody,
  compact_constructor_admitted:!!parsed?.parts?.some(p=>!p.opaque&&p.semantic_ids?.length),
  original_strict_failure_is_retained:!c.header_remains_exact};
});
tr.ambiguousDisplay.delete(seed.source);tr.planCache.clear();
report.body_proof_negative_cases=[];
if(sourceLocale==='zh-Hans'||sourceLocale==='zh-Hant'){
 const ambiguous=selected.find(c=>c.item_id===2116&&c.join===' '),end=ambiguous.source.indexOf('\n'),aHead=ambiguous.source.slice(0,end),aBody=ambiguous.source.slice(end+1);
 const opening=aHead.slice(0,aHead.indexOf('<C9>')),inner=aHead.slice(opening.length,-1),members=tr.details.effectUnits(inner,false,aBody,[' ',' ',' ']);
 assert(members&&members.filter(u=>!u.separator).length===2,'physical 2116 complete two-unit source');
 const units=members.filter(u=>!u.separator).map(u=>u.source);
 const mutations=[['body_proof_wrong_amount',aHead.replace('150','151')],
  ['body_proof_reordered_effects',opening+[...units].reverse().join(' ')+aHead.slice(-1)],
  ['body_proof_extra_known_effect',opening+inner+' '+units[0]+aHead.slice(-1)]];
 for(const [kind,mutated] of mutations)for(const mode of ['primary','secondary','annotation']){
  const source=mutated+'\n'+aBody,plan=tr.render(source,mode),value=mode==='annotation'?secondaryText(plan):plan.text;
  report.body_proof_negative_cases.push({kind,mode,source,actual:plan,ambiguous_official_body:aBody,
   physical_constructor_is_not_claimed:true,ambiguous_body_remains_exact:value.slice(value.indexOf('\n')+1)===aBody});
 }
}
report.body_proof_negative_failure_count=report.body_proof_negative_cases.filter(c=>!c.ambiguous_body_remains_exact).length;
if(options.callbacks){
 assert.equal(options.label,'ja','actual captured callback is JA only');
 const harnessPath=path.join(root,'tests/test_native_agent.js');let core=fs.readFileSync(harnessPath,'utf8');core=core.slice(0,core.indexOf('\ntest('));
 for(const [variable,file] of [['AGENT','native_agent.js'],['RESOLVER','runtime_text.js'],['PARAGRAPHS','runtime_paragraph.js'],['IDENTITIES','runtime_identity.js']])
  core=core.replace(new RegExp('const '+variable+' = [^\\n]+'),()=>`const ${variable} = ${JSON.stringify(fs.readFileSync(path.join(scripts,file),'utf8'))};`);
 core=core.replace('return {\n        api: sandbox.rpc.exports,',`return {\n        heldResolver(){return vm.runInContext('resolver',context);},\n        heldPlan(label){sandbox.readbackPointer=String(label);const result=vm.runInContext('labels.get(readbackPointer)?.plan',context);delete sandbox.readbackPointer;return result;},\n        api: sandbox.rpc.exports,`);
 assert(core.includes('heldPlan(label)'),'pointer harness instrumentation anchor');
 const moduleOut={exports:{}};new Function('require','__dirname','module',core+'\nmodule.exports={makeRuntime};')(require,path.join(root,'tests'),moduleOut);
 const runtime=moduleOut.exports.makeRuntime(null,true);runtime.api.load(model,'primary',true,1);
 const names=['root','note_base','normal_contents','success_info','text'],nodes=names.map((name,i)=>{const p=runtime.label(0xb10000+i*0x1000,'');p.name=name;return p;});
 nodes.forEach((p,i)=>{if(i)p.parent=nodes[i-1];});runtime.registerLayout(nodes[0],57);const leaf=nodes.at(-1),held=runtime.heldResolver();
 report.callback_checks=[];report.callback_failures=[];report.callback_source_sha256=Object.fromEntries(['native_agent.js','runtime_text.js','runtime_paragraph.js','runtime_identity.js'].map(name=>[name,sha(fs.readFileSync(path.join(scripts,name)))]));
 report.callback_harness_sha256=sha(fs.readFileSync(harnessPath));
 for(const [kind,source] of [['actual_ja_75_units',input.actual_ja_75_units.original],...negatives,['whole_conflict_runtime_guard',seed.source]]){
  const conflicting=kind==='whole_conflict_runtime_guard';if(conflicting){held.ambiguousDisplay.add(source);held.planCache.clear();tr.ambiguousDisplay.add(source);tr.planCache.clear();}
  for(const mode of ['primary','secondary','annotation']){
   const expected=tr.render(source,mode);runtime.api.select(mode,true);leaf.owned.text=source;leaf.dirty[0x688]=1;runtime.update(leaf);
   const actual=runtime.heldPlan(leaf),snap=runtime.api.snapshot(true).rows.find(row=>row.pointer===String(leaf));
   const complete=leaf.text()===expected.text&&JSON.stringify(actual?.layers||[])===JSON.stringify(expected.layers)&&(!actual||actual.kind===expected.kind);
   const diagnostic=snap?.input_identity_diagnostic,provenance=diagnostic?.phase==='owned_update'&&diagnostic.layout_id===57&&JSON.stringify(diagnostic.node_path)===JSON.stringify(['text','success_info','normal_contents','note_base','root']);
   const record={kind,mode,source,expected,actual_plan:actual??null,actual_text:leaf.text(),diagnostic,complete_plan_equal:complete,owned_input_provenance_exact:provenance};
   report.callback_checks.push(record);if(!complete||!provenance)report.callback_failures.push(record);
  }
  if(conflicting){held.ambiguousDisplay.delete(source);held.planCache.clear();tr.ambiguousDisplay.delete(source);tr.planCache.clear();}
 }
 runtime.api.select('annotation',true);leaf.owned.text=seed.source;leaf.dirty[0x688]=1;runtime.update(leaf);runtime.api.disable();runtime.update(leaf);
 report.callback_disable_restores_original=leaf.text()===seed.source;runtime.destroy(leaf);
 report.callback_failure_count=report.callback_failures.length+(!report.callback_disable_restores_original?1:0);
 report.actual_callback_entry=true;report.callback_scope='existing pointer harness actual owned_update; no game attach or pixel claim';
}
report.wire_mtime_unchanged=before===fs.statSync(options.wire).mtimeMs;
report.script_sha256_after=Object.fromEntries(Object.entries(scriptPaths).map(([k,v])=>[k,sha(fs.readFileSync(v))]));
assert.deepEqual(report.script_sha256_after,scriptHashes);assert(report.wire_mtime_unchanged);
fs.writeFileSync(options.output,JSON.stringify(report,null,2)+'\n',{encoding:'utf8',flag:'wx'});
console.log(JSON.stringify({output:path.resolve(options.output),sha256:sha(fs.readFileSync(options.output)),label:options.label,mode_plan_count:report.mode_plan_count,strict_failure_count:report.strict_failure_count,semantic_failure_count:report.semantic_failure_count,negative_failure_count:report.negative_failure_count,body_proof_negative_failure_count:report.body_proof_negative_failure_count,actual_capture_checks:report.actual_capture_checks.length,callback_mode_plans:report.callback_checks?.length??0,callback_failure_count:report.callback_failure_count??null}));
process.exitCode=report.semantic_failure_count||report.negative_failure_count||report.body_proof_negative_failure_count||report.normal_primary_source_failure_count||report.callback_failure_count?1:0;
