'use strict';
// Shared pure resolver: runs synchronously inside the native label callback.
// No RPC, timers, pointers, filesystem access, or fuzzy substring matching.
const PRINTF_TOKEN=/%%|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[dius]/g;
class RuntimeText {
    constructor(model) {
        this.model = model;
        const detailRows=model.detail_numeric||[],shadowed=new Set(detailRows.map(([pattern])=>pattern));
        this.numeric = (model.numeric || []).filter(([pattern])=>!shadowed.has(pattern)).map(([pattern, pair]) => [new RegExp('^(?:'+pattern+')$'), pair]);
        this.rawNumeric = (model.raw_numeric || []).map(([pattern,pair])=>[new RegExp('^(?:'+pattern+')$'),pair]);
        this.producerNumeric = (model.producer_numeric || []).map(([pattern,pair,styles])=>[new RegExp('^(?:'+pattern+')$'),pair,styles]);
        this.producerLines = (model.producer_lines || []).map(([pattern,pair,styles])=>[new RegExp('^(?:'+pattern+')$'),pair,styles]);
        this.producerLineCache = new Map();
        this.detailNumeric = detailRows.map(([pattern,pair])=>[new RegExp('^(?:'+pattern+')$'),pair]);
        const inlineRows=model.detail_inline_icons||[];
        this.detailInlineIcons=inlineRows.map(([pattern,pair])=>[new RegExp(pattern,'g'),pair]);
        this.detailContexts=model.detail_contexts||{};
        this.numericIndex=RuntimeText.numericIndex(this.numeric,model.numeric||[],shadowed);
        this.detailNumericIndex=RuntimeText.numericIndex(this.detailNumeric,detailRows);
        this.detailInlineIconIndex=RuntimeText.numericIndex(this.detailInlineIcons,inlineRows);
        this.numericCandidateCache=new Map();this.detailNumericCandidateCache=new Map();this.detailInlineIconCandidateCache=new Map();
        this.scoped = Object.fromEntries(Object.entries(model.scoped || {}).map(([k,v])=>[k,new RuntimeText(v)]));
        this.details = model.details ? new RuntimeText(model.details) : null;
        this.detailSources = new Set(model.detail_sources || []);
        this.ambiguousDisplay = new Set(model.ambiguous_display || []);
        this.cache = new Map();
        this.planCache = new Map();
        this.speakerCache = new Map();
        this.historyCache = new Map();
        this.keyed = Object.fromEntries(Object.entries(model.keyed || {}).map(([k,v])=>[k,{source:v.source,tr:new RuntimeText(v.model)}]));
    }
    static numericLiteral(pattern) {
        const captures=['([+-]?\\d+)','([^<>\\r\\n]{1,512}?)'],runs=[];let run='';
        for(let at=0;at<pattern.length;) {
            const capture=captures.find(value=>pattern.startsWith(value,at));
            if(capture){if(run)runs.push(run);run='';at+=capture.length;continue;}
            const value=pattern[at++];
            if(value==='\\') {
                if(at>=pattern.length)return null;
                const escaped=pattern[at++];
                if(/[A-Za-z0-9]/.test(escaped))return null;
                run+=escaped;continue;
            }
            if('^$.*+?()[]{}|'.includes(value))return null;
            run+=value;
        }
        if(run)runs.push(run);
        return runs.sort((a,b)=>b.length-a.length||a.localeCompare(b))[0]||null;
    }
    static numericIndex(compiled,rows,excluded=new Set()) {
        const fallback=[],byFirst=new Map();let at=0;
        for(const row of rows) {
            if(excluded.has(row[0]))continue;
            const rule=compiled[at++],literal=RuntimeText.numericLiteral(row[0]),entry={at:at-1,rule};
            if(!literal){fallback.push(entry);continue;}
            const first=Array.from(literal)[0];
            if(!byFirst.has(first))byFirst.set(first,new Map());
            const bucket=byFirst.get(first);
            if(!bucket.has(literal))bucket.set(literal,[]);
            bucket.get(literal).push(entry);
        }
        return {fallback,byFirst};
    }
    static numericCandidates(source,index,cache) {
        if(cache.has(source))return cache.get(source);
        const selected=index.fallback.slice();
        for(const first of new Set(Array.from(source))) {
            const bucket=index.byFirst.get(first);if(!bucket)continue;
            for(const [literal,entries] of bucket)if(source.includes(literal))selected.push(...entries);
        }
        selected.sort((a,b)=>a.at-b.at);const result=selected.map(entry=>entry.rule);
        if(cache.size>=20000)cache.clear();cache.set(source,result);return result;
    }
    static renderFormat(template,replacement) {
        return template.replace(PRINTF_TOKEN,token=>token==='%%'?'%':replacement());
    }
    speakerContext(name,source) {
        const models=this.model.speaker_contexts||{};
        if(!Object.hasOwn(models,name))return null;
        const selected=models[name],body=source.replace(/^(?:<#[^<>]*>)+/,'');
        if(!Object.hasOwn(selected.pairs,source)&&!Object.hasOwn(selected.pairs,body))return null;
        if(!this.speakerCache.has(name))this.speakerCache.set(name,{tr:new RuntimeText(selected)});
        return this.speakerCache.get(name);
    }
    historyContext(name,source,kind='body') {
        const model=this.model.history_contexts;if(!model)return null;
        const body=kind==='name'?source:source.replace(/^(?:<#[^<>]*>)+/,'');
        const shared=kind==='name'?model.names:model.texts;
        if(!shared||!Object.hasOwn(shared,body))return null;
        let index=shared[body];
        const narrowed=kind==='body'&&Object.hasOwn(model.speakers||{},name)?model.speakers[name]:null;
        if(index<0&&narrowed&&Object.hasOwn(narrowed,body))index=narrowed[body];
        const key=JSON.stringify([kind,body,index]);
        if(!this.historyCache.has(key)) {
            const pair=Number.isInteger(index)&&index>=0?model.pairs[index]:null;
            const local=pair?{pairs:{[body]:pair},plain_pairs:{[body]:pair},same_language:model.same_language}:
                {pairs:{},plain_pairs:{},ambiguous_display:[body]};
            if(this.historyCache.size>=2048)this.historyCache.clear();
            this.historyCache.set(key,{tr:new RuntimeText(local),strict:true});
        }
        return this.historyCache.get(key);
    }
    pair(source) {
        const producer=this.producerPair(source);if(producer)return producer;
        if (Object.hasOwn(this.model.plain_pairs,source)) return this.model.plain_pairs[source];
        let authoritative=null;
        for(const [pattern,pair] of RuntimeText.numericCandidates(source,this.detailNumericIndex,this.detailNumericCandidateCache)) {
            const m=pattern.exec(source);if(!m||m[0]!==source)continue;
            const rendered=pair.map(target=>{let i=1;return RuntimeText.renderFormat(target,()=>m[i++]);});
            if(authoritative&&JSON.stringify(authoritative)!==JSON.stringify(rendered))return null;
            authoritative=rendered;
        }
        if(authoritative)return authoritative;
        let found=null;
        for(const [pattern,pair] of RuntimeText.numericCandidates(source,this.numericIndex,this.numericCandidateCache)) {
            const m=pattern.exec(source);
            if(!m || m[0]!==source)continue;
            const rendered=pair.map((target,side)=>{
                let i=1;
                return RuntimeText.renderFormat(target,()=>{
                    const v=m[i++];return (Object.hasOwn(this.model.plain_pairs,v)?this.model.plain_pairs[v]:[v,v])[side];
                });
            });
            if(found && JSON.stringify(found)!==JSON.stringify(rendered))return null;
            found=rendered;
        }
        return found;
    }
    static rubyRanges(source) {
        if(!source.includes('<R')&&!source.includes('</R'))return [];
        const ranges=[];let at=0;
        while(at<source.length) {
            const opening=source.indexOf('<R>',at),closing=source.indexOf('</R',at);
            if(closing>=0&&(opening<0||closing<opening))return null;
            if(opening<0)return source.includes('<R',at)?null:ranges;
            const closeStart=source.indexOf('</R',opening+3);
            if(closeStart<0)return null;
            const nested=source.indexOf('<R',opening+3);
            if(nested>=0&&nested<closeStart)return null;
            const closeEnd=source.indexOf('>',closeStart+3);
            if(closeEnd<0)return null;
            ranges.push([opening,closeEnd+1]);at=closeEnd+1;
        }
        return ranges;
    }
    static overlaps(span,ranges) {return ranges.some(([start,end])=>span[0]<end&&start<span[1]);}
    hasDetailContext(source,description) {
        const values=this.detailContexts[description]||{},ranges=RuntimeText.rubyRanges(source);
        if(ranges===null)return false;
        return Object.keys(values).some(span=>{
            let at=source.indexOf(span);while(at>=0) {if(!RuntimeText.overlaps([at,at+span.length],ranges))return true;at=source.indexOf(span,at+span.length);}return false;
        });
    }
    replaceDetailContext(source,mode,description) {
        const values=this.detailContexts[description]||{},ranges=RuntimeText.rubyRanges(source);
        if(ranges===null)return source;
        const selected=[];
        for(const [span,pair] of Object.entries(values)) {
            const target=pair[mode==='secondary'?1:0];
            for(let at=source.indexOf(span);at>=0;at=source.indexOf(span,at+span.length))
                if(!RuntimeText.overlaps([at,at+span.length],ranges))selected.push({start:at,end:at+span.length,target});
        }
        selected.sort((a,b)=>a.start-b.start||a.end-b.end);
        if(selected.some((row,index)=>index&&selected[index-1].end>row.start))return source;
        for(let at=selected.length-1;at>=0;at--) {const row=selected[at];source=source.slice(0,row.start)+row.target+source.slice(row.end);}
        return source;
    }
    hasDetailInlineIcon(source) {
        const ranges=RuntimeText.rubyRanges(source);if(ranges===null)return false;
        for(const [pattern] of RuntimeText.numericCandidates(source,this.detailInlineIconIndex,this.detailInlineIconCandidateCache)) {
            pattern.lastIndex=0;
            for(let match;(match=pattern.exec(source));) {
                if(!RuntimeText.overlaps([match.index,match.index+match[0].length],ranges))return true;
                if(!match[0].length)break;
            }
        }
        return false;
    }
    replaceDetailInlineIcons(source,mode) {
        const ranges=RuntimeText.rubyRanges(source);if(ranges===null)return source;
        const matches=new Map();
        for(const [pattern,pair] of RuntimeText.numericCandidates(source,this.detailInlineIconIndex,this.detailInlineIconCandidateCache)) {
            pattern.lastIndex=0;
            for(let match;(match=pattern.exec(source));) {
                const target=pair[mode==='secondary'?1:0];let at=1;
                const rendered=RuntimeText.renderFormat(target,()=>match[at++]);
                const key=match.index+'\x00'+(match.index+match[0].length);
                if(!matches.has(key))matches.set(key,{start:match.index,end:match.index+match[0].length,values:new Set()});
                matches.get(key).values.add(rendered);
                if(!match[0].length)break;
            }
        }
        const conflicting=[...matches.values()].filter(row=>row.values.size!==1);
        const selected=[...matches.values()].filter(row=>row.values.size===1&&
            !conflicting.some(other=>row.start<other.end&&other.start<row.end)&&
            !RuntimeText.overlaps([row.start,row.end],ranges)).sort((a,b)=>a.start-b.start||a.end-b.end);
        if(selected.some((row,index)=>index&&selected[index-1].end>row.start))return source;
        for(let at=selected.length-1;at>=0;at--) {
            const row=selected[at],value=row.values.values().next().value;
            source=source.slice(0,row.start)+value+source.slice(row.end);
        }
        return source;
    }
    anchoredDetails(source) {
        if(!this.details||!source.includes('\n'))return null;
        for(let at=source.indexOf('\n');at>=0;at=source.indexOf('\n',at+1)) {
            let suffix=source.slice(at+1);
            for(let controls=0;controls<16;controls++) {
                if(this.detailSources.has(suffix))return [this.details,suffix];
                const control=/^<\/?[Cc][0-9a-fA-F]*>|^<\/?B>|^<[sS]\d+>/.exec(suffix);
                if(!control)break;
                suffix=suffix.slice(control[0].length);
            }
        }
        return null;
    }
    rawPair(source) {
        if(Object.hasOwn(this.model.pairs,source))return this.model.pairs[source];
        // Preserve layout-owned size controls around a complete known literal.
        // Do not use a stripped fragment or a generic printf match as identity.
        const size=/^(?:<[sS]\d+>)+/.exec(source);
        if(size) {
            const body=source.slice(size[0].length);
            if(Object.hasOwn(this.model.pairs,body))return this.model.pairs[body].map(target=>size[0]+target);
        }
        const producer=this.producerPair(source);if(producer)return producer;
        if(!source.includes('<'))return null;
        let found=null;
        for(const [pattern,pair] of this.rawNumeric) {
            const m=pattern.exec(source);if(!m||m[0]!==source)continue;
            const rendered=pair.map((target,side)=>{
                let i=1;return RuntimeText.renderFormat(target,()=>{
                    const v=m[i++];return (Object.hasOwn(this.model.plain_pairs,v)?this.model.plain_pairs[v]:[v,v])[side];
                });
            });
            if(found&&JSON.stringify(found)!==JSON.stringify(rendered))return null;found=rendered;
        }
        return found;
    }
    producerPair(source,rules=this.producerNumeric) {
        let found=null;
        for(const [pattern,pair,styles] of rules) {
            const m=pattern.exec(source);if(!m||m[0]!==source)continue;
            const values=m.slice(1).map(value=>value.replace(/[０-９]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0)));
            if(values.some(value=>Number(value)<-2147483648||Number(value)>2147483647))continue;
            const rendered=pair.map((target,side)=>{
                let i=0;return RuntimeText.renderFormat(target,()=>{
                    const value=values[i],style=styles[side][i++];
                    return style==='fullwidth'?value.replace(/[0-9]/g,c=>String.fromCharCode(c.charCodeAt(0)+0xfee0)):value;
                });
            });
            if(found&&JSON.stringify(found)!==JSON.stringify(rendered))return null;found=rendered;
        }
        return found;
    }
    producerLinePairs(source) {
        if(!this.producerLines.length||!source.includes('<I'))return [];
        if(this.producerLineCache.has(source))return this.producerLineCache.get(source);
        const ranges=RuntimeText.rubyRanges(source);if(ranges===null)return [];
        const result=[];let at=0;
        source.split(/(\r\n|\n|\\n)/).forEach((line,i)=>{
            const end=at+line.length;
            if(!(i%2)&&!RuntimeText.overlaps([at,end],ranges)) {
                const wrapped=/^((?:<\/?[Cc][0-9a-fA-F]*>|<\/?B>|<[sS]\d+>)*)(.*?)((?:<\/[Cc]>|<\/B>)*)$/.exec(line);
                const pair=wrapped&&this.producerPair(wrapped[2],this.producerLines);
                if(pair)result.push([[at,end],pair.map(text=>wrapped[1]+text+wrapped[3])]);
            }
            at=end;
        });
        if(this.producerLineCache.size>=2048)this.producerLineCache.clear();
        this.producerLineCache.set(source,result);return result;
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
            if(!capacities[number]) {
                // No annotation can attach to an icon/control-only line.
                const line=[prefix()];while(units.length&&units[0].tag)take(line);
                result.push(line.join('')+close());continue;
            }
            if(!capacities.slice(number+1).some(Boolean)){const line=[prefix()];while(units.length)take(line);result.push(line.join('')+close());continue;}
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
            const capacities=leftGroup.map(([,line])=>Array.from(line.replace(/<[^<>]*>/g,'')).filter(char=>!/\s/u.test(char)).length);
            const reflowed=RuntimeText.reflowSecondaryParagraph(text,capacities);if(reflowed===null)return null;
            reflowed.forEach((value,index)=>{result[leftGroup[index][0]]=value;});
        }
        return result;
    }
    static annotationPlan(a,b) {
        const left=a.split(/(\r\n|\n|\\n)/),visible=RuntimeText.visualSecondary(b);let right=visible.split(/\r\n|\n|\\n/);
        const count=(left.length+1)/2;
        const needsReflow=count!==right.length||left.some((v,i)=>!(i%2)&&Boolean(v.trim())!==Boolean(right[i/2]?.trim()));
        if(needsReflow||(visible.includes('<')&&count>1)) {
            const reflowed=RuntimeText.reflowAnnotationLines(a,visible);
            if(reflowed!==null)right=reflowed;
            else if(needsReflow) {
                const payload=right.join(' '),anchor=left.findIndex((v,i)=>!(i%2)&&v.trim());
                right=Array(count).fill('');right[Math.max(0,anchor/2)]=payload;
            }
        } else if(count===1)right[0]+=RuntimeText.closeColours(right[0]);
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
        if(mode==='annotation'&&(!RuntimeText.needsAnnotation(a,b)||
                (a===source&&b===source&&this.ambiguousDisplay.has(source.replace(/^(?:<#[^<>]*>)+/,''))))) {
            const result={text:a,layers:[],kind:'plain'};
            if(this.planCache.size>=20000)this.planCache.clear();this.planCache.set(ck,result);return result;
        }
        let result;
        const anchored=this.anchoredDetails(source);
        const known=this.rawPair(source)!==null||
            this.rawPair(source.replace(/^(?:<#[^<>]*>)+/,''))!==null||
            this.producerLinePairs(source).length>0||
            Boolean(anchored&&anchored[0].hasDetailInlineIcon(source))||
            Boolean(anchored&&anchored[0].hasDetailContext(source,anchored[1]))||
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
    translate(source,mode='annotation',key='',scope='',detailContext='') {
        if(this.model.same_language&&mode==='annotation')mode='primary';
        const ck=mode+'\x00'+key+'\x00'+scope+'\x00'+detailContext+'\x00'+source;
        if(this.cache.has(ck))return this.cache.get(ck);
        const result=this.resolve(source,mode,key,scope,detailContext);
        if(this.cache.size>=20000)this.cache.clear();
        this.cache.set(ck,result);return result;
    }
    resolve(source,mode,key,scope,detailContext='') {
        if(mode==='bilingual')mode='annotation';
        if(source.length>16384)return source;
        const keyed=Object.hasOwn(this.keyed,key)?this.keyed[key]:null;
        if(keyed && keyed.source===source) return keyed.tr.translate(source,mode);
        if(scope&&this.scoped[scope]) {
            const t=this.scoped[scope].translate(source,mode);if(t!==source)return t;
        }
        const anchored=this.anchoredDetails(source);
        if(anchored)return anchored[0].translate(source,mode,'','',anchored[1]);
        if(mode==='primary'||mode==='secondary') {
            const spans=this.producerLinePairs(source);
            if(spans.length) {
                const result=[];let at=0;
                for(const [[start,end],pair] of spans) {
                    result.push(this.translate(source.slice(at,start),mode,'','',detailContext),pair[mode==='primary'?0:1]);
                    at=end;
                }
                result.push(this.translate(source.slice(at),mode,'','',detailContext));
                return result.join('');
            }
        }
        if(detailContext)source=this.replaceDetailContext(source,mode,detailContext);
        if(this.detailInlineIcons.length)source=this.replaceDetailInlineIcons(source,mode);
        if(this.ambiguousDisplay.has(source)||this.ambiguousDisplay.has(source.replace(/^(?:<#[^<>]*>)+/,'')))return source;
        const pair=this.rawPair(source);
        if(pair&&(mode==='primary'||mode==='secondary'))return pair[mode==='primary'?0:1];
        const controls=/^(?:<#[^<>]*>)+/.exec(source);
        if(controls)return controls[0]+this.translate(source.slice(controls[0].length),mode);
        if(source.includes('<R>')) {
            const parts=source.split(/(<#[^<>]*>|\r\n|\n|\\n)/);
            return parts.length>1?parts.map((t,i)=>i%2?t:this.translate(t,mode)).join(''):source;
        }
        if(!/[<>]/.test(source)) {const t=this.component(source,mode);if(t!==source)return t;}
        return source.split(/(<[^<>]*>|\r\n|\n|\\n)/).map((t,i)=>i%2?t:this.component(t,mode)).join('');
    }
}
if(typeof module!=='undefined')module.exports={RuntimeText};
