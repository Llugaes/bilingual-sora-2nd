import struct
import unittest

from sora_bilingual.localization.dynamic_identity import (
    _producer_models,
    _resolved_tokens,
    _SUFFIX_HELPER_SHAPE,
)


class DynamicIdentityTests(unittest.TestCase):
    def test_suffix_only_helper_uses_its_own_argument_count(self):
        values = (0xC0011000, 0x4000017E)
        data = bytearray(30)
        positions = [0, 12, 18, 24]
        for position, value in zip(positions[1:3], values):
            data[position : position + 2] = b"\0\4"
            struct.pack_into("<I", data, position + 2, value)
        code = [
            ("prepare-local", 4),
            ("push", "string"),
            ("push", "int", 382),
            ("local-call", "ITEM_ADD_MESSAGE_TK"),
        ]
        self.assertEqual(
            _resolved_tokens(bytes(data), positions, code, 3, (1, 2), _SUFFIX_HELPER_SHAPE),
            [0x4000FFFF, 0x40000010, 0x40000011, values[1], values[0]],
        )

    def test_three_argument_talk_frame_uses_the_same_relative_slots(self):
        values = (0xC0011000, 0xC0012000, 0x4000017E)
        positions = [0, 12, 18, 24, 30]
        data = bytearray(36)
        for position, value in zip(positions[1:4], values):
            data[position : position + 2] = b"\0\4"
            struct.pack_into("<I", data, position + 2, value)
        code = [
            ("prepare-local", 5),
            ("push", "string"),
            ("push", "string"),
            ("push", "int", 382),
            ("local-call", "ITEM_ADD_MESSAGE2_TK"),
        ]
        self.assertEqual(
            _resolved_tokens(bytes(data), positions, code, 4, (1, 2, 2)),
            [0x4000FFFF, 0x40000010, values[1], 0x40000011, values[2], values[0]],
        )

    def test_slot_copies_follow_the_current_stack_top(self):
        # This is the raw outer local-call sequence for an item helper.  Its
        # values make the slot(2,5) adjustment observable after three pushes.
        values = (9, 0xC016AE36, 0xC016AE3A, 220)
        positions = (0, 6, 12, 18, 24, 30)
        data = bytearray(40)
        for position, value in zip(positions[1:5], values):
            data[position : position + 2] = b"\0\4"
            struct.pack_into("<I", data, position + 2, value if value != 220 else 0x400000DC)
        code = [
            ("prepare-local", 6),
            ("push", "int", 9),
            ("push", "string"),
            ("push", "string"),
            ("push", "int", 220),
            ("local-call", "ITEM_ADD_MESSAGE2_EV"),
        ]
        self.assertEqual(
            _resolved_tokens(bytes(data), list(positions), code, 5, (1, 2, 2, 9)),
            [0x4000FFFF, 0x40000010, 0xC016AE3A, 0x40000011, 0x400000DC, 0xC016AE36],
        )

        for declaration in ((1, 2, 2), (1, 2, 1, 9), (1, 2, 5, 9)):
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                _resolved_tokens(bytes(data), list(positions), code, 5, declaration)
        # A surrounding function's values must never stand in for a local frame.
        code[0] = ("line",)
        with self.assertRaises(ValueError):
            _resolved_tokens(bytes(data), list(positions), code, 5, (1, 2, 2, 9))

    def test_each_source_locale_gets_a_complete_numeric_validation_model(self):
        entry = {
            "key": "dynamic/script/scena/example.dat/F/called/1/item/220",
            "texts": {
                "zh-Hans": "拿到了<C0><I%d></C><C5>钥匙</C>。",
                "en": "Received <C0><I%d></C><C5>Key</C>.",
                "ja": "<C0><I%d></C><C5>鍵</C>を受け取った。",
            },
            "dynamic_producer": {
                "numbers": {
                    "zh-Hans": ["ascii"],
                    "en": ["ascii"],
                    "ja": ["ascii"],
                }
            },
        }
        rows = _producer_models(entry, "zh-Hans", "en")
        self.assertEqual(set(rows), {"zh-Hans", "en", "ja"})
        row = rows["zh-Hans"]
        self.assertTrue(row["sourcePattern"].startswith("^(?:"))
        self.assertEqual(len(row["model"]["producer_numeric"]), 1)


if __name__ == "__main__":
    unittest.main()
