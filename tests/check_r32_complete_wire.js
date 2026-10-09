'use strict';
// Replay saved physical producer inputs against receipt-verified indexed wires.
// No resource scan, compilation, guessed identity, or expected-text rewriting.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');

const options={root:path.resolve(__dirname,'..'),runtimeRoot:null,labels:['en'],out:null,classifyOnly:false,recipes:null};
for(let i=2;i<process.argv.length;i++) {
    const arg=process.argv[i];
    if(arg==='--root')options.root=path.resolve(process.argv[++i]);
    else if(arg==='--runtime-root')options.runtimeRoot=path.resolve(process.argv[++i]);
    else if(arg==='--out')options.out=path.resolve(process.argv[++i]);
    else if(arg==='--recipes')options.recipes=path.resolve(process.argv[++i]);
    else if(arg==='--classify-only')options.classifyOnly=true;
    else if(arg==='--labels'){
        options.labels=[];
        while(i+1<process.argv.length&&!process.argv[i+1].startsWith('--'))options.labels.push(process.argv[++i]);
    } else throw new Error('Unknown argument: '+arg);
}
const allLabels=['en','ja','zh-Hans','zh-Hant','en-manual'];
if(options.labels.includes('all'))options.labels=allLabels;
assert(options.labels.length&&options.labels.every(label=>allLabels.includes(label)),'unsupported receipt label');
const root=options.root,runtimeRoot=options.runtimeRoot||root;
const out=options.out||path.join(root,'generated/r32-complete-wire-audit.json');
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const readJSON=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const paths={
    freeze:path.join(root,'generated/r32-coverage-source-freeze.json'),
    tools:path.join(root,'generated/r32-tools-step5-four.json'),
    recipes:options.recipes||path.join(root,'generated/r32-recipes-step5-four.json'),
    fishing:path.join(root,'generated/r32-fishing-raw-producers.json'),
    priorRecipe:path.join(root,'generated/r32-recipe-node-after-strict.json'),
};
const freeze=readJSON(paths.freeze),sourceFiles={};
for(const name of ['runtime_text.js','native_transport.js']) {
    const relative='sora_bilingual/game/scripts/'+name,file=path.join(runtimeRoot,relative);
    sourceFiles[relative]=sha(fs.readFileSync(file));
    assert.equal(sourceFiles[relative],freeze.files[relative],'runtime differs from frozen production source: '+relative);
}
const {RuntimeText}=require(path.join(runtimeRoot,'sora_bilingual/game/scripts/runtime_text.js'));
const readWire=new Function('rpc',fs.readFileSync(path.join(runtimeRoot,'sora_bilingual/game/scripts/native_transport.js'),'utf8')+';return readIndexedModel;')({exports:{}});
const inputHashes=Object.fromEntries(['tools','recipes','fishing'].map(key=>[path.relative(root,paths[key]),sha(fs.readFileSync(paths[key]))]));
const fixtures={tools:readJSON(paths.tools).cases,recipes:readJSON(paths.recipes).cases,fishing:readJSON(paths.fishing)};
assert.equal(fixtures.tools.length,1512,'four-source ordinary producer denominator changed');
const recipeLocales=new Set(fixtures.recipes.map(row=>row.locale));
assert.equal(fixtures.recipes.length,157*2*recipeLocales.size,'physical cooking producer denominator changed');
for(const locale of recipeLocales)assert.equal(fixtures.recipes.filter(row=>row.locale===locale).length,314,'locale cooking denominator changed');
assert.equal(new Set(fixtures.recipes.map(row=>row.item_id)).size,157,'physical outcomes omitted');
assert.equal(fixtures.fishing.length,7,'physical rod denominator changed');

