'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {RuntimeBooks}=require('../sora_bilingual/game/scripts/runtime_books');
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text');
const lines=(prefix,count)=>Array.from({length:count},(_,i)=>prefix+i).join('\n');
const document={source:[['cover','原文'],['','原文后半']],primary:[['cover',lines('中文',19)],['',lines('正文',30)]],
    secondary:[['cover',lines('French ',32)],['',lines('German ',53)]]};
test('whole documents preserve every line, order and illustration boundary with bounded pages',()=>{
    const books=new RuntimeBooks({116:document},RuntimeText);
    for(const style of [{},{rubyScale:1,rubyGap:8,lineGap:24,offsetY:24}]) {
        const pages=books.pages(116,'annotation',style),budget=RuntimeBooks.lineBudget(style);
        assert.ok(pages.length>document.source.length);
        for(const side of ['primary','secondary'])assert.equal(pages.flatMap(p=>p[side+'Lines']?p[side].split('\n'):[]).join('\n'),document[side].map(p=>p[1]).join('\n'));
        for(const image of ['cover',''])assert.equal(pages.filter(p=>p.image===image).flatMap(p=>p.primaryLines?p.primary.split('\n'):[]).join('\n'),document.primary.filter(p=>p[0]===image).map(p=>p[1]).join('\n'));
        for(let i=0;i<pages.length;i++) {
            const page=pages[i];assert.ok(page.primary.split('\n').length<=budget);
            assert.ok(page.secondary.split('\n').length<=budget);
            const context=books.context(116,i+1,page.source,'annotation',style);
            const tr=new RuntimeText(context.model);
            assert.equal(tr.translate(page.source,'primary'),page.primary);
            assert.equal(tr.translate(page.source,'secondary'),page.secondary);
            const plan=tr.render(page.source,'annotation');assert.notEqual(plan.kind,'plain');
        }
    }
});
test('single language keeps selected native pagination; unknown identity and changed source fail closed',()=>{
    const books=new RuntimeBooks({116:document},RuntimeText);
    for(const mode of ['primary','secondary']) {
        const pages=books.pages(116,mode);assert.equal(pages.length,document[mode].length);
        assert.deepEqual(pages.map(p=>[p.image,p[mode]]),document[mode]);
    }
    assert.equal(books.pages(999,'annotation'),null);
    assert.equal(books.context(116,1,'different','annotation'),null);
    assert.equal(books.context(116,999,'原文','annotation'),null);
});
test('different illustration order is not page-zipped and saved page limit cannot overflow',()=>{
    const changed={...document,secondary:[['wrong','foreign']]};
    assert.equal(new RuntimeBooks({1:changed},RuntimeText).pages(1,'annotation'),null);
    const long=[['',lines('line',2000)]];
    assert.equal(new RuntimeBooks({1:{source:long,primary:long,secondary:long}},RuntimeText).pages(1,'annotation'),null);
});
