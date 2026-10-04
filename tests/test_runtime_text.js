'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { RuntimeText } = require('../sora_bilingual/game/scripts/runtime_text.js');

const baseModel = overrides => ({
    pairs: {},
    plain_pairs: {},
    numeric: [],
    raw_numeric: [],
    producer_numeric: [],
    detail_numeric: [],
    ...overrides,
});

test('punctuation fragments cannot inject tutorial text into skill effects or printf arguments',()=>{
    const runtime=new RuntimeText(baseModel({
        pairs:{'...':['...','………']},
        plain_pairs:{',':[',','をセットすると、'],'...':['...','………'],Quick:['Quick','加速']},
        numeric:[['CP\\+([+-]?\\d+)',['CP+%d','CP+%d']],
            ['Slot([^<>\\r\\n]{1,512}?)End',['Slot%sEnd','枠%s終']],
            ['-([^<>\\r\\n]{1,512}?)-',['-%s-','枠%s終']]],
    }));
    const source='<c698>Quick</C><c698>, </C><c698>CP+15</C>';
    assert.equal(runtime.translate(source,'primary'),source);
    assert.equal(runtime.translate(source,'secondary'),'<c698>加速</C><c698>, </C><c698>CP+15</C>');
    assert.ok(!JSON.stringify(runtime.render(source)).includes('をセットすると、'));
    for(const [source,expected] of [['Quick・,','加速・,'],[',・Quick',',・加速'],['Quick・,・...','加速・,・...']]) {
        assert.equal(runtime.translate('<c698>'+source+'</C>','secondary'),'<c698>'+expected+'</C>');
        assert.ok(!JSON.stringify(runtime.render('<c698>'+source+'</C>')).includes('をセットすると、'));
    }
    for(const punctuation of [',','...',', ',' / ']) {
        assert.equal(runtime.component(punctuation,'secondary'),punctuation);
        assert.equal(runtime.literalArgument(punctuation,1),punctuation);
        assert.equal(runtime.translate('Slot'+punctuation+'End','secondary'),'枠'+punctuation+'終');
    }
    assert.equal(runtime.translate('...','secondary'),'………');
    for(const punctuation of ['---','-💡-','-\u{1f7e1}-'])
        assert.equal(runtime.translate('<c698>'+punctuation+'</C>','secondary'),'<c698>'+punctuation+'</C>');
    for(const word of ['Ä','é','한','字','𠀀','あ'])
        assert.equal(runtime.translate('<c698>-'+word+'-</C>','secondary'),'<c698>枠'+word+'終</C>');
});

test('complete pairs render target languages when source alone has native controls',()=>{
    const cases=[
        ['<R>言葉</Rことば>', ['话语','Words']],
        ['Source<w1800>\nsecond line',['第一行\n第二行','First line\nsecond line']],
        ['1,100...1,000...900...',['１１００、１０００、９００……','1,100...1,000...900...']],
    ];
    for(const [source,pair] of cases) {
        const plan=new RuntimeText(baseModel({pairs:{[source]:pair}})).render(source);
        assert.equal(plan.kind,'ruby',source);
        for(const line of pair[1].split('\n'))assert.ok(plan.text.includes('</R'+line+'>'),source);
    }
});

test('different original readings need a secondary layer even with the same Latin base',()=>{
    const source='<R>Ｆｌａｍｍｅ！</R火焰啊！>';
    for(const target of ['<R>Ｆｌａｍｍｅ！</R炎よ！>','<R>Flamme!']) {
        const plan=new RuntimeText(baseModel({pairs:{[source]:[source,target]}})).render(source);
        assert.equal(plan.kind,'layered');
        assert.equal(plan.layers.length,1);
        assert.equal(plan.layers[0].text,target);
        assert.ok(plan.text.endsWith(source));
    }
    assert.equal(RuntimeText.needsAnnotation('<R>ABC</Rsame>','<R>ＡＢＣ</Rsame>'),false);
});

test('complete numeric effect template wins over a free-form constructor, but not another concrete template',()=>{
    const source='危机时2回合“心眼”';
    const numeric=[
        ['危机时([+-]?\\d+)回合“心眼”',['危机时%d回合“心眼”','ピンチ時に%dターン「心眼」']],
        ['危机时([+-]?\\d+)回合([^<>\\r\\n]{1,512}?)([^<>\\r\\n]{1,512}?)',['危机时%d回合%s%s','ピンチ時に%dターン%s%s']],
    ];
    for(const rows of [numeric,[...numeric].reverse()]) {
        const runtime=new RuntimeText(baseModel({numeric:rows,plain_pairs:{'2':['2','２']}}));
        assert.equal(runtime.translate(source,'secondary'),'ピンチ時に2ターン「心眼」');
        assert.equal(runtime.render(source).kind,'ruby');
    }
    numeric.push(['危机时([+-]?\\d+)回合“心眼”',['危机时%u回合“心眼”','別の効果%u']]);
    assert.equal(new RuntimeText(baseModel({numeric})).translate(source,'secondary'),source);
});

