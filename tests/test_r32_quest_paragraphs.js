'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(process.argv[2]||'.');
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const {RuntimeParagraphs}=require(path.join(root,'sora_bilingual/game/scripts/runtime_paragraph.js'));
const rows=JSON.parse(fs.readFileSync('tests/fixtures/r32-quest-physical-paragraphs.json','utf8')).entries;
const models=JSON.parse(fs.readFileSync('generated/r32-quest-component-models.json','utf8'));
const failures=[];let checks=0;
function equal(actual,expected,name){checks++;try{assert.deepStrictEqual(actual,expected);}catch{failures.push({name,actual,expected});}}
const normalized=value=>value.replace(/<[^<>]*>/g,'').replace(/\s/gu,'');
for(const item of models) {
 const global=new RuntimeText(item.model),local=item.model.scoped.quest_notes;
 const paragraphs=new RuntimeParagraphs(local,RuntimeText,{preserveQuestLines:true});
 for(const row of rows.filter(r=>r.key.startsWith('table/t_quest.tbl/'))) {
  const source=row.texts[item.source],slots=RuntimeParagraphs.slots(source).map(s=>s.text);
  const primary=[],secondary=[];
  for(let index=0;index<slots.length;index++) {
   const a=paragraphs.lookup(source,index,slots[index],'primary');
   const b=paragraphs.lookup(source,index,slots[index],'secondary');
   equal(a?.text,slots[index],row.key+'/'+item.source+'/primary/'+index);
   primary.push(a?.text||'');secondary.push(b?.text||'');
   equal(paragraphs.lookup(source,index,slots[index]+'<Q>','secondary'),null,'changed incoming rejected');
  }
  equal(normalized(secondary.join('\n')),normalized(row.texts[item.secondary]),row.key+'/complete secondary');
  if(item.source==='en') {
   const target=row.texts[item.secondary].split('\n');
   // Independent resource oracle: one official target title, a blank slot for
   // English's wrapped continuation, then each complete physical name line.
   const expected=[target[0],'',...target.slice(1)];
   equal(secondary,expected,row.key+'/'+item.secondary+'/official line groups');
  }
  equal(paragraphs.lookup(source,-1,slots[0],'secondary'),null,'invalid lifecycle slot');
 }
 if(item.source==='en') {
  const engine=rows.find(r=>r.key.startsWith('table/t_quest.tbl/')&&r.texts.en.startsWith('★'));
  equal(global.render(engine.texts.en,'secondary').text,engine.texts.en,'cross-table conflict remains global');
  const plain=new RuntimeParagraphs(item.model,RuntimeText);
  equal(plain.lookup(engine.texts.en,0,engine.texts.en.split('\n')[0],'secondary'),null,'unowned copy has no guessed domain');
 }
}
const out=process.argv[3]||'generated/r32-quest-component-after.json';
fs.writeFileSync(out,JSON.stringify({checks,failure_count:failures.length,failures,root,game_attached:false},null,2));
console.log(JSON.stringify({checks,failures:failures.length}));process.exitCode=failures.length?1:0;
