'use strict';
// Redirect only the synchronous image-cache CALL, not the global file reader
// (which the optional loose-file DLL may already detour). The C bridge keeps
// unrelated resource reads out of JavaScript and preserves all five arguments.
function installFontImageBridge(entry,original,routes) {
    if(!Array.isArray(routes)||!routes.length||routes.length>4)throw Error('Invalid font routes');
    const owners=[],table=Memory.alloc(16*routes.length);
    routes.forEach((row,index)=>{
        if(!/^sora_font_[a-f0-9]{64}$/.test(row.alias)||typeof row.path!=='string'||row.path.includes('\0'))
            throw Error('Invalid font image route');
        const alias=Memory.allocUtf8String(row.alias+'.dds'),path=Memory.allocUtf8String(row.path);
        owners.push(alias,path);table.add(index*16).writePointer(alias);table.add(index*16+8).writePointer(path);
    });
    const count=Memory.alloc(4);count.writeU32(routes.length);
    const before=new Uint8Array(entry.readByteArray(5));
    if(before[0]!==0xe8||!entry.add(5).add(new DataView(before.buffer).getInt32(1,true)).equals(original))
        throw Error('Image-cache reader CALL differs from the verified executable');
    const bridge=new CModule(`
        #include <gum/guminterceptor.h>
        typedef struct {const char *name; const char *path;} Route;
        extern Route routes[];
        extern unsigned int route_count;
        static int equal(const char *a,const char *b) {
            for(unsigned int i=0;i<128;i++) {if(a[i]!=b[i])return 0;if(!a[i])return 1;}return 0;
        }
        void read_image(GumInvocationContext *context) {
            const char *path=gum_invocation_context_get_nth_argument(context,1);
            if(!path)return;
            const char *name=path;
            for(unsigned int i=0;i<512&&path[i];i++)if(path[i]=='/'||path[i]=='\\\\')name=path+i+1;
            for(unsigned int i=0;i<route_count;i++)if(equal(name,routes[i].name)) {
                gum_invocation_context_replace_nth_argument(context,1,(void *)routes[i].path);return;
            }
        }
    `,{routes:table,route_count:count});
    // Interceptor owns instruction relocation and thread-safe installation;
    // do not hand-write a five-byte CALL while another game thread may run it.
    const listener=Interceptor.attach(entry,{onEnter:bridge.read_image});
    Interceptor.flush();
    return {owners,table,count,bridge,listener}; // resident lifetime, never hot-unloaded
}

function createFontMaterialRefresh(base,report) {
    const rebuild=new NativeFunction(base.add(report.native.font_rebind.rva),'void',['pointer']);
    return label=>{
        const manager=base.add(report.font_manager_global).readPointer(),index=label.add(0x300).readU32();
        const count=manager.add(0x10).readU32();
        if(count>1024)throw Error('Invalid font manager count');
        // The engine explicitly supports an unbound index with a null image.
        const image=index<count?manager.add(8).readPointer().add(index*8).readPointer().add(0x20).readPointer():ptr(0);
        const material=label.add(0x650).readPointer();
        const hasShadow=!label.add(0x680).readPointer().add(0x40).readPointer().isNull();
        const shadow=hasShadow?label.add(0x658).readPointer():ptr(0);
        if(!material.isNull()&&material.add(0x30).readPointer().equals(image)&&
            (shadow.isNull()||shadow.add(0x30).readPointer().equals(image)))return false;
        // Label vtable +0x28 rebuilds the normal material and all primitive
        // references, retires icon batches and invalidates the shadow batch.
        // Its released shadow handle remains in +0x658 until the next Draw;
        // clear it so a second font switch/destruction cannot release it twice.
        rebuild(label);label.add(0x658).writePointer(ptr(0));
        return true;
    };
}

