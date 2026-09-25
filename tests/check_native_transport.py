import os
"""Exercise the production model RPC in a disposable process, never the game."""
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import frida
from native_catalog import ready_model
from native_config import read_config
from native_runtime import NativeLabels

ROOT=Path(__file__).resolve().parents[1]


def main():
    model,_,_=ready_model(Path(os.environ['SORA_GAME_DIR']),read_config())
    print(json.dumps({'compact_utf8_bytes':len(json.dumps(model,ensure_ascii=False,separators=(',',':')).encode()),
                      'rpc_json_bytes':len(json.dumps(model).encode())}),flush=True)
    source='\n'.join((ROOT/name).read_text('utf-8') for name in ('runtime_text.js','runtime_identity.js'))
    source+='''\nrpc.exports={load(model,mode,active,scale,layout){
      globalThis.tr=new RuntimeText(model);
      globalThis.ids=new ScriptIdentities(model.script_identities);
      globalThis.tables=new TableIdentities(model.table_identities);
      return true;
    },sample(text){return tr.translate(text,'secondary');}};'''
    transport=ROOT/'native_transport.js'
    if transport.exists():source+='\n'+transport.read_text('utf-8')
    host=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.buffer.read()'],stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    session=None
    try:
        session=frida.attach(host.pid);session.on('detached',lambda *a:print('detached:',a,flush=True))
        script=session.create_script(source);script.on('destroyed',lambda:print('script destroyed',flush=True));script.load()
        native=NativeLabels(lambda _:None);native.script=script
        start=time.perf_counter();assert native.load(model,read_config(),'annotation')
        source,pair=next(iter(model['pairs'].items()))
        assert script.exports_sync.sample(source)==pair[1]
        result={'model_loaded':True,'seconds':round(time.perf_counter()-start,3),'game_attached':False}
        print(json.dumps(result),flush=True)
        (ROOT/'generated/native-transport-check.json').write_text(json.dumps(result,indent=2),'utf-8')
    finally:
        if session is not None:
            try:session.detach()
            except frida.InvalidOperationError:pass
        host.communicate(timeout=5)


if __name__=='__main__':main()
