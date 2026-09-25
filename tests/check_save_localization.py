import os
"""Replay the reported save-menu strings against complete local-resource models.

Only reads installed archives and prepares caches. Never starts/attaches a game.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native_catalog import load_entries,load_model,model_path
from native_config import read_config

GAME=Path(os.environ['SORA_GAME_DIR'])


def main():
    entries,signature=load_entries(GAME)
    navi=[e for e in entries if e['key'].startswith('table/t_quest.tbl/NaviText/') and e['key'].endswith('/title')]
    assert len(navi)==156 and all(len(e['texts'])==8 for e in navi),len(navi)
    fixtures=[
        ('第２章“大地翻腾”\u3000\u3000\u3000\u3000 ＜Nightmare＞','２章「荒ぶる大地」','Chapter 2: The Raging Land'),
        ('做好准备搭乘定期船','準備を整えて定期船に乗ろう','Prepare to Board the Airliner'),
        ('\u3000·艾丝蒂尔\u3000\u3000\u3000Lv.39','エステル','Estelle'),
        ('\u3000·克萝赛\u3000\u3000\u3000\u3000Lv.38','クローゼ','Kloe'),
        ('\u3000·雪拉扎德\u3000\u3000\u3000Lv.39','シェラザード','Scherazard'),
        ('\u3000·奥利维尔\u3000\u3000\u3000Lv.39','オリビエ','Olivier')]
    report={'game_started':False,'game_attached':False,'navigation_objectives':len(navi),'models':[]}
    cases_path=ROOT/'generated/save-replay.tmp.json'
    runner=r"""const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./runtime_text');
const r=new RuntimeText(JSON.parse(fs.readFileSync(process.argv[1],'utf8')));
const cases=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),primary=process.argv[3];
for(const [source,ja,en] of cases){
 const p=r.render(source,'annotation');
 assert.equal(p.kind,'ruby',source);assert.ok(p.text.includes(ja),source+' => '+p.text);
 assert.equal(r.translate(source,'secondary').includes(ja),true);
 if(primary==='en')assert.ok(p.text.includes(en),source+' => '+p.text);
 for(const token of ['Lv.39','Lv.38','＜Nightmare＞'])if(source.includes(token))assert.ok(p.text.includes(token));
}
console.log(cases.length);
"""
    try:
        cases_path.write_text(json.dumps(fixtures,ensure_ascii=False),'utf-8')
        for primary in ('zh-Hans','en'):
            config={**read_config(),'primary':primary,'secondary':'ja','game_language':'zh-Hans'}
            start=time.perf_counter();model=load_model(entries,signature,config,game=GAME)
            elapsed=time.perf_counter()-start
            path=model_path(signature,config)
            run=subprocess.run(['node','-e',runner,str(path),str(cases_path),primary],cwd=ROOT,text=True,capture_output=True)
            if run.returncode:raise AssertionError(run.stderr)
            report['models'].append({'primary':primary,'secondary':'ja','prepare_seconds':round(elapsed,3),
                                     'cases':int(run.stdout),'exact_sources':len(model['pairs']),'path':path.name})
            print(json.dumps(report['models'][-1]),flush=True)
    finally:cases_path.unlink(missing_ok=True)
    (ROOT/'generated/save-localization-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')


if __name__=='__main__':main()
