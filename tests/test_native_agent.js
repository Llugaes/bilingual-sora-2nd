'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const AGENT = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/native_agent.js'), 'utf8');
const RESOLVER = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_text.js'), 'utf8');
const PARAGRAPHS = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_paragraph.js'), 'utf8');
const IDENTITIES = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_identity.js'), 'utf8');

function makeRuntime(rubyCase = null, diagnostics = false, measureBackend = false) {
    const hooks = new Map();
    const messages = [];
    const allocations = [];
    let threadId = 1;
    let duringSetter=null;
    const scriptReads=[];
    const memoryCost={scalarReads:0,blockReads:0,scalarWrites:0,blockWrites:0,textReads:0};
    const measureScopes={pushes:[],pops:[]};

    class Pointer {
        constructor(address) { this.address = address; }
        add(offset) { return new Pointer(this.address + offset); }
        equals(other) { return this.address === other.address; }
        isNull() { return false; }
        toString() { return `0x${this.address.toString(16)}`; }
        toInt32() {return this.address|0;}
        readByteArray(size) {
            const bytes=new Uint8Array(size);
            if(this.address===0x10001500)bytes.set([0x48,0x8b,0x9c,0x24,0xc0,0,0,0].slice(0,size));
            return bytes.buffer;
        }
        writeByteArray(){}
    }

    class TextPointer extends Pointer {
        constructor(label) { super(label.address + 0x9000); this.label = label; }
        readUtf8String() { memoryCost.textReads++;return this.label.owned.text; }
    }

    class FieldPointer extends Pointer {
        constructor(label, offset) { super(label.address + offset); this.label = label; this.offset = offset; }
        readByteArray(size) {
            const data=new ArrayBuffer(size),view=new DataView(data);
            for(const [offset,value] of [[0x2e8,this.label.flags],[0x304,this.label.fontSize]])
                if(offset>=this.offset&&offset+4<=this.offset+size)view.setUint32(offset-this.offset,value,true);
            return data;
        }
        readPointer() {
            if(this.offset===0x680)return this.label.glyphManager;
            if(this.offset===0x88)return this.label.name ? allocate(this.label.name) : nullPointer;
            if(this.offset===0x80)return this.label.parent || nullPointer;
            if (this.offset !== 0x318) throw Error(`unexpected pointer field ${this.offset}`);
            return this.label.owned ? new TextPointer(this.label) : nullPointer;
        }
        readU32() {
            if (this.offset === 0x2e8) return this.label.flags;
            if (this.offset === 0x2ec) return this.label.textKeyHash || 0;
            if (this.offset === 0x304) return this.label.fontSize;
            if (this.offset === 0x330) return this.label.glyphs;
            if (this.offset === 0x334) return this.label.total;
            if (this.offset === 0x668) return this.label.logLines||0;
            if (this.offset === 0x41c) return this.label.revealUnits || 0;
            throw Error(`unexpected numeric field ${this.offset}`);
        }
        readS32(){if(this.offset===0x36c)return 0;if(this.offset===0x374)return this.label.logBottom||0;return this.readU32()|0;}
        readFloat() {if(this.offset===0x378)return this.label.progress;if(this.offset===0x2fc)return -12;throw Error('unexpected float field');}
        writeFloat(value) {if(this.offset===0x378){this.label.progress=value;return;}throw Error('unexpected float field');}
        writeU32(value) {if(this.offset===0x2e8){this.label.flags=value;return;}throw Error('unexpected integer field');}
        writeU8(value) {
            if (![0x688,0x689].includes(this.offset)) throw Error('unexpected dirty flag');
            this.label.dirty[this.offset]=value;
        }
    }

    class LabelPointer extends Pointer {
        constructor(address, text, glyphs = 0, fontSize = 29) {
            super(address);
            this.vtable = base.add(REPORT.vtable);
            this.owned = {text: String(text)};
            this.glyphs = glyphs;
            this.fontSize = fontSize;
            this.flags = 1;
            this.copyCount = 0;
            this.dirty={};
            this.reflows=0;
            this.progress=0;this.total=0;this.cursor=0;this.parserText=this.owned;
            this.resetCount=0;
        }
        add(offset) { return new FieldPointer(this, offset); }
        readPointer() { return this.vtable; }
        text() { return this.owned.text; }
    }

    class Utf8Buffer extends Pointer {
        constructor(address, text) { super(address); this.text = String(text); }
        readUtf8String() { return this.text; }
        isNull() { return false; }
    }
    class ScratchPointer extends Pointer {
        constructor(address,values=new Map(),offset=0) {super(address);this.values=values;this.offset=offset;}
        add(n){return new ScratchPointer(this.address+n,this.values,this.offset+n);}
        readFloat(){memoryCost.scalarReads++;return this.values.get(this.offset)??0;}
        writeFloat(v){memoryCost.scalarWrites++;this.values.set(this.offset,v);}
        readPointer(){memoryCost.scalarReads++;return this.values.get(this.offset)??nullPointer;}
        readByteArray(size){
            memoryCost.blockReads++;
            const view=new DataView(new ArrayBuffer(size));
            for(let i=0;i+4<=size;i+=4){const at=this.offset+i,value=this.values.get(at)??0;if(at===0xc0)view.setUint32(i,value,true);else view.setFloat32(i,value,true);}
            return view.buffer;
        }
        writeByteArray(bytes){
            memoryCost.blockWrites++;
            const view=new DataView(Uint8Array.from(new Uint8Array(bytes)).buffer);
            for(let i=0;i+4<=view.byteLength;i+=4)this.values.set(this.offset+i,view.getFloat32(i,true));
        }
        writePointer(v){this.values.set(this.offset,v);}
        readU8(){return this.values.get(this.offset)??0;}
        writeU8(v){this.values.set(this.offset,v);}
        writeS32(v){this.values.set(this.offset,v);}
        readS32(){return this.values.get(this.offset)??0;}
        readU32(){return this.readS32()>>>0;}
    }
    class RegionPointer extends Pointer {
        constructor(data,address=0x33000000,offset=0){super(address);this.data=data;this.offset=offset;}
        add(n){return new RegionPointer(this.data,this.address+n,this.offset+n);}
        readByteArray(n){scriptReads.push(n);if(this.offset<0||this.offset+n>this.data.length)throw Error('unmapped');return Uint8Array.from(this.data.subarray(this.offset,this.offset+n)).buffer;}
        readU32(){return this.data.readUInt32LE(this.offset);}
    }

    const base = new Pointer(0x10000000);
    const nullPointer = {
        isNull() { return true; },
        toString() { return '0x0'; },
    };
    const REPORT = {
        diagnostics,
        node_names:true,
        icon_callback_vtable:0xb18458,
        vtable: 0x500,
        native: {
            set_text: {rva: 0x100, bytes: '00000000000000000000000000000000'},
            reset_text: {rva: 0x180, bytes: '00000000000000000000000000000000'},
            measure_text: {rva: 0x190, bytes: '00000000000000000000000000000000'},
            copy_label_ready: {rva: 0x198, bytes: '00000000000000000000000000000000'},
            line_ruby_origin: {rva: 0x195, bytes: '00000000000000000000000000000000'},
            destroy: {rva: 0x200, bytes: '00000000000000000000000000000000'},
            update: {rva: 0x300, bytes: '00000000000000000000000000000000'},
            layout_ready: {rva: 0x380, bytes: '00000000000000000000000000000000'},
            ruby_context_init: {rva: 0x600, bytes: '00000000000000000000000000000000'},
            ruby_begin: {rva: 0x650, bytes: '00000000000000000000000000000000'},
            ruby_place_return: {rva: 0x700, bytes: '00000000000000000000000000000000'},
            ruby_measure_return: {rva: 0x800, bytes: '00000000000000000000000000000000'},
            ruby_base_measure_return: {rva:0x880,bytes:'00000000000000000000000000000000'},
            newline_prepare: {rva: 0x900, bytes: '00000000000000000000000000000000'},
            ruby_base_measure_end:{rva:0xa00,bytes:'00000000000000000000000000000000'},
            ruby_compensate:{rva:0xb00,bytes:'00000000000000000000000000000000'},
            ruby_end:{rva:0xc00,bytes:'00000000000000000000000000000000'},
            parse_text:{rva:0xd00,bytes:'00000000000000000000000000000000'},
            icon_callback_clone:{rva:0xd10,bytes:'00000000000000000000000000000000'},
            dialogue_popup:{rva:0xe00,bytes:'00000000000000000000000000000000'},
            dialogue_builder:{rva:0xf00,bytes:'00000000000000000000000000000000'},
            quest_builder:{rva:0x1100,bytes:'00000000000000000000000000000000'},
            quest_paragraph_ready:{rva:0x1200,bytes:'00000000000000000000000000000000'},
            quest_line_return:{rva:0x1300,bytes:'00000000000000000000000000000000'},
            log_measure:{rva:0x1400,bytes:'00000000000000000000000000000000'},
            log_measure_row:{rva:0x1500,bytes:'488b9c24c00000000000000000000000'},
            log_measure_calculate:{rva:0x1600,bytes:'00000000000000000000000000000000'},
            log_measure_body:{rva:0x1680,bytes:'00000000000000000000000000000000'},
            log_measure_row_end:{rva:0x1700,bytes:'00000000000000000000000000000000'},
            font_reset:{rva:0x1800,bytes:'00000000000000000000000000000000'},
            font_load:{rva:0x1900,bytes:'00000000000000000000000000000000'},
        },
    };

    function invoke(address, args) {
        const callback = hooks.get(String(address));
        const call={};
        if (callback) callback.onEnter.call(call,args);
        return ()=>callback?.onLeave?.call(call);
    }

    function copyIntoLabel(label, buffer) {
        // This models the native setter retaining an owned copy.  In
        // particular, it never aliases Memory.allocUtf8String's backing data.
        label.owned = {text: buffer.isNull() ? '' : String(buffer.readUtf8String())};
        label.copyCount++;
        label.total=[...label.owned.text.replace(/<[^>]*>/g,'')].length;
        // Verified native SetText (0x588a40): animated labels lose their
        // glyphs/progress, but retain the OLD parser buffer and end cursor.
        if(label.flags&4){label.glyphs=0;label.progress=0;}
    }

    function allocate(text) {
        const buffer = new Utf8Buffer(0x20000000 + allocations.length * 0x100, text);
        allocations.push(buffer);
        return buffer;
    }

    function renderRuby(label) {
        if (rubyCase && label.text().includes('<R>')) {
                const values=new Map([[0,rubyCase.x],[4,rubyCase.nativeY??0],[0x158,.375],[0x15c,.375]]);
                const field=o=>({readFloat(){return values.get(o);},writeFloat(v){values.set(o,v);}});
                const ctx = {...field(0),add:field};
                const hook = hooks.get(String(base.add(REPORT.native.ruby_context_init.rva)));
                const call = {returnAddress:base.add(rubyCase.wrongCallsite ? 0x777 : rubyCase.measurement ? 0x800 : 0x700),
                    context:{r15:rubyCase.wrongLabel ? new Pointer(123) : label,
                        rbx:{readFloat:()=> (rubyCase.baseLeft??0)+40,add:()=>({readFloat:()=>rubyCase.origin??0,readU8:()=>0}),toString:()=> '0x700000'},
                        rbp:{add:off=>({readS32:()=>({0x3c8:0,0x3cc:rubyCase.primaryTop??0,0x3d0:40,0x17c:0,0x184:rubyCase.bottom??18})[off]??0})}}};
                hook.onEnter.call(call, [ctx]);
                hook.onLeave.call(call);
                rubyCase.after = values.get(0);
                rubyCase.scale=values.get(0x158);rubyCase.y=values.get(4);
        }
    }

    // This contract harness intentionally exercises internal re-entry guards.
    // Real Frida suppresses nested hooks: cold/hot measurement must also pass
    // check_native_reentry.py, which runs production callbacks in real Frida.
    function NativeFunction(address) {
        if(address.equals(base.add(REPORT.native.icon_callback_clone.rva)))return (source,target)=>{
            target.writePointer(source.readPointer());target.add(8).writePointer(source.add(8).readPointer());return target;
        };
        if(address.equals(base.add(REPORT.native.reset_text.rva)))return label=>{
            label.resetCount++;label.cursor=0;label.parserText=label.owned;
            label.glyphs=0;label.progress=0;label.dirty[0x688]=1;
        };
        if (!address.equals(base.add(REPORT.native.set_text.rva))) throw Error('unexpected native function');
        return (label, buffer) => {
            const args=[label,buffer],leave=invoke(address,args);
            copyIntoLabel(label, args[1]);
            invoke(base.add(0x190),[label])();
            if(duringSetter){const callback=duringSetter;duringSetter=null;const saved=threadId;try{callback();}finally{threadId=saved;}}
            if (!rubyCase?.deferred) renderRuby(label);
            leave();
        };
    }

    const sandbox = {
        REPORT,
        Process: {
            arch:'x64',pageSize:4096,
            getModuleByName(name) {
                assert.equal(name, 'sora_2nd.exe');
                return {base};
            },
            getCurrentThreadId() { return threadId; },
        },
        Memory: {allocUtf8String: allocate,alloc:()=>new Pointer(0x11000000),protect:()=>true,
            patchCode:(p,n,fn)=>fn(p)},
        X86Writer:class {
            constructor(p,{pc}){this.pc=pc;this.offset=0;}
            putNop(){this.offset++;}
            putXorRegReg(){this.offset+=2;}
            putMovRegRegOffsetPtr(){} putCmpRegI32(){} putJccShortLabel(){} putLabel(){}
            putJmpAddress(target){
                // Scalar policy tests model the gate; its emitted machine code
                // is independently executed by check_native_log_measure.py.
                if(this.pc.equals(base.add(0x1500)))hooks.set(String(this.pc),hooks.get(String(target.add(2))));
                this.offset+=5;
            }
            flush(){} dispose(){}
        },
        NativeFunction,
        Interceptor: {attach(address, callback) { hooks.set(String(address),typeof callback==='function'?{onEnter:callback}:callback); },flush(){}},
        send(message) { messages.push(message); },
        rpc: {exports: {}},
        Uint8Array,
        Array,
        Object,
        Map,
        Set,
        Error,
        String,
        ptr:v=>new Pointer(v),
    };
    if(measureBackend)sandbox.createNativeMeasure=callbacks=>({
        onEnter:callbacks.onEnter,onLeave:callbacks.onLeave,
        push(thread,label,owned,factor){const token=measureScopes.pushes.length+1;measureScopes.pushes.push({thread,label:String(label),text:owned.readUtf8String(),factor,token});return token;},
        pop(thread,token){measureScopes.pops.push({thread,token});},
        status(){return {pushes:measureScopes.pushes.length,pops:measureScopes.pops.length};}
    });
    const context=vm.createContext(sandbox);
    vm.runInContext(RESOLVER+'\n'+PARAGRAPHS+'\n'+IDENTITIES+'\n'+AGENT, context, {filename: 'native_agent.js'});

    return {
        api: sandbox.rpc.exports,
        messages,
        allocations,
        scriptReads,
        memoryCost,
        measureScopes,
        fontReload(load=false){invoke(base.add(load?0x1900:0x1800),[])();},
        logMeasure(records,{mode=0,fontSize=29,flags=1,metric=72,textKeyHash=0,mismatch=false,planMismatch=false,width=900,descriptorHeight}={}) {
            const owner=new ScratchPointer(0x410000),stack=new ScratchPointer(0x420000);
            owner.values.set(0x1d4,mode);
            const name=new LabelPointer(0x430000,'',0,fontSize),body=new LabelPointer(0x440000,'',0,fontSize);
            name.name='name';body.name='text';name.flags=body.flags=flags;
            body.textKeyHash=textKeyHash;
            const window=new ScratchPointer(0x450000);window.add(0x2d8).writeS32(width);
            const begin=hooks.get(String(base.add(0x1400))),rowHook=hooks.get(String(base.add(0x1500))),end=hooks.get(String(base.add(0x1700)));
            const call={};begin?.onEnter.call(call,[owner]);
            const result={setters:0,cleanup:0,heights:[],widths:[],ids:[]},vmContext=context;
            for(let i=0;i<records.length;i++) {
                const record=new ScratchPointer(0x460000),descriptor=new ScratchPointer(0x470000);
                record.add(0x20).writePointer(allocate(records[i][0]));record.add(8).writePointer(allocate(records[i][1]));
                descriptor.writeS32(i+1);
                stack.add(0xc0).writePointer(record);stack.add(0xc8).writePointer(descriptor);
                const context={r13:owner,rsi:name,rdi:body,r14:window,rsp:stack,rip:base.add(0x1500)};
                rowHook?.onEnter.call({context});
                context.rbx=record;
                context.rip=base.add([0x1500,0x1700,0x1600,0x1680][context.rax.toInt32()]);
                if(context.rip.equals(base.add(0x1500))||context.rip.equals(base.add(0x1680))) {
                    const inputs=[[name,record.add(0x20).readPointer()],[body,record.add(8).readPointer()]];
                    for(const [p,input] of context.rip.equals(base.add(0x1680))?inputs.slice(1):inputs) {
                        const args=[p,input],leave=invoke(base.add(0x100),args);
                        copyIntoLabel(p,args[1]);invoke(base.add(0x190),[p])();leave();result.setters++;
                        p.logLines=input.readUtf8String()?input.readUtf8String().split(/\n|\\n/).length:0;
                        p.logBottom=metric+i;
                    }
                    if(mismatch)body.owned.text='Changed after preview';
                    if(planMismatch)vm.runInContext('labels.get("'+String(body)+'").plan={...labels.get("'+String(body)+'").plan,layers:[{text:"different secondary"}]};',vmContext);
                }
                if(!context.rip.equals(base.add(0x1700))) {
                    context.rip=base.add(0x1600);
                    hooks.get(String(base.add(0x1600)))?.onEnter.call({context});
                    if(!context.rip.equals(base.add(0x1700))) {
                        const nh=name.total?name.logLines*33:0,bh=body.total?body.logBottom+body.logLines:0;
                        descriptor.add(0x14).writeS32(width);
                        descriptor.add(0x18).writeFloat(mode===1?148:bh+nh+37+(nh===0?-3:0)+5);
                    }
                }
                if(descriptorHeight!==undefined)descriptor.add(0x18).writeFloat(descriptorHeight);
                end?.onEnter.call({context});
                result.heights.push(descriptor.add(0x18).readFloat());result.ids.push(descriptor.readS32());
                result.widths.push(descriptor.add(0x14).readS32());
            }
            // The native destructor tail must run even for every cache hit.
            result.cleanup=records.length;
            begin?.onLeave.call(call);
            assert.equal(sandbox.rpc.exports.status().failed,false,JSON.stringify(sandbox.rpc.exports.status()));
            return result;
        },
        dialogueSet(label,text,data,functionName,values) {
            const machine=new ScratchPointer(0x34000000),object=new ScratchPointer(0x35000000),stack=new ScratchPointer(0x36000000);
            object.values.set(0,new RegionPointer(data));machine.values.set(8,object);
            machine.values.set(0x88,allocate(functionName));machine.values.set(0x70,values.length);
            machine.values.set(0x64,values.length*4);machine.values.set(0x58,stack);
            values.forEach((v,i)=>stack.values.set((values.length-i-1)*4,v));
            const buffer=allocate(text),leaveHandler=invoke(base.add(0xe00),[]);
            const leaveBuilder=invoke(base.add(0xf00),[nullPointer,buffer,nullPointer,machine]);leaveBuilder();
            const args=[label,buffer],leaveSetter=invoke(base.add(0x100),args);
            copyIntoLabel(label,args[1]);leaveSetter();leaveHandler();
            assert.equal(buffer.text,text,'fixed-size builder output must stay unchanged');
            return buffer;
        },
        externalBuffer(label,buffer) {
            const args=[label,buffer],leave=invoke(base.add(0x100),args);copyIntoLabel(label,args[1]);leave();
        },
        markSubtitle(root){vm.runInContext('subtitleRoots.add('+JSON.stringify(String(root))+');',context);},
        parseOrigin(label,measurement=false,delta=12) {
            const parser=new ScratchPointer(label.address+0x400);parser.add(4).writeFloat(100);parser.add(0x1ab).writeU8(measurement?1:0);
            const leave=invoke(base.add(0x195),[label,parser]);
            if(!measurement)parser.add(4).writeFloat(100+delta);
            leave();
            return parser.add(4).readFloat();
        },
        compensate(label,measurement=false) {
            const parser=new ScratchPointer(0x700000);
            parser.add(4).writeFloat(100);
            parser.add(0x1ab).writeU8(measurement?1:0);
            const context={r15:label,rbx:parser};
            hooks.get(String(base.add(0xb00))).onEnter.call({context});
            if(!parser.add(0x1a7).readU8()) {
                parser.add(4).writeFloat(112);
                parser.add(0x1a7).writeU8(1);
            }
            hooks.get(String(base.add(0xc00))).onEnter.call({context});
            return {y:parser.add(4).readFloat(),flag:parser.add(0x1a7).readU8()};
        },
        rubyAllowed(label,measurement=false) {
            const parser=new ScratchPointer(0x770000),context={r15:label,rbx:parser};
            parser.add(0x1ab).writeU8(measurement?1:0);
            hooks.get(String(base.add(0x650))).onEnter.call({context});
            // 0x586f49: flag 8 suppresses the annotation body entirely.
            const allowed=!(label.flags&8);
            hooks.get(String(base.add(0xc00))).onEnter.call({context});
            return allowed;
        },
        auxiliary(label,index=0,geometry={}) {
            const row=sandbox.rpc.exports.snapshot().find(v=>v.original===label.originalForTest||v.displayed===label.text());
            const layer=row.layers[index];
            const parser=new ScratchPointer(0x700000);
            if(geometry.iconCallback){
                const callback=new ScratchPointer(0x710000);
                callback.writePointer(base.add(REPORT.icon_callback_vtable));callback.add(8).writePointer(label);
                parser.add(0x240).writePointer(callback);
            }
            parser.writeFloat(20);parser.add(4).writeFloat(geometry.origin??100);
            parser.values.set(8,label.add(0x318).readPointer().add(layer.offset));
            const frame=new ScratchPointer(0x800000);
            parser.add(0x1c).writeS32(geometry.unitStart??0);
            frame.add(0x22c).writeS32(geometry.primaryUnits??0);
            frame.add(0x17c).writeS32(0);frame.add(0x184).writeS32(geometry.bottom??18);
            for(const off of [0x3c8,0x3cc,0x3d0,0x3d4])frame.add(off).writeS32(0x7fffffff);
            const machine={r15:label,rbx:parser,rbp:frame};
            const measureContext=new ScratchPointer(0x880000),measureArgs=[measureContext,allocate(''),new Pointer(0)];
            const measureCall={returnAddress:base.add(0x880),context:machine};
            const initializer=hooks.get(String(base.add(0x600)));
            initializer.onEnter.call(measureCall,measureArgs);initializer.onLeave.call(measureCall);
            assert.equal(measureArgs[1].readUtf8String(),layer.primary);
            assert.equal(measureArgs[2].toInt32(),[...layer.primary].length);
            assert.equal(measureContext.add(0x1a9).readU8(),0,'measurement must not draw duplicate text');
            frame.add(0x3cc).writeS32(geometry.primaryTop??0);
            hooks.get(String(base.add(0xa00))).onEnter.call({context:machine});
            const init=hooks.get(String(base.add(0x600)));
            const results=[];
            for(const placement of [false,true]) {
                const child=new ScratchPointer(0x900000);
                child.writeFloat(-100);child.add(4).writeFloat(geometry.nativeY??80);
                child.add(0x158).writeFloat(.375);child.add(0x15c).writeFloat(.375);
                const call={returnAddress:base.add(placement?0x700:0x800),context:machine};
                const args=[child,allocate('_'),new Pointer(1)];
                init.onEnter.call(call,args);init.onLeave.call(call);
                const ph=hooks.get(String(base.add(0xd00))),parseCall={};
                child.add(0x1a5).writeU8(1);ph.onEnter.call(parseCall,[label,child]);
                results.push({text:args[1].readUtf8String(),count:args[2].toInt32(),
                    x:child.readFloat(),y:child.add(4).readFloat(),scale:child.add(0x158).readFloat(),
                    iconCallback:!child.add(0x240).readPointer().isNull(),
                    iconCallbackOwned:child.add(0x240).readPointer().equals?.(child.add(0x208))??false,
                    nestedRubyDisabled:child.add(0x1a5).readU8()});
                ph.onLeave.call(parseCall);
            }
            if(geometry.glyphQuads)label.glyphs=geometry.secondaryCount;
            hooks.get(String(base.add(0xb00))).onEnter.call({context:machine});
            const duringCompensation=parser.add(0x1a7).readU8();
            hooks.get(String(base.add(0xc00))).onEnter.call({context:machine});
            if(geometry.glyphQuads) {
                const array=new ScratchPointer(0xa00000),manager=new ScratchPointer(0xb00000);
                label.glyphs=geometry.glyphQuads.length;manager.values.set(0x20,array);label.glyphManager=manager;
                geometry.glyphQuads.forEach(([x,y,w,h,kind=0],i)=>{
                    const q=new ScratchPointer(0xc00000+i*0x100);
                    for(const [o,v] of [[0x38,x],[0x3c,y],[8,w],[0x1c,h],[0xc0,kind]])q.values.set(o,v);
                    array.values.set(i*8,q);
                });
            }
            return {results,duringCompensation,restoredCompensation:parser.add(0x1a7).readU8(),
                primaryX:parser.readFloat(),primaryY:parser.add(4).readFloat(),
                bounds:[0x3c8,0x3cc,0x3d0,0x3d4].map(v=>frame.add(v).readS32())};
        },
        keyTable(hash,key,source) {
            vm.runInContext('textKeys.set('+JSON.stringify(hash)+','+JSON.stringify({key,source})+');',context);
        },
        glyphLayout(label) {
            const lease=this.beginUpdate(label);
            hooks.get(String(base.add(0x380))).onEnter.call({context:{rsi:label}});
            // Native Update samples the local matrix here, before onLeave.
            const a=label.glyphManager.add(0x20).readPointer(),out=[];
            for(let i=0;i<label.glyphs;i++) {const q=a.add(i*8).readPointer();out.push([0x38,0x3c,8,0x1c].map(o=>q.add(o).readFloat()));}
            lease();return out;
        },
        glyphColors(label,values) {
            const a=label.glyphManager.add(0x20).readPointer();
            if(values)values.forEach((v,i)=>v.forEach((c,j)=>a.add(i*8).readPointer().add(0x98+j*4).writeFloat(c)));
            return Array.from({length:label.glyphs},(_,i)=>[0,1,2,3].map(j=>a.add(i*8).readPointer().add(0x98+j*4).readFloat()));
        },
        finishLayout(label) {
            hooks.get(String(base.add(REPORT.native.layout_ready.rva))).onEnter.call({context:{rsi:label}});
        },
        glyphGeometry(label) {
            const a=label.glyphManager.add(0x20).readPointer();
            return Array.from({length:label.glyphs},(_,i)=>[0x38,0x3c,8,0x1c].map(o=>a.add(i*8).readPointer().add(o).readFloat()));
        },
        capturedRuby(label,quads,primaryEnd,measurement=false) {
            this.capturedRubyRuns(label,quads,[[0,primaryEnd,quads.length]],measurement);
        },
        capturedRubyRuns(label,quads,ranges,measurement=false) {
            const parser=new ScratchPointer(0x770000),frame=new ScratchPointer(0x880000);
            parser.add(0x1ab).writeU8(measurement?1:0);
            const context={r15:label,rbx:parser,rbp:frame};
            const init=hooks.get(String(base.add(0x600)));
            const target=new ScratchPointer(0x990000);
            for(const [start,primaryEnd,end] of ranges) {
                label.glyphs=start;
                hooks.get(String(base.add(0x650))).onEnter.call({context});
                label.glyphs=primaryEnd;
                init.onEnter.call({returnAddress:base.add(0x880),context},[target]);
                init.onEnter.call({returnAddress:base.add(0x700),context},[target]);
                label.glyphs=end;
                hooks.get(String(base.add(0xb00))).onEnter.call({context});
                hooks.get(String(base.add(0xc00))).onEnter.call({context});
            }
            label.glyphs=quads.length;
            const array=new ScratchPointer(0xaa0000),manager=new ScratchPointer(0xbb0000);
            manager.values.set(0x20,array);label.glyphManager=manager;
            quads.forEach(([x,y,w,h,kind=0],i)=>{
                const q=new ScratchPointer(0xcc0000+i*0x100);
                for(const [o,v] of [[0x38,x],[0x3c,y],[8,w],[0x1c,h],[0xc0,kind]])q.values.set(o,v);
                array.values.set(i*8,q);
            });
        },
        newline(label,bottom) {
            const call={context:{r13:label,rsi:new ScratchPointer(0x700000),r12:new Pointer(bottom)}};
            hooks.get(String(base.add(REPORT.native.newline_prepare.rva))).onEnter.call(call);
            return call.context.r12.address;
        },
        label(address, text, glyphs, fontSize) { return new LabelPointer(address, text, glyphs, fontSize); },
        questBegin(currentThread=1) {
            threadId=currentThread;
            const call={};hooks.get(String(base.add(REPORT.native.quest_builder.rva))).onEnter.call(call);
            return call;
        },
        questParagraph(source,currentThread=1) {
            threadId=currentThread;
            const rbp={add(offset) {assert.equal(offset,0x760);return allocate(source);}};
            hooks.get(String(base.add(REPORT.native.quest_paragraph_ready.rva))).onEnter.call({context:{rbp}});
        },
        questLine(label,text,currentThread=1,returnAddress=base.add(REPORT.native.quest_line_return.rva)) {
            threadId=currentThread;
            const buffer=allocate(text),args=[label,buffer],call={returnAddress};
            const hook=hooks.get(String(base.add(REPORT.native.set_text.rva)));
            hook.onEnter.call(call,args);copyIntoLabel(label,args[1]);hook.onLeave.call(call);
            return buffer;
        },
        questEnd(call,currentThread=1) {
            threadId=currentThread;hooks.get(String(base.add(REPORT.native.quest_builder.rva))).onLeave.call(call);
        },
        laneCount(label) {
            return vm.runInContext('labels.get('+JSON.stringify(String(label))+')?.glyphLanes?.length ?? 0',context);
        },
        repeatOwnedRubyParse(label,rounds,primaryStart=1) {
            const parser=new ScratchPointer(0xd10000),frame=new ScratchPointer(0xd20000),context={r15:label,rbx:parser,rbp:frame};
            parser.writeFloat(100);parser.add(4).writeFloat(80);
            frame.add(0x3c8).writeS32(0);frame.add(0x3d0).writeS32(50);
            const begin=hooks.get(String(base.add(REPORT.native.ruby_begin.rva))),init=hooks.get(String(base.add(REPORT.native.ruby_context_init.rva))),
                compensate=hooks.get(String(base.add(REPORT.native.ruby_compensate.rva))),end=hooks.get(String(base.add(REPORT.native.ruby_end.rva)));
            for(let i=0;i<rounds;i++) {
                label.glyphs=primaryStart;begin.onEnter.call({context});
                label.glyphs=primaryStart+2;
                const target=new ScratchPointer(0xd30000);target.add(0x158).writeFloat(.375);target.add(0x15c).writeFloat(.375);
                const call={returnAddress:base.add(REPORT.native.ruby_place_return.rva),context},args=[target,allocate(''),new Pointer(1)];
                init.onEnter.call(call,args);init.onLeave.call(call);
                label.glyphs=primaryStart+3;compensate.onEnter.call({context});end.onEnter.call({context});
            }
        },
        setGlyphQuads(label,quads) {
            const array=new ScratchPointer(0xd40000),manager=new ScratchPointer(0xd50000);manager.values.set(0x20,array);label.glyphManager=manager;label.glyphs=quads.length;
            quads.forEach(([x,y,w,h,kind=0],i)=>{
                const q=new ScratchPointer(0xd60000+i*0x100);
                for(const [o,v] of [[0x38,x],[0x3c,y],[8,w],[0x1c,h],[0xc0,kind]])q.values.set(o,v);
                array.values.set(i*8,q);
            });
        },
        externalSet(label, text, currentThread=1) {
            threadId=currentThread;
            const buffer = allocate(text);
            const args=[label,buffer],leave=invoke(base.add(REPORT.native.set_text.rva),args);
            copyIntoLabel(label, args[1]);
            leave();
            return buffer;
        },
        inlinedSet(label,text) {
            copyIntoLabel(label,allocate(text));
            invoke(base.add(0x190),[label])();
            return label.text(); // Native measurement consumes this immediately.
        },
        cloneLabel(source,address) {
            // Native copy constructor copies owned UTF-8, then measures before
            // the first Update; it never goes through SetText.
            const target=new LabelPointer(address,source.text(),0,source.fontSize);
            target.flags=source.flags;target.textKeyHash=source.textKeyHash;
            hooks.get(String(base.add(0x198)))?.onEnter.call({context:{rdi:target,rbx:source}});
            invoke(base.add(0x190),[target])();
            return target;
        },
        update(label, currentThread = 1) {
            threadId = currentThread;
            const leave=invoke(base.add(REPORT.native.update.rva), [label]);
            if(label.dirty[0x689]) {
                invoke(base.add(0x190),[label])();
                label.reflows++;label.dirty[0x689]=0;
            }
            if((label.flags&4)&&!(label.flags&0x10)&&label.dirty[0x688]) {
                const count=Math.min(label.total,Math.floor(label.progress));
                if(label.parserText===label.owned&&count>label.cursor){label.glyphs+=count-label.cursor;label.cursor=count;}
            }
            label.dirty[0x688]=0;
            if (rubyCase?.deferred) renderRuby(label);
            leave();
        },
        duringSetter(callback){duringSetter=callback;},
        beginUpdate(label,currentThread=1){threadId=currentThread;return invoke(base.add(REPORT.native.update.rva),[label]);},
        destroy(label) { invoke(base.add(REPORT.native.destroy.rva), [label]); },
    };
}

