'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function transport(payload){
    let active={old:true},provenance=null;const rpc={exports:{load(m,_mode,_active,_scale,_layout,p){if(m.invalid)throw Error('Invalid model');active=m;provenance=p;return true;}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../sora_bilingual/game/scripts/native_transport.js'),'utf8'),{rpc,File:{readAllText:()=>JSON.stringify(payload)}});
    return {rpc:rpc.exports,active:()=>active,provenance:()=>provenance};
}
test('packed caches preserve multilingual values, shared arrays and prototype-like keys',()=>{
    const {rpc,active}=transport({schema:1,root:6,nodes:['ja','日本語 / 한국어','__proto__',[0,1], [1,0,3], 'nested', [1,2,1,0,3,5,4]]});
    assert.equal(rpc.modelpackedfile('unused','annotation',true,.9,{}),true);
    assert.equal(active().__proto__,'日本語 / 한국어');
    assert.deepEqual(JSON.parse(JSON.stringify(active())),{['__proto__']:'日本語 / 한국어',ja:['日本語 / 한국어'],nested:{ja:['日本語 / 한국어']}});
    assert.strictEqual(active().ja,active().nested.ja);
});
test('invalid packed caches never replace the active model',()=>{
    for(const payload of [null,{schema:2,nodes:[]},{schema:1,root:0,nodes:[[0,0]]},
        {schema:1,root:0,nodes:[[0,1],'future']},{schema:1,root:8,nodes:['x']},
        {schema:1,root:2,nodes:['k','v',[1,0,1,0,1]]},
        {schema:1,root:0,nodes:[{}]},{schema:1,root:2,nodes:[12,'v',[1,0,1]]}]) {
        const {rpc,active}=transport(payload);
        assert.throws(()=>rpc.modelpackedfile('unused','annotation',true,.9,{}));
        assert.ok(active().old);
    }
});
test('partial, reordered and malformed transfers never replace the active model',()=>{
    const {rpc,active}=transport();rpc.modelbegin('a');rpc.modelpart('a',0,'{"v":');
    assert.throws(()=>rpc.modelpart('a',2,'1}'));
    assert.throws(()=>rpc.modelcommit('a',1,9,'primary',true,1,{}));assert.ok(active().old);
    rpc.modelabort('a');assert.throws(()=>rpc.modelpart('a',1,'1}'));
    rpc.modelbegin('b');rpc.modelpart('b',0,'{');
    assert.throws(()=>rpc.modelcommit('b',1,1,'primary',true,1,{}));assert.ok(active().old);
});
test('only successful complete transfer commits; failed load preserves old model',()=>{
    const {rpc,active,provenance}=transport(),text=JSON.stringify({v:'日本語 / français / 한국어'});
    rpc.modelbegin('a');rpc.modelpart('a',0,text.slice(0,9));rpc.modelpart('a',1,text.slice(9));
    assert.equal(rpc.modelcommit('a',2,text.length,'annotation',true,.9,{}),true);
    assert.equal(active().v,'日本語 / français / 한국어');
    assert.equal(provenance().format,'json-rpc');assert.equal(provenance().code_units,text.length);
    const invalid=JSON.stringify({invalid:true});rpc.modelbegin('b');rpc.modelpart('b',0,invalid);
    assert.throws(()=>rpc.modelcommit('b',1,invalid.length,'primary',true,1,{}));
    assert.equal(active().v,'日本語 / français / 한국어');
    assert.equal(provenance().code_units,text.length,'failed transfer retains actual loaded provenance');
});

function indexedFileFixture(size=2*1024*1024+37,options={}) {
    const bytes=new Uint8Array(size),header=new DataView(bytes.buffer);
    [0x41524f53,0x32444f4d,2,1,0,32,48,size].forEach((v,i)=>header.setUint32(i*4,v,true));
    // A null root with unused payload keeps this IO fixture independent of the
    // Python encoder. Structural corruption is covered by test_model_wire.py.
    let closed=0,reads=0,checkpoints=0,active='old';
    class File {
        static SEEK_SET=0;static SEEK_END=2;
        constructor(path,mode){assert.equal(mode,'rb');this.at=0;}
        seek(offset,whence){this.at=(whence===File.SEEK_END?bytes.length:0)+offset;}
        tell(){return this.at;}
        readBytes(count){
            reads++;
            if(options.errorAt===reads)throw Error('fixture read error');
            if(options.truncated&&this.at>=32)return new ArrayBuffer(0);
            if(options.grown&&this.at===bytes.length)return new Uint8Array([1]).buffer;
            const chunk=bytes.slice(this.at,this.at+Math.min(count,options.shortReads?16384:count));
            this.at+=chunk.length;return chunk.buffer;
        }
        close(){closed++;}
    }
    const context={File,rpc:{exports:{load(model){active=model;return true;}}}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../sora_bilingual/game/scripts/native_transport.js'),'utf8'),context);
    context.createModelLoadCheckpoint=()=>()=>{checkpoints++;assert.equal(active,'old','partial model escaped');};
    return {context,bytes,stats:()=>({closed,reads,checkpoints,active})};
}

test('chunked indexed reads preserve bytes and publish only after full validation',()=>{
    for(const shortReads of [false,true]) {
        const f=indexedFileFixture(undefined,{shortReads});
        const buffer=f.context.readIndexedModelFile('fixture.wire.bin',()=>{});
        assert.deepEqual(new Uint8Array(buffer),f.bytes);
        assert.equal(f.context.rpc.exports.modelpackedfile('fixture.wire.bin'),true);
        assert.equal(f.stats().active,null);
        assert.ok(f.stats().checkpoints>=3);
        assert.equal(f.stats().closed,2);
    }
});

test('bad headers, interrupted reads and changing file length keep old model and close file',()=>{
    for(const options of [{truncated:true},{grown:true},{errorAt:2},{badHeader:true},{badNode:true}]) {
        const f=indexedFileFixture(undefined,options);
        if(options.badHeader)new DataView(f.bytes.buffer).setUint32(28,1,true);
        if(options.badNode)new DataView(f.bytes.buffer).setUint32(32,9,true);
        assert.throws(()=>f.context.rpc.exports.modelpackedfile('fixture.wire.bin'));
        assert.equal(f.stats().active,'old');assert.equal(f.stats().closed,1);
    }
});
