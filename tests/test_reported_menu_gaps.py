import json
from pathlib import Path
import unittest
from menu_text import MenuTranslator


@unittest.skipUnless(Path('generated/table-next.json').exists(),'local game catalog required')
class ReportedMenuGaps(unittest.TestCase):
    def test_overdrive_six_part_description_keeps_all_stats_and_translates_headers(self):
        entries=json.loads(Path('generated/table-next.json').read_text(encoding='utf-8'))['entries']
        tr=MenuTranslator(entries,'zh-Hans','ja')
        source='基本效果：解除＆免疫减益效果 命中率+100% 必杀率、魔法必杀率+30%\n特有效果：STR･DEF+12% ATS+6%'
        result=tr.translate(source)
        self.assertIn('デバフ解除＆無効',result)
        self.assertIn('独自効果',result)
        self.assertIn('STR･DEF+12%',result)

    def test_overdrive_name_from_screenshot(self):
        entries=json.loads(Path('generated/table-next.json').read_text(encoding='utf-8'))['entries']
        translated=MenuTranslator(entries,'zh-Hans','ja').translate('勇气之心')
        self.assertIn('<R>勇气之心</R',translated)

    def test_identical_cjk_names_still_show_the_secondary_language(self):
        tr=MenuTranslator([{'texts':{'zh-Hans':'勇猛果敢','ja':'勇猛果敢'}}],'zh-Hans','ja')
        self.assertEqual(tr.translate('勇猛果敢'),'<R>勇猛果敢</R勇猛果敢>')

    def test_support_counter_uses_its_own_table(self):
        entries=json.loads(Path('generated/table-next.json').read_text(encoding='utf-8'))['entries']
        tr=MenuTranslator(entries,'zh-Hans','ja')
        self.assertEqual(tr.dictionary('annotation')['\x02support\x00反击'],'<R>反击</R反撃>')
