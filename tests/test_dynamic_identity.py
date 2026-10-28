import struct
import unittest
from unittest.mock import MagicMock, patch

from sora_bilingual.localization.dynamic_identity import (
    _producer_models,
    _resolved_tokens,
    _SUFFIX_HELPER_SHAPE,
    _literal_sites,
)


class DynamicIdentityTests(unittest.TestCase):
    def test_literal_sites_require_metadata_tokens_complete_stack_and_entry(self):
        # One real-layout called descriptor and its reverse literal pushes.
        tokens = [0x4000FFFF, 0xC00000C8, 0x40000011, 0x400000DC, 0xC00000D0]
        for command in (0, 6, 8):
            data = bytearray(512)
            struct.pack_into("<4sIIIII", data, 0, b"#scp", 24, 1, 56, 0, 0)
            struct.pack_into("<II", data, 40, 1, 56)
            struct.pack_into("<I", data, 52, 0xC00000B4)
            data[180:185] = b"Talk\0"
            data[200:204] = b"Get\0"
            data[208:210] = b".\0"
            raw = [0x40000005, 0x40000000 | command, *tokens]
            struct.pack_into("<IHHI", data, 56, 0, 3, len(raw), 68)
            for i, value in enumerate(raw):
                struct.pack_into("<II", data, 68 + i * 8, value, 0)
            positions = [256 + i * 6 for i in range(len(tokens) + 2)]
            code = []
            for position, value in zip(positions, reversed(tokens)):
                data[position : position + 2] = b"\0\4"
                struct.pack_into("<I", data, position + 2, value)
                code.append(
                    ("push", "string") if value >> 30 == 3 else ("push", "int", value & 0x1FFFFFFF)
                )
            code += [("system-call", 5, command, len(tokens)), ("pop", len(tokens))]
            result = (command, tokens, [positions[-2] + 4])
            self.assertEqual(_literal_sites(bytes(data), "Talk", 0, positions, code), result)
            for invalid in (
                [*code[:-1], ("pop", 1)],
                [*code, ("branch", 11, 2)],
                [("slot", 2, 1), *code[1:]],
            ):
                with self.assertRaises(ValueError):
                    _literal_sites(bytes(data), "Talk", 0, positions, invalid)
            changed = bytearray(data)
            struct.pack_into("<I", changed, positions[0] + 2, 0xC00000C8)
            with self.assertRaises(ValueError):
                _literal_sites(bytes(changed), "Talk", 0, positions, code)
            struct.pack_into("<I", data, 68 + 4 * 8 + 4, 1)
            with self.assertRaisesRegex(ValueError, "dynamic"):
                _literal_sites(bytes(data), "Talk", 0, positions, code)

    def test_cache_permission_error_must_not_become_an_empty_successful_index(self):
        from sora_bilingual.localization.dynamic_identity import compile_dynamic_identities

        archive = MagicMock()
        archive.__enter__.return_value = archive
        archive.read.return_value = b"owned fixture"
        entry = {
            "key": "dynamic/script/scena/example.dat/F/called/0/item/220",
            "texts": {"en": "source", "ja": "primary", "zh-Hans": "secondary"},
            "producer_origin": {
                "family": "item_add_message",
                "signature": {"path": "script/scena/example.dat", "function": "F", "called": 0},
            },
        }
        with (
            patch("sora_bilingual.localization.dynamic_identity.FpacArchive", return_value=archive),
            patch(
                "sora_bilingual.localization.dynamic_identity._logical_script_entries",
                return_value={"script/scena/example.dat": "owned"},
            ),
            patch(
                "sora_bilingual.localization.dynamic_identity._producer_models",
                return_value={"en": {"model": {}, "sourcePattern": "^source$"}},
            ),
            patch(
                "sora_bilingual.localization.language_cache.notification_metadata",
                side_effect=PermissionError("owned denial"),
            ) as metadata,
        ):
            with self.assertRaisesRegex(PermissionError, "owned denial"):
                compile_dynamic_identities("owned-project-fixture", [entry], "ja", "zh-Hans", "en")
            self.assertEqual(metadata.call_count, 1)

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
