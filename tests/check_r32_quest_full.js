'use strict';
// Raw official records are the oracle. No production model is constructed here.
// Run: node --max-old-space-size=4096 tests/check_r32_quest_full.js
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),generated=path.join(root,'generated');
const read=name=>fs.readFileSync(path.join(root,name));
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const json=name=>JSON.parse(read(name).toString('utf8'));
const scripts='sora_bilingual/game/scripts/';
const {RuntimeText}=require(path.join(root,scripts,'runtime_text.js'));
const {RuntimeParagraphs}=require(path.join(root,scripts,'runtime_paragraph.js'));
const split=value=>String(value??'').split(/\r\n|\n|\\n/);
const strip=value=>String(value??'').replace(/<[^<>]*>/g,'');
const norm=value=>strip(value).replace(/\s/gu,'');
const fold=value=>String(value??'').replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0));
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const configurations=[['en','zh-Hans'],['ja','zh-Hans'],['zh-Hans','ja'],['zh-Hant','ja']];
const focusIds={
    classroom:'f51f6b07d66b4bbdee3f595d4adcb74ccef3add90078d9ad909f2eda7384201c',
    dormitory:'279345c2ba6783d0625843227507936025e2ffbf884a604f3d1516d43b579b3e',
    engine:'35b172722d34f6059fba9266feb0b2d196aa9fa420219cd30e0552da2caea2c3',
    emptyanchor_parts:'2ee189e1235510ed5bac19d4e92c66f56d60deff29cae4a2996b0c0a6d7b6787',
    emptyanchor_measure:'64bcf9e86a25b56ae8ec9f35abde29d8d6f0a655a55e88babf9a175cfea53379',
    emptyanchor_final:'e9c2bce28bc64beba07d0b6159c19c092358a0ac580393caa5386f17c4d67658'
};
const keyFor=id=>'table/t_quest.tbl/QuestText/sha256:'+id+'/body';
// Independently read complete marker groups; no runtime line allocator is used.
function groups(value) {
    const out=[];let active=null;
    for(const [index,line] of split(value).entries()) {
        const visible=strip(line).trim();if(!visible){active=null;continue;}
        const first=Array.from(visible)[0];
        const kind=first==='●'?'member':['・','·','•'].includes(first)?'action':['★','☆'].includes(first)?'progress':null;
        if(!active||kind){active={kind:kind||'text',indexes:[],lines:[]};out.push(active);}
        active.indexes.push(index);active.lines.push(line);
    }
    return out;
}
function semanticCheck(source,target,actual) {
    const left=groups(source),right=groups(target),reasons=[];
    const comparable=left.length===right.length&&left.every((group,i)=>group.kind===right[i].kind);
    if(comparable)left.forEach((group,i)=>{
        const lines=group.indexes.map(index=>actual[index]??'');
        if(norm(lines.join('\n'))!==norm(right[i].lines.join('\n')))reasons.push('semantic_group_payload_or_boundary:'+i+':'+group.kind);
        if(group.kind==='member'&&right[i].lines.length===1&&lines.filter(norm).length!==1)reasons.push('single_official_member_split:'+i);
    });
    else if(right.some(group=>group.kind==='member')) {
        const members=value=>groups(value).filter(group=>group.kind==='member').map(group=>norm(group.lines.join('\n')));
        if(!same(members(target),members(actual.join('\n'))))reasons.push('official_member_groups_not_retained');
    }
    return {comparable,reasons};
}
// Decode the wire with the same production transport used by the resident.
function wireModel(bytes,wirePath) {
    let model;const context={rpc:{exports:{load(value){model=value;return true;}}},
        File:{readAllBytes:()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)}};
    vm.runInNewContext(read(scripts+'native_transport.js').toString('utf8'),context);
    context.rpc.exports.modelpackedfile(wirePath,'annotation',true,1,{});
    assert(model?.scoped?.quest_notes,'actual wire lacks scoped.quest_notes');return model;
}
function nativeHarness() {
    const source=read('tests/test_native_agent.js').toString('utf8');
    const boundary=source.indexOf('\ntest(');assert(boundary>0);
    const module={exports:{}};
    new Function('require','__dirname','module',source.slice(0,boundary)+'\nmodule.exports={makeRuntime};')(require,__dirname,module);
    return module.exports.makeRuntime;
}
function inlineSecondary(value) {
    // A reading lives in the closing tag. Parse independently of RuntimeText.
    let out='',at=0;
    for(;;) {
        const start=value.indexOf('<R>',at);if(start<0)break;
        out+=value.slice(at,start);
        const close=value.indexOf('</R',start+3),end=close<0?-1:value.indexOf('>',close+3);
        if(close<0||end<0||value.slice(start+3,close).includes('<R>'))throw Error('unbalanced_annotation_ruby');
        out+=value.slice(close+3,end);at=end+1;
    }
    return out+value.slice(at);
}
function annotationPayload(plan,secondary) {
    if(!norm(secondary))return '';
    if(plan.kind==='layered')return (plan.layers||[]).map(layer=>layer.text).join('\n');
    if(plan.kind==='ruby')return inlineSecondary(plan.text);
    return plan.text;
}
function expectedFocus(kind,source,target,sourceLanguage) {
    if(['classroom','dormitory','engine'].includes(kind)) {
        const expected=split(target);if(sourceLanguage==='en')expected.splice(1,0,'');return expected;
    }
    if(sourceLanguage==='en') {
        const positions=split(source).flatMap((line,i)=>norm(line)?[i]:[]),targetLines=split(target).filter(norm);
        assert(targetLines.length<=positions.length,'explicit empty-anchor fixture must fit whole official lines');
        const expected=split(source).map(()=>'');targetLines.forEach((line,i)=>{expected[positions[i]]=line;});return expected;
    }
    return null;
}
function counters() {
    return {cases:0,eligible:0,raw_missing_locale_records:0,compiler_rejected_records:0,unsupported_control_records:0,
        primary_exact_pass:0,secondary_complete_pass:0,annotation_strict_pass:0,annotation_width_equivalent_pass:0,
        semantic_group_pass:0,semantic_group_not_comparable:0,quest_lines_null:0,lookup_null:0,
        secondary_on_empty_source_records:0,member_split_records:0,strict_failure_records:0,width_equivalent_failure_records:0};
}
function rawRejections(entries,sourceLanguage,targetLanguage) {
    const bySource=new Map(),missing=[];
    for(const entry of entries) {
        const source=entry.texts?.[sourceLanguage],target=entry.texts?.[targetLanguage];
        if(typeof source!=='string'||!source.trim()||typeof target!=='string'||!target.trim()){missing.push(entry.key);continue;}
        if(!bySource.has(source))bySource.set(source,[]);bySource.get(source).push({key:entry.key,target});
    }
    const duplicateGroups=[],conflicts=[];
    for(const [source,records] of bySource) {
        if(records.length>1)duplicateGroups.push({source,records:records.length});
        // The compiler admits width-only alternatives; different complete
        // target content is still a conflict, and no owner is guessed here.
        if(new Set(records.map(row=>fold(row.target))).size>1)conflicts.push({source,records});
    }
    return {missing,duplicateGroups,conflicts};
}

