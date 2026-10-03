'use strict';
// UI mutations run on UI callbacks. Font RPC stages independent resources;
// publication and reflow happen at Update, never during background loading.
const base = Process.getModuleByName('sora_2nd.exe').base;
// Validate every site before constructing any adapter: factories may install
// hooks immediately, and a NativeFunction call flushes their pending patches.
for (const [name, point] of Object.entries(REPORT.native)) {
    const actual = Array.from(new Uint8Array(base.add(point.rva).readByteArray(16)))
        .map(x => x.toString(16).padStart(2, '0')).join('');
    if (actual !== point.bytes) throw Error('Native runtime code differs from executable at '+name+'; connection refused before installing hooks');
}
const labels = new Map();
const threads = new Set();
let dictionary = Object.create(null), enabled = false, epoch = 0;
let updates = 0, writes = 0, destroyed = 0, failed = false;
let failureReason=null;
const timings=Object.fromEntries(['identity','pointerIdentity','setter','resolve','measure','parse','geometry','geometryNative'].map(key=>[key,{count:0,totalMs:0,maxMs:0,over8Ms:0}]));
function recordTiming(stage,start) {
    if(start===undefined)return;
    const ms=Date.now()-start,row=timings[stage];row.count++;row.totalMs+=ms;row.maxMs=Math.max(row.maxMs,ms);
    if(ms>=8)row.over8Ms++;
}
let replayEpoch = -1;
let annotationScale = 1;
const nativeSizeFallbacks=new Map();
const rewriteStacks=new Map(), labelCallbacks=new Map();
let rubyScale = 0.8, rubyGap = 3, rubyLineGap = 12, rubyOffsetX = 0;
let secondaryColor = [230/255,230/255,230/255];
let secondaryOpacity=.9,bilingualOffsetY=0;
let resolver=null, renderMode='annotation';
let activeModel=null;
let TextFactory=RuntimeText, ScriptFactory=typeof ScriptIdentities==='undefined'?null:ScriptIdentities;
let TableFactory=typeof TableIdentities==='undefined'?null:TableIdentities;
let ParagraphFactory=typeof RuntimeParagraphs==='undefined'?null:RuntimeParagraphs,paragraphs=null;
let BooksFactory=typeof RuntimeBooks==='undefined'?null:RuntimeBooks,books=null;
const nativeBooks=typeof createNativeBooks==='function'?createNativeBooks(base,REPORT,()=>({
    active:enabled&&!failed&&(!runtimeFonts||runtimeFonts.isReady()),books,mode:renderMode,
    style:{rubyScale,rubyGap,lineGap:rubyLineGap,offsetY:bilingualOffsetY}
})):null;
let immediateWrites=0;
let scriptIdentities=null,tableIdentities=null,identityHits=0,identityMisses=0,tableIdentityHits=0;
const dialogueFrames=new Map();
const logOrigins=typeof LogIdentities==='function'?new LogIdentities():null;
const logWriteFrames=new Map(),logPresentFrames=new Map();
const logBuildFrames=new Map(),logRows=new Map(),logControllers=new Map();
const logTextGroups=new Map();
const logOriginStats={commits:0,withIdentity:0,matched:0,rejected:0,resets:0};
const questFrames=new Map();
const logMeasureFrames=new Map(),logHeightCache=new Map(),logNameCache=new Map();
let logCacheBytes=0,logFontGeneration=0;
const logMeasureStats={runs:0,totalMs:0,hits:0,misses:0,nameHits:0,fixedRows:0,fallbacks:0,lastFallback:null};
const resourceHash=typeof createNativeSha256==='function'?createNativeSha256():scriptSha256;
const auxiliaryContexts=new Map(), compensation=new Map(), rubyPermissions=new Map();
const annotationMetrics=new Map();
const subtitleRoots=new Set(),insetRoots=new Map(),layoutRoots=new Map();let scannedLayouts=false;
let fontGeneration=0,fontsWereReady=!REPORT.runtime_fonts;
function invalidateFontGeometry(){
    fontGeneration++;epoch++;logFontGeneration++;
    logHeightCache.clear();logNameCache.clear();logCacheBytes=0;
}
const runtimeFonts=REPORT.runtime_fonts?createNativeFonts(base,REPORT,resourceHash,invalidateFontGeometry):null;
const setter = new NativeFunction(base.add(REPORT.native.set_text.rva), 'void', ['pointer','pointer']);
const resetText = new NativeFunction(base.add(REPORT.native.reset_text.rva), 'void', ['pointer']);
const cloneIconCallback = REPORT.native.icon_callback_clone
    ? new NativeFunction(base.add(REPORT.native.icon_callback_clone.rva), 'pointer', ['pointer','pointer']) : null;
// Loaded once with the resident agent, never patched into a running session.
// Keep this module alive for the full lifetime of its synchronous function.
const geometryModule=typeof NATIVE_GEOMETRY_SOURCE==='string'?new CModule(NATIVE_GEOMETRY_SOURCE):null;
const adjustStaticRuby=geometryModule?new NativeFunction(geometryModule.adjust_static_ruby,
    'int',['pointer','uint','pointer','uint','pointer'],{scheduling:'exclusive'}):null;
const geometryStyle=adjustStaticRuby?Memory.alloc(7*4):null;
const nativeParser=typeof createNativeParser==='function'&&REPORT.native.parse_text
    ?createNativeParser(auxiliaryContexts,fail):null;
let nativeMeasure=null;
const nativeLabelTiming=REPORT.performance_diagnostics&&typeof createNativeLabelTiming==='function'?createNativeLabelTiming({
    setter:base.add(REPORT.native.set_text.rva),update:base.add(REPORT.native.update.rva)
}):null;
const labelHooks=nativeLabelTiming||Interceptor;
const textKeys = new Map();
if (REPORT.text_table_global) {
    const manager=base.add(REPORT.text_table_global).readPointer();
    const table=manager.add(0x6b8).readPointer();
    const data=table.add(0x10).readPointer(), descriptor=table.add(0x20).readPointer();
    const index=table.add(0x28).readPointer(), count=table.add(0x30).readU32();
    const start=descriptor.add(0x44).readU32(), stride=descriptor.add(0x48).readU32();
    if(count>20000 || stride!==16) throw Error('Unvalidated runtime text table');
    for(let i=0;i<count;i++) {
        const entry=index.add(i*8), hash=entry.readU32(), number=entry.add(4).readU32();
        if(number===0xffffffff)continue;
        if(number>=count)throw Error('Invalid runtime text index');
        const record=data.add(start+number*stride);
        const key=record.readPointer().readUtf8String(), source=record.add(8).readPointer().readUtf8String();
        if(!key.startsWith('TXT_') || key.length>256 || source.length>16384 || textKeys.has(hash))
            throw Error('Unvalidated runtime text key');
        textKeys.set(hash,{key,source});
    }
}
function registerLayout(layout) {
    if(layout.isNull())return;
    const root=layout.add(0xa8).readPointer();
    if(root.isNull())return;
    const id=layout.add(0x80).readU32(),key=String(root);
    const previous=layoutRoots.get(String(layout));
    if(previous){subtitleRoots.delete(previous);insetRoots.delete(previous);}
    layoutRoots.set(String(layout),key);
    if(id===7)subtitleRoots.add(key);else subtitleRoots.delete(key);
    // 0x26402..0x26414 creates ActiveVoice layout 32; 0x25b29 selects text.
    // Layout 6 root/text is the small dialogue body (read-only capture 153).
    const insetSurface=id===32?'active_voice':id===6?'small_dialogue':null;
    if(insetSurface)insetRoots.set(key,insetSurface);else insetRoots.delete(key);
}
function scanLayouts() {
    if(scannedLayouts||!REPORT.layout_manager_global)return;
    const manager=base.add(REPORT.layout_manager_global).readPointer();
    const count=manager.add(0x58).readU32();
    if(count>8192||manager.add(0x5c).readU32()!==0)throw Error('Unvalidated layout instance count');
    const data=manager.add(0x50).readPointer();
    for(let i=0;i<count;i++)registerLayout(data.add(i*8).readPointer());
    scannedLayouts=true;
}
function translationKey(row) {
    scanLayouts();
    const entry=textKeys.size ? textKeys.get(row.pointer.add(0x2ec).readU32()) : null;
    // A dynamic widget may retain its layout's initial text key. Use that key
    // only when its source still agrees with the game's current text table.
    row.textKey=entry && entry.source===row.original ? entry.key : null;
    const keyed=row.textKey ? '\x01'+row.textKey+'\x00'+row.original : '';
    if(keyed && Object.hasOwn(dictionary,keyed))return keyed;
    row.scope=null;
    row.surface='standard';row.surfaceRoot=null;
    row.dialogueSpeaker=false;
    if(REPORT.node_names) {
        let p=row.pointer;
        const names=[];
        let subtitle=false,insetRoot=null;
        for(let i=0;i<12&&!p.isNull();i++) {
            if(subtitleRoots.has(String(p)))subtitle=true;
            if(insetRoots.has(String(p)))insetRoot=String(p);
            const np=p.add(0x88).readPointer();
            const name=np.isNull()?'':np.readUtf8String();
            if(name.length>256)throw Error('Unvalidated node name');
            names.push(name);p=p.add(0x80).readPointer();
        }
        if(subtitle&&names[0]==='text')row.surface='subtitle';
        const insetSurface=insetRoots.get(insetRoot);
        if(names[0]==='text'&&((insetSurface==='active_voice'&&names[1]==='item'&&names[2]==='items')||
                (insetSurface==='small_dialogue'&&names[1]==='root'))) {
            row.surface=insetSurface;row.surfaceRoot=insetRoot;
        }
        row.dialogueSpeaker=subtitle&&['name_text','prev_name_text'].includes(names[0]);
        if(names[0]==='name'&&names.includes('item_template'))row.scope='item_name';
        // Both engine spot-name builders copy and join the original table
        // string before SetText, so its native table pointer is no longer here.
        if(names[0]==='spot_name')row.scope='map_spot';
        if(names[0]==='name' && names.includes('skill_template')) {
            if(names.includes('ability_list')||names.includes('temp_ability_list'))row.scope='support';
            if(names.includes('overdrive_list')||names.includes('temp_overdrive_list'))row.scope='overdrive';
        }
    }
    const scoped=row.scope ? '\x02'+row.scope+'\x00'+row.original : '';
    return scoped && Object.hasOwn(dictionary,scoped) ? scoped : row.original;
}
function isLabel(p) { return p.readPointer().equals(base.add(REPORT.vtable)); }
function readText(p) {
    const value = p.add(0x318).readPointer();
    if (value.isNull()) return '';
    const text = value.readUtf8String();
    if (text.length > 32768) throw Error('Label text exceeds render limit');
    return text;
}
function remember(p, text) {
    const key = String(p);
    if (!labels.has(key) && labels.size >= 10000) throw Error('Label tracking limit');
    const row = {pointer:p, original:text, displayed:text, epoch:-1,
        fontGeneration:labels.get(key)?.fontGeneration};
    labels.set(key,row);
    return row;
}
function enterLabel(p) {
    const thread=Process.getCurrentThreadId();threads.add(thread);
    const key=String(p),previous=labelCallbacks.get(key);
    if(previous && previous.thread!==thread) {
        fail('Concurrent callbacks for the same label: '+key);return null;
    }
    const lease=previous||{key,thread,depth:0};lease.depth++;labelCallbacks.set(key,lease);return lease;
}
function leaveLabel(lease) {
    if(lease && --lease.depth===0 && labelCallbacks.get(lease.key)===lease)labelCallbacks.delete(lease.key);
}
function activeRewrite(p) {
    const stack=rewriteStacks.get(Process.getCurrentThreadId())||[];
    for(let i=stack.length-1;i>=0;i--)if(stack[i].pointer.equals(p))return stack[i];
    return null;
}
const sourceOnlyDialogue={model:{pairs:{},plain_pairs:{}}};
function wantedText(row,allocateLayers=true) {
    const started=Date.now();
    const p=row.pointer,key=translationKey(row);
    row.renderSize=p.add(0x304).readU32();
    let wanted=row.original;
    row.glyphLanes=[];row.laneCount=-1;row.laneUnits=-1;row.lanesDirty=false;
    row.offsetPositions=null;
    row.nativeRanges=null;
    row.animated=!!(p.add(0x2e8).readU32()&4);
    row.plan={text:wanted,layers:[],kind:'plain'};
    if(enabled&&!failed&&(!runtimeFonts||runtimeFonts.isReady())) {
        if(resolver) {
            const mode=renderMode==='bilingual'?'annotation':renderMode;
            const strictDialogue=Number.isInteger(row.scriptIdentity?.callId);
            const scriptContext=row.scriptIdentity&&scriptIdentities?scriptIdentities.lookup(row.scriptIdentity,row.original):null;
            const speakerContext=row.logKind==='name'&&row.logIdentity&&scriptIdentities?
                scriptIdentities.historySpeakerLookup(row.logIdentity,row.original):null;
            const context=nativeBooks?.context(row.book,row.original)||speakerContext||(strictDialogue?(scriptContext||sourceOnlyDialogue):scriptContext||
                (row.scriptPointer&&scriptIdentities?scriptIdentities.pointerLookup(row.scriptPointer,row.original):null)||
                (row.tableIdentity&&tableIdentities?tableIdentities.lookup(row.tableIdentity,row.original):null)||
                (row.logKind?resolver.historyContext(row.logSpeaker||'',row.original,row.logKind):null)||
                (row.logSpeaker?resolver.speakerContext(row.logSpeaker,row.original):null));
            if(context&&!context.tr)context.tr=new TextFactory(context.model);
            const local=context?.tr;
            const useLocal=local&&(strictDialogue||context.strict||Object.hasOwn(local.model.pairs,row.original)||
                local.translate(row.original,'secondary')!==row.original||local.translate(row.original,'primary')!==row.original);
            const translator=useLocal?local:resolver;
            const paragraph=row.paragraph&&paragraphs?paragraphs.lookup(row.paragraph.source,row.paragraph.index,row.original,mode):null;
            row.plan=paragraph||translator.render(row.original,mode,row.textKey||'',row.scope||'');
            // Inline native ruby is only emitted when its closing tag is
            // parsed. Animated lines need the same independent prefix lane
            // as formatted dialogue so it can reveal alongside the main run.
            if(row.plan.kind==='ruby'&&(p.add(0x2e8).readU32()&4)) {
                const a=paragraph?paragraphs.lookup(row.paragraph.source,row.paragraph.index,row.original,'primary').text:
                    translator.translate(row.original,'primary',row.textKey||'',row.scope||'');
                const b=paragraph?paragraphs.lookup(row.paragraph.source,row.paragraph.index,row.original,'secondary').text:
                    translator.translate(row.original,'secondary',row.textKey||'',row.scope||'');
                row.plan=TextFactory.annotationPlan(a,b);
            }
            wanted=row.plan.text;
        } else {
            wanted=Object.hasOwn(dictionary,key) ? dictionary[key] : row.original;
            // Legacy experiments cannot distinguish original ruby. Never
            // apply their geometry adjustment to a source containing ruby.
            row.plan={text:wanted,layers:[],kind:wanted!==row.original&&wanted.includes('<R>')&&!row.original.includes('<R>')?'ruby':'plain'};
        }
    }
    if(wanted.length+(row.plan.layers||[]).reduce((n,v)=>n+v.text.length,0)>32768)
        throw Error('Rendered text and annotation payload exceed limit');
    row.matched=wanted!==row.original;
    let prefixLength=0;
    const shrink=row.plan.kind==='ruby'||row.plan.kind==='layered';
    // Original readings/size commands must keep their parser advances, but
    // still receive the same owned-glyph scale as other bilingual text.
    // Readings confined to the secondary never exempt the main paragraph.
    const primaryReadings=row.plan.kind==='layered'&&row.plan.layers.some(layer=>(layer.primary||'').includes('<R>'));
    const primaryMetrics=primaryReadings||(row.plan.kind==='layered'&&/<[sS]\d+>/.test(row.original));
    const hasText=text=>/[A-Za-z0-9\u00c0-\uffff]/.test(text.replace(/<[^<>]*>/g,''));
    const uncovered=row.plan.kind==='ruby'?hasText(wanted.replace(/<R>[^<>]*<\/R[^<>]*>/g,'')):
        row.plan.kind==='layered'&&wanted.split(/\r\n|\n|\\n/).some(line=>!line.includes('<R></R_>')&&hasText(line));
    // A native label may use a small/late-bound base size or explicit <s>
    // commands. That is not a connection failure. Outside the validated
    // size-command range, keep its native parser metrics and scale only the
    // owned glyphs afterwards, as we already do for mixed text/icon rows.
    const nativeSizeFallback=shrink&&annotationScale<1&&(row.renderSize<12||row.renderSize>256);
    if(nativeSizeFallback&&!nativeSizeFallbacks.has(row.renderSize)&&nativeSizeFallbacks.size<16) {
        nativeSizeFallbacks.set(row.renderSize,true);
        if(REPORT.diagnostics)send({type:'native_size_fallback',fontSize:row.renderSize,sourceLength:row.original.length});
    }
    row.reserveRubyHeight=row.plan.kind==='ruby'&&!uncovered&&!nativeSizeFallback;
    row.reserveAuxiliaryHeight=row.plan.kind==='layered'&&/\r\n|\n|\\n/.test(wanted);
    row.preservePrimaryLayout=shrink&&Boolean(uncovered||nativeSizeFallback||primaryMetrics);
    row.extendLineSpacing=shrink&&!uncovered&&!nativeSizeFallback&&(!primaryMetrics||primaryReadings);
    // Mixed labels keep native parser advances. Their owned glyphs are scaled
    // after layout, so untranslated levels, times and icons do not move.
    if(shrink&&!row.preservePrimaryLayout&&annotationScale<1) {
        const size=row.renderSize;
        if(row.plan.kind==='ruby') {
            // Size only owned ruby runs. Same-label dates/difficulty badges
            // and other untranslated runs retain their current native size.
            let current=size;
            wanted=wanted.replace(/<s\d+>|<R>[^<>]*<\/R[^<>]*>/g,token=>{
                if(token.startsWith('<s')){current=Number(token.slice(2,-1));return token;}
                return '<s'+Math.max(12,Math.round(current*annotationScale))+'>'+token+'<s'+current+'>';
            });
        } else {
            const prefix='<s'+Math.max(12,Math.round(size*annotationScale))+'>';
            prefixLength=prefix.length;wanted=prefix+wanted;
        }
    }
    row.layerBuffers=allocateLayers?(row.plan.layers||[]).map(layer=>({layer:{...layer,offset:layer.offset+prefixLength},buffer:Memory.allocUtf8String(layer.text),primaryBuffer:Memory.allocUtf8String(layer.primary||row.original)})):[];
    if(wanted.length>32768)throw Error('Rendered text exceeds limit');
    recordTiming('resolve',started);
    return wanted;
}
function captureMetadata(row) {
    // Read native fields only while this object's own callback is active.
    const p=row.pointer;
    row.metadata={size:p.add(0x304).readU32(),flags:p.add(0x2e8).readU32()};
}
function textLayoutChanged(row,p) {
    return row.renderSize!==p.add(0x304).readU32()||
        (row.metadata?.flags&0x0c)!==(p.add(0x2e8).readU32()&0x0c);
}
function prepareTextReset(p) {
    // Update already owns its nested setter/reset and preserves reveal state.
    // This boundary handles native constructors finalizing flags before the
    // first Update: 0x536c50 -> 0x533e4d -> 0x533f42 (popup height).
    if(labelCallbacks.has(String(p))||activeRewrite(p)||!isLabel(p))return 0;
    const row=labels.get(String(p));
    if(!row||(row.epoch===epoch&&!textLayoutChanged(row,p))||readText(p)!==row.displayed)return 0;
    const lease=enterLabel(p);if(!lease)return 0;
    try {
        const previouslyOwned=row.plan?.kind==='ruby'||row.plan?.kind==='layered';
        const renderEpoch=epoch,wanted=wantedText(row);
        const owned=row.plan.kind==='ruby'||row.plan.kind==='layered';
        const changed=wanted!==row.displayed;
        if(changed)copyOwnedText(row,wanted);
        row.epoch=renderEpoch;captureMetadata(row);
        // The replacement's NativeCallback runs outside a listener, so the
        // setter already measured changed bytes through the real hooks.
        // Equal bytes with changed geometry need one explicit C measurement.
        return previouslyOwned||owned?(changed?2:1):0;
    }catch(e){fail(e);return 0;}finally{leaveLabel(lease);}
}
const nativeTextReset=typeof createNativeTextReset==='function'?createNativeTextReset(
    base.add(REPORT.native.reset_text.rva),base.add(REPORT.native.measure_text.rva),prepareTextReset):null;
