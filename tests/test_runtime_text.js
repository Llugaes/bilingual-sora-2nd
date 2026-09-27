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

test('element-title producer keeps the native icon and count singular', () => {
    const runtime = new RuntimeText(baseModel({
        producer_numeric: [[
            '幻属性【 属性值：<I48>×(-?(?:0|[1-9][0-9]{0,9})) 】',
            ['Mirage Element [Elemental Value: <I48>x%d]', '幻属性【 属性値：<I48>×%d 】'],
            [['ascii'], ['ascii']],
        ]],
    }));
    const source = '幻属性【 属性值：<I48>×2 】';
    assert.equal(runtime.translate(source, 'primary'), 'Mirage Element [Elemental Value: <I48>x2]');
    assert.equal(runtime.translate(source, 'secondary'), '幻属性【 属性値：<I48>×2 】');
    const plan = runtime.render(source, 'annotation');
    assert.equal(plan.kind, 'layered');
    assert.equal(plan.text.split('<I48>').length - 1, 1);
    assert.equal(plan.layers.reduce((total, layer) => total + layer.text.split('<I48>').length - 1, 0), 1);
    assert.equal(plan.text.split('2').length - 1, 1);
    assert.equal(plan.layers.reduce((total, layer) => total + layer.text.split('2').length - 1, 0), 1);
    assert.equal(runtime.translate('幻属性【 属性值：<I47>×2 】', 'primary'), '幻属性【 属性值：<I47>×2 】');
    assert.equal(runtime.translate('幻属性【 属性值：<I48>×2147483647 】', 'primary'), 'Mirage Element [Elemental Value: <I48>x2147483647]');
    assert.equal(runtime.translate('幻属性【 属性值：<I48>×2147483648 】', 'primary'), '幻属性【 属性值：<I48>×2147483648 】');
});

test('element title survives a full detail label without loosening icon or line boundaries', () => {
    const rule = ['幻属性【 属性值：<I48>×(-?(?:0|[1-9][0-9]{0,9})) 】',
        ['Mirage Element [Elemental Value: <I48>x%d]', '幻属性【 属性値：<I48>×%d 】'], [['ascii'], ['ascii']]];
    const local = baseModel({producer_numeric: [rule], producer_lines: [rule],
        pairs: {'说明': ['Description', '説明']}, plain_pairs: {'说明': ['Description', '説明']}});
    const runtime = new RuntimeText(baseModel({producer_numeric: [rule], producer_lines: [rule],
        plain_pairs: {'2': ['two', '２']}, detail_sources: ['说明'], details: local}));
    for (const [suffix, expected] of [['说明', 'Description'], ['UNKNOWN', 'UNKNOWN']]) {
        const source = '<S32><C1>幻属性【 属性值：<I48>×2 】</C>\n' + suffix;
        assert.equal(runtime.translate(source, 'primary'), '<S32><C1>Mirage Element [Elemental Value: <I48>x2]</C>\n' + expected);
        const plan = runtime.render(source, 'annotation');
        assert.equal(plan.kind, 'layered');
        assert.match(plan.text, /Mirage Element/);
        assert.match(plan.layers.map(x => x.text).join(''), /幻属性【 属性値：<I48>×2 】/);
    }
    for (const title of ['幻属性【 属性值：<I47>×2 】', '幻属性【 属性值：<I48>×2147483648 】',
        '前缀幻属性【 属性值：<I48>×2 】', '幻属性【 属性值：<I48>×2 】后缀',
        '<R>幻属性【 属性值：<I48>×2 】</R注解>', '<R>幻属性【 属性值：<I48>×2 】']) {
        const source = title + '\n说明';
        assert.equal(runtime.producerLinePairs(source).length, 0);
        assert.doesNotMatch(runtime.translate(source, 'primary'), /Mirage Element/);
    }
    const conflict = new RuntimeText(baseModel({producer_lines: [rule, [rule[0], ['OTHER %d', 'OTHER %d'], rule[2]]]}));
    assert.equal(conflict.producerLinePairs('幻属性【 属性值：<I48>×2 】').length, 0);
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
