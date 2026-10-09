'use strict';
const fs=require('fs'),assert=require('node:assert/strict');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js'),family=JSON.parse(fs.readFileSync('tests/fixtures/r22-malformed-ruby-family.json','utf8'));
const models=[JSON.parse(fs.readFileSync('tests/fixtures/r22-native-ruby-detail.json','utf8')).model,JSON.parse(fs.readFileSync('generated/r22-rev3-native-ruby-fixture.json','utf8')).model],reports=[];
for(const model of models)for(const row of family.cases){
 const source=row.prefix+family.suffix;assert.equal(RuntimeText.rubyRanges(source),null,row.name);
 for(const order of [['annotation','primary','secondary'],['primary','secondary','annotation']]){
  const tr=new RuntimeText(model);
  for(const mode of order){
   const p=tr.render(source,mode);assert.equal(p.text,source,row.name+'/'+mode);assert.equal(p.layers.length,0);assert.equal(p.kind,'plain');
   assert.equal(tr.translate(source,mode),source);assert.equal(tr.ownerPair(source),null);
  }
 }
 reports.push({name:row.name,source,three_final_modes_refused:true});
}
fs.writeFileSync('generated/r22-rev4-malformed-final.json',JSON.stringify({reports,positive_model_modified:false,game_attached:false},null,2));
console.log(JSON.stringify({models:models.length,family_cases:family.cases.length,two_mode_orders:true,passed:true}));
