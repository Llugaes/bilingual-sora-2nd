'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const root=process.cwd(),{RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const receipt=JSON.parse(fs.readFileSync('generated/r26-production-receipt.json','utf8'));
const model=JSON.parse(fs.readFileSync(receipt.model_path,'utf8'));
model.item_help_headers=JSON.parse(fs.readFileSync('generated/r26-tools-header-contracts.json','utf8')).find(x=>x.locale==='en').contract;
const tr=new RuntimeText(model),modes=['primary','secondary','annotation'];
const rows=JSON.parse(fs.readFileSync('generated/r26-tools-real-producer-fixtures.json','utf8')).rows.filter(r=>r.locale==='en');
let positive=0,negative=0,parameters=0;
for(const row of rows) {
 const a=tr.render(row.texts.en,'primary'),b=tr.render(row.texts.en,'secondary'),annotation=tr.render(row.texts.en,'annotation');
 assert.equal(a.text,row.texts.ja,row.physical+'/primary');assert.equal(b.text,row.texts['zh-Hans'],row.physical+'/secondary');
 assert.equal(annotation.text.replaceAll('<R></R_>',''),a.text,row.physical+'/annotation primary lane');positive+=3;
 const controls=s=>(s.match(/<I\d+>/g)||[]);
 assert.deepStrictEqual(controls(a.text),controls(row.texts.en));assert.deepStrictEqual(controls(b.text),controls(row.texts.en));
 for(const layer of annotation.layers)if(layer.semantic_ids?.includes(row.head_key)||layer.semantic_ids?.includes(row.range_key))assert(!/<I\d+>/.test(layer.text),'header icon leaked into type/range layer');
 const styled='<s100><c698>'+row.texts.en.replace('\n','</C>\n');
 for(const mode of modes) {
  const plan=tr.render(styled,mode),base=tr.render(row.texts.en,mode);
  assert.equal(plan.text,'<s100><c698>'+base.text.replace('\n','</C>\n'));parameters++;
 }
}
const first=rows.find(r=>r.physical===143),source=first.texts.en;
for(const value of ['0','1499','2147483647']) {
 const input=source.replace('1500',value);
 assert.equal(tr.render(input,'primary').text,first.texts.ja.replace('1500',value));
 assert.equal(tr.render(input,'secondary').text,first.texts['zh-Hans'].replace('1500',value));
 assert(tr.render(input,'annotation').layers.some(l=>l.parameters?.includes(value)));parameters+=3;
}
const wholeReject=[source.replace('1500','2147483648'),source.replace('1500','1.5'),source.replace('1500','NaN'),
 source.replace('Heal 1500 HP','<X999>Heal 1500 HP</X>')];
for(const input of wholeReject)for(const mode of modes) {
 const plan=tr.render(input,mode),head=input.slice(0,input.indexOf('\n'));
 assert(plan.text.startsWith(head+'\n'),'rejected effect header entered fallback');
 const body=mode==='secondary'?first.texts['zh-Hans'].split('\n').slice(1).join('\n'):first.texts.ja.split('\n').slice(1).join('\n');
 const ranges=RuntimeText.rubyRanges(plan.text);assert(ranges);
 const visible=ranges.slice().reverse().reduce((text,[start,end])=>text.slice(0,start)+text.slice(start+3,text.indexOf('</R',start+3))+text.slice(end),plan.text);
 assert(visible.endsWith(body),'independent resource body lost to header refusal');
 assert(!plan.layers.some(l=>l.semantic_ids?.some(id=>id===first.head_key||id===first.range_key)),'rejected header acquired effect layers');negative++;
}
for(const input of [source.split('\n')[0],source.replace(first.texts.en.split('\n').slice(1).join('\n'),'Unproved Body')])for(const mode of modes) {
 assert.deepStrictEqual(tr.render(input,mode),{text:input,layers:[],kind:'plain'},'unowned body bypassed refusal');
 assert.equal(tr.translate(input,mode),input,'unowned body translate bypassed refusal');negative++;
}
const originalHeadInputs=[source.replace('Heal 1500 HP','Unproved Effect 1500'),source.replace('<I299>','<I298>'),
 source.replace('Recovery','Support'),source.replace('Heal 1500 HP','Heal 1500 HP, Unproved Effect')];
for(const input of originalHeadInputs)for(const mode of modes) {
 const plan=tr.render(input,mode),head=input.slice(0,input.indexOf('\n'));
 assert(plan.text.startsWith(head+'\n'),'unproved header entered word fallback');negative++;
}
const standalone=source.split('\n')[0],literalPair=['complete Japanese field','complete Chinese field'];
const complete=new RuntimeText({...model,pairs:{...model.pairs,[standalone]:literalPair}});
const keyed=new RuntimeText({...model,keyed:{...model.keyed,actual_field:{source:standalone,model:{pairs:{[standalone]:literalPair}}}}});
for(const mode of modes) {
 const baselineComplete=new RuntimeText({...complete.model,item_help_headers:null});
 const baselineKeyed=new RuntimeText({...keyed.model,item_help_headers:null});
 assert.deepStrictEqual(complete.render(standalone,mode),baselineComplete.render(standalone,mode),'whole literal lost to header scope');
 assert.deepStrictEqual(keyed.render(standalone,mode,'actual_field'),baselineKeyed.render(standalone,mode,'actual_field'),'actual key owner lost to header scope');
}
const conflictModel={...model,pairs:{...model.pairs,[source]:['wrong complete target','wrong secondary target']}};
const conflict=new RuntimeText(conflictModel);assert.equal(conflict.effectDetailPlan(source),null,'new fragment target overrode complete identity');negative++;
const old=JSON.parse(fs.readFileSync('generated/r25-stage5-qualified-original-producers-final.json','utf8'));
for(const row of old.rows)for(const mode of modes)assert.deepStrictEqual(tr.render(row.source,mode,'',''),row.modes[mode].plan,row.id+'/'+mode);
const py=JSON.parse(fs.readFileSync('generated/r26-tools-python-plans.json','utf8')),localeModels=JSON.parse(fs.readFileSync('generated/r26-tools-test-models.json','utf8'));
const translators=Object.fromEntries(Object.entries(localeModels).map(([locale,m])=>[locale,new RuntimeText(m)]));
for(const row of py.rows)for(const mode of modes)assert.deepStrictEqual(translators[row.locale].render(row.source,mode),row.modes[mode],row.locale+'/'+row.physical+'/'+mode);
const result={created_utc:new Date().toISOString(),production_source_sha256:crypto.createHash('sha256').update(fs.readFileSync('sora_bilingual/game/scripts/runtime_text.js')).digest('hex'),
 compiler_sha256:crypto.createHash('sha256').update(fs.readFileSync('sora_bilingual/localization/item_help_headers.py')).digest('hex'),
 whole_identity_precedence_mode_checks:6,positive_complete_modes:positive,style_numeric_control_checks:parameters,negative_checks:negative,old_full_plans_unchanged:old.rows.length*3,
 eight_locale_python_js_complete_plan_parity:py.rows.length*3,game_attached:false,final_wire_compiled:false};
fs.writeFileSync('generated/r26-tools-header-regression.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