test('cloned annotated templates inherit the raw source before their first measurement',()=>{
    const r=makeRuntime();
    r.api.load({pairs:{Source:['Primary','Secondary']},plain_pairs:{Source:['Primary','Secondary']}},'annotation',true,.8,{ruby_scale:.6});
    const template=r.label(0x3910,'Source',0,24);r.externalSet(template,'Source');
    const copy=r.cloneLabel(template,0x3920);
    const row=r.api.snapshot().at(-1);
    assert.equal(row.original,'Source');assert.equal(row.presentation,'ruby');
    assert.equal(copy.text(),template.text());
    r.api.select('primary',true);r.update(copy);
    assert.equal(copy.text(),'Primary');
    r.api.select('annotation',true);r.update(copy);
    assert.equal(copy.text(),template.text());
    // Source templates can remain hidden with an older mode/style. Re-render
    // their new instance using the CURRENT style, never reverse-parse ruby.
    r.api.style(.9,{ruby_scale:.5});
    const another=r.cloneLabel(template,0x3930);
    assert.match(another.text(),/^<s22>/);
    assert.equal(r.api.snapshot().at(-1).original,'Source');
    r.api.select('primary',true);
    const primaryCopy=r.cloneLabel(template,0x3940);
    assert.equal(primaryCopy.text(),'Primary');
    assert.equal(r.api.status().failed,false);
});

