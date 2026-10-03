'use strict';

const assert=require('node:assert/strict');
const test=require('node:test');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const {RuntimeParagraphs}=require('../sora_bilingual/game/scripts/runtime_paragraph.js');

const model=pairs=>({pairs,plain_pairs:pairs,numeric:[],raw_numeric:[]});

test('lazy paragraph candidates preserve all legacy boundaries, markup and ambiguity after eviction',()=>{
    const pairs={
        '甲\n乙':['甲\n乙','one\ntwo'],'乙\n丙':['乙\n丙','other\nthree'],
        '甲\n乙\n丙':['甲\n乙\n丙','long one\nlong two\nlong three'],
        '首\\n尾':['首\\n尾','first\\nlast'],'首\r\n尾':['首\r\n尾','a\r\nb'],
        '<C1>前\n后</C>':['<C1>前\n后</C>','<C1>first\nlast</C>'],
        '<unknown>前\n后':['<unknown>前\n后','first\nlast'],
        'bad\npair':['bad\npair'],
    };
    for(let i=0;i<150;i++)pairs['头'+i+'\n尾']=['头'+i+'\n尾','start '+i+'\nend'];
    const paragraph_sources={};
    for(const source of Object.keys(pairs)) {
        const [first]=source.split(/\r\n|\n|\\n/);
        (paragraph_sources[first]??=[]).push(source);
    }
    const legacy=new RuntimeParagraphs(model(pairs),RuntimeText);
    const indexed=new RuntimeParagraphs({...model(pairs),paragraph_sources},RuntimeText);
    assert.equal(indexed.byFirstLine.size,0);
    const sources=[...Object.keys(pairs),'前缀\n甲\n乙\n丙\n后缀','同\n甲\n乙\n同\n乙\n丙'];
    for(const source of sources.concat(sources.slice().reverse())) {
        for(const [i,slot] of RuntimeParagraphs.slots(source).entries()) {
            for(const mode of ['primary','secondary','annotation','bilingual'])
                assert.deepEqual(indexed.lookup(source,i,slot.text,mode),legacy.lookup(source,i,slot.text,mode));
        }
    }
    assert.ok(indexed.byFirstLine.size<=128);
});

test('producer integers keep declared digit width and one complete rich-text lane',()=>{
    const bp='BP上升了<C2>2<C0>点。',target='ＢＰが<C2>2<C0>上がった。';
    const tr=new RuntimeText({...model({'2':['2','２']}),producer_numeric:[
        ['BP上升了<C2>(-?(?:0|[1-9][0-9]{0,9}))<C0>点。',['BP上升了<C2>%d<C0>点。','ＢＰが<C2>%d<C0>上がった。'],[['ascii'],['ascii']]],
        ['要支付(-?(?:０|[１-９][０-９]{0,9}))米拉休息吗？',['要支付%d米拉休息吗？','Spend %d mira to rest?'],[['fullwidth'],['ascii']]]
    ]});
    assert.deepEqual(tr.rawPair(bp),[bp,target]);
    const plan=tr.render(bp,'annotation');
    assert.equal(plan.kind,'layered');assert.equal(plan.text,'<R></R_>'+bp);
    assert.deepEqual(plan.layers.map(l=>l.text),[target+RuntimeText.closeColours(target)]);
    assert.deepEqual(tr.rawPair('要支付１００米拉休息吗？'),['要支付１００米拉休息吗？','Spend 100 mira to rest?']);
    assert.equal(tr.rawPair('要支付100米拉休息吗？'),null);
    assert.equal(tr.rawPair('BP上升了<C2>2147483648<C0>点。'),null);
});

