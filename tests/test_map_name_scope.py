import unittest
from sora_bilingual.localization.menu_text import MenuTranslator


class MapNameScopeTests(unittest.TestCase):
    def test_area_and_spot_names_share_the_verified_map_scope_only(self):
        area = {
            "key": "table/t_mapjump.tbl/sha256:area/name",
            "texts": {"en": "Area", "ja": "地区"},
        }
        spot = {
            "key": "table/t_mapjump.tbl/MapJumpSpotData/sha256:spot/name",
            "texts": {"en": "Spot\nName", "ja": "地点\n名"},
        }
        viewer = {
            "key": "table/t_viewer.tbl/ViewerMapData/sha256:viewer/name",
            "texts": {"en": "Area", "ja": "別の地区名"},
        }
        tr = MenuTranslator([area, spot, viewer], "en", "ja", "en")
        self.assertNotIn("Area", tr.pairs)
        self.assertEqual(tr.scoped["map_spot"].pairs["Area"], ("Area", "地区"))
        self.assertEqual(tr.scoped["map_spot"].pairs["SpotName"], ("SpotName", "地点名"))

    def test_actual_area_spot_same_name_conflict_is_still_rejected(self):
        rows = [
            {"key": key, "texts": {"en": "Shared", "ja": target}}
            for key, target in (
                ("table/t_mapjump.tbl/sha256:area/name", "地区名"),
                ("table/t_mapjump.tbl/MapJumpSpotData/sha256:spot/name", "地点名"),
            )
        ]
        tr = MenuTranslator(rows, "en", "ja", "en")
        self.assertNotIn("Shared", tr.scoped["map_spot"].pairs)
