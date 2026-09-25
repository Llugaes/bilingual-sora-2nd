'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const AGENT = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/native_agent.js'), 'utf8');
const RESOLVER = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_text.js'), 'utf8');
const IDENTITIES = fs.readFileSync(path.join(__dirname, '..', 'sora_bilingual/game/scripts/runtime_identity.js'), 'utf8');

function makeRuntime(rubyCase = null) {
    const hooks = new Map();
    const messages = [];
    const allocations = [];
    let threadId = 1;
    let duringSetter=null;
    const scriptReads=[];

    class Pointer {
        constructor(address) { this.address = address; }
        add(offset) { return new Pointer(this.address + offset); }
        equals(other) { return this.address === other.address; }
        isNull() { return false; }
        toString() { return `0x${this.address.toString(16)}`; }
        toInt32() {return this.address|0;}
        readByteArray(size) { return new Uint8Array(size).buffer; }
    }

    class TextPointer extends Pointer {
        constructor(label) { super(label.address + 0x9000); this.label = label; }
        readUtf8String() { return this.label.owned.text; }
    }

    class FieldPointer extends Pointer {
        constructor(label, offset) { super(label.address + offset); this.label = label; this.offset = offset; }
        readPointer() {
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
            throw Error(`unexpected numeric field ${this.offset}`);
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
        readFloat(){return this.values.get(this.offset)??0;}
        writeFloat(v){this.values.set(this.offset,v);}
        readPointer(){return this.values.get(this.offset)??nullPointer;}
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
        node_names:true,
        vtable: 0x500,
        native: {
            set_text: {rva: 0x100, bytes: '00000000000000000000000000000000'},
            destroy: {rva: 0x200, bytes: '00000000000000000000000000000000'},
            update: {rva: 0x300, bytes: '00000000000000000000000000000000'},
            ruby_context_init: {rva: 0x600, bytes: '00000000000000000000000000000000'},
            ruby_place_return: {rva: 0x700, bytes: '00000000000000000000000000000000'},
            ruby_measure_return: {rva: 0x800, bytes: '00000000000000000000000000000000'},
            newline_prepare: {rva: 0x900, bytes: '00000000000000000000000000000000'},
            ruby_base_measure_end:{rva:0xa00,bytes:'00000000000000000000000000000000'},
            ruby_compensate:{rva:0xb00,bytes:'00000000000000000000000000000000'},
            ruby_end:{rva:0xc00,bytes:'00000000000000000000000000000000'},
            parse_text:{rva:0xd00,bytes:'00000000000000000000000000000000'},
            dialogue_popup:{rva:0xe00,bytes:'00000000000000000000000000000000'},
            dialogue_builder:{rva:0xf00,bytes:'00000000000000000000000000000000'},
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
                        rbx:{readFloat:()=> (rubyCase.baseLeft??0)+40,add:()=>({readFloat:()=>rubyCase.origin??0})},
                        rbp:{add:off=>({readS32:()=>({0x3c8:0,0x3d0:40,0x17c:0,0x184:rubyCase.bottom??18})[off]??0})}}};
                hook.onEnter.call(call, [ctx]);
                hook.onLeave.call(call);
                rubyCase.after = values.get(0);
                rubyCase.scale=values.get(0x158);rubyCase.y=values.get(4);
        }
    }

    function NativeFunction(address) {
        if (!address.equals(base.add(REPORT.native.set_text.rva))) throw Error('unexpected native function');
        return (label, buffer) => {
            const args=[label,buffer],leave=invoke(address,args);
            copyIntoLabel(label, args[1]);
            if(duringSetter){const callback=duringSetter;duringSetter=null;const saved=threadId;try{callback();}finally{threadId=saved;}}
            if (!rubyCase?.deferred) renderRuby(label);
            leave();
        };
    }

    const sandbox = {
        REPORT,
        Process: {
            getModuleByName(name) {
                assert.equal(name, 'sora_2nd.exe');
                return {base};
            },
            getCurrentThreadId() { return threadId; },
        },
        Memory: {allocUtf8String: allocate},
        NativeFunction,
        Interceptor: {attach(address, callback) { hooks.set(String(address), callback); }},
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
    const context=vm.createContext(sandbox);
    vm.runInContext(RESOLVER+'\n'+IDENTITIES+'\n'+AGENT, context, {filename: 'native_agent.js'});

    return {
        api: sandbox.rpc.exports,
        messages,
        allocations,
        scriptReads,
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
        compensate(label) {
            const parser=new ScratchPointer(0x700000);
            parser.add(4).writeFloat(100);
            const context={r15:label,rbx:parser};
            hooks.get(String(base.add(0xb00))).onEnter.call({context});
            if(!parser.add(0x1a7).readU8())parser.add(4).writeFloat(112);
            hooks.get(String(base.add(0xc00))).onEnter.call({context});
            return {y:parser.add(4).readFloat(),flag:parser.add(0x1a7).readU8()};
        },
        auxiliary(label,index=0,geometry={}) {
            const row=sandbox.rpc.exports.snapshot().find(v=>v.original===label.originalForTest||v.displayed===label.text());
            const layer=row.layers[index];
            const parser=new ScratchPointer(0x700000);
            parser.writeFloat(20);parser.add(4).writeFloat(geometry.origin??100);
            parser.values.set(8,label.add(0x318).readPointer().add(layer.offset));
            const frame=new ScratchPointer(0x800000);
            frame.add(0x17c).writeS32(0);frame.add(0x184).writeS32(geometry.bottom??18);
            for(const off of [0x3c8,0x3cc,0x3d0,0x3d4])frame.add(off).writeS32(0x7fffffff);
            const machine={r15:label,rbx:parser,rbp:frame};
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
                    nestedRubyDisabled:child.add(0x1a5).readU8()});
                ph.onLeave.call(parseCall);
            }
            hooks.get(String(base.add(0xb00))).onEnter.call({context:machine});
            const duringCompensation=parser.add(0x1a7).readU8();
            hooks.get(String(base.add(0xc00))).onEnter.call({context:machine});
            return {results,duringCompensation,restoredCompensation:parser.add(0x1a7).readU8(),
                primaryX:parser.readFloat(),primaryY:parser.add(4).readFloat(),
                bounds:[0x3c8,0x3cc,0x3d0,0x3d4].map(v=>frame.add(v).readS32())};
        },
        keyTable(hash,key,source) {
            vm.runInContext('textKeys.set('+JSON.stringify(hash)+','+JSON.stringify({key,source})+');',context);
        },
        newline(label,bottom) {
            const call={context:{r13:label,r12:new Pointer(bottom)}};
            hooks.get(String(base.add(REPORT.native.newline_prepare.rva))).onEnter.call(call);
            return call.context.r12.address;
        },
        label(address, text, glyphs, fontSize) { return new LabelPointer(address, text, glyphs, fontSize); },
        externalSet(label, text, currentThread=1) {
            threadId=currentThread;
            const buffer = allocate(text);
            const args=[label,buffer],leave=invoke(base.add(REPORT.native.set_text.rva),args);
            copyIntoLabel(label, args[1]);
            leave();
            return buffer;
        },
        update(label, currentThread = 1) {
            threadId = currentThread;
            const leave=invoke(base.add(REPORT.native.update.rva), [label]);
            if (rubyCase?.deferred) renderRuby(label);
            leave();
        },
        duringSetter(callback){duringSetter=callback;},
        beginUpdate(label,currentThread=1){threadId=currentThread;return invoke(base.add(REPORT.native.update.rva),[label]);},
        destroy(label) { invoke(base.add(REPORT.native.destroy.rva), [label]); },
    };
}

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

