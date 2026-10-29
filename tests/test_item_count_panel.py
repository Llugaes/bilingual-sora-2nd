from collections import Counter
from dataclasses import replace
import unittest

from sora_bilingual.localization.resources import Called, Function, Script
from sora_bilingual.localization.item_count_panel import HELPER_CODE, ITEM_IDS, panel_contract


def fixture(extra_literals=True):
    args = [("int", 5), ("int", 8), ("int", 65535), ("int", 16), ("string", "Owned"), ("int", 10)]
    slots = {}
    for number, ident in enumerate(ITEM_IDS):
        args.extend((("int", 17), ("int", ident), ("string", "  "), ("int", 18), ("call", None)))
        slots[len(args) - 1] = ident
        if extra_literals:
            args.append(("string", ""))
        if number < 6:
            args.append(("int", 10))
    calls = (Called(None, 3, tuple(args)),) + tuple(
        Called("count", 0, (("int", i),)) for i in ITEM_IDS
    )
    code, strings = [], []
    for slot in range(len(args) - 1, 1, -1):
        arg = args[slot]
        if slot in slots:
            code.extend(
                (
                    ("prepare-local", len(code) + 3),
                    ("push", "int", slots[slot]),
                    ("local-call", "count"),
                    ("byte", 9, 0),
                )
            )
        elif arg[0] == "string":
            strings.append(arg[1])
            code.append(("push", "string"))
        else:
            code.append(("push", *arg))
    code.extend((("system-call", 5, 8, len(args) - 2), ("pop", len(args) - 2), ("return",)))
    return Script(
        {
            "Panel": Function("Panel", 0, (), calls, tuple(code), tuple(strings)),
            "count": Function("count", 1, (1,), (), HELPER_CODE, ()),
        }
    )


class ItemCountPanelTests(unittest.TestCase):
    def test_alignment_uses_unique_complete_program_and_keeps_each_locale_call_id(self):
        from types import SimpleNamespace
        from sora_bilingual.localization.dynamic_producers import _count_panel_entries

        proof = panel_contract(fixture(), "Panel", 0)
        scripts = {
            lang: {
                "script/scena/test.dat": SimpleNamespace(
                    functions={"Panel": SimpleNamespace(count_panels=((called, proof),))}
                )
            }
            for lang, called in (("ja", 1), ("zh-Hans", 3))
        }
        items = {lang: {i: (f"{lang}-{i}", 0) for i in ITEM_IDS} for lang in scripts}
        audit = {"counters": Counter(), "diagnostics": []}
        rows = _count_panel_entries(scripts, items, audit)
        self.assertEqual(rows[0]["called_ids"], {"ja": 1, "zh-Hans": 3})
        scripts["ja"]["script/scena/test.dat"].functions["Panel"].count_panels += ((4, proof),)
        self.assertEqual(_count_panel_entries(scripts, items, audit), [])
        self.assertEqual(audit["counters"]["count_panel_ambiguous_alignment"], 1)

    def test_contract_tracks_all_seven_values_across_optional_literal_chunks(self):
        for extra in (False, True):
            proof = panel_contract(fixture(extra), "Panel", 0)
            self.assertIsNotNone(proof)
            self.assertEqual(len(proof["slots"]), 7)
            self.assertEqual(
                [p[1] for p in proof["parts"] if isinstance(p, tuple) and p[0] == "item"],
                list(ITEM_IDS),
            )

    def test_unknown_helpers_reordered_ids_and_branch_entry_are_denied(self):
        script = fixture()
        original = script.functions["Panel"]
        for replacement in (
            replace(original, code_shape=original.code_shape + (("branch", 11, 2),)),
            replace(
                original,
                called=original.called[:1]
                + (replace(original.called[1], args=(("int", 311),)),)
                + original.called[2:],
            ),
            replace(
                original,
                code_shape=tuple(
                    ("byte", 9, 1) if op == ("byte", 9, 0) else op for op in original.code_shape
                ),
            ),
        ):
            self.assertIsNone(
                panel_contract(Script({**script.functions, "Panel": replacement}), "Panel", 0)
            )
        bad_helper = replace(script.functions["count"], code_shape=(("return",),))
        self.assertIsNone(
            panel_contract(Script({**script.functions, "count": bad_helper}), "Panel", 0)
        )

    def test_complete_panel_compiles_into_one_fourteen_slot_translation(self):
        from sora_bilingual.localization.dynamic_producers import _count_panel_entries
        from sora_bilingual.localization.menu_text import MenuTranslator

        scripts = {
            lang: {"script/scena/test.dat": fixture(lang == "zh-Hans")}
            for lang in ("ja", "zh-Hans")
        }
        items = {lang: {i: (f"{lang}-{i}", 0) for i in ITEM_IDS} for lang in scripts}
        rows = _count_panel_entries(scripts, items, {"counters": Counter(), "diagnostics": []})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["texts"]["ja"].count("%d"), 14)
        values = tuple(v for number in range(7) for v in (42 + number, number * 19))
        source = row["texts"]["zh-Hans"] % values
        self.assertEqual(
            MenuTranslator(rows, "zh-Hans", "ja", "zh-Hans", True).producer_pair(source),
            (source, row["texts"]["ja"] % values),
        )


if __name__ == "__main__":
    unittest.main()
