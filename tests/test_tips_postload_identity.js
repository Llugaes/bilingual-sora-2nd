'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const {TableIdentities,scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
const PROFILE='tips_u16_flag_add7400_cap7799_v1';

function fixture(flag=105) {
    const data=Buffer.alloc(256),base=0x10000,at=16,pool=128;
    data.write('#TBL');data.writeUInt16LE(5,at);data.writeUInt16LE(flag,at+2);
    data.writeUInt32LE(17,at+4);data.writeUInt32LE(2,at+16);data.writeUInt32LE(7,at+32);
    for(const off of [8,24,40,48])data.writeBigUInt64LE(BigInt(base+pool),at+off);
    data.write('Shared\0NP\0conditions',pool);
    const record=Buffer.from(data.subarray(at,at+56));
    for(const off of [8,24,40,48])record.fill(0,off,off+8);
    class P {
        constructor(address){this.address=address;}
        add(n){return new P(this.address+n);}
        equals(p){return this.address===p.address;}
        toString(){return String(this.address);}
        readByteArray(n){const off=this.address-base;if(off<0||off+n>data.length)throw Error('unmapped');
            return Uint8Array.from(data.subarray(off,off+n)).buffer;}
        readPointer(){return new P(Number(data.readBigUInt64LE(this.address-base)));}
    }
    const candidate={key:'table/t_tips.tbl/full-owner/title',file:'f',offset:pool,
        record_at:at,field_at:40,record:record.toString('hex'),pointers:[8,24,40,48],
        record_kind:'TipsTableData',record_transform:PROFILE};
    const tables={files:{f:{header:data.subarray(0,8).toString('hex'),floor:pool,size:data.length,
            pool_sha256:scriptSha256(data.subarray(pool))}},
        models:{[candidate.key]:{source:'Shared',model:{pairs:{Shared:['first','second']}}}},
        sources:{Shared:[candidate]}};
    return {data,at,candidate,tables,pointer:new P(base+pool)};
}

test('native Tips post-load flag needs verified capability and keeps full original field',()=>{
    for(const [raw,loaded] of [[105,7505],[399,7799],[400,7799],[65535,7399]]){
        const f=fixture(raw);
        assert.equal(new TableIdentities(f.tables).select(f.pointer,'Shared').key,f.candidate.key);
        f.data.writeUInt16LE(loaded,f.at+2);
        const trace=[];
        assert.equal(new TableIdentities(f.tables).select(f.pointer,'Shared',e=>trace.push(e)),null);
        assert.equal(trace[0].stage,'record_mismatch');
        assert.equal(new TableIdentities(f.tables,scriptSha256,[PROFILE]).select(f.pointer,'Shared').key,f.candidate.key);
        f.data.writeUInt16LE(loaded+1,f.at+2);
        assert.equal(new TableIdentities(f.tables,scriptSha256,[PROFILE]).select(f.pointer,'Shared'),null);
    }
});

test('transform cannot grant another table, field, shape or unverified profile',()=>{
    for(const change of [
        c=>c.record_kind='HelpTitle',c=>c.record_transform='unknown',c=>c.field_at=8,
        c=>c.pointers=[8,40,48],c=>c.record=c.record.slice(0,-2),
    ]){
        const f=fixture();f.data.writeUInt16LE(7505,f.at+2);change(f.candidate);
        assert.equal(new TableIdentities(f.tables,scriptSha256,[PROFILE]).select(f.pointer,'Shared'),null);
    }
});

test('Tips transformation preserves ID, compound scalar metadata, pool and same-source conflicts',()=>{
    for(const off of [0,4,16,20,32,36,129]){
        const f=fixture();f.data.writeUInt16LE(7505,f.at+2);f.data[(off===129?0:f.at)+off]^=1;
        assert.equal(new TableIdentities(f.tables,scriptSha256,[PROFILE]).select(f.pointer,'Shared'),null);
    }
    const f=fixture();f.data.writeUInt16LE(7505,f.at+2);
    const other={...f.candidate,key:'table/t_tips.tbl/another-owner/title'};
    f.tables.sources.Shared.push(other);
    f.tables.models[other.key]={source:'Shared',model:{pairs:{Shared:['different','owner']}}};
    const trace=[];
    assert.equal(new TableIdentities(f.tables,scriptSha256,[PROFILE]).select(f.pointer,'Shared',e=>trace.push(e)),null);
    assert.equal(trace.at(-1).stage,'ambiguous_translation');
});
