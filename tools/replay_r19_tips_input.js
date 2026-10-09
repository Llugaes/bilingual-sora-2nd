'use strict';
// Exact existing-resident inputs and observed scopes. No owner is injected.
const fs=require('node:fs');
const crypto=require('node:crypto');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const capture=JSON.parse(fs.readFileSync('generated/r19-tips-existing-owner-snapshot-0449.json','utf8'));
const path=capture.status.inputIdentityDiagnostics.model_provenance.path;
const bytes=fs.readFileSync(path);
const model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const tr=new RuntimeText(model);
const sourceLayout='generated/r19-readonly-layout-044850.json';
const native=JSON.parse(fs.readFileSync(sourceLayout,'utf8'));
const result={wire:path,wire_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
  source_snapshot:'generated/r19-tips-existing-owner-snapshot-0449.json',source_layout:sourceLayout,
  model_modified:false,owner_injected:false,candidate_live_verified:false,rows:[]};
for(const row of capture.all_rows.filter(r=>r.scope==='note_help_title'&&
  ['Tactical Bonus','Changing Battle Difficulty','Stealing AT Bonuses','Overdrive'].includes(r.original))) {
  const scope=tr.scoped[row.scope];
  const paths=native.layouts.flatMap(l=>l.labels.filter(a=>a.label.text===row.original&&
    a.label.size.value===row.size&&a.label.flags.value===row.flags).map(a=>({layout:l.layout_id.value,
    path:a.path,pointer:a.ptr,owned_displayed:a.label.text})));
  result.rows.push({original:row.original,scope:row.scope,text_key:row.text_key,
    snapshot_has_pointer:Object.hasOwn(row,'pointer'),unique_external_attribute_match:paths.length===1,
    paths,render:tr.render(row.original,'annotation',row.text_key||'',row.scope),
    scope_whole_ambiguous:scope.ambiguousDisplay.has(row.original),
    scope_has_exact_pair:Object.hasOwn(scope.model.pairs,row.original),
    resource_candidates:(model.table_identities.sources[row.original]||[]).filter(c=>
      c.key.startsWith('table/t_help.tbl/')||c.key.startsWith('table/t_tips.tbl/')).map(c=>({key:c.key,record:c.record,
      record_at:c.record_at,pair:model.table_identities.models[c.key]?.model.pairs[row.original]}))});
}
fs.writeFileSync('generated/r19-tips-input-red.json',JSON.stringify(result,null,2));
if(result.rows.length!==4||result.rows.some(r=>r.render.text!==r.original||r.scope_has_exact_pair))
  throw Error('Observed shared-list absence was not reproduced');
console.log(JSON.stringify({wire_sha256:result.wire_sha256,captured_inputs:result.rows.length,
  failures_reproduced:result.rows.length,owner_injected:false}));
