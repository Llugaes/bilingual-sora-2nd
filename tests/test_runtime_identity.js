'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const crypto=require('node:crypto');
const {scriptSha256,ScriptIdentities,TableIdentities,LogIdentities}=require('../sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const model=(a,b)=>({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]},numeric:[]});

test('dynamic item identity preserves distinct outer calls through history and locale reload',()=>{
    const bytes=Buffer.alloc(64,17),hash=scriptSha256(bytes),helper='ITEM_ADD_MESSAGE2_EV';
    const tokens=['1073807359,1073741840,3222711866,1073741841,1073742044,3222711862',
        '1073807359,1073741840,3222713304,1073741841,1073742044,3222713300'];
    const source='拿到了<I7>木门钥匙。',pattern='拿到了<I([0-9]+)>木门钥匙。';
    const keys=[488,0].map((id,i)=>`dynamic/script/a.dat/Outer${i}/called/${id}/item/220`);
    const models=['Received','Obtained'].map(verb=>({pairs:{},plain_pairs:{},numeric:[],
        producer_numeric:[[pattern,['拿到了<I%d>木门钥匙。',verb+' <I%d>Wooden Door Key.'],[['ascii'],['ascii']]]]}));
    const scripts={[hash]:{[helper]:Object.fromEntries(tokens.map((token,i)=>[token,
        {recordKey:keys[i],callId:[488,0][i],sourcePattern:pattern,model:models[i],pc:36}]))}};
    const records=Object.fromEntries(keys.map((key,i)=>[key,{'zh-Hans':models[i]}]));
    const manifest={h:[{size:64,sha256:hash,functions:[helper],callRecords:{}}]};
    const ids=new ScriptIdentities({source_language:'zh-Hans',manifest,dynamic_producers:{scripts,records}});
    const site={pc:36,group:5,command:8},history=new LogIdentities();
    for(let i=0;i<2;i++) {
        const identity=ids.capture('h',()=>bytes,helper,tokens[i],site,source);
        assert.equal(identity.recordKey,keys[i]);
        assert.equal(identity.callId,[488,0][i]);
        history.commit(i,'stamp'+i,identity);
    }
    const reloaded=new ScriptIdentities({source_language:'ja',dynamic_producers:{scripts:{},records}});
    for(let i=0;i<2;i++) {
        const identity=history.lookup(i,'stamp'+i);
        const selected=reloaded.lookup(identity,source);
        assert.equal(new RuntimeText(selected.model).translate(source,'secondary'),['Received','Obtained'][i]+' <I7>Wooden Door Key.');
        assert.equal(reloaded.lookup({...identity,recordKey:'missing'},source),null);
    }
    assert.equal(ids.capture('h',()=>bytes,helper,tokens[0],site,'另一种物品。'),null);
    assert.equal(ids.capture('h',()=>bytes,helper,tokens[0],{...site,pc:37},source),null);
    assert.equal(ids.capture('h',()=>Buffer.alloc(64),helper,tokens[0],site,source),null);
    assert.equal(ids.capture('h',()=>bytes,helper,tokens[0],{...site,command:0},source)?.recordKey,undefined);
});

test('dialogue provenance uses the verified call site even when strings and arguments are equal',()=>{
    const bytes=Buffer.alloc(64,7),hash=scriptSha256(bytes),token='1,3221226000';
    const manifest={h:[{size:64,sha256:hash,functions:['Talk'],callSites:{Talk:{
        36:{record:0,token,group:5,command:0},40:{record:1,token,group:5,command:0},
    }}}]};
    const ids=new ScriptIdentities({manifest});
    const a=ids.capture('h',()=>bytes,'Talk',token,{pc:36,group:5,command:0});
    const b=ids.capture('h',()=>bytes,'Talk',token,{pc:40,group:5,command:0});
    assert.equal(a.callId,0);assert.equal(b.callId,1);
    assert.notDeepEqual(a,b,'independent calls must not share a dialogue identity');
    assert.equal(ids.capture('h',()=>bytes,'Talk',token,{pc:37,group:5,command:0}),null);
    assert.equal(ids.capture('h',()=>bytes,'Talk',token,{pc:36,group:5,command:8}),null);
    assert.equal(ids.capture('h',()=>bytes,'Talk','other',{pc:36,group:5,command:0}),null);
    assert.equal(ids.capture('h',()=>bytes,'Talk',token),null,'a site manifest cannot downgrade to string/argument identity');
    const target=new ScriptIdentities({manifest,scripts:{h:[{size:64,sha256:hash,functions:{Talk:{
        records:{0:{model:model('好。','Right.')},1:{model:model('好。','Agreed.')}},
        calls:{[token]:{model:model('好。','Wrong shared fallback')}},model:model('好。','Wrong function fallback'),
    }}}]}});
    assert.equal(target.lookup(a).model.pairs['好。'][1],'Right.');
    assert.equal(target.lookup(b).model.pairs['好。'][1],'Agreed.');
    assert.equal(target.lookup({...a,callId:2}),null,'unknown dialogue ID cannot use another call or function');
});

test('canonical record identity survives a source-script reload without duplicating locale models',()=>{
    const bytes=Buffer.alloc(64,11),hash=scriptSha256(bytes),key='script/a.dat/Talk/called/7/assembled_dialogue';
    const manifest={h:[{size:64,sha256:hash,functions:['Talk'],callSites:{Talk:{
        36:{record:3,token:'1',group:5,command:0},
    }},recordKeys:{Talk:{3:{key,source:'旧源。'}}}}]};
    const captured=new ScriptIdentities({source_language:'zh-Hans',manifest});
    const site={pc:36,group:5,command:0};
    const identity=captured.capture('h',()=>bytes,'Talk','1',site,'旧源。');
    assert.equal(identity.recordKey,key);assert.equal(identity.sourceLocale,'zh-Hans');
    assert.equal(identity.source,'旧源。');
    assert.equal(captured.capture('h',()=>bytes,'Talk','1',site,'错误来源。'),null);

    const active=new ScriptIdentities({
        source_language:'ja',record_pairs:{[key]:0},record_pair_values:[['Primary.','Secondary.']],
        scripts:{},manifest:{},
    });
    const resolved=active.lookup(identity,'旧源。');
    assert.deepEqual(resolved.model.pairs['旧源。'],['Primary.','Secondary.']);
    const translated=new RuntimeText(resolved.model);
    assert.equal(translated.translate('旧源。','primary'),'Primary.');
    assert.equal(translated.translate('旧源。','secondary'),'Secondary.');
    const annotated=translated.render('旧源。','annotation');
    assert.ok(annotated.text.includes('Primary.'));
    assert.ok(annotated.text.includes('Secondary.')||annotated.layers.some(layer=>layer.text.includes('Secondary.')));
    assert.equal(active.lookup(identity,'错误来源。'),null,'a stable key never relaxes exact source validation');
    assert.equal(active.lookup({...identity,source:'伪造。'},'旧源。'),null);
});

test('history marker identity preserves physical calls and only narrows with proven metadata',()=>{
    const a='script/a.dat/Talk/called/7/assembled_dialogue';
    const b='script/b.dat/Talk/called/9/assembled_dialogue';
    const pairModel={
        history_markers:{
            101:[
                ['zh-Hans','<#E_0>同一正文。','甲',a,3],
                ['ja','<#E_4>同一正文。','甲',a,4],
            ],
            102:[['zh-Hans','动态正文。',null,a,3]],
            103:[
                ['zh-Hans','冲突。',null,a,3],
                ['zh-Hans','冲突。','甲',b,8],
            ],
            65536:[['zh-Hans','宽标记。',null,a,3]],
            11:[['zh-Hans','小标记。',null,a,3]],
            12:[['zh-Hans','十二。',null,a,3]],
        },
        record_pairs:{[a]:0,[b]:1},
        record_pair_values:[['主。','副。'],['错误主。','错误副。']],
    };
    const ids=new ScriptIdentities(pairModel);
    const shared=ids.historyMarkerIdentity(101,'甲','<#E[99]>同一正文。');
    assert.equal(shared.callId,7,'stable canonical call remains the strict-dialogue key');
    assert.equal(shared.recordKey,a);
    assert.equal(shared.source,'<#E[99]>同一正文。','the actual runtime expression head is retained');
    assert.deepEqual(shared.sourceLocales,['ja','zh-Hans']);
    assert.deepEqual(shared.sourceCallIds,{ja:4,'zh-Hans':3});
    assert.equal(Object.hasOwn(shared,'sourceLocale'),false,'an unknown old locale is not guessed');
    assert.deepEqual(ids.lookup(shared,shared.source).model.pairs[shared.source],['<#E[99]>主。','<#E[99]>副。']);
    assert.equal(ids.historyMarkerIdentity(101,'乙','<#E_1>同一正文。'),null,'known speaker remains exact');
    assert.equal(ids.historyMarkerIdentity(101,'甲','<#E_1><K4>同一正文。'),null,'body controls remain identity-bearing');
    assert.equal(ids.historyMarkerIdentity(101,'甲','<#E_1>不同正文。'),null);

    const dynamic=ids.historyMarkerIdentity(102,'尤莉亚上尉','动态正文。');
    assert.equal(dynamic.recordKey,a,'missing static speaker metadata is not a qualification filter');
    assert.equal(dynamic.sourceLocale,'zh-Hans');
    assert.equal(ids.historyMarkerIdentity(103,'甲','冲突。'),null,'different physical calls never merge');
    assert.equal(ids.historyMarkerIdentity(103,'乙','冲突。').recordKey,a,'speaker can exclude a proven mismatch');
    assert.equal(ids.historyMarkerIdentity(65536,'任意','宽标记。').recordKey,a,'the persisted marker is a u32');
    assert.equal(ids.historyMarkerIdentity(11,'任意','小标记。').recordKey,a,'an operand equal to opcode 11 remains data');
    assert.equal(ids.historyMarkerIdentity(12,'任意','十二。').recordKey,a,'an operand equal to opcode 12 remains data');
    for(const marker of [0,-1,0xffff,0x100000000,1.5])assert.equal(ids.historyMarkerIdentity(marker,'甲','同一正文。'),null);
});

test('canonical records preserve a runtime expression head but reject body controls or text changes',()=>{
    const bytes=Buffer.alloc(64,12),hash=scriptSha256(bytes),key='script/a.dat/Talk/called/8/assembled_dialogue';
    const site={pc:36,group:5,command:0},manifest={h:[{
        size:64,sha256:hash,functions:['Talk'],
        callSites:{Talk:{36:{record:4,token:'1',group:5,command:0}}},
        recordKeys:{Talk:{4:{key,source:'<#E_0><K4>资源正文。'}}},
    }]};
    const captured=new ScriptIdentities({source_language:'zh-Hans',manifest});
    const actual='<#E_9><K4>资源正文。';
    const identity=captured.capture('h',()=>bytes,'Talk','1',site,actual);
    assert.equal(identity.source,actual);
    assert.equal(captured.capture('h',()=>bytes,'Talk','1',site,'<#E_9><K5>资源正文。'),null);
    assert.equal(captured.capture('h',()=>bytes,'Talk','1',site,'<#E_9><K4>不同正文。'),null);

    const active=new ScriptIdentities({
        record_pairs:{[key]:0},
        record_pair_values:[['<#E_0><K4>主语言。','<#E_0><K4>副语言。']],
    });
    const found=active.lookup(identity,actual),translated=new RuntimeText(found.model);
    assert.equal(translated.translate(actual,'primary'),'<#E_9><K4>主语言。');
    assert.equal(translated.translate(actual,'secondary'),'<#E_9><K4>副语言。');
    assert.equal(translated.translate('<K4>资源正文。','secondary'),'<K4>副语言。');
    const annotated=translated.render(actual,'annotation');
    assert.ok(annotated.text.includes('<#E_9>'));
    assert.ok(annotated.text.includes('主语言。'));
    assert.ok(annotated.text.includes('副语言。')||annotated.layers.some(layer=>layer.text.includes('副语言。')));
    assert.equal(active.lookup(identity,'<#E_1><K4>资源正文。'),null,'lookup retains the exact captured source');
});

test('VM operand identity resolves canonical IDs without guessing nested call instruction order',()=>{
    const bytes=Buffer.alloc(128,7),sha256=scriptSha256(bytes);
    const candidate={size:128,sha256,functions:['Talk'],callRecords:{Talk:{
        '5:0:1,32':[7],'5:0:?,33':[8],'5:0:1,44':[9,10],
    }},callSites:{Talk:{}}};
    const ids=new ScriptIdentities({manifest:{h:[candidate]}});
    const read=()=>bytes,site={pc:100,group:5,command:0};
    assert.equal(ids.capture('h',read,'Talk','1,32',site).callId,7);
    assert.equal(ids.capture('h',read,'Talk','999,33',site).callId,8);
    assert.equal(ids.capture('h',read,'Talk','1,44',site),null,'equal operands cannot merge distinct called IDs');
    candidate.callSites.Talk[100]={record:10,group:5,command:0};
    assert.equal(ids.capture('h',read,'Talk','1,44',site).callId,10);
    assert.equal(ids.capture('h',read,'Talk','1,32',{...site,pc:129}),null);
    assert.equal(ids.capture('h',read,'Talk','1,99',site).callId,undefined,'dynamic producers retain their separate resolver contract');
});

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

test('manifest captures a valid untranslated source identity for a later language model',()=>{
    const bytes=Buffer.alloc(64,7),hash=scriptSha256(bytes);
    const source=new ScriptIdentities({manifest:{h:[{size:64,sha256:hash,functions:['Talk']}]}});
    assert.equal(source.canCapture('h'),true);
    const identity=source.capture('h',()=>bytes,'Talk','1,3221226000');
    assert.deepEqual(identity,{signature:'h',sha256:hash,functionName:'Talk',argumentsToken:'1,3221226000'});
    assert.equal(source.lookup(identity),null,'capturing provenance does not invent a translation');
    assert.equal(source.capture('h',()=>bytes,'Missing','1'),null);
    bytes[0]=8;
    assert.equal(source.capture('h',()=>bytes,'Talk','1,3221226000'),null);
    const target=new ScriptIdentities({scripts:{h:[{size:64,sha256:scriptSha256(Buffer.alloc(64,7)),functions:{Talk:{model:model('other','other'),calls:{
        '1,3221226000':{model:model('好。','はい。')},'1,3221227000':{model:model('好。','よし。')}
    }}}}]}});
    assert.equal(target.canCapture('h'),true,'old resolver models remain provenance candidates');
    assert.deepEqual(target.capture('h',()=>Buffer.alloc(64,7),'Talk','1,3221226000'),identity);
    assert.equal(target.lookup(identity).model.pairs['好。'][1],'はい。');
});

test('manifest capture hashes native pointer blobs without converting their pointer',()=>{
    const bytes=Buffer.alloc(64,3),hash=scriptSha256(bytes),pointer={bytes};
    const nativeHash=()=>{throw Error('pointer capture must not use a JS byte hash');};
    nativeHash.pointer=(actual,size)=>{
        assert.equal(actual,pointer);assert.equal(size,64);
        return scriptSha256(actual.bytes);
    };
    const ids=new ScriptIdentities({manifest:{h:[{size:64,sha256:hash,functions:['Talk']}]}},nativeHash);
    assert.deepEqual(ids.capture('h',n=>({pointer,byteLength:n}),'Talk','1'),{
        signature:'h',sha256:hash,functionName:'Talk',argumentsToken:'1',
    });
    assert.equal(ids.capture('h',()=>({pointer,byteLength:63}),'Talk','1'),null);
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
