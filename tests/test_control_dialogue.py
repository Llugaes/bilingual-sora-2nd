from collections import Counter
from dataclasses import replace
import unittest

from sora_bilingual.localization.control_dialogue import control_dialogue_contract
from sora_bilingual.localization.resources import (
    Called,
    Function,
    align_functions,
    assembled_dialogue,
    _aligned_call_map,
)


def scene(body="Literal body", second="<K4>"):
    calls = (
        Called("Flag", 0, (("int", 7),)),
        Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 0),
                ("int", 1),
                ("string", "<#E_9>"),
                ("var", None),
                ("string", body),
            ),
        ),
    )
    code = (
        ("push", "special", 0),
        ("push", "string"),
        ("slot", 5, 1),
        ("prepare-local", 6),
        ("push", "int", 7),
        ("local-call", "Flag"),
        ("byte", 9, 0),
        ("branch", 15, 11),
        ("push", "string"),
        ("slot", 5, 1),
        ("branch", 11, 13),
        ("push", "string"),
        ("slot", 5, 1),
        ("push", "string"),
        ("slot", 2, 2),
        ("push", "string"),
        ("push", "int", 1),
        ("system-call", 5, 0, 4),
        ("pop", 4),
        ("pop", 1),
        ("return",),
    )
    return Function("Scene", 0, (), calls, code, ("<K>", "<K3>", second, body, "<#E_9>"))


class ControlDialogueTests(unittest.TestCase):
    def test_optional_literal_helper_defaults_require_resource_declaration(self):
        original = scene()
        # Executable helper call supplies an optional default omitted from its
        # metadata. Its literal producer/return frame and declaration agree.
        call = replace(original.called[0], args=())
        with_default = replace(
            original, called=(call, original.called[1]), local_arg_types=(("Flag", (9,)),)
        )
        self.assertIsNotNone(control_dialogue_contract(with_default, 1))
        self.assertIsNone(control_dialogue_contract(replace(with_default, local_arg_types=()), 1))
        self.assertIsNone(
            control_dialogue_contract(replace(with_default, local_arg_types=(("Flag", (1,)),)), 1)
        )

    def test_duplicate_metadata_needs_every_leaf_producer_to_match(self):
        original = scene()
        code = original.code_shape[:19] + original.code_shape[13:19] + original.code_shape[19:]
        duplicate = replace(
            original,
            called=original.called + (original.called[1],),
            code_shape=code,
            code_strings=original.code_strings + original.code_strings[-2:],
        )
        first = control_dialogue_contract(duplicate, 1)
        second = control_dialogue_contract(duplicate, 2)
        self.assertEqual(first["code_index"], 17)
        self.assertEqual(second["code_index"], 23)
        self.assertEqual(first["producer_identity"], "complete_ordered_dialogue_producers")
        damaged = list(code)
        damaged[22] = ("push", "int", 99)
        rejected = {}
        self.assertIsNone(
            control_dialogue_contract(
                replace(duplicate, code_shape=tuple(damaged)), 1, rejection=rejected
            )
        )
        self.assertEqual(rejected["reason"], "duplicate_call_without_ordered_producer_proof")

    def test_dynamic_wrapping_keeps_order_but_never_publishes_unproved_payload(self):
        en = scene()
        ja_call = replace(en.called[1], args=en.called[1].args + (("int", 10), ("string", "続き")))
        tail = Called("wait_prompt", 0, ())
        en = replace(en, called=en.called + (tail,))
        ja = replace(en, called=(en.called[0], ja_call, tail))
        self.assertEqual(_aligned_call_map(en, ja), {0: 0, 2: 2})
        for args in (
            ja_call.args[:2] + (("int", 99),) + ja_call.args[3:],
            ja_call.args[:3] + (("var", None),) + ja_call.args[3:4] + ja_call.args[5:],
            ja_call.args[:4] + (("call", None),) + ja_call.args[5:],
        ):
            changed = replace(ja, called=(ja.called[0], replace(ja_call, args=args), tail))
            self.assertNotIn(2, _aligned_call_map(en, changed))

    def test_literal_empty_control_is_proven_instead_of_ignoring_a_variable(self):
        contract = control_dialogue_contract(scene(second=""), 1)
        self.assertEqual(contract["variants"][""], "<#E_9>Literal body")

    def test_unreachable_helper_does_not_relax_reaching_path_proof(self):
        original = scene()
        # Both flag outcomes remain possible. One leaves before the read;
        # only the other contributes its local definition to this contract.
        code = list(original.code_shape)
        code[9] = ("unsupported-helper",)
        code[10] = ("branch", 11, 19)
        unreachable = replace(original, code_shape=tuple(code))
        self.assertEqual(
            control_dialogue_contract(unreachable, 1)["variants"],
            {"<K4>": "<#E_9><K4>Literal body"},
        )
        code[10] = original.code_shape[10]
        self.assertIsNone(control_dialogue_contract(replace(original, code_shape=tuple(code)), 1))

    def test_control_local_survives_a_long_region_before_the_dialogue(self):
        original = scene()
        extra = (("line",),) * 140
        code = tuple(
            (*op[:-1], op[-1] + len(extra))
            if op[0] in ("branch", "prepare-local") and op[-1] >= 13
            else op
            for op in original.code_shape
        )
        longer = replace(original, code_shape=code[:13] + extra + code[13:])
        self.assertEqual(
            control_dialogue_contract(longer, 1)["variants"],
            control_dialogue_contract(original, 1)["variants"],
        )

    def test_every_branch_value_is_retained_in_complete_outputs(self):
        f = scene()
        self.assertIsNone(assembled_dialogue(f.called[1]))
        contract = control_dialogue_contract(f, 1)
        self.assertEqual(contract["code_index"], 17)
        self.assertEqual(
            contract["variants"],
            {"<K3>": "<#E_9><K3>Literal body", "<K4>": "<#E_9><K4>Literal body"},
        )

    def test_unknown_visible_or_uninitialized_dynamic_values_are_rejected(self):
        for f in (
            scene(second="runtime actor"),
            scene(second="<UNKNOWN>"),
            replace(scene(), code_shape=()),
            replace(
                scene(),
                code_shape=scene().code_shape[:11]
                + (("push", "special", 0),)
                + scene().code_shape[12:],
            ),
            replace(scene(), called=scene().called + (scene().called[1],)),
        ):
            with self.subTest(f=f):
                self.assertIsNone(control_dialogue_contract(f, 1))

    def test_dynamic_control_calls_are_cross_aligned_with_physical_call_ids(self):
        audit = {"counters": Counter(), "diagnostics": []}
        entries = align_functions(
            "script/scene.dat", "Scene", {"en": scene("Literal body"), "ja": scene("原文")}, audit
        )
        controls = [e for e in entries if e.get("control_dialogue")]
        self.assertEqual(len(controls), 2)
        self.assertTrue(all(e["called_ids"] == {"en": 1, "ja": 1} for e in controls))
        self.assertEqual({e["texts"]["ja"] for e in controls}, {"<#E_9><K3>原文", "<#E_9><K4>原文"})


if __name__ == "__main__":
    unittest.main()
