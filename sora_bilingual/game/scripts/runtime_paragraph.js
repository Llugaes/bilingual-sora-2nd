'use strict';
// Exact multiline paragraph resolver for builders that split a verified source
// buffer into individual SetText calls. It deliberately has no substring or
// fuzzy fallback: callers retain the normal RuntimeText path when this returns
// null.

const MAX_SOURCE_BYTES=8192,MAX_SOURCE_LINES=256,MAX_MATCH_CHECKS=4096,MAX_PARAGRAPH_CACHE=128,MAX_LINE_RESOLVERS=512;

class RuntimeParagraphs {
    constructor(model,RuntimeText) {
        this.model=model||{};
        this.RuntimeText=RuntimeText;
        this.byFirstLine=new Map();
        this.paragraphCache=new Map();
        this.lineResolvers=new Map();
        if(typeof RuntimeText!=='function')return;
        for(const [source,pair] of Object.entries(this.model.pairs||{})) {
            if(!Array.isArray(pair)||pair.length!==2||!pair.every(value=>typeof value==='string'))continue;
            const slots=RuntimeParagraphs.slots(source);
            if(slots.length<2||!RuntimeParagraphs.supportedMarkup(source)||
                    !RuntimeParagraphs.supportedMarkup(pair[0])||!RuntimeParagraphs.supportedMarkup(pair[1]))continue;
            const entry={source,pair,slots,length:source.length};
            const first=slots[0].text;
            if(!this.byFirstLine.has(first))this.byFirstLine.set(first,[]);
            this.byFirstLine.get(first).push(entry);
        }
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
            const candidates=this.byFirstLine.get(slots[startIndex].text)||[];
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
        const first=primary===source
            ?entry.slots.map(slot=>slot.text)
            :this.RuntimeText.reflowAnnotationLines(source,primary);
        const second=this.RuntimeText.reflowAnnotationLines(source,secondary);
        if(first===null||second===null||first.length!==entry.slots.length||second.length!==entry.slots.length)
            return null;
        return [first,second];
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
