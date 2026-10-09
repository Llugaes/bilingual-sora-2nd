'use strict';
// Exact multiline paragraph resolver for builders that split a verified source
// buffer into individual SetText calls. It deliberately has no substring or
// fuzzy fallback: callers retain the normal RuntimeText path when this returns
// null.

const MAX_SOURCE_BYTES=8192,MAX_SOURCE_LINES=256,MAX_MATCH_CHECKS=4096,MAX_PARAGRAPH_CACHE=128,MAX_LINE_RESOLVERS=512;

class RuntimeParagraphs {
    constructor(model,RuntimeText,options={}) {
        this.model=model||{};
        this.RuntimeText=RuntimeText;
        this.preserveQuestLines=options.preserveQuestLines===true;
        this.byFirstLine=new Map();
        this.paragraphCache=new Map();
        this.lineResolvers=new Map();
        if(typeof RuntimeText!=='function')return;
        // Indexed models already carry the complete first-line candidate list.
        // Do not expand all translations into a second permanently live graph.
        if(this.model.paragraph_sources)return;
        for(const [source,pair] of Object.entries(this.model.pairs||{})) {
            const entry=RuntimeParagraphs.entry(source,pair,this.preserveQuestLines);if(!entry)continue;
            const first=entry.slots[0].text;
            if(!this.byFirstLine.has(first))this.byFirstLine.set(first,[]);
            this.byFirstLine.get(first).push(entry);
        }
    }

    static entry(source,pair,allowSingle=false) {
        if(!Array.isArray(pair)||pair.length!==2||!pair.every(value=>typeof value==='string'))return null;
        const slots=RuntimeParagraphs.slots(source);
        if(slots.length<(allowSingle?1:2)||!RuntimeParagraphs.supportedMarkup(source)||
                !RuntimeParagraphs.supportedMarkup(pair[0])||!RuntimeParagraphs.supportedMarkup(pair[1]))return null;
        return {source,pair,slots,length:source.length};
    }

    candidates(first) {
        if(!this.model.paragraph_sources)return this.byFirstLine.get(first)||[];
        if(this.byFirstLine.has(first))return this.byFirstLine.get(first);
        const index=this.model.paragraph_sources;
        const sources=Object.hasOwn(index,first)?index[first]:[];
        const entries=sources.map(source=>RuntimeParagraphs.entry(source,this.model.pairs[source],this.preserveQuestLines)).filter(Boolean);
        if(this.byFirstLine.size>=MAX_PARAGRAPH_CACHE)this.byFirstLine.clear();
        this.byFirstLine.set(first,entries);return entries;
    }

    static slots(value) {
        const slots=[],separator=/\r\n|\n|\\n/g;
        let start=0,match;
        while((match=separator.exec(value))!==null) {
            slots.push({text:value.slice(start,match.index),start,end:match.index});
            start=match.index+match[0].length;
        }
        slots.push({text:value.slice(start),start,end:value.length});
        return slots;
    }

    static supportedMarkup(value) {
        const tags=value.match(/<[^<>]*>/g)||[];
        if(/[<>]/.test(value.replace(/<[^<>]*>/g,'')))return false;
        return tags.every(tag=>
            /^<#[^<>]*>$/.test(tag) ||
            tag==='<R>' || /^<\/R[^<>]*>$/.test(tag) ||
            /^<\/?[Cc][0-9a-fA-F]*>$/.test(tag) ||
            /^<\/?B>$/.test(tag) || /^<[sS]\d+>$/.test(tag) || /^<I\d+>$/.test(tag)
        );
    }

    sourceMatches(full,slots,entry,startIndex,boundaries) {
        const start=slots[startIndex].start,end=start+entry.length;
        if(!full.startsWith(entry.source,start)||!boundaries.has(end))return false;
        const finalSlot=startIndex+entry.slots.length-1;
        return finalSlot<slots.length &&
            slots.slice(startIndex,finalSlot+1).map(slot=>slot.text).every(
                (value,index)=>value===entry.slots[index].text
            );
    }

    matches(fullSource) {
        if(typeof fullSource!=='string'||!this.RuntimeText||
                this.RuntimeText.byteLength(fullSource)>MAX_SOURCE_BYTES)return null;
        if(this.paragraphCache.has(fullSource))return this.paragraphCache.get(fullSource);
        const slots=RuntimeParagraphs.slots(fullSource);
        if(slots.length>MAX_SOURCE_LINES)return null;
        const boundaries=new Set([fullSource.length]);
        for(const slot of slots) {boundaries.add(slot.start);boundaries.add(slot.end);}
        const matches=[];let checks=0;
        for(let startIndex=0;startIndex<slots.length;startIndex++) {
            const candidates=this.candidates(slots[startIndex].text);
            for(const entry of candidates) {
                if(++checks>MAX_MATCH_CHECKS)return null;
                if(this.sourceMatches(fullSource,slots,entry,startIndex,boundaries))
                    matches.push({entry,startIndex});
            }
        }
        const result={slots,matches};
        if(this.paragraphCache.size>=MAX_PARAGRAPH_CACHE)this.paragraphCache.clear();
        this.paragraphCache.set(fullSource,result);
        return result;
    }

