'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const crypto=require('node:crypto');
const {scriptSha256,ScriptIdentities,TableIdentities,LogIdentities}=require('../sora_bilingual/game/scripts/runtime_identity.js');
const model=(a,b)=>({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]},numeric:[]});

test('log identity follows the physical record, not equal text or last observed dialogue',()=>{
    const records=new LogIdentities(),a={source:'好。',identity:{argumentsToken:'36'}},b={source:'好。',identity:{argumentsToken:'151'}};
    records.useOwner('owner');
    records.commit(7,'record bytes',a);records.commit(8,'record bytes',b);
    assert.equal(records.lookup(7,'record bytes'),a);
    assert.equal(records.lookup(8,'record bytes'),b);
    assert.equal(records.lookup(9,'record bytes'),null,'unobserved history must not borrow equal text');
    records.commit(7,'record bytes',null);
    assert.equal(records.lookup(7,'record bytes'),null,'even an identical non-dialogue overwrite clears provenance');
    assert.equal(records.lookup(8,'record bytes'),b);
});

test('log records reject changed bytes, owner replacement, same-address reset, and stale generation',()=>{
    const records=new LogIdentities(),origin={source:'source',identity:{argumentsToken:'1'}};
    records.useOwner('first');records.commit(0,'one',origin);
    assert.equal(records.lookup(0,'two'),null);
    assert.equal(records.lookup(0,'one'),null,'a changed record invalidates instead of temporarily hiding its identity');
    records.commit(0,'one',origin);const generation=records.generation;
    records.useOwner('first');assert.equal(records.lookup(0,'one'),origin);
    records.useOwner('second');assert.equal(records.lookup(0,'one'),null);
    records.commit(0,'one',origin);records.reset('second');
    assert.equal(records.lookup(0,'one'),null,'reset must clear even when the owner address is reused');
    assert.ok(records.generation>generation);
    assert.throws(()=>records.commit(1600,'one',origin),/slot/i);
    assert.throws(()=>records.commit(-1,'one',origin),/slot/i);
    assert.equal(records.lookup(1600,'one'),null);
});

test('script SHA-256 agrees with independent crypto across padding and block boundaries',()=>{
    for(const size of [0,1,3,55,56,63,64,65,511,4096,65536]) {
        const bytes=Buffer.alloc(size);for(let i=0;i<size;i++)bytes[i]=(i*13+7)%256;
        assert.equal(scriptSha256(bytes),crypto.createHash('sha256').update(bytes).digest('hex'));
    }
});

test('same Chinese source follows the exact script and encoded call arguments',()=>{
    const bytes=Buffer.alloc(64,9),hash=scriptSha256(bytes);
    const identities=new ScriptIdentities({scripts:{header:[{size:64,sha256:hash,functions:{Talk:{model:model('别的','他'),calls:{
        '1,3221226000':{model:model('好。','はい。')},'1,3221227000':{model:model('好。','よし。')}
    }}}}]}});
    for(const [token,target] of [['1,3221226000','はい。'],['1,3221227000','よし。']]) {
        assert.equal(identities.select('header',()=>bytes,'Talk',token).model.pairs['好。'][1],target);
    }
    bytes[50]=10;
    assert.equal(identities.select('header',()=>bytes,'Talk','1,3221226000'),null,'address reuse or changed blob must not use cached identity');
    assert.equal(identities.lookup({signature:'header',sha256:'wrong',functionName:'Talk',argumentsToken:'1'}),null);
});

test('dynamic numeric arguments preserve exact static string offsets; overlapping candidates never pick a winner',()=>{
    const bytes=Buffer.alloc(32),hash=scriptSha256(bytes);
    const fn={model:model('共通','共通'),calls:{'?,3221226000':{model:model('好。','はい。')}}};
    const ids=new ScriptIdentities({scripts:{h:[{size:32,sha256:hash,functions:{Talk:fn}}]}});
    assert.equal(ids.select('h',()=>bytes,'Talk','42,3221226000').model.pairs['好。'][1],'はい。');
    fn.calls['42,?']={model:model('好。','よし。')};
    assert.equal(new ScriptIdentities(ids).select('h',()=>bytes,'Talk','42,3221226000').model.pairs['好。'],undefined);
});

test('shared function fallback retains each actual argument vector for language reload',()=>{
    const bytes=Buffer.alloc(32),hash=scriptSha256(bytes);
    const ids=new ScriptIdentities({scripts:{h:[{size:32,sha256:hash,functions:{Talk:{model:model('好','はい'),calls:{}}}}]}});
    assert.equal(ids.select('h',()=>bytes,'Talk','1,2').identity.argumentsToken,'1,2');
    assert.equal(ids.select('h',()=>bytes,'Talk','3,4').identity.argumentsToken,'3,4');
});

function tableFixture() {
    const data=Buffer.alloc(128);data.write('#TBL');data.writeUInt32LE(1,4);
    const base=0x10000,offset=96;data.writeUInt32LE(42,16);data.writeBigUInt64LE(BigInt(base+offset),24);
    data.write('text',96);const record=Buffer.from(data.subarray(16,32));record.fill(0,8,16);
    class P {
        constructor(address){this.address=address;}
        add(n){return new P(this.address+n);}
        equals(p){return this.address===p.address;}
        toString(){return this.address.toString(16);}
        readByteArray(n){const at=this.address-base;if(at<0||at+n>data.length)throw Error('unmapped');return Uint8Array.from(data.subarray(at,at+n)).buffer;}
        readPointer(){return new P(Number(data.readBigUInt64LE(this.address-base)));}
    }
    const file={header:data.subarray(0,8).toString('hex'),floor:96,size:128,pool_sha256:scriptSha256(data.subarray(96))};
    const candidate={key:'item/42',file:'f',offset:96,record_at:16,field_at:8,record:record.toString('hex'),pointers:[8]};
    const tables={sources:{text:[candidate]},models:{'item/42':{source:'text',model:model('text','訳')}},files:{f:file}};
    return {data,tables,pointer:new P(base+offset)};
}

test('table identity validates header, pool, scalar record and live string pointer',()=>{
    const f=tableFixture(),ids=new TableIdentities(f.tables);
    assert.equal(ids.select(f.pointer,'text').key,'item/42');
    assert.equal(ids.select(f.pointer.add(1),'text'),null);
    f.data.writeUInt32LE(99,16);assert.equal(ids.select(f.pointer,'text'),null);
    f.data.writeUInt32LE(42,16);f.data[110]=1;assert.equal(ids.select(f.pointer,'text'),null);
});

test('shared table string pointers with different localisations remain ambiguous',()=>{
    const f=tableFixture();f.tables.sources.text.push({...f.tables.sources.text[0],key:'item/43'});
    f.tables.models['item/43']={source:'text',model:model('text','別訳')};
    assert.equal(new TableIdentities(f.tables).select(f.pointer,'text'),null);
});
