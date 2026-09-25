'use strict';
// Full SHA-256 via Windows CNG. No address-only cache: recycled resource
// addresses still get verified against their actual bytes on every lookup.
// https://learn.microsoft.com/en-us/windows/win32/api/bcrypt/nf-bcrypt-bcrypthash
function createNativeSha256() {
    const dll=Module.load('bcrypt.dll');
    const open=new NativeFunction(dll.getExportByName('BCryptOpenAlgorithmProvider'),'int',['pointer','pointer','pointer','uint']);
    const hash=new NativeFunction(dll.getExportByName('BCryptHash'),'int',['pointer','pointer','uint','pointer','uint','pointer','uint']);
    const handle=Memory.alloc(Process.pointerSize);
    const status=open(handle,Memory.allocUtf16String('SHA256'),ptr(0),0);
    if(status!==0)throw Error('SHA-256 provider unavailable: '+status);
    const provider=handle.readPointer(); // One provider for this resident script.
    const buffers=new Map();
    const digest=data=>{
        const size=data.byteLength;
        if(!Number.isInteger(size)||size<0||size>32*1024*1024)throw Error('Hash input exceeds resource limit');
        const thread=Process.getCurrentThreadId();
        let scratch=buffers.get(thread);
        if(!scratch){scratch={output:Memory.alloc(32),input:null,capacity:0};buffers.set(thread,scratch);}
        // Isolated buffers survive a cooperative NativeFunction call without
        // being overwritten by another game's thread.
        let input=data.pointer;
        if(!input) {
            if(size>scratch.capacity||!scratch.input){scratch.input=Memory.alloc(Math.max(1,size));scratch.capacity=size;}
            input=scratch.input;input.writeByteArray(data);
        }
        const result=hash(provider,ptr(0),0,input,size,scratch.output,32);
        if(result!==0)throw Error('SHA-256 failed: '+result);
        return Array.from(new Uint8Array(scratch.output.readByteArray(32))).map(v=>v.toString(16).padStart(2,'0')).join('');
    };
    digest.pointer=(pointer,size)=>digest({pointer,byteLength:size});
    return digest;
}
if(typeof module!=='undefined')module.exports={createNativeSha256};
