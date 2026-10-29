from collections import Counter
from dataclasses import replace
import unittest

from sora_bilingual.localization.resources import (
    Called,
    Function,
    _aligned_call_map,
    align_functions,
)
from sora_bilingual.localization.branch_dialogue import dispatch_regions


def fixture(selectors, language):
    code = [("slot", 2, 1), ("byte", 10, 0)]
    for selector in selectors:
        code.extend((("byte", 9, 0), ("push", "int", selector), ("op", 21), ("branch", 14, 0)))
    default = len(code)
    code.append(("branch", 11, 0))
    called, strings, exits = [], [], []
    for number, selector in enumerate(selectors):
        code[2 + number * 4 + 3] = ("branch", 14, len(code))
        source = f"{language} case {selector}"
        called.append(
            Called(None, 3, (("int", 5), ("int", 19), ("int", 12100), ("string", source)))
        )
        strings.append(source)
        code.extend(
            (("push", "string"), ("push", "int", 12100), ("system-call", 5, 19, 2), ("pop", 2))
        )
        exits.append(len(code))
        code.append(("branch", 11, 0))
    for at in [default, *exits]:
        code[at] = ("branch", 11, len(code))
    code.append(("return",))
    return Function("NPC", 0, (1,), tuple(called), tuple(code), tuple(strings))


class BranchDialogueTests(unittest.TestCase):
    def test_inserted_dialogue_branch_does_not_shift_later_translation(self):
        zh, ja = fixture([10, 20, 30], "zh"), fixture([10, 30], "ja")
        self.assertEqual(_aligned_call_map(zh, ja), {0: 0, 2: 1})
        rows = align_functions(
            "script/scena/test.dat",
            "NPC",
            {"zh-Hans": zh, "ja": ja},
            {"counters": Counter(), "diagnostics": []},
        )
        pairs = [r for r in rows if r.get("display_role") == "dialogue"]
        self.assertTrue(
            any(r["texts"] == {"ja": "ja case 30", "zh-Hans": "zh case 30"} for r in pairs)
        )
        self.assertFalse(any("zh case 20" in r["texts"].values() for r in pairs))

    def test_equal_call_shapes_with_changed_selectors_do_not_form_a_whole_function_pair(self):
        a, b = fixture([10, 20], "zh"), fixture([10, 30], "ja")
        self.assertNotEqual(a.called_sequence_shape(), b.called_sequence_shape())
        self.assertNotEqual(a.dialogue_sequence_shape(), b.dialogue_sequence_shape())
        self.assertEqual(_aligned_call_map(a, b), {0: 0})

    def test_ambiguous_or_escaping_case_programs_are_not_proven(self):
        original = fixture([10, 20], "zh")
        for program in (
            tuple(("branch", 14, 12) if i == 5 else op for i, op in enumerate(original.code_shape)),
            tuple(
                ("push", "int", 10) if i == 7 else op for i, op in enumerate(original.code_shape)
            ),
            original.code_shape[:-1] + (("branch", 11, 12), ("return",)),
            original.code_shape[:10],
        ):
            self.assertIsNone(dispatch_regions(replace(original, code_shape=program)))


if __name__ == "__main__":
    unittest.main()
