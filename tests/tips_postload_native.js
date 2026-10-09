'use strict';
let nativeModel;
const retained=[];
function keep(value){retained.push(value);return value;}
function bytes(value){return Uint8Array.from(value).buffer;}
function nativeCode(spec,targets){
    // Code gets its own page allocation; protect must not change a heap page
    // shared with later test data/callback allocations.
    const capacity=Math.ceil((spec.body.length+2048)/Process.pageSize)*Process.pageSize,
        out=keep(Memory.alloc(capacity));out.writeByteArray(bytes(spec.body));
    const local=new Map();let cursor=(spec.body.length+15)&~15;
    for(const patch of spec.patches){
        const target=targets[patch.target];if(!target)throw Error('Unknown native relocation');
        if(!local.has(patch.target)){
            const destination=out.add(cursor);
            if(patch.call){destination.writeByteArray([0x48,0xb8]);destination.add(2).writePointer(target);
                destination.add(10).writeByteArray([0xff,0xe0]);cursor+=16;}
            else{destination.writeByteArray(target.readByteArray(patch.width));cursor+=(patch.width+15)&~15;}
            if(cursor>capacity)throw Error('Native relocation arena exhausted');
            local.set(patch.target,destination);
        }
        const destination=local.get(patch.target);
        const delta=destination.sub(out.add(patch.next)).toInt32();
        if(!out.add(patch.next).add(delta).equals(destination))throw Error('rel32 does not fit');
        out.add(patch.offset).writeS32(delta);
    }
    if(!Memory.protect(out,capacity,'rwx'))throw Error('Native test code protection failed');return out;
}
function makeLoader(sample,raw,flagOverride=null){
    const blob=keep(Memory.alloc(raw.length));blob.writeByteArray(bytes(raw));
    if(flagOverride!==null)blob.add(88+2).writeU16(flagOverride);
    const descriptor=keep(Memory.allocUtf8String('TipsTableData'));
    const vtable=keep(Memory.alloc(48));const notes=[];
    const diagnostic=keep(new NativeCallback((level,file,code,message,flag,line)=>{
        notes.push({level,code,flag,line});},'void',['uint','pointer','uint','pointer','uint','uint']));
    const compare=nativeCode(sample.compare,{});
    const code=nativeCode(sample.loader,{vtable,descriptor,diagnostic,compare,
        message:keep(Memory.allocUtf8String(sample.message)),file:keep(Memory.allocUtf8String(sample.file))});
    const table=keep(Memory.alloc(64));
    const result=new NativeFunction(code,'pointer',['pointer','pointer'])(table,blob);
    if(!result.equals(table))throw Error('Native loader return differs');
    return {blob,table,notes};
}
function nativeItem(sample,manager,tableIds,family,id,captured){
    const textLabel=keep(Memory.alloc(4096)),child=keep(Memory.alloc(512)),root=keep(Memory.alloc(640));
    const vector=keep(Memory.alloc(Process.pointerSize));vector.writePointer(child);
    root.add(0x228).writePointer(vector);root.add(0x230).writeU64(1);
    const instance=keep(Memory.alloc(64));let result=null;
    const lookup=keep(new NativeCallback((node,name,index,recursive)=>{
        if(!node.equals(child)||name.readUtf8String()!=='text'||index!==0||(recursive&255)!==1)
            throw Error('Native child lookup ABI differs');return textLabel;
    },'pointer',['pointer','pointer','uint','uint']));
    const setter=keep(new NativeCallback((label,input)=>{
        try {
            if(!label.equals(textLabel))throw Error('Native label argument differs');
            const source=input.readUtf8String(),trace=[];
            if(source!==captured.original)throw Error('Native full source differs');
            const context=tableIds.select(input,source,e=>trace.push(e));
            const plan=context?new RuntimeText(context.model).render(source,'annotation',captured.text_key||'',captured.scope||''):
                new RuntimeText(nativeModel).render(source,'annotation',captured.text_key||'',captured.scope||'');
            result={source,selected_key:context?.key||null,plan,trace};
        }catch(error){result={error:String(error)};}
    },'void',['pointer','pointer']));
    const initialize=keep(new NativeCallback(()=>{},'void',['pointer']));
    const vtable=keep(Memory.alloc(48));vtable.add(32).writePointer(initialize);
    const global=keep(Memory.alloc(8));global.writePointer(manager);
    const code=nativeCode(sample.item,{vtable,name:keep(Memory.allocUtf8String('text')),manager:global,lookup,setter});
    const out=new NativeFunction(code,'pointer',['pointer','pointer','uint','uint'])(instance,root,id,family==='tips'?1:0);
    if(!out.equals(instance)||instance.add(0x18).readU32()!==id||
        instance.add(0x1c).readU8()!==(family==='tips'?1:0))throw Error('Native item owner/flag ABI differs');
    if(!result||result.error)throw Error(result?.error||'Native setter was not called');
    return result;
}
rpc.exports={
    load(model){nativeModel=model;return {runtime:Script.runtime};},
    run(samples,rawTips,rawHelp,capturedRows){
        const output=[];
        for(const sample of samples){
            const tips=makeLoader(sample,rawTips);
            const count=tips.blob.add(84).readU32(),stride=tips.blob.add(80).readU32(),start=tips.blob.add(76).readU32();
            if(count!==266||stride!==56)throw Error('Unexpected production Tips layout');
            for(let row=0;row<count;row++){
                const flag=rawTips[start+row*56+2]|rawTips[start+row*56+3]<<8;
                if(tips.blob.add(start+row*56+2).readU16()!==Math.min((flag+7400)&0xffff,7799))
                    throw Error('Native full-record conversion differs');
            }
            const helpBlob=keep(Memory.alloc(rawHelp.length));helpBlob.writeByteArray(bytes(rawHelp));
            const help=keep(Memory.alloc(64));help.add(0x10).writePointer(helpBlob);help.add(0x20).writePointer(helpBlob.add(8));help.add(0x28).writeU32(0);
            const helpStart=helpBlob.add(76).readU32(),helpStride=helpBlob.add(80).readU32(),helpCount=helpBlob.add(84).readU32();
            for(let row=0;row<helpCount;row++){
                const at=helpStart+row*helpStride+8;helpBlob.add(at).writePointer(helpBlob.add(helpBlob.add(at).readU32()));
            }
            const manager=keep(Memory.alloc(512));
            for(const [offset,table] of [[0x158,tips.table],[0x178,help]]){
                const wrapper=keep(Memory.alloc(16));wrapper.add(8).writePointer(table);manager.add(offset).writePointer(wrapper);
            }
            const enabled=new TableIdentities(nativeModel.table_identities,scriptSha256,['tips_u16_flag_add7400_cap7799_v1']);
            const disabled=new TableIdentities(nativeModel.table_identities,scriptSha256);
            const cases=[];
            for(const captured of capturedRows){
                for(const family of ['tips','help']){
                    const candidates=nativeModel.table_identities.sources[captured.original].filter(c=>
                        c.key.startsWith('table/t_'+family+'.tbl/')&&c.field_at===(family==='tips'?40:8));
                    if(candidates.length!==1)throw Error('Physical owner not unique for test input');
                    const candidate=candidates[0];
                    const id=family==='tips'?(candidate.record_at-start)/56:
                        parseInt(candidate.record.slice(2,4)+candidate.record.slice(0,2),16);
                    const expected=nativeModel.table_identities.models[candidate.key].model.pairs[captured.original];
                    const value=nativeItem(sample,manager,enabled,family,id,captured);
                    if(value.selected_key!==candidate.key||value.plan.text!==`<R>${expected[0]}</R${expected[1]}>`)
                        throw Error('Full native producer / identity / final render differs');
                    cases.push({source:captured.original,family,native_id:id,selected_key:value.selected_key,plan:value.plan});
                    if(family==='tips'){
                        const negative=nativeItem(sample,manager,disabled,family,id,captured);
                        if(negative.selected_key!==null||negative.plan.text!==captured.original||
                            !negative.trace.some(e=>e.stage==='record_mismatch'))throw Error('Unverified conversion did not fail closed');
                    }
                }
            }
            const limits=[];
            for(const [raw,expected] of [[399,7799],[400,7799],[65535,7399]]){
                const loaded=makeLoader(sample,rawTips,raw);const value=loaded.blob.add(start+2).readU16();
                if(value!==expected)throw Error('Native AX/cap arithmetic differs');
                limits.push({raw,result:value,diagnostics:loaded.notes});
            }
            output.push({sample:sample.sha256,converted_records:count,cases,limits});
        }
        return {samples:output,new_game_attach:false,candidate_live_verified:false};
    }
};
