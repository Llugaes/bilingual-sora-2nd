"""Exhaustive offline catalog audit; never opens or attaches to the game.

Counts are resource/resolver coverage, not a claim that every game surface has
been observed. Missing locales and ambiguous keys are reported separately.
"""
import json
import re
from collections import Counter
from pathlib import Path
from menu_text import MenuTranslator, visual_secondary

ROOT=Path(__file__).resolve().parent


def needs_annotation(a,b):
    a=re.sub(r'<[^<>]*>','',a).strip();b=re.sub(r'<[^<>]*>','',b).strip()
    return bool(a and b and (a!=b or re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]',a)))


def audit(entries,primary='zh-Hans',secondary='ja',source_language='zh-Hans'):
    tr=MenuTranslator(entries,primary,secondary,source_language)
    counts=Counter();gaps=[];cases=[]
    for source,(a,b) in tr.pairs.items():
        if not needs_annotation(a,b):continue
        counts['eligible_unambiguous_sources']+=1
        plan=tr.render(source)
        if plan['kind']=='layered':
            assert plan['text'].replace('<R></R_>','')==a,(source,'primary altered')
            actual=' '.join(v['text'] for v in plan['layers'])
            expected=re.sub(r'\r\n|\n|\\n',' ',visual_secondary(b))
            # Blank lines are not annotation-bearing lines.
            assert re.sub(r'\s+','',actual)==re.sub(r'\s+','',expected),(source,'secondary dropped',actual,expected)
            counts['independent_lanes']+=1
            if '<R>' in a+b:counts['original_ruby_preserved']+=1
            cases.append({'source':source,'mode':'annotation','plan':plan})
        elif plan['kind']=='ruby':
            chunks=re.compile(r'<R>([^<>]*)</R([^<>]*)>')
            main=chunks.sub(lambda m:m[1],plan['text'])
            second=chunks.sub(lambda m:m[2],plan['text'])
            normalize=lambda t:re.sub(r'\s+','',visual_secondary(t.replace('\\n','\n')))
            assert normalize(main)==normalize(a),(source,'primary content dropped')
            assert normalize(second)==normalize(b),(source,'secondary content dropped')
            counts['native_ruby']+=1
        else:
            counts['unannotated_unambiguous_sources']+=1
            gaps.append({'reason':'renderer_gap','source':source,'primary':a,'secondary':b})
    candidates={}
    for e in entries:
        t=e['texts'];source=t.get(source_language)
        if not source:continue
        if primary not in t or secondary not in t:
            counts['entries_missing_locale']+=1;continue
        if not needs_annotation(t[primary],t[secondary]):continue
        if source not in tr.pairs:
            candidates.setdefault(source,[]).append(e['key'])
    for source,keys in candidates.items():
        plan=tr.render(source)
        if source in tr.plain_pairs and plan['kind'] in ('ruby','layered'):
            counts['normalized_or_composite_sources']+=1;continue
        if plan['kind'] in ('ruby','layered'):counts['partially_annotated_ambiguous_sources']+=1
        if any(s==source for _,s,_ in tr.keyed):
            counts['requires_text_key']+=1;continue
        if any(s.render(source)['kind'] in ('ruby','layered') for s in tr.scoped.values()):
            counts['requires_owner_scope']+=1;continue
        counts['ambiguous_sources']+=1
        # These remain explicit gaps unless a real runtime key/owner scope is
        # known. Never guess a translation merely to inflate coverage.
        gaps.append({'reason':'ambiguous_source_requires_runtime_identity','source':source,'keys':keys})
    return {'counts':dict(counts),'gaps':gaps,'cases':cases}


def main():
    entries=json.loads((ROOT/'generated/catalog.json').read_text(encoding='utf-8'))['entries']
    result=audit(entries)
    result.update(catalog_entries=len(entries),primary='zh-Hans',secondary='ja',
                  game_started=False,game_attached=False)
    (ROOT/'generated/coverage-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('gaps','cases')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