const freezeBytes=read('generated/r32-coverage-source-freeze.json'),freeze=JSON.parse(freezeBytes);
const versionPaths=[scripts+'native_agent.js',scripts+'runtime_text.js',scripts+'runtime_paragraph.js',scripts+'runtime_identity.js',scripts+'native_transport.js','sora_bilingual/localization/menu_text.py','sora_bilingual/localization/model_wire.py','tests/test_native_agent.js'];
const sourceHashes=Object.fromEntries(versionPaths.map(name=>[name,sha(read(name))]));
for(const [name,digest] of Object.entries(sourceHashes))if(name in freeze.files)assert.equal(digest,freeze.files[name],'frozen production source changed: '+name);
const catalogPath='generated/r25-production/catalog.json',catalogBytes=read(catalogPath),catalogHash=sha(catalogBytes);
const catalog=JSON.parse(catalogBytes.toString('utf8'));
const entries=catalog.entries.filter(entry=>entry.key?.startsWith('table/t_quest.tbl/QuestText/')&&entry.key.endsWith('/body'));
const fcEngine=catalog.entries.find(entry=>entry.key?.startsWith('table/t_quest_fc.tbl/QuestText/')&&entry.texts?.en==='★ Received the internal combustion\nengine!');
assert.equal(entries.length,782);assert.equal(catalogHash,'5dc6a9081b20e028b39f05e67f2167770aaf0e95817daeee801ef3d3e9544e77');
const previousRedHash=sha(read('generated/r32-quest-full-audit-readonly.json'));
const makeRuntime=nativeHarness(),report={schema:1,generated_at_utc:new Date().toISOString(),
    evidence:'actual indexed-v2 production wires; official raw catalog oracle; production callback fixture, no game attachment',
    source_freeze_sha256:sha(freezeBytes),source_snapshot_sha256:freeze.snapshot_sha256,source_head:freeze.source_head,
    source_sha256:sourceHashes,test_sha256:sha(fs.readFileSync(__filename)),catalog_sha256:catalogHash,
    preserved_red_receipt_sha256:previousRedHash,denominator:{raw_body_records:entries.length,configurations:4,complete_records:3128},
    summary:counters(),by_language:[],failure_records:[],width_equivalent_failure_records:[],compiler_rejections:[],
    unknown_control_checks:[],focused_callbacks:[],negative_callbacks:[],game_attached:false,
    limits:['Native callbacks run in the existing pointer/Interceptor fixture, not a running EXE or packaged V8.',
        'Pixel width, rendered overlap, game input, viewport geometry and actual game acceptance are outside this receipt.',
        'Raw source/target marker sequences that differ are separately classified; no group alignment is invented.']};

