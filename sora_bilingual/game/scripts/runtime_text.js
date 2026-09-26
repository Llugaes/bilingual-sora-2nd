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
        if(!RuntimeText.needsAnnotation(a,b))return a;
        const sameCjk=a===b && /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(a);
        if(a===b&&!sameCjk)return a;
        if(/[<>]/.test(a+b))return null;
        const left=a.replace(/\\n/g,'\n').split(/(\r\n|\n)/),right=b.replace(/\\n/g,'\n').split(/\r\n|\n/);
        if((left.length+1)/2!==right.length || left.some((v,i)=>!(i%2)&&Boolean(v.trim())!==Boolean(right[i/2].trim())))return null;
        return left.map((v,i)=>i%2?v:RuntimeText.needsAnnotation(v,right[i/2])?'<R>'+v+'</R'+right[i/2]+'>':v).join('');
    }
    static needsAnnotation(a,b) {
        const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0)).trim();
        const left=visible(a),right=visible(b);
        return !!left&&!!right&&(left!==right||/[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(left));
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
    static latinWordCharacter(value) {
        return /^[A-Za-z0-9\u00c0-\u024f]$/.test(value);
    }
    static secondaryText(lines) {
        const result=[];
        for(const line of lines) {
            const last=result.at(-1);
            if(last&&line&&RuntimeText.latinWordCharacter(last.at(-1))&&RuntimeText.latinWordCharacter(line[0]))result.push(' ');
            result.push(line);
        }
        return result.join('');
    }
    static secondaryUnits(text) {
        const result=[],characterAt=at=>String.fromCodePoint(text.codePointAt(at));
        for(let at=0;at<text.length;) {
            if(text.startsWith('<R>',at)) {
                const close=text.indexOf('</R',at+3);if(close<0)return null;
                const end=text.indexOf('>',close);if(end<0)return null;
                const value=text.slice(at,end+1),base=text.slice(at+3,close);
                result.push({value,width:Array.from(base).filter(character=>!/^\s$/u.test(character)).length,tag:false});at=end+1;continue;
            }
            if(text[at]==='<') {
                const tag=/^<[^<>]*>/.exec(text.slice(at));
                if(!tag||!/^<\/?[Cc][0-9a-fA-F]*>$|^<\/?B>$|^<[sS]\d+>$|^<I\d+>$/.test(tag[0]))return null;
                result.push({value:tag[0],width:0,tag:true});at+=tag[0].length;continue;
            }
            let end=at+characterAt(at).length;
            if(RuntimeText.latinWordCharacter(characterAt(at))) {
                while(end<text.length&&RuntimeText.latinWordCharacter(characterAt(end)))end+=characterAt(end).length;
                while(end<text.length&&"'’‐-".includes(characterAt(end))&&end+characterAt(end).length<text.length&&RuntimeText.latinWordCharacter(characterAt(end+characterAt(end).length))) {
                    end+=characterAt(end).length;while(end<text.length&&RuntimeText.latinWordCharacter(characterAt(end)))end+=characterAt(end).length;
                }
            }
            const value=text.slice(at,end);result.push({value,width:Array.from(value).filter(character=>!/^\s$/u.test(character)).length,tag:false});at=end;
        }
        return result;
    }
    static reflowSecondaryParagraph(text,capacities) {
        const units=RuntimeText.secondaryUnits(text);if(units===null)return null;
        const result=[],state={colours:[],bold:false,size:''};
        const update=tag=>{
            if(/^<[Cc][0-9a-fA-F]*>$/.test(tag))state.colours.push(tag);
            else if(tag==='</C>'){if(state.colours.length)state.colours.pop();}
            else if(tag==='<B>')state.bold=true;
            else if(tag==='</B>')state.bold=false;
            else if(/^<[sS]\d+>$/.test(tag))state.size=tag;
        };
        const prefix=()=>state.colours.join('')+(state.bold?'<B>':'')+state.size;
        const close=()=>(state.bold?'</B>':'')+'</C>'.repeat(state.colours.length);
        const startsPunctuation=()=>{
            for(const unit of units)if(unit.width)return '、。！？）】》〉」』〕］｝'.includes(Array.from(unit.value.replace(/<[^<>]*>/g,''))[0]);
            return false;
        };
        const take=line=>{const unit=units.shift();line.push(unit.value);if(unit.tag)update(unit.value);return unit.width;};
        for(let number=0;number<capacities.length;number++) {
            if(number===capacities.length-1){const line=[prefix()];while(units.length)take(line);result.push(line.join('')+close());break;}
            while(result.length&&units.length&&units[0].width&&/^\s$/u.test(units[0].value))result[result.length-1]+=units.shift().value;
            const line=[prefix()];let used=0;
            const remainingCapacity=capacities.slice(number).reduce((sum,value)=>sum+value,0);
            const remainingText=units.reduce((sum,unit)=>sum+unit.width,0);
            const target=Math.max(1,Math.ceil(remainingText*capacities[number]/remainingCapacity));
            while(units.length&&(!line.length||used<target))used+=take(line);
            while(units.length&&units[0].tag&&['</C>','</B>'].includes(units[0].value))take(line);
            while(units.length&&startsPunctuation())used+=take(line);
            result.push(line.join('')+close());
        }
        return result;
    }
    static reflowAnnotationLines(primary,secondary) {
        const left=primary.split(/\r\n|\n|\\n/),right=secondary.split(/\r\n|\n|\\n/),result=Array(left.length).fill('');
        const paragraphs=lines=>{
            const groups=[],current=[];
            lines.forEach((line,index)=>{
                if(line.trim()) {
                    if(current.length&&/^\s/u.test(line))groups.push(current.splice(0));
                    current.push([index,line]);
                } else if(current.length) groups.push(current.splice(0));
            });
            if(current.length)groups.push(current);return groups;
        };
        const leftGroups=paragraphs(left),rightGroups=paragraphs(right);
        if(!leftGroups.length)return result;
        const groups=leftGroups.length===rightGroups.length
            ?leftGroups.map((group,index)=>[group,rightGroups[index]])
            :[[[].concat(...leftGroups),[].concat(...rightGroups)]];
        for(const [leftGroup,rightGroup] of groups) {
            const text=RuntimeText.secondaryText(rightGroup.map(([,line])=>line));
            const capacities=leftGroup.map(([,line])=>Math.max(1,Array.from(line.replace(/<[^<>]*>/g,'')).filter(char=>!/\s/u.test(char)).length));
            const reflowed=RuntimeText.reflowSecondaryParagraph(text,capacities);if(reflowed===null)return null;
            reflowed.forEach((value,index)=>{result[leftGroup[index][0]]=value;});
        }
        return result;
    }
    static annotationPlan(a,b) {
        const left=a.split(/(\r\n|\n|\\n)/),visible=RuntimeText.visualSecondary(b);let right=visible.split(/\r\n|\n|\\n/);
        const count=(left.length+1)/2;
        const needsReflow=count!==right.length||left.some((v,i)=>!(i%2)&&Boolean(v.trim())!==Boolean(right[i/2]?.trim()));
        if(needsReflow||visible.includes('<')) {
            const reflowed=RuntimeText.reflowAnnotationLines(a,visible);
            if(reflowed!==null)right=reflowed;
            else if(needsReflow) {
                const payload=right.join(' '),anchor=left.findIndex((v,i)=>!(i%2)&&v.trim());
                right=Array(count).fill('');right[Math.max(0,anchor/2)]=payload;
            }
        }
        let text='';const layers=[];
        left.forEach((part,i)=>{
            if(i%2){text+=part;return;}
            const payload=right[i/2];
            if(RuntimeText.needsAnnotation(part,payload)) {
                layers.push({offset:RuntimeText.byteLength(text)+6,text:payload,primary:part,protected:a.includes('<R>')||b.includes('<R>')});
                text+='<R></R_>';
            }
            text+=part;
        });
        return {text,layers,kind:'layered'};
    }
    render(source,mode='annotation',key='',scope='') {
        // Older resident adapters request bilingual for cutscene labels.
        // Keep that wire value compatible, but use annotations everywhere.
        if(mode==='bilingual')mode='annotation';
        if(this.model.same_language&&mode==='annotation')mode='primary';
        const ck=mode+'\x00'+key+'\x00'+scope+'\x00'+source;
        if(this.planCache.has(ck))return this.planCache.get(ck);
        const a=this.translate(source,'primary',key,scope),b=this.translate(source,'secondary',key,scope);
        if(mode==='annotation'&&!RuntimeText.needsAnnotation(a,b)) {
            const result={text:a,layers:[],kind:'plain'};
            if(this.planCache.size>=20000)this.planCache.clear();this.planCache.set(ck,result);return result;
        }
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
            const value=RuntimeText.ruby(a,b);if(value!==null)return value;
        }
        const trimmed=source.trim();
        if(trimmed&&trimmed!==source) {
            const inner=this.component(trimmed,mode);
            if(inner!==trimmed) {const at=source.indexOf(trimmed);return source.slice(0,at)+inner+source.slice(at+trimmed.length);}
        }
        const parts=source.split(/(\r\n|\n|\\n|[【】「」：:／/]| - |[ \u3000]{2,}|^[ \u3000]*[·・][ \u3000]*)/);
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
        if(mode==='bilingual')mode='annotation';
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
        if(source.includes('<R>')) {
            const parts=source.split(/(<#[^<>]*>|\r\n|\n|\\n)/);
            return parts.length>1?parts.map((t,i)=>i%2?t:this.translate(t,mode)).join(''):source;
        }
        if(!/[<>]/.test(source)) {const t=this.component(source,mode);if(t!==source)return t;}
        return source.split(/(<[^<>]*>|\r\n|\n|\\n)/).map((t,i)=>i%2?t:this.component(t,mode)).join('');
    }
}
if(typeof module!=='undefined')module.exports={RuntimeText};