test('numeric printf slots are never translated as names, including coloured mixed arguments',()=>{
    const runtime=new RuntimeText(baseModel({plain_pairs:{'2':['Two','２'],'药':['Potion','薬']},
        raw_numeric:[['<C1>([^<>\\r\\n]{1,512}?)</C> ([+-]?\\d+)',['<C1>%s</C> %d','<C1>%s</C> %d']]],
    }));
    assert.equal(runtime.translate('<C1>药</C> 2','primary'),'<C1>Potion</C> 2');
    assert.equal(runtime.translate('<C1>药</C> 2','secondary'),'<C1>薬</C> 2');
});

test('layout size wrapper preserves complete coloured prompt identity and layers', () => {
    const source='确定要移动至<C1>蔡恩拉德酒店</C>吗？';
    const targets=['Fast Travel to <C1>Zahnrad Hotel</C>?','<C1>ツァンラートホテル</C>へ移動しますか？'];
    const runtime=new RuntimeText(baseModel({pairs:{[source]:targets}}));
    for(const prefix of ['<s28>','<S56><s28>']) {
        assert.equal(runtime.translate(prefix+source,'primary'),prefix+targets[0]);
        assert.equal(runtime.translate(prefix+source,'secondary'),prefix+targets[1]);
        const plan=runtime.render(prefix+source);
        assert.equal(plan.kind,'layered');
        assert.ok(plan.layers.some(layer=>layer.text.includes('ツァンラートホテル')));
    }
    const nativeRuby='<s28><R>'+source+'</R原注>';
    assert.equal(runtime.translate(nativeRuby,'secondary'),nativeRuby);
    assert.equal(runtime.rawPair('<s28>蔡恩拉德酒店'),null);
});

function renderFormat(template, values) {
    let at = 0;
    return RuntimeText.renderFormat(template, () => values[at++]);
}

function oldLinearPair(model, source) {
    if (Object.hasOwn(model.plain_pairs, source)) return model.plain_pairs[source];
    const authoritative = [];
    for (const [pattern, pair] of model.detail_numeric) {
        const match = new RegExp('^(?:' + pattern + ')$').exec(source);
        if (!match) continue;
        authoritative.push(pair.map(target => renderFormat(target, match.slice(1))));
    }
    const unique = values => [...new Map(values.map(value => [JSON.stringify(value), value])).values()];
    if (authoritative.length) {
        const matches = unique(authoritative);
        return matches.length === 1 ? matches[0] : null;
    }
    const fallback = [];
    for (const [pattern, pair] of model.numeric) {
        const match = new RegExp('^(?:' + pattern + ')$').exec(source);
        if (!match) continue;
        fallback.push(pair.map(target => renderFormat(target, match.slice(1))));
    }
    const matches = unique(fallback);
    return matches.length === 1 ? matches[0] : null;
}

test('numeric candidate index avoids a full authoritative scan and keeps exact output', () => {
    const rules = Array.from({ length: 2000 }, (_, index) => {
        const label = '效果' + String(index).padStart(4, '0') + '值';
        return [label + '([+-]?\\d+)', [label + '%d', 'Effect ' + index + ' %d']];
    });
    const model = baseModel({ detail_numeric: rules, numeric: rules });
    const runtime = new RuntimeText(model);
    let attempts = 0;
    for (const row of runtime.detailNumeric) {
        const pattern = row[0];
        row[0] = { exec: source => { attempts++; return pattern.exec(source); } };
    }
    assert.deepEqual(runtime.pair('效果1999值25'), ['效果1999值25', 'Effect 1999 25']);
    assert.ok(attempts < 10, `expected a bounded candidate bucket, got ${attempts} regex attempts`);
});