test('a mutable emotion header cannot override a complete body conflict',()=>{
    const body='啊，说的也是呢。',source='<#E[1118]#M_0#B[#60s7]>'+body;
    const primary='<#E[1118]#M_0#B[#60s7]>Oh, I almost forgot!';
    const secondary='<#E[1118]#M_0#B[#60s7]>あっと、そうだったわね。';
    const tr=new RuntimeText({...model({[source]:[primary,secondary]}),ambiguous_display:[body]});
    assert.equal(tr.translate(source,'primary'),source);
    assert.equal(tr.translate(source,'secondary'),source);
    assert.equal(tr.render(source,'annotation').kind,'plain');
    assert.equal(new RuntimeText(model({[source]:[primary,secondary]})).translate(source,'primary'),primary);
    const unknown='<#E_9#M_0#B_0>'+body;
    assert.deepEqual(tr.render(unknown,'annotation'),{text:unknown,layers:[],kind:'plain'});
});

test('changed emotion headers retain complete body annotations and real ambiguity stays plain',()=>{
    const body='<K>绯小姐也是，过得好吗？',target='<K>フェイさんこそ元気だった？';
    const source='<#E_0#M_4#B_0>'+body;
    const plan=new RuntimeText(model({[body]:[body,target]})).render(source,'annotation');
    assert.equal(plan.kind,'layered');
    assert.equal(plan.text.replace(/<R><\/R_>/g,''),source);
    assert.deepEqual(plan.layers.map(layer=>layer.text),['フェイさんこそ元気だった？']);
    const conflict='<K>啊，绯小姐！',live='<#E_E#M_4#B_0>'+conflict;
    const tr=new RuntimeText({...model({}),ambiguous_display:[conflict],
        raw_numeric:[['<#E_E#M_4#B_0><K>啊，([^<>]+)！',['<#E_E#M_4#B_0><K>啊，%s！','<#E_E#M_4#B_0><K>Oh! %s!']]]});
    assert.deepEqual(tr.render(live,'annotation'),{text:live,layers:[],kind:'plain'});
});

test('icon-only lines never consume translated words assigned to following text lines',()=>{
    for(const decoration of ['<c930><I300>','<C1><I300></C>','──','42']) {
        const source=decoration+'\n甲\n乙',target=decoration+'\n一\n二';
        const plan=new RuntimeText(model({[source]:[source,target]})).render(source,'annotation');
        if(decoration.includes('<')) {
            assert.equal(plan.text.replace(/<R><\/R_>/g,''),source);
            assert.deepEqual(plan.layers.map(layer=>layer.primary),['甲','乙'],decoration);
            assert.deepEqual(plan.layers.map(layer=>layer.text.replace(/<[^<>]*>/g,'')),['一','二'],decoration);
        } else assert.equal(plan.text,decoration+'\n<R>甲</R一>\n<R>乙</R二>');
    }
});

test('paragraph lookup accepts only an exact multiline record at full-buffer line boundaries',()=>{
    const source='前置\n★根据哈恩队长所说，\n　目击者似乎是在卡鲁迪亚隧道\n　入口的尼克斯。\n尾部\n';
    const block='★根据哈恩队长所说，\n　目击者似乎是在卡鲁迪亚隧道\n　入口的尼克斯。';
    const target='★ハーン隊長の話によると、\n　カルデア隧道の入口にいる\n　ニクスという人が目撃者のようだ。';
    const paragraphs=new RuntimeParagraphs(model({[block]:[block,target]}),RuntimeText);

    const first=paragraphs.lookup(source,1,'★根据哈恩队长所说，','annotation');
    const second=paragraphs.lookup(source,2,'　目击者似乎是在卡鲁迪亚隧道','secondary');
    assert.ok(first);
    assert.equal(first.kind,'ruby');
    assert.equal(second.text,'　カルデア隧道の入口にいる');
    assert.equal(paragraphs.lookup('★根据哈恩队长所说，',0,'★根据哈恩队长所说，','annotation'),null);
    assert.equal(paragraphs.lookup(source,1,'伪造行', 'annotation'),null);
});

test('line index resolves repeated text through its containing exact paragraph',()=>{
    const source='头\n同\n尾一\n同\n尾二\n';
    const one='同\n尾一',two='同\n尾二';
    const paragraphs=new RuntimeParagraphs(model({
        [one]:[one,'One\nFirst tail'],
        [two]:[two,'Two\nSecond tail'],
    }),RuntimeText);

    assert.match(paragraphs.lookup(source,1,'同','secondary').text,/One/);
    assert.match(paragraphs.lookup(source,3,'同','secondary').text,/Two/);
    assert.match(paragraphs.lookup(source,2,'尾一','secondary').text,/tail/);
});

