import json
from pathlib import Path
import subprocess
import unittest
from menu_text import MenuTranslator

ROOT=Path(__file__).resolve().parents[1]

class RuntimeTextTests(unittest.TestCase):
    def test_native_resolver_matches_python_for_composites_and_dialogue(self):
        entries=[{'texts':{'zh-Hans':a,'ja':b}} for a,b in [
            ('妈妈从刚才开始','さっきからママが'),('就一直盯着海报看。','ポスターを見てるの。'),
            ('强化','強化'),('单体','単体'),('HP上限+%d','最大HP+%d'),('说明。','説明。'),
            ('勇猛果敢','勇猛果敢'),('HP','HP'),('选择%s？','%sを選択？'),('艾丝蒂尔','エステル'),
            ('甲\n乙','一二'),('保存','セーブ'),('保存','セーブする'),('第２章“大地翻腾”','２章「荒ぶる大地」')]]
        tr=MenuTranslator(entries,'zh-Hans','ja')
        sources=['<#E_0#M_0#B_0>妈妈从刚才开始\n就一直盯着海报看。',
                 '强化【<I299>单体：<c698>HP上限+20</C>】\n说明。','勇猛果敢',
                 'HP','选择艾丝蒂尔？','选择自定姓名？','甲\n乙','保存','药草','\n  单体\n','constructor','__proto__',
                 '第２章“大地翻腾”\u3000\u3000\u3000\u3000 ＜Nightmare＞','\u3000·艾丝蒂尔\u3000\u3000\u3000Lv.39']
        cases=[{'source':s,'mode':m,'expected':tr.translate(s,m)} for s in sources
               for m in ('annotation','primary','secondary')]
        runner="const fs=require('fs'),{RuntimeText}=require('./runtime_text.js');const data=JSON.parse(fs.readFileSync(0,'utf8'));const r=new RuntimeText(data.model);for(const c of data.cases)require('assert').strictEqual(r.translate(c.source,c.mode),c.expected);console.log(data.cases.length);"
        result=subprocess.run(['node','-e',runner],input=json.dumps({'model':tr.runtime_model(),'cases':cases}),
                              cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
