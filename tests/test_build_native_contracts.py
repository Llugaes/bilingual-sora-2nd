"""Source-line normalization must retain the reviewed diagnostic ABI boundary."""

import struct
import unittest
from types import SimpleNamespace

import capstone

from tools.build_native_contracts import Image


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


if __name__ == "__main__":
    unittest.main()
