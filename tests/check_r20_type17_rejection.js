'use strict';
const fs=require('fs'),assert=require('node:assert/strict'),crypto=require('crypto');
const receipt=JSON.parse(fs.readFileSync('generated/r20-production-receipt.json','utf8'));
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const rows=[];
// Fresh resolvers must establish the rejection themselves; no prior unit probe.
for(const number of ['2147483648','-2147483649','9'.repeat(100)])for(const wrapped of [false,true]) {
 const source=(wrapped?'<c698>':'')+'Damage dealt to enemies with Seal +'+number+'%'+(wrapped?'</C>':'');
 for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]) {
  const tr=new RuntimeText(model);
  for(const mode of order) {
   assert.equal(tr.translate(source,mode),source);
   assert.deepEqual(tr.render(source,mode),{text:source,layers:[],kind:'plain'});
  }
  rows.push({source,order,final_rejected:true});
 }
}
const positive=[];
for(const number of ['50','2147483647','-2147483648']) {
 const source='Damage dealt to enemies with Seal +'+number+'%',tr=new RuntimeText(model);
 const expected=['「封技」状態の敵に与えるダメージ+'+number+'％','对“封技”状态敌人造成的伤害+'+number+'％'];
 assert.equal(tr.translate(source,'primary'),expected[0]);assert.equal(tr.translate(source,'secondary'),expected[1]);
 assert.notEqual(tr.render(source).text,source);positive.push({source,expected,plan:tr.render(source)});
}
const tr=new RuntimeText(model),support="[Support - Ally - Single] DEF/ADF↑(5 turns), HP Regen, Cure Stat Debuff\n<C9>Grants the earth's protection and gradually restores HP.";
assert.ok(tr.translate(support,'primary').endsWith('大地による守護を与えつつ、ＨＰを徐々に回復させる。'));
assert.ok(tr.translate(support,'secondary').endsWith('赋予大地的守护，同时逐渐回复HP。'));
const unproved=support.replace('DEF/ADF↑(5 turns)','UnprovenEffect');
assert.ok(tr.translate(unproved,'primary').includes('UnprovenEffect'));
assert.ok(tr.translate(unproved,'primary').endsWith('大地による守護を与えつつ、ＨＰを徐々に回復させる。'));
const state='Damage dealt to enemies with UnprovenStatus +50%';
assert.ok(tr.render(state).text.includes('UnprovenStatus'));
for(const word of ['Seal','Heal','Mute','Confuse'])assert.equal(tr.translate(word,'primary'),word);
const captured=JSON.parse(fs.readFileSync('generated/r19-p0-current-source.json','utf8'));
const arts=captured.all_rows.find(r=>(r.original||'').includes('[Arts')).original;
assert.notEqual(tr.render(arts).text,arts);
const output={wire_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),negative_rows:rows,positive_rows:positive,
 support_body_preserved:true,unknown_effect_preserved:true,unknown_parameter_preserved:true,captured_arts_preserved:true,
 game_attached:false,pixels_verified:false};
fs.writeFileSync('generated/r20-type17-final-rejection.json',JSON.stringify(output,null,2));
console.log(JSON.stringify({negative_fresh_resolvers:rows.length,positive_rows:positive.length,support_body_preserved:true,captured_arts_preserved:true}));
