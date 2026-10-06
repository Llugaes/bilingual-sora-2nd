"""Normalized operands must keep the reviewed ABI and target boundaries."""

import copy
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import capstone

from test_native_contracts import PDATA_RVA, _offset, pe_fixture
from tools.build_native_contracts import Image, crc32_table, extend_contract


def diagnostic_template(
    line, *, target=0x2000, severity=3, line_register=0xB8, function="log_write_commit"
):
    # LEA R9=format; MOV R8D=line; LEA RDX=file; MOV ECX=severity;
    # CALL the explicitly reviewed diagnostic function; RET.
    code = (
        bytes.fromhex("4c8d0d0000000041")
        + bytes([line_register])
        + struct.pack("<I", line)
        + bytes.fromhex("488d1500000000b9")
        + struct.pack("<I", severity)
        + b"\xe8"
        + struct.pack("<i", target - 0x101E)
        + b"\xc3"
    )
    image = Image.__new__(Image)
    image.pe = SimpleNamespace(get_data=lambda start, size: code[start - 0x1000 :][:size])
    image.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    image.md.detail = True
    image.entries = {}
    image.continuations = {}
    return image.template(
        (0x1000, 0x1000 + len(code)),
        {"hook": 0},
        {
            function: (0x1000, 0x1000 + len(code)),
            "diagnostic_report": (0x2000, 0x208C),
        },
        {},
    )


class DiagnosticSourceLineTests(unittest.TestCase):
    def test_source_line_changes_preserve_hash_and_required_call_link(self):
        before = diagnostic_template(0x64B)
        after = diagnostic_template(0x656)
        self.assertEqual(before, after)
        self.assertIn([9, 4], before["masks"])
        self.assertEqual(before["links"][0]["function"], "diagnostic_report")
        self.assertEqual(before["links"][0]["displacement"], [26, 4])

    def test_unknown_call_target_does_not_normalize_source_line(self):
        before = diagnostic_template(0x64B, target=0x2100)
        after = diagnostic_template(0x656, target=0x2100)
        self.assertNotEqual(before["sha256"], after["sha256"])
        self.assertNotIn([9, 4], before["masks"])

    def test_changed_argument_register_or_severity_does_not_normalize(self):
        for options in ({"line_register": 0xB9}, {"severity": 2}):
            with self.subTest(options=options):
                before = diagnostic_template(0x64B, **options)
                after = diagnostic_template(0x656, **options)
                self.assertNotEqual(before["sha256"], after["sha256"])
                self.assertNotIn([9, 4], before["masks"])

    def test_unreviewed_function_does_not_normalize_source_line(self):
        before = diagnostic_template(0x64B, function="unreviewed")
        after = diagnostic_template(0x656, function="unreviewed")
        self.assertNotEqual(before["sha256"], after["sha256"])
        self.assertNotIn([9, 4], before["masks"])


def loader_image(code, *, imports=None):
    """A flat code buffer mapped at RVA 0x1000, as one loader sample."""
    image = Image.__new__(Image)
    image.pe = SimpleNamespace(
        get_data=lambda start, size: bytes(code[start - 0x1000 :][:size]),
        sections=[SimpleNamespace(VirtualAddress=0x1000)],
        OPTIONAL_HEADER=SimpleNamespace(SizeOfImage=0x10000),
    )
    image.md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    image.md.detail = True
    image.entries = {}
    image.functions = []
    image.starts = []
    image.continuations = {}
    image._imports = imports or {}
    return image


def wrapper_template(resume, *, function=0x3000, direct=True):
    if direct:
        # LEA R11,[resume]; NOP; NOP; JMP R11 -- leaves the caller's flags alone.
        code = bytes.fromhex("4c8d1d") + struct.pack("<i", resume - 0x1007) + b"\x90\x90"
    else:
        # LEA R11,[section]; SUB R11,section; ADD R11,resume; JMP R11.
        code = (
            bytes.fromhex("4c8d1d")
            + struct.pack("<i", 0x1000 - 0x1007)
            + bytes.fromhex("4981eb")
            + struct.pack("<I", 0x1000)
            + bytes.fromhex("4981c3")
            + struct.pack("<I", resume)
        )
    code += bytes.fromhex("41ffe3")
    image = loader_image(code)
    span = (0x1000, 0x1000 + len(code))
    image.continuations = {0x1000: ("cache_hash_wrapper", span)}
    return image.template(span, {}, {"font_image_read_call": (function, function + 0x600)}, {})


def helper_template(*, routine=0x2000, table=0x5000, slot=0x6098, routine_table=None):
    code = bytearray(0x1200)
    helper = (
        bytes.fromhex("8b9490")  # mov edx, [rax + rdx*4 + table]
        + struct.pack("<I", table)
        + bytes.fromhex("4805")  # add rax, routine
        + struct.pack("<I", routine)
        + bytes.fromhex("81f2ffffff00ffd0")  # xor edx, 0xffffff; call rax
        + bytes.fromhex("498b8424")  # mov rax, [r12 + import slot]
        + struct.pack("<I", slot)
        + b"\xc3"
    )
    code[: len(helper)] = helper
    at = routine - 0x1000
    code[at : at + 9] = (
        bytes.fromhex("488d05")
        + struct.pack("<i", (table if routine_table is None else routine_table) - routine - 7)
        + b"\xc3\xcc"
    )
    image = loader_image(code, imports={slot: ("KERNEL32.dll", "GetCurrentThreadId")})
    get_code = image.pe.get_data
    image.pe.get_data = lambda start, size: (
        crc32_table()[:size] if start == table else get_code(start, size)
    )
    span = (0x1000, 0x1000 + len(helper))
    image.continuations = {0x1000: ("cache_hash_helper", span)}
    return image, span


