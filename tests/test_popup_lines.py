import unittest

from tests.test_dynamic_producers import _build, _function, _items
from sora_bilingual.localization.resources import Called, Script
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.dynamic_producers import _popup_lines


class PopupLineTests(unittest.TestCase):
    def test_dynamic_or_unknown_operands_never_turn_into_static_text(self):
        head = (("int", 5), ("int", 8), ("int", 65535), ("string", "Title"))
        for tail in [(("int", 17),), (("int", 17), ("var", None)), (("int", 99),)]:
            self.assertIsNone(_popup_lines(Called(None, 3, head + tail)))
        mixed = head + (
            ("int", 10),
            ("string", "Got "),
            ("int", 17),
            ("int", 2622),
            ("string", "!"),
        )
        self.assertEqual(_popup_lines(Called(None, 3, mixed))[1], ("Title", None))

    def test_multiline_static_block_stays_together_with_unique_call_identity(self):
        scripts = {}
        for locale, first, second in [
            ("zh-Hans", "请合成", "结晶回路。"),
            ("en", "Please", "synthesize quartz."),
        ]:
            args = (
                ("int", 5),
                ("int", 8),
                ("int", 65535),
                ("string", first),
                ("int", 10),
                ("string", second),
                ("int", 10),
                ("int", 17),
                ("int", 3800),
            )
            calls = [Called(None, 3, args)]
            if locale == "en":
                calls.insert(0, Called("localized_unrelated_callback", 0, ()))
            scripts[locale] = {
                "script/scena/test.dat": Script({"Reward": _function("Reward", calls)})
            }
        entries, _ = _build(scripts, _items())
        lines = [e for e in entries if e.get("display_role") == "popup_line"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0]["texts"], {"zh-Hans": "请合成\n结晶回路。", "en": "Please\nsynthesize quartz."}
        )

    def test_static_line_survives_dynamic_item_list_and_split_color_literal(self):
        scripts = {}
        for locale, text in [
            ("zh-Hans", "已取得礼服！"),
            ("ja", "衣装を手に入れた！"),
            ("en", "Obtained a costume!"),
        ]:
            args = [("int", 5), ("int", 8), ("int", 65535), ("int", 16)]
            args += (
                [("string", "<C1>"), ("string", text)]
                if locale == "zh-Hans"
                else [("string", "<C1>" + text)]
            )
            args += [
                ("int", 10),
                ("int", 17),
                ("int", 2622),
                ("int", 10),
                ("int", 17),
                ("int", 2623),
            ]
            scripts[locale] = {
                "script/scena/test.dat": Script(
                    {"Reward": _function("Reward", [Called(None, 3, tuple(args))])}
                )
            }
        entries, _audit = _build(scripts, _items())
        lines = [e for e in entries if e.get("display_role") == "popup_line"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["texts"]["en"], "<C1>Obtained a costume!")
        self.assertEqual(lines[0]["texts"]["zh-Hans"], "<C1>已取得礼服！")
        # The original split argument still exists in the raw catalogue with
        # only CJK locales. It must not erase the complete reconstructed line.
        fragment = {
            "key": "script/test/called/0/arg/5/alignment/split",
            "texts": {"zh-Hans": "已取得礼服！"},
        }
        tr = MenuTranslator([*lines, fragment], "zh-Hans", "en", "zh-Hans")
        self.assertEqual(tr.translate("已取得礼服！", "secondary"), "<C1>Obtained a costume!")
        # Changing the item ID changes the physical call contract; it cannot
        # pair a translated line merely because the function name is equal.
        f = scripts["en"]["script/scena/test.dat"].functions["Reward"]
        args = list(f.called[0].args)
        args[-1] = ("int", 999)
        scripts["en"]["script/scena/test.dat"] = Script(
            {"Reward": _function("Reward", [Called(None, 3, tuple(args))])}
        )
        entries, _audit = _build(scripts, _items())
        line = next(
            e for e in entries if e.get("display_role") == "popup_line" and "zh-Hans" in e["texts"]
        )
        self.assertNotIn("en", line["texts"])


if __name__ == "__main__":
    unittest.main()
