import os
"""Real catalogue render timings in Frida's default runtime, outside the game."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import subprocess
import frida
from native_catalog import ready_model
from native_config import read_config
from menu_text import MenuTranslator

ROOT=Path(__file__).resolve().parents[1]
GAME=Path(os.environ['SORA_GAME_DIR'])

def main():
    model,_,_=ready_model(GAME,read_config())
    model={k:v for k,v in model.items() if k not in ('script_identities','table_identities')}
    sources=list(model['pairs']);sources=sources[::max(1,len(sources)//600)]
    sources+=['读音','交谈','<I1544>','<I915>','未知文本 '+str(len(sources))]
    cases=[]
    for source in sources:
        pair=model['pairs'].get(source)
        if pair:
            tr=MenuTranslator([{'texts':{'s':source,'a':pair[0],'b':pair[1]}}],'a','b','s',True)
            cases.append({'source':source,'expected':tr.render(source)})
        else:cases.append({'source':source})
    source=(ROOT/'runtime_text.js').read_text('utf-8')+'\nconst profileModel='+json.dumps(model,ensure_ascii=False,separators=(',',':'))+';'
    source+='''
const kernel=Process.getModuleByName('kernel32.dll'),counter=Memory.alloc(8),freq=Memory.alloc(8);
const qpc=new NativeFunction(kernel.getExportByName('QueryPerformanceCounter'),'int',['pointer'],{scheduling:'exclusive'});
new NativeFunction(kernel.getExportByName('QueryPerformanceFrequency'),'int',['pointer'])(freq);
const frequency=freq.readU64().toNumber();
function now(){qpc(counter);return counter.readU64().toNumber()*1000/frequency;}
rpc.exports={profile(cases){
  const setup=now(),tr=new RuntimeText(profileModel),setupMs=now()-setup;
  const times=[],outputs=[];
  for(const c of cases){const start=now();outputs.push(tr.render(c.source));times.push(now()-start);}
  const start=now();for(const c of cases)tr.render(c.source);const warmMs=now()-start;
  times.sort((a,b)=>a-b);
  return {cases:cases.length,setupMs,coldP95Ms:times[Math.floor(times.length*.95)],coldMaxMs:times[times.length-1],warmMeanMs:warmMs/cases.length,outputs};
}};
'''
    host=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.buffer.read()'],stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    session=None
    try:
        session=frida.attach(host.pid);agent=session.create_script(source);agent.load()
        result=agent.exports_sync.profile(cases)
        for case,plan in zip(cases,result.pop('outputs')):
            if 'expected' in case:assert plan==case['expected'],case['source']
        result.update(game_started=False,game_attached=False,runtime='frida-default',includes_game_layout=False)
        (ROOT/'generated/frida-text-performance.json').write_text(json.dumps(result,indent=2),'utf-8')
        print(json.dumps(result,indent=2))
    finally:
        if session is not None:session.detach()
        host.communicate(timeout=5)

if __name__=='__main__':main()
