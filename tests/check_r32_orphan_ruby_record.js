'use strict';
// Bounded replay of actual mp3041_02/QS214_00_00 bytes and compiled record pairs.
// Reads four selected SCPs and existing wire files; builds no production model.
// Run: node --max-old-space-size=4096 tests/check_r32_orphan_ruby_record.js [generated/output.json]
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),scripts='sora_bilingual/game/scripts/';
const oldRoot='dist/comprehensive-1.0.0-dev5-r32-coverage-local1/DEV/'+scripts;
const read=name=>fs.readFileSync(path.join(root,name));
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const json=name=>JSON.parse(read(name).toString('utf8'));
const oldReceipt='generated/r32-resource-coverage-readonly.json',originalReceiptHash=sha(read(oldReceipt));
const norm=value=>String(value??'').replace(/<[^<>]*>/g,'').replace(/\s/gu,'');
const fold=value=>String(value??'').replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0));
const equivalent=(a,b)=>norm(fold(a))===norm(fold(b));
const key='script/scena/mp3041_02.dat/QS214_00_00/called/77/assembled_dialogue';
const source='<#E_0#M_0#B_0><R>My thanks for your previous hospitality, Madame.';
const target='<#E_0#M_0#B_0>老板娘，当时受您关照了。';
const modes=['primary','secondary','annotation'];
function loadModule(name,prefix) {
    const module={exports:{}};
    new Function('module','exports',read(prefix+name).toString('utf8'))(module,module.exports);
    return module.exports;
}
function loadHarness(prefix) {
    let code=read('tests/test_native_agent.js').toString('utf8');
    code=code.slice(0,code.indexOf('\ntest('));
    for(const [variable,name] of [['AGENT','native_agent.js'],['RESOLVER','runtime_text.js'],
            ['PARAGRAPHS','runtime_paragraph.js'],['IDENTITIES','runtime_identity.js']])
        code=code.replace(new RegExp('const '+variable+' = [^\\n]+'),()=>
            'const '+variable+' = '+JSON.stringify(read(prefix+name).toString('utf8'))+';');
    const module={exports:{}};
    new Function('require','__dirname','module',code+'\nmodule.exports={makeRuntime};')(require,__dirname,module);
    return module.exports.makeRuntime;
}
function loadWire(locale) {
    const receipt=json('generated/r32-coverage-'+locale+'-production-receipt.json');
    const wire=fs.readFileSync(receipt.wire_path);assert.equal(sha(wire),receipt.wire_sha256);
    let model;
    const context={rpc:{exports:{load:value=>{model=value;return true;}}},
        File:{readAllBytes:()=>wire.buffer.slice(wire.byteOffset,wire.byteOffset+wire.byteLength)}};
    vm.runInNewContext(read(scripts+'native_transport.js').toString('utf8'),context);
    context.rpc.exports.modelpackedfile(receipt.wire_path,'secondary',true,1,{});
    return {model,receipt};
}
function compactIdentity(identity) {
    if(!identity)return null;const {signature,...rest}=identity;return rest;
}
function compactRow(row) {
    return {original:row?.original,displayed:row?.displayed,presentation:row?.presentation,
        script_identity:compactIdentity(row?.script_identity),log_identity:compactIdentity(row?.log_identity),
        log_kind:row?.log_kind,layers:row?.layers||[]};
}
function modeResult(mode,text,layers=[]) {
    if(mode==='primary')return text===source;
    if(mode==='secondary')return text===target;
    return equivalent(text,source)&&equivalent(layers.map(layer=>layer.text).join('\n'),target);
}
const python=process.env.SORA_AUDIT_PYTHON||'python';
const extraction=String.raw`
import pathlib,json,sys,hashlib,base64,struct
sys.stdout.reconfigure(encoding='utf-8');sys.path.insert(0,str(pathlib.Path.cwd()))
from sora_bilingual.localization.resources import FpacArchive,parse_scp,assembled_dialogue,_aligned_call_map
from sora_bilingual.localization.runtime_identity import script_signature
from sora_bilingual.config.locales import archive_names
base=pathlib.Path(r'D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter\pac\steam')
data={};fn='QS214_00_00';file='scena/mp3041_02.dat'
for lang in ['en','ja','zh-Hans','zh-Hant']:
 with FpacArchive(base/archive_names('script')[lang]) as archive:
  member=next(n for n in archive.entries if n.endswith('/'+file));raw=archive.read(member)
  data[lang]=(raw,parse_scp(raw),member)
output=[]
for src,tar in [('en','zh-Hans'),('ja','zh-Hans'),('zh-Hans','ja'),('zh-Hant','ja')]:
 raw,parsed,member=data[src];a=parsed.functions[fn];b=data[tar][1].functions[fn];mapped=_aligned_call_map(a,b)
 start,count=struct.unpack_from('<II',raw,4)
 at=next(start+i*32 for i in range(count) if raw[struct.unpack_from('<I',raw,start+i*32+28)[0]&0x3fffffff:][:len(fn)+1]==fn.encode()+b'\0')
 callsat=struct.unpack_from('<I',raw,at+20)[0];records=[]
 for i,call in enumerate(a.called):
  source=assembled_dialogue(call)
  if source is None:continue
  n=mapped.get(i);expected=assembled_dialogue(b.called[n]) if n is not None else None
  ca=callsat+i*12;argc,argat=struct.unpack_from('<HI',raw,ca+6)
  values=[struct.unpack_from('<I',raw,argat+j*8)[0] for j in range(2,argc)]
  records.append({'key':'script/'+file+'/'+fn+'/called/'+str(i)+'/assembled_dialogue','function':fn,'called':i,'source':source,'target':expected,'mapping_proved':n is not None,'values':values})
 output.append({'source_language':src,'target_language':tar,'resource':member,'signature':script_signature(raw),'sha256':hashlib.sha256(raw).hexdigest(),'blob':base64.b64encode(raw).decode(),'records':records})
sys.stdout.write(json.dumps(output,ensure_ascii=False))
`;
const extracted=spawnSync(python,['-B','-c',extraction],{cwd:root,encoding:'utf8',maxBuffer:32*1024*1024});
assert.equal(extracted.status,0,extracted.stderr);const fixtures=JSON.parse(extracted.stdout);
const revisions=[{name:'sealed_local1_before',prefix:oldRoot},{name:'workspace_after',prefix:scripts}];
for(const revision of revisions) {
    revision.RuntimeText=loadModule('runtime_text.js',revision.prefix).RuntimeText;
    revision.ScriptIdentities=loadModule('runtime_identity.js',revision.prefix).ScriptIdentities;
    revision.makeRuntime=loadHarness(revision.prefix);
}
const output={schema:1,evidence:'actual selected SCP bytes + existing wire + production callback pointer fixture; no game/UI/real renderer or new build',
    checker:path.join(__dirname,'check_r32_orphan_ruby_record.js'),checker_sha256:sha(fs.readFileSync(__filename)),
    original_failure_receipt:{path:path.join(root,oldReceipt),sha256:originalReceiptHash,unchanged:null},
    resource_count:fixtures.length,record_key:key,source,target,source_sha256:sha(source),target_sha256:sha(target),
    revisions:revisions.map(revision=>({name:revision.name,files:Object.fromEntries(
        ['runtime_text.js','native_agent.js','runtime_identity.js','runtime_paragraph.js'].map(name=>[name,{path:path.join(root,revision.prefix,name),sha256:sha(read(revision.prefix+name))}]))})),
    languages:[],native_callbacks:[],negative_boundaries:[],limitations:[
        'native callback and hidden measurement use the existing pointer harness; glyph geometry and live VM execution are not exercised',
        'permission relies on identity returned by ScriptIdentities.lookup; RuntimeText constructor does not independently authenticate a caller-supplied object',
        'mp6600 group5/command6 variable actor still lacks an observed VM invocation; no new omission is claimed']};