function primaryText(text) {
    return text.replace(/<R>(.*?)<\/R[^<>]*>/gs,'$1');
}
function secondaryText(plan) {
    if(!plan.layers?.length)
        return plan.text.replace(/<R>(.*?)<\/R([^<>]*)>/gs,(_match,base,reading)=>base?reading:'');
    let text=plan.text,at=0;
    for(const layer of plan.layers) {
        const anchor=text.indexOf('<R></R_>',at);
        if(anchor<0||!text.startsWith(layer.primary,anchor+8))
            return {error:'annotation_layer_anchor_or_primary_mismatch',text,layer};
        text=text.slice(0,anchor)+layer.text+text.slice(anchor+8+layer.primary.length);
        at=anchor+layer.text.length;
    }
    // Layer payloads can contain native inline ruby; keep its visible base.
    return primaryText(text);
}
// A separately reported comparison only; strict failures always remain.
const fullwidthEquivalent=text=>typeof text==='string'?text.replace(/[！-～]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xFEE0)):text;
const visible=text=>typeof text==='string'?text.replace(/<[^<>]*>/g,''):text;
const normalizationRules=[
    'Keep strict expected/source/actual unchanged; classify separately.',
    'NFKC and remove layout whitespace; do not reorder words, numbers, or icons.',
    'Ignore only C/c colour and s/S size controls; retain every <I...> icon in order.',
    'In native item header only, remove known bracket/parenthesis/colon/LINK tokens: []()【】:：/・･、.',
    'In native item header only, remove space-hyphen-space join; retain signs and percent marks.',
    'For Fishing bait-list only, remove known comma/、 separators; retain ordered names.',
    'After Tools first newline, retain punctuation and words; only typography/whitespace rules apply.',
];
function semanticProjection(text,domain) {
    if(typeof text!=='string')return null;
    let value=text.normalize('NFKC').replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,'');
    const chunks=value.split(/(\r\n|\n|\\n)/);
    if(domain==='tools'||domain==='recipes')chunks[0]=chunks[0].replace(/\s+-\s+/g,'').replace(/[\[\]()【】:：/・･、]/g,'');
    else if(domain==='fishing')chunks[0]=chunks[0].replace(/[,、]/g,'');
    return chunks.join('').replace(/\s/gu,'');
}
const iconSequence=text=>typeof text==='string'?text.match(/<I\d+>/g)||[]:null;
const numberSequence=text=>typeof text==='string'?visible(text).normalize('NFKC').match(/[+-]?\d+(?:\.\d+)?%?/g)||[]:null;
function classify(run) {
    run.known_frame_semantic_failure_count=0;run.retained_source_formatting_count=0;
    for(const failure of run.failures) {
        const pairs=[[failure.actual.primary,failure.expected.primary]];
        if(failure.mode==='annotation')pairs.push([failure.actual.secondary,failure.expected.secondary]);
        const equal=pairs.every(([actual,expected])=>semanticProjection(actual,failure.domain)===semanticProjection(expected,failure.domain)&&
            JSON.stringify(iconSequence(actual))===JSON.stringify(iconSequence(expected))&&
            JSON.stringify(numberSequence(actual))===JSON.stringify(numberSequence(expected)));
        failure.known_frame_complete_semantics_equal=equal;
        failure.classification=equal?'retained_source_formatting':'semantic_or_field_mismatch';
        if(equal)run.retained_source_formatting_count++;else run.known_frame_semantic_failure_count++;
        failure.unexpected_ascii_words=pairs.flatMap(([actual,expected])=>{
            if(typeof actual!=='string')return [];
            const target=new Set((visible(expected).match(/[A-Za-z][A-Za-z'-]*/g)||[]).map(word=>word.toLowerCase()));
            return (visible(actual).match(/[A-Za-z][A-Za-z'-]*/g)||[]).filter(word=>!target.has(word.toLowerCase()));
        });
    }
}
function summary(runs) {
    return {mode_checks:runs.reduce((sum,r)=>sum+r.mode_checks,0),
        annotation_secondary_checks:runs.reduce((sum,r)=>sum+r.annotation_secondary_checks,0),
        strict_failure_count:runs.reduce((sum,r)=>sum+r.strict_failure_count,0),
        fullwidth_equivalent_failure_count:runs.reduce((sum,r)=>sum+r.fullwidth_equivalent_failure_count,0),
        known_frame_semantic_failure_count:runs.reduce((sum,r)=>sum+r.known_frame_semantic_failure_count,0),
        retained_source_formatting_count:runs.reduce((sum,r)=>sum+r.retained_source_formatting_count,0),
        normal_primary_source_failures:runs.reduce((sum,r)=>sum+r.normal_primary_source_failures,0)};
}
const ids=row=>({...(row.item_id!==undefined?{item_id:row.item_id}:{}),
    ...(row.physical!==undefined?{physical:row.physical}:{}),...(row.key?{key:row.key}:{}),
    ...(row.join!==undefined?{join:row.join}:{}),...(row.styled!==undefined?{styled:row.styled}:{})});

const result=fs.existsSync(out)?readJSON(out):{
    schema:1,runs:[],scope:'receipt wire replay of original Tools/Recipe/Fishing cases; Quest full audit delegated',
    original_inputs_preserved:true,positive_identity_supplied:false,resource_scan:false,build_run:false,game_attached:false,
};
result.source_snapshot_sha256=freeze.snapshot_sha256;
result.runtime_root=runtimeRoot;
result.source_files=sourceFiles;
result.input_sha256=inputHashes;
result.semantic_normalization_rules=normalizationRules;
result.runs.forEach(classify);
if(fs.existsSync(paths.priorRecipe)) {
    const prior=readJSON(paths.priorRecipe);
    result.retained_eight_language_recipe_evidence={path:path.relative(root,paths.priorRecipe),
        sha256:sha(fs.readFileSync(paths.priorRecipe)),loaded_runtime_sha256:prior.runtime_text_sha256,
        runtime_snapshot_unchanged:prior.runtime_snapshot_unchanged,failure_count:prior.failure_count,
        locale_summary:prior.locale_summary,not_revalidated_by_four_source_wire_audit:true};
}

for(const label of options.classifyOnly?[]:options.labels) {
    const receiptPath=path.join(root,`generated/r32-coverage-${label}-production-receipt.json`);
    const receipt=readJSON(receiptPath),config=receipt.config,source=config.game_language;
    assert.equal(receipt.source_snapshot_sha256,freeze.snapshot_sha256,'receipt source snapshot changed');
    const manual=label==='en-manual';
    assert.equal(config.primary,manual?'ja':source,'normal primary must be real source');
    assert.equal(config.experimental_primary,manual,'pairing config differs from receipt contract');
    const wireBytes=fs.readFileSync(receipt.wire_path);
    assert.equal(sha(wireBytes),receipt.wire_sha256,'wire hash mismatch');
    assert.equal(sha(fs.readFileSync(receipt.model_path)),receipt.model_sha256,'complete model hash mismatch');
    let model=readWire(wireBytes.buffer.slice(wireBytes.byteOffset,wireBytes.byteOffset+wireBytes.byteLength));
    let tr=new RuntimeText(model);
    const run={label,source,primary:config.primary,secondary:config.secondary,manual,
        receipt_path:path.relative(root,receiptPath),receipt_sha256:sha(fs.readFileSync(receiptPath)),
        source_snapshot_sha256:receipt.source_snapshot_sha256,model_path:receipt.model_path,
        model_sha256:receipt.model_sha256,wire_path:receipt.wire_path,wire_sha256:receipt.wire_sha256,
        actual_wire_loaded:true,source_files:sourceFiles,input_sha256:inputHashes,
        domain_counts:{},mode_checks:0,annotation_secondary_checks:0,strict_failure_count:0,
        fullwidth_equivalent_failure_count:0,normal_primary_source_checks:0,
        normal_primary_source_failures:0,failures:[],cases:[]};
    for(const domain of ['tools','recipes','fishing']) {
        const inputRows=domain==='fishing'?fixtures[domain]:fixtures[domain].filter(row=>row.locale===source);
        run.domain_counts[domain]=inputRows.length;
        for(const row of inputRows) {
            const value=domain==='fishing'?row.texts[source]:row.source;
            assert.equal(value,row.texts[source],'saved source differs from original locale text');
            const expectedPrimary=manual?row.texts.ja:value;
            const expectedSecondary=row.texts[config.secondary];
            assert.equal(typeof expectedSecondary,'string','missing original target resource');
            const plans={};
            for(const mode of ['primary','secondary','annotation']) {
                const plan=tr.render(value,mode,'','');plans[mode]=plan;run.mode_checks++;
                const actual=primaryText(plan.text);
                const expected=mode==='secondary'?expectedSecondary:expectedPrimary;
                const annotationSecondary=mode==='annotation'?secondaryText(plan):null;
                if(mode==='annotation')run.annotation_secondary_checks++;
                const discrepancies=[];
                if(actual!==expected)discrepancies.push(visible(actual)===visible(expected)?'primary_controls':'primary_semantics');
                if(mode==='annotation'&&annotationSecondary!==expectedSecondary)
                    discrepancies.push(visible(annotationSecondary)===visible(expectedSecondary)?'annotation_secondary_controls':'annotation_secondary_semantics');
                if(!manual&&(mode==='primary'||mode==='annotation')) {
                    run.normal_primary_source_checks++;
                    const preserved=mode==='primary'?plan.text===value:actual===value;
                    if(!preserved){run.normal_primary_source_failures++;discrepancies.push('normal_primary_source_changed');}
                }
                if(discrepancies.length) {
                    run.strict_failure_count++;
                    const widthEquivalent=fullwidthEquivalent(actual)===fullwidthEquivalent(expected)&&
                        (mode!=='annotation'||fullwidthEquivalent(annotationSecondary)===fullwidthEquivalent(expectedSecondary));
                    if(!widthEquivalent)run.fullwidth_equivalent_failure_count++;
                    run.failures.push({domain,...ids(row),mode,source:value,expected:{primary:expected,secondary:mode==='annotation'?expectedSecondary:null},
                        actual:{primary:actual,secondary:annotationSecondary,plan},discrepancies,
                        fullwidth_equivalent:widthEquivalent,
                        refusal:{outer:tr.effectUnitFailures.get(value)||null,
                            details:[...(tr.details?.effectUnitFailures?.entries()||[])].filter(([text])=>text&&value.includes(text)).slice(-16).map(([text,reason])=>({text,reason}))}});
                }
            }
            run.cases.push({domain,...ids(row),source:value,expected:{primary:expectedPrimary,secondary:expectedSecondary},modes:plans});
        }
    }
    run.runtime_source_unchanged=Object.entries(sourceFiles).every(([name,digest])=>sha(fs.readFileSync(path.join(runtimeRoot,name)))===digest);
    assert(run.runtime_source_unchanged,'frozen runtime changed during replay');
    result.runs.push(run);
    classify(run);
    result.latest_labels=Object.fromEntries(allLabels.map(name=>[name,result.runs.map((r,index)=>[r,index]).filter(([r])=>r.label===name).at(-1)?.[1]??null]));
    result.summary=summary(result.runs);
    fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify({...run,cases:undefined,failures:undefined,source_files:undefined,input_sha256:undefined}));
    tr=null;model=null;if(global.gc)global.gc();
}
if(options.classifyOnly){result.summary=summary(result.runs);fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result.summary));}
process.exitCode=(options.classifyOnly?result.runs:result.runs.slice(-options.labels.length)).some(run=>run.strict_failure_count)?1:0;