function fail(error) {
    if (!failed) {failureReason=String(error);send({type:'error', message:failureReason});}
    failed = true; enabled = false; epoch++;
}
function ownedRow(p) {
    const row=labels.get(String(p));
    if(!row)return null;
    const rewrite=activeRewrite(p),text=rewrite ? rewrite.text : row.displayed;
    return text!==row.original && readText(p)===text ? row : null;
}
function auxiliaryLayer(p,parser,row=ownedRow(p)) {
    if(!row || row.plan.kind!=='layered')return null;
    const current=parser.add(8).readPointer(),owned=p.add(0x318).readPointer();
    const item=row.layerBuffers.find(v=>owned.add(v.layer.offset).equals(current));
    return item ? {...item,row,parser} : null;
}
function finishStaticRuby(row,array,count) {
    if(!adjustStaticRuby||row.animated||row.preservePrimaryLayout||row.plan.kind!=='ruby')return false;
    const lanes=row.glyphLanes;
    // Partial/layered runs still use the incremental JS path. A descriptor
    // contains only indices: never retain native glyph pointers across parses.
    if(lanes.some(v=>v.layer||!Number.isInteger(v.primaryStart)||!Number.isInteger(v.start)||!Number.isInteger(v.end)))return false;
    const bytes=lanes.length*12;
    if(!row.nativeRanges||row.nativeRanges.capacity<bytes)
        row.nativeRanges={capacity:bytes,pointer:Memory.alloc(bytes)};
    const ranges=new Uint32Array(lanes.length*3);
    lanes.forEach((v,i)=>ranges.set([v.primaryStart,v.start,v.end],i*3));
    row.nativeRanges.pointer.writeByteArray(ranges.buffer);
    geometryStyle.writeByteArray(new Float32Array([rubyGap,rubyOffsetX,...secondaryColor,secondaryOpacity,bilingualOffsetY]).buffer);
    const started=Date.now();
    const result=adjustStaticRuby(array,count,row.nativeRanges.pointer,lanes.length,geometryStyle);
    if(result!==0)throw Error('Invalid native annotation geometry ('+result+')');
    recordTiming('geometryNative',started);
    return true;
}
function finishAnnotationLanes(row) {
    const lanes=row?.glyphLanes;
    if(!lanes?.length)return;
    const p=row.pointer,count=p.add(0x330).readU32();
    const revealUnits=row.animated?p.add(0x41c).readU32():0;
    if(row.laneCount===count&&row.laneUnits===revealUnits&&!row.lanesDirty)return;
    const started=Date.now();
    row.laneCount=count;row.laneUnits=revealUnits;row.lanesDirty=false;
    if(count>32768)throw Error('Invalid native glyph count');
    const array=p.add(0x680).readPointer().add(0x20).readPointer();
    // Static runs arrive here only after fresh native parsing. Keep flag-0x40
    // rebuilding intact, but avoid hundreds of Frida calls for each label.
    if(finishStaticRuby(row,array,count)){recordTiming('geometry',started);return;}
    // Each Frida memory operation crosses the JS/native boundary. Read each
    // glyph once for the whole pass instead of reading it again for scale,
    // bounds, alignment and color. Write only fields owned by this layout.
    const glyphs=new Map();
    const glyph=index=>{
        if(glyphs.has(index))return glyphs.get(index);
        const q=array.add(index*8).readPointer(),data=q.readByteArray(0xc4),view=new DataView(data);
        const v={q,data,view,x:view.getFloat32(0x38,true),y:view.getFloat32(0x3c,true),
            w:view.getFloat32(8,true),h:view.getFloat32(0x1c,true),kind:view.getUint32(0xc0,true)};
        if(![v.x,v.y,v.w,v.h].every(Number.isFinite))throw Error('Invalid native glyph geometry');
        glyphs.set(index,v);return v;
    };
    // Undo this pass's previous offset before aligning newly revealed glyphs.
    // A native parser rebuild clears the cache, even if it reuses pointers.
    if(row.offsetPositions)for(const [index,saved] of row.offsetPositions) {
        if(index<count) {
            const v=glyph(index);
            if(saved.q.equals(v.q))v.y=saved.y;
        }
    }
    row.offsetPositions=null;
    const scalePrimaryRun=(lane,start,end)=>{
        if(!row.preservePrimaryLayout||annotationScale===1)return;
        // Reuse the original local matrices when typewriter output adds glyphs.
        // A new native parse creates fresh lanes; repeated frames never compound.
        const saved=lane.unscaled||(lane.unscaled=new Map());
        let segment=[];
        const flush=()=>{
            if(!segment.length)return;
            const left=Math.min(...segment.map(v=>v.x-Math.abs(v.w)/2));
            const bottom=Math.max(...segment.map(v=>v.y+Math.abs(v.h)/2));
            for(const {v,g} of segment) {
                g.w=Math.fround(v.w*annotationScale);g.h=Math.fround(v.h*annotationScale);
                g.x=Math.fround(left+(v.x-left)*annotationScale);g.y=Math.fround(bottom+(v.y-bottom)*annotationScale);
            }
            segment=[];
        };
        for(let i=start;i<end;i++) {
            const g=glyph(i),q=g.q;
            if(g.kind===1){flush();continue;}
            let v=saved.get(i);
            if(!v||!v.q.equals(q)) {
                v={q,x:g.x,y:g.y,w:g.w,h:g.h};
                saved.set(i,v);
            }
            segment.push({v,g,x:v.x,y:v.y,w:v.w,h:v.h});
        }
        flush();
    };
    const bounds=(start,end,includeIcons=false)=>{
        let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
        for(let i=start;i<end;i++) {
            const g=glyph(i);
            // Keep main-language icons at their native size and position.
            // Secondary icons are part of the added lane's visible bounds.
            if(!includeIcons&&g.kind===1)continue;
            const {x,y}=g,w=Math.abs(g.w),h=Math.abs(g.h);
            left=Math.min(left,x-w/2);right=Math.max(right,x+w/2);top=Math.min(top,y-h/2);bottom=Math.max(bottom,y+h/2);
        }
        return {left,right,top,bottom};
    };
    for(let i=0;i<lanes.length;i++) {
        const lane=lanes[i];
        const primaryStart=lane.layer?lane.end:lane.primaryStart;
        const primaryEnd=lane.layer?(lane.primaryEnd??lanes[i+1]?.primaryStart??count):lane.start;
        if(!(lane.start>=0&&lane.start<lane.end&&lane.end<=count))continue;
        const hasPrimary=primaryStart>=0&&primaryStart<primaryEnd&&primaryEnd<=count;
        if(hasPrimary)scalePrimaryRun(lane,primaryStart,primaryEnd);
        // The secondary parser already applies native ruby size, ruby_scale
        // and the source's absolute S/s emphasis. Ordinary ruby keeps those
        // metrics when primary text is shrunk with <s>. Preserve the same
        // secondary metrics when primary shrinking instead happens here
        // (explicit sizes, original readings, mixed runs). Shrinking this
        // lane again made enlarged dialogue annotations smaller than normal.
        const secondary=bounds(lane.start,lane.end,true),primary=hasPrimary?bounds(primaryStart,primaryEnd):null;
        const dx=primary?primary.left+rubyOffsetX-secondary.left:0,dy=primary?primary.top-rubyGap-secondary.bottom:0;
        if(!Number.isFinite(dx)||!Number.isFinite(dy))continue;
        // Parser +0x1c counts emitted main characters (including spaces/icons),
        // unlike +0x14 which counts markup bytes/codepoints. Read only the
        // persistent parser after Update; never alter the native reveal clock.
        const animated=lane.layer&&row.animated&&lane.mainUnits>0;
        const fraction=animated?Math.max(0,Math.min(1,(revealUnits-lane.unitStart)/lane.mainUnits)):1;
        const edge=secondary.left+(secondary.right-secondary.left)*fraction;
        for(let j=lane.start;j<lane.end;j++) {
            const g=glyph(j),q=g.q,left=g.x-Math.abs(g.w)/2;
            g.x=Math.fround(g.x+dx);g.y=Math.fround(g.y+dy);
            // Verified glyph renderer 0x583300 reads RGBA at 0x98..0xa4.
            // Keep original colors per parse: incremental typewriter layouts
            // must never apply the multiplier repeatedly. Opacity and reveal
            // multiply the saved native alpha, including icon/shadow quads.
            const colors=lane.colors||(lane.colors=new Map());
            let saved=colors.get(j);
            if(!saved||!saved.q.equals(q)) {
                saved={q,rgb:[0x98,0x9c,0xa0].map(off=>g.view.getFloat32(off,true)),alpha:g.view.getFloat32(0xa4,true)};
                if(!saved.rgb.every(v=>Number.isFinite(v)&&v>=0&&v<=1))throw Error('Invalid glyph color');
                colors.set(j,saved);
            }
            g.color=saved.rgb.map((v,c)=>v*secondaryColor[c]);
            let reveal=1;
            if(animated) {
                reveal=fraction===1?1:fraction===0?0:Math.max(0,Math.min(1,(edge-left)/Math.max(Math.abs(g.w),.001)));
            }
            g.color.push(saved.alpha*secondaryOpacity*reveal);
        }
    }
    if(bilingualOffsetY!==0) {
        row.offsetPositions=new Map();
        for(let i=0;i<count;i++) {
            const g=glyph(i);
            row.offsetPositions.set(i,{q:g.q,y:g.y});g.y=Math.fround(g.y+bilingualOffsetY);
        }
    }
    for(const g of glyphs.values()) {
        const {q,view,data}=g;
        for(const [off,value] of [[8,g.w],[0x1c,g.h]])if(view.getFloat32(off,true)!==value)q.add(off).writeFloat(value);
        if(view.getFloat32(0x38,true)!==g.x||view.getFloat32(0x3c,true)!==g.y) {
            view.setFloat32(0x38,g.x,true);view.setFloat32(0x3c,g.y,true);q.add(0x38).writeByteArray(data.slice(0x38,0x40));
        }
        if(g.color&&g.color.some((v,i)=>Math.fround(v)!==view.getFloat32(0x98+i*4,true))) {
            g.color.forEach((v,i)=>view.setFloat32(0x98+i*4,v,true));q.add(0x98).writeByteArray(data.slice(0x98,0xa8));
        }
    }
    recordTiming('geometry',started);
}
function copyOwnedText(row,text) {
    const p=row.pointer,buffer=Memory.allocUtf8String(text);
    const thread=Process.getCurrentThreadId(),stack=rewriteStacks.get(thread)||[];
    stack.push({pointer:p,text});rewriteStacks.set(thread,stack);
    try {setter(p,buffer);} finally {stack.pop();if(!stack.length)rewriteStacks.delete(thread);}
    if(readText(p)!==text)throw Error('SetText did not retain a copied string');
    row.displayed=text;writes++;
}
function observeNativeText(p,identify=null,force=false) {
    if(activeRewrite(p)||!isLabel(p))return;
    const lease=enterLabel(p);if(!lease)return;
    try {
        const current=readText(p),existing=labels.get(String(p));
        if(!force&&existing&&existing.displayed===current)return;
        const row=existing||remember(p,current);
        row.original=current;row.displayed=current;
        row.scriptIdentity=null;row.scriptPointer=null;row.tableIdentity=null;row.paragraph=null;row.logSpeaker=null;row.logKind=null;row.book=null;
        if(identify)identify(row);
        const renderEpoch=epoch,wanted=wantedText(row);
        if(wanted!==current){copyOwnedText(row,wanted);immediateWrites++;}
        row.epoch=renderEpoch;captureMetadata(row);
    }finally{leaveLabel(lease);}
}
function adoptCopiedLabel(p,source) {
    // The native copy constructor clones a template's owned UTF-8 buffer,
    // bypassing SetText. Carry provenance, not a reverse-parsed translation,
    // before its first measure/draw. Never share mutable lane/parser state.
    const original=labels.get(String(source));
    if(!original||!isLabel(p)||!isLabel(source))return;
    const current=readText(p);
    if(current!==original.displayed||readText(source)!==current)return;
    const lease=enterLabel(p);if(!lease)return;
    try {
        const row=remember(p,original.original);
        row.displayed=current;
        for(const key of ['scriptIdentity','scriptPointer','tableIdentity','paragraph','logSpeaker','logKind','book'])row[key]=original[key];
        const renderEpoch=epoch,wanted=wantedText(row);
        if(wanted!==current){copyOwnedText(row,wanted);immediateWrites++;}
        row.epoch=renderEpoch;captureMetadata(row);
    }finally{leaveLabel(lease);}
}
if(REPORT.native.copy_label_ready) Interceptor.attach(base.add(REPORT.native.copy_label_ready.rva),{
    onEnter(){try{adoptCopiedLabel(this.context.rdi,this.context.rbx);}catch(e){fail(e);}}
});
// Several native callers inline SetText's buffer copy (including save-party
// details), then call this common measuring entry. Resolve before it measures
// and draws; polling Update afterwards loses to the next inlined write.
if(REPORT.native.measure_text) Interceptor.attach(base.add(REPORT.native.measure_text.rva),{
    onEnter(args){
        this.started=Date.now();this.measureToken=0;
        try {
            const p=args[0];observeNativeText(p);
            const frame=logMeasureFrames.get(Process.getCurrentThreadId())?.at(-1);
            if(!nativeMeasure||!enabled||failed||!frame?.pending||
                    !frame.measuringLabels?.some(label=>label.equals(p)))return;
            const row=ownedRow(p);
            if(row?.plan.kind==='ruby'&&row.reserveRubyHeight&&!row.preservePrimaryLayout&&
                    !row.animated&&!row.plan.layers?.length) {
                this.measureThread=Process.getCurrentThreadId();
                this.measureToken=nativeMeasure.push(this.measureThread,p,p.add(0x318).readPointer(),rubyScale);
            }
        }catch(e){fail(e);}
    },
    onLeave(){
        try {if(this.measureToken)nativeMeasure.pop(this.measureThread,this.measureToken);}
        catch(e){fail(e);}finally{recordTiming('measure',this.started);}
    }
});
function beginAnnotationLane(p,parser,phase,row=ownedRow(p)) {
    if(parser.add(0x1ab).readU8())return;
    const layer=auxiliaryLayer(p,parser,row);
    if(!layer&&row?.plan.kind!=='ruby')return;
    const count=p.add(0x330).readU32(),key=String(parser);
    // A new parse may start after untranslated text or decoration. Plain
    // ruby enters at its opening tag; a layered anchor is identifiable only
    // at its closing tag's base-measure callback. Both entries must retire
    // the previous parse when the glyph cursor rewinds. Otherwise a layered
    // log row with a nonzero prefix retains one more scaling pass per frame.
    if(phase==='open'||(phase==='primary'&&layer)) {
        const previous=row.glyphLanes?.findLast(lane=>lane.parser===key);
        if(previous&&count<=previous.primaryStart) {
            row.glyphLanes=[];row.laneCount=-1;row.laneUnits=-1;
            row.offsetPositions=null;
        }
    }
    if(phase==='open'||phase==='primary') {
        // Plain ruby draws its base before the closing-tag measurement.
        // Empty layered anchors have no base; their primary run comes later.
        if(phase==='primary'&&!layer)return;
        if(!row.glyphLanes||count===0){row.glyphLanes=[];row.offsetPositions=null;}
        row.glyphLanes.push({primaryStart:count,parser:key,layer:!!layer,unitStart:parser.add(0x1c).readU32()});
    } else {
        const lane=row.glyphLanes?.findLast(v=>v.parser===key&&v[phase]===undefined);
        if(lane)lane[phase]=count;
    }
    row.lanesDirty=true;
}
if(REPORT.native.ruby_begin) Interceptor.attach(base.add(REPORT.native.ruby_begin.rva),{
    onEnter(){try{
        const p=this.context.r15,parser=this.context.rbx;
        const row=ownedRow(p);
        beginAnnotationLane(p,parser,'open',row);
        // Keep flag-8 labels' native primary-only measurement. A setter called
        // inside Update runs without nested Frida callbacks; clearing flag 8
        // during an external measurement added ruby height only on cold entry.
        // Lift the permission for drawing only, then restore it at ruby_end.
        if(!parser.add(0x1ab).readU8()&&(row?.plan.kind==='ruby'||auxiliaryLayer(p,parser,row))) {
            const flags=p.add(0x2e8).readU32();
            if(flags&8){rubyPermissions.set(String(parser),p);p.add(0x2e8).writeU32(flags&~8);}
        }
    }catch(e){fail(e);}}
});
// Update rebuilds flag-0x40 labels every frame. Correct local glyph positions
// after parsing and BEFORE Update transforms them into the rendered matrix.
// Doing this in Update.onLeave loses the correction on the next rebuild.
if(REPORT.native.layout_ready) Interceptor.attach(base.add(REPORT.native.layout_ready.rva),{
    onEnter(){try{
        const p=this.context.rsi;
        if(labels.get(String(p))?.glyphLanes?.length)finishAnnotationLanes(ownedRow(p));
        offsetTextProjection(p);
    }catch(e){fail(e);}}
});
// Align owned annotations with the measured primary run's left edge.
// Only adjust the parser's temporary context
// for a tracked translated label, never a label/global setting. Layout can
// be deferred until the native Update body after our SetText has returned.
function inheritAuxiliaryIcons(child,parent,label) {
    if(!cloneIconCallback)return;
    const source=parent.add(0x240).readPointer();
    if(source.isNull())return;
    if(!source.readPointer().equals(base.add(REPORT.icon_callback_vtable))||!source.add(8).readPointer().equals(label))
        throw Error('Unvalidated annotation icon callback');
    if(!child.add(0x240).readPointer().isNull())throw Error('Annotation icon callback already initialized');
    // The engine clones the character callback (+0x200) for ruby, but omits
    // the separate icon callback (+0x240). Use its verified clone operation
    // with the child's own small-function storage; native cleanup owns it.
    const storage=child.add(0x208),copy=cloneIconCallback(source,storage);
    if(!copy.equals(storage))throw Error('Unexpected annotation callback storage');
    child.add(0x240).writePointer(copy);
}
const rubyContextCallbacks={
    absoluteFactor(row,factor) {
        if(!row||!REPORT.font_manager_global)return factor;
        // S/s replaces the scale with requested pixels / this label's font
        // base. R starts with ruby pixels / font-0 base instead. Convert the
        // actual initial ruby scale to a ratio against the label's normal
        // size before restoring it after an absolute size command.
        const label=row.pointer,manager=base.add(REPORT.font_manager_global).readPointer();
        const index=label.add(0x300).readU32(),count=manager.add(0x10).readU32();
        if(index>=count||count>1024)throw Error('Invalid annotation font index');
        const font=manager.add(8).readPointer().add(index*8).readPointer();
        const fontSize=font.add(0x28).readU32(),labelSize=row.renderSize||label.add(0x304).readU32();
        if(!(fontSize>0&&fontSize<=4096&&labelSize>0&&labelSize<=4096))throw Error('Invalid annotation font metrics');
        return factor*fontSize/labelSize;
    },
    onEnter(args) {
        this.target = null;
        this.placement=this.returnAddress.equals(base.add(REPORT.native.ruby_place_return.rva));
        const measurement=REPORT.native.ruby_measure_return && this.returnAddress.equals(base.add(REPORT.native.ruby_measure_return.rva));
        this.baseMeasurement=REPORT.native.ruby_base_measure_return&&this.returnAddress.equals(base.add(REPORT.native.ruby_base_measure_return.rva));
        if(!this.placement && !measurement&&!this.baseMeasurement)return;
        try {
            const p = this.context.r15;
            // Reuse only within this callback: the next native entry must
            // validate ownership again, including same-buffer text changes.
            const row=ownedRow(p);
            this.owner=row;
            if(this.baseMeasurement)beginAnnotationLane(p,this.context.rbx,'primary',row);
            if(this.placement)beginAnnotationLane(p,this.context.rbx,'start',row);
            const layer=auxiliaryLayer(p,this.context.rbx,row);
            if(layer) {
                this.target=args[0];this.layer=layer;
                if(this.baseMeasurement&&(row.reserveAuxiliaryHeight||
                        (layer.layer.primary||'').includes('<R>')||layer.layer.text.includes('<R>'))) {
                    annotationMetrics.set(String(this.context.rbx),{primary:0,secondary:0,secondaryLine:0,
                        origin:this.context.rbx.add(4).readFloat(),layer:layer.layer});
                }
                this.metrics=annotationMetrics.get(String(this.context.rbx));
                if(this.placement&&row.reserveAuxiliaryHeight&&this.metrics?.layer===layer.layer) {
                    // 0x58709f measures this child at (0, 0); 0x58714a then
                    // reinitializes the SAME context for positioned drawing.
                    // Capture the local bounds before that reset. The bounds
                    // at ruby_compensate include the paragraph's Y because
                    // parse_text seeds its envelope with (0, 0): reserving that
                    // envelope feeds the preceding lines back into each line.
                    const top=args[0].add(0x1bc).readS32(),bottom=args[0].add(0x1c4).readS32();
                    const height=bottom-top;
                    if(height>=0&&height<=65536)this.metrics.secondaryLine=height;
                }
                const text=this.baseMeasurement?(layer.layer.primary||layer.row.original):layer.layer.text;
                args[1]=this.baseMeasurement?layer.primaryBuffer:layer.buffer;args[2]=ptr([...text].length);
                return;
            }
            if(this.baseMeasurement)return;
            const parent=auxiliaryContexts.get(String(this.context.rbx));
            if(parent) {this.target=args[0];this.inherited=parent;this.parent=this.context.rbx;return;}
            if (row?.plan.kind!=='ruby') return;
            this.target = args[0];
            this.source = row.original;
            this.clampLeft=p.add(0x2e8).readU32()===1;
            if(this.placement) {
                // Verified at 0x5870cd: native centering uses the primary run's
                // measured width and the parser cursor after that run.
                const width=Math.abs(this.context.rbp.add(0x3d0).readS32()-this.context.rbp.add(0x3c8).readS32());
                const end=this.context.rbx.readFloat();
                if(!Number.isFinite(end)||width>65536)throw Error('Invalid primary run bounds');
                this.baseLeft=end-width;
            }
        } catch (e) { fail(e); }
    },
    onLeave() {
        if (!this.target) return;
        try {
            if(this.baseMeasurement) {
                // Reuse the engine's existing read-only measuring pass. No
                // additional native call and no primary text is drawn here.
                this.target.add(0x1a9).writeU8(0);
                this.target.add(0x1a5).writeU8(1);
                if(this.metrics) {
                    // Read original primary readings in the existing measuring
                    // pass, with output disabled. Only owned layer scopes gain
                    // nested-reading permission; native single-language ruby
                    // keeps its original recursion/permission rules.
                    this.target.add(0x1ab).writeU8(1);
                    const scope={factor:1,placement:false,allowReadings:true,measureOnly:true,
                        metrics:this.metrics,metricRole:'primary',readingDepth:0};
                    if(nativeParser)nativeParser.set(this.target,scope);
                    else auxiliaryContexts.set(String(this.target),scope);
                }
                return;
            }
            const x = this.target.readFloat();
            if (!Number.isFinite(x)) throw Error('Non-finite ruby placement');
            // Nested native <R> readings start from the engine's fixed ruby
            // size (0x586f57..0x586f92), not the parent's current size. C/c/B
            // commands do not create contexts. Scale an actual nested reading
            // relative to its parent's annotation multiplier.
            const scaleFactor=this.inherited?this.inherited.factor:rubyScale;
            for(const offset of [0x158,0x15c]) {
                const field=this.target.add(offset),scale=field.readFloat();
                if(!Number.isFinite(scale)||scale<=0||scale>8)throw Error('Unvalidated ruby scale');
                field.writeFloat(scale*scaleFactor);
            }
            if(this.layer) {
                const factor=this.target.add(0x15c).readFloat();
                const auxiliary={factor,sizeFactor:rubyContextCallbacks.absoluteFactor(this.owner,factor),
                    placement:this.placement,allowReadings:!!this.metrics||this.placement};
                if(this.metrics&&!this.placement) {
                    Object.assign(auxiliary,{metrics:this.metrics,metricRole:'secondary',readingDepth:0,measureOnly:true});
                    this.target.add(0x1a9).writeU8(0);this.target.add(0x1ab).writeU8(1);
                }
                if(nativeParser)nativeParser.set(this.target,auxiliary);
                else auxiliaryContexts.set(String(this.target),auxiliary);
                if(this.placement) {
                    if(this.layer.layer.text.includes('<I'))inheritAuxiliaryIcons(this.target,this.layer.parser,this.layer.row.pointer);
                    const px=this.layer.parser.readFloat(),py=this.layer.parser.add(4).readFloat();
                    if(!Number.isFinite(px)||!Number.isFinite(py))throw Error('Invalid lane origin');
                    this.target.writeFloat(px+rubyOffsetX);
                    // Final spacing is shared with plain ruby and is resolved
                    // from rendered glyph edges in finishAnnotationLanes.
                }
                return;
            }
            if(this.inherited) {
                // Register this nested reading's own fixed multiplier for any
                // S/s commands it contains, and for a deeper native reading.
                const auxiliary={factor:this.target.add(0x15c).readFloat(),placement:this.placement,
                    allowReadings:this.inherited.allowReadings??this.placement};
                auxiliary.sizeFactor=this.inherited.metricRole==='primary'?1:
                    rubyContextCallbacks.absoluteFactor(this.owner,auxiliary.factor);
                if(this.inherited.metrics) {
                    Object.assign(auxiliary,{metrics:this.inherited.metrics,metricRole:this.inherited.metricRole,
                        readingDepth:this.inherited.readingDepth+1,measureOnly:true});
                    this.target.add(0x1a9).writeU8(0);this.target.add(0x1ab).writeU8(1);
                }
                if(nativeParser)nativeParser.set(this.target,auxiliary);
                else auxiliaryContexts.set(String(this.target),auxiliary);
                if(this.placement) {
                    inheritAuxiliaryIcons(this.target,this.parent,this.context.r15);
                    const origin=this.parent.add(4).readFloat(),y=this.target.add(4).readFloat();
                    this.target.add(4).writeFloat(origin+(y-origin)*this.inherited.factor);
                }
                return;
            }
            // The parser may subsequently consume <S…>/<s…> and reset its
            // scale fields to an absolute label size. Keep this owned ruby
            // context available to the verified command tail so it can retain
            // the native ruby baseline as well as the user's ruby_scale.
            if(nativeParser)nativeParser.trackScale(this.target,
                rubyContextCallbacks.absoluteFactor(this.owner,this.target.add(0x15c).readFloat()));
            if (this.placement) {
                const shifted=this.baseLeft+rubyOffsetX;
                this.target.writeFloat(this.clampLeft?Math.max(0,shifted):shifted);
                if(this.clampLeft && shifted<0)
                    if(REPORT.diagnostics)send({type:'ruby_clamped', original:this.source, before:shifted, after:0});
            }
        } catch (e) { fail(e); }
    }
};
if(typeof createNativeMeasure==='function')nativeMeasure=createNativeMeasure(rubyContextCallbacks,{
    measurement:base.add(REPORT.native.ruby_measure_return.rva),
    baseMeasurement:base.add(REPORT.native.ruby_base_measure_return.rva),
    placement:base.add(REPORT.native.ruby_place_return.rva)
},fail,nativeParser);
Interceptor.attach(base.add(REPORT.native.ruby_context_init.rva),nativeMeasure?{
    onEnter:nativeMeasure.onEnter,onLeave:nativeMeasure.onLeave
}:rubyContextCallbacks);
if(REPORT.native.layout_create) Interceptor.attach(base.add(REPORT.native.layout_create.rva),{
    onLeave(value){try{registerLayout(value);}catch(e){fail(e);}}
});
if(REPORT.native.layout_release) Interceptor.attach(base.add(REPORT.native.layout_release.rva),{
    onEnter(args){const k=String(args[1]);const root=layoutRoots.get(k);if(root){subtitleRoots.delete(root);insetRoots.delete(root);}layoutRoots.delete(k);}
});
// An empty annotation anchor must not contribute an invalid empty bounding
// box or the engine's one-time ruby baseline compensation. These sites are
// fingerprinted alongside SetText and only touch the current parser context.
if(REPORT.native.ruby_base_measure_end) Interceptor.attach(base.add(REPORT.native.ruby_base_measure_end.rva),{onEnter(){
    try {
        const item=auxiliaryLayer(this.context.r15,this.context.rbx);if(!item)return;
        const lane=item.row.glyphLanes?.findLast(v=>v.layer&&v.parser===String(this.context.rbx));
        if(lane)lane.mainUnits=this.context.rbp.add(0x22c).readU32();
        for(const off of [0x3c8,0x3cc,0x3d0,0x3d4])this.context.rbp.add(off).writeS32(0);
    }catch(e){fail(e);}
}});
if(REPORT.native.ruby_compensate) Interceptor.attach(base.add(REPORT.native.ruby_compensate.rva),{onEnter(){
    try {
        const p=this.context.rbx;
        const scope=auxiliaryContexts.get(String(p));
        if(scope?.metrics&&scope.readingDepth===0) {
            // 0x587224 has completed this reading's existing native parse.
            // Its bounds are at rbp-0x40 + 0x1b8..0x1c4. Read the height,
            // not a guessed font size, once per native reading on this line.
            const top=this.context.rbp.add(0x17c).readS32(),bottom=this.context.rbp.add(0x184).readS32();
            const height=bottom-top;
            if(height>=0&&height<=65536)scope.metrics[scope.metricRole]=Math.max(scope.metrics[scope.metricRole],height);
        }
        const row=ownedRow(this.context.r15);
        beginAnnotationLane(this.context.r15,p,'end',row);
        const layer=auxiliaryLayer(this.context.r15,p,row);
        if(layer) {
            const key=String(p),metrics=annotationMetrics.get(key);
            if(metrics?.layer===layer.layer) {
                annotationMetrics.delete(key);
                // The local secondary envelope already contains its original
                // readings. Reserve them once, in both measuring and drawing.
                const secondary=row.reserveAuxiliaryHeight&&metrics.secondaryLine>0?
                    Math.max(metrics.secondary,metrics.secondaryLine+rubyGap):metrics.secondary;
                const reserve=metrics.primary*(row.preservePrimaryLayout?annotationScale:1)+secondary;
                const origin=p.add(4).readFloat(),next=origin+reserve;
                if(!Number.isFinite(next)||reserve<0||reserve>65536)throw Error('Invalid native reading reserve');
                if(reserve) {
                    // The anchor precedes primary glyphs, so native bounds and
                    // subsequent newlines include this reserve in both passes.
                    // Include the old origin so the first line's blank space
                    // is not cancelled by bounding-box normalisation.
                    p.add(4).writeFloat(next);
                    p.add(0x1bc).writeS32(Math.min(p.add(0x1bc).readS32(),Math.floor(origin)));
                    p.add(0x1c4).writeS32(Math.max(p.add(0x1c4).readS32(),Math.ceil(next)));
                }
            }
        }
        if(!layer&&row?.plan.kind!=='ruby')return;
        // Measurement always retains the native one-time height reserve.
        // Suppressing it only for mixed/layered cold setters made their bounds
        // 12 units shorter than nested setters (whose hooks Frida suppresses).
        // Drawing corrects its origin separately, without changing the bounds.
        if(p.add(0x1ab).readU8())return;
        compensation.set(String(p),p.add(0x1a7).readU8());p.add(0x1a7).writeU8(1);
    }catch(e){fail(e);}
}});
if(REPORT.native.ruby_end) Interceptor.attach(base.add(REPORT.native.ruby_end.rva),{onEnter(){
    try {
        const p=this.context.rbx,k=String(p);
        if(compensation.has(k)){p.add(0x1a7).writeU8(compensation.get(k));compensation.delete(k);}
        const owner=rubyPermissions.get(k);
        if(owner){owner.add(0x2e8).writeU32(owner.add(0x2e8).readU32()|8);rubyPermissions.delete(k);}
    }catch(e){fail(e);}
}});
if(REPORT.native.parse_text) Interceptor.attach(base.add(REPORT.native.parse_text.rva),nativeParser?{
    onEnter:nativeParser.onEnter,onLeave:nativeParser.onLeave
}:{
    onEnter(args) {
        this.key=String(args[1]);this.aux=auxiliaryContexts.has(this.key);
        // The verified draw path (0x587718/0x587764) uses label+0x400.
        // Count only that outer parser, not its nested ruby measuring passes.
        // Together with measure timing this separates opening cost from the
        // post-parse geometry loop, without streaming any dialogue content.
        if(args[1].equals(args[0].add(0x400)))this.started=Date.now();
        // Permit original ruby inside the secondary's own temporary context.
        if(this.aux) {
            const scope=auxiliaryContexts.get(this.key);
            args[1].add(0x1a5).writeU8((scope.allowReadings??scope.placement)?0:1);
            if(scope.measureOnly){args[1].add(0x1a9).writeU8(0);args[1].add(0x1ab).writeU8(1);}
        }
    },
    onLeave(){if(this.aux)auxiliaryContexts.delete(this.key);recordTiming('parse',this.started);}
});
const nativeSizeHook=nativeParser?.installSizeHook&&REPORT.native.ruby_size_end
    ?nativeParser.installSizeHook(base.add(REPORT.native.ruby_size_end.rva),REPORT.native.ruby_size_end.bytes):null;
