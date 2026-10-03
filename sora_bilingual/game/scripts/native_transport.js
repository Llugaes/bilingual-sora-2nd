// Bounded RPC messages; only a complete staged model can replace the active one.
// The file's ArrayBuffer is external memory. Keeping millions of decoded model
// objects alive made V8's natural major collections stall native hooks ~300 ms.
// This reader retains a bounded working set, with exact, collision-checked keys.
function readIndexedModel(buffer) {
    const view=new DataView(buffer),invalid=()=>{throw Error('Invalid indexed model');};
    if(view.byteLength<32||view.getUint32(0,true)!==0x41524f53||view.getUint32(4,true)!==0x32444f4d||
            view.getUint32(8,true)!==2)invalid();
    const count=view.getUint32(12,true),root=view.getUint32(16,true),table=view.getUint32(20,true),
        data=view.getUint32(24,true),size=view.getUint32(28,true);
    if(!count||count>4000000||root>=count||table!==32||data!==32+count*16||size!==view.byteLength||data>size)invalid();
    const u32=at=>view.getUint32(at,true),node=id=>table+id*16;
    let hashes=new Uint32Array(count),hashed=new Uint8Array(count),keysSeen=new Uint32Array(count);
    const storedHash=id=>{
        if(hashed[id])return hashes[id];
        const row=node(id),length=u32(row+4),start=data+u32(row+8);
        let hash=2166136261;
        for(let i=0;i<length;i++)hash=Math.imul(hash^view.getUint16(start+i*2,true),16777619);
        hashes[id]=hash>>>0;hashed[id]=1;return hash>>>0;
    };
    for(let id=0;id<count;id++) {
        const row=node(id),kind=u32(row),length=u32(row+4),offset=u32(row+8),bytes=u32(row+12);
        const expected=kind<2?0:kind===2?8:kind===3?length*2:kind===4?length*4:kind===5?length*16:-1;
        if(expected<0||bytes!==expected||offset%4||data+offset+bytes>size||
                (kind===0&&length!==0)||(kind===1&&length>1)||(kind===2&&length!==0))invalid();
        const start=data+offset;
        if(kind===4||kind===5) {
            for(let i=0;i<length*(kind===5?2:1);i++) {
                const ref=u32(start+i*4);
                if(ref>=id||(kind===5&&i%2===0&&u32(node(ref))!==3))invalid();
                if(kind===5&&i%2===0) {
                    if(keysSeen[ref]===id+1)invalid();
                    keysSeen[ref]=id+1;
                }
            }
            if(kind===5) {
                const index=start+length*8,seen=new Uint8Array(length);
                let previous=0;
                for(let i=0;i<length;i++) {
                    const hash=u32(index+i*8),entry=u32(index+i*8+4);
                    if((i&&hash<previous)||entry>=length||seen[entry]||
                            hash!==storedHash(u32(start+entry*8)))invalid();
                    seen[entry]=1;previous=hash;
                }
            }
        }
    }
    hashes=null;hashed=null;keysSeen=null;
    const cache=new Map(),MAX_NODES=4096,MAX_BYTES=2*1024*1024;
    let cachedBytes=0;
    function remember(id,value) {
        const bytes=typeof value==='string'?value.length*2:64;
        if(bytes>MAX_BYTES/4)return value;
        while(cache.size>=MAX_NODES||cachedBytes+bytes>MAX_BYTES) {
            const oldest=cache.keys().next().value;
            cachedBytes-=cache.get(oldest).bytes;cache.delete(oldest);
        }
        cache.set(id,{value,bytes});cachedBytes+=bytes;return value;
    }
    function hashKey(key) {
        let hash=2166136261;
        for(let i=0;i<key.length;i++)hash=Math.imul(hash^key.charCodeAt(i),16777619);
        return hash>>>0;
    }
    function keyEquals(id,key) {
        const row=node(id),length=u32(row+4),start=data+u32(row+8);
        if(length!==key.length)return false;
        for(let i=0;i<length;i++)if(view.getUint16(start+i*2,true)!==key.charCodeAt(i))return false;
        return true;
    }
    function find(start,length,key) {
        const hash=hashKey(key),index=start+length*8;
        let low=0,high=length;
        while(low<high) {
            const mid=(low+high)>>>1;
            if(u32(index+mid*8)<hash)low=mid+1;else high=mid;
        }
        for(let i=low;i<length&&u32(index+i*8)===hash;i++) {
            const entry=start+u32(index+i*8+4)*8;
            if(keyEquals(u32(entry),key))return u32(entry+4);
        }
        return -1;
    }
    function decode(id) {
        const cached=cache.get(id);
        if(cached){cache.delete(id);cache.set(id,cached);return cached.value;}
        const row=node(id),kind=u32(row),length=u32(row+4),start=data+u32(row+8);
        if(kind===0)return null;
        if(kind===1)return !!length;
        if(kind===2)return view.getFloat64(start,true);
        if(kind===3) {
            let text='';
            const units=new Uint16Array(buffer,start,length);
            for(let i=0;i<length;i+=2048)text+=String.fromCharCode(...units.subarray(i,i+2048));
            return remember(id,text);
        }
        const array=kind===4,target=array?[]:{};
        // Only scalar leaves are eager. A tree of small nested containers must
        // not recursively materialize an unbounded graph behind one cache key.
        let leaf=length<=(array?16:8);
        for(let i=0;leaf&&i<length;i++)
            if(u32(node(u32(start+(array?i*4:i*8+4))))>3)leaf=false;
        if(leaf) {
            for(let i=0;i<length;i++) {
                if(array)target.push(decode(u32(start+i*4)));
                else Object.defineProperty(target,decode(u32(start+i*8)),{
                    value:decode(u32(start+i*8+4)),enumerable:true,writable:true,configurable:true});
            }
            return remember(id,target);
        }
        if(array)target.length=length;
        let lastKey=null,lastRef=-1;
        const reference=key=>{
            if(typeof key!=='string')return -1;
            if(key===lastKey)return lastRef;
            lastKey=key;
            const index=array?Number(key):-1;
            lastRef=array?(Number.isInteger(index)&&index>=0&&index<length&&String(index)===key?
                u32(start+index*4):-1):find(start,length,key);
            return lastRef;
        };
        return remember(id,new Proxy(target,{
            get(object,key,receiver) {
                const ref=reference(key);
                return ref<0?Reflect.get(object,key,receiver):decode(ref);
            },
            has(object,key) {return reference(key)>=0||Reflect.has(object,key);},
            getOwnPropertyDescriptor(object,key) {
                const ref=reference(key);
                return ref<0?Reflect.getOwnPropertyDescriptor(object,key):
                    {value:decode(ref),enumerable:true,writable:false,configurable:true};
            },
            ownKeys() {
                if(array)return Array.from({length},(_,i)=>String(i)).concat('length');
                const numeric=[],other=[];
                for(let i=0;i<length;i++) {
                    const key=decode(u32(start+i*8)),index=Number(key);
                    if(Number.isInteger(index)&&index>=0&&index<4294967295&&String(index)===key)numeric.push(key);
                    else other.push(key);
                }
                numeric.sort((a,b)=>Number(a)-Number(b));return numeric.concat(other);
            },
            // Model data is immutable; resolver caches live outside this graph.
            set(){return false;},defineProperty(){return false;},deleteProperty(){return false;},
            preventExtensions(){return false;},setPrototypeOf(){return false;}
        }));
    }
    return decode(root);
}

