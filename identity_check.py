"""Replay provenance and render conservation from real local assets, offline."""
import base64
import json
import subprocess
from collections import Counter
from pathlib import Path
from native_catalog import ready_model, model_path
from native_config import read_config
from menu_text import MenuTranslator
from audit_coverage import audit
from resources import FpacArchive, _ARCHIVES, _logical_script_entries
from tables import _TABLE_ARCHIVES, _logical_tables

ROOT=Path(__file__).resolve().parent
import os
GAME=Path(os.environ.get('SORA_GAME_DIR','generated/missing-game-fixture'))


def same_pair(actual, expected):
    """Fresh models use tuples; JSON caches use lists. Compare the content."""
    return isinstance(actual,(list,tuple)) and tuple(actual)==tuple(expected)


def main():
    config={**read_config(),'primary':'zh-Hans','secondary':'ja','game_language':'zh-Hans','scope':'all'}
    model,signature,_=ready_model(GAME,config)
    entries=json.loads((ROOT/'generated/catalog.json').read_text('utf-8'))['entries']
    by_key={e['key']:e for e in entries};contexts={};cases=[];scripts=[]
    with FpacArchive(GAME/'pac/steam'/_ARCHIVES['zh-Hans']) as archive:
        paths=_logical_script_entries(archive)
        for sig,bucket in model['script_identities']['scripts'].items():
            for script in bucket:
                scripts.append({'signature':sig,'data':base64.b64encode(archive.read(paths[script['paths'][0]])).decode(),
                                'sha256':script['sha256'],'functionName':next(iter(script['functions']))})
                for path in script['paths']:
                    for fn,context in script['functions'].items():contexts[path+'/'+fn]=(sig,script['sha256'],context)
                for fn,context in script['functions'].items():
                    for token,call in context['calls'].items():
                        actual=','.join('1073741866' if v=='?' else v for v in token.split(','))
                        identity={'signature':sig,'sha256':script['sha256'],'functionName':fn,'argumentsToken':actual}
                        for source,(a,b) in call['model']['pairs'].items():
                            if not source.strip():continue
                            tr=MenuTranslator([{'texts':{'s':source,'a':a,'b':b}}],'a','b','s',True)
                            cases.append({'identity':identity,'source':source,'plan':tr.render(source),
                                          'secondary':b})
    counts=Counter();remaining=[]
    coverage=audit(entries)
    for gap in coverage['gaps']:
        good=0;bad=[]
        for key in gap.get('keys',[]):
            e=by_key[key];t=e['texts'];source=gap['source'];pair=[t['zh-Hans'],t['ja']];ok=False
            if key.startswith('table/'):
                row=model['table_identities']['models'].get(key)
                ok=bool(row and same_pair(row['model']['pairs'].get(source),pair))
            elif '.dat/' in key:
                direct=model['script_identities'].get('pointer_models',{}).get(key)
                if direct and same_pair(direct['model']['pairs'].get(source),pair):
                    ok=True;counts['script_records_with_pointer_route']+=1
                path,rest=key.split('.dat/',1);parts=rest.split('/');found=contexts.get(path+'.dat/'+parts[0])
                if found:
                    context=found[2]
                    if len(parts)>2 and parts[1]=='called':
                        for call in context['calls'].values():
                            if int(parts[2]) not in call['records']:continue
                            if same_pair(call['model']['pairs'].get(source),pair):ok=True;break
                            # A fragment can be ambiguous inside a call, while
                            # its complete block retains the exact localised text.
                            alignment='/alignment/'+key.split('/alignment/',1)[1] if '/alignment/' in key else ''
                            whole=by_key.get(key.split('/arg/')[0]+'/assembled_dialogue'+alignment)
                            if whole and whole['texts'].get('zh-Hans') in call['model']['pairs']:
                                wt=whole['texts'];expected=[wt.get('zh-Hans'),wt.get('ja')]
                                if same_pair(call['model']['pairs'][expected[0]],expected) and source in expected[0] and t['ja'] in expected[1]:
                                    ok=True;counts['fragment_records_covered_by_complete_call']+=1;break
                    # Function-scoped resolution alone is not proof that an
                    # unrelated non-dialogue command carries this context.
            if ok:good+=1
            else:bad.append(key)
        counts['records_resolved']+=good;counts['records_remaining']+=len(bad)
        counts['sources_all_records_resolved' if not bad else 'sources_partial' if good else 'sources_remaining']+=1
        if bad:remaining.append({'source':gap['source'],'keys':bad,'resolved_keys':good})
    table_files={}
    import hashlib
    with FpacArchive(GAME/'pac/steam'/_TABLE_ARCHIVES['zh-Hans']) as archive:
        for path,actual in _logical_tables(archive).items():
            data=archive.read(actual);digest=hashlib.sha256(data).hexdigest()
            if digest in model['table_identities']['files']:table_files[digest]=base64.b64encode(data).decode()
    fixture=ROOT/'generated/identity-replay.tmp.json'
    try:
        fixture.write_text(json.dumps({'model':str(model_path(signature,config)),
            'scripts':scripts,'cases':cases,'table_files':table_files},ensure_ascii=False,separators=(',',':')),'utf-8')
        proc=subprocess.run(['node',str(ROOT/'tests/replay_identity.js'),str(fixture)],capture_output=True,text=True,encoding='utf-8',check=True)
        replay=json.loads(proc.stdout)
    finally:
        fixture.unlink(missing_ok=True)
    result={'counts':dict(counts),'replay':replay,'remaining':remaining,'catalog_entries':len(entries),
            'game_started':False,'game_attached':False,'meaning':'Offline record routing and content preservation; native reachability and visuals require game acceptance.'}
    (ROOT/'generated/identity-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='remaining'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