if(REPORT.native.line_ruby_origin) Interceptor.attach(base.add(REPORT.native.line_ruby_origin.rva),{
    onEnter(args) {
        this.parser=null;
        try {
            const row=ownedRow(args[0]),parser=args[1];
            // Keep the specific speaker/mixed-layout correction. Ordinary
            // labels retain their native origin; whole-group offset is an
            // explicit user setting, not an automatic global compensation.
            if(row?.plan.kind==='ruby'&&
                    (row.dialogueSpeaker||row.preservePrimaryLayout)&&
                    !row.original.includes('<R>')&&!parser.add(0x1ab).readU8()) {
                this.y=parser.add(4).readFloat();this.parser=parser;
                if(!Number.isFinite(this.y))throw Error('Invalid native line origin');
            }
        }catch(e){fail(e);}
    },
    onLeave(){if(this.parser)try{this.parser.add(4).writeFloat(this.y);}catch(e){fail(e);}}
});
if(REPORT.native.newline_prepare) Interceptor.attach(base.add(REPORT.native.newline_prepare.rva),{
    onEnter() {
        try {
            const row=ownedRow(this.context.r13);
            const parser=this.context.rsi;
            if(row?.glyphLanes?.length&&!parser.add(0x1ab).readU8()) {
                // A following untranslated line has no annotation anchor.
                // Close this layer at the actual native newline, not at the
                // next anchor or end of the entire label's glyph array.
                const lane=row.glyphLanes.findLast(v=>v.layer&&v.parser===String(parser)&&v.primaryEnd===undefined);
                if(lane){lane.primaryEnd=row.pointer.add(0x330).readU32();row.lanesDirty=true;}
            }
            if(!row?.extendLineSpacing)return;
            const bottom=this.context.r12.toInt32();
            if(bottom < -16384 || bottom > 65536)throw Error('Unvalidated newline extent');
            // The native newline path adds label spacing to r12, the previous
            // line's bottom. Extend this temporary layout value, not the label.
            this.context.r12=this.context.r12.add(rubyLineGap);
        }catch(e){fail(e);}
    }
});
Interceptor.attach(base.add(REPORT.native.destroy.rva), {onEnter(args) {
    const group=logTextGroups.get(String(args[0]));
    if(group){group.retired=true;logTextGroups.delete(String(group.name));logTextGroups.delete(String(group.body));}
    if (labels.delete(String(args[0]))) destroyed++;
    nativeBooks?.forget(args[0]);
}});
// actor_name_set copies a script literal into actor+2c0; actor_name_get
// returns that owned buffer when +2cc is nonzero. Preserve the script key
// across this copy, validating the current owner and bytes at consumption.
const actorNames=new Map(),ownedNames=new Map();
if(REPORT.native.actor_name_set)Interceptor.attach(base.add(REPORT.native.actor_name_set.rva),{
    onEnter(args){
        this.actor=args[0];this.entry=null;
        // Native null input changes only +25c6, preserving the owned name.
        if(args[1].isNull())return;
        const previous=actorNames.get(String(this.actor));
        if(previous)ownedNames.delete(String(previous.buffer));
        actorNames.delete(String(this.actor));
        try {
            if(args[1].isNull()||!scriptIdentities)return;
            const source=args[1].readUtf8String();
            if(!source||RuntimeText.byteLength(source)>=256)return;
            const entry=scriptIdentities.pointerSelect(args[1],source);
            if(entry)this.entry={source,key:entry.key};
        }catch(_){/* Unverified names retain their original lookup path. */}
    },
    onLeave(){
        if(!this.entry)return;
        try {
            const buffer=this.actor.add(0x2c0).readPointer(),length=this.actor.add(0x2cc).readU32();
            if(buffer.isNull()||length!==RuntimeText.byteLength(this.entry.source)||buffer.readUtf8String()!==this.entry.source)return;
            if(actorNames.size>=4096){actorNames.clear();ownedNames.clear();}
            const row={...this.entry,actor:this.actor,buffer};
            actorNames.set(String(this.actor),row);ownedNames.set(String(buffer),row);
        }catch(_){/* Failed or empty native copies have no provenance. */}
    }
});
function ownedNameIdentity(input,source) {
    const row=ownedNames.get(String(input));if(!row||row.source!==source)return null;
    try {
        if(row.actor.add(0x2c0).readPointer().equals(input)&&
                row.actor.add(0x2cc).readU32()===RuntimeText.byteLength(source)&&input.readUtf8String()===source)return row.key;
    }catch(_){}
    ownedNames.delete(String(input));actorNames.delete(String(row.actor));return null;
}
// Carry provenance only along the verified native dialogue call stack and
// its exact output buffer. Never rewrite the builder's fixed 0x800-byte buffer.
for(const name of ['dialogue_popup','dialogue_message','dialogue_bubble']) {
    if(!REPORT.native[name])continue;
    Interceptor.attach(base.add(REPORT.native[name].rva),{
        onEnter(){
            this.thread=Process.getCurrentThreadId();
            const stack=dialogueFrames.get(this.thread)||[];
            this.frame={outputs:new Map()};stack.push(this.frame);dialogueFrames.set(this.thread,stack);
        },
        onLeave(){
            const stack=dialogueFrames.get(this.thread);
            if(stack?.at(-1)===this.frame)stack.pop();else stack?.splice(0);
            if(!stack?.length)dialogueFrames.delete(this.thread);
        }
    });
}
if(REPORT.native.dialogue_builder)Interceptor.attach(base.add(REPORT.native.dialogue_builder.rva),{
    onEnter(args){
        this.frame=dialogueFrames.get(Process.getCurrentThreadId())?.at(-1);
        if(!this.frame||!scriptIdentities)return;
        this.output=args[1];this.frame.outputs.delete(String(this.output));
        try {
            const vm=args[3],blob=vm.add(8).readPointer().readPointer();
            if(blob.readU32()!==0x70637323)return;
            const start=blob.add(4).readU32(),count=blob.add(8).readU32();
            if(start<24||count<1||count>65536||start+count*32>16*1024*1024)return;
            const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n))).map(v=>v.toString(16).padStart(2,'0')).join('');
            const signature=hex(blob,24)+hex(blob.add(start),32)+hex(blob.add(start+(count-1)*32),32);
            if(!scriptIdentities.canCapture(signature))return;
            const functionName=vm.add(0x88).readPointer().readUtf8String();
            if(functionName.length>256)return;
            const argc=vm.add(0x70).readU32(),top=vm.add(0x64).readS32(),stack=vm.add(0x58).readPointer();
            if(argc>512||top<argc*4||top>16*1024*1024)return;
            const values=[];for(let i=0;i<argc;i++)values.push(stack.add(top-(i+1)*4).readU32());
            const site={pc:vm.add(0x10).readU32(),group:vm.add(0x68).readU32(),command:vm.add(0x6c).readU32()};
            this.candidate={signature,blob,functionName,argumentsToken:values.join(','),site};
        } catch(e) {
            // Unknown or changing resources lose identity, never game stability.
            identityMisses++;
        }
    },
    onLeave(){
        if(!this.candidate)return;
        const started=Date.now();
        try {
            const source=this.output.readUtf8String();
            if(RuntimeText.byteLength(source)>=2048)return;
            // Provenance belongs to the source invocation, not the selected
            // languages. A later language may distinguish today's equal pair.
            const {signature,blob,functionName,argumentsToken,site}=this.candidate;
            this.identity=scriptIdentities?.capture(signature,n=>resourceHash.pointer?{pointer:blob,byteLength:n}:blob.readByteArray(n),functionName,argumentsToken,site,source);
            if(!this.identity)return;
            this.frame.outputs.set(String(this.output),{source,identity:this.identity});
        }catch(e){identityMisses++;}finally{recordTiming('identity',started);}
    }
});
// The history copies dialogue bytes into a ring; heap strings cannot identify
// the original script call. Record only synchronous builder -> writer
// provenance, then validate the current slot payload before giving it to a UI.
function logOwner() {
    if(!logOrigins||!REPORT.log_owner_global)return null;
    const owner=base.add(REPORT.log_owner_global).readPointer();
    logOrigins.useOwner(owner.isNull()?null:String(owner));
    return owner.isNull()?null:owner;
}
function logStamp(record) {
    // Status bits at +188 may change when history is viewed; they are not a
    // record generation. Payload bytes are replaced only by the native writer.
    return Array.from(new Uint8Array(record.readByteArray(0x188))).map(v=>v.toString(16).padStart(2,'0')).join('');
}
function resetLogOrigins() {
    logOrigins?.reset();logWriteFrames.clear();logPresentFrames.clear();logBuildFrames.clear();logRows.clear();logControllers.clear();logTextGroups.clear();logOriginStats.resets++;
}
function rememberLogTextGroup(controller) {
    const name=controller.add(0x10).readPointer(),body=controller.add(0x18).readPointer();
    for(const p of [name,body]) {
        const previous=logTextGroups.get(String(p));
        if(previous){previous.retired=true;logTextGroups.delete(String(previous.name));logTextGroups.delete(String(previous.body));}
    }
    if(controller.add(0x88).readU32()!==0||name.isNull()||body.isNull()||!isLabel(name)||!isLabel(body))return;
    const frame=controller.add(8).readPointer(),parent=body.add(0x80).readPointer();
    if(frame.isNull()||parent.isNull()||!name.add(0x80).readPointer().equals(parent)||
            !frame.add(0x80).readPointer().equals(parent))return;
    // 0x360130 writes the row rectangle's height. 0x589130 maps its nine
    // native anchors to top offsets; +f4 is the node's local Y position.
    // Bound the shared translation by native measured bottoms, without a
    // second glyph traversal or any frame/child-position mutation.
    const height=frame.add(0x2dc).readFloat(),anchor=frame.add(0x2e0).readU32();
    const topFactors=[0,0,-1,-1,-.5,-.5,0,-1,-.5];
    if(!(height>0&&height<=65536)||anchor>=topFactors.length)return;
    const bottom=frame.add(0xf4).readFloat()+height*(1+topFactors[anchor]);
    const ends=[name,body].filter(p=>p.add(0x334).readU32()>0)
        .map(p=>p.add(0xf4).readFloat()+p.add(0x374).readS32());
    if(!ends.length||![bottom,...ends].every(Number.isFinite))return;
    const room=bottom-Math.max(...ends)-4;
    const group={name,body,parent,room,retired:false};
    logTextGroups.set(String(name),group);logTextGroups.set(String(body),group);
}
function offsetTextProjection(p) {
    const row=labels.get(String(p));
    if(row&&insetRoots.get(row.surfaceRoot)===row.surface&&row.epoch===epoch&&['ruby','layered'].includes(row.plan?.kind)) {
        projectTextInset(p,p.add(0x80).readPointer(),8);
        return;
    }
    offsetLogProjection(p);
}
function offsetLogProjection(p) {
    const lease=labelCallbacks.get(String(p)),group=logTextGroups.get(String(p));
    if(!lease||lease.depth!==1||lease.projection||!group||group.retired||!enabled||failed||
            !['annotation','bilingual'].includes(renderMode))return;
    if(![group.name,group.body].some(label=>{
        const row=labels.get(String(label));
        return row?.epoch===epoch&&['ruby','layered'].includes(row.plan?.kind);
    }))return;
    const delta=Math.max(0,Math.min(8,group.room-Math.max(0,bilingualOffsetY)));
    projectTextInset(p,group.parent,delta);
}
function projectTextInset(p,parent,delta) {
    const lease=labelCallbacks.get(String(p));
    if(!delta||parent.isNull()||!lease||lease.depth!==1||lease.projection||!enabled||failed||
            !['annotation','bilingual'].includes(renderMode))return;
    // Update projects glyphs through label+08 after layout_ready. Temporarily
    // translate that matrix, then restore it on Update return: unchanged
    // frames, repeated parses and controller reuse never accumulate offsets.
    const offsets=[0x38,0x3c,0x40],axis=[0x18,0x1c,0x20];
    const original=offsets.map(off=>p.add(off).readFloat()),direction=axis.map(off=>parent.add(off).readFloat());
    if(![...original,...direction].every(Number.isFinite))return;
    lease.projection={p,offsets,original};
    offsets.forEach((off,i)=>p.add(off).writeFloat(original[i]+direction[i]*delta));
}
function restoreTextProjection(lease) {
    const saved=lease?.projection;if(!saved)return;
    saved.offsets.forEach((off,i)=>saved.p.add(off).writeFloat(saved.original[i]));
    lease.projection=null;
}
function newLogContributions() {
    const owner=logOwner();
    return {owner:owner?String(owner):null,epoch:logOrigins.epoch,parts:[],invalid:false};
}
function captureLogPart(frame,slot,input) {
    if(!frame||frame.invalid)return;
    try {
        const owner=logOwner();
        // The two native append loops use different index registers, but both
        // pass the actual ring text in RDX. Derive its slot from that pointer;
        // the alignment and exact pointer checks below still validate it.
        if(owner&&slot===null)slot=input.sub(owner.add(0x160550)).toInt32()/0x18c;
        if(!owner||frame.owner!==String(owner)||frame.epoch!==logOrigins.epoch||
                !Number.isInteger(slot)||slot<0||slot>=1600||frame.parts.length>=1600)throw Error('Invalid log contribution');
        const record=owner.add(0x1604ec+slot*0x18c);
        if(!record.add(0x64).equals(input))throw Error('Unrelated log source pointer');
        const entry=logOrigins.entries.get(slot),stamp=logStamp(record);
        const speaker=record.add(4).readUtf8String();
        if(RuntimeText.byteLength(speaker)>=0x60)throw Error('Invalid log speaker');
        frame.parts.push({slot,entry,stamp,speaker,marker:record.readU32(),text:input.readUtf8String()});
    }catch(_){frame.invalid=true;}
}
function logContributionsIdentity(frame,source) {
    const owner=logOwner();
    if(!frame||frame.invalid||!owner||frame.owner!==String(owner)||frame.epoch!==logOrigins.epoch||!frame.parts.length)return null;
    if(frame.parts.map(v=>v.text).join('')!==source)return null;
    let identity=null,key=null,missing=false;
    for(const part of frame.parts) {
        const entry=logOrigins.entries.get(part.slot);
        const stamp=logStamp(owner.add(0x1604ec+part.slot*0x18c));
        if(entry!==part.entry||part.stamp!==stamp||entry&&entry.stamp!==stamp)return null;
        if(!entry){missing=true;continue;}
        const current=entry.origin.identity,currentKey=JSON.stringify(current);
        if(key!==null&&key!==currentKey)return null;
        identity=current;key=currentKey;
    }
    if(!missing)return identity?.source===source?identity:null;
    // The native writer persists the script's message marker at record+0.
    // Reconstruct a physical call ID only through the compiled marker index;
    // equal source/target strings never merge independent calls. Every split
    // record still belongs to the same owner, generation and intact payload.
    const first=frame.parts[0];
    if(frame.parts.some(part=>part.marker!==first.marker||part.speaker!==first.speaker))return null;
    const restored=scriptIdentities?.historyMarkerIdentity?.(first.marker,first.speaker,source);
    if(identity&&(!restored||restored.recordKey!==identity.recordKey))return null;
    return restored||null;
}
function logContributionsSpeaker(frame,source) {
    const owner=logOwner();
    if(!frame||frame.invalid||!owner||frame.owner!==String(owner)||frame.epoch!==logOrigins.epoch||!frame.parts.length)return undefined;
    if(frame.parts.map(part=>part.text).join('')!==source)return undefined;
    const speaker=frame.parts[0].speaker;
    for(const part of frame.parts) {
        const record=owner.add(0x1604ec+part.slot*0x18c);
        if(part.speaker!==speaker||record.add(4).readUtf8String()!==speaker||record.add(0x64).readUtf8String()!==part.text)return undefined;
    }
    return speaker;
}
function rememberLogController(frame) {
    try {
        const {controller,body,slot,parts}=frame||{};
        if(!controller||!body||!parts||parts.invalid||!parts.parts.length||
                controller.add(0x38).readS32()!==slot||!controller.add(0x18).readPointer().equals(body))return;
        const owner=logOwner();
        if(!owner||parts.owner!==String(owner)||parts.epoch!==logOrigins.epoch)return;
        const key=String(controller);
        // The game owns a fixed controller pool. Refuse unbounded pointer
        // churn without disabling ordinary translation.
        if(!logControllers.has(key)&&logControllers.size>=4096){logOriginStats.rejected++;return;}
        logControllers.set(key,{controller,body,slot,owner:parts.owner,epoch:parts.epoch,
            source:parts.parts.map(part=>part.text).join(''),
            parts:parts.parts.map(part=>({slot:part.slot,text:part.text,speaker:part.speaker,marker:part.marker,
                stamp:part.stamp,entry:part.entry}))});
    }catch(_){logOriginStats.rejected++;}
}
function currentLogControllerParts(binding) {
    const owner=logOwner();
    if(!binding||!owner||binding.owner!==String(owner)||binding.epoch!==logOrigins.epoch||
            binding.controller.add(0x38).readS32()!==binding.slot||
            !binding.controller.add(0x18).readPointer().equals(binding.body))return null;
    const current=newLogContributions();
    for(const saved of binding.parts) {
        const record=owner.add(0x1604ec+saved.slot*0x18c);
        captureLogPart(current,saved.slot,record.add(0x64));
    }
    if(current.invalid||current.parts.length!==binding.parts.length)return null;
    for(let i=0;i<current.parts.length;i++)
        if(current.parts[i].slot!==binding.parts[i].slot||current.parts[i].text!==binding.parts[i].text||
                current.parts[i].speaker!==binding.parts[i].speaker||current.parts[i].stamp!==binding.parts[i].stamp||
                current.parts[i].entry!==binding.parts[i].entry)return null;
    return current;
}
function reconcileLogController(controller) {
    const binding=logControllers.get(String(controller));
    const owner=logOwner();
    if(!binding||!owner||binding.owner!==String(owner)||binding.epoch!==logOrigins.epoch||
            binding.controller.add(0x38).readS32()!==binding.slot||
            !binding.controller.add(0x18).readPointer().equals(binding.body)||
            readText(binding.body)!==binding.source)return;
    const parts=currentLogControllerParts(binding);
    if(!parts)return;
    const source=parts.parts.map(part=>part.text).join('');
    if(source!==binding.source)return;
    const thread=Process.getCurrentThreadId(),stack=logPresentFrames.get(thread)||[];
    const frame={slot:binding.slot,body:binding.body,parts};stack.push(frame);logPresentFrames.set(thread,stack);
    try {
        observeNativeText(binding.body,row=>identifyInput(row,binding.body.add(0x318).readPointer(),
            base.add(REPORT.native.log_text_return.rva)),true);
    }finally {
        if(stack.at(-1)===frame)stack.pop();else resetLogOrigins();
        if(!stack.length)logPresentFrames.delete(thread);
    }
}
function logInputProvenance(row,input,caller) {
    if(!logOrigins)return null;
    try {
        const thread=Process.getCurrentThreadId(),present=logPresentFrames.get(thread)?.at(-1);
        if(present&&REPORT.native.log_name_return&&caller?.equals(base.add(REPORT.native.log_name_return.rva))&&
                Number.isInteger(present.slot)&&present.slot>=0&&present.slot<1600) {
            const owner=logOwner(),name=owner?.add(0x1604f0+present.slot*0x18c).readUtf8String();
            if(name&&name===row.original&&RuntimeText.byteLength(name)<0x60) {
                const parts=present.parts,source=parts?.parts.map(part=>part.text).join('');
                if(logContributionsSpeaker(parts,source)!==name)return null;
                return {kind:'name',speaker:name,identity:logContributionsIdentity(parts,source)};
            }
            return null;
        }
        let parts=null;
        if(present&&caller?.equals(base.add(REPORT.native.log_text_return.rva))&&row.pointer.equals(present.body))parts=present.parts;
        const measure=logMeasureFrames.get(thread)?.at(-1);
        if(measure?.record&&row.pointer.equals(measure.name)&&input.equals(measure.record.add(0x20).readPointer())) {
            const pieces=logRows.get(String(measure.owner))?.get(String(measure.record));
            const speaker=pieces&&logContributionsSpeaker(pieces,pieces.parts.map(part=>part.text).join(''));
            return speaker&&speaker===row.original?{kind:'name',speaker,
                identity:logContributionsIdentity(pieces,pieces.parts.map(part=>part.text).join(''))}:null;
        }
        if(measure?.record&&row.pointer.equals(measure.body)&&input.equals(measure.record.add(8).readPointer()))
            parts=logRows.get(String(measure.owner))?.get(String(measure.record));
        if(parts) {
            const speaker=logContributionsSpeaker(parts,row.original);
            if(speaker!==undefined)return {identity:logContributionsIdentity(parts,row.original),speaker,kind:'body'};
        }
    }catch(_){logOriginStats.rejected++;}
    return null;
}
for(const point of ['log_owner_destroyed','log_owner_created'])if(REPORT.native[point])
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(){resetLogOrigins();}});
if(logOrigins&&REPORT.native.log_write&&REPORT.native.log_write_commit) {
    Interceptor.attach(base.add(REPORT.native.log_write.rva),{
        onEnter(args){
            this.thread=Process.getCurrentThreadId();
            const stack=logWriteFrames.get(this.thread)||[],dialogue=dialogueFrames.get(this.thread)?.at(-1);
            this.frame={owner:args[0],origin:null};
            stack.push(this.frame);logWriteFrames.set(this.thread,stack);
            try {
                const owner=logOwner(),origin=dialogue?.outputs.get(String(args[1]));
                if(owner?.equals(args[0])&&origin&&args[1].readUtf8String()===origin.source)this.frame.origin=origin;
            }catch(_){logOriginStats.rejected++;}
        },
        onLeave(){
            const stack=logWriteFrames.get(this.thread);
            if(stack?.at(-1)===this.frame)stack.pop();else resetLogOrigins();
            if(!stack?.length)logWriteFrames.delete(this.thread);
        }
    });
    for(const point of ['log_write_commit','log_write_append_commit'])if(REPORT.native[point])
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(){
        const frame=logWriteFrames.get(Process.getCurrentThreadId())?.at(-1);
        try {
            const owner=logOwner();
            if(!owner||!frame||!frame.owner.equals(owner)||!this.context.rbp.equals(owner)){
                resetLogOrigins();return;
            }
            const record=this.context.rcx.add(-0x180);
            const delta=record.sub(owner.add(0x1604ec)).toInt32(),slot=delta/0x18c;
            if(!Number.isInteger(slot)||slot<0||slot>=1600||!owner.add(0x1604ec+slot*0x18c).equals(record)){
                resetLogOrigins();return;
            }
            logOrigins.commit(slot,logStamp(record),frame.origin);
            logOriginStats.commits++;if(frame.origin)logOriginStats.withIdentity++;
        }catch(_){resetLogOrigins();logOriginStats.rejected++;}
    }});
}
if(logOrigins&&REPORT.native.log_record_bind)Interceptor.attach(base.add(REPORT.native.log_record_bind.rva),{
    onEnter(args){
        this.thread=Process.getCurrentThreadId();
        const stack=logPresentFrames.get(this.thread)||[];
        this.frame={controller:args[0],slot:args[1].toInt32(),body:null,parts:null};
        try {this.frame.body=args[0].add(0x18).readPointer();this.frame.parts=newLogContributions();}
        catch(_){logOriginStats.rejected++;}
        stack.push(this.frame);logPresentFrames.set(this.thread,stack);
    },
    onLeave(){
        const stack=logPresentFrames.get(this.thread);
        if(stack?.at(-1)===this.frame){
            rememberLogController(this.frame);
            try{rememberLogTextGroup(this.frame.controller);}catch(e){fail(e);}
            stack.pop();
        }else resetLogOrigins();
        if(!stack?.length)logPresentFrames.delete(this.thread);
    }
});
if(logOrigins&&REPORT.native.log_record_activate)Interceptor.attach(base.add(REPORT.native.log_record_activate.rva),{
    onEnter(args){try{reconcileLogController(args[0]);}catch(e){fail(e);}}
});
for(const [point,multiple] of [['log_present_append',true],['log_present_single',false]])if(REPORT.native[point])
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(){
        const frame=logPresentFrames.get(Process.getCurrentThreadId())?.at(-1);
        if(frame?.parts)captureLogPart(frame.parts,multiple?null:frame.slot,multiple?this.context.rdx:this.context.rdi);
    }});