class RelinkedLoaderTests(unittest.TestCase):
    def test_direct_resume_is_a_required_link_independent_of_its_address(self):
        before = wrapper_template(0x3000 + 223)
        after = wrapper_template(0x4000 + 223, function=0x4000)
        self.assertEqual(before, after)
        self.assertEqual(before["masks"], [[3, 4]])
        self.assertEqual(
            before["links"],
            [
                {
                    "displacement": [3, 4],
                    "next": 7,
                    "function": "font_image_read_call",
                    "addend": 223,
                }
            ],
        )
        self.assertNotEqual(
            before["sha256"], wrapper_template(0x3000 + 223, direct=False)["sha256"]
        )
        with self.assertRaises(AssertionError):
            wrapper_template(0x7000)

    def test_image_base_resume_pair_keeps_its_reviewed_form(self):
        template = wrapper_template(0x3000 + 223, direct=False)
        self.assertEqual(template["masks"], [[3, 4], [10, 4], [17, 4]])
        self.assertEqual(
            template["links"],
            [
                {
                    "displacement": [17, 4],
                    "encoding": "rva32",
                    "function": "font_image_read_call",
                    "addend": 223,
                }
            ],
        )
        self.assertEqual(
            template["equal_targets"],
            [
                {
                    "left": {"displacement": [3, 4], "next": 7},
                    "right": {"displacement": [10, 4], "encoding": "rva32"},
                }
            ],
        )

    def test_image_relative_helper_operands_become_verified_references(self):
        image, span = helper_template()
        image.image_relative = True
        template = image.template(span, {}, {}, {})
        self.assertEqual(template["masks"], [[3, 4], [9, 4], [25, 4]])
        (callee,) = template["continuations"]
        self.assertEqual(
            {key: callee[key] for key in ("displacement", "encoding", "name")},
            {"displacement": [9, 4], "encoding": "rva32", "name": "path_hash_update"},
        )
        self.assertEqual(callee["template"]["size"], 8)
        self.assertEqual(callee["template"]["masks"], [[3, 4]])
        self.assertEqual(
            template["equal_targets"],
            [
                {
                    "left": {"displacement": [3, 4], "encoding": "rva32"},
                    "right": {
                        "continuation": "path_hash_update",
                        "displacement": [3, 4],
                        "next": 7,
                    },
                }
            ],
        )
        self.assertEqual(
            template["imports"],
            [
                {
                    "displacement": [25, 4],
                    "encoding": "rva32",
                    "dll": "KERNEL32.dll",
                    "name": "GetCurrentThreadId",
                }
            ],
        )

        moved, span = helper_template(routine=0x2100, table=0x5100, slot=0x60A0)
        moved.image_relative = True
        self.assertEqual(moved.template(span, {}, {}, {}), template)

    def test_helper_table_must_be_the_one_its_callee_reads(self):
        image, span = helper_template(routine_table=0x5004)
        image.image_relative = True
        with self.assertRaisesRegex(AssertionError, "table"):
            image.template(span, {}, {}, {})

    def test_original_compilation_keeps_helper_addresses_pinned(self):
        image, span = helper_template()
        template = image.template(span, {}, {}, {})
        self.assertEqual(template["masks"], [])
        self.assertNotIn("imports", template)
        self.assertNotIn("continuations", template)
        moved, span = helper_template(slot=0x60A0)
        self.assertNotEqual(moved.template(span, {}, {}, {})["sha256"], template["sha256"])


class ExtendContractTests(unittest.TestCase):
    def test_unknown_body_cannot_be_learned_from_a_sample(self):
        raw, contract = pe_fixture()
        raw[_offset(0x2200) : _offset(0x2204)] = b"\x01\0\0\0"
        for index in range(2):
            struct.pack_into("<I", raw, _offset(PDATA_RVA + 12 * index + 8), 0x2200)
        raw[_offset(0x1000)] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sora_2nd.exe"
            path.write_bytes(raw)
            sample = Image(path)
            try:
                with self.assertRaises(ValueError):
                    extend_contract(contract, sample)
            finally:
                sample.pe.close()

    def test_sample_already_covered_adds_no_variant_or_evidence(self):
        raw, contract = pe_fixture()
        raw[_offset(0x1058)] = 0xCC  # reviewed extent of the PDATA-less leaf
        raw[_offset(0x2200) : _offset(0x2204)] = b"\x01\0\0\0"  # plain UNWIND_INFO
        for index in range(2):
            struct.pack_into("<I", raw, _offset(PDATA_RVA + 12 * index + 8), 0x2200)
        expected = copy.deepcopy(contract)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sora_2nd.exe"
            path.write_bytes(raw)
            sample = Image(path)
            try:
                self.assertEqual(extend_contract(contract, sample), [])
            finally:
                sample.pe.close()
        self.assertEqual(contract["functions"], expected["functions"])
        self.assertEqual(contract["metadata"], expected["metadata"])


if __name__ == "__main__":
    unittest.main()
