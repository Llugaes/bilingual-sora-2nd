'use strict';
// Font delivery owns a complete face (metrics + atlas), never one half of it.
// The native adapter stages resources away from label Update; Update only
// publishes a ready pointer. Originals remain alive until native font reset.
function createRuntimeFonts(api) {
    let manifest=null,pending=null,applied=null,enabled=true,generation=0;
    let state='unconfigured',error=null;
    const cache=new Map(),inflight=new Map();
    function status(){return {state,error,ready:state==='ready',cached:cache.size};}
    function restore() {
        pending=null;
        if(applied) {
            if(api.current()===applied.face)api.publish(applied.original);
            applied=null;
        }
    }
    async function prepare() {
        const serial=++generation;
        error=null;
        if(!manifest||!enabled){state=manifest?'disabled':'unconfigured';return status();}
        pending=null;
        if(applied&&api.current()===applied.face){state='ready';return status();}
        applied=null;state='preparing';
        try {
            const original=api.current(),identity=api.identity(original);
            const row=manifest.faces.find(row=>row.source_sha256===identity.sha256||row.sha256===identity.sha256);
            if(!row)throw Error('当前游戏字库与已验证的原始字库不符');
            if(row.sha256===identity.sha256){state='ready';return status();}
            const key=row.sha256+':'+identity.size;
            let face=cache.get(key);
            if(!face) {
                let job=inflight.get(key);
                if(!job) {
                    if(cache.size+inflight.size>=4)throw Error('字体基准发生了不受支持的变化，未继续分配贴图');
                    job=Promise.resolve(api.stage(row,identity.size)).then(value=>{
                        cache.set(key,value);return value;
                    }).finally(()=>inflight.delete(key));
                    inflight.set(key,job);
                }
                face=await job;
            }
            if(serial!==generation||!enabled)return status();
            if(api.current()!==original)throw Error('字体准备期间游戏字库已切换，请重试');
            pending={original,face};state='applying';
        } catch(reason) {
            if(serial===generation){state='error';error=String(reason);}
        }
        return status();
    }
    return {
        configure(value) {
            if(!value||value.version!==1||!Array.isArray(value.faces)||!value.faces.length||value.faces.length>4)
                throw Error('Invalid runtime font manifest');
            if(manifest&&JSON.stringify(manifest)!==JSON.stringify(value))
                throw Error('Runtime font candidate cannot change inside an existing game');
            manifest=value;return prepare();
        },
        tick() {
            if(!pending||(!enabled&&!pending.restore))return false;
            const next=pending;pending=null;
            if(api.current()!==next.original){state='error';error='游戏字库已切换，未应用过期字体';return false;}
            api.publish(next.face);applied=next.restore?null:next;state=next.restore?'disabled':'ready';return true;
        },
        beforeReset() {++generation;restore();state=manifest?'preparing':'unconfigured';},
        afterLoad(){return prepare();},
        select(active) {
            if(enabled===active)return;
            enabled=active;
            if(!active){
                ++generation;pending=applied?{original:applied.face,face:applied.original,restore:true}:null;
                state=manifest?'disabling':'unconfigured';
            }
            else return prepare();
        },
        isReady(){return state==='ready';},
        status
    };
}
if(typeof module!=='undefined')module.exports={createRuntimeFonts};
