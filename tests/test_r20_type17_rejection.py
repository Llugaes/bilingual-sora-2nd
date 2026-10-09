"""Final ordinary formatter must retain a complete typed range rejection."""

import unittest

from sora_bilingual.localization.item_help_composition import _condition_parameter_entries
from sora_bilingual.localization.menu_text import MenuTranslator


class Type17FinalRejectionTests(unittest.TestCase):
    def translator(self):
        languages = ("en", "ja", "zh-Hans")
        templates = dict(
            zip(
                languages,
                (
                    "Damage dealt to enemies with %s +%d%%",
                    "「%s」状態の敵に与えるダメージ+%d％",
                    "对“%s”状态敌人造成的伤害+%d％",
                ),
            )
        )
        entries = [
            {
                "key": "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8",
                "texts": dict(zip(languages, (", ", "、", "、"))),
            },
            {
                "key": "table/t_itemhelp.tbl/sha256:condition/condition",
                "texts": dict(zip(languages, ("Seal", "封技", "封技"))),
            },
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:effect/name",
                "texts": templates,
            },
        ]
        bound = _condition_parameter_entries(
            entries,
            {"sha256:effect": {"name": templates}},
            {"sha256:effect": {"id": 1089, "parameter_types": (17,)}},
            languages,
        )
        return MenuTranslator(entries + bound, "ja", "zh-Hans", "en")

    def test_rejection_is_established_by_final_calls_and_keeps_valid_boundaries(self):
        for number in ("2147483648", "-2147483649", "9" * 100):
            for opening, closing in (("", ""), ("<c698>", "</C>")):
                source = opening + "Damage dealt to enemies with Seal +" + number + "%" + closing
                for modes in (
                    ("primary", "secondary", "annotation"),
                    ("annotation", "secondary", "primary"),
                ):
                    tr = self.translator()
                    for mode in modes:
                        self.assertEqual(tr.translate(source, mode), source)
                        self.assertEqual(
                            tr.render(source, mode), {"text": source, "layers": [], "kind": "plain"}
                        )
        for number in ("50", "2147483647", "-2147483648"):
            tr = self.translator()
            source = "Damage dealt to enemies with Seal +" + number + "%"
            self.assertEqual(
                tr.translate(source, "primary"), "「封技」状態の敵に与えるダメージ+" + number + "％"
            )
            self.assertEqual(
                tr.translate(source, "secondary"), "对“封技”状态敌人造成的伤害+" + number + "％"
            )
        self.assertIn(
            "UnprovenStatus",
            self.translator().translate(
                "Damage dealt to enemies with UnprovenStatus +50%", "primary"
            ),
        )


if __name__ == "__main__":
    unittest.main()
