// A parked agent owns no external process. Authenticated loopback control lets
// a new tool process reuse it instead of installing a second set of hooks.
(() => {
    let listener=null,owner=null,secret=null;
    const limit=16*1024*1024;
    const methods=new Set(['modelwireversion','modelpackedfile','fonts','select','style','configure','reloadlogic','disable','replay','status','snapshot']);
    const encode=value=>{
        const text=JSON.stringify(value).replace(/[^\x00-\x7f]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
        if(text.length>limit)throw Error('Control response too large');
        const bytes=new Uint8Array(text.length+4);new DataView(bytes.buffer).setUint32(0,text.length,true);
        for(let i=0;i<text.length;i++)bytes[i+4]=text.charCodeAt(i);
        return bytes.buffer;
    };
    async function read(connection,max) {
        const header=await connection.input.readAll(4),size=new DataView(header).getUint32(0,true);
        if(!size||size>max)throw Error('Invalid control frame');
        const data=new Uint8Array(await connection.input.readAll(size));let text='';
        for(let at=0;at<data.length;at+=8192)text+=String.fromCharCode(...data.subarray(at,at+8192));
        return JSON.parse(text);
    }
    async function serve(connection) {
        const timeout=setTimeout(()=>connection.close().catch(()=>{}),3000);
        try {
            await connection.setNoDelay(true);
            const hello=await read(connection,4096);
            if(hello.token!==secret||hello.method!=='hello'||owner!==null)throw Error('Unavailable control session');
            clearTimeout(timeout);owner=connection;
            await connection.output.writeAll(encode({ok:true,value:{protocol:1,pid:Process.id}}));
            while(owner===connection) {
                const request=await read(connection,limit);
                let result;
                try {
                    if(!methods.has(request.method)||!Array.isArray(request.args))throw Error('Unknown control operation');
                    result={ok:true,value:await rpc.exports[request.method](...request.args)};
                } catch(error) {result={ok:false,error:String(error)};}
                await connection.output.writeAll(encode(result));
            }
        } catch (_) {
            // A normal exit and an unexpected lost client both remove effects.
        } finally {
            clearTimeout(timeout);
            if(owner===connection){rpc.exports.disable();owner=null;}
            await connection.close().catch(()=>{});
        }
    }
    rpc.exports.startcontrol=async function(token) {
        if(listener!==null)throw Error('Control already started');
        if(typeof token!=='string'||token.length!==64)throw Error('Invalid control identity');
        secret=token;
        listener=await Socket.listen({family:'ipv4',host:'127.0.0.1',port:0});
        (async()=>{while(listener!==null){try{serve(await listener.accept());}catch(_){break;}}})();
        return {protocol:1,pid:Process.id,port:listener.port};
    };
})();
