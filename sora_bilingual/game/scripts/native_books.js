'use strict';
// Version-bound book adapter. The game continues to own its reader, input,
// page indicator, animations and image loader. Only two read-only table
// queries return owned document pages while the MOD is active.
function createNativeBooks(base,report,state) {
    if(!report.native.book_count||!report.native.book_page||!report.native.book_update)return null;
    const records=new Map(),inputs=new Map(),bindings=new Map(),frames=new Map();
    const update=new NativeFunction(base.add(report.native.book_update.rva),'void',['pointer','uint']);
    function stamp() {const s=state();return {books:s.books,key:JSON.stringify([s.active,s.mode,s.style])};}
    const inReader=caller=>caller.compare(base.add(0x406320))>=0&&caller.compare(base.add(0x409000))<0;
    function pages(id) {const s=state();return s.active?s.books?.pages(id,s.mode,s.style):null;}
    function nativeCount(id) {return state().books?.documents[id]?.source.length||0;}
    function record(id,page,value) {
        const key=id+':'+page;let row=records.get(key);
        if(!row) {
            row={pointer:Memory.alloc(24),source:null,image:null};records.set(key,row);
            row.pointer.writeU16(id);row.pointer.add(2).writeU16(page);row.pointer.add(4).writeU32(0);
        }
        if(row.source!==value.source) {
            if(row.body)inputs.delete(String(row.body));
            row.body=Memory.allocUtf8String(value.source);row.source=value.source;
            row.pointer.add(8).writePointer(row.body);
            inputs.set(String(row.body),{id,page,source:value.source});
        }
        if(row.image!==value.image) {
            row.imageBuffer=Memory.allocUtf8String(value.image);row.image=value.image;
            row.pointer.add(16).writePointer(row.imageBuffer);
        }
        const origin=inputs.get(String(row.body));
        origin.nativePage=value.nativePage;
        origin.pageCount=pages(id)?.length||nativeCount(id);
        origin.controller=frames.get(Process.getCurrentThreadId())?.at(-1)?.controller||null;
        return row.pointer;
    }
    const listeners=[];
    listeners.push(Interceptor.attach(base.add(report.native.book_count.rva),{
        onEnter(args){this.id=inReader(this.returnAddress)?args[1].toUInt32()&0xffff:null;},
        onLeave(result){if(this.id!==null){const value=pages(this.id);if(value)result.replace(value.length);}}
    }));
    listeners.push(Interceptor.attach(base.add(report.native.book_page.rva),{
        onEnter(args) {
            this.value=null;this.request=null;if(!inReader(this.returnAddress))return;
            const id=args[1].toUInt32()&0xffff,page=args[2].toUInt32()&0xffff;
            this.request={id,page};
            const available=pages(id),count=nativeCount(id);
            if(available&&page>=1&&page<=available.length)this.value={id,page,value:available[page-1]};
            // Native lookup still executes; it must see a real source page,
            // including during the frame that switches the MOD off.
            if(count)args[2]=ptr(this.value?this.value.value.nativePage:Math.min(count,Math.max(1,page)));
        },
        onLeave(result){
            if(this.value){const {id,page,value}=this.value;result.replace(record(id,page,value));}
            else if(this.request&&!result.isNull()) {
                const controller=frames.get(Process.getCurrentThreadId())?.at(-1)?.controller;
                if(controller) {
                    const body=result.add(8).readPointer();
                    const page=result.add(2).readU16();
                    inputs.set(String(body),{id:this.request.id,page,nativePage:page,pageCount:nativeCount(this.request.id),source:body.readUtf8String(),controller});
                }
            }
        }
    }));
    listeners.push(Interceptor.attach(base.add(report.native.book_update.rva),{
        onEnter(args) {
            this.thread=Process.getCurrentThreadId();
            const stack=frames.get(this.thread)||[];
            this.frame={controller:args[0],stamp:stamp()};stack.push(this.frame);frames.set(this.thread,stack);
            const controller=args[0],id=controller.add(0x1a8).readU32();
            const available=pages(id),count=available?.length||nativeCount(id);
            if(!count)return;
            if(available&&report.native.book_open_return&&this.returnAddress.equals(base.add(report.native.book_open_return.rva))) {
                // Opening reads the game's physical bookmark. Navigation and
                // our settings refresh already carry a document page number.
                const saved=args[1].toUInt32(),found=available.findIndex(p=>p.nativePage>=saved);
                const page=found<0?available.length:found+1;
                args[1]=ptr(page);controller.add(0x1a4).writeU32(page);
            }
            const slot=controller.add(0x1a4),current=slot.readU32();
            const next=Math.max(1,Math.min(count,current));if(next!==current)slot.writeU32(next);
        },
        onLeave() {
            const stack=frames.get(this.thread);if(stack?.at(-1)===this.frame)stack.pop();
            if(!stack?.length)frames.delete(this.thread);
            for(const binding of bindings.values())if(binding.controller.equals(this.frame.controller))binding.stamp=this.frame.stamp;
        }
    }));
    if(report.native.book_saved_page)listeners.push(Interceptor.attach(base.add(report.native.book_saved_page.rva),{
        onEnter() {
            const controller=this.context.rsi,id=controller.add(0x1a8).readU32(),index=controller.add(0x1a4).readU32();
            const value=pages(id)?.[index-1];if(value)this.context.rax=ptr(value.nativePage);
        }
    }));
    return {
        listeners,
        input(pointer,source,caller) {
            if(!caller?.equals(base.add(report.native.book_text_return.rva)))return null;
            const value=inputs.get(String(pointer));return value?.source===source?value:null;
        },
        bind(label,origin) {
            if(origin?.controller)bindings.set(String(label),{controller:origin.controller,origin:{...origin},stamp:stamp(),refreshing:false});
            else bindings.delete(String(label));
        },
        forget(label) {bindings.delete(String(label));},
        refresh(label) {
            const binding=bindings.get(String(label));if(!binding||binding.refreshing)return;
            const next=stamp();if(binding.stamp.books===next.books&&binding.stamp.key===next.key)return;
            binding.refreshing=true;
            try {
                const origin=binding.origin,available=pages(origin.id);
                const index=available?Math.min(available.length,Math.floor((origin.page-1)*available.length/origin.pageCount)+1):origin.nativePage;
                binding.controller.add(0x1a4).writeU32(index);
                update(binding.controller,index);binding.stamp=next;
            }
            finally {binding.refreshing=false;}
        },
        context(origin,source) {const s=state();return origin&&s.active?s.books?.context(origin.id,origin.page,source,s.mode,s.style):null;}
    };
}
