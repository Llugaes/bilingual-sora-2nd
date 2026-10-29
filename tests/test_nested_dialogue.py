import unittest
from types import SimpleNamespace

from sora_bilingual.localization.control_dialogue import control_dialogue_contract
from sora_bilingual.localization.resources import Called


def fixture(domain=(0,)):
    outer = Called(
        None,
        3,
        (
            ("int", 5),
            ("int", 0),
            ("int", 0),
            ("string", "<#E_0>"),
            ("call", None),
            ("string", "Full body"),
        ),
    )
    action = Called(
        None, 3, (("int", 1), ("int", 47), ("int", 0), ("int", 2), ("string", "Animation"))
    )
    return SimpleNamespace(
        called=(Called("wait_prompt", 0, ()), outer, action),
        code_shape=(
            ("prepare-local", 2),
            ("local-call", "wait_prompt"),
            ("push", "string"),
            ("push", "string"),
            ("push", "int", 2),
            ("push", "int", 0),
            ("system-call", 1, 47, 3),
            ("pop", 3),
            ("byte", 9, 0),
            ("push", "string"),
            ("push", "int", 0),
            ("system-call", 5, 0, 4),
            ("pop", 4),
            ("return",),
        ),
        code_strings=("Full body", "Animation", "<#E_0>"),
        local_return_values=(("wait_prompt", domain),),
    )


class NestedDialogueTests(unittest.TestCase):
    def test_unknown_write_and_branch_into_arguments_are_denied(self):
        for extra in (("byte", 39, 0), ("branch", 11, 7)):
            f = fixture()
            f.code_shape = (*f.code_shape[:2], extra, *f.code_shape[2:])
            self.assertIsNone(control_dialogue_contract(f, 1))

    def test_helper_names_do_not_authorize_a_changed_return_program(self):
        from sora_bilingual.localization.nested_dialogue import helper_return_values

        helper = SimpleNamespace(
            arg_types=(), code_shape=(("push", "special", 0), ("byte", 10, 0), ("return",))
        )
        self.assertEqual(helper_return_values({"any_name": helper}), {"any_name": (0,)})
        for code in (
            (("push", "special", 0), ("byte", 10, 1), ("return",)),
            (("push", "special", 0), ("byte", 10, 0), ("return",), ("branch", 11, 2)),
            (("push", "int", 0), ("byte", 10, 0), ("return",)),
        ):
            helper.code_shape = code
            self.assertEqual(helper_return_values({"wait_prompt": helper}), {})

    def test_known_void_result_preserves_full_body(self):
        result = control_dialogue_contract(fixture(), 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["variants"], {"": "<#E_0>Full body"})
        self.assertEqual(result["raw_values"], {"": [0]})

    def test_unknown_return_cannot_be_erased(self):
        self.assertIsNone(control_dialogue_contract(fixture(()), 1))

    def test_item_opcode_return_cannot_be_erased(self):
        self.assertIsNone(control_dialogue_contract(fixture((0x40000011,)), 1))

    def test_boolean_return_is_finite_and_non_display(self):
        result = control_dialogue_contract(fixture((0x40000000, 0x40000001)), 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["raw_values"][""], [0x40000000, 0x40000001])


if __name__ == "__main__":
    unittest.main()
