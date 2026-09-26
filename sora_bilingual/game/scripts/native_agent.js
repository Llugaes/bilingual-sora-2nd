'use strict';
// No RPC/native calls to UI methods. RPC only changes JS configuration.
const base = Process.getModuleByName('sora_2nd.exe').base;
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
let immediateWrites=0;
let scriptIdentities=null,tableIdentities=null,identityHits=0,identityMisses=0,tableIdentityHits=0;
const dialogueFrames=new Map();
const questFrames=new Map();
const logMeasureFrames=new Map(),logHeightCache=new Map(),logNameCache=new Map();
let logCacheBytes=0,logFontGeneration=0;
const logMeasureStats={runs:0,totalMs:0,hits:0,misses:0,nameHits:0,fixedRows:0,fallbacks:0,lastFallback:null};
const resourceHash=typeof createNativeSha256==='function'?createNativeSha256():scriptSha256;
const auxiliaryContexts=new Map(), compensation=new Map(), rubyPermissions=new Map();
const subtitleRoots=new Set(),layoutRoots=new Map();let scannedLayouts=false;
for (const [name, point] of Object.entries(REPORT.native)) {
    const actual = Array.from(new Uint8Array(base.add(point.rva).readByteArray(16)))
        .map(x => x.toString(16).padStart(2, '0')).join('');
    if (actual !== point.bytes) throw Error('Native runtime code changed at '+name+'; remove other probes before attaching');
}
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
    layoutRoots.set(String(layout),key);
    if(id===7)subtitleRoots.add(key);else subtitleRoots.delete(key);
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
    row.surface='standard';
    row.dialogueSpeaker=false;
    if(REPORT.node_names) {
        let p=row.pointer;
        const names=[];
        let subtitle=false;
        for(let i=0;i<12&&!p.isNull();i++) {
            if(subtitleRoots.has(String(p)))subtitle=true;
            const np=p.add(0x88).readPointer();
            const name=np.isNull()?'':np.readUtf8String();
            if(name.length>256)throw Error('Unvalidated node name');
            names.push(name);p=p.add(0x80).readPointer();
        }
        if(subtitle&&names[0]==='text')row.surface='subtitle';
        row.dialogueSpeaker=subtitle&&['name_text','prev_name_text'].includes(names[0]);
        if(names[0]==='name'&&names.includes('item_template'))row.scope='item_name';
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
    const row = {pointer:p, original:text, displayed:text, epoch:-1};
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
    if(enabled&&!failed) {
        if(resolver) {
            const mode=renderMode==='bilingual'?'annotation':renderMode;
            const context=(row.scriptIdentity&&scriptIdentities?scriptIdentities.lookup(row.scriptIdentity):null)||
                (row.scriptPointer&&scriptIdentities?scriptIdentities.pointerLookup(row.scriptPointer,row.original):null)||
                (row.tableIdentity&&tableIdentities?tableIdentities.lookup(row.tableIdentity,row.original):null);
            if(context&&!context.tr)context.tr=new TextFactory(context.model);
            const local=context?.tr;
            const useLocal=local&&(Object.hasOwn(local.model.pairs,row.original)||local.translate(row.original,'secondary')!==row.original);
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
    const primaryMetrics=row.plan.kind==='layered'&&/<R>|<[sS]\d+>/.test(row.original);
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
    row.preservePrimaryLayout=shrink&&Boolean(uncovered||nativeSizeFallback||primaryMetrics);
    row.extendLineSpacing=shrink&&!uncovered&&!nativeSizeFallback&&!primaryMetrics;
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
    const scaleRun=(lane,start,end,includeIcons=false)=>{
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
            if(!includeIcons&&g.kind===1){flush();continue;}
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
        if(hasPrimary)scaleRun(lane,primaryStart,primaryEnd);
        scaleRun(lane,lane.start,lane.end,true);
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
function observeNativeText(p) {
    if(activeRewrite(p)||!isLabel(p))return;
    const lease=enterLabel(p);if(!lease)return;
    try {
        const current=readText(p),existing=labels.get(String(p));
        if(existing&&existing.displayed===current)return;
        const row=existing||remember(p,current);
        row.original=current;row.displayed=current;
        row.scriptIdentity=null;row.scriptPointer=null;row.tableIdentity=null;row.paragraph=null;
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
        for(const key of ['scriptIdentity','scriptPointer','tableIdentity','paragraph'])row[key]=original[key];
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
    // A new parse may start with untranslated text/icons, so its first owned
    // run need not start at glyph zero. Rewinding the same parser to an
    // already seen run discards the previous parse and its geometry/colors.
    // Otherwise flag-0x40 log labels accumulate one more lane every frame.
    if(phase==='open') {
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
            if(this.baseMeasurement)beginAnnotationLane(p,this.context.rbx,'primary',row);
            if(this.placement)beginAnnotationLane(p,this.context.rbx,'start',row);
            const layer=auxiliaryLayer(p,this.context.rbx,row);
            if(layer) {
                this.target=args[0];this.layer=layer;
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
                return;
            }
            const x = this.target.readFloat();
            if (!Number.isFinite(x)) throw Error('Non-finite ruby placement');
            for(const offset of [0x158,0x15c]) {
                const field=this.target.add(offset),scale=field.readFloat();
                if(!Number.isFinite(scale)||scale<=0||scale>8)throw Error('Unvalidated ruby scale');
                field.writeFloat(scale*(this.inherited ? this.inherited.factor : rubyScale));
            }
            if(this.layer) {
                const factor=this.target.add(0x15c).readFloat();
                const auxiliary={factor,placement:this.placement};
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
                if(this.placement) {
                    inheritAuxiliaryIcons(this.target,this.parent,this.context.r15);
                    const origin=this.parent.add(4).readFloat(),y=this.target.add(4).readFloat();
                    this.target.add(4).writeFloat(origin+(y-origin)*this.inherited.factor);
                }
                return;
            }
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
    baseMeasurement:base.add(REPORT.native.ruby_base_measure_return.rva)
},fail);
Interceptor.attach(base.add(REPORT.native.ruby_context_init.rva),nativeMeasure?{
    onEnter:nativeMeasure.onEnter,onLeave:nativeMeasure.onLeave
}:rubyContextCallbacks);
if(REPORT.native.layout_create) Interceptor.attach(base.add(REPORT.native.layout_create.rva),{
    onLeave(value){try{registerLayout(value);}catch(e){fail(e);}}
});
if(REPORT.native.layout_release) Interceptor.attach(base.add(REPORT.native.layout_release.rva),{
    onEnter(args){const k=String(args[1]);const root=layoutRoots.get(k);if(root)subtitleRoots.delete(root);layoutRoots.delete(k);}
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
        const row=ownedRow(this.context.r15);
        beginAnnotationLane(this.context.r15,p,'end',row);
        if(!auxiliaryLayer(this.context.r15,p,row)&&row?.plan.kind!=='ruby')return;
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
        if(this.aux)args[1].add(0x1a5).writeU8(auxiliaryContexts.get(this.key).placement?0:1);
    },
    onLeave(){if(this.aux)auxiliaryContexts.delete(this.key);recordTiming('parse',this.started);}
});
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
    if (labels.delete(String(args[0]))) destroyed++;
}});
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
            if(!Object.hasOwn(scriptIdentities.scripts,signature))return;
            const functionName=vm.add(0x88).readPointer().readUtf8String();
            if(functionName.length>256)return;
            const argc=vm.add(0x70).readU32(),top=vm.add(0x64).readS32(),stack=vm.add(0x58).readPointer();
            if(argc>512||top<argc*4||top>16*1024*1024)return;
            const values=[];for(let i=0;i<argc;i++)values.push(stack.add(top-(i+1)*4).readU32());
            this.candidate={signature,blob,functionName,argumentsToken:values.join(',')};
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
            // Exact globally unambiguous text already carries a complete pair;
            // only ambiguous/context-dependent calls need resource identity.
            if(resolver&&Object.hasOwn(resolver.model.pairs,source))return;
            const {signature,blob,functionName,argumentsToken}=this.candidate;
            this.identity=scriptIdentities?.select(signature,n=>resourceHash.pointer?{pointer:blob,byteLength:n}:blob.readByteArray(n),functionName,argumentsToken)?.identity;
            if(!this.identity)return;
            this.frame.outputs.set(String(this.output),{source,identity:this.identity});
        }catch(e){identityMisses++;}finally{recordTiming('identity',started);}
    }
});
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
    row.paragraph=questLineContext(row.original,caller);
    const frame=dialogueFrames.get(Process.getCurrentThreadId())?.at(-1);
    const origin=frame?.outputs.get(String(input));
    if(origin&&origin.source===row.original){row.scriptIdentity=origin.identity;identityHits++;}
    const needsIdentity=!resolver||!Object.hasOwn(resolver.model.pairs,row.original);
    const started=needsIdentity?Date.now():undefined;
    if(needsIdentity&&!row.scriptIdentity&&tableIdentities) {
        const entry=tableIdentities.select(input,row.original);
        if(entry){row.tableIdentity=entry.key;tableIdentityHits++;}
    }
    if(needsIdentity&&!row.scriptIdentity&&!row.tableIdentity&&scriptIdentities) {
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
    Interceptor.attach(base.add(REPORT.native[point].rva),{onEnter(){
        logHeightCache.clear();logNameCache.clear();logCacheBytes=0;logFontGeneration++;
    }});
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
Interceptor.attach(base.add(REPORT.native.set_text.rva), {onEnter(args) {
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
Interceptor.attach(base.add(REPORT.native.update.rva), {onEnter(args) {
    this.lease=null;
    this.pausedReveal=null;
    if (activeRewrite(args[0])) return;
    updates++;
    try {
        const p=args[0];
        if (!isLabel(p)) return;
        this.lease=enterLabel(p);if(!this.lease)return;
        const row=labels.get(String(p)) || remember(p,readText(p));
        // Some constructors finish animated/ruby-disabled flags AFTER SetText.
        // Those flags change the parser and its Y origin, even at equal text
        // and font size. Reconcile once at Update, as on a hot mode switch.
        // Exclude pause (0x10): pausing must never restart the reveal lifecycle.
        if (row.epoch === epoch&&row.renderSize===p.add(0x304).readU32()
            &&(row.metadata?.flags&0x0c)===(p.add(0x2e8).readU32()&0x0c)) return;
        // A text write bypassing SetText invalidates our remembered source.
        const current=readText(p);
        if (current !== row.displayed) {row.original=current;row.displayed=current;row.scriptIdentity=null;row.scriptPointer=null;row.tableIdentity=null;row.paragraph=null;}
        const renderEpoch=epoch,wanted=wantedText(row);
        const replay = epoch === replayEpoch && Object.hasOwn(dictionary,row.original);
        const changed=wanted!==row.displayed||replay;
        const geometry=!changed&&(row.plan.kind==='ruby'||row.plan.kind==='layered');
        // SetText's animated branch clears glyphs without reinitializing the
        // persistent parser. Snapshot BEFORE the setter, then use the game's
        // initializer to replace its stale cursor/buffer on this UI callback.
        const reveal=(changed||geometry)&&(p.add(0x2e8).readU32()&4)?{
            progress:p.add(0x378).readFloat(),total:p.add(0x334).readU32()
        }:null;
        if (wanted !== row.displayed || replay) {
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
    } catch(e) {fail(e);}
},onLeave(){
    try {
        if(this.pausedReveal){const p=this.pausedReveal;p.add(0x2e8).writeU32(p.add(0x2e8).readU32()|0x10);}
    }
    catch(e){fail(e);}finally{leaveLabel(this.lease);}
}});
rpc.exports = {
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
        const factories=new Function(source+'\nreturn {RuntimeText,ScriptIdentities,TableIdentities,RuntimeParagraphs:typeof RuntimeParagraphs===\"undefined\"?null:RuntimeParagraphs};')();
        if(!activeModel)throw Error('No active model for logic update');
        const next=new factories.RuntimeText(activeModel);
        const scripts=new factories.ScriptIdentities(activeModel.script_identities,resourceHash);
        const tables=new factories.TableIdentities(activeModel.table_identities,resourceHash);
        const nextParagraphs=factories.RuntimeParagraphs?new factories.RuntimeParagraphs(activeModel,factories.RuntimeText):null;
        TextFactory=factories.RuntimeText;ScriptFactory=factories.ScriptIdentities;TableFactory=factories.TableIdentities;
        resolver=next;scriptIdentities=scripts;tableIdentities=tables;epoch++;
        ParagraphFactory=factories.RuntimeParagraphs;paragraphs=nextParagraphs;
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
        return true;
    },
    configure(values, active, scale=1) {
        if (scale == null) scale=1; // Frida pads omitted RPC arguments with null.
        if (!Number.isFinite(scale) || scale<0.7 || scale>1) throw Error('Annotation scale must be 0.7..1');
        resolver=null;activeModel=null;scriptIdentities=null;tableIdentities=null;paragraphs=null;dictionary=Object.assign(Object.create(null),values);enabled=!!active;annotationScale=scale;epoch++;return true;
    },
    disable() {if(enabled){enabled=false;epoch++;}return true;},
    replay() {enabled=false;replayEpoch=++epoch;return true;},
    snapshot() {return [...labels.values()].map(r=>({original:r.original,displayed:r.displayed,text_key:r.textKey,scope:r.scope,
        script_identity:r.scriptIdentity,script_pointer_key:r.scriptPointer,table_identity:r.tableIdentity,presentation:r.plan?.kind,surface:r.surface,layers:r.layerBuffers?.map(v=>v.layer),...r.metadata}));},
    status() {
        const parser=nativeParser?.status();
        const measured=parser?{...timings,parse:{count:parser.count,totalMs:parser.totalMs,maxMs:parser.maxMs,over8Ms:parser.over8Ms}}:timings;
        return {enabled,failed,failureReason,timings:measured,nativeParser:parser,nativeMeasure:nativeMeasure?.status(),logMeasureStats,logHeightCacheSize:logHeightCache.size,nativeSizeFallbacks:[...nativeSizeFallbacks.keys()],epoch,labels:labels.size,updates,writes,destroyed,threads:[...threads],
        immediateWrites,identityHits,identityMisses,tableIdentityHits,renderMode,matched:[...labels.values()].filter(r=>r.matched).length,
        modified:[...labels.values()].filter(r=>r.displayed!==r.original).length};}
};
send({type:'native_ready'});
