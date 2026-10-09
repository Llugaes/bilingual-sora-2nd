'use strict';
// Replay real resident originals and whole resource families without attaching.
const fs=require('fs'),assert=require('node:assert/strict'),crypto=require('crypto');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const root=process.cwd(),oldRoot=process.env.SORA_BASELINE_PRODUCT||root+'/dist/comprehensive-1.0.0-dev5-r18/DEV';
const read=new Function('rpc',fs.readFileSync(root+'/sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const json=p=>JSON.parse(fs.readFileSync(p,'utf8')),digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const load=p=>{const b=fs.readFileSync(p);return {model:read(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)),sha:digest(b)};};
const receipt=json('generated/r20-production-receipt.json'),current=json('generated/r19-p0-current-source.json');
const before=json('generated/r19-tips-existing-owner-snapshot-0449.json');
const old=load(before.status.inputIdentityDiagnostics.model_provenance.path),previous=load(current.status.inputIdentityDiagnostics.model_provenance.path),fresh=load(receipt.wire_path);
assert.equal(fresh.sha,receipt.wire_sha256);
const OldText=require(oldRoot+'/sora_bilingual/game/scripts/runtime_text.js').RuntimeText;
const PreviousText=require(root+'/dist/comprehensive-1.0.0-dev5-r19/DEV/sora_bilingual/game/scripts/runtime_text.js').RuntimeText;
const tr=new RuntimeText(fresh.model),oldTr=new OldText(old.model),previousTr=new PreviousText(previous.model);
const rows=json('generated/r19-complete-production.json').rows.map(row=>({...row}));
for(const row of rows) {
  assert.equal(tr.translate(row.source,'primary',row.key||'',row.scope||''),row.primary,row.name);
  assert.equal(tr.translate(row.source,'secondary',row.key||'',row.scope||''),row.secondary,row.name);
  row.plan=tr.render(row.source,'annotation',row.key||'',row.scope||'');
}
const arts=current.all_rows.find(row=>(row.original||'').includes('[Arts')).original;
const matrix=[];
for(const [name,m] of [['r18',old],['r19',previous],['r20',fresh]])for(const [renderer,Ctor] of [['r18',OldText],['r19',PreviousText],['r20',RuntimeText]]) {
  const rt=new Ctor(m.model),plan=rt.render(arts);
  matrix.push({model:name,wire_sha256:m.sha,renderer,source:arts,plan,translated:plan.text!==arts});
}
assert.equal(matrix.find(r=>r.model==='r19'&&r.renderer==='r19').translated,false);
assert.equal(matrix.find(r=>r.model==='r20'&&r.renderer==='r20').translated,true);
assert.ok(!tr.render(arts).text.includes('Petrify/Confuse'));
rows.push({name:'captured menu/battle Arts original, no granted identity',level:'actual-original replay; r20 pixels pending',source:arts,
 primary:tr.translate(arts,'primary'),secondary:tr.translate(arts,'secondary'),plan:tr.render(arts)});
let capturedSuccess=0;const losses=[];
for(const row of current.all_rows)for(const mode of ['primary','secondary']) {
 const a=oldTr.translate(row.original,mode,row.text_key||'',row.scope||'');
 const b=tr.translate(row.original,mode,row.text_key||'',row.scope||'');
 if(a!==row.original){capturedSuccess++;if(b===row.original)losses.push({source:row.original,mode,scope:row.scope,key:row.text_key});}
}
// Keep the native complete description suffix as independent authority even
// when no partition can prove the effect tail. Iterate every actual body.
const headers=tr.model.skill_help_headers,bodyFailures=[];let bodyChecks=0;
for(const source of tr.model.detail_sources) {
 const beforePair=['primary','secondary'].map(mode=>oldTr.details.translate(source,mode));
 if(beforePair.every(t=>t===source))continue;
 const index=bodyChecks/2,head=headers.formats[index%headers.formats.length].source.replace('%s','<I277>')+
     headers.ranges[index%headers.ranges.length].source+headers.close[0]+' ';
 const full=head+'<c698>HP Regen</C><c698>, </C><c698>UnprovenEffect</C>\n<C9>'+source;
 for(const [side,mode] of ['primary','secondary'].entries()) {
   const after=tr.translate(full,mode),expected=tr.details.translate(source,mode);
   if(!after.endsWith('\n<C9>'+expected)||!after.includes('UnprovenEffect'))bodyFailures.push({source,mode});
   bodyChecks++;
 }
}
assert.deepEqual(bodyFailures,[],'known resource body or unknown tail swallowed');
let headerChecks=0,headerAdmitted=0,headerRefused=0;
const knownBody="Grants the earth's protection and gradually restores HP.";
for(const format of headers.formats)for(const range of headers.ranges) {
 const head=format.source.replace('%s','<I277>')+range.source+headers.close[0]+' ';
 if(tr.skillHeader(head))headerAdmitted++;else headerRefused++;
 const full=head+'HP Regen, UnprovenEffect\n<C9>'+knownBody;
 for(const mode of ['primary','secondary']) {
  const after=tr.translate(full,mode);
  assert.ok(after.endsWith('\n'+tr.details.translate('<C9>'+knownBody,mode)),JSON.stringify({head,mode,after}));
  assert.ok(after.includes('UnprovenEffect'));headerChecks++;
 }
}
assert.deepEqual(losses,[],'previously successful captured input became wholly untranslated');
const support='[Support - Ally - Single] DEF/ADF↑(5 turns), HP Regen, Cure Stat Debuff\n<C9>Grants the earth\'s protection and gradually restores HP.';
assert.equal(previousTr.render(support).text,support);
assert.ok(tr.render(support).text.includes('大地')||tr.render(support).layers.some(l=>l.text.includes('大地')));
rows.push({name:'Support full resource-body constructor fixture',level:'resource/constructor replay; full setter original not captured',source:support,
 primary:tr.translate(support,'primary'),secondary:tr.translate(support,'secondary'),plan:tr.render(support)});
// Execute the actual ownership function with captured ancestry, not a scope
// passed to the renderer in advance. Fake pointers only simulate node reads.
const agent=fs.readFileSync('sora_bilingual/game/scripts/native_agent.js','utf8');
const ownershipFunction=agent.slice(agent.indexOf('function translationKey(row)'),agent.indexOf('function isLabel(p)'));
function scopeFor(path,layoutId,source) {
 const names=path.split('/').reverse(),zero={isNull:()=>true,toString:()=> '0'};
 const nodes=names.map((name,i)=>({isNull:()=>false,toString:()=>String(i+1),add(offset){return {
  readU32:()=>0,readPointer:()=>offset===0x80?(nodes[i+1]||zero):{isNull:()=>false,readUtf8String:()=>name}};}}));
 const row={pointer:nodes[0],original:source};
 const fn=new Function('row','resolver','layoutKinds',`const scanLayouts=()=>{},REPORT={node_names:true},textKeys=new Map(),dictionary={},subtitleRoots=new Set(),insetRoots=new Map();${ownershipFunction}\ntranslationKey(row);return row.scope;`);
 return fn(row,tr,new Map([[String(nodes.at(-1)),layoutId]]));
}
const graph=json('generated/r19-p0-readonly-layout-20261006T070944544748Z.json');
const actualSlots=graph.layouts.filter(l=>l.layout_id.value===36).flatMap(l=>l.labels).filter(l=>/^root\/orbment_root\/orbment\/origin\/name\/name_[0-6]\/text$/.test(l.path));
assert.equal(actualSlots.length,7);
for(const slot of actualSlots)assert.equal(scopeFor(slot.path,36,''),'item_name');
const slotPath=actualSlots[0].path,slotResults=[];
for(const source of ['Heal','Seal','Mute','Confuse']) {
 const scope=scopeFor(slotPath,36,source),plan=tr.render(source,'annotation','',scope);
 assert.equal(scope,'item_name');assert.notEqual(plan.text,source);
 assert.equal(tr.render(source).text,source,'item name leaked globally');
 slotResults.push({source,scope,plan,level:'native producer + captured path simulation; reported same-name slot pixels pending'});
 for(const path of [slotPath.replace('orbment_root','other'),slotPath.replace('/origin/','/other/'),slotPath.replace('/name_0/','/name_7/'),slotPath.replace('/text','/title')])
  assert.equal(scopeFor(path,36,source),null);
 assert.equal(scopeFor(slotPath,14,source),null);
}
// Derive expected targets from raw enum/resource fields, not the runtime pair.
const params=json('generated/r20-status-parameter-resource-result.json').rows;let parameterChecks=0;
for(const row of params)for(const number of [0,50,100,2147483647]) {
 const source=RuntimeText.renderFormat(row.texts.en,()=>number);
 for(const [side,mode] of ['primary','secondary'].entries()) {
  assert.equal(tr.translate(source,mode),RuntimeText.renderFormat(row.texts[side?'zh-Hans':'ja'],()=>number),source);parameterChecks++;
 }
}
const state='Damage dealt to enemies with Seal +50%';
assert.ok(!tr.render(state).text.includes('Seal'));
assert.ok(tr.render('Damage dealt to enemies with UnprovenStatus +50%').text.includes('UnprovenStatus'));
rows.push({name:'native type17 condition formatter Seal',level:'native enum/resource replay; r20 pixels pending',source:state,
 primary:tr.translate(state,'primary'),secondary:tr.translate(state,'secondary'),plan:tr.render(state)});
const output={wire_sha256:fresh.sha,renderer_sha256:digest(fs.readFileSync('sora_bilingual/game/scripts/runtime_text.js')),
 captured_rows:current.all_rows.length,captured_success_checks:capturedSuccess,captured_success_losses:losses,
 body_checks:bodyChecks,body_failures:bodyFailures,header_cross_checks:headerChecks,
 header_constructor_admitted:headerAdmitted,header_constructor_refused:headerRefused,
 actual_slot_paths:actualSlots.map(l=>l.path),slot_results:slotResults,
 condition_parameter_checks:parameterChecks,matrix,rows,game_attached:false,candidate_live_verified:false};
fs.writeFileSync('generated/r20-complete-production.json',JSON.stringify(output,null,2));
console.log(JSON.stringify({wire_sha256:fresh.sha,captured_success_checks:capturedSuccess,body_checks:bodyChecks,
 header_cross_checks:headerChecks,actual_slot_paths:actualSlots.length,condition_parameter_checks:parameterChecks,replay_rows:rows.length,game_attached:false}));
