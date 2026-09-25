'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function transport(){
    let active={old:true};const rpc={exports:{load(m){if(m.invalid)throw Error('Invalid model');active=m;return true;}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../native_transport.js'),'utf8'),{rpc});
    return {rpc:rpc.exports,active:()=>active};
}
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
