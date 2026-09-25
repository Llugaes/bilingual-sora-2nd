'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const {performance}=require('node:perf_hooks');
const {ScriptIdentities,TableIdentities}=require('../runtime_identity.js');
const {RuntimeText}=require('../runtime_text.js');
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const model=JSON.parse(fs.readFileSync(fixture.model,'utf8'));
const ids=new ScriptIdentities(model.script_identities),times=[];
const scriptFiles=new Map();let fileNumber=0;
for(const s of fixture.scripts) {
    const data=Buffer.from(s.data,'base64'),start=performance.now();
    scriptFiles.set(s.sha256,{data,base:0x100000000+(fileNumber++)*0x1000000});
    const selected=ids.select(s.signature,n=>data.subarray(0,n),s.functionName,'');
    times.push(performance.now()-start);assert.equal(selected.identity.sha256,s.sha256);
}
let cases=0;
for(const c of fixture.cases) {
    const context=ids.lookup(c.identity);assert.ok(context);
    context.tr ||= new RuntimeText(context.model);
    assert.deepEqual(context.tr.render(c.source),c.plan,c.source);
    assert.equal(context.tr.translate(c.source,'secondary'),c.secondary);cases++;
}
const tables=model.table_identities,ti=new TableIdentities(tables),files=new Map();
let sequence=0,tableCases=0;
for(const [id,raw] of Object.entries(fixture.table_files))files.set(id,{data:Buffer.from(raw,'base64'),base:0x10000000+(sequence++)*0x1000000});
// Relocate the exact candidate fields as the native table loader does.
for(const candidates of Object.values(tables.sources))for(const c of candidates) {
    const f=files.get(c.file);assert.ok(f);
    f.data.writeBigUInt64LE(BigInt(f.base+c.offset),c.record_at+c.field_at);
}
const memoryBlocks=new Map([...files.values(),...scriptFiles.values()].map(f=>[f.base,f]));
class Pointer {
    constructor(address){this.address=address;}
    add(n){return new Pointer(this.address+n);}
    toString(){return this.address.toString(16);}
    equals(p){return this.address===p.address;}
    locate(n){const f=memoryBlocks.get(Math.floor(this.address/0x1000000)*0x1000000);if(f&&this.address+n<=f.base+f.data.length)return [f.data,this.address-f.base];throw Error('unmapped');}
    readByteArray(n){const [data,at]=this.locate(n);return Uint8Array.from(data.subarray(at,at+n)).buffer;}
    readPointer(){const [data,at]=this.locate(8);return new Pointer(Number(data.readBigUInt64LE(at)));}
}
let scriptPointerCases=0;
const done=new Set();
for(const [source,candidates] of Object.entries(model.script_identities.pointers||{}))for(const c of candidates) {
    const identity=c.sha256+'/'+c.offset;
    if(done.has(identity))continue;done.add(identity);
    const file=scriptFiles.get(c.sha256);assert.ok(file);
    const selected=ids.pointerSelect(new Pointer(file.base+c.offset),source);
    assert.ok(selected,source);assert.deepEqual(selected.model.pairs[source],model.script_identities.pointer_models[c.key].model.pairs[source]);
    scriptPointerCases++;
}
for(const [source,candidates] of Object.entries(tables.sources))for(const c of candidates) {
    const pointer=new Pointer(files.get(c.file).base+c.offset),selected=ti.select(pointer,source);
    assert.ok(selected,source);assert.deepEqual(selected.model.pairs[source],tables.models[c.key].model.pairs[source]);tableCases++;
}
times.sort((a,b)=>a-b);
console.log(JSON.stringify({scripts:fixture.scripts.length,context_render_cases:cases,table_pointer_cases:tableCases,script_pointer_cases:scriptPointerCases,
    script_identity_p95_ms:times[Math.floor(times.length*.95)],script_identity_max_ms:times.at(-1)}));
