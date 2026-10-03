'use strict';
// Document pagination runs only when a book is opened or its display settings
// change. Native source pages and illustration runs remain separate from text
// identity; equal page numbers in different locales are never paired.
class RuntimeBooks {
    constructor(documents,Text) {this.documents=documents||{};this.Text=Text;this.cache=new Map();}
    static runs(pages) {
        const result=[];
        for(const [image,text] of pages) {
            if(!result.length||result.at(-1).image!==image)result.push({image,pages:[]});
            result.at(-1).pages.push(text);
        }
        return result;
    }
    static lines(pages) {return pages.join('\n').split(/\r\n|\n/);}
    // note_books.lay: contents_text has 680 units of height and 30-unit type.
    // Reserve the first annotation plus both native reading lanes. Normal
    // single-language pages keep the game's own wraps and page boundaries.
    static lineBudget(style={}) {
        const scale=style.rubyScale??.8,gap=style.rubyGap??3,line=style.lineGap??12;
        const pitch=30*(1+scale)+2*gap+line+30+9;
        return Math.max(1,Math.floor((680-60-Math.abs(style.offsetY||0))/pitch));
    }
    pages(id,mode,style={}) {
        const doc=this.documents[id];if(!doc)return null;
        const budget=RuntimeBooks.lineBudget(style),key=JSON.stringify([String(id),mode,budget]);
        if(this.cache.has(key))return this.cache.get(key);
        const sides=['source','primary','secondary'].map(side=>RuntimeBooks.runs(doc[side]));
        if(sides.some(runs=>runs.length!==sides[0].length||runs.some((run,i)=>run.image!==sides[0][i].image)))return null;
        const output=[],bilingual=mode==='annotation'||mode==='bilingual';
        if(!bilingual) {
            const chosen=doc[mode==='secondary'?'secondary':'primary'];
            for(let i=0;i<chosen.length;i++) {
                const nativePage=Math.min(doc.source.length,Math.floor(i*doc.source.length/chosen.length)+1);
                output.push({image:chosen[i][0],source:doc.source[nativePage-1][1],primary:chosen[i][1],secondary:chosen[i][1],nativePage});
            }
        } else {
            const a=RuntimeBooks.lines(doc.primary.map(p=>p[1])),b=RuntimeBooks.lines(doc.secondary.map(p=>p[1]));
            const images=doc.primary.flatMap(([image,text])=>text.split(/\r\n|\n/).map(()=>image));
            const length=Math.max(a.length,b.length),cuts=new Set([0,length]);
            for(let i=budget;i<length;i+=budget)cuts.add(i);
            // Illustrations belong to the selected primary document. Their
            // page boundaries do not establish corresponding sentences in
            // another locale (French can continue an article past a picture).
            for(let i=1;i<images.length;i++)if(images[i]!==images[i-1])cuts.add(Math.ceil(i*length/a.length));
            const sorted=[...cuts].sort((a,b)=>a-b);
            for(let i=0;i<sorted.length-1;i++) {
                const start=sorted[i],end=sorted[i+1],fromA=Math.floor(start*a.length/length),toA=Math.floor(end*a.length/length);
                const fromB=Math.floor(start*b.length/length),toB=Math.floor(end*b.length/length);
                const nativePage=Math.min(doc.source.length,Math.floor(start*doc.source.length/length)+1);
                output.push({image:images[fromA],source:doc.source[nativePage-1][1],nativePage,
                    primary:a.slice(fromA,toA).join('\n'),secondary:b.slice(fromB,toB).join('\n'),
                    primaryLines:toA-fromA,secondaryLines:toB-fromB});
            }
        }
        // Native saved reading position is one byte. Refuse incompatible
        // resources rather than wrap a page index into unrelated content.
        if(!output.length||output.length>255)return null;
        if(this.cache.size>=256)this.cache.clear();this.cache.set(key,output);return output;
    }
    context(id,page,source,mode,style) {
        const value=this.pages(id,mode,style)?.[page-1];
        if(!value||value.source!==source)return null;
        if(!value.context) {
            // A very short primary caption may finish before its translated
            // continuation. Show that continuation once at normal size;
            // never repeat an earlier primary sentence to fabricate a pair.
            const a=value.primary.trim()?value.primary:value.secondary,b=value.primary.trim()?value.secondary:value.primary;
            value.context={strict:true,model:{pairs:{[source]:[a,b]},numeric:[],raw_numeric:[]}};
        }
        return value.context;
    }
}
if(typeof module!=='undefined')module.exports={RuntimeBooks};
