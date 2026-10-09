import unittest
from sora_bilingual.localization.menu_text import MenuTranslator


def contract(names):
    return {
        "key": "table/t_itemhelp.tbl/generated/condition_list/98",
        "texts": {},
        "condition_list_contract": {
            "id": 98,
            "parameter_types": [10],
            "templates": {"en": "Role %s", "ja": "役%s", "zh-Hans": "状态%s"},
            "links": {"en": "/", "ja": "･", "zh-Hans": "･"},
            "percent": {"en": "%d%%", "ja": "%d％", "zh-Hans": "%d％"},
            "names": names,
        },
    }


class ConditionListContractTests(unittest.TestCase):
    def test_unrelated_item_homograph_stays_ambiguous_but_complete_condition_role_resolves(self):
        names = [{"en": "A", "ja": "甲", "zh-Hans": "甲"}, {"en": "B", "ja": "乙", "zh-Hans": "乙"}]
        entries = [
            contract(names),
            {"key": "table/t_condition_info.tbl/sha256:a/name", "texts": names[0]},
            {
                "key": "table/t_item.tbl/sha256:b/name",
                "texts": {"en": "A", "ja": "物品", "zh-Hans": "道具"},
            },
        ]
        tr = MenuTranslator(entries, "zh-Hans", "ja", "en")
        # The complete production model has the condition/item homograph in
        # this gate; a tiny fixture cannot reproduce the catalog's admission.
        tr.ambiguous_display.add("A")
        self.assertEqual(
            tr.condition_list_pair("<c698>Role A/B 100%</C>"),
            ("<c698>状态甲･乙 100％</C>", "<c698>役甲･乙 100％</C>"),
        )

    def test_role_local_conflict_and_missing_target_are_rejected(self):
        for names in (
            [{"en": "A", "ja": "甲", "zh-Hans": "甲"}, {"en": "A", "ja": "乙", "zh-Hans": "乙"}],
            [{"en": "A", "ja": "甲"}],
        ):
            tr = MenuTranslator([contract(names)], "zh-Hans", "ja", "en")
            self.assertIsNone(tr.condition_list_pair("Role A 100%"))

    def test_whole_constructor_ambiguity_still_refuses_translation(self):
        tr = MenuTranslator(
            [contract([{"en": "A", "ja": "甲", "zh-Hans": "甲"}])], "zh-Hans", "ja", "en"
        )
        tr.ambiguous_display.add("Role A 100%")
        self.assertIsNone(tr.condition_list_pair("<c698>Role A 100%</C>"))
