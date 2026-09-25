"""Local resource/model cache. Never starts or attaches to the game."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from catalog_build import build_all
from menu_text import MenuTranslator
from locales import DEFAULT_PRIMARY
from cache_io import publish_json,read_model

ROOT=Path(__file__).resolve().parent

def fingerprint(game):
    paths=sorted((Path(game)/'pac'/'steam').glob('*.pac'))
    resources=[(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in paths
               if p.name.startswith(('script','table'))]
    parser_code=b''.join((ROOT/n).read_bytes() for n in
        ('resources.py','tables.py','menu_tables.py','catalog_build.py','locales.py'))
    code=hashlib.sha256(parser_code+b''.join((ROOT/n).read_bytes() for n in
        ('menu_text.py','native_catalog.py','runtime_identity.py'))).hexdigest()
    return {'resources':resources,'code':code,'catalog_code':hashlib.sha256(parser_code).hexdigest()}

def load_entries(game,output=ROOT/'generated'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    stamp=fingerprint(game)
    signature=json.dumps(stamp,sort_keys=True)
    catalog_signature=json.dumps({'resources':stamp['resources'],'code':stamp['catalog_code']},sort_keys=True)
    manifest=output/'catalog-signature.json';catalog=output/'catalog.json'
    if not manifest.exists() or manifest.read_text(encoding='utf-8')!=catalog_signature or not catalog.exists():
        result=build_all(game,output)
        manifest.write_text(catalog_signature,encoding='utf-8')
        return result['entries'],signature
    return json.loads(catalog.read_text(encoding='utf-8'))['entries'],signature

def model_path(signature,config,output=ROOT/'generated'):
    identity=[signature,config['primary'],config['secondary'],config.get('game_language',DEFAULT_PRIMARY),
              config.get('scope','all'),config.get('sources',[])]
    digest=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
    return Path(output)/('runtime-'+digest[:20]+'.json')

def ready_model(game,config,output=ROOT/'generated'):
    """Fast startup: a current model does not need the 500k-entry catalog."""
    signature=json.dumps(fingerprint(game),sort_keys=True)
    path=model_path(signature,config,output)
    cached=read_model(path)
    if cached is not None:return cached,signature,None
    entries,signature=load_entries(game,output)
    return load_model(entries,signature,config,output,game=game),signature,entries

def load_model(entries,signature,config,output=ROOT/'generated',*,game):
    path=model_path(signature,config,output)
    cached=read_model(path)
    if cached is not None:return cached
    selected=entries
    if config.get('scope')=='menu':selected=[e for e in entries if e.get('key','').startswith('table/')]
    if config.get('scope')=='selected':
        sources=set(config.get('sources',[]));lang=config.get('game_language',DEFAULT_PRIMARY)
        selected=[e for e in entries if e['texts'].get(lang) in sources]
    model=MenuTranslator(selected,config['primary'],config['secondary'],config.get('game_language',DEFAULT_PRIMARY)).runtime_model()
    coverage=Counter();source=config.get('game_language',DEFAULT_PRIMARY)
    for entry in selected:
        texts=entry['texts']
        if not texts.get(source,'').strip():continue
        coverage['source_records']+=1
        missing=[side for side in ('primary','secondary') if not texts.get(config[side],'').strip()]
        for side in missing:coverage['missing_'+side]+=1
        if not missing:coverage['complete_pair_records']+=1
    model['coverage']=dict(coverage)
    if config.get('scope','all')!='selected' and not coverage['complete_pair_records']:
        raise ValueError('本地资源没有所选源语言、主语言和副语言的可用配对；请检查资源与源语言设置。')
    from runtime_identity import compile_script_identities, compile_table_identities
    args=(game,selected,config['primary'],config['secondary'],config.get('game_language',DEFAULT_PRIMARY))
    model['script_identities']=compile_script_identities(*args)
    model['table_identities']=compile_table_identities(*args)
    publish_json(path,model)
    return model

if __name__=='__main__':
    import argparse,time
    parser=argparse.ArgumentParser();parser.add_argument('--game-dir',required=True,type=Path)
    args=parser.parse_args();start=time.perf_counter()
    entries,signature=load_entries(args.game_dir)
    from native_config import read_config
    model=load_model(entries,signature,read_config(),game=args.game_dir)
    print(json.dumps({'entries':len(entries),'exact_sources':len(model['pairs']),'seconds':round(time.perf_counter()-start,2)}))
