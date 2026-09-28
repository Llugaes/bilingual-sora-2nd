'use strict';
// Pure SHA-256 for the injected runtime (which has no Node crypto module).
// Re-hash the live blob on each dialogue call: allocator address reuse must
// never make a new script inherit an old script's localisation identity.
function scriptSha256(input) {
    const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const bytes=input instanceof Uint8Array?input:new Uint8Array(input);
    const data=new Uint8Array(Math.ceil((bytes.length+9)/64)*64);data.set(bytes);data[bytes.length]=128;
    const view=new DataView(data.buffer);view.setUint32(data.length-8,Math.floor(bytes.length/0x20000000));
    view.setUint32(data.length-4,bytes.length*8);
    const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const w=new Uint32Array(64),ror=(x,n)=>(x>>>n)|(x<<(32-n));
    for(let at=0;at<data.length;at+=64) {
        for(let i=0;i<16;i++)w[i]=view.getUint32(at+i*4);
        for(let i=16;i<64;i++) {
            const a=w[i-15],b=w[i-2];
            w[i]=w[i-16]+(ror(a,7)^ror(a,18)^(a>>>3))+w[i-7]+(ror(b,17)^ror(b,19)^(b>>>10));
        }
        let [a,b,c,d,e,f,g,z]=h;
        for(let i=0;i<64;i++) {
            const t1=(z+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+k[i]+w[i])|0;
            const t2=((ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c)))|0;
            z=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;
        }
        [a,b,c,d,e,f,g,z].forEach((v,i)=>h[i]=(h[i]+v)>>>0);
    }
    return h.map(v=>v.toString(16).padStart(8,'0')).join('');
}
const expressionPrefix=value=>(value.match(/^(?:<#[^<>]*>)*/)||[''])[0];
const expressionBody=value=>value.slice(expressionPrefix(value).length);

class ScriptIdentities {
    constructor(model,hash=scriptSha256) {
        this.hash=hash;
        this.scripts=model?.scripts||{};this.manifest=model?.manifest||{};this.cache=new Map();
        this.sourceLanguage=model?.source_language||null;
        this.recordPairs=model?.record_pairs||{};this.recordPairValues=model?.record_pair_values||[];
        this.historyMarkers=model?.history_markers||{};
        this.historySpeakerSetters=model?.history_speaker_setters||{};
        this.dynamicProducers=model?.dynamic_producers||{scripts:{},records:{}};
        this.producerPatterns=new Map();
        this.callPatterns=new WeakMap();
        this.pointers=model?.pointers||{};this.pointerModels=model?.pointer_models||{};this.pointerCache=new Map();
    }
    pointerLookup(key,source) {
        const item=Object.hasOwn(this.pointerModels,key)?this.pointerModels[key]:null;
        if(!item||item.source!==source)return null;
        if(!this.pointerCache.has(key))this.pointerCache.set(key,{key,model:item.model});
        return this.pointerCache.get(key);
    }
    pointerSelect(pointer,source) {
        if(!Object.hasOwn(this.pointers,source))return null;
        const verified=new Map();let result=null,pair=null;
        for(const c of this.pointers[source]) {
            try {
                if(c.size>16*1024*1024||c.offset>=c.size)continue;
                const base=pointer.add(-c.offset),token=String(base)+'/'+c.sha256;
                if(!verified.has(token)) {
                    const header=Array.from(new Uint8Array(base.readByteArray(24))).map(v=>v.toString(16).padStart(2,'0')).join('');
                    verified.set(token,header===c.header&&(this.hash.pointer?this.hash.pointer(base,c.size):this.hash(base.readByteArray(c.size)))===c.sha256);
                }
                if(!verified.get(token))continue;
                const current=this.pointerLookup(c.key,source);if(!current)continue;
                const expected=JSON.stringify(current.model.pairs[source]);
                if(result&&expected!==pair)return null;
                result=current;pair=expected;
            }catch(e){/* Heap copies and unrelated resources have no script identity. */}
        }
        return result;
    }
    historyMarkerIdentity(marker,speaker,source) {
        if(!Number.isInteger(marker)||marker<0||marker>0xffffffff||marker===0||marker===0xffff||typeof speaker!=='string'||typeof source!=='string')return null;
        const rows=this.historyMarkers[String(marker)];
        if(!Array.isArray(rows))return null;
        const byKey=new Map();
        for(const row of rows) {
            if(!Array.isArray(row)||row.length!==5)continue;
            const [locale,expected,expectedSpeaker,key,called]=row;
            if(typeof locale!=='string'||typeof expected!=='string'||
                    expectedSpeaker!==null&&typeof expectedSpeaker!=='string'||
                    typeof key!=='string'||!Number.isInteger(called)||called<0||
                    expressionBody(expected)!==expressionBody(source)||
                    expectedSpeaker!==null&&expectedSpeaker!==speaker)continue;
            if(!byKey.has(key))byKey.set(key,[]);
            byKey.get(key).push({locale,called});
        }
        if(byKey.size!==1)return null;
        const [recordKey,matches]=byKey.entries().next().value;
        const canonical=/\/called\/(\d+)\/assembled_dialogue$/.exec(recordKey);
        if(!canonical)return null;
        const sourceCallIds={},sourceLocales=[];
        for(const match of matches) {
            if(Object.hasOwn(sourceCallIds,match.locale)&&sourceCallIds[match.locale]!==match.called)return null;
            if(!Object.hasOwn(sourceCallIds,match.locale))sourceLocales.push(match.locale);
            sourceCallIds[match.locale]=match.called;
        }
        sourceLocales.sort();
        if(!sourceLocales.length)return null;
        const identity={
            callId:Number(canonical[1]),recordKey,source,sourceLocales,sourceCallIds,historyMarker:marker,
        };
        if(sourceLocales.length===1)identity.sourceLocale=sourceLocales[0];
        return identity;
    }
    historySpeakerLookup(identity,name) {
        if(!identity?.recordKey||typeof name!=='string')return null;
        const rows=this.historySpeakerSetters[identity.recordKey];
        if(!Array.isArray(rows))return null;
        const candidates=new Map();
        for(const row of rows) {
            if(!Array.isArray(row)||row.length!==4||row.some(value=>typeof value!=='string'))continue;
            const [locale,expected,...pair]=row;
            if(name!==expected||identity.sourceLocale&&identity.sourceLocale!==locale||
                    identity.sourceLocales&&!identity.sourceLocales.includes(locale))continue;
            candidates.set(JSON.stringify(pair),pair);
        }
        if(candidates.size!==1)return null;
        const pair=candidates.values().next().value;
        const key='speaker/'+identity.recordKey+'/'+name;
        if(!this.cache.has(key)) {
            if(this.cache.size>=1024)this.cache.clear();
            const pairs={[name]:pair};
            this.cache.set(key,{model:{pairs,plain_pairs:pairs},strict:true});
        }
        return this.cache.get(key);
    }
    recordLookup(identity,key,source) {
        if(typeof identity.source!=='string'||source!==identity.source||
                !Object.hasOwn(this.recordPairs,key))return null;
        const index=this.recordPairs[key],pair=this.recordPairValues[index];
        if(!Number.isInteger(index)||!Array.isArray(pair)||pair.length!==2||
                pair.some(value=>typeof value!=='string'))return null;
        const id='record/'+key+'/'+identity.source;
        if(!this.cache.has(id)) {
            if(this.cache.size>=1024)this.cache.clear();
            const prefix=expressionPrefix(identity.source),body=expressionBody(identity.source);
            const bodyPair=pair.map(expressionBody),fullPair=bodyPair.map(value=>prefix+value);
            const pairs={[identity.source]:fullPair};
            if(body!==identity.source)pairs[body]=bodyPair;
            this.cache.set(id,{identity,model:{pairs,plain_pairs:pairs,numeric:[]}});
        }
        return this.cache.get(id);
    }
    producerSourceMatches(pattern,source) {
        if(typeof pattern!=='string'||typeof source!=='string')return false;
        if(!this.producerPatterns.has(pattern))this.producerPatterns.set(pattern,new RegExp('^(?:'+pattern+')$'));
        const match=this.producerPatterns.get(pattern).exec(source);
        return !!match&&match[0]===source&&match.slice(1).every(value=>Number.isInteger(Number(value))&&Number(value)>=-2147483648&&Number(value)<=2147483647);
    }
    producerLookup(identity,source) {
        const model=this.dynamicProducers.records?.[identity.recordKey]?.[identity.sourceLocale];
        if(!model||!Array.isArray(model.producer_numeric)||model.producer_numeric.length!==1||
                !this.producerSourceMatches(model.producer_numeric[0][0],source))return null;
        const key='producer/'+identity.recordKey+'/'+identity.sourceLocale;
        if(!this.cache.has(key)) {
            if(this.cache.size>=1024)this.cache.clear();
            this.cache.set(key,{model,strict:true});
        }
        return this.cache.get(key);
    }
    lookup(identity,source=identity?.source) {
        if(Object.hasOwn(identity,'source')&&source!==identity.source)return null;
        if(identity.producer)return this.producerLookup(identity,source);
        const {signature,sha256,functionName,argumentsToken}=identity;
        const scripts=Object.hasOwn(this.scripts,signature)?this.scripts[signature]:[];
        const script=scripts.find(v=>v.sha256===sha256);
        const fn=script&&Object.hasOwn(script.functions,functionName)?script.functions[functionName]:null;
        if(Object.hasOwn(identity,'callId')) {
            if(!Number.isInteger(identity.callId)||identity.callId<0)return null;
            const record=fn&&Object.hasOwn(fn.records||{},identity.callId)?fn.records[identity.callId]:null;
            if(record?.model) {
                const id=sha256+'/'+functionName+'/called/'+identity.callId;
                if(!this.cache.has(id)) {
                    if(this.cache.size>=1024)this.cache.clear();
                    this.cache.set(id,{identity,model:record.model});
                }
                return this.cache.get(id);
            }
            const key=record?.key||identity.recordKey;
            if(!key||identity.recordKey&&identity.recordKey!==key)return null;
            return this.recordLookup(identity,key,source);
        }
        if(!fn)return null;
        let call=Object.hasOwn(fn.calls,argumentsToken)?fn.calls[argumentsToken]:null;
        if(!call) {
            const actual=argumentsToken.split(','),matches=Object.entries(fn.calls).filter(([token])=>{
                if(!token.includes('?'))return false;
                const expected=token.split(',');
                return expected.length===actual.length&&expected.every((v,i)=>v==='?'||v===actual[i]);
            });
            if(matches.length===1)call=matches[0][1];
        }
        const id=sha256+'/'+functionName+'/'+(call?argumentsToken:'function');
        if(!this.cache.has(id)) {
            if(this.cache.size>=1024)this.cache.clear();
            this.cache.set(id,{identity,model:call?.model||fn.model});
        }
        return this.cache.get(id);
    }
    capturedIdentity(candidate,identity,functionName,source) {
        if(source!==null&&source!==undefined) {
            if(typeof source!=='string')return null;
            identity.source=source;
            if(this.sourceLanguage)identity.sourceLocale=this.sourceLanguage;
        }
        if(!Object.hasOwn(identity,'callId'))return identity;
        const record=candidate.recordKeys?.[functionName]?.[identity.callId];
        if(!record)return identity;
        if(typeof source!=='string'||typeof record.source!=='string'||
                expressionBody(record.source)!==expressionBody(source)||typeof record.key!=='string')return null;
        identity.recordKey=record.key;
        return identity;
    }
    captureCandidates(signature) {
        const manifest=Object.hasOwn(this.manifest,signature)?this.manifest[signature]:null;
        if(Array.isArray(manifest)&&manifest.length)return manifest;
        const scripts=Object.hasOwn(this.scripts,signature)?this.scripts[signature]:[];
        return scripts.map(script=>({
            size:script.size,sha256:script.sha256,
            functions:Array.isArray(script.functions)?script.functions:Object.keys(script.functions||{}),
        }));
    }
    canCapture(signature) {return this.captureCandidates(signature).length>0;}
    capture(signature,readBlob,functionName,argumentsToken,site=null,source=null) {
        if(typeof functionName!=='string'||!functionName||typeof argumentsToken!=='string')return null;
        const hashes=new Map();
        for(const candidate of this.captureCandidates(signature)) {
            if(!Array.isArray(candidate.functions)||!candidate.functions.includes(functionName))continue;
            if(!Number.isInteger(candidate.size)||candidate.size<24||candidate.size>16*1024*1024||
                typeof candidate.sha256!=='string'||!/^[0-9a-f]{64}$/.test(candidate.sha256))continue;
            try {
                if(!hashes.has(candidate.size)) {
                    const blob=readBlob(candidate.size);
                    if(blob&&typeof blob==='object'&&Object.hasOwn(blob,'pointer')) {
                        hashes.set(candidate.size,blob.byteLength===candidate.size&&typeof this.hash.pointer==='function'?
                            this.hash.pointer(blob.pointer,candidate.size):null);
                    } else {
                        const bytes=blob instanceof Uint8Array?blob:new Uint8Array(blob);
                        hashes.set(candidate.size,bytes.byteLength===candidate.size?this.hash(bytes):null);
                    }
                }
                if(hashes.get(candidate.size)!==candidate.sha256)continue;
                const identity={signature,sha256:candidate.sha256,functionName,argumentsToken};
                const producer=this.dynamicProducers.scripts?.[candidate.sha256]?.[functionName]?.[argumentsToken];
                if(producer&&site?.group===5&&site.command===8) {
                    if(!Number.isInteger(site.pc)||site.pc<4||site.pc>candidate.size||site.pc!==producer.pc||
                            !Number.isInteger(producer.callId)||producer.callId<0||
                            typeof producer.recordKey!=='string'||
                            !this.producerSourceMatches(producer.sourcePattern,source))return null;
                    return {...identity,producer:true,callId:producer.callId,recordKey:producer.recordKey,
                        source,sourceLocale:this.sourceLanguage,pc:site.pc};
                }
                if(Object.hasOwn(candidate,'callRecords')) {
                    if(!site||!Number.isInteger(site.pc)||site.pc<4||site.pc>candidate.size)return null;
                    const index=candidate.callRecords[functionName]||{};
                    const prefix=site.group+':'+site.command+':',token=prefix+argumentsToken;
                    let matches=Object.hasOwn(index,token)?index[token]:[];
                    if(!this.callPatterns.has(index))this.callPatterns.set(index,Object.entries(index).filter(([key])=>key.includes('?')));
                    for(const [pattern,records] of this.callPatterns.get(index)) {
                        if(!pattern.startsWith(prefix))continue;
                        const expected=pattern.slice(prefix.length).split(','),actual=argumentsToken.split(',');
                        if(expected.length===actual.length&&expected.every((v,i)=>v==='?'||v===actual[i]))matches=matches.concat(records);
                    }
                    if(!matches.length)return this.capturedIdentity(candidate,identity,functionName,source); // Dynamic producers retain their own parameter contracts.
                    if(matches.length>1) {
                        const call=candidate.callSites?.[functionName]?.[site.pc];
                        matches=call&&call.group===site.group&&call.command===site.command&&matches.includes(call.record)?[call.record]:[];
                    }
                    if(matches.length!==1)return null;
                    identity.callId=matches[0];identity.pc=site.pc;
                    return this.capturedIdentity(candidate,identity,functionName,source);
                }
                if(Object.hasOwn(candidate,'callSites')) {
                    const sites=candidate.callSites[functionName];
                    if(!site||!Number.isInteger(site.pc)||!sites||!Object.hasOwn(sites,site.pc))return null;
                    const call=sites[site.pc],actual=argumentsToken.split(','),expected=call.token.split(',');
                    if(call.group!==site.group||call.command!==site.command||expected.length!==actual.length||
                            !expected.every((value,i)=>value==='?'||value===actual[i]))return null;
                    identity.callId=call.record;identity.pc=site.pc;
                }
                return this.capturedIdentity(candidate,identity,functionName,source);
            }catch(e){/* An unrelated or unreadable heap buffer has no provenance. */}
        }
        return null;
    }
    select(signature,readBlob,functionName,argumentsToken) {
        const candidates=Object.hasOwn(this.scripts,signature)?this.scripts[signature]:[];
        const hashes=new Map();
        for(const script of candidates) {
            if(!Object.hasOwn(script.functions,functionName))continue;
            if(!Number.isInteger(script.size)||script.size<24||script.size>16*1024*1024)continue;
            if(!hashes.has(script.size))hashes.set(script.size,this.hash(readBlob(script.size)));
            if(hashes.get(script.size)!==script.sha256)continue;
            const identity={signature,sha256:script.sha256,functionName,argumentsToken};
            // Function fallback shares a resolver, not an invocation's args.
            // A later language reload may index a previously unneeded call.
            const selected=this.lookup(identity);
            return selected?{...selected,identity}:null;
        }
        return null;
    }
}
class TableIdentities {
    constructor(model,hash=scriptSha256) {this.hash=hash;this.model=model||{sources:{},models:{},files:{}};this.cache=new Map();}
    lookup(key,source) {
        const row=Object.hasOwn(this.model.models,key)?this.model.models[key]:null;
        if(!row||row.source!==source)return null;
        if(!this.cache.has(key))this.cache.set(key,{key,model:row.model});
        return this.cache.get(key);
    }
    select(pointer,source) {
        if(!Object.hasOwn(this.model.sources,source))return null;
        const verified=new Map();let found=null,pair=null;
        const hex=data=>Array.from(new Uint8Array(data)).map(v=>v.toString(16).padStart(2,'0')).join('');
        for(const candidate of this.model.sources[source]) {
            try {
                const file=this.model.files[candidate.file];
                if(!file||file.size>32*1024*1024||file.floor>file.size||candidate.offset>=file.size)continue;
                const base=pointer.add(-candidate.offset),token=String(base)+'/'+candidate.file;
                if(!verified.has(token)) {
                    const header=base.readByteArray(file.header.length/2);
                    verified.set(token,hex(header)===file.header &&
                        (this.hash.pointer?this.hash.pointer(base.add(file.floor),file.size-file.floor):this.hash(base.add(file.floor).readByteArray(file.size-file.floor)))===file.pool_sha256);
                }
                if(!verified.get(token))continue;
                const record=base.add(candidate.record_at);
                if(!record.add(candidate.field_at).readPointer().equals(pointer))continue;
                const bytes=new Uint8Array(record.readByteArray(candidate.record.length/2));
                for(const off of candidate.pointers)bytes.fill(0,off,off+8);
                if(hex(bytes)!==candidate.record)continue;
                const current=this.lookup(candidate.key,source);
                if(!current)continue;
                const value=JSON.stringify(current.model.pairs[source]);
                if(found&&value!==pair)return null; // shared pool pointer, distinct translations
                found=current;pair=value;
            }catch(e){/* An ordinary heap copy is not a table pointer. */}
        }
        return found;
    }
}
// The native history owns a 1600-slot ring. Its copied strings no longer
// identify a script call: keep the observed writer's provenance by slot and
// validate the entire current record before using it. This is not a text cache.
class LogIdentities {
    constructor(){this.owner=null;this.generation=0;this.epoch=0;this.entries=new Map();}
    reset(owner=this.owner){this.owner=owner;this.entries.clear();this.generation++;this.epoch++;}
    useOwner(owner){if(owner!==this.owner)this.reset(owner);}
    commit(slot,stamp,origin){
        if(!Number.isInteger(slot)||slot<0||slot>=1600)throw Error('Invalid history slot');
        this.generation++;
        this.entries.delete(slot);
        if(origin)this.entries.set(slot,{stamp,origin,generation:this.generation});
    }
    lookup(slot,stamp){
        const item=this.entries.get(slot);
        if(!item)return null;
        if(item.stamp!==stamp){this.entries.delete(slot);return null;}
        return item.origin;
    }
}
if(typeof module!=='undefined')module.exports={scriptSha256,ScriptIdentities,TableIdentities,LogIdentities};