(() => {
    let staged=null;
    rpc.exports.modelwireversion=()=>2;
    rpc.exports.modelpackedfile=function(path,mode,active,scale,layout) {
        if(path.endsWith('.wire.bin'))
            return rpc.exports.load(readIndexedModel(File.readAllBytes(path)),mode,active,scale,layout);
        const payload=JSON.parse(File.readAllText(path));
        if(payload.schema!==1||!Array.isArray(payload.nodes)||payload.nodes.length>4000000)
            throw Error('Invalid packed model');
        const nodes=payload.nodes;
        const reference=(id,limit)=>{
            if(!Number.isInteger(id)||id<0||id>=limit)throw Error('Invalid model reference');
            return nodes[id];
        };
        for(let i=0;i<nodes.length;i++) {
            const row=nodes[i];
            if(!Array.isArray(row)) {
                if(row!==null&&!['string','number','boolean'].includes(typeof row))throw Error('Invalid model value');
                continue;
            }
            if(row[0]===0) {
                const value=new Array(row.length-1);
                for(let j=1;j<row.length;j++)value[j-1]=reference(row[j],i);
                nodes[i]=value;
            } else if(row[0]===1&&row.length%2===1) {
                const value={};
                for(let j=1;j<row.length;j+=2) {
                    const key=reference(row[j],i),item=reference(row[j+1],i);
                    if(typeof key!=='string'||Object.hasOwn(value,key))throw Error('Invalid model key');
                    if(key==='__proto__')Object.defineProperty(value,key,{value:item,enumerable:true,writable:true,configurable:true});
                    else value[key]=item;
                }
                nodes[i]=value;
            } else throw Error('Invalid model node');
        }
        return rpc.exports.load(reference(payload.root,nodes.length),mode,active,scale,layout);
    };
    rpc.exports.modelbegin=function(token) {
        if(typeof token!=='string'||!token)throw Error('Invalid model transfer');
        staged={token,chunks:[],length:0};return true;
    };
    rpc.exports.modelpart=function(token,index,text) {
        if(!staged||staged.token!==token||index!==staged.chunks.length)throw Error('Out-of-order model transfer');
        if(typeof text!=='string'||text.length>1048576)throw Error('Oversized model part');
        staged.chunks.push(text);staged.length+=text.length;return true;
    };
    rpc.exports.modelabort=function(token) {
        if(staged&&staged.token===token)staged=null;return true;
    };
    rpc.exports.modelcommit=function(token,count,length,mode,active,scale,layout) {
        if(!staged||staged.token!==token||staged.chunks.length!==count||staged.length!==length)
            throw Error('Incomplete model transfer');
        const transfer=staged;staged=null;
        let text=transfer.chunks.join('');transfer.chunks.length=0;
        const model=JSON.parse(text);text=null;
        return rpc.exports.load(model,mode,active,scale,layout);
    };
})();