test('copying native ruby or an untracked template does not invent a reversible source',()=>{
    const r=makeRuntime();r.api.load({pairs:{}},'annotation',true,.8);
    const original='<R>native</Rreading>';
    const untracked=r.label(0x3950,original);
    assert.equal(r.cloneLabel(untracked,0x3960).text(),original);
    r.externalSet(untracked,original);
    const tracked=r.cloneLabel(untracked,0x3970);
    r.api.select('primary',true);r.update(tracked);
    assert.equal(tracked.text(),original);assert.equal(r.api.status().failed,false);
});

test('external setter refreshes source and native setter copies its buffer', () => {
    const runtime = makeRuntime();
    const label = runtime.label(0x4000, 'raw');
    runtime.externalSet(label, 'raw');
    runtime.api.configure({raw: 'translated'}, true);
    runtime.update(label);
    const translationBuffer = runtime.allocations.at(-1);
    assert.equal(label.text(), 'translated');
    assert.notStrictEqual(label.owned, translationBuffer);
    translationBuffer.text = 'corrupted after SetText';
    assert.equal(label.text(), 'translated');

    runtime.externalSet(label, 'fresh source');
    runtime.update(label);
    assert.equal(label.text(), 'fresh source');
    assert.equal(runtime.api.status().modified, 0);
});

test('first setter already copies translated text, without waiting for an update or Python polling',()=>{
    const runtime=makeRuntime();
    runtime.api.configure({'中文':'<R>中文</R日本語>'},true);
    const label=runtime.label(0x9000,'');
    runtime.externalSet(label,'中文');
    assert.equal(label.text(),'<R>中文</R日本語>');
    assert.equal(label.copyCount,1);
    runtime.api.disable();runtime.update(label);
    assert.equal(label.text(),'中文');
});

test('runtime rules translate a new composite immediately and mode changes reuse the model',()=>{
    const runtime=makeRuntime();
    runtime.api.load({pairs:{'说明。':['说明。','説明。']},plain_pairs:{'说明。':['说明。','説明。']},
        numeric:[['HP上限\\+([+-]?\\d+)',['HP上限+%d','最大HP+%d']]]},'annotation',true,.9);
    const label=runtime.label(0x9100,'',0,32);
    runtime.externalSet(label,'<I299>HP上限+20\n说明。');
    assert.equal(label.text(),'<I299><s29><R>HP上限+20</R最大HP+20><s32>\n<s29><R>说明。</R説明。><s32>');
    runtime.api.select('secondary',true);runtime.update(label);
    assert.equal(label.text(),'<I299>最大HP+20\n説明。');
    runtime.api.select('primary',true);runtime.update(label);
    assert.equal(label.text(),'<I299>HP上限+20\n说明。');
    runtime.api.style(.8,{ruby_scale:.7,ruby_gap:4,line_gap:10});
    runtime.api.select('annotation',true);runtime.update(label);
    assert.ok(label.text().startsWith('<I299><s26><R>HP上限+20'));
});