test('ruby measurement and drawing share the smaller size; drawing alone moves upward', () => {
    for(const measurement of [false,true]) {
        const sample={x:10,measurement};const runtime=makeRuntime(sample);
        const label=runtime.label(0x4350,'测试');
        runtime.api.configure({'测试':'<R>测试</Rテスト>'},true);runtime.update(label);
        assert.ok(Math.abs(sample.scale-.3)<1e-8);
        assert.equal(sample.y,measurement?0:-21);
    }
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
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),source);
});

test('unannotated numeric lines inside a formatted paragraph retain their native size',()=>{
    const runtime=makeRuntime(),a='<C2>Text</C>\n4',b='<C2>Texte</C>\n４';
    runtime.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
    const label=runtime.label(0x4650,a);runtime.update(label);
    assert.equal(label.text(),'<R></R_><C2>Text</C>\n4');
});

test('plain and formatted annotation lanes have the same measured gap across sizes and native offsets',()=>{
    for(const fontSize of [18,32,64])for(const bottom of [10,18,24])for(const nativeY of [30,80,110]) {
        const sample={x:10,origin:100,bottom,nativeY};const runtime=makeRuntime(sample);
        runtime.api.configure({'Text':'<R>Text</RTexte>'},true);
        const label=runtime.label(0x4630,'Text',0,fontSize);runtime.update(label);
        const formatted=makeRuntime(),a='<C2>Text</C>',b='<C2>Texte</C>';
        formatted.api.load({pairs:{[a]:[a,b]},plain_pairs:{[a]:[a,b]}},'annotation',true,.9);
        const other=formatted.label(0x4640,a,0,fontSize);formatted.update(other);
        const y=formatted.auxiliary(other,0,{origin:100,bottom,nativeY}).results[1].y;
        assert.equal(y,sample.y);assert.equal(100-(y+bottom),3);
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
    const runtime = makeRuntime();
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
        assert.equal(result.results[1].y,59);
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
    assert.equal(result.results[1].y,79,'measured annotation bottom is three units above primary origin');
    assert.equal(runtime.api.status().failed,false);
    runtime.api.disable();runtime.update(label);assert.equal(label.text(),a);
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