test('primary source bytes remain untouched while target slots reflow styles and native ruby atomically',()=>{
    const block='<#E_0#M_0#B_0>甲甲\n乙乙';
    const target='<C1><B><s27><R>一二</Rいちに>三\n四五六</B></C>';
    const paragraphs=new RuntimeParagraphs(model({[block]:[block,target]}),RuntimeText);

    const primary=paragraphs.lookup(block,0,'<#E_0#M_0#B_0>甲甲','primary');
    const secondary0=paragraphs.lookup(block,0,'<#E_0#M_0#B_0>甲甲','secondary');
    const secondary1=paragraphs.lookup(block,1,'乙乙','secondary');
    assert.equal(primary.text,'<#E_0#M_0#B_0>甲甲');
    assert.match(secondary0.text,/<R>一二<\/Rいちに>/);
    assert.match(secondary0.text,/<C1><B><s27>/);
    assert.match(secondary1.text,/<C1><B><s27>/,'style context is reopened for the next slot');
    assert.match(secondary1.text,/四五六/);
});

test('different primary and secondary line counts reflow independently for all modes',()=>{
    const source='原文甲甲\n原文乙乙';
    const primary='Primary one has a verylongword\nand another sentence\nfor the second slot';
    const secondary='副文一二三\n四五六七';
    const paragraphs=new RuntimeParagraphs(model({[source]:[primary,secondary]}),RuntimeText);

    const one=paragraphs.lookup(source,0,'原文甲甲','primary');
    const two=paragraphs.lookup(source,1,'原文乙乙','primary');
    const annotated=paragraphs.lookup(source,1,'原文乙乙','annotation');
    assert.ok(one.text);
    assert.ok(two.text);
    assert.ok(annotated);
    assert.notEqual(one.text,'原文甲甲');
    assert.equal(paragraphs.lookup(source,0,'原文甲甲','secondary').text,'副文一二三');
});

test('eight language targets retain every reflowed slot across primary secondary and annotation modes',()=>{
    const source='原文甲甲\n原文乙乙';
    const targets=[
        '简体中文一\n简体中文二\n简体中文三',
        '繁體中文一\n繁體中文二\n繁體中文三',
        '日本語一\n日本語二\n日本語三',
        '한국어 하나\n한국어 둘\n한국어 셋',
        'English first\nEnglish second\nEnglish third',
        'Français premier\nFrançais deuxième\nFrançais troisième',
        'Deutsch eins\nDeutsch zwei\nDeutsch drei',
        'Español uno\nEspañol dos\nEspañol tres',
    ];
    for(const target of targets) {
        const paragraphs=new RuntimeParagraphs(model({[source]:[source,target]}),RuntimeText);
        const expected=RuntimeText.reflowAnnotationLines(source,target);
        const actual=[0,1].map(index=>paragraphs.lookup(source,index,source.split('\n')[index],'secondary').text);
        assert.deepEqual(actual,expected,target);
        for(const index of [0,1]) {
            const line=source.split('\n')[index];
            assert.equal(paragraphs.lookup(source,index,line,'primary').text,line,target);
            assert.ok(paragraphs.lookup(source,index,line,'annotation'),target);
        }
    }
});

test('unknown markup and ambiguous longest matches never create a paragraph plan',()=>{
    const unknown='甲\n<X>乙</X>';
    const source='甲\n<X>乙</X>\n';
    const paragraphs=new RuntimeParagraphs(model({[unknown]:[unknown,'一\n二']}),RuntimeText);
    assert.equal(paragraphs.lookup(source,0,'甲','annotation'),null);

    const overlap='甲\n乙\n丙';
    const ambiguous=new RuntimeParagraphs(model({
        '甲\n乙':['甲\n乙','一\n二'],
        '乙\n丙':['乙\n丙','三\n四'],
    }),RuntimeText);
    assert.equal(ambiguous.lookup(overlap,1,'乙','secondary'),null);
});