test('invalid locale reload leaves the old resolver and enabled state intact',()=>{
    const runtime=makeRuntime(),label=runtime.label(0x9110,'回复药');
    const model={pairs:{'回复药':['Tear Balm','ティアの薬']},plain_pairs:{'回复药':['Tear Balm','ティアの薬']}};
    runtime.api.load(model,'primary',true,1);runtime.update(label);
    assert.equal(label.text(),'Tear Balm');
    assert.throws(()=>runtime.api.load({...model,numeric:[['[',['x','y']]]},'annotation',false,.9));
    runtime.update(label);assert.equal(label.text(),'Tear Balm');
    runtime.api.select('secondary',true);runtime.update(label);assert.equal(label.text(),'ティアの薬');
});

test('text logic hot update preserves labels and mode; rejected code keeps old logic',()=>{
    const runtime=makeRuntime(),label=runtime.label(0x9140,'回复药');
    const model={pairs:{'回复药':['Tear Balm','ティアの薬']},plain_pairs:{'回复药':['Tear Balm','ティアの薬']}};
    runtime.api.load(model,'secondary',true,1);runtime.update(label);
    const updated=RESOLVER+'\n'+IDENTITIES+"\nconst oldRender=RuntimeText.prototype.render;RuntimeText.prototype.render=function(...a){const p=oldRender.apply(this,a);return {...p,text:p.text+'!'};};";
    runtime.api.reloadlogic(updated);runtime.update(label);
    assert.equal(label.text(),'ティアの薬!');assert.equal(runtime.api.status().renderMode,'secondary');
    assert.throws(()=>runtime.api.reloadlogic('throw Error("bad release")'));
    runtime.update(label);assert.equal(label.text(),'ティアの薬!');
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),'回复药');
});

test('status and snapshot never dereference a hidden native object',()=>{
    const runtime=makeRuntime();const label=runtime.label(0x9200,'原文');
    runtime.api.configure({'原文':'翻译'},true);runtime.update(label);
    label.add=()=>{throw Error('background pointer read')};
    assert.equal(runtime.api.status().modified,1);
    assert.equal(runtime.api.snapshot()[0].original,'原文');
});

test('enable, disable, and internal re-entry restore the original source', () => {
    const runtime = makeRuntime();
    const label = runtime.label(0x4010, 'raw');
    runtime.externalSet(label, 'raw');
    runtime.api.configure({raw: 'translated'}, true);
    runtime.update(label);
    assert.equal(label.text(), 'translated');

    // The NativeFunction invocation re-enters the setter hook.  Its internal
    // guard must prevent translated text becoming the remembered source.
    runtime.api.disable();
    runtime.update(label);
    assert.equal(label.text(), 'raw');
    assert.equal(runtime.api.status().modified, 0);
});

test('an unchanged epoch does not invoke SetText twice', () => {
    const runtime = makeRuntime();
    const label = runtime.label(0x4020, 'raw');
    runtime.externalSet(label, 'raw');
    runtime.api.configure({raw: 'translated'}, true);
    runtime.update(label);
    const afterFirstUpdate = runtime.api.status().writes;
    runtime.update(label);
    assert.equal(afterFirstUpdate, 1);
    assert.equal(runtime.api.status().writes, 1);
    assert.equal(label.copyCount, 2); // one external source setter and one native translation setter
});

test('re-submitting a translated owned string retains the restorable source', () => {
    const runtime=makeRuntime();
    const label=runtime.label(0x4200,'original');
    runtime.api.configure({original:'<R>original</Rannotation>'},true);
    runtime.update(label);
    runtime.externalSet(label,label.text());
    runtime.update(label);
    runtime.api.disable();
    runtime.update(label);
    assert.equal(label.text(),'original');
    assert.equal(runtime.api.status().modified,0);
});

test('the actual text key disambiguates a label but a stale key never overrides dynamic text', () => {
    const runtime=makeRuntime();
    runtime.keyTable(99,'TXT_SAVE','保存');
    const label=runtime.label(0x4300,'保存');label.textKeyHash=99;
    runtime.api.configure({'\x01TXT_SAVE\x00保存':'<R>保存</Rセーブ>','生命露水':'<R>生命露水</R命の雫>'},true);
    runtime.update(label);
    assert.equal(label.text(),'<R>保存</Rセーブ>');
    runtime.externalSet(label,'生命露水');
    runtime.update(label);
    assert.equal(label.text(),'<R>生命露水</R命の雫>');
    runtime.api.disable();runtime.update(label);
    assert.equal(label.text(),'生命露水');
});

test('support list ancestry selects its own translation of a repeated name', () => {
    const runtime=makeRuntime();
    const label=runtime.label(0x4310,'反击');label.name='name';
    label.parent=runtime.label(0x4320,'');label.parent.name='skill_template';
    label.parent.parent=runtime.label(0x4330,'');label.parent.parent.name='ability_list';
    runtime.api.configure({'\x02support\x00反击':'<R>反击</R反撃>'},true);
    runtime.update(label);
    assert.equal(label.text(),'<R>反击</R反撃>');
    const other=runtime.label(0x4340,'反击');runtime.update(other);
    assert.equal(other.text(),'反击');
});

test('inventory name ownership disambiguates a copied item name without translating other surfaces',()=>{
    const r=makeRuntime(),label=r.label(0x4341,'Map');label.name='name';
    label.parent=r.label(0x4342,'');label.parent.name='item_template';
    r.api.load({pairs:{},plain_pairs:{},scoped:{item_name:{pairs:{Map:['Map','Carte']},plain_pairs:{Map:['Map','Carte']}}}},'annotation',true,1);
    r.externalSet(label,'Map');assert.equal(label.text(),'<R>Map</RCarte>');
    const other=r.label(0x4343,'Map');r.externalSet(other,'Map');assert.equal(other.text(),'Map');
    r.api.select('secondary',true);r.update(label);assert.equal(label.text(),'Carte');
    assert.equal(r.api.status().failed,false);
});

test('ruby measurement and drawing share scale without a second parser gap adjustment', () => {
    for(const measurement of [false,true]) {
        const sample={x:10,measurement};const runtime=makeRuntime(sample);
        const label=runtime.label(0x4350,'测试');
        runtime.api.configure({'测试':'<R>测试</Rテスト>'},true);runtime.update(label);
        assert.ok(Math.abs(sample.scale-.3)<1e-8);
        assert.equal(sample.y,0,'ink spacing is resolved at the glyph stage, not the parser origin');
    }
});

test('completed typewriter dialogue survives repeated language and annotation toggles',()=>{
    for(const flags of [4,5,0x14,0x15,0x45]) {
    const r=makeRuntime(),a='Hello there.',b='Bonjour !';
    r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'primary',true,1);
    const label=r.label(0x4700,a);label.flags=flags;
    r.externalSet(label,a);r.update(label);
    // Game has already initialized and finished this dialogue before the key.
    label.parserText=label.owned;label.cursor=label.total;label.progress=label.total;label.glyphs=label.total;
    for(const mode of ['annotation','primary','secondary','annotation','primary']) {
        r.api.select(mode,true);r.update(label);
        assert.ok(label.glyphs>0,mode+': current sentence must not disappear');
        assert.equal(label.parserText,label.owned,mode+': parser must reference the new owned buffer');
        assert.equal(label.cursor,label.total,mode+': completed sentence must stay complete');
        assert.equal(label.flags,flags,'pause and shadow/animation flags remain game-owned');
    }
    r.api.disable();r.update(label);assert.equal(label.text(),a);assert.ok(label.glyphs>0);
    }
});

test('inlined native writes translate before measurement without waiting for an epoch change',()=>{
    const r=makeRuntime(),p=r.label(0xa500,'');p.flags=32;r.update(p);
    r.api.load({pairs:{Estelle:['Estelle','エステル'],Olivier:['Olivier','オリビエ']},
        plain_pairs:{Estelle:['Estelle','エステル'],Olivier:['Olivier','オリビエ']}},'annotation',true,.8);
    r.update(p);
    for(const name of ['Estelle','Olivier','Estelle']) {
        const text='　·'+name+'　　　Lv.39',display=r.inlinedSet(p,text);
        assert.match(display,/<R>/);assert.ok(display.includes('Lv.39'));
        assert.equal(r.api.snapshot()[0].original,text);
        r.update(p);assert.equal(p.text(),display);
    }
    r.api.select('secondary',true);r.update(p);
    assert.match(r.inlinedSet(p,'　·Estelle　　　Lv.39'),/エステル/);
    assert.equal(r.api.status().failed,false);
    r.api.disable();r.update(p);assert.equal(p.text(),'　·Estelle　　　Lv.39');
    assert.equal(r.inlinedSet(p,'　·Olivier　　　Lv.39'),'　·Olivier　　　Lv.39');
});

test('typewriter refresh retains partial progress and does not rebuild unchanged frames',()=>{
    const r=makeRuntime(),a='abcdefghijkl',b='mnopqrstuvwx';
    r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'primary',true,1);
    const label=r.label(0x4710,a);label.flags=5;r.externalSet(label,a);r.update(label);
    label.parserText=label.owned;label.progress=6;label.cursor=6;label.glyphs=6;
    r.api.select('secondary',true);r.update(label);
    assert.equal(label.progress,6);assert.equal(label.glyphs,6);
    const resets=label.resetCount;r.update(label);r.update(label);assert.equal(label.resetCount,resets);
    r.api.select('annotation',true);r.update(label);
    const ratio=label.progress/label.total, count=label.resetCount;
    r.api.style(1,{ruby_gap:7});r.update(label);
    assert.equal(label.progress/label.total,ratio);assert.ok(label.glyphs>0);
    assert.equal(label.resetCount,count+1);
    r.externalSet(label,'new game sentence');
    assert.equal(label.resetCount,count+1,'game-initiated SetText retains its native lifecycle');
});

test('digits, width variants and icon-only pairs never acquire mod geometry',()=>{
    for(const [a,b] of [['4','４'],['HP','ＨＰ'],['<I1544>','<I1544>'],['<s27>4','<s30>４'],['Nightmare','Nightmare']]) {
        const runtime=makeRuntime(),label=runtime.label(0x4610,a);
        runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
        runtime.update(label);assert.equal(label.text(),a);
        assert.equal(runtime.newline(label,40),40);
        assert.equal(runtime.api.snapshot()[0].presentation,'plain');
        runtime.api.select('secondary',true);runtime.update(label);assert.equal(label.text(),b);
    }
});

test('mixed chapter and difficulty keep native size, advance and following baseline',()=>{
    const runtime=makeRuntime(),source='第２章“大地翻腾”　　　　 ＜Nightmare＞';
    const pair=['第２章“大地翻腾”','２章「荒ぶる大地」'];
    runtime.api.load({pairs:{[pair[0]]:pair},plain_pairs:{[pair[0]]:pair}},'annotation',true,.9);
    const label=runtime.label(0x4620,source);runtime.update(label);
    assert.equal(label.text(),'<R>第２章“大地翻腾”</R２章「荒ぶる大地」>　　　　 ＜Nightmare＞');
    assert.deepEqual(runtime.compensate(label),{y:100,flag:0});
    assert.deepEqual(runtime.compensate(label,true),{y:112,flag:1});
    assert.equal(runtime.parseOrigin(label),100);
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),source);
});

test('unannotated numeric lines inside a formatted paragraph retain their native size',()=>{
    const runtime=makeRuntime(),a='<C2>Text</C>\n4',b='<C2>Texte</C>\n４';
    runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
    const label=runtime.label(0x4650,a);runtime.update(label);
    assert.equal(label.text(),'<R></R_><C2>Text</C>\n4');
});

test('late native font changes and rebuilt menus use the same size as a hot style refresh',()=>{
    const r=makeRuntime(),a='鼠标·键盘';r.api.configure({[a]:'<R>'+a+'</Rマウス・キーボード>'},true,.85);
    const label=r.label(0x4660,'',0,32);r.externalSet(label,a);
    assert.match(label.text(),/^<s27>/);
    label.fontSize=24;r.update(label);assert.match(label.text(),/^<s20>/);
    const expected=label.text();r.api.style(.85,{ruby_scale:.85,ruby_gap:2});r.update(label);
    assert.equal(label.text(),expected);
    r.destroy(label);const rebuilt=r.label(0x4660,'',0,32);r.externalSet(rebuilt,a);
    rebuilt.fontSize=24;r.update(rebuilt);assert.equal(rebuilt.text(),expected);
    const writes=rebuilt.copyCount;r.update(rebuilt);assert.equal(rebuilt.copyCount,writes);
});

