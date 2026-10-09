'use strict';
const assert=require('node:assert/strict'),test=require('node:test');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const base=extra=>({pairs:{},plain_pairs:{},numeric:[],raw_numeric:[],producer_numeric:[],detail_numeric:[],...extra});
function details(equivalent=false) {
    const rows=[['A',['JA','ZA']],['B',['JB','ZB']],['C',['JC','ZC']],
        ['A, B',equivalent?['JA、JB','ZA，ZB']:['JAB','ZAB']]];
    return base({detail_join:[', ','、','，'],detail_join_literals:rows.map(r=>r[0]),
        detail_join_pairs:Object.fromEntries(rows),plain_pairs:Object.fromEntries(rows),
        detail_effect_units:rows.map(([pattern,pair],i)=>({pattern,pair,ids:['effect/'+i+'/name']}))});
}
const visible=plan=>plan.text.replace(/<[^<>]*>/g,'');

test('hard partition refusal survives context, component and final render fallbacks',()=>{
    const source='A, B, C',detail=details();
    for(const context of [null,'','Known description'])for(const mode of ['primary','secondary','annotation']) {
        const tr=new RuntimeText(detail);
        assert.equal(tr.translate(source,mode,'','',context),source);
        assert.equal(tr.effectUnitFailures.get(source),'different_partition_targets');
        assert.equal(tr.translate(source,mode,'','',context),source,'warm decision');
    }
    const tr=new RuntimeText(base({details:detail,detail_sources:['Known description']}));
    const plan=tr.render(source+'\nKnown description');
    assert.equal(visible(plan),source+'\nKnown description');
    assert.equal(plan.layers.length,0);
});

test('equivalent partitions choose independent units and complete records survive refusal',()=>{
    const source='A, B, C',equivalent=new RuntimeText(details(true));
    assert.equal(equivalent.effectUnits(source).filter(u=>u.semantic_ids).length,3);
    assert.equal(equivalent.translate(source,'primary','','','Known description'),'JA、JB、JC');
    const pair=['Complete record','完整记录'];
    const tr=new RuntimeText({...details(),pairs:{[source]:pair},plain_pairs:{[source]:pair}});
    assert.equal(tr.effectUnits(source),null);
    for(const mode of ['primary','secondary'])
        assert.equal(tr.translate(source,mode,'','','Known description'),pair[mode==='primary'?0:1]);
    assert.equal(visible(tr.render(source)),pair[0]);
});

test('partial effect membership refuses while unrelated headers retain their fallback',()=>{
    const tr=new RuntimeText({...details(),pairs:{Title:['見出し','标题']},plain_pairs:{Title:['見出し','标题']}});
    for(const source of ['A, Unknown','A, , B',Array(33).fill('A').join(', ')])
        assert.equal(tr.translate(source,'primary','','','Known description'),source);
    assert.equal(tr.translate('Title','primary','','','Known description'),'見出し');
    assert.equal(tr.translate('Unknown','primary','','','Known description'),'Unknown');
    const ruby='<R>A</Rnative>';
    assert.equal(tr.translate(ruby,'primary','','','Known description'),ruby);
});

test('valid owner key or scope precedes semantic segmentation in every target order',()=>{
    const source='A, B\nKnown description';
    for(const owned of [['Owned header\nOwned description','所有者正文'],
        ['所有者正文','Owned header\nOwned description'],['En owner','De owner']]) {
        for(const channel of ['key','scope']) {
            const scoped=base({pairs:{[source]:owned},plain_pairs:{[source]:owned}});
            const tr=new RuntimeText(base({details:details(),detail_sources:['Known description'],
                ...(channel==='key'?{keyed:{OWNER:{source,model:scoped}}}:{scoped:{OWNER:scoped}})}));
            const key=channel==='key'?'OWNER':'',scope=channel==='scope'?'OWNER':'';
            const plan=tr.render(source,'annotation',key,scope);
            assert.equal(visible(plan),owned[0]);
            assert.equal(tr.translate(source,'primary',key,scope),owned[0]);
            assert.equal(tr.translate(source,'secondary',key,scope),owned[1]);
            assert.equal(plan.layers.filter(l=>l.semantic_ids).length,0);
            assert.deepEqual(tr.render(source,'annotation',key,scope),plan);
        }
    }
});

