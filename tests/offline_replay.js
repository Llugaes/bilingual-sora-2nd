// Uses this user's local catalog/captures; never attaches to a process.
'use strict';
const fs=require('fs'),assert=require('assert/strict'),{performance}=require('perf_hooks');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const start=performance.now();
const resolver=new RuntimeText(JSON.parse(fs.readFileSync(data.model,'utf8')));
const loadMs=performance.now()-start;
const cold=[];
for(const c of data.cases) {
    const t=performance.now();const plan=resolver.render(c.source,c.mode,c.key||'',c.scope||'');
    cold.push(performance.now()-t);
    const result=resolver.translate(c.source,c.mode,c.key||'',c.scope||'');
    assert.equal(result,c.expected,JSON.stringify({source:c.source,mode:c.mode,scope:c.scope}));
    if(c.plan)assert.deepEqual(plan,c.plan,JSON.stringify({source:c.source,mode:c.mode}));
}
const t=performance.now();
for(let i=0;i<100;i++)for(const c of data.cases)resolver.render(c.source,c.mode,c.key||'',c.scope||'');
const warmMs=(performance.now()-t)/(100*data.cases.length);
cold.sort((a,b)=>a-b);
console.log(JSON.stringify({cases:data.cases.length,model_load_ms:loadMs,cold_p95_ms:cold[Math.floor(cold.length*.95)],cold_max_ms:cold.at(-1),warm_mean_ms:warmMs}));