test('geometry-only changes remeasure unchanged annotated text once, leaving plain labels alone',()=>{
    const r=makeRuntime(),label=r.label(0x4680,'Text'),plain=r.label(0x4690,'4');
    r.api.load({pairs:{Text:['Text','Texte']},plain_pairs:{Text:['Text','Texte']}},'annotation',true,.86);
    r.update(label);r.update(plain);
    const text=label.text(),copies=label.copyCount,reflows=label.reflows;
    r.api.style(.86,{ruby_scale:.7,ruby_gap:2,line_gap:5});
    r.update(label);r.update(plain);
    assert.equal(label.text(),text);assert.equal(label.copyCount,copies);
    assert.equal(label.reflows,reflows+1);assert.equal(plain.reflows,0);
    r.update(label);assert.equal(label.reflows,reflows+1);
});

test('every hot text refresh gets one formal measurement after the nested setter',()=>{
    const pairs=[['Text','Texte'],['回复','回復'],['我方','味方'],['恢复HP','HP回復'],
        ['Description','説明'],['<C3>Formatted</C>','<C3>装飾</C>']];
    const entries=Object.fromEntries(pairs.map(p=>[p[0],p]));
    const model={pairs:entries,plain_pairs:entries};
    const sources=['Text','<C3>回复</C>/<I299>我方 恢复HP\nDescription','<C3>Formatted</C>'];
    for(const flags of [0,8,12,72,4,20])for(const source of sources) {
        const r=makeRuntime(),p=r.label(0xb330,'');p.flags=flags;
        r.api.load(model,'primary',true,.85);r.externalSet(p,source);
        p.progress=p.total/2;
        const fraction=p.progress/p.total;
        for(const mode of ['annotation','primary','annotation']) {
            const before=p.reflows;
            r.api.select(mode,true);r.update(p);
            assert.equal(p.reflows,before+1,`missing formal measure: ${flags}/${source}/${mode}`);
            assert.equal(p.flags,flags,'pause and permission flags must be restored');
            if(flags&4)assert.equal(p.progress/p.total,fraction,'refresh retains reveal fraction');
            r.update(p);r.update(p);
            assert.equal(p.reflows,before+1,'stable frames must not repeat measurement');
            assert.equal(r.api.status().failed,false,r.api.status().failureReason);
        }
    }
});

test('small and late-bound native sizes retain bilingual text without stopping other labels',()=>{
    for(const size of [0,1,8,11,257,0xffffffff]) {
        const r=makeRuntime(),source='魔獣',pairs={[source]:['Monster','魔獣']};
        r.api.load({pairs,plain_pairs:pairs},'annotation',true,.8);
        const p=r.label(0x4691,source,0,size),other=r.label(0x4692,source,0,32);
        r.update(p);r.update(other);
        assert.equal(p.text(),'<R>Monster</R魔獣>');
        assert.match(other.text(),/^<s26>/);
        assert.equal(r.api.status().failed,false);
        assert.deepEqual([...r.api.status().nativeSizeFallbacks],[size]);
        r.capturedRubyRuns(p,[[20,40,10,10],[20,18,6,6]],[[0,1,2]]);
        const scaled=r.glyphLayout(p);
        assert.equal(scaled[0][2],8);assert.ok(Math.abs(scaled[1][2]-4.8)<.00001);
        r.api.select('primary',true);r.update(p);assert.equal(p.text(),'Monster');
        r.api.select('annotation',true);r.update(p);assert.match(p.text(),/<R>/);
        p.fontSize=24;r.update(p);assert.match(p.text(),/^<s19>/);
        r.api.disable();r.update(p);assert.equal(p.text(),source);
    }
});

test('mixed party rows scale owned text while retaining native advances and level geometry',()=>{
    const r=makeRuntime(),source=' ·Estelle    Lv.39\n ·Olivier    Lv.39';
    const pairs={Estelle:['Estelle','エステル'],Olivier:['Olivier','オリビエ']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.8,{ruby_gap:2,line_gap:12});
    const p=r.label(0x4621,source,0,26);r.inlinedSet(p,source);
    assert.match(p.text(),/ ·<R>Estelle<\/Rエステル>    Lv.39/);
    assert.equal(r.newline(p,40),40);
    for(const delta of [0,12,8])assert.equal(r.parseOrigin(p,false,delta),100);
    // Two native ruby runs, separated by the untouched level on each line.
    const input=[[20,30,26,26],[20,18,14,14],[130,30,26,26],
        [20,76,26,26],[20,64,14,14],[130,76,26,26]];
    r.capturedRubyRuns(p,input,[[0,1,2],[3,4,5]]);
    const output=r.glyphLayout(p);
    for(const i of [2,5])assert.deepEqual(output[i],input[i]);
    for(const i of [0,3]) {
        assert.ok(Math.abs(output[i][3]-input[i][3]*.8)<.001,'owned main text follows configured scale');
        assert.ok(Math.abs(output[i][1]+output[i][3]/2-input[i][1]-input[i][3]/2)<1e-5,'retain original float32 bottom');
    }
    for(const [main,secondary] of [[0,1],[3,4]])
        assert.ok(Math.abs(output[main][1]-output[main][3]/2-(output[secondary][1]+output[secondary][3]/2)-2)<.001);
    assert.deepEqual(r.glyphLayout(p),output,'cached mixed rows must not shrink repeatedly');
    r.api.select('primary',true);r.update(p);
    assert.deepEqual(r.glyphLayout(p),output,'stale ruby ranges cannot move plain glyphs');
    assert.equal(p.text(),source);assert.equal(r.parseOrigin(p),112);
});

test('mixed formatted text scales around native icons without shrinking counters or accumulating',()=>{
    for(const scale of [.7,.8,1]) {
        const r=makeRuntime(),a='<C2>Name<I7>Text</C>\n42',b='<C2>Nom<I7>Texte</C>\n42';
        r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,scale,{ruby_gap:2});
        const p=r.label(0x4622,a,0,40);r.update(p);
        const input=[[20,12,20,20],[20,40,40,40],[70,40,40,40,1],[120,40,40,40],[20,90,40,40]];
        r.auxiliary(p,0,{glyphQuads:input,secondaryCount:1});
        p.glyphs=4;r.newline(p,60);p.glyphs=5;
        assert.equal(r.api.status().failed,false,r.api.status().failureReason);
        // The following plain line belongs to the same native glyph array,
        // but is not part of the translated primary line.
        const output=r.glyphLayout(p);
        assert.deepEqual(output[2],input[2].slice(0,4),'native icon retains size and position');
        assert.deepEqual(output[4],input[4],'following plain counter retains size and position');
        assert.equal(output[1][2],40*scale);
        assert.equal(output[3][2],40*scale);
        assert.deepEqual(r.glyphLayout(p),output);
        assert.equal(r.api.status().failed,false);
    }
});

test('ruby-enabled native measurement retains its ruby-height reserve',()=>{
    const r=makeRuntime(),label=r.label(0x4681,'输入');
    r.api.configure({'输入':'<R>输入</R入力>'},true,.86);r.update(label);
    // Captured native trace: ordinary initial SetText runs parser hooks; a
    // nested setter from Update measures natively without those callbacks.
    // Suppression in the first path incorrectly dropped 12 layout units.
    assert.deepEqual(r.compensate(label,true),{y:112,flag:1});
    assert.deepEqual(r.compensate(label,false),{y:100,flag:0});
});

test('formatted footer uses actual glyph edges rather than native measurement bounds',()=>{
    const a='完成总计<C3>15件</C>委托并汇报。',b='計<C3>１５件</C>のクエストを達成して報告する。';
    const runtime=makeRuntime();runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85,{ruby_gap:2});
    const label=runtime.label(0x4670,a);runtime.update(label);
    const input=[[10,100,14,14],[20,100,14,14],[15,100,24,24],[40,100,24,24]];
    runtime.auxiliary(label,0,{origin:100,primaryTop:-12,bottom:18,glyphQuads:input,secondaryCount:2});
    const v=runtime.glyphLayout(label);
    assert.equal(v[1][1]+7,86,'secondary edge must be two units above the actual primary top at 88');
    assert.equal(runtime.api.status().failed,false);
});

test('plain, outlined, animated and formatted labels share one glyph gap across sizes and offsets',()=>{
    for(const fontSize of [18,32,64])for(const nativeY of [30,80,110])for(const flags of [0,1,128,773]) {
        const runtime=makeRuntime();
        runtime.api.configure({'Text':'<R>Text</RTexte>'},true);
        const label=runtime.label(0x4630,'Text',0,fontSize);label.flags=flags;runtime.update(label);
        const primary=[20,100,fontSize,fontSize],secondary=[40,nativeY,14,14];
        runtime.capturedRuby(label,[primary,secondary],1);
        const ordinary=runtime.glyphLayout(label);
        const formatted=makeRuntime(),a='<C2>Text</C>',b='<C2>Texte</C>';
        formatted.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
        const other=formatted.label(0x4640,a,0,fontSize);formatted.update(other);
        formatted.auxiliary(other,0,{glyphQuads:[secondary,primary],secondaryCount:1});
        const styled=formatted.glyphLayout(other);
        assert.deepEqual(ordinary[0],primary);assert.deepEqual(styled[1],primary);
        assert.deepEqual(ordinary[1],styled[0]);assert.equal(primary[1]-primary[3]/2-(styled[0][1]+7),3);
        assert.equal(runtime.api.status().failed,false);assert.equal(formatted.api.status().failed,false);
    }
});

test('horizontal offset moves only new drawing, retaining list clamp and original annotation coordinates',()=>{
    for(const [x,measurement,expected] of [[10,false,6],[-20,false,6],[10,true,10]]) {
        const sample={x,measurement},runtime=makeRuntime(sample),label=runtime.label(0x4380,'测试');
        runtime.api.load({pairs:{'测试':['测试','テスト']},plain_pairs:{'测试':['测试','テスト']}},'annotation',true,.9,{ruby_offset_x:6});
        runtime.update(label);assert.equal(sample.after,expected);
    }
    const runtime=makeRuntime(),source='<R>女神</R爱德斯>';
    runtime.api.load({pairs:{[source]:[source,'女神']},plain_pairs:{[source]:[source,'女神']}},'annotation',true,.9,{ruby_offset_x:7});
    const label=runtime.label(0x4390,source,0,32);runtime.update(label);
    const result=runtime.auxiliary(label);
    assert.equal(result.primaryX,20);assert.equal(result.primaryY,100);
    assert.equal(result.results[1].x,27);
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),source);
});

test('secondary icon parser owns a cloned icon callback only for its drawing pass',()=>{
    const runtime=makeRuntime(),source='<I289>物理攻击',secondary='<I289>物理攻撃';
    runtime.api.load({pairs:{[source]:[source,secondary]},plain_pairs:{[source]:[source,secondary]}},'annotation',true,.85);
    const label=runtime.label(0x4398,source,0,32);runtime.update(label);
    const result=runtime.auxiliary(label,0,{iconCallback:true});
    assert.equal(result.results[0].iconCallback,false,'measuring must not draw icons');
    assert.equal(result.results[1].iconCallback,true,'drawing must receive the native icon callback');
    assert.equal(result.results[1].iconCallbackOwned,true,'the child must own its callback storage, not borrow parent lifetime');
    const without=runtime.auxiliary(label);
    assert.equal(without.results[1].iconCallback,false,'a measuring parent cannot acquire drawing callbacks');
    assert.equal(runtime.api.status().failed,false);
});

test('logic reload rejects native instrumentation before executing any supplied code',()=>{
    const r=makeRuntime(),p=r.label(0x9210,'原文');
    r.api.load({pairs:{'原文':['原文','訳文']},plain_pairs:{'原文':['原文','訳文']}},'secondary',true,1);r.update(p);
    for(const source of [
        'Interceptor.attach(ptr(123), {});',
        'new NativeFunction(ptr(123), "void", []);',
        'Memory.allocUtf8String("test");',
        'globalThis.nativeProbe = Process.getCurrentThreadId();',
    ])assert.throws(()=>r.api.reloadlogic(source),/Resident instrumentation cannot be hot-loaded/);
    r.update(p);assert.equal(p.text(),'訳文');assert.equal(r.api.status().failed,false);
});