function callbackReplay(revision,model,blob,row,site) {
    const records=[];
    for(const mode of modes) {
        const runtime=revision.makeRuntime(null,true);runtime.api.load(model,mode,true,1);
        const live=runtime.label(0xe10000,''),log=runtime.label(0xe20000,'');
        const buffer=runtime.dialogueSet(live,row.source,blob,row.function,row.values,7,site);
        const liveRow=compactRow(runtime.api.snapshot().find(item=>item.original===row.source&&!item.log_kind));
        records.push({revision:revision.name,mode,path:'live',builder_unchanged:buffer.text===row.source,
            official_complete:modeResult(mode,live.text(),liveRow.layers),...liveRow});runtime.destroy(live);
        runtime.logShow(log,7,row.source);
        const logRow=compactRow(runtime.api.snapshot().find(item=>item.original===row.source&&item.log_kind==='body'));
        records.push({revision:revision.name,mode,path:'history',official_complete:modeResult(mode,log.text(),logRow.layers),...logRow});runtime.destroy(log);
        for(const width of [8,900]) {
            runtime.fontReload();const measured=runtime.logMeasure([['',row.source,7]],{width});
            const measureRow=compactRow(runtime.api.snapshot().find(item=>item.original===row.source));
            records.push({revision:revision.name,mode,path:'hidden_measure',width,body:measured.bodies[0],
                official_complete:modeResult(mode,measured.bodies[0],measureRow.layers),snapshot:measureRow,
                fixture_heights:measured.heights,fixture_widths:measured.widths,setters:measured.setters,cleanup:measured.cleanup});
        }
        assert.equal(runtime.api.status().failed,false);runtime.api.disable();
    }
    return records;
}
let decisive=null;
for(const fixture of fixtures) {
    const {model,receipt}=loadWire(fixture.source_language),blob=Buffer.from(fixture.blob,'base64');
    assert.equal(sha(blob),fixture.sha256);assert.equal(fixture.records.length,196);
    const manifest=(model.script_identities.manifest[fixture.signature]||[]).find(row=>row.sha256===fixture.sha256);assert(manifest);
    const language={source_language:fixture.source_language,target_language:fixture.target_language,resource:fixture.resource,
        source_file_sha256:fixture.sha256,wire_sha256:receipt.wire_sha256,records:fixture.records.length,revisions:[]};
    for(const revision of revisions) {
        const identities=new revision.ScriptIdentities(model.script_identities);
        const stats={identities:0,primary_exact:0,secondary_official_equivalent:0},failures=[];
        for(const row of fixture.records) {
            assert(row.mapping_proved&&typeof row.target==='string');
            const sites=Object.entries(manifest.callSites?.[row.function]||{}).filter(([,value])=>value.record===row.called);
            assert.equal(sites.length,1);const site={pc:Number(sites[0][0]),group:sites[0][1].group,command:sites[0][1].command};
            const identity=identities.capture(fixture.signature,size=>blob.subarray(0,size),row.function,row.values.join(','),site,row.source);
            assert.equal(identity?.recordKey,row.key);stats.identities++;
            const context=identities.lookup(identity,row.source);assert(context);
            const translator=new revision.RuntimeText(context.model,context.identity||null);
            const primary=translator.translate(row.source,'primary'),secondary=translator.translate(row.source,'secondary');
            if(primary===row.source)stats.primary_exact++;
            if(equivalent(secondary,row.target))stats.secondary_official_equivalent++;
            else failures.push({key:row.key,source:row.source,target:row.target,actual:secondary,identity:compactIdentity(identity)});
            if(fixture.source_language==='en'&&row.called===77) {
                assert.equal(row.source,source);assert.equal(row.target,target);assert.equal(site.pc,193242);
                assert.equal(fixture.sha256,'585f93b841cadb8c0120c3411cf4b88c8a2903605f3ddbeb5af8b973c7a60366');
                language[revision.name+'_plans']=Object.fromEntries(modes.map(mode=>[mode,translator.render(source,mode)]));
                output.native_callbacks.push(...callbackReplay(revision,model,blob,row,site));
                if(revision.name==='workspace_after')decisive={RuntimeText:revision.RuntimeText,context,identity,model};
            }
        }
        language.revisions.push({revision:revision.name,stats,failures});
    }
    output.languages.push(language);
    process.stderr.write(JSON.stringify({source:fixture.source_language,stats:language.revisions.map(row=>({revision:row.revision,...row.stats,failures:row.failures.length}))})+'\n');
}
assert(decisive);
const {RuntimeText,context,identity,model}=decisive;
const negativeResolvers=[['global_without_identity',new RuntimeText(model),source],
    ['local_without_identity',new RuntimeText(context.model),source],
    ['changed_full_source',new RuntimeText(context.model,identity),source+' changed'],
    ['emotion_prefix_changed',new RuntimeText(context.model,identity),source.replace('<#E_0#M_0#B_0>','<#E_1>')],
    ['expression_stripped_alias',new RuntimeText(context.model,identity),source.replace(/^<#[^<>]*>/,'')]];
for(const [name,translator,text] of negativeResolvers)for(const mode of modes) {
    const plan=translator.render(text,mode),translated=translator.translate(text,mode);
    const refused=plan.text===text&&!plan.layers.length&&translated===text;
    output.negative_boundaries.push({name,mode,synthetic:false,refused,plan});assert(refused,name+':'+mode);
}
for(const [name,text,b] of [['unknown_Q',source+'<Q>unexpected',target],['nested_R',source+'<R>nested',target],
        ['leading_unknown_control','<Q>'+source,target],['invalid_target',source,'<R>malformed target']]) {
    const pairs={[text]:[text,b]},translator=new RuntimeText({pairs,plain_pairs:pairs},{...identity,source:text});
    for(const mode of modes) {
        const plan=translator.render(text,mode),refused=plan.text===text&&!plan.layers.length&&translator.translate(text,mode)===text;
        output.negative_boundaries.push({name,mode,synthetic:true,refused,plan});assert(refused,name+':'+mode);
    }
}
for(const language of output.languages)for(const row of language.revisions) {
    assert.equal(row.stats.identities,196);assert.equal(row.stats.primary_exact,196);
    assert.equal(row.failures.length,row.revision==='sealed_local1_before'&&language.source_language==='en'?1:0);
}
assert(output.native_callbacks.filter(row=>row.revision==='workspace_after').every(row=>row.official_complete));
assert(output.native_callbacks.filter(row=>row.revision==='sealed_local1_before'&&row.mode!=='primary').every(row=>!row.official_complete));
assert.equal(sha(read(oldReceipt)),originalReceiptHash);output.original_failure_receipt.unchanged=true;
output.summary={owned_records:784,before_secondary_failures:1,after_secondary_failures:0,
    after_primary_exact:784,native_callback_paths:output.native_callbacks.length,
    after_native_callback_paths:output.native_callbacks.filter(row=>row.revision==='workspace_after').length,
    after_native_callback_failures:output.native_callbacks.filter(row=>row.revision==='workspace_after'&&!row.official_complete).length,
    negative_boundary_checks:output.negative_boundaries.length,negative_refusals:output.negative_boundaries.filter(row=>row.refused).length};
const outputPath=path.resolve(root,process.argv[2]||'generated/r32-orphan-ruby-owned-record-after.json');
fs.writeFileSync(outputPath,JSON.stringify(output,null,2)+'\n','utf8');
console.log(JSON.stringify({path:outputPath,sha256:sha(fs.readFileSync(outputPath)),summary:output.summary}));
