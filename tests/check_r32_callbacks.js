'use strict';
// Production callback entry, including copied fishing text without SetText.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=process.cwd(),product=path.resolve(process.argv[2]||root),label=process.argv[3]||'en-manual';
const receipt=JSON.parse(fs.readFileSync(`generated/r32-coverage-${label}-production-receipt.json`,'utf8'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const wirePath=process.argv[4]||receipt.wire_path,bytes=fs.readFileSync(wirePath);
if(hash(wirePath)!==receipt.wire_sha256)throw Error('wire digest mismatch');
const read=new Function('rpc',fs.readFileSync(path.join(product,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
const model=read(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length));
const directory=path.join(root,'tests');
let core=fs.readFileSync(path.join(directory,'test_native_agent.js'),'utf8');core=core.slice(0,core.indexOf('\ntest('));
for(const [variable,file] of [['AGENT','native_agent.js'],['RESOLVER','runtime_text.js'],['PARAGRAPHS','runtime_paragraph.js'],['IDENTITIES','runtime_identity.js']])
 core=core.replace(new RegExp('const '+variable+' = [^\\n]+'),()=>`const ${variable} = ${JSON.stringify(fs.readFileSync(path.join(product,'sora_bilingual/game/scripts',file),'utf8'))};`);
const moduleOut={exports:{}};new Function('require','__dirname','module',core+'\nmodule.exports={makeRuntime};')(require,directory,moduleOut);
const {RuntimeText}=require(path.join(product,'sora_bilingual/game/scripts/runtime_text.js'));
const tr=new RuntimeText(model),r=moduleOut.exports.makeRuntime(),failures=[],counts={},modes=['primary','secondary','annotation'];
function equal(actual,expected,name){counts[name.split('/')[0]]=(counts[name.split('/')[0]]||0)+1;
 if(actual!==expected)failures.push({name,actual,expected});}
const rows=[
 ...JSON.parse(fs.readFileSync('generated/r32-tools-step5-four.json','utf8')).cases.filter(c=>c.locale===receipt.config.game_language).map(c=>({...c,family:'tools'})),
 ...JSON.parse(fs.readFileSync(process.argv[5]||'generated/r32-recipes-step5-four.json','utf8')).cases.filter(c=>c.locale===receipt.config.game_language).map(c=>({...c,family:'recipe'})),
];
const rods=JSON.parse(fs.readFileSync('generated/r32-fishing-raw-producers.json','utf8'));
const fishing=Array.isArray(rods)?rods:(rods.entries||rods.rows);
for(const row of fishing)rows.push({family:'fishing',source:row.texts[receipt.config.game_language]});
r.api.load(model,'primary',true,1);
let address=0xf00000;
for(const row of rows){
 const p=r.label(address+=0x1000,'');
 for(const mode of modes){
  r.api.select(mode,true);
  if(row.family==='fishing')r.inlinedSet(p,row.source);else r.externalSet(p,row.source);
  r.update(p);equal(p.text(),tr.render(row.source,mode).text,row.family+'/'+mode+'/entry');
  const writes=r.api.status().writes;r.update(p);
  equal(r.api.status().writes,writes,row.family+'/'+mode+'/unchanged_update');
 }
 r.api.disable();r.update(p);equal(p.text(),row.source,row.family+'/disable_restore');
 r.api.select('annotation',true);r.update(p);
 equal(p.text(),tr.render(row.source,'annotation').text,row.family+'/reenable_same_text');
 r.destroy(p);
}
const unknown=fishing[0].texts[receipt.config.game_language]+'<Q>';
const bad=r.label(address+=0x1000,unknown);r.update(bad);equal(bad.text(),unknown,'negative/unknown_fishing_controls');r.destroy(bad);
equal(r.api.status().failed,false,'native/failed');
const output={source_snapshot_sha256:receipt.source_snapshot_sha256,wire_sha256:receipt.wire_sha256,
 product_root:product,label,counts,failure_count:failures.length,failures,
 production_scripts:Object.fromEntries(['native_agent.js','runtime_text.js','runtime_paragraph.js','runtime_identity.js'].map(f=>[f,hash(path.join(product,'sora_bilingual/game/scripts',f))])),
 recipe_fixture:process.argv[5]||'generated/r32-recipes-step5-four.json',
 recipe_fixture_sha256:hash(process.argv[5]||'generated/r32-recipes-step5-four.json'),
 input_count:rows.length,actual_callback_entry:true,game_attached:false,
 scope:'simulated native pointers exercising actual production callbacks, not game pixels or FPS'};
fs.writeFileSync(`generated/r32-callbacks-${label}${product===root?'':'-package'}.json`,JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,failures:failures.slice(0,3)}));process.exitCode=failures.length?1:0;