test('newline breathing room applies only while this mod owns an annotated label', () => {
    const runtime=makeRuntime();const label=runtime.label(0x4360,'原文\n下一行');
    assert.equal(runtime.newline(label,38),38);
    runtime.api.configure({'原文\n下一行':'<R>原文</R原文>\n<R>下一行</R次の行>'},true);
    runtime.update(label);assert.equal(runtime.newline(label,38),50);
    runtime.api.disable();runtime.update(label);assert.equal(runtime.newline(label,38),38);
});

test('a label may move sequentially between game threads without disabling bilingual text', () => {
    const runtime=makeRuntime();
    const label=runtime.label(0x4210,'original');
    runtime.api.configure({original:'translated'},true);
    runtime.update(label,11);
    runtime.update(label,22);
    runtime.update(label,11);
    assert.equal(label.text(),'translated');
    assert.equal(runtime.api.status().failed,false);
    runtime.api.disable();runtime.update(label,22);
    assert.equal(label.text(),'original');
});

test('destructor removes a row so an address reuse starts from fresh raw text', () => {
    const runtime = makeRuntime();
    const oldLabel = runtime.label(0x4030, 'old raw');
    runtime.externalSet(oldLabel, 'old raw');
    runtime.api.configure({'old raw': 'old translation'}, true);
    runtime.update(oldLabel);
    assert.equal(oldLabel.text(), 'old translation');
    runtime.destroy(oldLabel);
    assert.equal(runtime.api.status().labels, 0);

    const reusedAddress = runtime.label(0x4030, 'new raw');
    runtime.update(reusedAddress);
    assert.equal(reusedAddress.text(), 'new raw');
    assert.equal(runtime.api.status().destroyed, 1);
    assert.equal(runtime.api.status().modified, 0);
});

test('two game threads updating different labels preserve the connection and both translations', () => {
    const runtime = makeRuntime();
    const label = runtime.label(0x4040, 'raw');
    runtime.externalSet(label, 'raw',11);
    runtime.api.configure({raw: 'translated'}, true);
    runtime.update(label, 11);
    const writes = runtime.api.status().writes;
    const other=runtime.label(0x4440,'raw');runtime.update(other,22);
    const status = runtime.api.status();
    assert.equal(status.failed, false);
    assert.equal(status.enabled, true);
    assert.equal(status.writes, writes+1);
    assert.equal(other.text(),'translated');
    assert.deepEqual(Array.from(status.threads), [11, 22]);
    assert.ok(!runtime.messages.some(message => message.type === 'error'));
});

test('cooperative native setter keeps suppression local to its own thread and label',()=>{
    const runtime=makeRuntime(),a=runtime.label(0x4510,'a'),b=runtime.label(0x4520,'b');
    runtime.api.configure({a:'A',b:'B'},true);
    runtime.duringSetter(()=>runtime.externalSet(b,'b',22));runtime.update(a,11);
    assert.equal(a.text(),'A');assert.equal(b.text(),'B');assert.equal(runtime.api.status().failed,false);
    runtime.api.disable();runtime.update(a,11);runtime.update(b,22);
    assert.equal(a.text(),'a');assert.equal(b.text(),'b');
});

test('simultaneous callbacks on the same label remain rejected, without a foreign native rewrite',()=>{
    const runtime=makeRuntime(),a=runtime.label(0x4530,'a');runtime.api.configure({a:'A'},true);
    const finish=runtime.beginUpdate(a,11),writes=runtime.api.status().writes;
    runtime.update(a,22);assert.equal(runtime.api.status().failed,true);assert.equal(runtime.api.status().writes,writes);
    finish();runtime.update(a,11);assert.equal(a.text(),'a');
});

test('mode change during a native setter is applied on the next update rather than acknowledged prematurely',()=>{
    const runtime=makeRuntime(),a=runtime.label(0x4540,'a');runtime.api.configure({a:'A'},true);
    runtime.duringSetter(()=>runtime.api.disable());runtime.update(a);
    assert.equal(a.text(),'A');runtime.update(a);assert.equal(a.text(),'a');
});

test('ruby annotation scale prefixes an absolute native size and disable restores raw text', () => {
    const runtime = makeRuntime(null,true);
    const label = runtime.label(0x4050, 'raw ruby', 7, 29);
    runtime.externalSet(label, 'raw ruby');
    runtime.api.configure({'raw ruby': '<R>base</Rannotation>'}, true, 0.9);
    runtime.update(label);
    assert.equal(label.text(), '<s26><R>base</Rannotation><s29>');
    const event = runtime.messages.find(message => message.type === 'native_text');
    assert.equal(event.fontSize, 29);

    runtime.api.disable();
    runtime.update(label);
    assert.equal(label.text(), 'raw ruby');
});

test('bulk history updates do not stream per-label text when diagnostics are disabled',()=>{
    for(const diagnostics of [false,true]) {
        const r=makeRuntime(null,diagnostics);
        r.api.configure({source:'<R>Primary</RSecondary>'},true,.8);
        for(let i=0;i<400;i++)r.update(r.label(0x8000+i*0x10000,'source'));
        assert.equal(r.api.status().writes,400);
        assert.equal(r.messages.filter(v=>v.type==='native_text').length,diagnostics?400:0);
        assert.equal(r.api.status().failed,false);
    }
});

test('null RPC scale uses the native default and does not add a size tag', () => {
    const runtime = makeRuntime();
    const label = runtime.label(0x4060, 'raw ruby', 0, 29);
    runtime.externalSet(label, 'raw ruby');
    runtime.api.configure({'raw ruby': '<R>base</Rannotation>'}, true, null);
    runtime.update(label);
    assert.equal(label.text(), '<R>base</Rannotation>');
    assert.equal(runtime.api.status().failed, false);
});

test('ruby placement clamps only an owned negative left edge at the verified callsite', () => {
    for (const sample of [
        {x:-42,expected:0}, {x:-24,deferred:true,expected:0}, {x:7,expected:0},
        {x:7,baseLeft:19,expected:19},
        {x:-42,wrongCallsite:true,expected:-42},
        {x:-42,wrongLabel:true,expected:-42},
        {x:-42,flags:2,baseLeft:19,expected:19},
    ]) {
        const runtime=makeRuntime(sample);
        const label=runtime.label(0x4100,'raw ruby');
        label.flags=sample.flags ?? 1;
        runtime.api.configure({'raw ruby':'<R>还魂粉</Rゼラムパウダー>'},true,0.9);
        runtime.update(label);
        assert.equal(sample.after,sample.expected);
        assert.equal(runtime.api.status().failed,false);
        runtime.api.disable();runtime.update(label);
        assert.equal(label.text(),'raw ruby');
    }
});

test('original ruby and emphasis remain unchanged while a separately owned lane renders',()=>{
    for(const a of ['来到<R>女神</R爱德斯>身旁。','<R>绝对不行</R・・・・>']) {
        const b='<R>女神</Rエイドス>の傍へ。';const runtime=makeRuntime();
        runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
        const label=runtime.label(0x9990,'',0,32);runtime.externalSet(label,a);
        assert.equal(label.text(),'<R></R_>'+a);
        assert.equal(runtime.newline(label,100),100,'original line positions are untouched');
        const result=runtime.auxiliary(label);
        assert.deepEqual(result.bounds,[0,0,0,0]);
        assert.equal(result.primaryX,20);assert.equal(result.primaryY,100);
        assert.equal(result.duringCompensation,1);assert.equal(result.restoredCompensation,0);
        for(const [i,v] of result.results.entries()) {
            assert.equal(v.text,b);assert.equal(v.count,[...b].length);
            assert.equal(v.nestedRubyDisabled,i===0?1:0);assert.ok(Math.abs(v.scale-.3)<1e-8);
        }
        assert.equal(result.results[1].x,20);
        assert.equal(result.results[1].y,80,'original parser positions remain native');
        runtime.api.select('secondary',true);runtime.update(label);assert.equal(label.text(),b);
        runtime.api.disable();runtime.update(label);assert.equal(label.text(),a);
        assert.equal(runtime.api.status().failed,false);
    }
});

test('original native ruby in single-language mode never gets mod geometry',()=>{
    const sample={x:-5};const runtime=makeRuntime(sample),a='神',b='<R>神</Rかみ>';
    runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'secondary',true,.9);
    const label=runtime.label(0x9980,a);runtime.update(label);
    assert.equal(label.text(),b);assert.equal(sample.after,-5);
    assert.equal(sample.scale,.375);assert.equal(sample.y,0);
});

test('native reading in the secondary does not exempt a whole page from main scaling',()=>{
    const r=makeRuntime(),a='门的接缝不好。\n门外很安静。',b='戸の<R>建付</Rたてつけ>が悪い。\n外は静かだ。';
    r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85);
    const p=r.label(0xb100,a,0,32);r.update(p);
    assert.ok(p.text().startsWith('<s27>'), 'secondary reading must not suppress configured main scale');
    assert.equal(r.api.snapshot().find(v=>v.original===a).layers.length,2);
    r.api.select('primary',true);r.update(p);assert.equal(p.text(),a);
});

test('catalog labels permit only owned annotations inside native ruby-disabled controls',()=>{
    const r=makeRuntime(),p=r.label(0xb200,'调查');p.flags=8;
    r.api.load({pairs:{'调查':['调查','調査']},plain_pairs:{'调查':['调查','調査']}},'annotation',true,.85);
    r.update(p);assert.equal(r.rubyAllowed(p),true);assert.equal(p.flags,8);
    assert.equal(r.rubyAllowed(p,true),false,'cold measurement must retain native primary-only height');
    r.api.select('primary',true);r.update(p);assert.equal(r.rubyAllowed(p),false);assert.equal(p.flags,8);
    const native=r.label(0xb300,'<R>字</Rじ>');native.flags=8;r.update(native);
    assert.equal(r.rubyAllowed(native),false);assert.equal(native.flags,8);
});

test('late animated flags rebuild the secondary lane without waiting for a mode change',()=>{
    const r=makeRuntime(),p=r.label(0xb310,'');
    r.api.load({pairs:{ABCD:['ABCD','甲乙丙丁']},plain_pairs:{ABCD:['ABCD','甲乙丙丁']}},'annotation',true,.85);
    r.externalSet(p,'ABCD');
    assert.equal(r.api.snapshot()[0].presentation,'ruby');
    p.flags=4;r.update(p);
    assert.equal(r.api.snapshot()[0].presentation,'layered');
    const writes=r.api.status().writes;
    r.update(p);assert.equal(r.api.status().writes,writes,'stable animation flags must not rebuild every frame');
    p.flags|=0x10;r.update(p);
    assert.equal(r.api.status().writes,writes,'pause flags must not invalidate the dialogue');
});

test('late catalog flags remeasure once just as switching into bilingual mode does',()=>{
    const r=makeRuntime(),p=r.label(0xb320,'');
    r.api.load({pairs:{Title:['Title','題名']},plain_pairs:{Title:['Title','題名']}},'annotation',true,.85);
    r.externalSet(p,'Title');
    const reflows=p.reflows;
    p.flags=8;r.update(p);
    assert.equal(p.reflows,reflows+1);
    assert.equal(r.rubyAllowed(p),true);assert.equal(p.flags,8);
    r.update(p);assert.equal(p.reflows,reflows+1,'final native flags must be cached after repair');
});

test('secondary tint multiplies original RGB once and preserves primary colors and alpha',()=>{
    const r=makeRuntime(),p=r.label(0xb400,'字');
    r.api.load({pairs:{'字':['字','Letter']},plain_pairs:{'字':['字','Letter']}},'annotation',true,1,{secondary_color:[.9,.8,.7],secondary_opacity:1});
    r.update(p);r.capturedRuby(p,[[10,30,20,20],[10,5,10,10],[20,5,10,10]],1);
    const original=[[.2,.4,.6,.8],[1,.8,.2,.7],[0,0,0,.4]];
    r.glyphColors(p,original);r.glyphLayout(p);
    const expected=[original[0],[.9,.64,.14,.7],original[2]];
    for(let n=0;n<3;n++){r.glyphLayout(p);r.glyphColors(p).forEach((v,i)=>v.forEach((c,j)=>assert.ok(Math.abs(c-expected[i][j])<1e-6)));}
});

