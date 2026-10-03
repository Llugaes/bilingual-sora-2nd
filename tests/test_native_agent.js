'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const AGENT = fs.readFileSync(process.env.NATIVE_AGENT_SOURCE||path.join(__dirname, '..', 'sora_bilingual/game/scripts/native_agent.js'), 'utf8');
const RESOLVER = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_text.js'), 'utf8');
const PARAGRAPHS = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_paragraph.js'), 'utf8');
const IDENTITIES = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_identity.js'), 'utf8');

function makeRuntime(rubyCase = null, diagnostics = false, measureBackend = false) {
    const hooks = new Map();
    const messages = [];
    const allocations = [];
    let threadId = 1;
    let duringSetter=null;
    let logOwnerPointer=null;
    let fontManagerPointer=null;
    const scriptReads=[];
    const memoryCost={scalarReads:0,blockReads:0,scalarWrites:0,blockWrites:0,textReads:0};
    const measureScopes={pushes:[],pops:[]};

    class Pointer {
        constructor(address) { this.address = address; }
        add(offset) { return new Pointer(this.address + offset); }
        sub(other) {return new Pointer(this.address-other.address);}
        readPointer(){if(this.address===0x10002000)return logOwnerPointer;if(this.address===0x10003000)return fontManagerPointer;throw Error('unexpected global pointer');}
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
            if (this.offset === 0x300) return this.label.fontIndex||0;
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
        readFloat() {if(this.label.matrix.has(this.offset))return this.label.matrix.get(this.offset);if(this.offset===0x378)return this.label.progress;if(this.offset===0x2fc)return -12;throw Error('unexpected float field');}
        writeFloat(value) {if(this.label.matrix.has(this.offset)){this.label.matrix.set(this.offset,value);return;}if(this.offset===0x378){this.label.progress=value;return;}throw Error('unexpected float field');}
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
            this.matrix=new Map([[0x18,0],[0x1c,1],[0x20,0],[0x38,0],[0x3c,0],[0x40,0],[0xf4,0]]);
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
        readUtf8String(){const end=this.data.indexOf(0,this.offset);return this.data.subarray(this.offset,end<0?this.data.length:end).toString('utf8');}
    }

    const base = new Pointer(0x10000000);
    const nullPointer = {
        isNull() { return true; },
        toString() { return '0x0'; },
    };
    const REPORT = {
        diagnostics,
        node_names:true,
        log_owner_global:0x2000,
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
            actor_name_set:{rva:0xdd0,bytes:'00000000000000000000000000000000'},
            dialogue_popup:{rva:0xe00,bytes:'00000000000000000000000000000000'},
            dialogue_builder:{rva:0xf00,bytes:'00000000000000000000000000000000'},
            log_write:{rva:0xf10,bytes:'00000000000000000000000000000000'},
            log_write_commit:{rva:0xf20,bytes:'00000000000000000000000000000000'},
            log_write_append_commit:{rva:0xf28,bytes:'00000000000000000000000000000000'},
            log_owner_destroyed:{rva:0xf30,bytes:'00000000000000000000000000000000'},
            log_owner_created:{rva:0xf40,bytes:'00000000000000000000000000000000'},
            log_record_bind:{rva:0xf50,bytes:'00000000000000000000000000000000'},
            log_record_activate:{rva:0xf58,bytes:'00000000000000000000000000000000'},
            log_name_return:{rva:0xf60,bytes:'00000000000000000000000000000000'},
            log_text_return:{rva:0xf70,bytes:'00000000000000000000000000000000'},
            log_present_append:{rva:0xf80,bytes:'00000000000000000000000000000000'},
            log_present_single:{rva:0xf90,bytes:'00000000000000000000000000000000'},
            log_rows_build:{rva:0xfa0,bytes:'00000000000000000000000000000000'},
            log_row_start:{rva:0xfb0,bytes:'00000000000000000000000000000000'},
            log_row_append:{rva:0xfc0,bytes:'00000000000000000000000000000000'},
            log_row_single:{rva:0xfd0,bytes:'00000000000000000000000000000000'},
            log_row_commit:{rva:0xfe0,bytes:'00000000000000000000000000000000'},
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

    function invoke(address, args,returnAddress) {
        const callback = hooks.get(String(address));
        const call={returnAddress};
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
                const nativeScale=rubyCase.nativeScale??.375;
                const values=new Map([[0,rubyCase.x],[4,rubyCase.nativeY??0],[0x158,nativeScale],[0x15c,nativeScale]]);
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

    logOwnerPointer=new RegionPointer(Buffer.alloc(0x200000),0x50000000);
    function writeLog(buffer,slots){
        const owner=logOwnerPointer,leave=invoke(base.add(0xf10),[owner,buffer]);
        for(const [slot,chunk] of Array.isArray(slots)?slots:[[slots,buffer.readUtf8String()]]){
            const at=0x1604ec+slot*0x18c;
            owner.data.fill(0,at,at+0x18c);owner.data.write(chunk,at+0x64,0x120,'utf8');
            const append=slot!==0||owner.data[0x160550+1599*0x18c]!==0;
            // The real writer's append path leaves R8 at the preceding
            // record. RCX advances through the actual copy destination.
            const commit=hooks.get(String(base.add(append?0xf28:0xf20)))||hooks.get(String(base.add(0xf20)));
            commit.onEnter.call({context:{
                rbp:owner,r8:owner.add((append?(slot+1599)%1600:slot)*0x18c),rcx:owner.add(at+0x180)
            }});
        }
        leave();
    }
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
            const pending=records.map((row,i)=>{
                const p=new ScratchPointer(0x460000+i*0x38);
                p.writeS32(row[2]??i);p.add(0x20).writePointer(allocate(row[0]));p.add(8).writePointer(allocate(row[1]));return p;
            });
            const leaveBuild=invoke(base.add(0xfa0),[owner]);
            for(let i=0;i<records.length;i++){
                invoke(base.add(0xfb0),[])();
                const slots=records[i][3]||[records[i][2]??i];
                for(const slot of slots){
                    const input=logOwnerPointer.add(0x160550+slot*0x18c);
                    hooks.get(String(base.add(slots.length>1?0xfc0:0xfd0))).onEnter.call({context:{rbx:new Pointer(slot),r15:new Pointer(slot),rdx:input,rdi:input}});
                }
                hooks.get(String(base.add(0xfe0))).onEnter.call({context:{rbx:pending[i]}});
            }
            leaveBuild();
            const call={};begin?.onEnter.call(call,[owner]);
            const result={setters:0,cleanup:0,heights:[],widths:[],ids:[],bodies:[],names:[]},vmContext=context;
            for(let i=0;i<records.length;i++) {
                const record=pending[i],descriptor=new ScratchPointer(0x470000);
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
                result.bodies.push(body.text());
                result.names.push(name.text());
            }
            // The native destructor tail must run even for every cache hit.
            result.cleanup=records.length;
            begin?.onLeave.call(call);
            assert.equal(sandbox.rpc.exports.status().failed,false,JSON.stringify(sandbox.rpc.exports.status()));
            return result;
        },
        actorName(actorAddress,data,offset,source,oldActor=null) {
            const actor=oldActor||new ScratchPointer(actorAddress), input=data?new RegionPointer(data).add(offset):allocate(source);
            const leave=invoke(base.add(0xdd0),[actor,input,new Pointer(0)]);
            const copy=allocate(source);actor.add(0x2c0).writePointer(copy);actor.add(0x2cc).writeS32(Buffer.byteLength(source));
            leave();return {actor,copy};
        },
        actorNameFlags(actor){invoke(base.add(0xdd0),[actor,nullPointer,new Pointer(1)])();},
        setFromPointer(label,input){const args=[label,input],leave=invoke(base.add(0x100),args);copyIntoLabel(label,args[1]);leave();},
        dialogueSet(label,text,data,functionName,values,logSlot,site) {
            const machine=new ScratchPointer(0x34000000),object=new ScratchPointer(0x35000000),stack=new ScratchPointer(0x36000000);
            object.values.set(0,new RegionPointer(data));machine.values.set(8,object);
            machine.values.set(0x88,allocate(functionName));machine.values.set(0x70,values.length);
            machine.values.set(0x64,values.length*4);machine.values.set(0x58,stack);
            if(site)for(const [field,value] of [[0x10,site.pc],[0x68,site.group],[0x6c,site.command]])machine.values.set(field,value);
            values.forEach((v,i)=>stack.values.set((values.length-i-1)*4,v));
            const buffer=allocate(text),leaveHandler=invoke(base.add(0xe00),[]);
            const leaveBuilder=invoke(base.add(0xf00),[nullPointer,buffer,nullPointer,machine]);leaveBuilder();
            const args=[label,buffer],leaveSetter=invoke(base.add(0x100),args);
            copyIntoLabel(label,args[1]);leaveSetter();
            if(logSlot!==undefined)writeLog(buffer,logSlot);
            leaveHandler();
            assert.equal(buffer.text,text,'fixed-size builder output must stay unchanged');
            return buffer;
        },
        logWrite(text,slot){writeLog(allocate(text),slot);},
        logRestore(text,slot,speaker,marker=0){
            const at=0x1604ec+slot*0x18c;
            logOwnerPointer.data.fill(0,at,at+0x18c);
            logOwnerPointer.data.writeUInt32LE(marker,at);
            logOwnerPointer.data.write(speaker,at+4,0x60,'utf8');
            logOwnerPointer.data.write(text,at+0x64,0x124,'utf8');
        },
        logMutateRecord(slot,offset,value){logOwnerPointer.data.writeUInt8(value,0x1604ec+slot*0x18c+offset);},
        logReset(){invoke(base.add(0xf40),[])();},
        logNameShow(label,slot,text,slots=[slot]){
            const controller=new ScratchPointer(0x480000);controller.add(0x18).writePointer(label);
            const leaveFrame=invoke(base.add(0xf50),[controller,new Pointer(slot)]);
            for(const piece of slots){
                const input=logOwnerPointer.add(0x160550+piece*0x18c);
                hooks.get(String(base.add(slots.length>1?0xf80:0xf90))).onEnter.call({context:{rbx:new Pointer(slots.length-1),rax:new Pointer(piece),rdx:input,rdi:input}});
            }
            const args=[label,allocate(text)],leave=invoke(base.add(0x100),args,base.add(0xf60));
            copyIntoLabel(label,args[1]);leave();leaveFrame();
        },
        logShow(label,slot,text,slots=[slot],nodes=null){
            const controller=new ScratchPointer(0x480000);controller.add(0x18).writePointer(label);controller.add(0x38).writeS32(slot);
            if(nodes){
                const parent=new ScratchPointer(0x480100),frame=new ScratchPointer(0x480200);
                parent.add(0x1c).writeFloat(1);
                frame.add(0x80).writePointer(parent);frame.add(0x2dc).writeFloat(nodes.height);
                frame.add(0x2e0).writeS32(nodes.anchor||0);frame.add(0xf4).writeFloat(nodes.frameY||0);
                controller.add(8).writePointer(frame);controller.add(0x10).writePointer(nodes.name);
                controller.add(0x88).writeS32(nodes.mode||0);
                nodes.name.parent=label.parent=parent;
                nodes.name.matrix.set(0xf4,9);label.matrix.set(0xf4,nodes.bodyY??48);
                nodes.name.matrix.set(0x3c,409);label.matrix.set(0x3c,400+(nodes.bodyY??48));
                nodes.name.logBottom=nodes.nameBottom??28;label.logBottom=nodes.bodyBottom;
            }
            const leaveFrame=invoke(base.add(0xf50),[controller,new Pointer(slot)]);
            for(const piece of slots){
                const input=logOwnerPointer.add(0x160550+piece*0x18c);
                hooks.get(String(base.add(slots.length>1?0xf80:0xf90))).onEnter.call({context:{rbx:new Pointer(slots.length-1),rax:new Pointer(piece),rdx:input,rdi:input}});
            }
            const args=[label,allocate(text)],leave=invoke(base.add(0x100),args,base.add(0xf70));
            copyIntoLabel(label,args[1]);leave();leaveFrame();
            return controller;
        },
        logActivate(controller){invoke(base.add(0xf58),[controller])();},
        externalBuffer(label,buffer) {
            const args=[label,buffer],leave=invoke(base.add(0x100),args);copyIntoLabel(label,args[1]);leave();
        },
        registerLayout(root,id){
            const layout=new ScratchPointer(0x718000);layout.add(0x80).writeS32(id);layout.add(0xa8).writePointer(root);
            sandbox.testLayout=layout;vm.runInContext('registerLayout(testLayout)',context);delete sandbox.testLayout;
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
            parser.add(0x1ab).writeU8(geometry.measuring?1:0);
            parser.add(0x1bc).writeS32(0x7fffffff);parser.add(0x1c4).writeS32(-0x80000000);
            parser.values.set(8,label.add(0x318).readPointer().add(layer.offset));
            parser.add(0x158).writeFloat(geometry.primaryScale??1);
            parser.add(0x15c).writeFloat(geometry.primaryScale??1);
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
            const recordReading=(parent,height)=>{
                if(!height)return;
                const nestedFrame=new ScratchPointer(0x870000);
                nestedFrame.add(0x178).writeS32(0);nestedFrame.add(0x17c).writeS32(0);
                nestedFrame.add(0x180).writeS32(12);nestedFrame.add(0x184).writeS32(height);
                hooks.get(String(base.add(0xb00))).onEnter.call({context:{r15:label,rbx:parent,rbp:nestedFrame}});
            };
            recordReading(measureContext,geometry.primaryReadingHeight);
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
                const nativeScale=geometry.nativeScale??.375;
                child.add(0x158).writeFloat(nativeScale);child.add(0x15c).writeFloat(nativeScale);
                const call={returnAddress:base.add(placement?0x700:0x800),context:machine};
                const args=[child,allocate('_'),new Pointer(1)];
                init.onEnter.call(call,args);init.onLeave.call(call);
                const ph=hooks.get(String(base.add(0xd00))),parseCall={};
                child.add(0x1a5).writeU8(1);ph.onEnter.call(parseCall,[label,child]);
                if(!placement)recordReading(child,geometry.secondaryReadingHeight);
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
                reservedTop:parser.add(0x1bc).readS32(),reservedBottom:parser.add(0x1c4).readS32(),
                bounds:[0x3c8,0x3cc,0x3d0,0x3d4].map(v=>frame.add(v).readS32())};
        },
        layerSizeContext(label,index=0,{primaryScale=1,absoluteSize=1.5,nativeScale=.375,fontBase=null}={}) {
            if(fontBase!==null) {
                REPORT.font_manager_global=0x3000;
                fontManagerPointer=new ScratchPointer(0x723000);
                const fonts=new ScratchPointer(0x724000),font=new ScratchPointer(0x725000);
                fontManagerPointer.add(8).writePointer(fonts);fontManagerPointer.add(0x10).writeS32(1);
                fonts.writePointer(font);font.add(0x28).writeS32(fontBase);
            }
            const row=sandbox.rpc.exports.snapshot().find(v=>v.original===label.originalForTest||v.displayed===label.text());
            const layer=row.layers[index],parser=new ScratchPointer(0x720000),target=new ScratchPointer(0x721000);
            parser.values.set(8,label.add(0x318).readPointer().add(layer.offset));
            parser.add(0x158).writeFloat(primaryScale);parser.add(0x15c).writeFloat(primaryScale);
            target.add(0x158).writeFloat(nativeScale);target.add(0x15c).writeFloat(nativeScale);
            const initializer=hooks.get(String(base.add(0x600))),call={returnAddress:base.add(0x800),context:{r15:label,rbx:parser,rbp:new ScratchPointer(0x722000)}};
            initializer.onEnter.call(call,[target,allocate('_'),new Pointer(1)]);
            initializer.onLeave.call(call);
            const scope=vm.runInContext('auxiliaryContexts.get('+JSON.stringify(String(target))+')',context);
            const factor=scope?.factor,sizeFactor=scope?.sizeFactor??factor;
            return {layer:layer.text,factor,sizeFactor,initial:target.add(0x15c).readFloat(),
                emphasized:absoluteSize*sizeFactor,primary:absoluteSize};
        },
        nestedRubyScale(label,index=0,{nativeScale=.375,emphasizedScale=null,primaryScale=25/29}={}) {
            const row=sandbox.rpc.exports.snapshot().find(v=>v.original===label.originalForTest||v.displayed===label.text());
            const layer=row.layers[index],parser=new ScratchPointer(0x730000),frame=new ScratchPointer(0x740000);
            parser.values.set(8,label.add(0x318).readPointer().add(layer.offset));
            parser.add(0x158).writeFloat(primaryScale);
            parser.add(0x15c).writeFloat(primaryScale);
            const initializer=hooks.get(String(base.add(0x600))),parent=new ScratchPointer(0x750000),parentArgs=[parent,allocate('_'),new Pointer(1)];
            parent.add(0x158).writeFloat(nativeScale);parent.add(0x15c).writeFloat(nativeScale);
            const parentCall={returnAddress:base.add(0x800),context:{r15:label,rbx:parser,rbp:frame}};
            initializer.onEnter.call(parentCall,parentArgs);initializer.onLeave.call(parentCall);
            const factorOf=pointer=>vm.runInContext('auxiliaryContexts.get('+JSON.stringify(String(pointer))+')?.factor',context);
            const parentFactor=factorOf(parent);
            // The verified S/s tail resets this to an absolute label scale and
            // the native parser applies parentFactor afterwards. Simulate that
            // sequence before a nested native reading is initialized.
            if(emphasizedScale!==null) {
                parent.add(0x158).writeFloat(emphasizedScale);
                parent.add(0x15c).writeFloat(emphasizedScale);
            }
            parent.add(4).writeFloat(100);
            const child=new ScratchPointer(0x760000),childArgs=[child,allocate('_'),new Pointer(1)];
            // The native R handler derives xmm6 from the global ruby font
            // size, independently of its parent's current float fields.
            child.add(0x158).writeFloat(nativeScale);
            child.add(0x15c).writeFloat(nativeScale);
            child.add(4).writeFloat(80);
            const childCall={returnAddress:base.add(0x700),context:{r15:label,rbx:parent,rbp:frame}};
            initializer.onEnter.call(childCall,childArgs);initializer.onLeave.call(childCall);
            const childFactor=factorOf(child);
            const grandchild=new ScratchPointer(0x770000),grandchildArgs=[grandchild,allocate('_'),new Pointer(1)];
            grandchild.add(0x158).writeFloat(nativeScale);
            grandchild.add(0x15c).writeFloat(nativeScale);
            grandchild.add(4).writeFloat(80);
            const grandchildCall={returnAddress:base.add(0x700),context:{r15:label,rbx:child,rbp:frame}};
            initializer.onEnter.call(grandchildCall,grandchildArgs);initializer.onLeave.call(grandchildCall);
            const grandchildFactor=factorOf(grandchild);
            return {parent:parent.add(0x15c).readFloat(),child:child.add(0x15c).readFloat(),
                grandchild:grandchild.add(0x15c).readFloat(),parentFactor,childFactor,grandchildFactor,
                childY:child.add(4).readFloat(),grandchildY:grandchild.add(4).readFloat()};
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
        projectedUpdate(label){
            const leave=invoke(base.add(REPORT.native.update.rva),[label]);
            hooks.get(String(base.add(0x380))).onEnter.call({context:{rsi:label}});
            const y=label.add(0x3c).readFloat();
            // A repeated layout callback in one Update must not add again.
            hooks.get(String(base.add(0x380))).onEnter.call({context:{rsi:label}});
            assert.equal(label.add(0x3c).readFloat(),y);leave();return y;
        },
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

test('copied map spot labels resolve across modes without changing unrelated names',()=>{
    const r=makeRuntime(),label=r.label(0x4344,'神秘森林');label.name='spot_name';
    r.api.load({pairs:{},plain_pairs:{},scoped:{map_spot:{pairs:{'神秘森林':['神秘森林','ミストヴァルト']},plain_pairs:{'神秘森林':['神秘森林','ミストヴァルト']}}}},'annotation',true,1);
    r.externalSet(label,'神秘森林');assert.equal(label.text(),'<R>神秘森林</Rミストヴァルト>');
    const other=r.label(0x4345,'神秘森林');r.externalSet(other,'神秘森林');assert.equal(other.text(),'神秘森林');
    r.api.select('secondary',true);r.update(label);assert.equal(label.text(),'ミストヴァルト');
    r.api.disable();r.update(label);assert.equal(label.text(),'神秘森林');
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
        assert.equal(scaled[0][2],8);assert.equal(scaled[1][2],6,'secondary already has its parser scale');
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

test('native reading inside a secondary layer scales relative to its parent',()=>{
    const a='完成总计25件委托并汇报。',b='計２５件の<R>依頼</Rいらい>を達成して報告する。';
    const runtime=makeRuntime();runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85);
    const label=runtime.label(0x4671,a);runtime.update(label);
    const scales=runtime.nestedRubyScale(label);
    assert.ok(Math.abs(scales.parent-.3)<1e-6);
    assert.ok(Math.abs(scales.child-.1125)<1e-6,'native nested reading starts from the engine baseline times its parent multiplier');
    assert.ok(Math.abs(scales.grandchild-.0421875)<1e-6,'a deeper reading must use its own parent multiplier');
    assert.ok(Math.abs(scales.grandchildY-(scales.childY+(80-scales.childY)*scales.child))<1e-6,
        'a deeper reading must retain the preceding auxiliary context');
    assert.equal(runtime.api.status().failed,false);
});

test('emphasis before a native reading does not become its fixed multiplier',()=>{
    const a='完成总计25件委托并汇报。',b='<S5>計２５件の<R>依頼</Rいらい>を達成して報告する。';
    const runtime=makeRuntime();runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85);
    runtime.api.style(.85,{ruby_scale:.9});
    const label=runtime.label(0x4672,a);runtime.update(label);
    // Native ruby .5 times the user .9 is the stable annotation multiplier.
    // After S5 the parent is .675. The nested reading still begins at the
    // native .5 baseline and uses the stable .45 parent multiplier.
    const scales=runtime.nestedRubyScale(label,0,{nativeScale:.5,emphasizedScale:.675});
    assert.ok(Math.abs(scales.parent-.675)<1e-6);
    assert.ok(Math.abs(scales.parentFactor-.45)<1e-6);
    assert.ok(Math.abs(scales.child-.225)<1e-6);
    assert.ok(Math.abs(scales.grandchild-.1125)<1e-6);
    assert.ok(Math.abs(scales.childFactor-.225)<1e-6,'a nested reading must register its own multiplier after S5');
    assert.ok(Math.abs(scales.grandchildFactor-.1125)<1e-6,'a deeper native reading must register its own multiplier after S5');
    assert.equal(runtime.api.status().failed,false);
});

test('layered S/C dialogue keeps native ruby baseline and source emphasis ratio',()=>{
    const primary='<#E_0#M_0#B_0><S3><C2>外公～\n２楼我整理好了。';
    const secondary='<#E_0#M_0#B_0><C2><S3>おじいちゃ～ん。\n２階のお片付けは終わったよ。';
    const runtime=makeRuntime(),label=runtime.label(0x4673,primary,0,32);
    runtime.api.load({pairs:{[primary]:[primary,secondary]},plain_pairs:{[primary]:[primary,secondary]}},'annotation',true,.85,{ruby_scale:.9});
    runtime.externalSet(label,primary);
    const result=runtime.layerSizeContext(label,0,{primaryScale:1,nativeScale:.5});
    assert.match(result.layer,/^<C2><S3>おじいちゃ～/,'the real target tag order remains C then S');
    assert.ok(Math.abs(result.initial-.45)<1e-6,`normal ruby size ${result.initial}`);
    assert.ok(Math.abs(result.factor-.45)<1e-6,`layer S/s factor ${result.factor}`);
    assert.ok(Math.abs(result.primary-1.5)<1e-6);
    assert.ok(Math.abs(result.emphasized-.675)<1e-6);
    assert.ok(Math.abs(result.emphasized/result.primary-.45)<1e-6);
    assert.equal(runtime.api.status().failed,false);
});

test('layered S5 dialogue keeps the same native emphasis ratio in both languages',()=>{
    const primary='<S5>艾丝蒂尔姐姐！',secondary='<S5>エステルお姉ちゃんっ！';
    const runtime=makeRuntime(),label=runtime.label(0x4674,primary,0,32);
    runtime.api.load({pairs:{[primary]:[primary,secondary]},plain_pairs:{[primary]:[primary,secondary]}},'annotation',true,.85,{ruby_scale:.9});
    runtime.externalSet(label,primary);
    const result=runtime.layerSizeContext(label,0,{primaryScale:1,nativeScale:.5});
    assert.equal(result.layer,secondary);
    assert.ok(Math.abs(result.initial-.45)<1e-6);
    assert.ok(Math.abs(result.factor-.45)<1e-6);
    assert.ok(Math.abs(result.primary-1.5)<1e-6);
    assert.ok(Math.abs(result.emphasized-.675)<1e-6);
    assert.equal(runtime.api.status().failed,false);
});

test('colour-only layered text keeps the ordinary native ruby size',()=>{
    const primary='完成总计<C3>25件</C>委托并汇报。';
    const secondary='計<C3>２５件</C>のクエストを達成して報告する。';
    const runtime=makeRuntime(),label=runtime.label(0x4675,primary,0,32);
    runtime.api.load({pairs:{[primary]:[primary,secondary]},plain_pairs:{[primary]:[primary,secondary]}},'annotation',true,.85,{ruby_scale:.9});
    runtime.externalSet(label,primary);
    const result=runtime.layerSizeContext(label,0,{primaryScale:27/32,absoluteSize:1,nativeScale:.5});
    assert.match(result.layer,/^計<C3>２５件/);
    assert.ok(Math.abs(result.initial-.45)<1e-6);
    assert.ok(Math.abs(result.factor-.45)<1e-6);
    assert.ok(Math.abs(result.primary-1)<1e-6);
    assert.equal(runtime.api.status().failed,false);
});

test('ordinary, colour-layer, S3 and S5 secondary text share the native ruby ratio',()=>{
    // Fixed fixture scales exercise the plain-ruby, synthetic-layer and
    // absolute-S callback routes with the same visible glyph. Actual native
    // scales depend on the font and label; this is not a live glyph-size
    // comparison or proof of a new font fix.
    const plainCase={x:0,nativeScale:.5};
    const plain=makeRuntime(plainCase),plainSource='甲',plainTarget='乙';
    const plainLabel=plain.label(0x4677,plainSource,0,32);
    plain.api.configure({[plainSource]:`<R>${plainSource}</R${plainTarget}>`},true);
    plain.api.style(.85,{ruby_scale:.9});
    plain.update(plainLabel);
    assert.match(plainLabel.text(),/<R>/,`plain annotated output ${plainLabel.text()}`);
    assert.ok(Math.abs(plainCase.scale-.45)<1e-6,`ordinary ruby ${plainCase.scale}`);

    const layer=(source,target,primaryScale)=>{
        const runtime=makeRuntime(),label=runtime.label(0x4678,source,0,32);
        runtime.api.load({pairs:{[source]:[source,target]},plain_pairs:{[source]:[source,target]}},
            'annotation',true,.85,{ruby_scale:.9});
        runtime.externalSet(label,source);
        return runtime.layerSizeContext(label,0,{primaryScale,nativeScale:.5});
    };
    const colour=layer('<C2>甲</C>','<C2>乙</C>',27/32);
    const s3=layer('<S3>甲','<S3>乙',1);
    const s5=layer('<S5>甲','<S5>乙',1);
    for(const result of [colour,s3,s5]) {
        assert.ok(Math.abs(result.initial-.45)<1e-6,`layer ruby ${result.initial}`);
        assert.ok(Math.abs(result.factor-.45)<1e-6,`layer factor ${result.factor}`);
    }
    for(const result of [s3,s5])
        assert.ok(Math.abs(result.emphasized/result.primary-.45)<1e-6,
            `S secondary ratio ${result.emphasized/result.primary}`);
});

test('equipment replacement keeps every real C/icon reflow layer at the native ruby size',()=>{
    // table/t_text.tbl/TXT_CAMP_EQUIP_CHANGE_CHOICES after its two native
    // string arguments have been expanded.  The target has a different line
    // split, so RuntimeText creates three synthetic layers: C-only, C+icon,
    // then C-only.  C does not make a ruby child; every layer must instead
    // begin from the engine's ruby baseline before ruby_scale is applied.
    const source='<C2>克萝赛</C><C1>装备中的</C>\n<I123> <C2>猫咪靴</C>\n <C1>将会被卸下，确定要继续吗？</C>';
    const primary='<C2>クローゼ</C><C1>が装備中の</C>\n<I123> <C2>にゃんこブーツ</C> <C1>が\n外されますがよろしいですか？</C>';
    const runtime=makeRuntime(),label=runtime.label(0x4676,source,0,32);
    runtime.api.load({pairs:{[source]:[primary,source]},plain_pairs:{[source]:[primary,source]}},
        'annotation',true,.85,{ruby_scale:.9});
    runtime.externalSet(label,source);
    const row=runtime.api.snapshot().find(v=>v.original===source);
    assert.equal(row.presentation,'layered');
    assert.deepEqual(Array.from(row.layers,layer=>layer.text),[
        '<C2>克萝赛</C><C1>装备中的</C>',
        '<I123> <C2>猫咪靴</C> <C1>将会被</C>',
        '<C1>卸下，确定要继续吗？</C>',
    ]);
    const nativePrimary=27/32, expected=.375*.9;
    for(const index of [0,1,2]) {
        const result=runtime.auxiliary(label,index,{primaryScale:nativePrimary,iconCallback:index===1});
        // The measurement and placement callbacks are the real layer entry
        // sequence; both retain the ordinary native-ruby baseline.
        for(const callback of result.results)
            assert.ok(Math.abs(callback.scale-expected)<1e-6,
                `layer ${index} callback began at ${callback.scale}, expected ${expected}`);
        assert.equal(result.results[1].iconCallback,index===1);
    }
    assert.equal(runtime.api.status().failed,false,runtime.api.status().failureReason);
});

test('Chinese-primary equipment confirmation retains ruby scaling after Japanese reflow',()=>{
    const source='<C2>克萝赛</C><C1>装备中的</C>\n<I123> <C2>猫咪靴</C>\n <C1>将会被卸下，确定要继续吗？</C>';
    const secondary='<C2>クローゼ</C><C1>が装備中の</C>\n<I123> <C2>にゃんこブーツ</C> <C1>が\n外されますがよろしいですか？</C>';
    const runtime=makeRuntime(),label=runtime.label(0x4679,source,0,32);
    runtime.api.load({pairs:{[source]:[source,secondary]},plain_pairs:{[source]:[source,secondary]}},
        'annotation',true,.85,{ruby_scale:.9});
    runtime.externalSet(label,source);
    const row=runtime.api.snapshot().find(v=>v.original===source);
    assert.equal(row.presentation,'layered');assert.equal(row.layers.length,3);
    for(let index=0;index<row.layers.length;index++) {
        const icons=row.layers[index].text.includes('<I');
        const result=runtime.auxiliary(label,index,{primaryScale:27/32,iconCallback:icons});
        for(const callback of result.results)
            assert.ok(Math.abs(callback.scale-.375*.9)<1e-6,
                `Japanese layer ${index} changed native ruby scale to ${callback.scale}`);
        assert.equal(result.results[1].iconCallback,icons);
    }
    assert.equal(runtime.api.status().failed,false,runtime.api.status().failureReason);
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

test('original ruby text and emphasis survive a separately owned lane',()=>{
    for(const a of ['来到<R>女神</R爱德斯>身旁。','<R>绝对不行</R・・・・>']) {
        const b='<R>女神</Rエイドス>の傍へ。';const runtime=makeRuntime();
        runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
        const label=runtime.label(0x9990,'',0,32);runtime.externalSet(label,a);
        assert.equal(label.text(),'<R></R_>'+a);
        const result=runtime.auxiliary(label);
        assert.deepEqual(result.bounds,[0,0,0,0]);
        assert.equal(result.primaryX,20);assert.equal(result.primaryY,100);
        assert.equal(result.duringCompensation,1);assert.equal(result.restoredCompensation,0);
        for(const [i,v] of result.results.entries()) {
            assert.equal(v.text,b);assert.equal(v.count,[...b].length);
            assert.equal(v.nestedRubyDisabled,0,'owned original readings participate in both measure and draw');
            assert.ok(Math.abs(v.scale-(.375*.8))<1e-8,
                'an auxiliary layer keeps the engine ruby baseline before user ruby_scale');
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

test('recovery release preserves 0.3.33 multiline origins instead of reserving whole child bounds',()=>{
    // Regression boundary: the withdrawn reserve affected every layered
    // multiline label, including menus, tutorial popups and NPC bubbles.
    for(const measuring of [false,true])for(const flags of [65,789,865]) {
        const r=makeRuntime(),a='<C1>标题\n第一行<I4>\n第二行',b='<C1>見出し\n一行目<I4>\n二行目';
        const p=r.label(0x9969,a,0,33);p.flags=flags;
        r.api.load({pairs:{[a]:[a,b]}},'annotation',true,.85,{ruby_scale:.9,ruby_gap:0,line_gap:6});r.update(p);
        for(let pass=0;pass<3;pass++)for(const [line,bottom] of [18,240,2137].entries()) {
            const origin=100+line*45;
            const out=r.auxiliary(p,line,{origin,measuring,bottom});
            assert.equal(out.primaryY,origin,'a child envelope must not enlarge the menu/paragraph baseline');
        }
        assert.equal(r.api.status().failed,false);
        r.api.select('primary',true);r.update(p);assert.equal(p.text(),a);
        r.api.select('secondary',true);r.update(p);assert.equal(p.text(),b);
        r.api.disable();r.update(p);assert.equal(p.text(),a);
    }
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
    const manifest={[signature]:[{size:data.length,sha256:scriptSha256(data),functions:['Talk']}]};
    runtime.api.load({...make('承知。'),script_identities:{scripts:{},manifest}},'annotation',true,1);
    runtime.dialogueSet(label,'好。',data,'Talk',[1,3221226000]);assert.match(label.text(),/承知。/);
    assert.equal(runtime.scriptReads.filter(n=>n===data.length).length,hashes+1,'source provenance is retained even when the current global pair is complete');
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

function historyFixture(source='相同的完整对白。') {
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const r=makeRuntime(),data=Buffer.alloc(128);data.write('#scp');data.writeUInt32LE(24,4);data.writeUInt32LE(1,8);
    const signature=Buffer.concat([data.subarray(0,24),data.subarray(24,56),data.subarray(24,56)]).toString('hex');
    const local=target=>({pairs:{[source]:[source,target]},plain_pairs:{[source]:[source,target]},numeric:[]});
    r.api.load({pairs:{},plain_pairs:{},script_identities:{scripts:{[signature]:[{size:data.length,sha256:scriptSha256(data),functions:{Talk:{model:{pairs:{},plain_pairs:{}},calls:{
        '1,36':{model:local('一つ目の台詞。')},'1,151':{model:local('二つ目の台詞。')}
    }}}}]}}},'secondary',true,1);
    const p=r.label(0xab00,'');
    return {r,source,write:(call,slots)=>r.dialogueSet(p,source,data,'Talk',[1,call],slots)};
}

test('history captures IDs before a later language introduces a translation conflict',()=>{
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const r=makeRuntime(),source='啊，说的也是呢。',data=Buffer.alloc(128);
    data.write('#scp');data.writeUInt32LE(24,4);data.writeUInt32LE(1,8);
    const signature=Buffer.concat([data.subarray(0,24),data.subarray(24,56),data.subarray(24,56)]).toString('hex');
    const sha256=scriptSha256(data),manifest={[signature]:[{size:data.length,sha256,functions:['Talk']}]};
    const sharedPairs={[source]:[source,'あ、そうだったわね。']};
    const shared={pairs:sharedPairs,plain_pairs:sharedPairs};
    r.api.load({...shared,script_identities:{scripts:{},manifest}},'secondary',true,1);
    const live=r.label(0xab00,'');
    r.dialogueSet(live,source,data,'Talk',[1,36],7);
    r.dialogueSet(live,source,data,'Talk',[1,151],8);
    assert.equal(live.text(),'あ、そうだったわね。');
    assert.equal(r.api.status().logOriginSlots,2,'capture must not depend on the current language conflict set');
    const row=r.label(0xac00,'');
    r.logShow(row,8,source);assert.equal(row.text(),'あ、そうだったわね。');
    const local=target=>({pairs:{[source]:[source,target]},plain_pairs:{[source]:[source,target]}});
    r.api.load({pairs:{},plain_pairs:{},ambiguous_display:[source],script_identities:{manifest,scripts:{
        [signature]:[{size:data.length,sha256,functions:{Talk:{model:{pairs:{},plain_pairs:{}},calls:{
            '1,36':{model:local('Oh, right.')},'1,151':{model:local('Oh, I almost forgot!')}
        }}}}]
    }}},'secondary',true,1);
    r.update(row);assert.equal(row.text(),'Oh, I almost forgot!','already visible history must retain its ID across reload');
    r.logShow(row,7,source);assert.equal(row.text(),'Oh, right.');
    r.logShow(row,8,source);assert.equal(row.text(),'Oh, I almost forgot!');
    assert.equal(r.logMeasure([['',source,7]]).bodies[0],'Oh, right.');
    assert.equal(r.logMeasure([['',source,8]]).bodies[0],'Oh, I almost forgot!');
    r.api.select('annotation',true);r.update(row);
    assert.match(row.text(),/Oh, I almost forgot!/);
    assert.equal(r.api.status().failed,false);
});

test('absolute size commands use a relative ruby ratio when label and font sizes differ',()=>{
    const primary='<#E_0#M_0#B_0><S5>Ｙｅｓ　Ｓｉｒ！',secondary='<#E_0#M_0#B_0><S5>イエス・サー！';
    for(const fontBase of [32,48,64])for(const labelSize of [26,32]) {
        const runtime=makeRuntime(),label=runtime.label(0x4676,primary,0,labelSize);
        runtime.api.load({pairs:{[primary]:[primary,secondary]}},'annotation',true,.85,{ruby_scale:.8});
        runtime.externalSet(label,primary);
        const result=runtime.layerSizeContext(label,0,{fontBase,nativeScale:18/fontBase,
            primaryScale:labelSize/fontBase,absoluteSize:48/fontBase});
        assert.ok(Math.abs(result.initial-18/fontBase*.8)<1e-6,'ordinary native reading scale stays unchanged');
        assert.ok(Math.abs(result.factor-result.initial)<1e-6,'nested readings still inherit the actual parent scale');
        assert.ok(Math.abs(result.emphasized/result.initial-48/labelSize)<1e-6,
            `font=${fontBase}, label=${labelSize}: S5 must amplify secondary by the same factor as primary`);
    }
});

test('emphasis survives the complete annotation glyph pass at every size and reveal mode',()=>{
    // 2026-09-29 layout 7 capture: label 33, font base 48, S5 primary 37,
    // ruby 18, ruby_scale .9, annotation_scale .85. Testing only the size
    // callback missed the second shrink in finishAnnotationLanes.
    const commands=[... [12,24,28,33,37,48,64,96].map(pixels=>[`<s${pixels}>`,pixels]),['<S5>',37]];
    for(const animated of [false,true])for(const labelSize of [26,32,33,48])
        for(const fontBase of [32,48,64])for(const [command,pixels] of commands) {
            const header='<#L[1#107w7]#G[6]#M_2#B_0#S[1]>';
            const r=makeRuntime(),source=header+command+'……吵死了，闭嘴！',target=header+command+'……うるさい、黙れ！';
            const label=r.label(0x467a,source,0,labelSize);
            if(animated)label.flags|=4;
            r.api.load({pairs:{[source]:[source,target]}},'annotation',true,.85,{ruby_scale:.9});
            r.externalSet(label,source);
            const metric=r.layerSizeContext(label,0,{fontBase,nativeScale:18/fontBase,
                primaryScale:labelSize/fontBase,absoluteSize:pixels/fontBase});
            // Feed the parser's resulting same-character geometry through the
            // production layer registration and final glyph correction.
            r.auxiliary(label,0,{secondaryCount:1,primaryUnits:1,glyphQuads:[
                [10,0,metric.emphasized*fontBase,metric.emphasized*fontBase],
                [10,40,pixels,pixels],
            ]});
            label.revealUnits=1;
            const output=r.glyphLayout(label),secondary=output[0][2],primary=output[1][2];
            const expected=18*.9*pixels/labelSize;
            assert.ok(Math.abs(secondary-expected)<.0001,
                `animated=${animated}, label=${labelSize}, font=${fontBase}, pixels=${pixels}: ${secondary} != ${expected}`);
            assert.ok(Math.abs(primary-pixels*.85)<.0001,'primary retains configured shrink');
            assert.deepEqual(r.glyphLayout(label),output,'repeat frames never compound either scale');
        }
});

test('native readings reserve a plus a-prime above every owned line including the first',()=>{
    const a='<R>刺激</R香辛料>是首行。\n再来<R>刺激</R香辛料>。',b='<R>刺激</Rスパイス>だ。\nまた<R>刺激</Rスパイス>。';
    for(const measuring of [false,true]) {
        const r=makeRuntime();r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85);
        const p=r.label(0xb690,a,0,32);r.update(p);
        for(const index of [0,1])for(let rebuild=0;rebuild<3;rebuild++) {
            const origin=100+index*80;
            const out=r.auxiliary(p,index,{origin,measuring,primaryReadingHeight:18,secondaryReadingHeight:5});
            const expected=origin+18*.85+5;
            assert.ok(Math.abs(out.primaryY-expected)<1e-4,`line ${index}, measuring=${measuring}: ${out.primaryY} != ${expected}`);
            assert.equal(out.reservedTop,origin,'leading reserve belongs to the measured paragraph even on its first line');
            assert.equal(out.reservedBottom,Math.ceil(expected));
        }
        assert.equal(r.api.status().failed,false);
    }
});

test('primary and secondary reading reserves are independent and absent readings add nothing',()=>{
    for(const mainReading of [false,true])for(const secondaryReading of [false,true])for(const measuring of [false,true]) {
        const a='<C1>'+(mainReading?'<R>字</Rじ>':'字')+'</C>',b=secondaryReading?'<R>語</Rご>':'word';
        const r=makeRuntime();r.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.85,{line_gap:4});
        const p=r.label(0xb695,a,0,32);r.update(p);
        assert.equal(r.newline(p,100),104,'base line gap x is independent of reading reserves');
        const out=r.auxiliary(p,0,{origin:100,measuring,primaryReadingHeight:mainReading?18:0,secondaryReadingHeight:secondaryReading?5:0});
        // Primary native ruby selects post-geometry scale. Secondary-only ruby
        // keeps the existing main <s> path, so its measured reading is final.
        const extra=(mainReading?18*.85:0)+(secondaryReading?5:0);
        assert.ok(Math.abs(out.primaryY-(100+extra))<1e-4,`${mainReading}/${secondaryReading}/${measuring}`);
        assert.equal(r.api.status().failed,false);
    }
});

test('activating an already bound history row reconciles its retained physical record',()=>{
    const {r,source,write}=historyFixture();
    write(36,7);
    r.api.select('primary',true);
    const row=r.label(0xab80,''),controller=r.logShow(row,7,source);
    assert.equal(row.text(),source,'a row materialized in primary mode remains native');
    r.api.select('secondary',true);
    r.logActivate(controller);
    assert.equal(row.text(),'一つ目の台詞。');
    assert.equal(r.api.status().failed,false);
});

test('history activation rejects stale ownership, row ids, payloads and origins',()=>{
    const {r,source,write}=historyFixture();
    write(36,7);r.api.select('primary',true);
    const row=r.label(0xaba0,''),controller=r.logShow(row,7,source);
    r.api.select('secondary',true);

    controller.add(0x38).writeS32(8);r.logActivate(controller);
    assert.equal(row.text(),source,'a reused controller must still own the bound ring slot');
    controller.add(0x38).writeS32(7);
    row.owned.text=source+' changed';r.logActivate(controller);
    assert.equal(row.text(),source+' changed','activation never repairs a body with different bytes');
    row.owned.text=source;

    r.logWrite(source,7);r.logActivate(controller);
    assert.equal(row.text(),source,'equal-byte ring overwrite cannot retain an old call identity');
    write(36,7);r.logActivate(controller);
    assert.equal(row.text(),source,'a new commit with the old bytes still requires a native rebind');
    r.logShow(row,7,source);
    assert.equal(row.text(),'一つ目の台詞。','the real binder replaces the controller identity after overwrite');
    const writes=r.api.status().writes;r.logActivate(controller);
    assert.equal(r.api.status().writes,writes,'an already reconciled row is idempotent');

    r.api.select('primary',true);r.update(row);assert.equal(row.text(),source);
    r.logReset();r.api.select('secondary',true);r.logActivate(controller);
    assert.equal(row.text(),source,'owner lifecycle reset invalidates controller sidecars');
    assert.equal(r.api.status().failed,false);
});

test('history activation never borrows a new call identity from an equal-byte slot overwrite',()=>{
    const {r,source,write}=historyFixture();
    write(36,7);r.api.select('primary',true);
    const row=r.label(0xabc0,''),controller=r.logShow(row,7,source);
    r.api.select('secondary',true);write(151,7);r.logActivate(controller);
    assert.equal(row.text(),source,'old controller binding must not acquire the new call ID');
    r.logShow(row,7,source);
    assert.equal(row.text(),'二つ目の台詞。','only native rebind admits the new physical record');
    assert.equal(r.api.status().failed,false);
});

test('history activation validates the full unknown-record stamp even when text is unchanged',()=>{
    const source='没有捕获身份的记录。',target='Identity-free translated record.';
    const r=makeRuntime(),pairs={[source]:[source,target]};
    r.api.load({pairs,plain_pairs:pairs},'primary',true,1);
    r.logRestore(source,7,'甲');
    const row=r.label(0xabd0,''),controller=r.logShow(row,7,source);
    r.api.select('secondary',true);r.logMutateRecord(7,0,1);r.logActivate(controller);
    assert.equal(row.text(),source,'same text and speaker cannot hide an unknown record stamp change');
    r.logShow(row,7,source);assert.equal(row.text(),target,'native rebind accepts the current unknown record');
    assert.equal(r.api.status().failed,false);
});

test('bilingual log projects names and bodies downward together without mutating native positions',()=>{
    const r=makeRuntime(),name=r.label(0xabd1,'姓名'),body=r.label(0xabd2,'');
    const pairs={'姓名':['姓名','Name'],'正文':['正文','Body']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,1);
    r.externalSet(name,'姓名');r.logRestore('正文',7,'姓名');
    r.logShow(body,7,'正文',[7],{name,height:150,bodyBottom:70});
    assert.equal(r.api.status().failed,false,JSON.stringify(r.api.status()));
    for(let frame=0;frame<3;frame++) {
        assert.equal(r.projectedUpdate(name),417);assert.equal(r.projectedUpdate(body),456);
        assert.equal(name.add(0x3c).readFloat(),409);assert.equal(body.add(0x3c).readFloat(),448);
        assert.equal(name.add(0xf4).readFloat(),9);assert.equal(body.add(0xf4).readFloat(),48);
    }
    for(const mode of ['primary','secondary']) {
        r.api.select(mode,true);
        assert.equal(r.projectedUpdate(name),409);assert.equal(r.projectedUpdate(body),448);
    }
    r.api.select('annotation',true);
    assert.equal(r.projectedUpdate(name),417);assert.equal(r.projectedUpdate(body),456);
    r.destroy(body);assert.equal(r.projectedUpdate(name),409,'destroyed sibling retires the whole group');
    assert.equal(r.api.status().failed,false);
});

test('log inset uses one bottom-limited delta, including untranslated bodies and empty names',()=>{
    for(const emptyName of [false,true])for(const height of [130,124,118]) {
        const r=makeRuntime(),name=r.label(0xabe1,emptyName?'':'姓名'),body=r.label(0xabe2,'');
        const pairs=emptyName?{'正文':['正文','Body']}:{'姓名':['姓名','Name']};
        r.api.load({pairs,plain_pairs:pairs},'annotation',true,1);r.externalSet(name,emptyName?'':'姓名');r.logRestore('正文',7,'姓名');
        r.logShow(body,7,'正文',[7],{name,height,bodyBottom:70});
        const delta=Math.max(0,Math.min(8,height-48-70-4));
        assert.equal(r.projectedUpdate(name),409+delta);
        assert.equal(r.projectedUpdate(body),448+delta);
        assert.ok(48+70+delta<=Math.max(height-4,48+70),'do not spend nonexistent bottom space');
        r.logShow(body,7,'正文',[7],{name,height:200,bodyBottom:70,mode:1});
        assert.equal(r.projectedUpdate(name),409);assert.equal(r.projectedUpdate(body),448,'active voice is not the dialogue log');
        assert.equal(r.api.status().failed,false);
    }
});

test('restored history uses persisted message IDs before same-text conflict fallback',()=>{
    const source='啊……',speaker='艾丝蒂尔';
    const keys=[36,151].map(id=>`script/scena/test.dat/Talk/called/${id}/assembled_dialogue`);
    const model={pairs:{},plain_pairs:{},script_identities:{
        record_pairs:{[keys[0]]:0,[keys[1]]:1},
        record_pair_values:[[source,'First reaction.'],[source,'Another reaction.']],
        history_markers:{1001:[['zh-Hans',source,speaker,keys[0],36]],1002:[['zh-Hans',source,speaker,keys[1],151]]}
    }};
    const r=makeRuntime();r.api.load(model,'annotation',true,1);
    const first=r.label(0xabe0,''),second=r.label(0xabf0,'');
    r.logRestore(source,7,speaker,1001);r.logRestore(source,8,speaker,1002);
    r.logShow(first,7,source);r.logShow(second,8,source);
    assert.equal(first.text(),'<R>'+source+'</RFirst reaction.>');
    assert.equal(second.text(),'<R>'+source+'</RAnother reaction.>');
    // No builder callback or current scene supplied these old records' IDs.
    r.api.select('secondary',true);r.update(first);r.update(second);
    assert.equal(first.text(),'First reaction.');assert.equal(second.text(),'Another reaction.');
    assert.deepEqual(r.logMeasure([[speaker,source,7],[speaker,source,8]]).bodies,
        ['First reaction.','Another reaction.'],'hidden row measurement restores the same independent IDs');
    r.api.select('primary',true);r.update(first);
    r.api.select('secondary',true);r.logActivate(r.logShow(first,7,source));
    assert.equal(first.text(),'First reaction.','reopening keeps the same physical record');
    r.logRestore(source,7,speaker,9999);r.logShow(first,7,source);
    assert.equal(first.text(),source,'an unknown ID cannot borrow a same-text translation');
    assert.equal(r.logMeasure([[speaker,source,7]]).bodies[0],source,
        'a prior measured translation cannot override the newly persisted marker');
    r.logRestore(source,7,'另一角色',1001);r.logShow(first,7,source);
    assert.equal(first.text(),source,'known speaker metadata still validates the physical call');
    assert.equal(r.api.status().failed,false);
});

test('restored multi-part history requires one marker and intact bytes for every contribution',()=>{
    const source='第一行\n第二行',key='script/scena/test.dat/Talk/called/4/assembled_dialogue';
    const r=makeRuntime();r.api.load({pairs:{},plain_pairs:{},script_identities:{
        record_pairs:{[key]:0},record_pair_values:[[source,'Complete message.']],
        history_markers:{700:[['zh-Hans',source,null,key,4]]}
    }},'secondary',true,1);
    const row=r.label(0xabf8,'');
    r.logRestore('第一行\n',7,'动态角色',700);r.logRestore('第二行',8,'动态角色',700);
    r.logShow(row,7,source,[7,8]);assert.equal(row.text(),'Complete message.');
    assert.equal(r.logMeasure([['动态角色',source,8,[7,8]]]).bodies[0],'Complete message.');
    r.logRestore('第二行',8,'动态角色',701);r.logShow(row,7,source,[7,8]);
    assert.equal(row.text(),source,'different physical markers cannot be concatenated into one call');
    r.logRestore('第二行',8,'动态角色',700);r.logShow(row,7,source+'changed',[7,8]);
    assert.equal(row.text(),source+'changed','full source must match the persisted parts');
    assert.equal(r.api.status().failed,false);
});

test('native history saves actual call IDs and never substitutes a different dialogue',()=>{
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const r=makeRuntime(),source='相同的对白。',data=Buffer.alloc(128);
    data.write('#scp');data.writeUInt32LE(24,4);data.writeUInt32LE(1,8);
    const signature=Buffer.concat([data.subarray(0,24),data.subarray(24,56),data.subarray(24,56)]).toString('hex');
    const sha256=scriptSha256(data),manifest={[signature]:[{size:128,sha256,functions:['Talk'],callSites:{Talk:{
        100:{record:4,group:5,command:0,token:'1,36'},104:{record:9,group:5,command:0,token:'1,36'},
    }}}]};
    const local=target=>({pairs:{[source]:[source,target]},plain_pairs:{[source]:[source,target]}});
    r.api.load({...local('Shared now'),script_identities:{manifest,scripts:{}}},'secondary',true,1);
    const live=r.label(0xab00,'');
    for(const [slot,pc] of [[7,100],[8,104]])r.dialogueSet(live,source,data,'Talk',[1,36],slot,{pc,group:5,command:0});
    assert.equal(r.api.status().logOriginSlots,2);
    const row=r.label(0xac00,'');r.logShow(row,8,source);
    const next={...local('WRONG global dialogue'),script_identities:{manifest,scripts:{[signature]:[{size:128,sha256,functions:{Talk:{
        records:{4:{model:local('Right.')},9:{model:local('Agreed.')}},calls:{},model:local('WRONG function'),
    }}}]}}};
    r.api.load(next,'secondary',true,1);r.update(row);assert.equal(row.text(),'Agreed.');
    r.logShow(row,7,source);assert.equal(row.text(),'Right.');
    assert.equal(r.logMeasure([['',source,8]]).bodies[0],'Agreed.');
    r.api.select('annotation',true);r.update(row);assert.ok(row.text().includes('Right.'));
    delete next.script_identities.scripts[signature][0].functions.Talk.records[4];
    r.api.load(next,'secondary',true,1);r.update(row);
    assert.equal(row.text(),source,'missing own ID cannot borrow a globally matching sentence');
});

test('consecutive distinct dialogue bodies keep their own IDs in every log slot, including ring wrap',()=>{
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const r=makeRuntime(),data=Buffer.alloc(128);
    data.write('#scp');data.writeUInt32LE(24,4);data.writeUInt32LE(1,8);
    const signature=Buffer.concat([data.subarray(0,24),data.subarray(24,56),data.subarray(24,56)]).toString('hex');
    const sources=['我先回谈话室，等那孩子回来吧。','要是找到了，就把人带过来吧。','嗯，我知道了。'];
    const targets=['I will wait in the lounge.','Bring her here when you find her.','All right.'];
    const keys=sources.map((_,i)=>`script/a.dat/Talk/called/${i}/assembled_dialogue`);
    const manifest={[signature]:[{size:128,sha256:scriptSha256(data),functions:['Talk'],
        callSites:{Talk:Object.fromEntries(sources.map((_,i)=>[100+i*4,{record:i,group:5,command:0,token:`1,${i}`}]))},
        recordKeys:{Talk:Object.fromEntries(sources.map((source,i)=>[i,{key:keys[i],source}]))}}]};
    r.api.load({pairs:{},plain_pairs:{},script_identities:{manifest,
        record_pairs:Object.fromEntries(keys.map((key,i)=>[key,i])),record_pair_values:sources.map((source,i)=>[source,targets[i]])}},
        'secondary',true,1);
    const live=r.label(0xab20,''),log=r.label(0xab30,'');
    for(const slots of [[0,1,2],[1598,1599,0]]) {
        for(let i=0;i<sources.length;i++) {
            r.dialogueSet(live,sources[i],data,'Talk',[1,i],slots[i],{pc:100+i*4,group:5,command:0});
            assert.equal(live.text(),targets[i],'normal dialogue must already use its own ID');
        }
        for(let i=0;i<sources.length;i++) {
            r.logShow(log,slots[i],sources[i]);assert.equal(log.text(),targets[i]);
            assert.equal(r.logMeasure([['',sources[i],slots[i]]],{fontSize:slots[0]===0?29:30}).bodies[0],targets[i]);
            r.api.select('annotation',true);r.update(log);assert.ok(log.text().includes(targets[i]));
            r.api.select('secondary',true);
            r.logShow(log,slots[i],sources[i]);assert.equal(log.text(),targets[i],'reopened rows keep each earlier ID');
        }
    }
    assert.equal(r.api.status().failed,false);
});

test('restored history uses retained speaker and full text without inventing a script identity',()=>{
    const r=makeRuntime(),source='<#E_0><K4>相同的完整对白。',target='<#E_0><K4>女性の台詞。';
    const pairs={[source]:[source,target]};
    r.api.load({pairs:{},plain_pairs:{},ambiguous_display:[source],speaker_contexts:{
        '雪拉扎德':{pairs,plain_pairs:pairs}
    }},'secondary',true,1);
    r.logRestore(source,7,'雪拉扎德');
    const p=r.label(0xac00,'');r.logShow(p,7,source);
    assert.equal(p.text(),target);
    assert.equal(r.api.status().identityHits,0);
    assert.equal(r.logMeasure([['雪拉扎德',source,7]]).bodies[0],target);
    r.api.select('annotation',true);r.update(p);
    assert.equal(r.api.snapshot().find(row=>row.original===source&&row.presentation==='layered')?.layers[0].text,'女性の台詞。');
    r.api.select('secondary',true);
    r.logRestore(source,7,'陌生人');r.logShow(p,7,source);assert.equal(p.text(),source);
    r.logRestore(source,7,'雪拉扎德');r.logShow(p,7,source+'篡改');assert.equal(p.text(),source+'篡改');
    r.externalSet(p,source);assert.equal(p.text(),source,'speaker context cannot leak into ordinary setters');
});

test('identity-free old history uses an official candidate without leaking into live text or exact IDs',()=>{
    const r=makeRuntime(),body='这样啊……',source='<#E_8>'+body,key='script/a.dat/Talk/called/8/assembled_dialogue';
    r.api.load({pairs:{},plain_pairs:{},history_contexts:{
        pairs:[[body,'そうか。'],[body,'なるほど。']],texts:{[body]:-1},names:{},speakers:{'艾丝蒂尔':{[body]:-1}},
        fallback_texts:{[body]:0},fallback_speakers:{'艾丝蒂尔':{[body]:1}},
    },script_identities:{record_pairs:{[key]:0},record_pair_values:[[body,'その通り。']],
        history_markers:{801:[['zh-Hans',source,'艾丝蒂尔',key,8]]},
    }},'secondary',true,1);
    const row=r.label(0xae20,'');r.logRestore(source,7,'艾丝蒂尔');r.logShow(row,7,source);
    assert.equal(row.text(),'<#E_8>なるほど。');
    assert.equal(r.logMeasure([['艾丝蒂尔',source,7]]).bodies[0],'<#E_8>なるほど。');
    assert.equal(r.api.status().identityHits,0,'candidate display does not invent a physical call ID');
    r.api.select('annotation',true);r.update(row);
    assert.match(row.text()+JSON.stringify(r.api.snapshot()),/なるほど/);
    r.api.select('secondary',true);r.logRestore(source,8,'艾丝蒂尔',801);r.logShow(row,8,source);
    assert.equal(row.text(),'<#E_8>その通り。','a real marker-derived ID wins over the candidate');
    r.externalSet(row,source);assert.equal(row.text(),source,'old-history fallback is not a live dialogue resolver');
    assert.equal(r.api.status().failed,false);
});

test('history names use the actual dialogue setter in visible and measuring controls',()=>{
    const r=makeRuntime(),source='……让各位久等了。',name='女子的声音';
    const keys=[12,24].map(call=>`script/a.dat/Talk/called/${call}/assembled_dialogue`);
    r.api.load({pairs:{},plain_pairs:{},history_contexts:{pairs:[[name,'Wrong generic name']],texts:{},speakers:{},names:{[name]:0}},
        script_identities:{history_markers:Object.fromEntries(keys.map((key,i)=>[100+i,[['zh-Hans',source,name,key,12+i*12]]])),
        history_speaker_setters:Object.fromEntries(keys.map((key,i)=>[key,[['zh-Hans',name,name,i?'女の声':'女性の声']]]))}
    },'secondary',true,1);
    const label=r.label(0xae30,'');
    for(const [slot,marker,expected] of [[7,100,'女性の声'],[8,101,'女の声']]) {
        r.logRestore(source,slot,name,marker);r.logNameShow(label,slot,name);
        assert.equal(label.text(),expected);
        assert.equal(r.logMeasure([[name,source,slot]]).names[0],expected);
    }
    r.externalSet(label,name);assert.equal(label.text(),name,'setter provenance does not follow a reused name control');
    assert.equal(r.api.status().failed,false);
});

test('multi-slot history names retain the full dialogue identity before visible and measuring setters',()=>{
    const r=makeRuntime(),source='第一行\n第二行',name='女子的声音';
    const key='script/a.dat/Talk/called/12/assembled_dialogue';
    r.api.load({pairs:{},plain_pairs:{},history_contexts:{pairs:[[name,'Wrong generic name']],texts:{},speakers:{},names:{[name]:0}},
        script_identities:{history_markers:{100:[['zh-Hans',source,name,key,12]]},
        history_speaker_setters:{[key]:[['zh-Hans',name,name,'女性の声']]}}
    },'secondary',true,1);
    const label=r.label(0xae30,'');
    r.logRestore('第一行\n',1599,name,100);r.logRestore('第二行',0,name,100);
    r.logNameShow(label,1599,name,[1599,0]);assert.equal(label.text(),'女性の声');
    assert.equal(r.logMeasure([[name,source,0,[1599,0]]]).names[0],'女性の声');
    r.logRestore('第二行',0,name,101);r.logNameShow(label,1599,name,[1599,0]);
    assert.notEqual(label.text(),'女性の声','different physical markers cannot inherit a setter identity');
    assert.equal(r.api.status().failed,false);
});

test('restored history can replace primary language when secondary equals the game language',()=>{
    const r=makeRuntime(),body='<K4>相同的完整对白。',source='<#E_4>'+body,target='<#E_4><K4>Complete dialogue.';
    const pairs={[body]:['<K4>Complete dialogue.',body]};
    r.api.load({pairs:{},plain_pairs:{},ambiguous_display:[body],speaker_contexts:{
        '雪拉扎德':{pairs,plain_pairs:{}}
    }},'primary',true,1);
    r.logRestore(source,7,'雪拉扎德');
    const p=r.label(0xac00,'');r.logShow(p,7,source);
    assert.equal(p.text(),target);
    assert.equal(r.logMeasure([['雪拉扎德',source,7]]).bodies[0],target);
});

test('mixed source-language history renders old bodies and names without leaking into menus',()=>{
    const r=makeRuntime(),old='<#E_4>歡迎來到中央工房。',current='<#E_4>欢迎来到中央工房。';
    const history={pairs:[['欢迎来到中央工房。','ようこそ中央工房。'],['埃里克','エイリク']],
        texts:{'歡迎來到中央工房。':0,'欢迎来到中央工房。':0},names:{'艾瑞克':1,'埃里克':1},speakers:{}};
    const model={pairs:{},plain_pairs:{},history_contexts:history};
    r.api.load(model,'secondary',true,1);
    r.logRestore(old,7,'艾瑞克');r.logRestore(current,8,'埃里克');
    const body=r.label(0xac00,''),name=r.label(0xad00,'');
    for(const [slot,source,speaker] of [[7,old,'艾瑞克'],[8,current,'埃里克']]) {
        r.logShow(body,slot,source);assert.equal(body.text(),'<#E_4>ようこそ中央工房。');
        r.logNameShow(name,slot,speaker);assert.equal(name.text(),'エイリク');
        const measured=r.logMeasure([[speaker,source,slot]],{fontSize:slot+24});
        assert.equal(measured.bodies[0],'<#E_4>ようこそ中央工房。');
        assert.equal(measured.names[0],'エイリク');
    }
    r.api.load(model,'annotation',true,1);r.update(body);r.update(name);
    assert.match(body.text(),/ようこそ中央工房/);
    assert.match(name.text()+JSON.stringify(r.api.snapshot().find(row=>row.original==='埃里克')?.layers||[]),/エイリク/);
    r.externalSet(body,old);assert.equal(body.text(),old);
    r.externalSet(name,'艾瑞克');assert.equal(name.text(),'艾瑞克');
    r.logShow(body,7,old+'篡改');assert.equal(body.text(),old+'篡改');
    assert.equal(r.api.status().identityHits,0,'old exact lookup must not invent script identity');
});

test('a copied history body retains its body-only history context',()=>{
    const r=makeRuntime(),source='<#E_4>歡迎來到中央工房。';
    r.api.load({pairs:{},plain_pairs:{},history_contexts:{
        pairs:[['欢迎来到中央工房。','ようこそ中央工房。']],
        texts:{'歡迎來到中央工房。':0},names:{},speakers:{},
    }},'secondary',true,1);
    r.logRestore(source,7,'艾瑞克');
    const body=r.label(0xae80,'');r.logShow(body,7,source);
    assert.equal(body.text(),'<#E_4>ようこそ中央工房。');
    const copy=r.cloneLabel(body,0xae90);
    assert.equal(copy.text(),'<#E_4>ようこそ中央工房。');
    assert.equal(r.api.status().failed,false);
});

test('mixed-language history ambiguity blocks a current-locale global match',()=>{
    const r=makeRuntime(),source='<#E_9>共同文字';
    r.api.load({pairs:{'共同文字':['共同文字','Wrong current-locale match']},plain_pairs:{},
        history_contexts:{pairs:[],texts:{'共同文字':-1},speakers:{},names:{}}},'secondary',true,1);
    r.logRestore(source,7,'甲');const row=r.label(0xae00,'');r.logShow(row,7,source);
    assert.equal(row.text(),source);assert.equal(r.logMeasure([['甲',source,7]]).bodies[0],source);
    r.api.select('annotation',true);r.update(row);assert.equal(row.text(),source);
});

test('copied history retains exact branch identity in both measurement and visible rows',()=>{
    const {r,source,write}=historyFixture('<K>相同的完整对白。');
    write(36,7);write(151,8);
    const p=r.label(0xac00,'');
    r.logShow(p,7,source);assert.equal(p.text(),'一つ目の台詞。');
    r.logShow(p,8,source);assert.equal(p.text(),'二つ目の台詞。');
    const first=r.logMeasure([['',source,7]]),second=r.logMeasure([['',source,8]]);
    assert.equal(first.bodies[0],'一つ目の台詞。');
    assert.equal(second.bodies[0],'二つ目の台詞。');
    assert.equal(second.setters,1,'another branch must not reuse the first body descriptor');
    assert.equal(r.logMeasure([['',source,7]]).setters,0);
    r.api.select('annotation',true);r.update(p);
    const rendered=r.api.snapshot().find(row=>row.original===source&&row.presentation==='layered');
    assert.equal(rendered?.layers[0].text,'二つ目の台詞。');
    r.api.select('primary',true);r.update(p);assert.equal(p.text(),source);
    r.api.select('secondary',true);r.update(p);assert.equal(p.text(),'二つ目の台詞。');
    assert.equal(r.api.status().failed,false);
});

test('history overwrite, same-address lifecycle reset, and unobserved old records cannot retain provenance',()=>{
    const {r,source,write}=historyFixture(),p=r.label(0xac00,'');
    write(36,7);r.logShow(p,7,source);assert.equal(p.text(),'一つ目の台詞。');
    r.logWrite(source,7);r.logShow(p,7,source);assert.equal(p.text(),source,'equal-byte overwrite must erase identity');
    write(151,7);r.logReset();r.logShow(p,7,source);assert.equal(p.text(),source);
    r.logShow(p,9,source);assert.equal(p.text(),source,'unknown history cannot borrow another slot');
    assert.equal(r.api.status().failed,false);
});

test('long history validates every contributing slot, rejecting mixed and unknown origins',()=>{
    const {r,source,write}=historyFixture('<K>'+('很长的剧情正文。'.repeat(24))),p=r.label(0xac00,'');
    const chunks=[source.slice(0,80),source.slice(80,160),source.slice(160)];
    write(36,chunks.map((chunk,i)=>[10+i,chunk]));
    write(151,chunks.map((chunk,i)=>[20+i,chunk]));
    r.logShow(p,12,source,[10,11,12]);assert.equal(p.text(),'一つ目の台詞。');
    assert.equal(r.logMeasure([['',source,12,[10,11,12]]]).bodies[0],'一つ目の台詞。');
    r.logShow(p,12,source,[10,21,12]);assert.equal(p.text(),source,'same bytes are not sufficient across distinct calls');
    assert.equal(r.logMeasure([['',source,12,[10,21,12]]]).bodies[0],source);
    r.logWrite(chunks[1],11);r.logShow(p,12,source,[10,11,12]);assert.equal(p.text(),source,'one unknown contributor invalidates the combined body');
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
    for(const [actual,expected] of geometry[3].map((value,index)=>[value,[32,4,14,14][index]]))
        assert.ok(Math.abs(actual-expected)<1e-6,`${actual} != ${expected}`);
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

test('layered log rebuilds after a decorative prefix do not accumulate scaling or tint',()=>{
    const r=makeRuntime(),source='<c930>──\n钥匙在城里。\n──',target='<c930>──\n鍵は市中に。\n──';
    const pairs={[source]:[source,target]};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85,
        {secondary_color:[.9,.9,.9],secondary_opacity:.9});
    const label=r.label(0xcb00,'');label.flags=65;r.externalSet(label,source);
    // The first owned anchor follows already-emitted decoration. Its base
    // measurement callback is the layered lane entry; glyph count is nonzero.
    const quads=[[100,10,200,2],[45,30,14,14],[50,50,20,20]];
    let expected;
    for(let frame=0;frame<100;frame++) {
        label.glyphs=1;
        r.auxiliary(label,0,{glyphQuads:quads,secondaryCount:2});
        r.newline(label,100);
        r.glyphColors(label,quads.map(()=>[1,.5,0,1]));
        r.finishLayout(label);
        const actual={geometry:r.glyphGeometry(label),colors:r.glyphColors(label)};
        expected??=actual;
        assert.deepEqual(actual,expected,'fresh native glyphs must receive each correction once');
        assert.equal(r.laneCount(label),1,'each native rebuild must replace the prior layered lane');
        r.finishLayout(label);
        assert.deepEqual(r.glyphGeometry(label),expected.geometry,'same-pass revisit must be idempotent');
    }
    assert.equal(r.api.status().failed,false,r.api.status().failureReason);
});

test('multiple layered lines retain only the current parse after decoration, icons or counters',()=>{
    for(const prefix of ['──','<I300>','42']) {
        const r=makeRuntime(),source='<c930>'+prefix+'\n甲\n乙',target='<c930>'+prefix+'\n一\n二';
        const pairs={[source]:[source,target]};
        r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85,
            {secondary_color:[.8,.7,.6],secondary_opacity:.9,bilingual_offset_y:2});
        const label=r.label(0xcc00,'');label.flags=65;r.externalSet(label,source);
        const quads=[[100,10,200,2,1],[40,30,14,14],[60,30,14,14],[50,50,20,20],
            [40,70,14,14],[60,70,14,14],[50,90,20,20]];
        let expected;
        for(let frame=0;frame<50;frame++) {
            label.glyphs=1;r.auxiliary(label,0,{glyphQuads:quads,secondaryCount:3});
            label.glyphs=4;r.newline(label,100);
            r.auxiliary(label,1,{glyphQuads:quads,secondaryCount:6});r.newline(label,140);
            r.glyphColors(label,quads.map(()=>[1,.5,0,1]));r.finishLayout(label);
            const actual={geometry:r.glyphGeometry(label),colors:r.glyphColors(label)};
            expected??=actual;
            assert.deepEqual(actual,expected,prefix+': repeated parse geometry and colors');
            assert.equal(r.laneCount(label),2,'multiple lines in one pass must survive');
            assert.deepEqual(actual.geometry[0],[100,12,200,2],'unowned prefix only receives explicit group offset');
        }
        assert.equal(r.api.status().failed,false,r.api.status().failureReason);
    }
});

test('animated layered rebuilds keep scale stable while reveal progress changes',()=>{
    const r=makeRuntime(),source='<c930>──\nAB',target='<c930>──\n甲乙';
    const pairs={[source]:[source,target]};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,.85,{secondary_opacity:.9});
    const label=r.label(0xcd00,'');label.flags=4;r.externalSet(label,source);
    const quads=[[100,10,200,2],[40,30,14,14],[60,30,14,14],[50,50,20,20]];
    const expected=new Map();
    for(let frame=0;frame<60;frame++) {
        label.glyphs=1;
        r.auxiliary(label,0,{glyphQuads:quads,secondaryCount:3,unitStart:1,primaryUnits:2});
        r.newline(label,100);label.revealUnits=1+frame%3;
        r.glyphColors(label,quads.map(()=>[1,.5,0,1]));r.finishLayout(label);
        const actual={geometry:r.glyphGeometry(label),colors:r.glyphColors(label)};
        if(!expected.has(label.revealUnits))expected.set(label.revealUnits,actual);
        assert.deepEqual(actual,expected.get(label.revealUnits),'progress may change alpha, never accumulate scale');
        assert.equal(r.laneCount(label),1);
        assert.equal(actual.geometry[1][2],14,'secondary parser size is not shrunk a second time');
        assert.equal(actual.geometry[3][2],17);
    }
    assert.equal(expected.get(1).colors[1][3],0);
    assert.ok(expected.get(3).colors[1][3]>.89);
    assert.equal(r.api.status().failed,false,r.api.status().failureReason);
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


test('actor-owned copied names retain their physical script setter identity, including equal source names',()=>{
    const r=makeRuntime(),source='女子的声音',data=Buffer.alloc(160);
    data.write(source,48);data.write(source,96);
    const {scriptSha256}=require('../sora_bilingual/game/scripts/runtime_identity.js');
    const keys=['script/a.dat/Talk/called/1/arg/1','script/a.dat/Talk/called/2/arg/1'];
    const pairs=keys.map((key,i)=>({key,source,model:{pairs:{[source]:[source,['女性の声','女の声'][i]]},plain_pairs:{}}}));
    r.api.load({pairs:{},plain_pairs:{},script_identities:{pointers:{[source]:[48,96].map((offset,i)=>({offset,key:keys[i],size:data.length,sha256:scriptSha256(data),header:data.subarray(0,24).toString('hex')}))},pointer_models:Object.fromEntries(pairs.map(row=>[row.key,row]))}},'secondary',true,1);
    const label=r.label(0x9190,''),first=r.actorName(0x610000,data,48,source);
    r.actorNameFlags(first.actor);
    r.setFromPointer(label,first.copy);assert.equal(label.text(),'女性の声');
    r.api.select('primary',true);r.update(label);assert.equal(label.text(),source);
    r.api.select('secondary',true);r.update(label);assert.equal(label.text(),'女性の声');
    const second=r.actorName(0x610000,data,96,source,first.actor);
    r.setFromPointer(label,second.copy);assert.equal(label.text(),'女の声');
    r.setFromPointer(label,first.copy);assert.equal(label.text(),source,'retired owned buffer cannot retain a setter');
    const unknown=r.actorName(0x610000,null,0,source,first.actor);
    r.setFromPointer(label,unknown.copy);assert.equal(label.text(),source,'unknown heap source cannot borrow the previous identity');
});


test('active voice projection is scoped to its native layout and restored on every Update',()=>{
    const r=makeRuntime(),source='不过，你也别那么灰心。',target='まあ、そう気ぃ落とさんと。';
    const pairs={[source]:[source,target]};r.api.load({pairs,plain_pairs:pairs},'annotation',true,1);
    for(const id of [32,7,8,0])for(const node of ['text','name']) {
        const root=r.label(0xe010,'');root.name='root';r.registerLayout(root,id);
        const items=r.label(0xe020,'');items.name='items';items.parent=root;
        const item=r.label(0xe030,'');item.name='item';item.parent=items;
        item.add(0x1c).writeFloat(2);
        const label=r.label(0xe040,source);label.name=node;label.parent=item;
        label.add(0x3c).writeFloat(400);
        for(let frame=0;frame<4;frame++) {
            assert.equal(r.projectedUpdate(label),400+(id===32&&node==='text'?16:0),`${id}/${node}`);
            assert.equal(label.add(0x3c).readFloat(),400,'restore before the next native Update');
        }
        r.registerLayout(root,7);assert.equal(r.projectedUpdate(label),400,'retired voice root loses its inset even with unchanged text');
        r.registerLayout(root,id);
        for(const mode of ['primary','secondary']) {
            r.api.select(mode,true);assert.equal(r.projectedUpdate(label),400);
        }
        r.api.select('annotation',true);r.api.disable();assert.equal(r.projectedUpdate(label),400);
        r.api.select('annotation',true);r.destroy(label);
    }
    assert.equal(r.api.status().failed,false,r.api.status().failureReason);
});

test('small dialogue body uses the shared inset without moving its speaker name',()=>{
    const r=makeRuntime(),source='各位，身为亲卫队，',pairs={[source]:[source,'皆さん、親衛隊として']};
    r.api.load({pairs,plain_pairs:pairs},'annotation',true,1);
    for(const id of [6,7,8,32])for(const name of ['text','Text','name_text']) {
        const root=r.label(0xea010,'');root.name='root';r.registerLayout(root,id);
        root.add(0x1c).writeFloat(2);
        const label=r.label(0xea040,source);label.name=name;label.parent=root;
        label.add(0x3c).writeFloat(400);
        for(let i=0;i<3;i++) {
            assert.equal(r.projectedUpdate(label),400+(id===6&&name==='text'?16:0),`${id}/${name}`);
            assert.equal(label.add(0x3c).readFloat(),400);
        }
        for(const mode of ['primary','secondary']) {
            r.api.select(mode,true);assert.equal(r.projectedUpdate(label),400,mode);
        }
        r.api.select('annotation',true);r.api.disable();assert.equal(r.projectedUpdate(label),400,'disabled');
        r.api.select('annotation',true);r.registerLayout(root,8);assert.equal(r.projectedUpdate(label),400);
        r.destroy(label);
    }
    const root=r.label(0xeb010,'');root.name='root';r.registerLayout(root,6);
    const unknown=r.label(0xeb040,'unmapped text');unknown.name='text';unknown.parent=root;
    unknown.add(0x3c).writeFloat(400);
    assert.equal(r.projectedUpdate(unknown),400,'bilingual mode without secondary text retains native position');
});