if(logOrigins&&REPORT.native.log_rows_build)Interceptor.attach(base.add(REPORT.native.log_rows_build.rva),{
    onEnter(args){
        this.thread=Process.getCurrentThreadId();
        const stack=logBuildFrames.get(this.thread)||[];
        this.frame={owner:args[0],rows:new Map(),parts:null};
        logRows.delete(String(args[0]));stack.push(this.frame);logBuildFrames.set(this.thread,stack);
    },
    onLeave(){
        const stack=logBuildFrames.get(this.thread);
        if(stack?.at(-1)===this.frame){
            stack.pop();if(logRows.size>=16)logRows.clear();logRows.set(String(this.frame.owner),this.frame.rows);
        }else resetLogOrigins();
        if(!stack?.length)logBuildFrames.delete(this.thread);
    }
});
for(const point of ['log_row_start','log_row_append','log_row_single','log_row_commit'])if(REPORT.native[point])
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(){
        const frame=logBuildFrames.get(Process.getCurrentThreadId())?.at(-1);
        if(!frame)return;
        try {
            if(point==='log_row_start')frame.parts=newLogContributions();
            else if(point==='log_row_commit') {
                if(frame.rows.size>=1600)throw Error('Invalid log row count');
                frame.rows.set(String(this.context.rbx),frame.parts);frame.parts=null;
            }else if(frame.parts)captureLogPart(frame.parts,
                point==='log_row_append'?null:this.context.r15.toInt32(),
                point==='log_row_append'?this.context.rdx:this.context.rdi);
        }catch(_){frame.parts=null;logOriginStats.rejected++;}
    }});