test('animated secondary follows its own main line without changing the native reveal clock',()=>{
    const r=makeRuntime(),p=r.label(0xb500,'ABCD');p.flags=4;
    r.api.load({pairs:{ABCD:['ABCD','甲乙丙丁']},plain_pairs:{ABCD:['ABCD','甲乙丙丁']}},'annotation',true,1,{secondary_opacity:1});
    r.update(p);
    assert.equal(r.api.snapshot()[0].presentation,'layered','secondary must exist before the final main character');
    r.auxiliary(p,0,{unitStart:7,primaryUnits:4,secondaryCount:4,glyphQuads:[
        [5,5,10,10],[15,5,10,10],[25,5,10,10],[35,5,10,10],[5,30,10,20]
    ]});
    r.glyphColors(p,Array.from({length:5},()=>[1,1,1,.6]));
    p.progress=123;const total=p.total;
    for(const [units,expected] of [[7,[0,0,0,0]],[8,[.6,0,0,0]],[9,[.6,.6,0,0]],[11,[.6,.6,.6,.6]],[11,[.6,.6,.6,.6]]]) {
        p.revealUnits=units;r.glyphLayout(p);
        r.glyphColors(p).forEach((v,i)=>assert.ok(Math.abs(v[3]-[...expected,.6][i])<1e-6));
        assert.equal(p.progress,123);assert.equal(p.total,total);
    }
});

test('long log lanes keep native-memory boundary calls linear with a small per-glyph budget',()=>{
    const r=makeRuntime(),p=r.label(0xb450,'对白');
    r.api.load({pairs:{'对白':['对白','Dialogue']},plain_pairs:{'对白':['对白','Dialogue']}},'annotation',true,.85,{secondary_color:[.9,.9,.9]});
    r.update(p);
    const primary=Array.from({length:80},(_,i)=>[i*18,40,18,24]);
    const secondary=Array.from({length:80},(_,i)=>[i*10,10,10,12]);
    r.capturedRuby(p,[...primary,...secondary],80);
    Object.keys(r.memoryCost).forEach(k=>r.memoryCost[k]=0);
    r.finishLayout(p);
    assert.equal(r.api.status().failed,false,r.api.status().failureReason);
    assert.ok(r.memoryCost.scalarReads+r.memoryCost.blockReads<=160*3+8,JSON.stringify(r.memoryCost));
    const reads=r.memoryCost.scalarReads+r.memoryCost.blockReads;
    r.finishLayout(p);
    assert.ok(r.memoryCost.scalarReads+r.memoryCost.blockReads-reads<=2,'an unchanged layout must not scan glyph memory again');
});

test('secondary opacity includes icons and composes with per-line reveal without fading primary text',()=>{
    const r=makeRuntime(),p=r.label(0xb580,'AB');p.flags=4;
    r.api.load({pairs:{AB:['AB','字<I2>']},plain_pairs:{AB:['AB','字<I2>']}},'annotation',true,1,
        {secondary_color:[1,1,1],secondary_opacity:.5});
    r.update(p);
    r.auxiliary(p,0,{unitStart:2,primaryUnits:2,secondaryCount:2,glyphQuads:[
        [5,5,10,10],[15,5,10,10,1],[5,30,10,20]
    ]});
    r.glyphColors(p,[[.2,.4,.6,.8],[.8,.6,.4,.6],[1,1,1,.9]]);
    for(const [units,alpha] of [[2,[0,0,.9]],[3,[.4,0,.9]],[4,[.4,.3,.9]],[4,[.4,.3,.9]]]) {
        p.revealUnits=units;r.glyphLayout(p);
        r.glyphColors(p).forEach((v,i)=>assert.ok(Math.abs(v[3]-alpha[i])<1e-6));
    }
});

test('bilingual group offset moves both languages once, survives rebuilds and leaves single language untouched',()=>{
    const r=makeRuntime(),p=r.label(0xb590,'字');
    r.api.load({pairs:{'字':['字','Letter']},plain_pairs:{'字':['字','Letter']}},'annotation',true,1,
        {ruby_gap:2,bilingual_offset_y:7});
    r.update(p);
    const input=[[10,30,20,20],[10,5,10,10],[20,5,10,10,1]];
    r.capturedRuby(p,input,1);
    const expected=r.glyphLayout(p);
    assert.equal(expected[0][1],37);
    assert.equal(expected[1][1],20);
    assert.equal(expected[2][1],20);
    for(let i=0;i<4;i++)assert.deepEqual(r.glyphLayout(p),expected);
    r.capturedRuby(p,input,1);assert.deepEqual(r.glyphLayout(p),expected);
    r.api.select('primary',true);r.update(p);r.setGlyphQuads(p,[[10,30,20,20]]);
    assert.deepEqual(r.glyphLayout(p),[[10,30,20,20]]);
    r.api.select('annotation',true);r.api.style(1,{ruby_gap:2,bilingual_offset_y:-4});r.update(p);
    r.capturedRuby(p,input,1);
    const shifted=r.glyphLayout(p);
    assert.equal(shifted[0][1],26);assert.equal(shifted[1][1],9);assert.equal(shifted[2][1],9);
});

test('subtitles and ordinary dialogue both annotate above without appended paragraphs',()=>{
    const runtime=makeRuntime(),a='甲\n乙',b='一\n二';
    runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
    const root=runtime.label(0x9910,'');runtime.markSubtitle(root);
    const subtitle=runtime.label(0x9920,a);subtitle.name='text';subtitle.parent=root;
    runtime.update(subtitle);assert.equal(subtitle.text().replace(/<s\d+>/g,''),'<R>甲</R一>\n<R>乙</R二>');
    assert.equal(subtitle.text().split('\n').length,2);
    assert.equal(runtime.api.snapshot().find(v=>v.displayed===subtitle.text()).surface,'subtitle');
    const name=runtime.label(0x9930,a);name.name='name_text';name.parent=root;
    runtime.update(name);assert.ok(name.text().includes('<R>'));
    const ordinary=runtime.label(0x9940,a);ordinary.name='text';
    runtime.update(ordinary);assert.ok(ordinary.text().includes('<R>'));
    runtime.api.select('secondary',true);runtime.update(subtitle);assert.equal(subtitle.text(),b);
    runtime.api.disable();runtime.update(subtitle);assert.equal(subtitle.text(),a);
});

test('ordinary text keeps native origin while speakers retain the scoped collision correction',()=>{
    const r=makeRuntime(),root=r.label(0xa100,'');r.markSubtitle(root);
    r.api.load({pairs:{Name:['Name','Nom']},plain_pairs:{Name:['Name','Nom']}},'annotation',true,1);
    for(const [node,dialogue,expected] of [['name_text',true,100],['prev_name_text',true,100],['text',true,112],['name_text',false,112]]) {
        const p=r.label(0xa200,'Name');p.name=node;if(dialogue)p.parent=root;r.update(p);
        assert.equal(r.parseOrigin(p),expected);assert.equal(r.parseOrigin(p,true),100);
        r.api.select('primary',true);r.update(p);assert.equal(r.parseOrigin(p),112);
        r.api.select('annotation',true);r.destroy(p);
    }
});

test('a long owned rendering may be resubmitted without becoming a new raw source',()=>{
    const runtime=makeRuntime(),label=runtime.label(0x9970,'raw');
    runtime.api.configure({raw:'x'.repeat(20000)},true);runtime.update(label);
    runtime.externalSet(label,label.text());runtime.update(label);
    assert.equal(runtime.api.status().failed,false);
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),'raw');
});

test('ordinary formatted lanes retain configured main size and gap, with corrected UTF-8 anchor offsets',()=>{
    const runtime=makeRuntime(),a='<C2>甲</C>\n乙',b='<C2>一</C>\n二';
    runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
    const label=runtime.label(0x9960,a,0,32);runtime.update(label);
    assert.ok(label.text().startsWith('<s29><R></R_>'));
    assert.equal(runtime.newline(label,100),112);
    const result=runtime.auxiliary(label,1);assert.equal(result.results[1].text,'二');
    assert.equal(result.results[1].y,80,'spacing is deferred to the shared glyph stage');
    assert.equal(runtime.api.status().failed,false);
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),a);
});

test('icon labels place the added lane before world transform, on every native rebuild',()=>{
    const r=makeRuntime(),a='<I1553> Skip scene',b='<I1553> Next scene';
    r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.8,{ruby_gap:3});
    const p=r.label(0xa400,a);p.flags=65;r.update(p);
    // Reduced live capture: two secondary quads (text + shadow), icon,
    // and primary text + shadow. Icon is taller and farther left.
    const input=[[32.02,23.4075,14.04,14.04],[34.02,25.4075,14.04,14.04],
        [16,31.5,32,32,1],[56,31.5,24,24],[58,33.5,24,24]];
    const check=(gap)=>{
        p.glyphs=0;r.auxiliary(p,0,{glyphQuads:input,secondaryCount:2});
        const out=r.glyphLayout(p);
        assert.deepEqual(out.slice(2),input.slice(2).map(v=>v.slice(0,4)),'icon/primary stay put');
        assert.ok(Math.abs((out[0][0]-out[0][2]/2)-44)<.001,'align with letters, not icon');
        assert.ok(Math.abs((31.5-12)-(out[1][1]+out[1][3]/2)-gap)<.001,'gap includes shadow');
        assert.deepEqual(r.glyphLayout(p),out,'no cumulative shift without a new layout');
        assert.equal(r.api.status().failed,false);
    };
    check(3);check(3);
    r.api.style(.8,{ruby_gap:6});r.update(p);check(6);
    r.api.select('primary',true);r.update(p);assert.equal(p.text(),a);
    r.api.select('annotation',true);r.update(p);check(6);
});

test('native dialogue carries exact VM identity through its builder without retaining a stale stack buffer',()=>{
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const runtime=makeRuntime(),data=Buffer.alloc(128);data.write('#scp');data.writeUInt32LE(24,4);data.writeUInt32LE(1,8);
    const signature=Buffer.concat([data.subarray(0,24),data.subarray(24,56),data.subarray(24,56)]).toString('hex');
    const make=target=>({pairs:{'好。':['好。',target]},plain_pairs:{'好。':['好。',target]},numeric:[]});
    const model={pairs:{},plain_pairs:{},numeric:[],script_identities:{scripts:{[signature]:[{size:data.length,sha256:scriptSha256(data),functions:{Talk:{model:{pairs:{},plain_pairs:{},numeric:[]},calls:{
        '1,3221226000':{model:make('はい。')},'1,3221227000':{model:make('よし。')}
    }}}}]}}};
    runtime.api.load(model,'annotation',true,1);
    const label=runtime.label(0xa000,'');
    runtime.dialogueSet(label,'好。',data,'Talk',[1,3221226000]);assert.match(label.text(),/はい。/);
    const buffer=runtime.dialogueSet(label,'好。',data,'Talk',[1,3221227000]);assert.match(label.text(),/よし。/);
    assert.equal(runtime.api.status().identityHits,2);
    runtime.api.select('secondary',true);runtime.update(label);assert.equal(label.text(),'よし。');
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),'好。');
    runtime.api.select('annotation',true);runtime.externalBuffer(label,buffer);
    assert.equal(label.text(),'好。','source pointer reuse after handler exit must not retain provenance');
    assert.equal(runtime.api.status().failed,false);
    const hashes=runtime.scriptReads.filter(n=>n===data.length).length;
    runtime.api.load({...model,...make('承知。')},'annotation',true,1);
    runtime.dialogueSet(label,'好。',data,'Talk',[1,3221226000]);assert.match(label.text(),/承知。/);
    assert.equal(runtime.scriptReads.filter(n=>n===data.length).length,hashes,'exact complete global pairs do not rehash the script');
});


test('quest paragraphs require the verified builder frame and preserve provenance across language modes',()=>{
    const r=makeRuntime(),source='★根据哈恩队长所说，\n　目击者似乎是在卡鲁迪亚隧道\n　入口的尼克斯。';
    const target='★ハーン隊長の話によると、\n　カルデア隧道の入口にいる\n　ニクスという人が目撃者のようだ。';
    const pairs={[source]:[source,target]},lines=source.split('\n'),targetLines=target.split('\n');
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.9);
    const frame=r.questBegin(7);r.questParagraph(source+'\n',7);
    const labels=lines.map((line,index)=>{
        const label=r.label(0xc100+index*0x100,'');r.questLine(label,line,7);return label;
    });
    r.questEnd(frame,7);
    labels.forEach((label,index)=>assert.match(label.text(),new RegExp(targetLines[index])));
    const copy=r.cloneLabel(labels[1],0xc500);
    assert.equal(copy.text(),labels[1].text(),'copy constructor keeps the exact paragraph provenance');
    r.api.select('primary',true);for(const label of [...labels,copy])r.update(label);
    assert.deepEqual(labels.map(label=>label.text()),lines);
    assert.equal(copy.text(),lines[1]);
    r.api.select('secondary',true);for(const label of [...labels,copy])r.update(label);
    assert.deepEqual(labels.map(label=>label.text()),targetLines);
    assert.equal(copy.text(),targetLines[1]);
    r.api.select('annotation',true);for(const label of labels)r.update(label);
    labels.forEach((label,index)=>assert.match(label.text(),new RegExp(targetLines[index])));

    const outside=r.label(0xc700,'');r.externalSet(outside,lines[0]);
    assert.equal(outside.text(),lines[0],'the identical isolated line is never a paragraph match');
    assert.equal(r.api.status().failed,false);
});