test('owner colors, hard lines and native ruby remain intact',()=>{
    const source='A, B\nKnown description',owned=['<C2>Own<R>字</Rじ></C>\r\nBody','<C3>自有字</C>\r\n正文'];
    const tr=new RuntimeText(base({details:details(),detail_sources:['Known description'],
        keyed:{OWNER:{source,model:base({pairs:{[source]:owned}})}}}));
    const plan=tr.render(source,'annotation','OWNER');
    assert.ok(plan.text.includes('<C2>Own<R>字</Rじ></C>\r\n'));
    assert.equal(plan.layers.filter(l=>l.semantic_ids).length,0);
    assert.ok(plan.layers.some(l=>l.protected));
});

test('owned segmentation is allowed only when both reconstructed complete targets agree',()=>{
    const source='A, B',pair=['JA、JB','ZA，ZB'],detail=details(true);
    const tr=new RuntimeText(base({details:detail,keyed:{OWNER:{source,model:base({pairs:{[source]:pair}})}}}));
    assert.equal(tr.render(source,'annotation','OWNER').layers.filter(l=>l.semantic_ids).length,2);
    const bad=new RuntimeText(base({details:detail,keyed:{OWNER:{source,model:base({pairs:{[source]:[pair[0],'另一所有者']}})}}}));
    assert.equal(bad.render(source,'annotation','OWNER').layers.filter(l=>l.semantic_ids).length,0);
});

test('canonical integer owner preserves its full target and stale key grants no ownership',()=>{
    const template='A %d, B\nKnown description',source='A 5, B\nKnown description';
    const owned=base({numeric:[['A ([+-]?\\d+), B\\nKnown description',['Owner %d\nBody','自有%d\n正文']]]});
    const tr=new RuntimeText(base({keyed:{OWNER:{source:template,model:owned}},details:details(),detail_sources:['Known description']}));
    assert.equal(tr.keyedMatches('OWNER',source),true);
    assert.equal(visible(tr.render(source,'annotation','OWNER')),'Owner 5\nBody');
    assert.equal(tr.ownerPair('A +5, B\nKnown description','OWNER'),null);
    assert.equal(tr.ownerPair('Different','OWNER'),null);
    assert.equal(tr.ownerPair(source,'MISSING'),null);
});

test('no context, empty context and literal null have order independent typed caches',()=>{
    const detail=base({detail_join:[', ','、','，'],detail_effect_units:[{pattern:'A',pair:['JA','ZA'],ids:['effect/a/name']}]});
    for(const order of [[null,'','null'],['null','',null],['',null,'null']]) {
        const tr=new RuntimeText(detail);
        for(const context of order) {
            const cold=new RuntimeText(detail).translate('A','primary','','',context);
            assert.equal(tr.translate('A','primary','','',context),cold);
            assert.equal(tr.translate('A','primary','','',context),cold);
            assert.equal(cold,context===null?'A':'JA');
        }
    }
});

test('bound effect roles precede unowned decorated templates while owned identities remain first',()=>{
    const source='A<I270> (5 turns)',pattern='A<I270> \\((\\d+) turns\\)';
    for(const targets of [['5ターンA<I270>','5回合A<I270>'],['5回合A<I270>','5ターンA<I270>']]) {
        const templates=targets.map(t=>'<C2>'+t.replace('5','%d')+'</C>');
        const detail=base({detail_join:[', ','、','，'],raw_numeric:[[pattern,templates]],
            detail_effect_units:[{pattern,pair:targets.map(t=>t.replace('5','%d')),ids:['typed16/name']}]});
        const tr=new RuntimeText(base({details:detail,detail_sources:['Body']}));
        assert.deepEqual(tr.details.rawPair(source),targets.map(t=>'<C2>'+t+'</C>'));
        for(const [side,mode] of ['primary','secondary'].entries()) {
            assert.equal(tr.details.translate(source,mode),'<C2>'+targets[side]+'</C>');
            assert.equal(tr.details.translate(source,mode,'','','Body'),targets[side]);
            assert.equal(tr.translate(source+'\nBody',mode),targets[side]+'\nBody');
        }
        assert.equal(tr.render(source+'\nBody').layers.filter(l=>l.semantic_ids).length,1);
        const full=source+'\nBody',owned=['<C3>Owner</C>\nOwned body','<C4>所有者</C>\n正文'];
        const keyed=new RuntimeText(base({details:detail,detail_sources:['Body'],
            keyed:{OWNER:{source:full,model:base({pairs:{[full]:owned}})}}}));
        assert.equal(keyed.translate(full,'primary','OWNER'),owned[0]);
        assert.equal(visible(keyed.render(full,'annotation','OWNER')),'Owner\nOwned body');
        assert.equal(keyed.render(full,'annotation','OWNER').layers.filter(l=>l.semantic_ids).length,0);
    }
});