// Quest history builds a complete paragraph before splitting it into labels.
// Keep that exact source only for the verified synchronous builder/callsite;
// isolated lines must never be matched against an unrelated quest paragraph.
if(REPORT.native.quest_builder&&REPORT.native.quest_paragraph_ready&&ParagraphFactory) {
    Interceptor.attach(base.add(REPORT.native.quest_builder.rva),{
        onEnter(){
            const thread=Process.getCurrentThreadId(),stack=questFrames.get(thread)||[];
            this.questThread=thread;this.questFrame={source:null,slots:[],next:0};
            stack.push(this.questFrame);questFrames.set(thread,stack);
        },
        onLeave(){
            const stack=questFrames.get(this.questThread);
            if(stack?.at(-1)===this.questFrame)stack.pop();
            if(!stack?.length)questFrames.delete(this.questThread);
        }
    });
    Interceptor.attach(base.add(REPORT.native.quest_paragraph_ready.rva),{
        onEnter(){
            const frame=questFrames.get(Process.getCurrentThreadId())?.at(-1);
            if(!frame)return;
            try {
                const source=this.context.rbp.add(0x760).readUtf8String();
                if(TextFactory.byteLength(source)>8192)return;
                const slots=ParagraphFactory.slots(source);
                if(slots.length>256)return;
                frame.source=source;frame.slots=slots;frame.next=0;
            }catch(_){frame.source=null;}
        }
    });
}
function questLineContext(incoming,caller) {
    if(!REPORT.native.quest_line_return||!caller?.equals(base.add(REPORT.native.quest_line_return.rva)))return null;
    const frame=questFrames.get(Process.getCurrentThreadId())?.at(-1);
    if(!frame?.source)return null;
    const index=frame.next++;
    if(frame.slots[index]?.text!==incoming){frame.source=null;return null;}
    return {source:frame.source,index};
}
function identifyInput(row,input,caller) {
    row.book=nativeBooks?.input(input,row.original,caller)||null;
    nativeBooks?.bind(row.pointer,row.book);
    row.logSpeaker=null;
    row.logKind=null;
    row.logIdentity=null;
    row.paragraph=questLineContext(row.original,caller);
    const frame=dialogueFrames.get(Process.getCurrentThreadId())?.at(-1);
    const origin=frame?.outputs.get(String(input));
    if(origin&&origin.source===row.original){row.scriptIdentity=origin.identity;identityHits++;}
    row.scriptPointer=ownedNameIdentity(input,row.original)||row.scriptPointer;
    const needsIdentity=!resolver||!Object.hasOwn(resolver.model.pairs,row.original);
    const started=needsIdentity?Date.now():undefined;
    // Preserve copied provenance even when today's global translation is unique;
    // the same visible row can survive a language-model reload.
    if(!row.scriptIdentity){
        const origin=logInputProvenance(row,input,caller);
        if(origin?.identity){
            if(origin.kind==='name')row.logIdentity=origin.identity;
            else row.scriptIdentity=origin.identity;
            identityHits++;logOriginStats.matched++;
        }
        row.logSpeaker=origin?.speaker||null;
        row.logKind=origin?.kind||null;
    }
    if(needsIdentity&&!row.scriptIdentity&&tableIdentities) {
        const entry=tableIdentities.select(input,row.original);
        if(entry){row.tableIdentity=entry.key;tableIdentityHits++;}
    }
    if(needsIdentity&&!row.scriptIdentity&&!row.scriptPointer&&!row.tableIdentity&&scriptIdentities) {
        const entry=scriptIdentities.pointerSelect(input,row.original);
        if(entry){row.scriptPointer=entry.key;identityHits++;}
    }
    recordTiming('pointerIdentity',started);
}
// Only the MessageLog's hidden measuring template uses this cache. The game
// clones all visible rows before entering this loop. Its final row setters,
// native line/glyph state and temporary-string destructor tail stay intact.
function logMeasureKey(p,input) {
    if(!isLabel(p))return null;
    const original=input.isNull()?'':input.readUtf8String();
    if(original.length>16384)return null;
    const current=labels.get(String(p));
    if(current&&current.displayed!==current.original&&original===current.displayed)return null;
    const row={pointer:p,original,displayed:original,epoch:-1};
    identifyInput(row,input,null);
    const wanted=wantedText(row,false);
    // Icon callbacks can depend on the current device/layout resources. Their
    // generation is not part of the font epoch, so retain native measurement.
    if(/<I\d+>/.test(original+wanted+JSON.stringify(row.plan.layers||[])))return null;
    const bytes=p.add(0x2d8).readByteArray(0x40),style=Array.from(new Uint8Array(bytes));
    let font='';
    if(REPORT.font_manager_global) {
        const manager=base.add(REPORT.font_manager_global).readPointer();
        const index=new DataView(bytes).getUint32(0x28,true),count=manager.add(0x10).readU32();
        if(count>256||index>=count)return null;
        const face=manager.add(8).readPointer().add(index*8).readPointer();
        font=[String(manager),String(face),face.add(0x28).readU32()];
    }
    // Layer payloads are not contained in the placeholder's wanted bytes.
    // Include actual resolved output, not merely source text or a hash.
    return [original,wanted,row.plan.kind,JSON.stringify(row.plan.layers||[]),style,font,
        [row.reserveRubyHeight,row.preservePrimaryLayout,row.extendLineSpacing],[annotationScale,rubyScale,rubyLineGap]];
}
function logMeasuredPlanMatches(p,expected) {
    const row=labels.get(String(p));
    return row&&row.original===expected[0]&&row.displayed===expected[1]&&readText(p)===expected[1]&&
        row.plan.kind===expected[2]&&JSON.stringify(row.plan.layers||[])===expected[3]&&
        JSON.stringify([row.reserveRubyHeight,row.preservePrimaryLayout,row.extendLineSpacing])===JSON.stringify(expected[6])&&
        JSON.stringify(Array.from(new Uint8Array(p.add(0x2d8).readByteArray(0x40))))===JSON.stringify(expected[4]);
}
function installLogMeasureGate(callback) {
    const entry=base.add(REPORT.native.log_measure_row.rva);
    // Interceptor callbacks restore general registers, but changing their RIP
    // does not redirect the relocated instruction stream. Use an explicit,
    // version-verified branch gate instead. RAX and flags are dead at all four
    // continuations; the displaced RBX load is executed on every path.
    const original=[0x48,0x8b,0x9c,0x24,0xc0,0,0,0];
    if(Process.arch!=='x64'||JSON.stringify(Array.from(new Uint8Array(entry.readByteArray(8))))!==JSON.stringify(original))
        throw Error('Unvalidated MessageLog branch instruction');
    const gate=Memory.alloc(Process.pageSize,{near:entry,maxDistance:0x40000000});
    Memory.patchCode(gate,256,writable=>{
        const writer=new X86Writer(writable,{pc:gate});
        writer.putXorRegReg('eax','eax');
        for(let i=0;i<16;i++)writer.putNop();
        writer.putMovRegRegOffsetPtr('rbx','rsp',0xc0);
        for(const [value,label] of [[1,'cached'],[2,'fixed'],[3,'name']]) {
            writer.putCmpRegI32('eax',value);writer.putJccShortLabel('je',label,'no-hint');
        }
        writer.putJmpAddress(entry.add(8));
        for(const [label,point] of [['cached','log_measure_row_end'],['fixed','log_measure_calculate'],['name','log_measure_body']]) {
            writer.putLabel(label);writer.putJmpAddress(base.add(REPORT.native[point].rva));
        }
        writer.flush();writer.dispose();
    });
    if(!Memory.protect(gate,Process.pageSize,'r-x'))throw Error('Cannot protect MessageLog branch gate');
    const listener=Interceptor.attach(gate.add(2),function(){callback.onEnter.call(this);});
    Interceptor.flush();
    if(JSON.stringify(Array.from(new Uint8Array(entry.readByteArray(8))))!==JSON.stringify(original))
        throw Error('MessageLog branch changed during installation');
    // Build the replacement off-target and check its size before modifying
    // executable bytes. The near allocation must produce exactly rel32 JMP.
    const patch=Memory.alloc(16),writer=new X86Writer(patch,{pc:entry});
    writer.putJmpAddress(gate);
    if(writer.offset!==5)throw Error('MessageLog branch is outside rel32 range');
    while(writer.offset<8)writer.putNop();
    writer.flush();writer.dispose();
    Memory.patchCode(entry,8,writable=>{
        writable.writeByteArray(patch.readByteArray(8));
    });
    return {gate,listener}; // retain executable memory for the resident lifetime
}
for(const point of ['font_reset','font_load'])if(REPORT.native[point])
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(args){
        this.fontOwner=runtimeFonts?.isManager(args[0]);
        if(this.fontOwner&&point==='font_reset')runtimeFonts.beforeReset();
        logHeightCache.clear();logNameCache.clear();logCacheBytes=0;logFontGeneration++;
    },onLeave(){if(this.fontOwner&&point==='font_load'){
        invalidateFontGeometry();runtimeFonts.loaded();
    }}});