function createNativeFonts(base,report,hash,onPublish) {
    const point=name=>base.add(report.native[name].rva);
    const manager=()=>base.add(report.font_manager_global).readPointer();
    const imageCache=()=>base.add(report.image_cache_global).readPointer();
    const allocate=new NativeFunction(point('font_allocate'),'pointer',['pointer','uint64']);
    const readFont=new NativeFunction(point('font_read'),'int',['pointer','pointer','pointer']);
    const acquire=new NativeFunction(point('font_image_acquire'),'pointer',['pointer','pointer','uint','int']);
    const reset=new NativeFunction(point('font_reset'),'void',['pointer']);
    let bridge=null,configured=null,pendingConfig=null,reloadRequested=false,enableRequested=false,requestedActive=true;
    const current=()=>{
        const owner=manager();
        if(owner.isNull()||owner.add(0x10).readU64().compare(1)!==0)throw Error('Unexpected game font count');
        return String(owner.add(8).readPointer().readPointer());
    };
    const identity=value=>{
        const face=ptr(value),data=face.add(8).readPointer();
        const bytes=40+data.add(36).readU32(),glyphs=data.add(8).readU32();
        if(bytes<40||bytes>16*1024*1024||bytes!==40+glyphs*24||data.add(32).readU32()!==0x49544c46)
            throw Error('Invalid live FNT header');
        const size=face.add(0x28).readU32();
        if(size<1||size>512)throw Error('Invalid live font size');
        return {sha256:hash.pointer(data,bytes),size};
    };
    function release(face) {
        const temporary=Memory.alloc(32),vector=Memory.alloc(8);
        vector.writePointer(face);temporary.add(8).writePointer(vector);
        temporary.add(16).writeU64(1);temporary.add(24).writeU64(1);
        reset(temporary); // engine owns the allocator, FNT and image-ref cleanup
    }
    const session=createRuntimeFonts({current,identity,
        publish(value){manager().add(8).readPointer().writePointer(ptr(value));onPublish();},
        stage(row,size) {return new Promise((resolve,reject)=>setImmediate(()=>{
            // Called from the control/event-loop thread, never label Update.
            try {
                for(const [path,digest] of [[row.path,row.sha256],[row.image.path,row.image.sha256]])
                    if(hash(File.readAllBytes(path))!==digest)throw Error('Prepared font file changed');
                const heap=base.add(report.font_allocator_global).readPointer();
                if(heap.isNull()||imageCache().isNull())throw Error('Font resources are not initialized');
                const face=allocate(heap.add(8),48);
                if(face.isNull())throw Error('Cannot allocate a font face');
                face.writeByteArray(new Uint8Array(48));
                try {
                    if(readFont(ptr(0),face,Memory.allocUtf8String(row.path))!==0)throw Error('Cannot read prepared FNT');
                    face.add(0x28).writeU32(size); // use engine setting, not FNT nominal size
                    if(identity(String(face)).sha256!==row.sha256)throw Error('Loaded FNT does not match candidate');
                    const image=acquire(imageCache(),Memory.allocUtf8String(row.alias),0,0);
                    face.add(0x20).writePointer(image);
                    if(image.isNull())throw Error('Cannot load prepared font atlas');
                    const resource=image.add(8).readPointer();
                    if(resource.isNull()||resource.add(0x48).readU32()!==0xb224cb11||resource.add(0x64).readU32()!==1||
                        image.add(0x1c).readU32()!==row.image.width||image.add(0x20).readU32()!==row.image.height)
                        throw Error('Prepared font atlas is incomplete');
                    resolve(String(face));
                } catch(error) {release(face);throw error;}
            } catch(error) {reject(error);}
        }));}
    });
    const refreshLabel=createFontMaterialRefresh(base,report);
    return {...session,refreshLabel,
        configure(manifest) {
            if(!manifest||manifest.version!==1||!Array.isArray(manifest.faces)||manifest.faces.length!==4)
                throw Error('Invalid runtime font manifest');
            for(const row of manifest.faces) {
                if(!/^[a-f0-9]{64}$/.test(row.sha256)||!/^[a-f0-9]{64}$/.test(row.source_sha256)||
                    !row.image||!/^[a-f0-9]{64}$/.test(row.image.sha256)||row.alias!=='sora_font_'+row.image.sha256||
                    !Number.isInteger(row.image.width)||!Number.isInteger(row.image.height)||
                    row.image.width<=0||row.image.height<=0||row.image.width*row.image.height>32*1024*1024||
                    [row.path,row.image.path].some(p=>typeof p!=='string'||p.includes('\0')||!/^([A-Za-z]:[\\/]|\\\\)/.test(p)))
                    throw Error('Invalid runtime font face');
            }
            if(configured&&JSON.stringify(configured)!==JSON.stringify(manifest))
                throw Error('Runtime font candidate cannot change inside an existing game');
            if(!bridge)bridge=installFontImageBridge(point('font_image_read_call'),base.add(report.font_file_read),
                manifest.faces.map(row=>({alias:row.alias,path:row.image.path})));
            configured=manifest;pendingConfig=manifest;
            return {state:'preparing',ready:false};
        },
        tick() {
            // Capture the currently owned face on the game's UI callback.
            // Only the immutable candidate is touched during background IO.
            if(enableRequested){enableRequested=false;session.select(true);}
            if(pendingConfig){const value=pendingConfig;pendingConfig=null;session.configure(value);reloadRequested=false;}
            if(reloadRequested){reloadRequested=false;session.afterLoad();}
            return session.tick();
        },
        select(active){
            if(active===requestedActive)return;
            requestedActive=active;
            if(active)enableRequested=true;else{enableRequested=false;session.select(false);}
        },
        isReady(){return !pendingConfig&&!reloadRequested&&!enableRequested&&session.isReady();},
        status(){const value=session.status();return pendingConfig||reloadRequested||enableRequested?{...value,state:'preparing',ready:false}:value;},
        isManager(value){return value.equals(manager());},
        loaded(){reloadRequested=true;}
    };
}
if(typeof module!=='undefined')module.exports={installFontImageBridge,createNativeFonts};
