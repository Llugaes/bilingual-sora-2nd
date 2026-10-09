'use strict';
const fs=require('fs'),assert=require('node:assert/strict');
const receipt=JSON.parse(fs.readFileSync('generated/r22-production-receipt.json','utf8'));
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const inputs=JSON.parse(fs.readFileSync('generated/r22-family-oracle-inputs.json','utf8')),results=[],failures=[];
// Family coverage reuses immutable model indexes only. Plans and refusal state
// are cold before each input; no preliminary translate call warms that source.
// The four feedback inputs and independent gate also construct fresh resolvers.
const resolvers=Object.fromEntries(['primary','secondary','annotation'].map(m=>[m,new RuntimeText(model)]));
const plain=s=>s.replace(/<[^<>]*>/g,'');
for(const row of inputs.rows){
 const modes={};
 for(const mode of ['primary','secondary','annotation']){
  const tr=resolvers[mode];tr.planCache.clear();tr.effectUnitFailures.clear();tr.details.effectUnitFailures.clear();
  const plan=tr.render(row.source,mode),primary=plain(plan.text.replace(/<R>([^<>]*)<\/R[^<>]*>/g,(_,s)=>s)),
   secondary=plain(plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[^<>]*<\/R([^<>]*)>/g)].filter(m=>m[1]!=='_').map(m=>m[1]).join(''));
  const want=plain(mode==='secondary'?row.secondary_member:row.primary_member);
  const secondaryNeeded=plain(row.primary_member).normalize('NFKC')!==plain(row.secondary_member).normalize('NFKC')||/[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(plain(row.secondary_member));
  if(!primary.includes(want)||(mode==='annotation'&&secondaryNeeded&&!secondary.includes(plain(row.secondary_member))))failures.push({family:row.family,ids:row.ids,source:row.source,mode,want,plan});
  modes[mode]=plan;
 }
 results.push({...row,modes});
}
fs.writeFileSync('generated/r22-family-oracle-final.json',JSON.stringify({wire:receipt.wire_sha256,rows:results,failures,game_attached:false,pixels_verified:false},null,2));
console.log(JSON.stringify({raw_family_rows:results.length,failures:failures.length,first:failures.slice(0,3)}));
assert.equal(failures.length,0,'raw/native family final render failed');
