'use strict';
const fs=require('node:fs');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const transport=fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8');
const read=new Function('rpc',transport+'\nreturn readIndexedModel;')({exports:{}});
const root=require('node:path').resolve(__dirname,'..');
const wire=root+'/dist/comprehensive-1.0.0-dev5-r18/DEV/generated/runtime-cfc71a4c822cbac5a77b.wire.bin';
const bytes=fs.readFileSync(wire);
const model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const tr=new RuntimeText(model);
const result={join:model.details.detail_join,
  units:model.details.detail_effect_units.filter(r=>/^(?:HP Regen|CP Regen|Cure Stat Debuff|STR.*turns|Impede)$/.test(r.source)).slice(-20),
  pairs:Object.entries(model.pairs).filter(([s,p])=>/HP Regen|CP Regen|Resist.*Burn|Resist.*Mute/.test(s)),
  contexts:model.detail_sources?.slice(0,3),
  sources:Object.entries(model.details.pairs).filter(([s,p])=>/CP Regen|HP Regen/.test(s)).slice(0,18),
  scopedTips:Object.fromEntries(['tips_title','note_help_title'].map(scope=>[scope,
    Object.entries(model.scoped[scope]?.pairs||{}).filter(([s])=>/Orbment|Tactical Bonus|Stealing AT|Overdrive|Changing Battle/.test(s))])),
  probes:[],live:[]};
const desc=model.detail_sources.find(s=>s.length>40&&!s.includes('%')&&model.details.pairs[s]);
for(const head of ['STR<I270> (5 turns), CP Regen, Cure Stat Debuff',
  '<c698>STR<I270> (5 turns)</C><c698>, </C><c698>CP Regen</C><c698>, </C><c698>Cure Stat Debuff</C>',
  '<c698>HP Regen</C>',
  '<c698>Resist Burn/Confuse/Deathblow 100%</C>',
  '<c698>Resist Mute/Freeze 100%</C>']){
  const source=head+'\n<C0>'+desc;
  result.probes.push({source,primary:tr.translate(source,'primary'),secondary:tr.translate(source,'secondary'),
    effectUnits:tr.details.effectUnits(head),failure:tr.details.effectUnitFailures.get(head),plan:tr.render(source)});
}
const capture=JSON.parse(fs.readFileSync(root+'/generated/replacement-r19-current-target-layout.json','utf8'));
for(const layout of capture.layouts)for(const label of layout.labels){
  const source=label.label.text;
  result.live.push({path:label.path,source,render:tr.render(source),primary:tr.translate(source,'primary'),secondary:tr.translate(source,'secondary')});
}
console.log(JSON.stringify(result,null,2));
