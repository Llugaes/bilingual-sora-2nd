'use strict';
// Exact captured nine-line input, current production wires, observed save ancestry.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),args=process.argv.slice(2);
const options={out:path.join(root,'generated/r32-local3-save-playtime-wire.json'),
 oldProduct:process.env.SORA_BASELINE_PRODUCT||'dist/r32-coverage-local2/DEV'};
for(let i=0;i<args.length;i++){
 if(args[i]==='--out')options.out=path.resolve(args[++i]);
 else if(args[i]==='--old-product')options.oldProduct=path.resolve(args[++i]);
 else throw Error('Unknown argument '+args[i]);
}
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const freeze=json(path.join(root,'generated/r32-coverage-source-freeze.json'));
const fixturePath=path.join(root,'tests/fixtures/r32-save-summary-live002-en.json'),fixture=json(fixturePath);
const source=fixture.row.original,scope=fixture.row.scope,lines=source.split('\n');
if(lines.length!==9||fixture.row.original_truncated||scope!=='save_summary')throw Error('captured input contract changed');
if(crypto.createHash('sha256').update(source).digest('hex')!==fixture.source_utf8_sha256)throw Error('captured source hash differs');
const declared=json(path.join(root,'generated/r32-save-playtime-component-after.json')).declared_display_caption_contract;
const last=/^(\s*)Playtime(.*)$/.exec(lines.at(-1));if(!last)throw Error('original clock field is not Playtime');
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const jsNames=['runtime_text.js','native_transport.js','native_agent.js','runtime_paragraph.js','runtime_identity.js'];
const jsHashes=Object.fromEntries(jsNames.map(name=>[name,hash(path.join(root,'sora_bilingual/game/scripts',name))]));
for(const [name,digest] of Object.entries(jsHashes))if(digest!==freeze.files['sora_bilingual/game/scripts/'+name])throw Error('source differs from freeze: '+name);
const read=new Function('rpc',fs.readFileSync(path.join(root,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
const modelFrom=p=>{const b=fs.readFileSync(p);return read(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));};
let code=fs.readFileSync(path.join(root,'tests/test_native_agent.js'),'utf8'),mod={exports:{}};
new Function('require','__dirname','module',code.slice(0,code.indexOf('\ntest('))+'\nmodule.exports={makeRuntime};')(require,path.join(root,'tests'),mod);
const oldCache=json(path.join(options.oldProduct,'candidate-cache.json'));
const modes=['primary','secondary','annotation'],labels=['en','ja','zh-Hans','zh-Hant','en-manual'];
const report={source_snapshot_sha256:freeze.snapshot_sha256,fixture_path:fixturePath,fixture_sha256:hash(fixturePath),
 source,source_utf8_sha256:fixture.source_utf8_sha256,line_count:9,observed_scope:scope,
 observed_layout_id:fixture.row.input_identity_diagnostic.layout_id,observed_node_path:fixture.row.input_identity_diagnostic.node_path,
 declared_display_caption_contract:declared,production_scripts:jsHashes,old_product:options.oldProduct,
 scope:'actual indexed production wires and production callbacks in captured layout/path; simulated pointers, not game pixels',
 game_attached:false,production_model_compiled:false,positive_native_identity_injected:false,failures:[],cases:[],checks:0};
const check=(ok,name,actual,expected)=>{report.checks++;if(!ok)report.failures.push({name,actual,expected});};
for(const label of labels){
 const receiptPath=path.join(root,`generated/r32-coverage-${label}-production-receipt.json`),receipt=json(receiptPath),config=receipt.config;
 if(receipt.source_snapshot_sha256!==freeze.snapshot_sha256)throw Error('stale receipt '+label);
 if(hash(receipt.wire_path)!==receipt.wire_sha256)throw Error('wire differs '+label);
 const oldRows=oldCache.config_matrix.filter(row=>JSON.stringify(row.config)===JSON.stringify(config));
 if(oldRows.length!==1)throw Error('old physical config is not unique');
 const oldWire=path.join(options.oldProduct,'generated',oldRows[0].wire_name);
 if(hash(oldWire)!==oldRows[0].wire_sha256)throw Error('old wire integrity differs');
 const tr=new RuntimeText(modelFrom(receipt.wire_path)),old=new RuntimeText(modelFrom(oldWire));
 const r=mod.exports.makeRuntime(null,true);r.api.load(tr.model,'annotation',true,1);
 const parent=r.label(0xf10000,''),leaf=r.label(0xf11000,'');
 const observed=fixture.row.input_identity_diagnostic;
 parent.name=observed.node_path[1];leaf.name=observed.node_path[0];leaf.parent=parent;r.registerLayout(parent,observed.layout_id);
 const row={label,receipt_sha256:hash(receiptPath),wire_path:receipt.wire_path,wire_sha256:receipt.wire_sha256,
  old_wire_path:oldWire,old_wire_sha256:hash(oldWire),source,scope,modes:{},expected:{},baseline_modes:{},callback:{}};
 for(const mode of modes){
  const plan=tr.render(source,mode,'',scope),before=old.render(source,mode,'',scope);
  const a=declared[config.primary],b=declared[config.secondary];if(!a||!b)throw Error('caption target not declared');
  const caption=mode==='primary'?a:mode==='secondary'?b:`<R>${a}</R${b}>`;
  const expectedLast=last[1]+caption+last[2],oldLines=before.text.split('\n'),expected=[...oldLines.slice(0,8),expectedLast].join('\n');
  check(plan.text===expected,label+'/'+mode+'/complete_9_lines',plan.text,expected);
  check(plan.text.split('\n').length===9,label+'/'+mode+'/line_count',plan.text.split('\n').length,9);
  check(plan.text.split('\n').at(-1)===expectedLast,label+'/'+mode+'/clock_bytes',plan.text.split('\n').at(-1),expectedLast);
  if(label==='en'&&mode==='primary')check(plan.text===source,label+'/normal_primary_retains_source',plan.text,source);
  r.api.select(mode,true);r.registerLayout(parent,observed.layout_id);r.externalSet(leaf,source);
  const snap=r.api.snapshot().find(v=>v.original===source);
  check(snap?.scope===scope,label+'/'+mode+'/observed_scope',snap?.scope,scope);
  check(leaf.text()===plan.text,label+'/'+mode+'/actual_callback',leaf.text(),plan.text);
  r.registerLayout(parent,7);r.externalSet(leaf,source);
  check(leaf.text().split('\n').at(-1)===lines.at(-1),label+'/'+mode+'/outside_save_layout_caption',leaf.text().split('\n').at(-1),lines.at(-1));
  const unknown=['Unknown saved input',...lines.slice(1)].join('\n');r.registerLayout(parent,observed.layout_id);r.externalSet(leaf,unknown);
  check(leaf.text().split('\n').at(-1)===lines.at(-1),label+'/'+mode+'/unknown_popup_caption',leaf.text().split('\n').at(-1),lines.at(-1));
  check(r.api.snapshot().find(v=>v.original===unknown)?.scope!==scope,label+'/'+mode+'/unknown_popup_scope',r.api.snapshot().find(v=>v.original===unknown)?.scope,'not save_summary');
  row.modes[mode]=plan;row.expected[mode]=expected;row.baseline_modes[mode]=before;
  row.callback[mode]={scope:snap?.scope,complete_text:plan.text,expected_last_line:expectedLast};
 }
 check(r.api.status().failed===false,label+'/native_failed',r.api.status().failed,false);r.api.disable();r.destroy(leaf);r.destroy(parent);
 report.cases.push(row);if(global.gc)global.gc();
}
for(const [name,digest] of Object.entries(jsHashes))if(hash(path.join(root,'sora_bilingual/game/scripts',name))!==digest)throw Error('source changed during replay');
report.failure_count=report.failures.length;report.mode_plans=report.cases.length*3;
fs.writeFileSync(options.out,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({out:options.out,source_snapshot_sha256:report.source_snapshot_sha256,checks:report.checks,mode_plans:report.mode_plans,failure_count:report.failure_count,failures:report.failures.slice(0,3)}));
process.exitCode=report.failure_count?1:0;
