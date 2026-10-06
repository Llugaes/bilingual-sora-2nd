"""Relocation must preserve the data and import dependencies a helper consumes."""

import hashlib
import struct
import unittest

import pefile

from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
from sora_bilingual.game.native_contracts import resolve_native_contracts
from test_native_contracts import _offset, _write_rel32, relinked_helper_fixture


class NativeReferenceSafetyTests(unittest.TestCase):
    def fixture(self, table=0x2040):
        raw, contract = relinked_helper_fixture(table_rva=table)
        data = bytes(range(32))
        raw[_offset(table) : _offset(table) + len(data)] = data
        helper = contract["functions"]["root"]["variants"][0]["continuations"][0]["template"]
        helper["data_refs"] = [
            {
                "displacement": [3, 4],
                "encoding": "rva32",
                "size": len(data),
                "alignment": 4,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ]
        return raw, contract

    def resolve(self, raw, contract):
        with pefile.PE(data=raw, fast_load=True) as pe:
            return resolve_native_contracts(pe, contract)

    def test_identical_data_can_move_with_both_reviewed_readers(self):
        _, contract = self.fixture()
        moved, _ = self.fixture(0x2080)
        self.assertEqual(self.resolve(moved, contract)["functions"], {"root": 0x1000})

    def test_equal_references_do_not_allow_corrupt_data(self):
        raw, contract = self.fixture()
        raw[_offset(0x2044)] ^= 1
        with self.assertRaises(ExecutableCompatibilityError) as caught:
            self.resolve(raw, contract)
        self.assertIn("data_refs[0]", caught.exception.details[0]["path"])

    def test_both_references_to_unmapped_data_are_rejected(self):
        raw, contract = self.fixture()
        struct.pack_into("<I", raw, _offset(0x1043), 0x8000)
        _write_rel32(raw, 0x1083, 0x1087, 0x8000)
        with self.assertRaises(ExecutableCompatibilityError):
            self.resolve(raw, contract)

    def test_import_slot_with_conflicting_descriptors_is_rejected(self):
        raw, contract = self.fixture()
        # Two DLL descriptors claim the same IAT slot; picking the first
        # name would accept an import the loader can bind differently.
        struct.pack_into("<5I", raw, _offset(0x2314), 0x23A0, 0, 0, 0x2360, 0x2380)
        raw[_offset(0x2360) : _offset(0x2360) + 10] = b"USER32.dll"
        struct.pack_into("<Q", raw, _offset(0x23A0), 0x23E0)
        raw[_offset(0x23E2) : _offset(0x23E2) + 11] = b"ExitProcess"
        struct.pack_into("<II", raw, 0x98 + 112 + 8, 0x2300, 60)
        with self.assertRaises(ExecutableCompatibilityError):
            self.resolve(raw, contract)


if __name__ == "__main__":
    unittest.main()
