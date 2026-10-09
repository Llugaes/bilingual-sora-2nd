'use strict';
// Replay saved read-only resident bytes; never attach or mutate the game.
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {TableIdentities,scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const receipt=JSON.parse(fs.readFileSync('generated/r19-production-receipt.json','utf8'));
const wire=fs.readFileSync(receipt.wire_path);
assert.equal(crypto.createHash('sha256').update(wire).digest('hex'),receipt.wire_sha256);
const read=new Function('rpc',fs.readFileSync('sora_bilingual/game/scripts/native_transport.js','utf8')+'\nreturn readIndexedModel;')({exports:{}});
const model=read(wire.buffer.slice(wire.byteOffset,wire.byteOffset+wire.byteLength));
const evidence=JSON.parse(fs.readFileSync('generated/r19-tips-existing-table-readonly.json','utf8'));
const capture=JSON.parse(fs.readFileSync('generated/r19-tips-existing-owner-snapshot-0449.json','utf8'));
const sources=new Set(['Tactical Bonus','Stealing AT Bonuses','Changing Battle Difficulty','Overdrive']);
const captured=capture.all_rows.filter(r=>r.scope==='note_help_title'&&sources.has(r.original));
assert.equal(captured.length,4);
const regions=evidence.tables.map(row=>({family:row.family,base:BigInt(row.blob),
    bytes:fs.readFileSync(`generated/r19-${row.family}-resident-table.bin`)}));
class Pointer {
    constructor(address){this.address=BigInt(address);}
    add(n){return new Pointer(this.address+BigInt(n));}
    equals(other){return this.address===other.address;}
    toString(){return '0x'+this.address.toString(16);}
    readByteArray(length){
        const region=regions.find(r=>this.address>=r.base&&this.address+BigInt(length)<=r.base+BigInt(r.bytes.length));
        if(!region)throw Error('outside saved resident range');
        const off=Number(this.address-region.base);
        return Uint8Array.from(region.bytes.subarray(off,off+length)).buffer;
    }
    readPointer(){return new Pointer(Buffer.from(this.readByteArray(8)).readBigUInt64LE());}
}
const output=[];
for(const region of regions){
    const data=region.bytes,start=data.readUInt32LE(76),stride=data.readUInt32LE(80),count=data.readUInt32LE(84);
    const field=region.family==='tips'?40:8;
    for(const capturedRow of [...captured,{original:'Orbments',text_key:null,scope:null,
        fixture_level:'resource source in saved resident table; reported failing UI carrier not captured'}]){
        // Discover actual source pointers from the saved native table, before consulting model candidates.
        const pointers=new Set();
        for(let i=0;i<count;i++){
            const address=data.readBigUInt64LE(start+i*stride+field),offset=Number(address-region.base);
            if(offset<0||offset>=data.length)continue;
            const end=data.indexOf(0,offset);
            if(end>=offset&&data.toString('utf8',offset,end)===capturedRow.original)pointers.add(address.toString());
        }
        assert.equal(pointers.size,1,'saved source pointer must be unique');
        const pointer=new Pointer([...pointers][0]),trace=[];
        const plain=new TableIdentities(model.table_identities,scriptSha256).select(pointer,capturedRow.original,e=>trace.push(e));
        const verified=new TableIdentities(model.table_identities,scriptSha256,['tips_u16_flag_add7400_cap7799_v1'])
            .select(pointer,capturedRow.original);
        assert.ok(verified);assert.ok(verified.key.startsWith('table/t_'+region.family+'.tbl/'));
        const plan=new RuntimeText(verified.model).render(capturedRow.original,'annotation',capturedRow.text_key||'',capturedRow.scope||'');
        assert.notEqual(plan.text,capturedRow.original);
        if(region.family==='tips'){
            assert.equal(plain,null);assert.ok(trace.some(e=>e.stage==='record_mismatch'));
        }else assert.equal(plain.key,verified.key);
        output.push({source:capturedRow.original,family:region.family,pointer:pointer.toString(),
            fixture_level:capturedRow.fixture_level||null,
            captured_key:capturedRow.text_key,captured_scope:capturedRow.scope,
            without_capability:plain?.key||null,selected_key:verified.key,plan,negative_trace:trace});
    }
}
assert.equal(output.length,10);
const result={wire_sha256:receipt.wire_sha256,level:'saved actual resident buffers and captured original; offline pointer replay',
    owner_injected:false,game_attached:false,candidate_live_verified:false,cases:output};
fs.writeFileSync('generated/r19-tips-resident-replay.json',JSON.stringify(result,null,2));
console.log(JSON.stringify({captured_source_cases:8,unobserved_Orbments_resource_cases:2,
    Tips_captured_red_to_green:4,Help_captured_retained:4,game_attached:false,wire_sha256:receipt.wire_sha256}));