test('quest paragraph context rejects wrong caller ordering thread and exited builder frames',()=>{
    const r=makeRuntime(),source='甲甲\n乙乙',target='一一\n二二',pairs={[source]:[source,target]};
    r.api.load({pairs,plain_pairs:pairs},'secondary',true,1);
    const frame=r.questBegin(11);r.questParagraph(source,11);
    const wrongCaller=r.label(0xc801,'');r.questLine(wrongCaller,'甲甲',11,null);
    assert.equal(wrongCaller.text(),'甲甲');
    const first=r.label(0xc802,'');r.questLine(first,'甲甲',11);
    assert.equal(first.text(),'一一','a rejected caller does not advance the verified frame');
    const wrongOrder=r.label(0xc803,'');r.questLine(wrongOrder,'甲甲',11);
    assert.equal(wrongOrder.text(),'甲甲');
    const afterMismatch=r.label(0xc804,'');r.questLine(afterMismatch,'乙乙',11);
    assert.equal(afterMismatch.text(),'乙乙','mismatched order clears paragraph context');
    r.questEnd(frame,11);

    const threadFrame=r.questBegin(12);r.questParagraph(source,12);
    const foreign=r.label(0xc805,'');r.questLine(foreign,'甲甲',13);
    assert.equal(foreign.text(),'甲甲');
    const local=r.label(0xc806,'');r.questLine(local,'甲甲',12);
    assert.equal(local.text(),'一一');r.questEnd(threadFrame,12);

    const exited=r.questBegin(14);r.questParagraph(source,14);r.questEnd(exited,14);
    const late=r.label(0xc807,'');r.questLine(late,'甲甲',14);
    assert.equal(late.text(),'甲甲','no stale frame survives builder exit');
    assert.equal(r.api.status().failed,false);
});

test('quest paragraphs reflow non-primary language slots before per-line rendering',()=>{
    const r=makeRuntime(),source='原文甲甲\n原文乙乙';
    const primary='第一行较长的主语言\n第二行继续内容\n第三行结束';
    const secondary='Secondary first line\nSecondary second line\nSecondary third line';
    const pairs={[source]:[primary,secondary]},lines=source.split('\n');
    const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
    const expectedPrimary=RuntimeText.reflowAnnotationLines(source,primary),expectedSecondary=RuntimeText.reflowAnnotationLines(source,secondary);
    r.api.load({pairs,plain_pairs:pairs},'primary',true,1);
    const frame=r.questBegin(15);r.questParagraph(source,15);
    const labels=lines.map((line,index)=>{const label=r.label(0xc900+index*0x100,'');r.questLine(label,line,15);return label;});r.questEnd(frame,15);
    assert.deepEqual(labels.map(label=>label.text()),expectedPrimary);
    r.api.select('secondary',true);for(const label of labels)r.update(label);
    assert.deepEqual(labels.map(label=>label.text()),expectedSecondary);
    r.api.select('annotation',true);for(const label of labels)r.update(label);
    assert.ok(labels.every(label=>label.text()!==label.owned.text||label.text().includes('<R>')));
    assert.equal(r.api.status().failed,false);
});

test('log parsing validates owned text once per callback, without repeated full UTF-8 reads',()=>{
    const r=makeRuntime(),p=r.label(0xc980,'');
    r.api.load({pairs:{Token:['Token','訳']},plain_pairs:{Token:['Token','訳']}},'annotation',true,.85);
    r.externalSet(p,'前缀：Token');
    const before=r.memoryCost.textReads;
    r.repeatOwnedRubyParse(p,100,1);
    assert.ok(r.memoryCost.textReads-before<=400,'repeated owned checks must share the same callback-local result');
    assert.equal(r.api.status().failed,false);
});

test('repeated native parser rebuilds replace an offset owned ruby lane without touching tail glyphs',()=>{
    const r=makeRuntime(),source='前缀：Token\n42',pairs={Token:['Token','訳']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.8,{secondary_color:[.5,.5,.5],secondary_opacity:1});
    const label=r.label(0xca00,'');r.externalSet(label,source);
    r.repeatOwnedRubyParse(label,100,1);
    assert.equal(r.laneCount(label),1,'a new parser pass at the same nonzero primary offset replaces prior lanes');
    const quads=[[10,20,20,20],[35,20,20,20],[55,20,20,20],[45,5,14,14],[85,20,20,20],[105,20,16,16,1]];
    r.setGlyphQuads(label,quads);r.glyphColors(label,quads.map(()=>[.2,.4,.6,.8]));
    r.finishLayout(label);const geometry=r.glyphGeometry(label),colors=r.glyphColors(label);
    // The untranslated prefix preserves native parser advances, while owned
    // glyphs are scaled post-layout. The annotation is placed once from its
    // scaled primary edge; stale lanes would repeat the transform.
    assert.equal(geometry[1][2],16);assert.equal(geometry[2][2],16);
    for(const [actual,expected] of geometry[3].map((value,index)=>[value,[30.6,5.4,11.2,11.2][index]]))
        assert.ok(Math.abs(actual-expected)<1e-6);
    r.finishLayout(label);assert.deepEqual(r.glyphGeometry(label),geometry,'a completed parser pass cannot reuse stale lane geometry');
    assert.deepEqual(geometry[4],quads[4].slice(0,4),'untranslated trailing number stays native');
    assert.deepEqual(geometry[5],quads[5].slice(0,4),'native icon stays native');
    assert.deepEqual(colors[0],[.2,.4,.6,.8]);
    colors[3].forEach((v,i)=>assert.ok(Math.abs(v-[.1,.2,.3,.8][i])<1e-6));
    assert.deepEqual(colors[4],[.2,.4,.6,.8]);assert.deepEqual(colors[5],[.2,.4,.6,.8]);
    assert.equal(r.api.status().failed,false,r.api.status().failureReason);
});

test('log measurement skips unused fixed heights and reuses only matching descriptors',()=>{
    const r=makeRuntime(),pairs={'话':['话','words'],'名字':['名字','name']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85);
    const records=[['名字','话'],['',''],['名字','话\\n第二行']];
    const fixed=r.logMeasure(records,{mode:1});
    assert.equal(fixed.setters,0);assert.deepEqual(fixed.heights,[148,148,148]);assert.equal(fixed.cleanup,3);
    const cold=r.logMeasure(records),warm=r.logMeasure(records,{metric:999});
    assert.equal(cold.setters,5);assert.equal(warm.setters,0,JSON.stringify(r.api.status().logMeasureStats));
    assert.deepEqual(warm.heights,cold.heights);assert.deepEqual(warm.ids,[1,2,3]);assert.equal(warm.cleanup,3);
    assert.equal(r.logMeasure(records,{fontSize:32}).setters,5);
    assert.equal(r.logMeasure(records,{flags:9}).setters,5);
    r.api.style(.8,{ruby_scale:.8});assert.equal(r.logMeasure(records).setters,5);
    const changed={'话':['话','different words'],'名字':['名字','name']};
    r.api.load({pairs:changed,plain_pairs:changed},'annotation',true,.85);
    assert.equal(r.logMeasure(records).setters,2,'changed resolved bodies must be measured while unchanged names remain reusable');
    assert.equal(r.logMeasure(records,{mode:2}).setters,6,'unknown modes must retain native path');
});

test('log descriptor cache preserves current width, resolved identity and resource generations',()=>{
    const r=makeRuntime(),pair=target=>({pairs:{same:['same',target]},plain_pairs:{same:['same',target]}});
    r.api.load({pairs:{},plain_pairs:{},keyed:{TXT_A:{source:'same',model:pair('first')},TXT_B:{source:'same',model:pair('second')}}},'annotation',true,.85);
    r.keyTable(101,'TXT_A','same');r.keyTable(102,'TXT_B','same');
    const records=[['','same']];
    assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,2);
    assert.equal(r.logMeasure(records,{textKeyHash:102}).setters,1,'different body output still measures; the unchanged name may be reused');
    const warm=r.logMeasure(records,{textKeyHash:101,width:1200});
    assert.equal(warm.setters,0);assert.deepEqual(warm.widths,[1200],'window width is always read from the current native template');
    r.fontReload();assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,2);
    r.fontReload(true);assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,2);
    r.api.style(.84,{});
    assert.equal(r.logMeasure(records,{textKeyHash:101,mismatch:true}).setters,2);
    assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,1,'unconfirmed body preview is never admitted');
    assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,0);
    r.api.style(.83,{});
    r.logMeasure(records,{textKeyHash:101,planMismatch:true});
    assert.equal(r.logMeasure(records,{textKeyHash:101}).setters,1,'matching wanted bytes cannot hide a different layer payload');
    r.api.disable();assert.equal(r.logMeasure(records,{mode:1}).setters,2);
});

test('log descriptor cache has bounded size and keeps native fallback for invalid metrics',()=>{
    const r=makeRuntime();r.api.load({pairs:{},plain_pairs:{}},'annotation',true,.85);
    for(const metric of [NaN,Infinity,-1,70000]) {
        r.fontReload();
        r.logMeasure([['','invalid']],{descriptorHeight:metric});
        assert.equal(r.api.status().logHeightCacheSize,0);
    }
    const records=Array.from({length:4100},(_,i)=>['','history-'+i]);
    assert.equal(r.logMeasure(records).setters,4100);
    assert.equal(r.api.status().logHeightCacheSize,4096);
    assert.equal(r.logMeasure([records.at(-1)]).setters,0);
});

test('log measurement retains device-dependent icon callbacks on every open',()=>{
    const r=makeRuntime();r.api.load({pairs:{},plain_pairs:{}},'annotation',true,.85);
    const records=[['name','Press <I12>']];
    assert.equal(r.logMeasure(records).setters,2);
    assert.equal(r.logMeasure(records).setters,2);
    assert.equal(r.api.status().logHeightCacheSize,0);
});

test('log heights survive display-only changes and return to a previously measured language',()=>{
    const r=makeRuntime(),pairs={'话':['话','words'],'名字':['名字','name']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85,{ruby_scale:.9,line_gap:6});
    const records=[['名字','话']];
    const first=r.logMeasure(records);assert.equal(first.setters,2);
    r.api.style(.85,{ruby_scale:.9,line_gap:6,secondary_opacity:.4,secondary_color:[.4,.5,.6],bilingual_offset_y:-2});
    assert.equal(r.logMeasure(records).setters,0,'tint and group offset do not change measured heights');
    r.api.select('primary',true);assert.equal(r.logMeasure(records).setters,2);
    r.api.select('annotation',true);const restored=r.logMeasure(records);
    assert.equal(restored.setters,0,'restoring the same resolved text reuses its validated metrics');
    assert.deepEqual(restored.heights,first.heights);
    r.api.style(.85,{ruby_scale:.8,line_gap:6});
    assert.equal(r.logMeasure(records).setters,2,'ruby size changes the parser metrics');
    r.api.style(.85,{ruby_scale:.9,line_gap:7});
    assert.equal(r.logMeasure(records).setters,2,'line spacing changes the parser metrics');
    r.api.style(.85,{ruby_scale:.9,line_gap:6});
    assert.equal(r.logMeasure(records).setters,0);
    r.fontReload();assert.equal(r.logMeasure(records).setters,2,'resource reload still invalidates all descriptors');
});

test('native ruby measurement scope only surrounds owned simple log template measurements',()=>{
    const r=makeRuntime(null,false,true),pairs={'言':['言','Words'],'人':['人','Name']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85,{ruby_scale:.9});
    r.logMeasure([['人','言']]);
    assert.equal(r.measureScopes.pushes.length,2);
    assert.ok(r.measureScopes.pushes.every(scope=>scope.text.includes('<R>')&&scope.factor===.9));
    assert.deepEqual(r.measureScopes.pops,r.measureScopes.pushes.map(({thread,token})=>({thread,token})));
    const before=r.measureScopes.pushes.length;
    r.logMeasure([['人','言']]); // cached descriptors never enter the measurement path
    r.logMeasure([['人','言']],{flags:4}); // typewriter takes the independent layer path
    r.logMeasure([['','前缀 言 Lv.3']]); // mixed/unowned advances stay on the original hooks
    r.logMeasure([['人','言 <I12>']]); // device-dependent icon rows never acquire this scope
    r.api.select('primary',true);r.logMeasure([['人','言']]);
    r.api.select('annotation',true);
    r.inlinedSet(r.label(0xdb0000,''),'言'); // the shared measuring entry outside MessageLog
    assert.equal(r.measureScopes.pushes.length,before);
    assert.equal(r.api.status().failed,false);
});
