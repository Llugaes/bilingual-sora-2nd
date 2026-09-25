'use strict';
// Shared pure resolver: runs synchronously inside the native label callback.
// No RPC, timers, pointers, filesystem access, or fuzzy substring matching.
class RuntimeText {
    constructor(model) {
        this.model = model;
        this.numeric = (model.numeric || []).map(([pattern, pair]) => [new RegExp('^(?:'+pattern+')$'), pair]);
        this.rawNumeric = (model.raw_numeric || []).map(([pattern,pair])=>[new RegExp('^(?:'+pattern+')$'),pair]);
        this.scoped = Object.fromEntries(Object.entries(model.scoped || {}).map(([k,v])=>[k,new RuntimeText(v)]));
        this.details = model.details ? new RuntimeText(model.details) : null;
        this.detailSources = new Set(model.detail_sources || []);
        this.cache = new Map();
        this.planCache = new Map();
        this.keyed = Object.fromEntries(Object.entries(model.keyed || {}).map(([k,v])=>[k,{source:v.source,tr:new RuntimeText(v.model)}]));
    }
    pair(source) {
        if (Object.hasOwn(this.model.plain_pairs,source)) return this.model.plain_pairs[source];
        let found=null;
        for(const [pattern,pair] of this.numeric) {
            const m=pattern.exec(source);
            if(!m || m[0]!==source)continue;
            const rendered=pair.map((target,side)=>{
                let i=1;
                return target.replace(/%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[dius]/g,()=>{
                    const v=m[i++];return (Object.hasOwn(this.model.plain_pairs,v)?this.model.plain_pairs[v]:[v,v])[side];
                });
            });
            if(found && JSON.stringify(found)!==JSON.stringify(rendered))return null;
            found=rendered;
        }
        return found;
    }
    rawPair(source) {
        if(Object.hasOwn(this.model.pairs,source))return this.model.pairs[source];
        if(!source.includes('<'))return null;
        let found=null;
        for(const [pattern,pair] of this.rawNumeric) {
            const m=pattern.exec(source);if(!m||m[0]!==source)continue;
            const rendered=pair.map((target,side)=>{
                let i=1;return target.replace(/%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[dius]/g,()=>{
                    const v=m[i++];return (Object.hasOwn(this.model.plain_pairs,v)?this.model.plain_pairs[v]:[v,v])[side];
                });
            });
            if(found&&JSON.stringify(found)!==JSON.stringify(rendered))return null;found=rendered;
        }
        return found;
    }
    static ruby(a,b) {
        if(!a||!b)return a;
        const sameCjk=a===b && /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(a);
        if(a===b&&!sameCjk)return a;
        if(/[<>]/.test(a+b))return null;
        const left=a.replace(/\\n/g,'\n').split(/(\r\n|\n)/),right=b.replace(/\\n/g,'\n').split(/\r\n|\n/);
        if((left.length+1)/2!==right.length || left.some((v,i)=>!(i%2)&&Boolean(v.trim())!==Boolean(right[i/2].trim())))return null;
        return left.map((v,i)=>i%2?v:v&&right[i/2]&&(v!==right[i/2]||sameCjk)?'<R>'+v+'</R'+right[i/2]+'>':v).join('');
    }
    static visualSecondary(text) {
        return text.replace(/<[^<>]*>/g,t=>/^(?:<R>|<\/R[^<>]*>|<\/?[Cc][0-9a-fA-F]*>|<\/?B>|<[sS]\d+>|<I\d+>)$/.test(t)?t:'');
    }
    static closeColours(text) {
        let depth=0;for(const t of text.match(/<\/?[Cc][0-9a-fA-F]*>/g)||[])depth=t.startsWith('</')?Math.max(0,depth-1):depth+1;
        return '</C>'.repeat(depth);
    }
    static byteLength(text) {
        let n=0;for(const ch of text) {const c=ch.codePointAt(0);n+=c<128?1:c<2048?2:c<65536?3:4;}return n;
    }
    static annotationPlan(a,b) {
        const left=a.split(/(\r\n|\n|\\n)/);let right=RuntimeText.visualSecondary(b).split(/\r\n|\n|\\n/);
        const count=(left.length+1)/2;
        if(count!==right.length||left.some((v,i)=>!(i%2)&&Boolean(v.trim())!==Boolean(right[i/2]?.trim())))right=[right.join(' '),...Array(count-1).fill('')];
        let text='';const layers=[];
        left.forEach((part,i)=>{
            if(i%2){text+=part;return;}
            const payload=right[i/2];
            if(payload.trim()) {
                layers.push({offset:RuntimeText.byteLength(text)+6,text:payload,protected:a.includes('<R>')||b.includes('<R>')});
                text+='<R></R_>';
            }
            text+=part;
        });
        return {text,layers,kind:'layered'};
    }
    render(source,mode='annotation',key='',scope='') {
        if(this.model.same_language&&mode==='annotation')mode='primary';
        const ck=mode+'\x00'+key+'\x00'+scope+'\x00'+source;
        if(this.planCache.has(ck))return this.planCache.get(ck);
        const a=this.translate(source,'primary',key,scope),b=this.translate(source,'secondary',key,scope);
        let result;
        const known=this.rawPair(source)!==null||
            (Object.hasOwn(this.keyed,key)&&this.keyed[key].source===source);
        const prefix=(a.match(/^(?:<#[^<>]*>)*/)||[''])[0],body=a.slice(prefix.length),visibleB=RuntimeText.visualSecondary(b);
        if(mode==='annotation'&&known&&prefix&&!/[<>]/.test(body+visibleB)&&
                body.split(/\r\n|\n|\\n/).length===visibleB.split(/\r\n|\n|\\n/).length) {
            const value=RuntimeText.ruby(body,visibleB);
            if(value!==null) {
                const text=prefix+value;
                result={text,layers:[],kind:text!==source?'ruby':'plain'};
                if(this.planCache.size>=20000)this.planCache.clear();this.planCache.set(ck,result);return result;
            }
        }
        const left=a.split(/\r\n|\n|\\n/),right=b.split(/\r\n|\n|\\n/);
        const differentLines=left.length!==right.length||left.some((v,i)=>Boolean(v.trim())!==Boolean(right[i]?.trim()));
        if(mode==='annotation'&&((known&&(/[<>]/.test(a+b)||differentLines))||(a!==b&&((a+b).includes('<R>')||differentLines)))&&RuntimeText.visualSecondary(b).trim())
            result=RuntimeText.annotationPlan(a,b);
        else {
            const text=this.translate(source,mode,key,scope);
            result={text,layers:[],kind:mode==='annotation'&&text!==source&&text.includes('<R>')?'ruby':'plain'};
        }
        if(this.planCache.size>=20000)this.planCache.clear();this.planCache.set(ck,result);return result;
    }
    component(source,mode) {
        const pair=this.pair(source);
        if(pair) {
            const [a,b]=pair;
            if(mode==='primary')return a;
            if(mode==='secondary')return b;
            if(mode==='bilingual')return a===b?a:a+'\n'+b;
            const value=RuntimeText.ruby(a,b);if(value!==null)return value;
        }
        const trimmed=source.trim();
        if(trimmed&&trimmed!==source) {
            const inner=this.component(trimmed,mode);
            if(inner!==trimmed) {const at=source.indexOf(trimmed);return source.slice(0,at)+inner+source.slice(at+trimmed.length);}
        }
        const parts=source.split(/([【】「」：:／/]| - |[ \u3000]{2,}|^[ \u3000]*[·・][ \u3000]*)/);
        if(parts.length>1)return parts.map((p,i)=>i%2?p:this.component(p,mode)).join('');
        return source;
    }
    translate(source,mode='annotation',key='',scope='') {
        if(this.model.same_language&&mode==='annotation')mode='primary';
        const ck=mode+'\x00'+key+'\x00'+scope+'\x00'+source;
        if(this.cache.has(ck))return this.cache.get(ck);
        const result=this.resolve(source,mode,key,scope);
        if(this.cache.size>=20000)this.cache.clear();
        this.cache.set(ck,result);return result;
    }
    resolve(source,mode,key,scope) {
        if(source.length>16384)return source;
        const keyed=Object.hasOwn(this.keyed,key)?this.keyed[key]:null;
        if(keyed && keyed.source===source) return keyed.tr.translate(source,mode);
        if(scope&&this.scoped[scope]) {
            const t=this.scoped[scope].translate(source,mode);if(t!==source)return t;
        }
        if(this.details) {
            for(let at=source.indexOf('\n');at>=0;at=source.indexOf('\n',at+1))
                if(this.detailSources.has(source.slice(at+1)))return this.details.translate(source,mode);
        }
        const pair=this.rawPair(source);
        if(pair&&(mode==='primary'||mode==='secondary'))return pair[mode==='primary'?0:1];
        if(mode==='bilingual') {
            const a=this.translate(source,'primary',key,scope),b=this.translate(source,'secondary',key,scope);
            return a===b?a:a+RuntimeText.closeColours(a)+'\n'+RuntimeText.visualSecondary(b);
        }
        if(source.includes('<R>')) {
            const parts=source.split(/(<#[^<>]*>|\r\n|\n|\\n)/);
            return parts.length>1?parts.map((t,i)=>i%2?t:this.translate(t,mode)).join(''):source;
        }
        if(!/[<>]/.test(source)) {const t=this.component(source,mode);if(t!==source)return t;}
        return source.split(/(<[^<>]*>|\r\n|\n|\\n)/).map((t,i)=>i%2?t:this.component(t,mode)).join('');
    }
}
if(typeof module!=='undefined')module.exports={RuntimeText};
