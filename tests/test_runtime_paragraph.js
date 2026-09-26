'use strict';

const assert=require('node:assert/strict');
const test=require('node:test');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const {RuntimeParagraphs}=require('../sora_bilingual/game/scripts/runtime_paragraph.js');

const model=pairs=>({pairs,plain_pairs:pairs,numeric:[],raw_numeric:[]});

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
