'use strict';
// No RPC/native calls to UI methods. RPC only changes JS configuration.
const base = Process.getModuleByName('sora_2nd.exe').base;
const labels = new Map();
const threads = new Set();
let dictionary = Object.create(null), enabled = false, epoch = 0;
let updates = 0, writes = 0, destroyed = 0, failed = false;
let failureReason=null;
const timings={identity:{count:0,totalMs:0,maxMs:0,over8Ms:0},setter:{count:0,totalMs:0,maxMs:0,over8Ms:0}};
function recordTiming(stage,start) {
    if(start===undefined)return;
    const ms=Date.now()-start,row=timings[stage];row.count++;row.totalMs+=ms;row.maxMs=Math.max(row.maxMs,ms);
    if(ms>=8)row.over8Ms++;
}
let replayEpoch = -1;
let annotationScale = 1;
const rewriteStacks=new Map(), labelCallbacks=new Map();
let rubyScale = 0.8, rubyGap = 3, rubyLineGap = 12, rubyOffsetX = 0;
let resolver=null, renderMode='annotation';
let activeModel=null;
let TextFactory=RuntimeText, ScriptFactory=typeof ScriptIdentities==='undefined'?null:ScriptIdentities;
let TableFactory=typeof TableIdentities==='undefined'?null:TableIdentities;
let immediateWrites=0;
let scriptIdentities=null,tableIdentities=null,identityHits=0,identityMisses=0,tableIdentityHits=0;
const dialogueFrames=new Map();
const resourceHash=typeof createNativeSha256==='function'?createNativeSha256():scriptSha256;
const auxiliaryContexts=new Map(), compensation=new Map();
const subtitleRoots=new Set(),layoutRoots=new Map();let scannedLayouts=false;
for (const [name, point] of Object.entries(REPORT.native)) {
    const actual = Array.from(new Uint8Array(base.add(point.rva).readByteArray(16)))
        .map(x => x.toString(16).padStart(2, '0')).join('');
    if (actual !== point.bytes) throw Error('Native runtime code changed at '+name+'; remove other probes before attaching');
}
const setter = new NativeFunction(base.add(REPORT.native.set_text.rva), 'void', ['pointer','pointer']);
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
function wantedText(row) {
    const p=row.pointer,key=translationKey(row);
    row.renderSize=p.add(0x304).readU32();
    let wanted=row.original;
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
            row.plan=useLocal?local.render(row.original,mode):resolver.render(row.original,mode,row.textKey||'',row.scope||'');
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
    const shrink=row.plan.kind==='ruby'||(row.plan.kind==='layered'&&!row.plan.layers.some(v=>v.protected));
    const hasText=text=>/[A-Za-z0-9\u00c0-\uffff]/.test(text.replace(/<[^<>]*>/g,''));
    const uncovered=row.plan.kind==='ruby'?hasText(wanted.replace(/<R>[^<>]*<\/R[^<>]*>/g,'')):
        row.plan.kind==='layered'&&wanted.split(/\r\n|\n|\\n/).some(line=>!line.includes('<R></R_>')&&hasText(line));
    // Mixed labels (e.g. chapter + difficulty) keep their native advances, so
    // shrinking the chapter cannot move the untranslated suffix horizontally.
    if(shrink&&!uncovered&&annotationScale<1) {
        const size=p.add(0x304).readU32();
        if(size<12||size>256)throw Error('Unvalidated label font size');
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
    row.layerBuffers=(row.plan.layers||[]).map(layer=>({layer:{...layer,offset:layer.offset+prefixLength},buffer:Memory.allocUtf8String(layer.text),primaryBuffer:Memory.allocUtf8String(layer.primary||row.original)}));
    if(wanted.length>32768)throw Error('Rendered text exceeds limit');
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
function annotatedOwner(p) {
    const row=ownedRow(p);return row?.plan?.kind==='ruby'?row:null;
}
function auxiliaryLayer(p,parser) {
    const row=ownedRow(p);
    if(!row || row.plan.kind!=='layered')return null;
    const current=parser.add(8).readPointer(),owned=p.add(0x318).readPointer();
    const item=row.layerBuffers.find(v=>owned.add(v.layer.offset).equals(current));
    return item ? {...item,row,parser} : null;
}
function annotationY(frame,parser,nativeY,protectedLane=false,primaryTop=0) {
    // The native measuring pass starts at (0,0) and has already applied the
    // selected ruby scale. Its bottom is a font extent, not a guessed fraction
    // of label size. Anchor to the primary's measured ink top, which may differ
    // from the parser origin on centered headings and formatted footers.
    const top=frame.add(0x17c).readS32(),bottom=frame.add(0x184).readS32();
    const origin=parser.add(4).readFloat();
    if(!Number.isFinite(origin)||!Number.isFinite(nativeY))throw Error('Invalid annotation origin');
    if(top===0x7fffffff&&bottom===-2147483648)return nativeY; // no visible glyphs
    if(top>bottom||Math.abs(top)>65536||Math.abs(bottom)>65536)throw Error('Invalid annotation bounds');
    // Original ruby/emphasis keeps its native lane. Place the added lane above
    // its native origin, without moving either original text layer.
    if(!Number.isFinite(primaryTop)||Math.abs(primaryTop)>65536)throw Error('Invalid primary top');
    const edge=protectedLane?Math.min(origin+primaryTop,nativeY):origin+primaryTop;
    return edge-bottom-rubyGap;
}
// Align owned annotations with the measured primary run's left edge.
// Only adjust the parser's temporary context
// for a tracked translated label, never a label/global setting. Layout can
// be deferred until the native Update body after our SetText has returned.
Interceptor.attach(base.add(REPORT.native.ruby_context_init.rva), {
    onEnter(args) {
        this.target = null;
        this.placement=this.returnAddress.equals(base.add(REPORT.native.ruby_place_return.rva));
        const measurement=REPORT.native.ruby_measure_return && this.returnAddress.equals(base.add(REPORT.native.ruby_measure_return.rva));
        this.baseMeasurement=REPORT.native.ruby_base_measure_return&&this.returnAddress.equals(base.add(REPORT.native.ruby_base_measure_return.rva));
        if(!this.placement && !measurement&&!this.baseMeasurement)return;
        try {
            const p = this.context.r15;
            const layer=auxiliaryLayer(p,this.context.rbx);
            if(layer) {
                this.target=args[0];this.layer=layer;
                const text=this.baseMeasurement?(layer.layer.primary||layer.row.original):layer.layer.text;
                args[1]=this.baseMeasurement?layer.primaryBuffer:layer.buffer;args[2]=ptr([...text].length);
                return;
            }
            if(this.baseMeasurement)return;
            const parent=auxiliaryContexts.get(String(this.context.rbx));
            if(parent) {this.target=args[0];this.inherited=parent;this.parent=this.context.rbx;return;}
            const row = annotatedOwner(p);
            if (!row) return;
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
                auxiliaryContexts.set(String(this.target),{factor,placement:this.placement});
                if(this.placement) {
                    const px=this.layer.parser.readFloat(),py=this.layer.parser.add(4).readFloat();
                    if(!Number.isFinite(px)||!Number.isFinite(py))throw Error('Invalid lane origin');
                    this.target.writeFloat(px+rubyOffsetX);
                    // Move only the new lane. The primary and its original
                    // ruby keep their original font, cursor and line spacing.
                    this.target.add(4).writeFloat(annotationY(this.context.rbp,this.layer.parser,
                        this.target.add(4).readFloat(),this.layer.layer.protected,this.layer.layer.primaryTop||0));
                }
                return;
            }
            if(this.inherited) {
                if(this.placement) {
                    const origin=this.parent.add(4).readFloat(),y=this.target.add(4).readFloat();
                    this.target.add(4).writeFloat(origin+(y-origin)*this.inherited.factor);
                }
                return;
            }
            if(this.placement) {
                const y=this.target.add(4).readFloat();
                if(!Number.isFinite(y))throw Error('Unvalidated ruby position');
                this.target.add(4).writeFloat(annotationY(this.context.rbp,this.context.rbx,y,false,
                    this.context.rbp.add(0x3cc).readS32()));
            }
            if (this.placement) {
                const shifted=this.baseLeft+rubyOffsetX;
                this.target.writeFloat(this.clampLeft?Math.max(0,shifted):shifted);
                if(this.clampLeft && shifted<0)
                    if(REPORT.diagnostics)send({type:'ruby_clamped', original:this.source, before:shifted, after:0});
            }
        } catch (e) { fail(e); }
    }
});
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
        const top=this.context.rbp.add(0x3cc).readS32();
        item.layer.primaryTop=top===0x7fffffff?0:top;
        for(const off of [0x3c8,0x3cc,0x3d0,0x3d4])this.context.rbp.add(off).writeS32(0);
    }catch(e){fail(e);}
}});
if(REPORT.native.ruby_compensate) Interceptor.attach(base.add(REPORT.native.ruby_compensate.rva),{onEnter(){
    try {
        const p=this.context.rbx;
        if(!auxiliaryLayer(this.context.r15,p)&&!annotatedOwner(this.context.r15))return;
        compensation.set(String(p),p.add(0x1a7).readU8());p.add(0x1a7).writeU8(1);
    }catch(e){fail(e);}
}});
if(REPORT.native.ruby_end) Interceptor.attach(base.add(REPORT.native.ruby_end.rva),{onEnter(){
    try {
        const p=this.context.rbx,k=String(p);
        if(compensation.has(k)){p.add(0x1a7).writeU8(compensation.get(k));compensation.delete(k);}
    }catch(e){fail(e);}
}});
if(REPORT.native.parse_text) Interceptor.attach(base.add(REPORT.native.parse_text.rva),{
    onEnter(args) {
        this.key=String(args[1]);this.aux=auxiliaryContexts.has(this.key);
        // Permit original ruby inside the secondary's own temporary context.
        if(this.aux)args[1].add(0x1a5).writeU8(auxiliaryContexts.get(this.key).placement?0:1);
    },
    onLeave(){if(this.aux)auxiliaryContexts.delete(this.key);}
});
if(REPORT.native.newline_prepare) Interceptor.attach(base.add(REPORT.native.newline_prepare.rva),{
    onEnter() {
        try {
            const row=ownedRow(this.context.r13);
            if(!row || !(row.plan.kind==='ruby'||(row.plan.kind==='layered'&&!row.plan.layers.some(v=>v.protected))))return;
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
                const frame=dialogueFrames.get(Process.getCurrentThreadId())?.at(-1);
                const origin=frame?.outputs.get(String(args[1]));
                if(origin&&origin.source===incoming) {row.scriptIdentity=origin.identity;identityHits++;}
                const needsIdentity=!resolver||!Object.hasOwn(resolver.model.pairs,incoming);
                if(needsIdentity&&!row.scriptIdentity&&tableIdentities) {
                    const entry=tableIdentities.select(args[1],incoming);
                    if(entry){row.tableIdentity=entry.key;tableIdentityHits++;}
                }
                if(needsIdentity&&!row.scriptIdentity&&!row.tableIdentity&&scriptIdentities) {
                    const entry=scriptIdentities.pointerSelect(args[1],incoming);
                    if(entry){row.scriptPointer=entry.key;identityHits++;}
                }
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
    if (activeRewrite(args[0])) return;
    updates++;
    try {
        const p=args[0];
        if (!isLabel(p)) return;
        this.lease=enterLabel(p);if(!this.lease)return;
        const row=labels.get(String(p)) || remember(p,readText(p));
        if (row.epoch === epoch&&row.renderSize===p.add(0x304).readU32()) return;
        // A text write bypassing SetText invalidates our remembered source.
        const current=readText(p);
        if (current !== row.displayed) {row.original=current;row.displayed=current;row.scriptIdentity=null;row.scriptPointer=null;row.tableIdentity=null;}
        const renderEpoch=epoch,wanted=wantedText(row);
        const replay = epoch === replayEpoch && Object.hasOwn(dictionary,row.original);
        if (wanted !== row.displayed || replay) {
            const buffer=Memory.allocUtf8String(wanted);
            const thread=Process.getCurrentThreadId(),stack=rewriteStacks.get(thread)||[];
            stack.push({pointer:p,text:wanted});rewriteStacks.set(thread,stack);
            try {setter(p,buffer);} finally {stack.pop();if(!stack.length)rewriteStacks.delete(thread);}
            if (readText(p) !== wanted) throw Error('SetText did not retain a copied string');
            row.displayed=wanted; writes++;
            send({type:replay ? 'native_replay' : 'native_text', original:row.original, displayed:wanted,
                  glyphs:p.add(0x330).readU32(), fontSize:p.add(0x304).readU32(), thread:Process.getCurrentThreadId()});
        }
        row.epoch=renderEpoch;
        captureMetadata(row);
    } catch(e) {fail(e);}
},onLeave(){leaveLabel(this.lease);
}});
rpc.exports = {
    load(model, mode, active, scale=0.9, layout={}) {
        if(!['annotation','primary','secondary','bilingual'].includes(mode))throw Error('Unknown render mode');
        if(!Number.isFinite(scale)||scale<.7||scale>1)throw Error('Annotation scale must be 0.7..1');
        const next=new TextFactory(model);
        const nextScripts=ScriptFactory?new ScriptFactory(model.script_identities,resourceHash):null;
        const nextTables=TableFactory?new TableFactory(model.table_identities,resourceHash):null;
        rpc.exports.configure({},active,scale);
        resolver=next;renderMode=mode;
        scriptIdentities=nextScripts;tableIdentities=nextTables;
        activeModel=model;
        rpc.exports.style(scale,layout);
        return true;
    },
    reloadlogic(source) {
        const factories=new Function(source+'\nreturn {RuntimeText,ScriptIdentities,TableIdentities};')();
        if(!activeModel)throw Error('No active model for logic update');
        const next=new factories.RuntimeText(activeModel);
        const scripts=new factories.ScriptIdentities(activeModel.script_identities,resourceHash);
        const tables=new factories.TableIdentities(activeModel.table_identities,resourceHash);
        TextFactory=factories.RuntimeText;ScriptFactory=factories.ScriptIdentities;TableFactory=factories.TableIdentities;
        resolver=next;scriptIdentities=scripts;tableIdentities=tables;epoch++;
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
        resolver=null;activeModel=null;scriptIdentities=null;tableIdentities=null;dictionary=Object.assign(Object.create(null),values);enabled=!!active;annotationScale=scale;epoch++;return true;
    },
    disable() {if(enabled){enabled=false;epoch++;}return true;},
    replay() {enabled=false;replayEpoch=++epoch;return true;},
    snapshot() {return [...labels.values()].map(r=>({original:r.original,displayed:r.displayed,text_key:r.textKey,scope:r.scope,
        script_identity:r.scriptIdentity,script_pointer_key:r.scriptPointer,table_identity:r.tableIdentity,presentation:r.plan?.kind,surface:r.surface,layers:r.layerBuffers?.map(v=>v.layer),...r.metadata}));},
    status() {return {enabled,failed,failureReason,timings,epoch,labels:labels.size,updates,writes,destroyed,threads:[...threads],
        immediateWrites,identityHits,identityMisses,tableIdentityHits,renderMode,matched:[...labels.values()].filter(r=>r.matched).length,
        modified:[...labels.values()].filter(r=>r.displayed!==r.original).length};}
};
send({type:'native_ready'});