    reflow(entry) {
        const source=entry.source,[primary,secondary]=entry.pair;
        const flow=target=>this.preserveQuestLines
            ?this.questLines(source,target)
            :this.RuntimeText.reflowAnnotationLines(source,target);
        const first=primary===source
            ?entry.slots.map(slot=>slot.text)
            :flow(primary);
        const second=secondary===source?entry.slots.map(slot=>slot.text):flow(secondary);
        if(first===null||second===null||first.length!==entry.slots.length||second.length!==entry.slots.length)
            return null;
        return [first,second];
    }

    questLines(source,target) {
        const left=RuntimeParagraphs.slots(source).map(slot=>slot.text);
        const right=RuntimeParagraphs.slots(target).map(slot=>slot.text);
        const groups=lines=>{
            const result=[];let current=null;
            lines.forEach((text,index)=>{
                const visible=text.replace(/<[^<>]*>/g,'');
                const marker=/^[\s\u3000]*([●・·•★☆])/u.exec(visible)?.[1];
                const kind=marker==='●'?'member':marker&&'・·•'.includes(marker)?'action':marker?'progress':null;
                if(!visible.trim()){current=null;return;}
                if(!current||kind){current={kind:kind||'text',lines:[]};result.push(current);}
                current.lines.push([index,text]);
            });
            return result;
        };
        const a=groups(left),b=groups(right),result=Array(left.length).fill('');
        if(a.length!==b.length||a.some((g,i)=>g.kind!==b[i].kind)) {
            // Do not concatenate distinct list members into a guessed stream.
            if([...a,...b].some(group=>group.kind==='member'))return null;
            // An empty primary slot has no native glyph on which to anchor a
            // secondary lane. Put every target line on a nonempty source slot;
            // otherwise primary mode survives while annotation loses words.
            const occupied=left.map((text,index)=>[index,text]).filter(([,text])=>text.replace(/<[^<>]*>/g,'').trim());
            const targetLines=right.filter(text=>text.replace(/<[^<>]*>/g,'').trim());
            const owned=targetLines.length<=occupied.length
                ?this.RuntimeText.ownedSecondaryLines(targetLines)
                :this.RuntimeText.reflowAnnotationLines(occupied.map(([,text])=>text).join('\n'),targetLines.join('\n'));
            if(owned===null||owned.length>occupied.length)return null;
            owned.forEach((value,index)=>{result[occupied[index][0]]=value;});return result;
        }
        for(let i=0;i<a.length;i++) {
            const from=a[i].lines,to=b[i].lines.map(([,line])=>line);
            let values;
            if(to.length<=from.length)values=this.RuntimeText.ownedSecondaryLines(to);
            else values=this.RuntimeText.reflowAnnotationLines(from.map(([,line])=>line).join('\n'),to.join('\n'));
            if(values===null||values.length>from.length)return null;
            values.forEach((value,index)=>{result[from[index][0]]=value;});
        }
        return result;
    }

    lineResolver(source,primary,secondary) {
        const key=source+'\x00'+primary+'\x00'+secondary;
        if(this.lineResolvers.has(key))return this.lineResolvers.get(key);
        const pairs=Object.create(null),plainPairs=Object.create(null);
        pairs[source]=[primary,secondary];plainPairs[source]=[primary,secondary];
        const resolver=new this.RuntimeText({pairs,plain_pairs:plainPairs,numeric:[],raw_numeric:[]});
        if(this.lineResolvers.size>=MAX_LINE_RESOLVERS)this.lineResolvers.clear();
        this.lineResolvers.set(key,resolver);
        return resolver;
    }

    lookup(fullSource,lineIndex,exactLine,mode='annotation') {
        if(!Number.isInteger(lineIndex)||typeof exactLine!=='string'||
                !['annotation','bilingual','primary','secondary'].includes(mode))return null;
        const full=this.matches(fullSource);
        if(!full||lineIndex<0||lineIndex>=full.slots.length||full.slots[lineIndex].text!==exactLine)return null;
        let selected=null,ambiguous=false;
        for(const match of full.matches) {
            const offset=lineIndex-match.startIndex;
            if(offset<0||offset>=match.entry.slots.length||match.entry.slots[offset].text!==exactLine)continue;
            if(!selected||match.entry.length>selected.entry.length) {
                selected=match;ambiguous=false;
            } else if(match.entry.length===selected.entry.length&&
                    (match.entry.source!==selected.entry.source ||
                     match.entry.pair[0]!==selected.entry.pair[0] ||
                     match.entry.pair[1]!==selected.entry.pair[1])) {
                ambiguous=true;
            }
        }
        if(!selected||ambiguous)return null;
        const reflowed=this.reflow(selected.entry);
        if(!reflowed)return null;
        const slot=lineIndex-selected.startIndex;
        return this.lineResolver(exactLine,reflowed[0][slot],reflowed[1][slot]).render(exactLine,mode);
    }
}

if(typeof module!=='undefined')module.exports={RuntimeParagraphs};
