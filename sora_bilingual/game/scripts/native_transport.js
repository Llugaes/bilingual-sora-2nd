// Bounded RPC messages; only a complete staged model can replace the active one.
(() => {
    let staged=null;
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
