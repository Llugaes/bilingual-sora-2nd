"""Synthetic PE regressions for capability-scoped native contract lookup."""

from __future__ import annotations

import hashlib
import copy
import struct
import unittest

import pefile

from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError
from sora_bilingual.game.native_contracts import resolve_native_contracts


IMAGE_BASE = 0x140000000
TEXT_RVA = 0x1000
RDATA_RVA = 0x2000
DATA_RVA = 0x3000
PDATA_RVA = 0x4000


def _offset(rva: int) -> int:
    if TEXT_RVA <= rva < TEXT_RVA + 0x400:
        return 0x400 + rva - TEXT_RVA
    if RDATA_RVA <= rva < RDATA_RVA + 0x400:
        return 0x800 + rva - RDATA_RVA
    if DATA_RVA <= rva < DATA_RVA + 0x200:
        return 0xC00 + rva - DATA_RVA
    if PDATA_RVA <= rva < PDATA_RVA + 0x200:
        return 0xE00 + rva - PDATA_RVA
    raise ValueError(hex(rva))


def _write_rel32(raw: bytearray, displacement_rva: int, next_rva: int, target_rva: int) -> None:
    struct.pack_into("<i", raw, _offset(displacement_rva), target_rva - next_rva)


def _pe_raw(*, leaf_rva: int = 0x1050, state_rva: int = DATA_RVA) -> bytearray:
    raw = bytearray(0x1000)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", raw, 0x84, 0x8664, 4, 1, 0, 0, 0xF0, 0x22)
    optional = 0x98
    struct.pack_into("<H", raw, optional, 0x20B)
    struct.pack_into("<I", raw, optional + 16, TEXT_RVA)
    struct.pack_into("<Q", raw, optional + 24, IMAGE_BASE)
    struct.pack_into("<II", raw, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", raw, optional + 56, 0x5000, 0x400)
    struct.pack_into("<HH", raw, optional + 68, 2, 0x8160)
    struct.pack_into("<I", raw, optional + 108, 16)
    struct.pack_into("<II", raw, optional + 112 + 3 * 8, PDATA_RVA, 24)
    sections = (
        (b".text", TEXT_RVA, 0x400, 0x400, 0x400, 0x60000020),
        (b".rdata", RDATA_RVA, 0x400, 0x400, 0x800, 0x40000040),
        (b".data", DATA_RVA, 0x200, 0x200, 0xC00, 0xC0000040),
        (b".pdata", PDATA_RVA, 0x200, 0x200, 0xE00, 0x40000040),
    )
    for index, (name, rva, virtual_size, raw_size, raw_offset, characteristics) in enumerate(
        sections
    ):
        offset = 0x188 + index * 40
        raw[offset : offset + len(name)] = name
        struct.pack_into("<IIII", raw, offset + 8, virtual_size, rva, raw_size, raw_offset)
        struct.pack_into("<I", raw, offset + 36, characteristics)

    # main: CALL leaf, then a RIP global load. Both address operands are part
    # of the reviewed mask; opcodes and the whole remaining function are not.
    main = bytes((0xE8, 0, 0, 0, 0, 0x48, 0x8B, 0x05, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90))
    raw[_offset(0x1000) : _offset(0x1000) + len(main)] = main
    _write_rel32(raw, 0x1001, 0x1005, leaf_rva)
    _write_rel32(raw, 0x1008, 0x100C, state_rva)
    raw[_offset(leaf_rva) : _offset(leaf_rva) + 8] = b"\x55\x48\x89\xe5\xc3\x90\x90\x90"

    # vtable_site: LEA of a read-only vtable whose preceding slot is an MSVC
    # CompleteObjectLocator and TypeDescriptor name.
    vtable_site = bytes(
        (0x48, 0x8D, 0x05, 0, 0, 0, 0, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90)
    )
    raw[_offset(0x1020) : _offset(0x1020) + len(vtable_site)] = vtable_site
    _write_rel32(raw, 0x1023, 0x1027, 0x2010)
    struct.pack_into("<Q", raw, _offset(0x2008), IMAGE_BASE + 0x2100)
    struct.pack_into("<IIIIII", raw, _offset(0x2100), 1, 0, 0, 0x2140, 0, 0x2100)
    raw[_offset(0x2150) : _offset(0x2150) + 12] = b".?AVLabel@@\0"

    struct.pack_into("<III", raw, _offset(PDATA_RVA), 0x1000, 0x1010, 0)
    struct.pack_into("<III", raw, _offset(PDATA_RVA + 12), 0x1020, 0x1030, 0)
    return raw


def _masked_hash(raw: bytes, rva: int, size: int, masks: list[list[int]]) -> str:
    data = bytearray(raw[_offset(rva) : _offset(rva) + size])
    for offset, width in masks:
        data[offset : offset + width] = bytes(width)
    return hashlib.sha256(data).hexdigest()


def fixture_contract(raw: bytes) -> dict:
    main_masks = [[1, 4], [8, 4]]
    return {
        "schema": 1,
        "functions": {
            "main": {
                "leaf": False,
                "variants": [
                    {
                        "size": 16,
                        "sha256": _masked_hash(raw, 0x1000, 16, main_masks),
                        "masks": main_masks,
                        "points": {"main_hook": 0},
                        "links": [
                            {
                                "displacement": [1, 4],
                                "next": 5,
                                "function": "leaf",
                                "addend": 0,
                            }
                        ],
                        "globals": [{"name": "state", "displacement": [8, 4], "next": 12}],
                    }
                ],
            },
            "leaf": {
                "leaf": True,
                "variants": [
                    {
                        "size": 8,
                        "sha256": _masked_hash(raw, 0x1050, 8, []),
                        "masks": [],
                        "points": {"leaf_hook": 0},
                        "links": [],
                        "globals": [],
                    }
                ],
            },
            "vtable_site": {
                "leaf": False,
                "variants": [
                    {
                        "size": 16,
                        "sha256": _masked_hash(raw, 0x1020, 16, [[3, 4]]),
                        "masks": [[3, 4]],
                        "points": {"vtable_hook": 0},
                        "links": [],
                        "globals": [{"name": "label_vtable", "displacement": [3, 4], "next": 7}],
                    }
                ],
            },
        },
        "global_specs": {
            "state": {"alignment": 8, "writable": True},
            "label_vtable": {"alignment": 8, "writable": False, "rtti": ".?AVLabel@@"},
        },
        "metadata": {"contract_id": "synthetic-native-contract"},
    }


def pe_fixture(*, leaf_rva: int = 0x1050, state_rva: int = DATA_RVA) -> tuple[bytearray, dict]:
    """Return a parseable PE and its baseline-local function contract."""
    raw = _pe_raw(leaf_rva=leaf_rva, state_rva=state_rva)
    return raw, fixture_contract(raw)


def caller_constraint_fixture() -> tuple[bytearray, dict]:
    """One caller has three independent links to one of two equal functions."""
    raw, _ = pe_fixture()
    raw[_offset(0x1000) : _offset(0x1010)] = bytes((0xE8, 0, 0, 0, 0)) * 3 + b"\x90"
    for displacement, next_rva in ((0x1001, 0x1005), (0x1006, 0x100A), (0x100B, 0x100F)):
        _write_rel32(raw, displacement, next_rva, 0x1050)
    raw[_offset(0x1070) : _offset(0x1078)] = raw[_offset(0x1050) : _offset(0x1058)]
    for index, (start, end) in enumerate(((0x1000, 0x1010), (0x1050, 0x1058), (0x1070, 0x1078))):
        struct.pack_into("<III", raw, _offset(PDATA_RVA + 12 * index), start, end, 0)
    struct.pack_into("<I", raw, 0x98 + 112 + 3 * 8 + 4, 36)
    parent_masks = [[1, 4], [6, 4], [11, 4]]
    contract = {
        "schema": 1,
        "functions": {
            "parent": {
                "leaf": False,
                "variants": [
                    {
                        "size": 16,
                        "sha256": _masked_hash(raw, 0x1000, 16, parent_masks),
                        "masks": parent_masks,
                        "points": {"parent": 0},
                        "links": [
                            {
                                "displacement": [1, 4],
                                "next": 5,
                                "function": "book_count",
                                "addend": 0,
                            },
                            {
                                "displacement": [6, 4],
                                "next": 10,
                                "function": "book_count",
                                "addend": 0,
                            },
                            {
                                "displacement": [11, 4],
                                "next": 15,
                                "function": "book_count",
                                "addend": 0,
                            },
                        ],
                        "globals": [],
                    }
                ],
            },
            "book_count": {
                "leaf": False,
                "variants": [
                    {
                        "size": 8,
                        "sha256": _masked_hash(raw, 0x1050, 8, []),
                        "masks": [],
                        "points": {"book_count": 0},
                        "links": [],
                        "globals": [],
                    }
                ],
            },
        },
        "global_specs": {},
        "metadata": {"contract_id": "caller-constraint"},
    }
    return raw, contract


def continuation_fixture(
    *, continuation_rva: int = 0x1050, helper_rva: int = 0x1020
) -> tuple[bytearray, dict]:
    """A chained unwind fragment with a moved helper and audited return jump."""
    raw = _pe_raw()
    root = bytes((0xE9, 0, 0, 0, 0, 0x90, 0x90, 0x90))
    raw[_offset(0x1000) : _offset(0x1008)] = root
    _write_rel32(raw, 0x1001, 0x1005, continuation_rva)
    raw[_offset(helper_rva) : _offset(helper_rva) + 8] = b"\x55\x48\x89\xe5\xc3\x90\x90\x90"
    body = bytearray(23)
    body[0] = 0xE8
    body[5] = 0xE9
    body[10:13] = b"\x48\x8d\x05"
    body[17:19] = b"\x48\x2d"
    raw[_offset(continuation_rva) : _offset(continuation_rva) + len(body)] = body
    _write_rel32(raw, continuation_rva + 1, continuation_rva + 5, helper_rva)
    _write_rel32(raw, continuation_rva + 6, continuation_rva + 10, 0x1005)
    _write_rel32(raw, continuation_rva + 13, continuation_rva + 17, DATA_RVA)
    struct.pack_into("<I", raw, _offset(continuation_rva + 19), DATA_RVA)

    # The continuation record's UNW_FLAG_CHAININFO points back to root.
    raw[_offset(0x2200) : _offset(0x2204)] = b"\x01\0\0\0"
    raw[_offset(0x2210) : _offset(0x2214)] = b"\x01\0\0\0"
    raw[_offset(0x2220) : _offset(0x2224)] = b"\x21\0\0\0"
    struct.pack_into("<III", raw, _offset(0x2224), 0x1000, 0x1008, 0x2200)
    for index, (start, end, unwind) in enumerate(
        (
            (0x1000, 0x1008, 0x2200),
            (helper_rva, helper_rva + 8, 0x2210),
            (continuation_rva, continuation_rva + 23, 0x2220),
        )
    ):
        struct.pack_into("<III", raw, _offset(PDATA_RVA + 12 * index), start, end, unwind)
    struct.pack_into("<I", raw, 0x98 + 112 + 3 * 8 + 4, 36)

    root_masks = [[1, 4]]
    body_masks = [[1, 4], [6, 4], [13, 4], [19, 4]]
    contract = {
        "schema": 1,
        "functions": {
            "root": {
                "leaf": False,
                "variants": [
                    {
                        "size": 8,
                        "sha256": _masked_hash(raw, 0x1000, 8, root_masks),
                        "masks": root_masks,
                        "points": {"root_hook": 0},
                        "links": [],
                        "globals": [],
                        "continuations": [
                            {
                                "displacement": [1, 4],
                                "next": 5,
                                "template": {
                                    "size": 23,
                                    "sha256": _masked_hash(raw, continuation_rva, 23, body_masks),
                                    "masks": body_masks,
                                    "links": [
                                        {
                                            "displacement": [1, 4],
                                            "next": 5,
                                            "function": "helper",
                                            "addend": 0,
                                        },
                                        {
                                            "displacement": [6, 4],
                                            "next": 10,
                                            "function": "root",
                                            "addend": 5,
                                        },
                                    ],
                                    "globals": [],
                                    "equal_targets": [
                                        {
                                            "left": {"displacement": [13, 4], "next": 17},
                                            "right": {"displacement": [19, 4], "encoding": "rva32"},
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
            "helper": {
                "leaf": False,
                "variants": [
                    {
                        "size": 8,
                        "sha256": _masked_hash(raw, helper_rva, 8, []),
                        "masks": [],
                        "points": {"helper_hook": 0},
                        "links": [],
                        "globals": [],
                    }
                ],
            },
        },
        "global_specs": {},
        "metadata": {"contract_id": "continuation-contract"},
    }
    return raw, contract


class NativeContractTests(unittest.TestCase):
    def resolve(self, raw: bytes, contract: dict):
        pe = pefile.PE(data=raw, fast_load=True)
        self.addCleanup(pe.close)
        return resolve_native_contracts(pe, contract)

    def setUp(self):
        self.raw, self.contract = pe_fixture()

    def test_recovers_relocated_link_leaf_globals_and_rtti_without_image_hash(self):
        candidate, _ = pe_fixture(leaf_rva=0x1060, state_rva=0x3010)
        candidate[0x40] ^= 0x40  # non-loaded DOS stub
        candidate[_offset(0x1080)] = 0xCC  # unrelated executable byte
        candidate[_offset(0x2020)] = 0xA5  # unrelated read-only data
        result = self.resolve(candidate, self.contract)
        self.assertEqual(result["contract_id"], "synthetic-native-contract")
        self.assertEqual(
            result["functions"], {"main": 0x1000, "leaf": 0x1060, "vtable_site": 0x1020}
        )
        self.assertEqual(
            result["points"], {"main_hook": 0x1000, "leaf_hook": 0x1060, "vtable_hook": 0x1020}
        )
        self.assertEqual(result["globals"], {"state": 0x3010, "label_vtable": 0x2010})

    def test_changed_required_instruction_is_rejected(self):
        changed = self.raw.copy()
        changed[_offset(0x1000)] = 0x90
        with self.assertRaisesRegex(ExecutableCompatibilityError, "main"):
            self.resolve(changed, self.contract)

    def test_ambiguous_pdata_function_is_rejected(self):
        changed = self.raw.copy()
        changed[_offset(0x1080) : _offset(0x1090)] = changed[_offset(0x1000) : _offset(0x1010)]
        _write_rel32(changed, 0x1081, 0x1085, 0x1050)
        _write_rel32(changed, 0x1088, 0x108C, DATA_RVA)
        struct.pack_into("<III", changed, _offset(PDATA_RVA + 24), 0x1080, 0x1090, 0)
        struct.pack_into("<I", changed, 0x98 + 112 + 3 * 8 + 4, 36)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "main.*2"):
            self.resolve(changed, self.contract)

    def test_global_permissions_and_rtti_are_local_required_contracts(self):
        wrong_section, _ = pe_fixture(state_rva=0x2010)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "state.*可写"):
            self.resolve(wrong_section, self.contract)

        wrong_rtti = self.raw.copy()
        wrong_rtti[_offset(0x2150)] = ord("X")
        with self.assertRaisesRegex(ExecutableCompatibilityError, "RTTI"):
            self.resolve(wrong_rtti, self.contract)

    def test_read_only_requirement_does_not_reject_a_writable_global_slot(self):
        contract = copy.deepcopy(self.contract)
        contract["global_specs"]["state"]["writable"] = False
        self.assertEqual(self.resolve(self.raw, contract)["globals"]["state"], DATA_RVA)

    def test_zero_filled_virtual_global_is_a_complete_readable_image_interval(self):
        candidate, _ = pe_fixture(state_rva=0x3100)
        data_section = 0x188 + 2 * 40
        struct.pack_into("<I", candidate, data_section + 16, 0x100)
        self.assertEqual(self.resolve(candidate, self.contract)["globals"]["state"], 0x3100)

    def test_independent_caller_links_disambiguate_identical_book_count_functions(self):
        raw, contract = caller_constraint_fixture()
        self.assertEqual(self.resolve(raw, contract)["functions"]["book_count"], 0x1050)

    def test_unrelated_bad_pdata_and_false_leaf_caller_do_not_block_a_valid_contract(self):
        unrelated = self.raw.copy()
        struct.pack_into("<III", unrelated, _offset(PDATA_RVA + 24), 0x1800, 0x1810, 0)
        struct.pack_into("<I", unrelated, 0x98 + 112 + 3 * 8 + 4, 36)
        self.assertEqual(self.resolve(unrelated, self.contract)["functions"]["main"], 0x1000)

        false_caller = self.raw.copy()
        false_caller[_offset(0x1080) : _offset(0x1090)] = false_caller[
            _offset(0x1000) : _offset(0x1010)
        ]
        _write_rel32(false_caller, 0x1081, 0x1085, 0x5000)
        struct.pack_into("<III", false_caller, _offset(PDATA_RVA + 24), 0x1080, 0x1090, 0)
        struct.pack_into("<I", false_caller, 0x98 + 112 + 3 * 8 + 4, 36)
        self.assertEqual(self.resolve(false_caller, self.contract)["functions"]["main"], 0x1000)

    def test_bad_required_pdata_entry_and_conflicting_same_start_variants_reject(self):
        missing_main = self.raw.copy()
        struct.pack_into("<III", missing_main, _offset(PDATA_RVA), 0x1800, 0x1810, 0)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "main.*没有"):
            self.resolve(missing_main, self.contract)

        conflicting = copy.deepcopy(self.contract)
        variant = copy.deepcopy(conflicting["functions"]["main"]["variants"][0])
        variant["points"] = {"different_point": 0}
        conflicting["functions"]["main"]["variants"].append(variant)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "同址变体语义不一致"):
            self.resolve(self.raw, conflicting)

    def test_moved_continuation_and_helper_recover_but_body_or_return_changes_reject(self):
        baseline, contract = continuation_fixture()
        moved, _ = continuation_fixture(continuation_rva=0x1060, helper_rva=0x1030)
        self.assertEqual(
            self.resolve(moved, contract)["functions"], {"root": 0x1000, "helper": 0x1030}
        )

        changed_body = moved.copy()
        changed_body[_offset(0x1060)] = 0x90
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*continuation") as caught:
            self.resolve(changed_body, contract)
        self.assertEqual(caught.exception.details[0]["function"], "root")
        self.assertIn("continuation", caught.exception.details[0]["path"])
        self.assertIn("摘要", caught.exception.details[0]["reason"])
        self.assertIn("affected_callers", caught.exception.details[0])
        self.assertNotIn("helper 没有唯一匹配", str(caught.exception))

        wrong_return = moved.copy()
        _write_rel32(wrong_return, 0x1066, 0x106A, 0x1006)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*continuation"):
            self.resolve(wrong_return, contract)

        wrong_rva_pair = moved.copy()
        struct.pack_into("<I", wrong_rva_pair, _offset(0x1073), DATA_RVA + 8)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*continuation"):
            self.resolve(wrong_rva_pair, contract)

    def test_chaininfo_fragments_keep_their_audited_relative_position(self):
        baseline, contract = continuation_fixture()
        chained = copy.deepcopy(contract)
        root = chained["functions"]["root"]["variants"][0]
        template = root.pop("continuations")[0]["template"]
        template["offset"] = 0x50
        root["chained"] = [template]
        self.assertEqual(self.resolve(baseline, chained)["functions"]["root"], 0x1000)

        moved, _ = continuation_fixture(continuation_rva=0x1060, helper_rva=0x1030)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*chained") as caught:
            self.resolve(moved, chained)
        self.assertEqual(caught.exception.details[0]["function"], "root")
        self.assertIn("chained", caught.exception.details[0]["path"])
        self.assertIn("相对位置", caught.exception.details[0]["reason"])

        # A copied valid fragment must not stand in for the fragment reached
        # by the root's unchanged fallthrough jump at 0x1050.
        copied = baseline.copy()
        copied[_offset(0x1060) : _offset(0x1077)] = copied[_offset(0x1050) : _offset(0x1067)]
        copied[_offset(0x1050)] = 0x90
        struct.pack_into("<III", copied, _offset(PDATA_RVA + 24), 0x1060, 0x1077, 0x2220)
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*chained"):
            self.resolve(copied, chained)

        broken = baseline.copy()
        broken[_offset(0x1050)] = 0x90
        with self.assertRaisesRegex(ExecutableCompatibilityError, "root.*chained"):
            self.resolve(broken, chained)