if(REPORT.native.log_measure) Interceptor.attach(base.add(REPORT.native.log_measure.rva),{
    onEnter(args) {
        this.thread=Process.getCurrentThreadId();
        const stack=logMeasureFrames.get(this.thread)||[];
        this.frame={owner:args[0],pending:null,started:Date.now()};
        stack.push(this.frame);logMeasureFrames.set(this.thread,stack);
    },
    onLeave() {
        const stack=logMeasureFrames.get(this.thread);
        if(stack?.at(-1)===this.frame)stack.pop();else stack?.splice(0);
        if(!stack?.length)logMeasureFrames.delete(this.thread);
        logMeasureStats.runs++;logMeasureStats.totalMs+=Date.now()-this.frame.started;
    }
});
const logMeasureGate=REPORT.native.log_measure_row?installLogMeasureGate({
    onEnter() {
        this.context.rax=ptr(0);
        const frame=logMeasureFrames.get(Process.getCurrentThreadId())?.at(-1);
        if(!frame||!frame.owner.equals(this.context.r13))return;
        frame.pending=null;
        frame.record=this.context.rsp.add(0xc0).readPointer();frame.body=this.context.rdi;frame.name=this.context.rsi;
        if(!enabled||failed)return;
        try {
            const mode=frame.owner.add(0x1d4).readU32();
            if(mode===1) {
                // Active voice rows use constant 143+5, never either measure.
                this.context.rax=ptr(2);
                logMeasureStats.fixedRows++;return;
            }
            if(mode!==0)return;
            // Configuration epochs also change for tint, opacity and switching
            // back to an already measured language. Key actual parser inputs
            // instead; resource reloads still clear every stored descriptor.
            const record=this.context.rsp.add(0xc0).readPointer();
            const name=logMeasureKey(this.context.rsi,record.add(0x20).readPointer());
            const text=logMeasureKey(this.context.rdi,record.add(8).readPointer());
            if(!name||!text){logMeasureStats.fallbacks++;return;}
            const key=JSON.stringify([name,text]);
            if(key.length>131072){logMeasureStats.fallbacks++;return;}
            const height=logHeightCache.get(key);
            if(height!==undefined) {
                const descriptor=this.context.rsp.add(0xc8).readPointer();
                descriptor.add(0x14).writeS32(this.context.r14.add(0x2d8).readS32());
                descriptor.add(0x18).writeFloat(height);
                this.context.rax=ptr(1);
                logMeasureStats.hits++;return;
            }
            const nameKey=JSON.stringify(name),nameHeight=logNameCache.get(nameKey);
            frame.pending={key,epoch,generation:logFontGeneration,name,text,nameKey,nameHeight};
            frame.measuringLabels=[this.context.rsi,this.context.rdi];logMeasureStats.misses++;
            if(nameHeight!==undefined&&REPORT.native.log_measure_body) {
                this.context.rax=ptr(3);
                logMeasureStats.nameHits++;
            }
        }catch(error){frame.pending=null;logMeasureStats.fallbacks++;logMeasureStats.lastFallback=String(error).slice(0,160);}
    }
}):null;
if(REPORT.native.log_measure_row_end) Interceptor.attach(base.add(REPORT.native.log_measure_row_end.rva),{
    onEnter() {
        const frame=logMeasureFrames.get(Process.getCurrentThreadId())?.at(-1),pending=frame?.pending;
        if(!pending||!frame.owner.equals(this.context.r13))return;
        frame.pending=null;
        try {
            if(pending.nameHeight!==undefined) {
                // The native calculation used the previous hidden name label.
                // Replace only its scalar contribution, never its glyph state.
                const body=this.context.rdi,descriptor=this.context.rsp.add(0xc8).readPointer();
                const height=body.add(0x334).readU32()===0?0:
                    (Math.abs((body.add(0x374).readS32()-body.add(0x36c).readS32())|0)+body.add(0x668).readU32())>>>0;
                const f=Math.fround,name=pending.nameHeight;
                descriptor.add(0x18).writeFloat(f(f(f(f(f(height)+name)+37)+(name===0?-3:0))+5));
            }
            if(pending.epoch!==epoch||pending.generation!==logFontGeneration||failed)return;
            // The real setter remains the authority; a changed identity or
            // reentrant configuration must never publish preview dimensions.
            if(pending.nameHeight===undefined) {
                if(!logMeasuredPlanMatches(this.context.rsi,pending.name))return;
                const p=this.context.rsi;
                const contribution=p.add(0x334).readU32()===0?0:Math.fround(Math.fround(p.add(0x668).readU32())*33);
                if(contribution<=65536&&pending.nameKey.length<=4096) {
                    if(logNameCache.size>=256)logNameCache.delete(logNameCache.keys().next().value);
                    logNameCache.set(pending.nameKey,contribution);
                }
            }
            if(!logMeasuredPlanMatches(this.context.rdi,pending.text))return;
            const height=this.context.rsp.add(0xc8).readPointer().add(0x18).readFloat();
            if(!Number.isFinite(height)||height<0||height>65536)return;
            const bytes=pending.key.length*2+16;
            while(logHeightCache.size&&(logHeightCache.size>=4096||logCacheBytes+bytes>8*1024*1024)) {
                const key=logHeightCache.keys().next().value;
                logHeightCache.delete(key);logCacheBytes-=key.length*2+16;
            }
            if(!logHeightCache.has(pending.key)){logHeightCache.set(pending.key,height);logCacheBytes+=bytes;}
        }catch(_){logMeasureStats.fallbacks++;}
    }
});
labelHooks.attach(base.add(REPORT.native.set_text.rva), {onEnter(args) {
    this.row=null;this.lease=null;
    if (activeRewrite(args[0])) return;
    try {
        if (isLabel(args[0])) {
            this.lease=enterLabel(args[0]);if(!this.lease)return;
            this.started=Date.now();
            const incoming=args[1].isNull() ? '' : args[1].readUtf8String();
            let row=labels.get(String(args[0]));
            if(incoming.length>16384 && (!row || incoming!==row.displayed))throw Error('Source label text exceeds limit');
            // Some widgets re-submit their existing owned text while changing
            // layout. Do not turn our own rendered string into the raw source.
            if (row && row.displayed!==row.original && incoming===row.displayed) row.epoch=-1;
            else {
                row=remember(args[0],incoming);
                identifyInput(row,args[1],this.returnAddress);
            }
            this.renderEpoch=epoch;
            const wanted=wantedText(row);
            this.row=row;this.wanted=wanted;
            if(wanted!==incoming) {
                // The verified setter copies its input before returning.
                // Keep the allocation on this invocation until onLeave.
                this.buffer=Memory.allocUtf8String(wanted);args[1]=this.buffer;
                row.displayed=wanted;immediateWrites++;writes++;
            }
        }
    } catch(e) {fail(e);}
},onLeave() {
    try {
        if(!this.row || labels.get(String(this.row.pointer))!==this.row)return;
        if(readText(this.row.pointer)!==this.wanted)throw Error('SetText did not copy immediate text');
        this.row.displayed=this.wanted;this.row.epoch=this.renderEpoch;captureMetadata(this.row);
    }catch(e){fail(e);}finally{recordTiming('setter',this.started);leaveLabel(this.lease);}
}});
labelHooks.attach(base.add(REPORT.native.update.rva), {onEnter(args) {
    this.lease=null;
    this.pausedReveal=null;
    if (activeRewrite(args[0])) return;
    updates++;
    try {
        if(runtimeFonts){
            runtimeFonts.tick();
            const ready=runtimeFonts.isReady();
            if(ready!==fontsWereReady){fontsWereReady=ready;epoch++;}
        }
        const p=args[0];
        if (!isLabel(p)) return;
        nativeBooks?.refresh(p);
        this.lease=enterLabel(p);if(!this.lease)return;
        const row=labels.get(String(p)) || remember(p,readText(p));
        // Some constructors finish animated/ruby-disabled flags AFTER SetText.
        // Those flags change the parser and its Y origin, even at equal text
        // and font size. Reconcile once at Update, as on a hot mode switch.
        // Exclude pause (0x10): pausing must never restart the reveal lifecycle.
        if (row.epoch === epoch&&(!runtimeFonts||row.fontGeneration===fontGeneration)&&!textLayoutChanged(row,p)) return;
        // A text write bypassing SetText invalidates our remembered source.
        const current=readText(p);
        if (current !== row.displayed) {row.original=current;row.displayed=current;row.scriptIdentity=null;row.scriptPointer=null;row.tableIdentity=null;row.paragraph=null;row.logSpeaker=null;row.logKind=null;row.book=null;}
        const renderEpoch=epoch,wanted=wantedText(row);
        const replay = epoch === replayEpoch && Object.hasOwn(dictionary,row.original);
        const changed=wanted!==row.displayed||replay;
        const fontChanged=!!runtimeFonts&&row.fontGeneration!==fontGeneration&&runtimeFonts.refreshLabel(p);
        const geometry=fontChanged||(!changed&&(row.plan.kind==='ruby'||row.plan.kind==='layered'));
        // SetText's animated branch clears glyphs without reinitializing the
        // persistent parser. Snapshot BEFORE the setter, then use the game's
        // initializer to replace its stale cursor/buffer on this UI callback.
        const reveal=(changed||geometry)&&(p.add(0x2e8).readU32()&4)?{
            progress:p.add(0x378).readFloat(),total:p.add(0x334).readU32()
        }:null;
        if (wanted !== row.displayed || replay || fontChanged) {
            copyOwnedText(row,wanted);
            if(REPORT.diagnostics||replay)send({type:replay ? 'native_replay' : 'native_text', original:row.original, displayed:wanted,
                  glyphs:p.add(0x330).readU32(), fontSize:p.add(0x304).readU32(), thread:Process.getCurrentThreadId()});
        }
        if(reveal) {
            resetText(p);
            const total=p.add(0x334).readU32();
            const fraction=reveal.total>0?Math.min(1,Math.max(0,reveal.progress/reveal.total)):0;
            p.add(0x378).writeFloat(total*fraction);
            // A paused, already visible sentence still needs one redraw.
            // Restore only this pause bit after native Update; other flags
            // remain owned by the game.
            const flags=p.add(0x2e8).readU32();
            if(flags&0x10){this.pausedReveal=p;p.add(0x2e8).writeU32(flags&~0x10);}
        }
        if(changed||geometry) {
            // Frida suppresses hooks inside the nested setter/reset calls.
            // After this callback returns, native Update consumes these flags
            // in measure-then-draw order, with the same hooks as a cold setter.
            // Include changed strings, not only equal-text geometry refreshes:
            // ruby scale, layered anchors and line spacing all affect bounds.
            // Native measurement leaves the restored reveal progress intact.
            p.add(0x689).writeU8(1);
            p.add(0x688).writeU8(1);
        }
        row.epoch=renderEpoch;
        captureMetadata(row);
        row.fontGeneration=fontGeneration;
    } catch(e) {fail(e);}
},onLeave(){
    try {
        restoreTextProjection(this.lease);
        if(this.pausedReveal){const p=this.pausedReveal;p.add(0x2e8).writeU32(p.add(0x2e8).readU32()|0x10);}
    }
    catch(e){fail(e);}finally{leaveLabel(this.lease);}
}});
rpc.exports = {
    fonts(manifest) {
        if(!runtimeFonts)throw Error('This resident does not support runtime fonts');
        runtimeFonts.select(enabled);return runtimeFonts.configure(manifest);
    },
    load(model, mode, active, scale=0.9, layout={}) {
        if(!['annotation','primary','secondary','bilingual'].includes(mode))throw Error('Unknown render mode');
        if(!Number.isFinite(scale)||scale<.7||scale>1)throw Error('Annotation scale must be 0.7..1');
        const next=new TextFactory(model);
        const nextScripts=ScriptFactory?new ScriptFactory(model.script_identities,resourceHash):null;
        const nextTables=TableFactory?new TableFactory(model.table_identities,resourceHash):null;
        const nextParagraphs=ParagraphFactory?new ParagraphFactory(model,TextFactory):null;
        rpc.exports.configure({},active,scale);
        resolver=next;renderMode=mode;
        scriptIdentities=nextScripts;tableIdentities=nextTables;
        paragraphs=nextParagraphs;
        books=BooksFactory?new BooksFactory(model.books,TextFactory):null;
        activeModel=model;
        rpc.exports.style(scale,layout);
        return true;
    },
    reloadlogic(source) {
        // This channel replaces pure text factories only. A development
        // probe must never install/replace resident native callbacks here.
        // This is an accidental-instrumentation guard, not a JS sandbox.
        if(/\b(?:Interceptor|NativeFunction|NativeCallback|Memory|Process|Stalker|CModule)\b/.test(source))
            throw Error('Resident instrumentation cannot be hot-loaded; restart the game with a validated resident script');
        const factories=new Function(source+'\nreturn {RuntimeText,ScriptIdentities,TableIdentities,RuntimeParagraphs:typeof RuntimeParagraphs===\"undefined\"?null:RuntimeParagraphs,RuntimeBooks:typeof RuntimeBooks===\"undefined\"?null:RuntimeBooks};')();
        if(!activeModel)throw Error('No active model for logic update');
        const next=new factories.RuntimeText(activeModel);
        const scripts=new factories.ScriptIdentities(activeModel.script_identities,resourceHash);
        const tables=new factories.TableIdentities(activeModel.table_identities,resourceHash);
        const nextParagraphs=factories.RuntimeParagraphs?new factories.RuntimeParagraphs(activeModel,factories.RuntimeText):null;
        TextFactory=factories.RuntimeText;ScriptFactory=factories.ScriptIdentities;TableFactory=factories.TableIdentities;
        resolver=next;scriptIdentities=scripts;tableIdentities=tables;epoch++;
        ParagraphFactory=factories.RuntimeParagraphs;paragraphs=nextParagraphs;
        BooksFactory=factories.RuntimeBooks;books=BooksFactory?new BooksFactory(activeModel.books,TextFactory):null;
        return true;
    },
    style(scale,layout={}) {
        if(!Number.isFinite(scale)||scale<.7||scale>1)throw Error('Annotation scale must be 0.7..1');
        annotationScale=scale;
        layout=layout||{};
        rubyScale=Number.isFinite(layout.ruby_scale)?Math.min(1,Math.max(.5,layout.ruby_scale)):.8;
        rubyGap=Number.isFinite(layout.ruby_gap)?Math.min(8,Math.max(0,layout.ruby_gap)):3;
        rubyOffsetX=Number.isFinite(layout.ruby_offset_x)?Math.min(24,Math.max(-24,layout.ruby_offset_x)):0;
        rubyLineGap=Number.isFinite(layout.line_gap)?Math.min(24,Math.max(0,layout.line_gap)):12;
        secondaryColor=Array.isArray(layout.secondary_color)&&layout.secondary_color.length===3&&
            layout.secondary_color.every(v=>Number.isFinite(v)&&v>=0&&v<=1)?[...layout.secondary_color]:[230/255,230/255,230/255];
        secondaryOpacity=Number.isFinite(layout.secondary_opacity)?Math.min(1,Math.max(0,layout.secondary_opacity)):.9;
        bilingualOffsetY=Number.isFinite(layout.bilingual_offset_y)?Math.min(24,Math.max(-24,layout.bilingual_offset_y)):0;
        epoch++;
        return true;
    },
    select(mode,active) {
        if(!['annotation','primary','secondary','bilingual'].includes(mode))throw Error('Unknown render mode');
        if(renderMode!==mode||enabled!==!!active) {renderMode=mode;enabled=!!active;epoch++;}
        runtimeFonts?.select(enabled);
        return true;
    },
    configure(values, active, scale=1) {
        if (scale == null) scale=1; // Frida pads omitted RPC arguments with null.
        if (!Number.isFinite(scale) || scale<0.7 || scale>1) throw Error('Annotation scale must be 0.7..1');
        resolver=null;activeModel=null;scriptIdentities=null;tableIdentities=null;paragraphs=null;books=null;dictionary=Object.assign(Object.create(null),values);enabled=!!active;runtimeFonts?.select(enabled);annotationScale=scale;epoch++;return true;
    },
    disable() {if(enabled){enabled=false;epoch++;}runtimeFonts?.select(false);return true;},
    replay() {enabled=false;replayEpoch=++epoch;return true;},
    snapshot() {return [...labels.values()].map(r=>({original:r.original,displayed:r.displayed,text_key:r.textKey,scope:r.scope,
        script_identity:r.scriptIdentity,log_identity:r.logIdentity,log_kind:r.logKind,script_pointer_key:r.scriptPointer,table_identity:r.tableIdentity,presentation:r.plan?.kind,surface:r.surface,layers:r.layerBuffers?.map(v=>v.layer),...r.metadata}));},
    status() {
        const parser=nativeParser?.status();
        const measured=parser?{...timings,parse:{count:parser.count,totalMs:parser.totalMs,maxMs:parser.maxMs,over8Ms:parser.over8Ms}}:timings;
        return {enabled,failed,failureReason,runtimeFonts:runtimeFonts?.status(),timings:measured,nativeLabelTiming:nativeLabelTiming?.status(),nativeParser:parser,nativeMeasure:nativeMeasure?.status(),logMeasureStats,logOriginStats,logOriginSlots:logOrigins?.entries.size||0,logHeightCacheSize:logHeightCache.size,nativeSizeFallbacks:[...nativeSizeFallbacks.keys()],epoch,labels:labels.size,updates,writes,destroyed,threads:[...threads],
        immediateWrites,identityHits,identityMisses,tableIdentityHits,renderMode,matched:[...labels.values()].filter(r=>r.matched).length,
        modified:[...labels.values()].filter(r=>r.displayed!==r.original).length};}
};
send({type:'native_ready'});
