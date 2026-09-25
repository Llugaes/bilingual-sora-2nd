'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function transport(payload){
    let active={old:true};const rpc={exports:{load(m){if(m.invalid)throw Error('Invalid model');active=m;return true;}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../sora_bilingual/game/scripts/native_transport.js'),'utf8'),{rpc,File:{readAllText:()=>JSON.stringify(payload)}});
    return {rpc:rpc.exports,active:()=>active};
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
    const {rpc,active}=transport(),text=JSON.stringify({v:'日本語 / français / 한국어'});
    rpc.modelbegin('a');rpc.modelpart('a',0,text.slice(0,9));rpc.modelpart('a',1,text.slice(9));
    assert.equal(rpc.modelcommit('a',2,text.length,'annotation',true,.9,{}),true);
    assert.equal(active().v,'日本語 / français / 한국어');
    const invalid=JSON.stringify({invalid:true});rpc.modelbegin('b');rpc.modelpart('b',0,invalid);
    assert.throws(()=>rpc.modelcommit('b',1,invalid.length,'primary',true,1,{}));
    assert.equal(active().v,'日本語 / français / 한국어');
});
