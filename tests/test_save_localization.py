import struct
import unittest

from menu_tables import read_section, SCHEMAS
from menu_text import MenuTranslator
from resources import FormatError


def navi(rows):
    data=bytearray(56*len(rows))
    for i,(text,start,end) in enumerate(rows):
        at=i*56
        struct.pack_into('<Q',data,at,2)
        struct.pack_into('<Q',data,at+8,len(data));data.extend(text.encode()+b'\0')
        for off,value in ((24,start),(40,end)):
            struct.pack_into('<QQ',data,at+off,len(data),1)
            data.extend(struct.pack('<H',value))
    return data


class SaveLocalizationTests(unittest.TestCase):
    def test_level_prefix_comes_from_requested_locales(self):
        tr=MenuTranslator([
            {'key':'table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL','texts':{'fr':'Niv.','de':'St. ','es':'Nv.'}},
            {'texts':{'fr':'Nom','de':'Name','es':'Nombre'}}], 'de','es','fr')
        self.assertEqual(tr.translate(' ·Nom  Niv.39','primary'),' ·Name  St. 39')
        self.assertEqual(tr.translate(' ·Nom  Niv.39','secondary'),' ·Nombre  Nv.39')
        self.assertEqual(tr.translate('Unknown Name','primary'),'Unknown Name')

    def test_navigation_uses_condition_ids_not_chapter_or_row_order(self):
        a=navi([('准备搭船',18081,18086),('交谈',18086,18090)])
        b=navi([('Talk',18086,18090),('Board',18081,18086)])
        def read(data):return read_section(data,('NaviText',0,56,2),SCHEMAS['NaviText'],112)
        left,right=read(a),read(b)
        self.assertEqual(len(left),2)
        self.assertEqual({(v[0]['title'],right[k][0]['title']) for k,v in left.items()},
                         {('准备搭船','Board'),('交谈','Talk')})
        struct.pack_into('<Q',a,32,1000000)
        with self.assertRaises(FormatError):read(a)

    def test_character_name_table_survives_incomplete_voice_records(self):
        entries=[{'key':'table/t_name.tbl/id/name','texts':{'zh-Hans':'艾丝蒂尔','ja':'エステル','en':'Estelle'}},
                 {'key':'script/x/voice','texts':{'zh-Hans':'艾丝蒂尔','ja':'エステル'}}]
        tr=MenuTranslator(entries,'en','ja')
        self.assertEqual(tr.translate('艾丝蒂尔','primary'),'Estelle')
        self.assertEqual(tr.translate('艾丝蒂尔','secondary'),'エステル')
        self.assertEqual(tr.translate('艾丝蒂尔的日记','primary'),'艾丝蒂尔的日记')

    def test_save_heading_and_party_keep_difficulty_and_levels(self):
        tr=MenuTranslator([{'texts':{'zh-Hans':'第２章“大地翻腾”','ja':'２章「荒ぶる大地」'}},
                           {'texts':{'zh-Hans':'艾丝蒂尔','ja':'エステル'}}],'zh-Hans','ja')
        self.assertEqual(tr.translate('第２章“大地翻腾”\u3000\u3000\u3000\u3000 ＜Nightmare＞','secondary'),
                         '２章「荒ぶる大地」\u3000\u3000\u3000\u3000 ＜Nightmare＞')
        self.assertEqual(tr.translate('\u3000·艾丝蒂尔\u3000\u3000\u3000Lv.39','secondary'),
                         '\u3000·エステル\u3000\u3000\u3000Lv.39')


if __name__=='__main__':unittest.main()
