'use strict';
// Bounded baseline replay. Existing tests and RuntimeText files are read only.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const Module = require('node:module');
const repo = path.resolve(__dirname, '..');
const testPath = path.join(repo, 'tests/test_runtime_text.js');
const testName = 'complete effect sentence admission retains independent semantic annotation units';
const hash = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');

if (process.env.R32_EFFECT_BASELINE_HOOK === '1') {
    const selected = path.resolve(process.env.R32_EFFECT_BASELINE_RUNTIME);
    const originalLoad = Module._load;
    Module._load = function(request, parent, isMain) {
        if (parent && typeof parent.filename === 'string' && path.resolve(parent.filename) === testPath &&
            request === '../sora_bilingual/game/scripts/runtime_text.js')
            return originalLoad.call(this, selected, parent, isMain);
        return originalLoad.call(this, request, parent, isMain);
    };
} else if (require.main === module) {
    const baseModel = overrides => ({pairs:{}, plain_pairs:{}, numeric:[], raw_numeric:[],
        producer_numeric:[], detail_numeric:[], ...overrides});
    const probe = filename => {
        const {RuntimeText} = require(filename);
        const source = 'HP Regen, CP Regen';
        const pair = ['HP徐々回復、CP徐々上昇', 'HP逐渐回复，CP逐渐上升'];
        const independentRows = [
            {pattern:'^HP Regen$', pair:['HP徐々回復','HP逐渐回复'], ids:['effect/HP/name']},
            {pattern:'^CP Regen$', pair:['CP徐々上昇','CP逐渐上升'], ids:['effect/CP/name']},
        ];
        const completeRow = {pattern:'^HP Regen, CP Regen$', pair, ids:['effect/combined']};
        const details = rows => baseModel({detail_join:[', ','、','，'], detail_effect_units:rows});
        const input = rows => baseModel({pairs:{[source]:pair}, details:details(rows)});
        const capture = rows => {
            const tr = new RuntimeText(input(rows));
            const value = {input:input(rows), source, expected_pair:pair, expected_layer_count:2};
            for (const [name, run] of [
                ['whole_unit', () => tr.details.effectUnit(source)],
                ['effect_units', () => tr.details.effectUnits(source)],
                ['line_units', () => tr.details.effectLineUnits(source)],
                ['detail_plan', () => tr.effectDetailPlan(source)],
                ['annotation_plan', () => tr.render(source)],
                ['primary_plan', () => tr.render(source,'primary')],
                ['secondary_plan', () => tr.render(source,'secondary')],
            ]) {
                value[name] = run();
                value[name + '_failures'] = {outer:[...tr.effectUnitFailures], details:[...tr.details.effectUnitFailures]};
            }
            return value;
        };
        const wrongPair = ['別文','另文'];
        const mismatch = new RuntimeText(input([{...completeRow, pair:wrongPair}, ...independentRows]));
        const mismatchUnits = mismatch.details.effectUnits(source);
        return {
            independent:capture(independentRows),
            combined:capture([completeRow,...independentRows]),
            disagreement:{source, whole_pair:wrongPair, independent_pair:pair,
                expected:null, actual_units:mismatchUnits, failures:[...mismatch.details.effectUnitFailures]},
        };
    };
    if (process.argv[2] === '--probe') {
        process.stdout.write(JSON.stringify(probe(path.resolve(process.argv[3]))));
    } else {
        const output = path.resolve(process.argv[2] || path.join(repo,'generated/r32-effect-units-baseline.json'));
        const variants = [
            ['current','sora_bilingual/game/scripts/runtime_text.js'],
            ['local1','dist/comprehensive-1.0.0-dev5-r32-coverage-local1/DEV/sora_bilingual/game/scripts/runtime_text.js'],
            ['r31','dist/comprehensive-1.0.0-dev5-r31-language-follow-local1/DEV/sora_bilingual/game/scripts/runtime_text.js'],
        ];
        const receipt = {created_at:new Date().toISOString(), scope:'one unchanged named Node test plus bounded function probes',
            original_test:testPath, test_name:testName, test_sha256_before:hash(testPath),
            checker:__filename, checker_sha256:hash(__filename), node:process.version,
            production_modified:false, game_attached:false, build_run:false, variants:[]};
        if (fs.existsSync(output)) {
            const prior = JSON.parse(fs.readFileSync(output,'utf8'));
            if (prior.variants.some(v => (v.stdout + v.stderr).includes('ERR_INVALID_ARG_TYPE')))
                receipt.prior_invalid_harness_attempt = {created_at:prior.created_at,
                    checker_sha256:prior.checker_sha256, variants:prior.variants.map(v => ({label:v.label,
                        exit_code:v.exit_code,stdout:v.stdout,stderr:v.stderr})),
                    reason:'preload parent.filename was null; this attempt did not execute the named assertion'};
        }
        for (const [label, relative] of variants) {
            const filename = path.join(repo,relative), before = hash(filename);
            const args = ['--require',__filename,'--test','--test-reporter=tap','--test-name-pattern','^'+testName+'$',testPath];
            const result = cp.spawnSync(process.execPath,args,{cwd:repo,encoding:'utf8',
                env:{...process.env,R32_EFFECT_BASELINE_HOOK:'1',R32_EFFECT_BASELINE_RUNTIME:filename}});
            const diagnostic = cp.spawnSync(process.execPath,[__filename,'--probe',filename],
                {cwd:repo,encoding:'utf8',env:{...process.env,R32_EFFECT_BASELINE_HOOK:'0'}});
            const after = hash(filename);
            receipt.variants.push({label,runtime:filename,sha256_before:before,sha256_after:after,
                unchanged_during_probe:before===after, command:{executable:process.execPath,args,
                    environment:{R32_EFFECT_BASELINE_HOOK:'1',R32_EFFECT_BASELINE_RUNTIME:filename}},
                exit_code:result.status,signal:result.signal,stdout:result.stdout,stderr:result.stderr,
                named_assertion_executed:(result.stdout+result.stderr).includes('longest complete constructor swallowed independent units'),
                diagnostic_exit_code:diagnostic.status,
                probe:diagnostic.status===0?JSON.parse(diagnostic.stdout):null,diagnostic_stderr:diagnostic.stderr});
        }
        receipt.test_sha256_after=hash(testPath);
        receipt.test_unchanged=receipt.test_sha256_before===receipt.test_sha256_after;
        fs.writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');
        console.log(JSON.stringify({receipt:output,test_unchanged:receipt.test_unchanged,
            variants:receipt.variants.map(v=>({label:v.label,sha256:v.sha256_before,exit_code:v.exit_code,
                named_assertion_executed:v.named_assertion_executed,unchanged:v.unchanged_during_probe,
                independent_layers:v.probe?.independent.annotation_plan.layers.length,
                combined_layers:v.probe?.combined.annotation_plan.layers.length,
                combined_units:v.probe?.combined.effect_units?.length,
                disagreement_rejected:v.probe?.disagreement.actual_units===null}))},null,2));
    }
}
