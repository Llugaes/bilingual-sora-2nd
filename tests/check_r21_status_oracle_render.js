const fs=require('fs');
const receipt=JSON.parse(fs.readFileSync('generated/r21-production-receipt.json','utf8')),
 read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}}),
 bytes=fs.readFileSync(receipt.wire_path),model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)),
 {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js'),
 inputs=JSON.parse(fs.readFileSync('generated/r21-status-oracle-inputs.json','utf8')),tr=new RuntimeText(model);
const visible=s=>s.replace(/<[^<>]*>/g,'').trim(),rows=[];
for(const row of inputs.cases){
 const primary=tr.translate(row.source,'primary'),secondary=tr.translate(row.source,'secondary'),plan=tr.render(row.source),
       payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join(''),
       pair_correct=visible(primary)===visible(row.expected_primary)&&visible(secondary)===visible(row.expected_secondary),
       final_secondary_correct=visible(row.expected_primary)===visible(row.expected_secondary)||visible(payload)===visible(row.expected_secondary);
 rows.push({...row,primary,secondary,plan,pair_correct,final_secondary_correct});
}
const failures=rows.filter(r=>!r.pair_correct||!r.final_secondary_correct),result={wire_sha256:receipt.wire_sha256,
 renderer_sha256:require('crypto').createHash('sha256').update(fs.readFileSync('sora_bilingual/game/scripts/runtime_text.js')).digest('hex'),
 raw_resource_oracle:true,game_attached:false,actual_game_inputs:false,rows,failures:failures.map(({family,key,source,pair_correct,final_secondary_correct,primary,secondary,plan})=>({family,key,source,pair_correct,final_secondary_correct,primary,secondary,plan}))};
fs.writeFileSync('generated/r21-status-oracle-final.json',JSON.stringify(result,null,2));
console.log(JSON.stringify({rows:rows.length,failures:failures.length,failure_examples:result.failures.slice(0,6)}));

if(failures.length)process.exitCode=1;
