'use strict';
// Independent frozen-wire parser A/B. Production, package and fixtures are read only.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const root=path.resolve(__dirname,'..'),product=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
assert(!fs.existsSync(output),'never overwrite evidence');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const cache=json(path.join(product,'candidate-cache.json')),entries=cache.config_matrix.filter(r=>r.config.game_language==='en'&&r.config.primary==='en'&&r.config.secondary==='zh-Hans');assert.equal(entries.length,1);
const wirePath=path.join(product,'generated',entries[0].wire_name),wireStat=fs.statSync(wirePath),bytes=fs.readFileSync(wirePath);assert.equal(sha(bytes),entries[0].wire_sha256);
const packageScripts=path.join(product,'sora_bilingual/game/scripts'),workingScripts=path.join(root,'sora_bilingual/game/scripts');
const paths={frozen:path.join(packageScripts,'runtime_text.js'),working:path.join(workingScripts,'runtime_text.js')},scriptHashes=Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,sha(fs.readFileSync(p))]));
const classes=Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,require(p).RuntimeText]));
const reader=new Function('rpc',fs.readFileSync(path.join(packageScripts,'native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
const model=reader(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)),beforePath=path.join(root,'generated/r32-live008-recipe-resolve-node-before.json'),before=json(beforePath),actual=before.rows.map(r=>({kind:'captured_complete',source:r.input}));
assert.equal(before.wire_sha256,entries[0].wire_sha256);assert.equal(before.runtime_text_sha256,scriptHashes.frozen);
const snack=actual.find(r=>r.source.startsWith('Snacks [')).source;
const negatives=[['hp_empty',snack.replace('Heal 200 HP','Heal  HP')],['hp_noninteger',snack.replace('Heal 200 HP','Heal 2.5 HP')],['hp_text',snack.replace('Heal 200 HP','Heal UNKNOWN HP')],['hp_int32_overflow',snack.replace('Heal 200 HP','Heal 2147483648 HP')],['cp_noninteger',snack.replace('CP+20','CP+2.5')],['cp_empty',snack.replace('CP+20','CP+')],['turn_noninteger',snack.replace('(3 turns)','(3.5 turns)')],['turn_empty',snack.replace('(3 turns)','( turns)')],['unknown_control',snack.replace('<C9>','<X998><C9>')],['unknown_suffix',snack+' R32_UNKNOWN_SUFFIX'],['unknown_effect',snack.replace(' - STR<I270>(3 turns)',' - R32_UNKNOWN_EFFECT')],['unknown_join',snack.replaceAll(' - ',' | ')],['native_ruby',snack.replace('Heal 200 HP','<R>Heal 200 HP</Rreading>')]].map(([kind,source])=>({kind,source}));
const modes=['annotation','primary','secondary'];
function failures(tr,source){return {root:tr.effectUnitFailures.get(source)||null,details:tr.details?.effectUnitFailures.get(source)||null};}
function indexStats(index){return {total:index.fallback.length+[...index.byFirst.values()].reduce((a,b)=>a+[...b.values()].reduce((x,y)=>x+y.length,0),0),fallback:index.fallback.length,literals:[...index.byFirst.values()].reduce((a,b)=>a+b.size,0)};}
const results={},allCases=[...actual,...negatives];
for(const [label,Class] of Object.entries(classes)){
 let tr=new Class(model);const rows=[];
 for(const c of allCases)for(const mode of modes){let at=performance.now();const cold=tr.render(c.source,mode),coldMs=performance.now()-at,coldReasons=failures(tr,c.source);at=performance.now();const warm=tr.render(c.source,mode),warmMs=performance.now()-at;
  assert.deepEqual(cold,warm);rows.push({...c,mode,coldMs,warmMs,plan:cold,refusal_reasons:coldReasons,warm_refusal_reasons:failures(tr,c.source)});}
 const index_counts={parameter_guards:indexStats(tr.details.detailEffectParameterGuards),strict:indexStats(tr.details.detailEffectUnitIndex),raw_numeric:tr.rawNumericIndex?indexStats(tr.rawNumericIndex):{total:tr.rawNumeric.length,linear:true},producer_numeric:tr.producerNumericIndex?indexStats(tr.producerNumericIndex):{total:tr.producerNumeric.length,linear:true}};
 tr=null;if(global.gc)global.gc();
 const probe=new Class(model),labels=new WeakMap(),indexLabels=new WeakMap();let active=null;
 function register(t,name){for(const [field,kind] of [['rawNumeric','raw_numeric'],['producerNumeric','producer_numeric'],['detailEffectUnits','effect_strict'],['detailEffectDirectionGuards','direction_guards'],['detailEffectBlockedNumeric','effect_blocked']])for(const r of t[field]||[]){const rx=r instanceof RegExp?r:r.find?.(v=>v instanceof RegExp);if(rx)labels.set(rx,{resolver:name,kind});}
  for(const [field,kind] of [['detailEffectParameterGuards','parameter_guards'],['detailEffectUnitIndex','effect_strict'],['rawNumericIndex','raw_numeric'],['producerNumericIndex','producer_numeric']])if(t[field]){indexLabels.set(t[field],{resolver:name,kind});for(const e of [...t[field].fallback,...[...t[field].byFirst.values()].flatMap(b=>[...b.values()].flat())]){const rx=e.rule.find?.(v=>v instanceof RegExp);if(rx)labels.set(rx,{resolver:name,kind});}}
  if(t.details)register(t.details,name+'.details');}
 register(probe,'root');
 const originalExec=RegExp.prototype.exec,originalCandidates=Class.numericCandidates,originalMethods={};
 RegExp.prototype.exec=function(source){const result=originalExec.call(this,source);if(active){const tag=labels.get(this)||{resolver:'unlabelled',kind:'other'},key=tag.resolver+'/'+tag.kind,entry=active.regex[key]||(active.regex[key]={calls:0,matches:0});entry.calls++;if(result)entry.matches++;}return result;};
 Class.numericCandidates=function(source,index,candidateCache){const result=originalCandidates.call(this,source,index,candidateCache);if(active){const tag=indexLabels.get(index);if(tag){const key=tag.resolver+'/'+tag.kind,entry=active.candidates[key]||(active.candidates[key]={requests:0,total_selected:0,max_selected:0});entry.requests++;entry.total_selected+=result.length;entry.max_selected=Math.max(entry.max_selected,result.length);}}return result;};
 for(const method of ['effectUnits','effectUnit','rawPair','itemHelpHeader']){originalMethods[method]=Class.prototype[method];Class.prototype[method]=function(...args){if(active){active.methods[method]=(active.methods[method]||0)+1;if(method==='effectUnits')active.joins.push({source:args[0],join:args[3]||this.detailJoin});}return originalMethods[method].apply(this,args);};}
 const counts=[];
 try{for(const c of actual)for(const mode of modes)for(const temperature of ['first_plan','same_plan_repeat']){active={regex:{},candidates:{},methods:{},joins:[]};const plan=probe.render(c.source,mode);counts.push({...c,mode,temperature,...active,plan});active=null;}}
 finally{active=null;RegExp.prototype.exec=originalExec;Class.numericCandidates=originalCandidates;for(const [k,v] of Object.entries(originalMethods))Class.prototype[k]=v;}
 results[label]={rows,index_counts,counts};
}
const parity=[];for(let i=0;i<results.frozen.rows.length;i++){const a=results.frozen.rows[i],b=results.working.rows[i];parity.push({kind:a.kind,source:a.source,mode:a.mode,plan_equal:JSON.stringify(a.plan)===JSON.stringify(b.plan),refusal_equal:JSON.stringify(a.refusal_reasons)===JSON.stringify(b.refusal_reasons)});}
// Prove the actual guard indexing never excludes its own matching rule. These
// witnesses are test values, not claimed native strings or new whitelist rows.
const Current=classes.working,guardProbe=new Current(model),guardIndex=guardProbe.details.detailEffectParameterGuards;
const guardEntries=[...guardIndex.fallback,...[...guardIndex.byFirst.values()].flatMap(b=>[...b.values()].flat())].sort((a,b)=>a.at-b.at);
const witnessValues=['','UNKNOWN','2.5','0','+1','-1','0001','2147483648','4294967295','4294967296',' - ','<X998>'];
let witnessCount=0,matchingCount=0;const misses=[],guardCache=new Map();
for(const entry of guardEntries){const [row,rx]=entry.rule;assert(rx.source.startsWith('^(?:')&&rx.source.endsWith(')$'),'exact generated wrapper required');
 for(const value of witnessValues){const source=Current.renderFormat(row.source,()=>value),match=rx.exec(source);witnessCount++;if(!match)continue;matchingCount++;
  const selected=Current.numericCandidates(source,guardIndex,guardCache);if(!selected.includes(entry.rule))misses.push({row_source:row.source,pattern:rx.source,source});}}
// Bounded typed parameter/direction rejection checks on existing actual rows.
const typedRows=guardEntries.filter(e=>e.rule[0].parameter_kinds?.includes('u')).slice(0,2).map(e=>e.rule[0]);
const typedResults=[];for(const row of typedRows)for(const value of ['0','4294967295','4294967296','-1','2.5','']){const source=Current.renderFormat(row.source,()=>value),pair={};for(const [label,Class] of Object.entries(classes)){const tr=new Class({pairs:{},plain_pairs:{},detail_effect_units:[row]});pair[label]={unit:tr.effectUnit(source),reason:tr.effectUnitFailures.get(source)||null};}typedResults.push({row,source,value,...pair,equal:JSON.stringify(pair.frozen)===JSON.stringify(pair.working)});}
// Keep index ordering, fallback collisions, and custom producer rules observable.
const minimal={pairs:{},plain_pairs:{},
 raw_numeric:[['X<I1>([+-]?\\d+)',['A%d','B%d']],['(?:X|Y)<I1>([+-]?\\d+)',['A%d','CONFLICT%d']]],
 producer_numeric:[['N([+-]?\\d+)',['A%d','B%d'],[['ascii'],['ascii']]],['(?:N|M)([+-]?\\d+)',['A%d','CONFLICT%d'],[['ascii'],['ascii']]]]},numericChecks=[];
for(const source of ['X<I1>15','Y<I1>15','X<I1>UNKNOWN','N15','M15','NUNKNOWN']){const row={source};for(const [label,Class] of Object.entries(classes)){const tr=new Class(minimal);row[label]={rawPair:tr.rawPair(source),producerPair:tr.producerPair(source),customProducer:tr.producerPair(source,[tr.producerNumeric[0]])};}row.equal=JSON.stringify(row.frozen)===JSON.stringify(row.working);numericChecks.push(row);}
// Conflicting complete/partition targets and two native join topologies remain.
const effectSource='HP Regen, CP Regen',detailBase={pairs:{},plain_pairs:{},detail_join:[', ','、','，'],detail_effect_units:[{source:'HP Regen, CP Regen',pattern:'HP Regen, CP Regen',pair:['wrong','wrong'],ids:['test/combined']},{source:'HP Regen',pattern:'HP Regen',pair:['HP徐々回復','HP逐渐回复'],ids:['test/hp']},{source:'CP Regen',pattern:'CP Regen',pair:['CP徐々上昇','CP逐渐上升'],ids:['test/cp']}]},partitionChecks=[];
for(const [label,Class] of Object.entries(classes)){const tr=new Class(detailBase);const units=tr.effectUnits(effectSource);partitionChecks.push({label,source:effectSource,units,reason:tr.effectUnitFailures.get(effectSource)||null});}
const workingSnapshotStable=sha(fs.readFileSync(paths.working))===scriptHashes.working;
const report={schema:1,kind:'sealed local8 wire + frozen/working JS performance semantics A/B; not new candidate validation',source_snapshot_sha256:cache.source_snapshot_sha256,wire_path:wirePath,wire_sha256:entries[0].wire_sha256,script_paths:paths,script_sha256:scriptHashes,working_snapshot_stable:workingSnapshotStable,input_path:beforePath,input_sha256:sha(fs.readFileSync(beforePath)),results,parity,guard_index_witnesses:{guard_rows:guardEntries.length,witness_count:witnessCount,matching_witness_count:matchingCount,misses,necessary_literal_proof:'numericLiteral accepts only escaped literals and recognised captures; the selected literal occurs in every full regex match. Empty 0..512 capture does not remove surrounding literals. Unknown syntax retains ordered fallback.'},typed_parameter_checks:typedResults,numeric_conflict_fallback_custom_checks:numericChecks,partition_conflict_checks:partitionChecks,mode_plan_count:parity.length,plan_parity_failure_count:parity.filter(r=>!r.plan_equal).length,refusal_parity_failure_count:parity.filter(r=>!r.refusal_equal).length,package_wire_size_mtime_unchanged:fs.statSync(wirePath).size===wireStat.size&&fs.statSync(wirePath).mtimeMs===wireStat.mtimeMs,game_read:false,game_attached:false,production_modified:false,compiled:false,build_run:false,instrumentation_limit:'Only uninstrumented rows timings measure Node render. Regex counts instrumented separately; no frame-time or game acceptance claim.',checker_sha256:sha(fs.readFileSync(__filename))};
assert(report.package_wire_size_mtime_unchanged);fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({output,sha256:sha(fs.readFileSync(output)),scriptHashes,workingSnapshotStable,mode_plan_count:report.mode_plan_count,plan_parity_failure_count:report.plan_parity_failure_count,refusal_parity_failure_count:report.refusal_parity_failure_count,guard_rows:guardEntries.length,guard_matching_witnesses:matchingCount,guard_misses:misses.length,index_counts:Object.fromEntries(Object.entries(results).map(([k,v])=>[k,v.index_counts])),actual_timings:Object.fromEntries(Object.entries(results).map(([k,v])=>[k,v.rows.filter(r=>r.kind==='captured_complete').map(r=>({source:r.source,mode:r.mode,coldMs:r.coldMs,warmMs:r.warmMs}))])),typed_failures:typedResults.filter(r=>!r.equal).length,numeric_failures:numericChecks.filter(r=>!r.equal).length,partitionChecks}));
process.exitCode=report.plan_parity_failure_count||report.refusal_parity_failure_count||misses.length||typedResults.some(r=>!r.equal)||numericChecks.some(r=>!r.equal)||!workingSnapshotStable?1:0;
