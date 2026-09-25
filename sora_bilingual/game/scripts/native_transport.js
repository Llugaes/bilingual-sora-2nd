// Bounded RPC messages; only a complete staged model can replace the active one.
(() => {
    let staged=null;
    rpc.exports.modelpackedfile=function(path,mode,active,scale,layout) {
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
