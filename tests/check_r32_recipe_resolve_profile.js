'use strict';
// Read actual captured inputs and exact candidate wire. This measures parser
// work in Node; actual game callback timing remains a separate receipt.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {performance}=require('node:perf_hooks');
const root=path.resolve(__dirname,'..'),product=path.resolve(process.argv[2]);
const capture=path.resolve(process.argv[3]),output=path.resolve(process.argv[4]);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const scripts=path.join(product,'sora_bilingual/game/scripts');
const {RuntimeText}=require(path.join(scripts,'runtime_text.js'));
const transport=fs.readFileSync(path.join(scripts,'native_transport.js'),'utf8');
const readIndexed=new Function('rpc',transport+';return readIndexedModel;')({exports:{}});
const cache=JSON.parse(fs.readFileSync(path.join(product,'candidate-cache.json'),'utf8'));
const config=cache.config_matrix.find(x=>x.config.game_language==='en'&&x.config.primary==='en'&&x.config.secondary==='zh-Hans');
if(!config)throw new Error('actual candidate EN/en/ZH wire missing');
const bytes=fs.readFileSync(path.join(product,'generated',config.wire_name));
if(sha(bytes)!==config.wire_sha256)throw new Error('actual wire mismatch');
const source=JSON.parse(fs.readFileSync(capture,'utf8'));
const inputs=[...new Set(source.rows.filter(x=>x.source_matches_diagnostic&&
    ['success_info','unique_info','failure_info'].some(k=>x.input_identity_diagnostic?.node_path?.includes(k))).map(x=>x.original))];
if(!inputs.length)throw new Error('no actual recipe setter input');
const methods=['render','translate','_translate','effectDetailPlan','itemHelpHeader','effectUnits',
    'effectUnit','rawPair','wholeConflict','anchoredDetails','replaceDetailInlineIcons','detailBodyBoundary'];
const counts={};
for(const name of methods){
    const original=RuntimeText.prototype[name];if(typeof original!=='function')continue;
    counts[name]={calls:0,totalMs:0,maxMs:0};
    RuntimeText.prototype[name]=function(...args){const before=performance.now();
        try{return original.apply(this,args);}finally{const elapsed=performance.now()-before,c=counts[name];c.calls++;c.totalMs+=elapsed;c.maxMs=Math.max(c.maxMs,elapsed);}};
}
const tr=new RuntimeText(readIndexed(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length)));
const rows=[];
for(const input of inputs){
    const before=performance.now(),plan=tr.render(input,'annotation'),cold=performance.now()-before;
    const again=performance.now(),warm=tr.render(input,'annotation'),warmMs=performance.now()-again;
    if(JSON.stringify(plan)!==JSON.stringify(warm))throw new Error('warm/cold plan differs');
    rows.push({input,coldMs:cold,warmMs,plan});
}
const report={source_snapshot_sha256:cache.source_snapshot_sha256,wire_sha256:config.wire_sha256,
    runtime_text_sha256:sha(fs.readFileSync(path.join(scripts,'runtime_text.js'))),
    capture_sha256:sha(fs.readFileSync(capture)),actual_complete_inputs:inputs.length,counts,rows,
    scope:'Node inclusive method timings on actual captured complete inputs; not game performance acceptance',game_attached:false};
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({output,sha256:sha(fs.readFileSync(output)),inputs:inputs.length,
    timings:rows.map(x=>({input:x.input,coldMs:x.coldMs,warmMs:x.warmMs})),counts}));
