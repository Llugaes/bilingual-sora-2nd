// Native ABI + real File/CNG calls with fixture-owned engine resources.
// This exercises production staging, not the game's texture decoder/GPU.
rpc.exports.adapter=async function(manifest,originalBytes,failUpload=false) {
    const owners=[],keep=value=>(owners.push(value),value);
    const root=keep(Memory.alloc(128)),manager=keep(Memory.alloc(32)),vector=keep(Memory.alloc(8));
    root.add(16).writePointer(manager);root.add(24).writePointer(keep(Memory.alloc(64)));
    root.add(32).writePointer(keep(Memory.alloc(64)));
    manager.add(8).writePointer(vector);manager.add(16).writeU64(1);manager.add(24).writeU64(1);
    function setFace(face,data){face.writePointer(data);face.add(8).writePointer(data);face.add(16).writePointer(data.add(40));face.add(24).writeU32(1);face.add(40).writeU32(48);}
    const original=keep(Memory.alloc(48)),oldData=keep(Memory.alloc(originalBytes.length));
    oldData.writeByteArray(originalBytes);setFace(original,oldData);vector.writePointer(original);
    let inTick=false,stagedInTick=false,uploads=0,releases=0,publishes=0;
    const allocate=keep(new NativeCallback((heap,size)=>keep(Memory.alloc(size.toNumber())),'pointer',['pointer','uint64']));
    const read=keep(new NativeCallback((unused,face,path)=>{
        stagedInTick||=inTick;
        const bytes=File.readAllBytes(path.readUtf8String()),data=keep(Memory.alloc(bytes.byteLength));
        data.writeByteArray(bytes);setFace(face,data);return 0;
    },'int',['pointer','pointer','pointer']));
    const acquire=keep(new NativeCallback(()=>{
        stagedInTick||=inTick;uploads++;
        if(failUpload)return ptr(0);
        const image=keep(Memory.alloc(64)),resource=keep(Memory.alloc(128));
        resource.add(0x48).writeU32(0xb224cb11);resource.add(0x64).writeU32(1);
        image.add(8).writePointer(resource);image.add(0x1c).writeU32(4);image.add(0x20).writeU32(4);return image;
    },'pointer',['pointer','pointer','uint','int']));
    const reset=keep(new NativeCallback(temp=>{check(!temp.equals(manager),'cleanup touched live manager');releases++;},'void',['pointer']));
    const entry=keep(Memory.alloc(Process.pageSize,{near:native.original_read,maxDistance:0x7fffffff}));
    Memory.patchCode(entry,16,p=>{const w=new X86Writer(p,{pc:entry});w.putCallAddress(native.original_read);w.flush();w.dispose();});
    Memory.protect(entry,Process.pageSize,'r-x');
    const point=p=>({rva:p.sub(root).toString()}),report={
        font_manager_global:16,font_allocator_global:24,image_cache_global:32,
        font_file_read:native.original_read.sub(root).toString(),
        native:{font_allocate:point(allocate),font_read:point(read),font_reset:point(reset),
            font_image_acquire:point(acquire),font_image_read_call:point(entry),font_rebind:point(reset)}
    };
    const runtime=createNativeFonts(root,report,createNativeSha256(),()=>{check(inTick,'publication outside UI tick');publishes++;});
    function tick(){inTick=true;try{return runtime.tick();}finally{inTick=false;}}
    function current(){return vector.readPointer();}
    async function finish(){
        for(let i=0;i<100;i++){
            await new Promise(resolve=>setTimeout(resolve,5));
            if(['applying','error'].includes(runtime.status().state))return;
        }
        throw Error('staging did not complete');
    }
    runtime.configure(manifest);check(current().equals(original),'configure published early');
    tick();check(current().equals(original),'staging published early');await finish();
    if(failUpload){
        check(runtime.status().state==='error'&&releases===1&&current().equals(original),'failed atlas cleanup');
        check(!tick()&&publishes===0,'failed face published');
        return {passed:true,uploads,releases,publishes};
    }
    check(runtime.status().state==='applying',JSON.stringify(runtime.status()));
    check(!stagedInTick,'file/atlas loading ran during UI Update');
    tick();check(runtime.status().ready&&!current().equals(original),'complete face not applied');
    check(current().add(40).readU32()===48,'engine base size changed');
    runtime.select(false);check(!current().equals(original),'RPC restored outside UI Update');
    tick();check(current().equals(original),'exit did not restore original');
    runtime.select(true);tick();tick();check(runtime.status().ready&&uploads===1,'cached atlas uploaded again');
    runtime.select(false);tick();
    // Native reload can select an unknown third-party face. Keep it intact.
    oldData.add(40).writeU32(0x1234);runtime.loaded();tick();
    await new Promise(resolve=>setTimeout(resolve,5));
    runtime.select(true);tick();
    check(runtime.status().state==='error'&&current().equals(original),'unknown font was overwritten');
    check(releases===0,'cached successful face freed');
    return {passed:true,uploads,publishes,stagedInTick,scope:'native adapter fixture; GPU not exercised'};
};