test('resource label components leave icons, counts and punctuation out of secondary text', () => {
    const pairs={'幻属性':['Mirage Element','幻屬性'],'属性值':['Elemental Value','屬性值']};
    const runtime=new RuntimeText(baseModel({pairs,plain_pairs:pairs,
        numeric:[['×([+-]?\\d+)',['x%d','×%d']]]}));
    for(const payload of ['<I48>×2','<I42>×3<I45>×3']) {
        const source='<S32>幻属性【 属性值：'+payload+' 】';
        assert.equal(runtime.translate(source,'primary'),'<S32>Mirage Element【 Elemental Value：'+payload+' 】');
        const plan=runtime.render(source);
        assert.equal(plan.kind,'ruby');
        assert.equal(plan.layers.length,0);
        const ruby=[...plan.text.matchAll(/<R>(.*?)<\/R([^<>]*)>/g)];
        assert.deepEqual(ruby.map(m=>m[2]),['幻屬性','屬性值']);
        assert.equal(plan.text.split('<I').length,source.split('<I').length);
        assert.ok(plan.text.endsWith(payload+' 】'));
    }
    const englishPairs={'Mirage Element':['幻属性','幻屬性'],'Elemental Value':['属性值','屬性值']};
    const english=new RuntimeText(baseModel({pairs:englishPairs,plain_pairs:englishPairs}));
    assert.equal(english.translate('Mirage Element [Elemental Value: <I48>x2]','primary'),
        '幻属性 [属性值: <I48>x2]');
    const spanishPairs={'Elemento espejismo':['幻属性','幻屬性'],'valor elemental':['属性值','屬性值']};
    const spanish=new RuntimeText(baseModel({pairs:spanishPairs,plain_pairs:spanishPairs}));
    assert.equal(spanish.translate('Elemento espejismo (valor elemental: <I48>×2)','primary'),
        '幻属性 (属性值: <I48>×2)');
});

test('indexed resolver matches the old linear oracle for conflicts, fallback and neighbours', () => {
    const model = baseModel({
        detail_numeric: [
            ['效果([+-]?\\d+)', ['效果%d', 'Effect %d']],
            ['效果([+-]?\\d+)', ['效果%d', 'Different %d']],
            ['回合([+-]?\\d+)', ['回合%d', 'Turns %d']],
        ],
        numeric: [
            ['效果([+-]?\\d+)', ['效果%d', 'Effect %d']],
            ['(?:无法索引|fallback)([+-]?\\d+)', ['无法索引%d', 'Fallback %d']],
            ['相邻([+-]?\\d+)', ['相邻%d', 'Neighbour %d']],
            ['普通([+-]?\\d+)', ['普通%d', 'Ordinary %d']],
            ['普通([+-]?\\d+)\\s*', ['普通%d', 'Conflicting ordinary %d']],
            ['STR([^<>\\r\\n]{1,512}?)', ['STR%s', 'STR %s']],
        ],
    });
    const runtime = new RuntimeText(model);
    for (const source of [
        '效果25', '回合5', '无法索引7', '相邻8', '普通9', 'STR↑', '相邻X', '完全无关',
    ]) {
        assert.deepEqual(runtime.pair(source), oldLinearPair(model, source), source);
    }
    assert.equal(runtime.pair('效果25'), null, 'authoritative conflict must not leak to numeric');
    assert.equal(runtime.pair('普通9'), null, 'indexed and fallback numeric conflicts must stay null');
});

test('all concrete templates and complete anchored details match the linear oracle', () => {
    for (const secondaryWord of ['Turns', 'ターン']) {
        const rules = Array.from({ length: 128 }, (_, index) => {
            const label = `状态${index}回合`;
            return [label + '([+-]?\\d+)', [label + '%d', `${secondaryWord} ${index} %d`]];
        });
        const detailModel = baseModel({ detail_numeric: rules, numeric: rules });
        const runtime = new RuntimeText({
            ...baseModel({}),
            details: detailModel,
            detail_sources: ['真实说明'],
        });
        for (let index = 0; index < rules.length; index++) {
            const source = `状态${index}回合${index}\n真实说明`;
            const expected = oldLinearPair(detailModel, `状态${index}回合${index}`);
            assert.deepEqual(runtime.details.pair(`状态${index}回合${index}`), expected);
            const plan = runtime.render(source, 'annotation');
            assert.notEqual(plan.text, source, source);
        }
        assert.equal(runtime.translate('状态127回合X\n真实说明', 'secondary'), '状态127回合X\n真实说明');
        assert.equal(
            runtime.translate('状态127回合127\n非详情说明', 'secondary'),
            '状态127回合127\n非详情说明',
        );
    }
});

