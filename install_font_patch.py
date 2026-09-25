"""Install removable loose fonts; update only files matching our own receipt."""
from pathlib import Path
import argparse
import hashlib
import json
import lz4.frame
from hooks import verify_target
from locales import LOCALES
from font_merge import parse_fnt,parse_dds
from universal_fonts import MAX_DECODED_BYTES
from native_config import write_config,replace_file
import tempfile
import os

ROOT=Path(__file__).resolve().parent
LOADER_SHA='e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7'

def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_bytes(path,data):
    handle=tempfile.NamedTemporaryFile(dir=path.parent,delete=False,suffix='.tmp')
    try:
        with handle:handle.write(data)
        replace_file(handle.name,path)
    finally:
        if os.path.exists(handle.name):os.unlink(handle.name)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--loader',type=Path,required=True)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--update',action='store_true',help='replace only files matching our previous receipt')
    parser.add_argument('--candidate',type=Path,default=ROOT/'generated/font-universal')
    args=parser.parse_args()
    game=args.game.resolve()
    verify_target(game/'sora_2nd.exe')
    candidate=args.candidate
    manifest=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    loader=args.loader.read_bytes()
    if sha(loader)!=LOADER_SHA:raise RuntimeError('Loader digest mismatch')
    expected={f'asset{v.font_suffix}/{tail}' for v in LOCALES.values()
        for tail in ('common/font/font_0.fnt','dx11/image/font_0.dds')}
    if manifest.get('version')!=2 or {v['path'] for v in manifest['files']}!=expected:
        raise RuntimeError('Candidate must include every configured font asset')
    files={
        'xinput1_4.dll':loader,
        'sora2looseload.ini':b'[Logging]\r\nEnabled=1\r\n',
    }
    for item in manifest['files']:
        path=(candidate/item['path']).resolve()
        if not path.is_relative_to(candidate.resolve()):raise RuntimeError('Candidate escaped root')
        data=path.read_bytes()
        if sha(data)!=item['sha256']:raise RuntimeError('Candidate digest mismatch')
        files[item['path']]=data
    for prefix in {f'asset{v.font_suffix}' for v in LOCALES.values()}:
        dds=lz4.frame.decompress(files[prefix+'/dx11/image/font_0.dds'])
        if len(dds)>MAX_DECODED_BYTES:raise RuntimeError('Font exceeds game buffer')
        image=parse_dds(dds)
        parse_fnt(files[prefix+'/common/font/font_0.fnt'],atlas_width=image.width,atlas_height=image.height)
    targets={game/name:data for name,data in files.items()}
    previous={}
    if args.update:
        if not args.install:
            parser.error('--update requires --install')
        old=json.loads((ROOT/'generated/font-install.json').read_text(encoding='utf-8'))
        if Path(old['game']).resolve()!=game:
            raise RuntimeError('Previous receipt belongs to another game directory')
        previous={Path(item['path']):item['sha256'] for item in old['files']}
        if not set(previous)<=set(targets):
            raise RuntimeError('Update would leave untracked installed files')
    for target in targets:
        if not target.resolve().is_relative_to(game):
            raise RuntimeError('Target escaped game root')
        if args.update and target in previous:
            if not target.is_file() or sha(target.read_bytes())!=previous[target]:
                raise RuntimeError(f'Installed file changed outside this tool: {target}')
        elif target.exists():
            raise RuntimeError(f'Refusing to overwrite existing file: {target}')
    receipt={'installed':args.install,'game':str(game),'files':[
        {'path':str(path),'size':len(data),'sha256':sha(data)} for path,data in targets.items()]}
    if args.install:
        import frida
        if any(p.name.lower()=='sora_2nd.exe' for p in frida.get_local_device().enumerate_processes()):
            raise RuntimeError('请先正常退出游戏，再更新字库文件。')
        created=[]
        originals={path:path.read_bytes() for path in previous} if args.update else {}
        try:
            for path,data in targets.items():
                path.parent.mkdir(parents=True,exist_ok=True)
                if path in originals:
                    created.append(path)
                    replace_bytes(path,data)
                else:
                    with path.open('xb') as stream:
                        created.append(path)
                        stream.write(data)
                if sha(path.read_bytes())!=sha(data):
                    raise RuntimeError(f'Install verification failed: {path}')
            write_config(receipt,ROOT/'generated/font-install.json')
        except Exception:
            # Only remove the exact new paths created by this transaction.
            for path in reversed(created):
                if path in originals:
                    replace_bytes(path,originals[path])
                else:
                    path.unlink()
            raise
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':
    main()
