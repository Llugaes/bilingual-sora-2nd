"""Parse real synthetic PE files; never start or attach a game."""

import hashlib
import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import pefile

from sora_bilingual.game import exe_compatibility as compatibility
from sora_bilingual.game import hooks


def pe_fixture():
    raw = bytearray(0x1000)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 0x80)
    raw[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", raw, 0x84, 0x8664, 6, 123, 0, 0, 0xF0, 0x22)
    optional = 0x98
    struct.pack_into("<H", raw, optional, 0x20B)
    struct.pack_into("<I", raw, optional + 16, 0x1000)
    struct.pack_into("<Q", raw, optional + 24, 0x140000000)
    struct.pack_into("<II", raw, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", raw, optional + 56, 0x7000, 0x400)
    struct.pack_into("<HH", raw, optional + 68, 2, 0x8160)
    struct.pack_into("<I", raw, optional + 108, 16)
    struct.pack_into("<II", raw, optional + 112 + 2 * 8, 0x5000, 0x80)
    names = (b".text", b".rdata", b".data", b".pdata", b".rsrc", b".reloc")
    for i, name in enumerate(names):
        section = 0x188 + i * 40
        raw[section : section + len(name)] = name
        struct.pack_into(
            "<IIII",
            raw,
            section + 8,
            0x380 if i == 2 else 0x80,
            (i + 1) * 0x1000,
            0x200,
            0x400 + i * 0x200,
        )
        struct.pack_into("<I", raw, section + 36, 0x60000020 if i == 0 else 0x40000040)
        raw[0x400 + i * 0x200 : 0x480 + i * 0x200] = bytes([i + 1]) * 0x80
    raw[0x400:0x406] = b"\x55\x48\x89\xe5\x41\x00"
    return raw


class ExecutableCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.raw = pe_fixture()
        self.pe = pefile.PE(data=self.raw, fast_load=True)
        self.addCleanup(self.pe.close)
        self.profile = compatibility.image_profile(self.pe)

    def verify(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            exe.write_bytes(raw)
            with (
                patch.object(compatibility, "_load_profile", return_value=self.profile),
                patch.object(compatibility, "TARGET_SHA256", hashlib.sha256(self.raw).hexdigest()),
                patch.object(hooks, "HOOKS", [("dialogue", "55 48 89 e5 41 00", 0)]),
            ):
                return hooks.verify_target(exe)

    def resource_tail(self):
        """Append an independently mapped resource section to the fixture."""
        raw = self.raw + bytes(0x200)
        # The new section does not move any mapped core bytes.  It is read-only
        # initialized data and the resource directory is its only reference.
        struct.pack_into("<H", raw, 0x86, 7)
        struct.pack_into("<I", raw, 0xD0, 0x8000)  # SizeOfImage
        section = 0x188 + 6 * 40
        raw[section : section + 6] = b".voice"
        struct.pack_into("<IIII", raw, section + 8, 0x80, 0x7000, 0x200, 0x1000)
        struct.pack_into("<I", raw, section + 36, 0x40000040)
        raw[0x1000:0x1080] = b"voice resource metadata".ljust(0x80, b"\0")
        struct.pack_into("<II", raw, 0x98 + 112 + 2 * 8, 0x7000, 0x80)
        return raw

    def test_known_image_is_still_exact(self):
        self.assertEqual(self.verify(self.raw)["compatibility"], "exact")

    def test_resource_timestamp_checksum_overlay_certificate_and_padding_allowed(self):
        variants = {"overlay": self.raw + b"separate publisher metadata"}
        for name, offset in (
            ("timestamp", 0x88),
            ("checksum", 0xD8),
            ("resource", 0xC40),
            ("padding", 0x4A0),
            ("header padding", 0x3FF),
        ):
            changed = self.raw.copy()
            changed[offset] ^= 0x40
            variants[name] = changed
        changed = self.raw + bytes(16)
        struct.pack_into("<II", changed, 0x98 + 112 + 4 * 8, len(self.raw), 16)
        variants["certificate"] = changed
        # Raw file offsets can move; RVAs and all mapped payloads stay fixed.
        changed = self.raw[:0x400] + bytes(0x200) + self.raw[0x400:]
        for i in range(6):
            struct.pack_into("<I", changed, 0x188 + i * 40 + 20, 0x600 + i * 0x200)
        variants["repacked"] = changed
        for name, raw in variants.items():
            with self.subTest(name=name):
                report = self.verify(raw)
                self.assertEqual(report["compatibility"], "compatible_image")
                self.assertEqual(report["hooks"][0]["rva"], 0x1000)
                self.assertEqual(report["sha256"], hashlib.sha256(raw).hexdigest())

    def test_nonloaded_headers_and_tail_resource_do_not_change_native_contract(self):
        variants = {}
        changed = self.raw.copy()
        changed[0x40] ^= 0x40  # DOS stub: the PE header remains at e_lfanew.
        variants["DOS stub"] = changed
        changed = self.raw.copy()
        changed[0x1C] ^= 0x40  # Reserved DOS-header word.
        variants["DOS reserved"] = changed
        changed = self.raw.copy()
        struct.pack_into("<II", changed, 0x8C, 0x900, 2)
        variants["COFF symbol metadata"] = changed
        variants["resource tail"] = self.resource_tail()
        for name, raw in variants.items():
            with self.subTest(name=name):
                report = self.verify(raw)
                self.assertEqual(report["compatibility"], "compatible_image")
                self.assertEqual(report["hooks"][0]["rva"], 0x1000)

    def test_tail_section_must_remain_read_only_and_be_the_resource_directory(self):
        executable = self.resource_tail()
        struct.pack_into("<I", executable, 0x188 + 6 * 40 + 36, 0x60000020)
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "可执行"):
            self.verify(executable)

        writable = self.resource_tail()
        struct.pack_into("<I", writable, 0x188 + 6 * 40 + 36, 0xC0000040)
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "可执行或可写"):
            self.verify(writable)

        unrelated = self.resource_tail()
        struct.pack_into("<II", unrelated, 0x98 + 112 + 2 * 8, 0x5000, 0x80)
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "非资源"):
            self.verify(unrelated)

        redirected = self.raw.copy()
        struct.pack_into("<II", redirected, 0x98 + 112 + 2 * 8, 0x1000, 0x80)
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "资源目录指向核心"):
            self.verify(redirected)

    def test_debug_symbols_are_not_runtime_contract_but_neighboring_constants_are(self):
        # A real IMAGE_DEBUG_DIRECTORY and RSDS record inside .rdata.
        raw = self.raw.copy()
        struct.pack_into("<II", raw, 0x98 + 112 + 6 * 8, 0x2000, 28)
        struct.pack_into("<IIHHIIII", raw, 0x600, 0, 123, 0, 0, 2, 32, 0x2030, 0x630)
        raw[0x630:0x634] = b"RSDS"
        raw[0x648:0x650] = b"old.pdb\0"
        with pefile.PE(data=raw, fast_load=True) as pe:
            self.profile = compatibility.image_profile(pe)
        for offset in (0x634, 0x644, 0x648):
            changed = raw.copy()
            changed[offset] ^= 1
            with self.subTest(offset=offset):
                self.assertEqual(self.verify(changed)["compatibility"], "compatible_image")
        # The record's type, signature, location, extent and adjacent bytes
        # cannot enlarge the ignored range or hide changed application data.
        for offset in (0x60C, 0x610, 0x614, 0x630, 0x650):
            changed = raw.copy()
            changed[offset] ^= 1
            with (
                self.subTest(offset=offset),
                self.assertRaises(compatibility.ExecutableCompatibilityError),
            ):
                self.verify(changed)

    def test_debug_directory_location_is_not_a_native_contract(self):
        changed = self.raw.copy()
        # Runtime validation relies on the trusted fixed CodeView span and
        # `.rdata` hash, not a candidate-controlled debug directory.
        struct.pack_into("<II", changed, 0x98 + 112 + 6 * 8, 0x1000, 28)
        self.assertEqual(self.verify(changed)["compatibility"], "compatible_image")

    def test_cli_digest_and_result_come_from_one_verified_snapshot(self):
        verified = {"compatibility": "compatible_image", "sha256": "a" * 64, "hooks": []}
        with (
            patch("sys.argv", ["compatibility", "--exe", "unused.exe"]),
            patch.object(hooks, "verify_target", return_value=verified) as verify,
            patch.object(Path, "read_bytes", side_effect=AssertionError("second snapshot")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(compatibility.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["sha256"], verified["sha256"])
        verify.assert_called_once()

    def test_rejected_snapshot_keeps_its_digest_without_reading_file_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            raw = b"invalid executable snapshot"
            exe.write_bytes(raw)
            with patch.object(Path, "read_bytes", return_value=raw) as read:
                with self.assertRaises(compatibility.ExecutableCompatibilityError) as caught:
                    hooks.verify_target(exe)
            read.assert_called_once()
            self.assertEqual(caught.exception.sha256, hashlib.sha256(raw).hexdigest())
            with (
                patch("sys.argv", ["compatibility", "--exe", str(exe)]),
                patch.object(hooks, "verify_target", side_effect=caught.exception),
                patch.object(Path, "read_bytes", side_effect=AssertionError("second snapshot")),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(compatibility.main(), 1)
            self.assertEqual(json.loads(output.getvalue())["sha256"], caught.exception.sha256)

    def test_cli_includes_structured_layout_differences(self):
        error = compatibility.ExecutableCompatibilityError(
            "layout changed", sha256="b" * 64, details=["OptionalHeader.AddressOfEntryPoint"]
        )
        with (
            patch("sys.argv", ["compatibility", "--exe", "unused.exe"]),
            patch.object(hooks, "verify_target", side_effect=error),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(compatibility.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["sha256"], "b" * 64)
        self.assertEqual(result["details"], ["OptionalHeader.AddressOfEntryPoint"])

    def test_every_core_section_rejects_changes_beyond_hook_entry(self):
        for i, name in enumerate((".text", ".rdata", ".data", ".pdata", ".rsrc", ".reloc")):
            if name == ".rsrc":
                continue
            changed = self.raw.copy()
            changed[0x440 + i * 0x200] ^= 0x80
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, name),
            ):
                self.verify(changed)

    def test_abi_header_changes_truncation_and_unsafe_directories_rejected(self):
        # Entry point, image base, section RVA, unwind directory, DLL flags.
        for offset in (0xA8, 0xB0, 0x194, 0x120, 0xDE):
            changed = self.raw.copy()
            changed[offset] ^= 1
            with (
                self.subTest(offset=offset),
                self.assertRaises(compatibility.ExecutableCompatibilityError),
            ):
                self.verify(changed)
        for directory in (2, 4):
            changed = self.raw.copy()
            struct.pack_into("<II", changed, 0x98 + 112 + directory * 8, 0x1000, 0xFFFF)
            with (
                self.subTest(directory=directory),
                self.assertRaises(compatibility.ExecutableCompatibilityError),
            ):
                self.verify(changed)
        for raw in (self.raw[:-0x200], b"not a PE", self.raw[:200]):
            with self.assertRaises(compatibility.ExecutableCompatibilityError):
                self.verify(raw)

    def test_invalid_file_alignment_is_a_diagnostic_rejection_before_hook_scanning(self):
        changed = self.raw.copy()
        struct.pack_into("<I", changed, 0x98 + 36, 0)
        with patch.object(hooks, "signature_matches", side_effect=AssertionError("scanned hooks")):
            with self.assertRaisesRegex(
                compatibility.ExecutableCompatibilityError, "FileAlignment"
            ) as caught:
                self.verify(changed)
        self.assertIn("OptionalHeader.FileAlignment=0x0", caught.exception.details)

        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            exe.write_bytes(changed)
            with (
                patch.object(compatibility, "_load_profile", return_value=self.profile),
                patch("sys.argv", ["compatibility", "--exe", str(exe)]),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(compatibility.main(), 1)
        result = json.loads(output.getvalue())
        self.assertIn("FileAlignment", result["error"])
        self.assertIn("OptionalHeader.FileAlignment=0x0", result["details"])

    def test_layout_error_names_the_changed_contract_before_scanning_hooks(self):
        changed = self.raw.copy()
        changed[0xA8] ^= 1  # AddressOfEntryPoint
        with patch.object(hooks, "signature_matches", side_effect=AssertionError("scanned hooks")):
            with self.assertRaisesRegex(
                compatibility.ExecutableCompatibilityError, "AddressOfEntryPoint"
            ):
                self.verify(changed)

    def test_native_report_uses_same_verified_snapshot(self):
        from sora_bilingual.game import native_runtime

        # Simulate the file changing after the verified snapshot was loaded.
        from contextlib import contextmanager

        @contextmanager
        def verified(exe):
            exe.write_bytes(b"replaced after verification")
            yield self.pe, {"compatibility": "fixture"}

        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            exe.write_bytes(self.raw)
            with (
                patch.object(native_runtime, "verified_target_image", verified),
                patch.object(native_runtime, "POINTS", {"set_text": 0x1000}),
            ):
                report = native_runtime.native_report(exe)
            self.assertEqual(
                report["native"]["set_text"]["bytes"], bytes(self.raw[0x400:0x410]).hex()
            )


if __name__ == "__main__":
    unittest.main()