test('anchored detail icon templates replace complete coloured turn segments only', () => {
    const detail = baseModel({
        pairs: {
            '技能说明': ['Skill description', '技の説明'],
            'CP逐渐上升': ['CP Regen', 'CP徐々上昇'],
            '解除能力降低': ['Cure Stat Debuff', '能力低下解除'],
        },
        plain_pairs: {
            '技能说明': ['Skill description', '技の説明'],
            'CP逐渐上升': ['CP Regen', 'CP徐々上昇'],
            '解除能力降低': ['Cure Stat Debuff', '能力低下解除'],
        },
        detail_inline_icons: [[
            '<c698>([+-]?\\d+)回合STR<I270></C>',
            ['<c698>STR<I270> (%d turns)</C>', '<c698>%dターンSTR<I270></C>'],
        ]],
    });
    const runtime = new RuntimeText(baseModel({ details: detail, detail_sources: ['技能说明'] }));
    const header = '<c698>5回合STR<I270></C><c698>／</C><c698>CP逐渐上升</C><c698>／</C><c698>解除能力降低</C>';
    const source = header + '\n<C0><C9>技能说明';
    assert.equal(runtime.translate(header, 'primary'), header, 'no detail suffix must deny the inline rule');
    assert.equal(
        runtime.translate(source, 'primary'),
        '<c698>STR<I270> (5 turns)</C><c698>／</C><c698>CP Regen</C><c698>／</C><c698>Cure Stat Debuff</C>\n<C0><C9>Skill description',
    );
    assert.equal(
        runtime.translate(source, 'secondary'),
        '<c698>5ターンSTR<I270></C><c698>／</C><c698>CP徐々上昇</C><c698>／</C><c698>能力低下解除</C>\n<C0><C9>技の説明',
    );
    const plan = runtime.render(source, 'annotation');
    assert.equal(plan.kind, 'layered');
    assert.equal(plan.text.split('<I270>').length - 1, 1, 'primary native icon stays singular');
    assert.ok(plan.layers.some(layer => layer.text.includes('5ターンSTR<I270>')));
});

test('conflicting inline icon spans deny every overlapping replacement', () => {
    const source = '<c698>5回合STR<I270></C>';
    const detail = new RuntimeText(baseModel({
        detail_inline_icons: [
            ['<c698>([+-]?\\d+)回合STR<I270></C>', ['<c698>A%d</C>', '<c698>甲%d</C>']],
            ['<c698>([+-]?\\d+)回合STR<I270></C>', ['<c698>B%d</C>', '<c698>乙%d</C>']],
            ['<c698>([+-]?\\d+)回合STR', ['<c698>C%d</C>', '<c698>丙%d</C>']],
        ],
    }));
    assert.equal(detail.replaceDetailInlineIcons(source, 'primary'), source);
    assert.equal(detail.replaceDetailInlineIcons(source, 'secondary'), source);
});

test('description-scoped detail contexts resolve CP without touching original ruby', () => {
    const detail = baseModel({
        pairs: {
            'Skill description': ['技能说明', '技の説明'],
            // The generic short phrase is deliberately absent: in the full
            // catalog it has conflicting condition/help meanings.
        },
        plain_pairs: {
            'Skill description': ['技能说明', '技の説明'],
        },
        detail_contexts: {
            '<C0><C9>Skill description': {
                '<c698>CP Regen</C>': ['<c698>CP逐渐上升</C>', '<c698>CP徐々上昇</C>'],
            },
        },
    });
    const runtime = new RuntimeText(baseModel({
        details: detail,
        detail_sources: ['Skill description', '<C0><C9>Skill description'],
    }));
    const source = '<c698>CP Regen</C>\n<C0><C9>Skill description';
    assert.equal(
        runtime.translate(source, 'primary'),
        '<c698>CP逐渐上升</C>\n<C0><C9>技能说明',
    );
    assert.equal(runtime.translate('<c698>CP Regen</C>', 'primary'), '<c698>CP Regen</C>');
    assert.equal(
        runtime.translate('<c698>CP Regen</C>\n<C0><C9>Other description', 'primary'),
        '<c698>CP Regen</C>\n<C0><C9>Other description',
    );
    const rubySource = '<R><c698>CP Regen</C></RCP Regen><c698>CP Regen</C>\n<C0><C9>Skill description';
    assert.equal(
        runtime.translate(rubySource, 'primary'),
        '<R><c698>CP Regen</C></RCP Regen><c698>CP逐渐上升</C>\n<C0><C9>技能说明',
    );
});

test('an unclosed ruby wrapper denies all detail span rules', () => {
    const detail = new RuntimeText(baseModel({
        detail_inline_icons: [[
            '<c698>([+-]?\\d+)回合STR<I270></C>',
            ['<c698>STR<I270> (%d turns)</C>', '<c698>%dターンSTR<I270></C>'],
        ]],
        detail_contexts: {
            description: {
                '<c698>CP Regen</C>': ['<c698>CP逐渐上升</C>', '<c698>CP徐々上昇</C>'],
            },
        },
    }));
    const malformed = '<R>已配对</Rpaired><R><c698>5回合STR<I270></C><c698>CP Regen</C>';
    assert.equal(RuntimeText.rubyRanges(malformed), null);
    assert.equal(detail.hasDetailInlineIcon(malformed), false);
    assert.equal(detail.hasDetailContext(malformed, 'description'), false);
    assert.equal(detail.replaceDetailInlineIcons(malformed, 'primary'), malformed);
    assert.equal(detail.replaceDetailContext(malformed, 'primary', 'description'), malformed);
});
