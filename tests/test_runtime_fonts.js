'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {createRuntimeFonts}=require('../sora_bilingual/game/scripts/runtime_fonts.js');
function fixture() {
    let current='original',stages=0,finish,fail;
    const publish=[],manifest={version:1,faces:[{source_sha256:'old',sha256:'new'}]};
    const runtime=createRuntimeFonts({current:()=>current,identity:face=>({sha256:face==='prepared'?'new':'old',size:48}),
        stage:()=>{stages++;return new Promise((yes,no)=>{finish=yes;fail=no;});},
        publish:face=>{current=face;publish.push(face);}});
    return {runtime,manifest,publish,current:()=>current,stages:()=>stages,
        finish:()=>finish('prepared'),fail:()=>fail(Error('atlas upload failed')),nativeLoad:()=>{current='new-original';}};
}
test('running game keeps its original face until metrics and atlas are both ready',async()=>{
    const f=fixture(),job=f.runtime.configure(f.manifest);
    assert.equal(f.runtime.status().state,'preparing');assert.equal(f.runtime.tick(),false);
    assert.equal(f.current(),'original');f.finish();await job;
    assert.equal(f.runtime.status().state,'applying');assert.equal(f.current(),'original');
    assert.equal(f.runtime.tick(),true);assert.equal(f.current(),'prepared');assert.equal(f.runtime.status().ready,true);
    assert.equal(f.runtime.tick(),false);await f.runtime.configure(f.manifest);assert.equal(f.stages(),1);
});
test('exit restores the original and never publishes a late completion',async()=>{
    for(const staged of [false,true]) {
        const f=fixture(),job=f.runtime.configure(f.manifest);
        if(staged){f.finish();await job;f.runtime.tick();}
        f.runtime.select(false);
        if(!staged){f.finish();await job;}
        f.runtime.tick();
        assert.equal(f.current(),'original');assert.equal(f.runtime.tick(),false);
        await f.runtime.select(true);assert.equal(f.runtime.tick(),true);assert.equal(f.stages(),1);
    }
});
test('native font reset frees its original while the cached prepared face remains reusable',async()=>{
    const f=fixture(),job=f.runtime.configure(f.manifest);f.finish();await job;f.runtime.tick();
    f.runtime.beforeReset();assert.equal(f.current(),'original');f.nativeLoad();
    await f.runtime.afterLoad();assert.equal(f.current(),'new-original');f.runtime.tick();
    assert.equal(f.current(),'prepared');assert.equal(f.stages(),1);
    f.runtime.select(false);f.runtime.tick();assert.equal(f.current(),'new-original');
});
test('failed atlas preparation does not replace a usable font',async()=>{
    const f=fixture(),job=f.runtime.configure(f.manifest);f.fail();await job;
    assert.equal(f.runtime.status().state,'error');assert.equal(f.runtime.status().ready,false);
    assert.equal(f.current(),'original');assert.equal(f.runtime.tick(),false);assert.deepEqual(f.publish,[]);
});
test('repeated preparation shares an in-flight atlas upload',async()=>{
    const f=fixture(),first=f.runtime.configure(f.manifest),second=f.runtime.configure(f.manifest);
    assert.equal(f.stages(),1);
    f.finish();await Promise.all([first,second]);
    assert.equal(f.runtime.tick(),true);assert.deepEqual(f.publish,['prepared']);
});
test('native reset during staging cannot publish the previous source face',async()=>{
    const f=fixture(),first=f.runtime.configure(f.manifest);
    f.runtime.beforeReset();f.nativeLoad();
    const second=f.runtime.afterLoad();assert.equal(f.stages(),1);
    f.finish();await Promise.all([first,second]);
    assert.equal(f.current(),'new-original');f.runtime.tick();
    f.runtime.select(false);f.runtime.tick();assert.equal(f.current(),'new-original');
});