for(const [sourceLanguage,targetLanguage] of configurations) {
    const receiptName='generated/r32-coverage-'+sourceLanguage+'-production-receipt.json',receiptBytes=read(receiptName),receipt=JSON.parse(receiptBytes);
    assert.equal(receipt.source_snapshot_sha256,freeze.snapshot_sha256);
    assert.equal(receipt.config.primary,sourceLanguage);assert.equal(receipt.config.game_language,sourceLanguage);
    assert.equal(receipt.config.secondary,targetLanguage);assert.equal(receipt.config.experimental_primary,false);
    const wire=fs.readFileSync(receipt.wire_path);assert.equal(sha(wire),receipt.wire_sha256);
    const model=wireModel(wire,receipt.wire_path),scope=model.scoped.quest_notes;
    const resolver=new RuntimeParagraphs(scope,RuntimeText,{preserveQuestLines:true});
    const rawReject=rawRejections(entries,sourceLanguage,targetLanguage),stats=counters();
    const language={source_language:sourceLanguage,secondary_language:targetLanguage,receipt_sha256:sha(receiptBytes),
        model_path:receipt.model_path,model_sha256:receipt.model_sha256,wire_path:receipt.wire_path,wire_sha256:receipt.wire_sha256,
        scoped_pair_count:Object.keys(scope.pairs||{}).length,scoped_ambiguous_display_count:(scope.ambiguous_display||[]).length,
        scoped_display_rejections_count:(scope.display_rejections||[]).length,
        raw_duplicate_source_groups:rawReject.duplicateGroups.length,raw_true_conflict_source_groups:rawReject.conflicts.length,
        raw_missing_target_records:rawReject.missing.length,stats};
    for(const rejection of rawReject.conflicts) {
        assert(!Object.hasOwn(scope.pairs,rejection.source),'actual wire guessed a conflicting QuestText target');
        const lines=split(rejection.source);
        assert(lines.every((line,i)=>resolver.lookup(rejection.source+'\n',i,line,'annotation')===null),'conflict entered paragraph resolver');
        report.compiler_rejections.push({source_language:sourceLanguage,reason:'real_complete_target_conflict',...rejection});
    }
    for(const entry of entries) {
        stats.cases++;const source=entry.texts?.[sourceLanguage],target=entry.texts?.[targetLanguage];
        if(typeof source!=='string'||!source.trim()||typeof target!=='string'||!target.trim()){stats.raw_missing_locale_records++;continue;}
        const lines=split(source),plans={primary:[],secondary:[],annotation:[]},reasons=[];
        for(const mode of Object.keys(plans))lines.forEach((line,i)=>plans[mode].push(resolver.lookup(source+'\n',i,line,mode)));
        const pair=scope.pairs[source],supported=RuntimeParagraphs.supportedMarkup(source)&&RuntimeParagraphs.supportedMarkup(target);
        if(!pair) {
            stats.compiler_rejected_records++;
            if(Object.values(plans).some(list=>list.some(Boolean)))reasons.push('compiler_rejection_has_partial_plan');
        } else if(!supported) {
            stats.unsupported_control_records++;
            if(Object.values(plans).some(list=>list.some(Boolean)))reasons.push('unsupported_control_has_partial_plan');
        } else {
            stats.eligible++;assert.equal(pair[0],source,'wire primary differs from raw source');assert.equal(pair[1],target,'wire secondary differs from official record');
            if(resolver.questLines(source,target)===null){stats.quest_lines_null++;reasons.push('questLines_null');}
            if(Object.values(plans).some(list=>list.some(plan=>plan===null))){stats.lookup_null++;reasons.push('lookup_null');}
            const secondary=plans.secondary.map(plan=>plan?.text??'');
            if(plans.primary.every((plan,i)=>plan?.text===lines[i]))stats.primary_exact_pass++;else reasons.push('primary_not_byte_exact');
            if(norm(secondary.join('\n'))===norm(target))stats.secondary_complete_pass++;else reasons.push('secondary_complete_content_diff');
            let actualAnnotation='';try{actualAnnotation=plans.annotation.map((plan,i)=>plan?annotationPayload(plan,secondary[i]):'').join('\n');}catch(error){reasons.push(error.message);}
            if(norm(actualAnnotation)===norm(target))stats.annotation_strict_pass++;else reasons.push('annotation_complete_content_diff');
            if(norm(fold(actualAnnotation))===norm(fold(target)))stats.annotation_width_equivalent_pass++;
            const groupCheck=semanticCheck(source,target,secondary);reasons.push(...groupCheck.reasons);
            if(groupCheck.comparable&&!groupCheck.reasons.length)stats.semantic_group_pass++;else if(!groupCheck.comparable)stats.semantic_group_not_comparable++;
            if(groupCheck.reasons.some(reason=>reason.startsWith('single_official_member_split'))){stats.member_split_records++;}
            const emptyAnchors=secondary.flatMap((line,i)=>norm(line)&&!norm(lines[i])?[{slot:i,source:lines[i],secondary:line,annotation:plans.annotation[i]}]:[]);
            if(emptyAnchors.length){stats.secondary_on_empty_source_records++;reasons.push('secondary_on_empty_source');}
            if(reasons.length) {
                const widthOnly=reasons.every(reason=>reason==='annotation_complete_content_diff')&&norm(fold(actualAnnotation))===norm(fold(target));
                const failure={key:entry.key,source_language:sourceLanguage,secondary_language:targetLanguage,source,target,
                    classification:widthOnly?'ascii_fullwidth_equivalent_annotation_suppression':'content_or_structure_failure',
                    reasons:[...new Set(reasons)],source_slots:lines.length,target_slots:split(target).length,
                    actual_primary:plans.primary.map(plan=>plan?.text??null),actual_secondary:secondary,actual_annotation:plans.annotation,
                    actual_annotation_payload:actualAnnotation,empty_anchors:emptyAnchors,
                    retained_equivalent_slots:secondary.flatMap((line,i)=>norm(line)&&plans.annotation[i]?.kind==='plain'&&norm(fold(lines[i]))===norm(fold(line))?
                        [{slot:i,source:lines[i],secondary:line,retained:plans.annotation[i].text}]:[])};
                report.failure_records.push(failure);stats.strict_failure_records++;
                if(!widthOnly){report.width_equivalent_failure_records.push(failure);stats.width_equivalent_failure_records++;}
            }
        }
    }
    const sample=entries.find(entry=>entry.key===keyFor(focusIds.engine));
    for(const side of ['source','target']) {
        const source=(side==='source'?'<QUEST_UNKNOWN>':'')+sample.texts[sourceLanguage],target=(side==='target'?'<QUEST_UNKNOWN>':'')+sample.texts[targetLanguage];
        const pairs={[source]:[source,target]},deny=new RuntimeParagraphs({pairs,plain_pairs:pairs},RuntimeText,{preserveQuestLines:true});
        const rejected=split(source).every((line,i)=>deny.lookup(source+'\n',i,line,'annotation')===null);
        report.unknown_control_checks.push({source_language:sourceLanguage,side,rejected});assert(rejected,'unknown Quest control accepted');
    }
    const runtime=makeRuntime(null,true);runtime.api.load(model,'secondary',true,1);
    for(const [kind,id] of Object.entries(focusIds)) {
        const entry=entries.find(row=>row.key===keyFor(id));assert(entry);
        const source=entry.texts[sourceLanguage],target=entry.texts[targetLanguage],lines=split(source),expected=expectedFocus(kind,source,target,sourceLanguage);
        const frame=runtime.questBegin(41);runtime.questParagraph(source+'\n',41);
        const labels=lines.map((line,i)=>{const label=runtime.label(0xf20000+i*0x100,'');runtime.questLine(label,line,41);return label;});runtime.questEnd(frame,41);
        const secondary=labels.map(label=>label.text());
        runtime.api.select('primary',true);labels.forEach(label=>runtime.update(label));const primary=labels.map(label=>label.text());
        runtime.api.select('annotation',true);labels.forEach(label=>runtime.update(label));
        const snapshot=runtime.api.snapshot(),annotation=labels.map(label=>{
            const row=snapshot.find(row=>row.original===lines[labels.indexOf(label)]&&row.displayed===label.text());
            return {text:label.text(),kind:row?.presentation||'plain',layers:row?.layers||[],diagnostic:row?.input_identity_diagnostic};
        });
        const annotationActual=annotation.map((plan,i)=>annotationPayload(plan,secondary[i])).join('\n');
        const check={kind,key:entry.key,source_language:sourceLanguage,secondary_language:targetLanguage,
            primary_exact:same(primary,lines),secondary_complete:norm(secondary.join('\n'))===norm(target),
            secondary_exact_expected:expected===null?null:same(secondary,expected),annotation_complete:norm(annotationActual)===norm(target),
            groups:semanticCheck(source,target,secondary),paragraph_scope:annotation.filter((_,i)=>norm(lines[i])).every(plan=>plan.diagnostic?.paragraph_scope==='quest_notes'),
            expected_secondary:expected,actual_primary:primary,actual_secondary:secondary,actual_annotation:annotation};
        report.focused_callbacks.push(check);
        assert(check.primary_exact&&check.secondary_complete&&check.annotation_complete&&check.secondary_exact_expected!==false&&!check.groups.reasons.length&&check.paragraph_scope,kind+'/'+sourceLanguage+' callback failed');
        labels.forEach(label=>runtime.destroy(label));runtime.api.select('secondary',true);
    }
    const engine=entries.find(row=>row.key===keyFor(focusIds.engine)),engineSource=engine.texts[sourceLanguage];
    const invalidFrame=runtime.questBegin(42);runtime.questParagraph(engineSource+'\n',42);
    const invalidLabel=runtime.label(0xf40000,'');runtime.questLine(invalidLabel,split(engineSource)[0],42,null);
    const invalidRow=runtime.api.snapshot().find(row=>row.original===split(engineSource)[0]&&row.displayed===invalidLabel.text());
    assert(invalidRow,'wrong-caller callback label was not captured');
    const invalidCallerRejected=invalidRow.input_identity_diagnostic?.paragraph_scope!=='quest_notes';
    const invalidCallerDisplayed=invalidLabel.text();runtime.questEnd(invalidFrame,42);runtime.destroy(invalidLabel);
    const expiredFrame=runtime.questBegin(43);runtime.questParagraph(engineSource+'\n',43);runtime.questEnd(expiredFrame,43);
    const expiredLabel=runtime.label(0xf50000,'');runtime.questLine(expiredLabel,split(engineSource)[0],43);
    const expiredRow=runtime.api.snapshot().find(row=>row.original===split(engineSource)[0]&&row.displayed===expiredLabel.text());
    assert(expiredRow,'exited-builder callback label was not captured');
    const exitedFrameRejected=expiredRow.input_identity_diagnostic?.paragraph_scope!=='quest_notes';
    const expiredDisplayed=expiredLabel.text();runtime.destroy(expiredLabel);
    // Reject paragraph provenance, not legitimate ordinary full-string pairs:
    // the Japanese engine is a complete one-line global translation too.
    const negative={source_language:sourceLanguage,invalid_caller_paragraph_identity_rejected:invalidCallerRejected,
        exited_builder_paragraph_identity_rejected:exitedFrameRejected,
        invalid_caller_ordinary_displayed:invalidCallerDisplayed,exited_builder_ordinary_displayed:expiredDisplayed};
    if(sourceLanguage==='en') {
        assert(fcEngine&&fcEngine.texts[targetLanguage]!==engine.texts[targetLanguage]);
        assert(!Object.hasOwn(model.pairs,engineSource),'global cross-table conflict was unquarantined');
        const outside=runtime.label(0xf60000,'');runtime.externalSet(outside,engineSource);
        negative.global_fc_engine_conflict_rejected=outside.text()===engineSource;runtime.destroy(outside);
        assert(negative.global_fc_engine_conflict_rejected,'unowned full engine text bypassed conflict');
    }
    assert(invalidCallerRejected&&exitedFrameRejected);assert.equal(runtime.api.status().failed,false);
    report.negative_callbacks.push(negative);report.by_language.push(language);
    for(const [name,value] of Object.entries(stats))report.summary[name]+=value;
    console.log(JSON.stringify({source_language:sourceLanguage,wire_sha256:receipt.wire_sha256,stats,focused_callbacks:6}));
}
assert.equal(report.summary.cases,3128);assert.equal(report.summary.eligible,3128);
assert.equal(report.summary.primary_exact_pass,3128);assert.equal(report.summary.secondary_complete_pass,3128);
assert.equal(report.summary.annotation_width_equivalent_pass,3128);assert.equal(report.width_equivalent_failure_records.length,0);
assert.equal(report.summary.strict_failure_records,2);
assert(same(report.failure_records.map(row=>row.key).sort(),['f37798c95daaf99ac4201a7ed4fb096e770c152db79c6dfdcd8a477d6bf89a3a','f8650534ce5925995877b595f54410a603b9c25ed6f54331f56ecfffa2391d89'].map(keyFor).sort()),'strict differences changed');
assert.equal(sha(read('generated/r32-quest-full-audit-readonly.json')),previousRedHash,'original red receipt was changed');
for(const [name,digest] of Object.entries(sourceHashes))assert.equal(sha(read(name)),digest,'source changed during audit: '+name);
report.summary.focused_callback_records=report.focused_callbacks.length;
report.summary.unknown_control_checks=report.unknown_control_checks.length;
report.summary.unknown_control_rejections=report.unknown_control_checks.filter(check=>check.rejected).length;
report.passed=true;report.strict_differences_preserved=true;
const output=process.argv[2]||path.join(generated,'r32-quest-complete-wire-audit.json');
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({output,audit_sha256:sha(fs.readFileSync(output)),test_sha256:report.test_sha256,summary:report.summary,passed:true}));
