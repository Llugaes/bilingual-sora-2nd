"""Exercise the public connection preflight using real, disposable PE fixtures."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from test_native_contracts import pe_fixture
from sora_bilingual.game import exe_compatibility as compatibility
from sora_bilingual.game import hooks, native_contract_data, native_runtime


class ExecutableCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.contract = pe_fixture()
        self.contract["functions"]["leaf"]["variants"][0]["points"] = {"font_file_read": 0}
        self.contract_patch = patch.object(native_contract_data, "CONTRACT", self.contract)
        self.contract_patch.start()
        self.addCleanup(self.contract_patch.stop)

    def verify(self, raw):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            exe.write_bytes(raw)
            return hooks.verify_target(exe)

    def test_native_contract_does_not_require_legacy_capture_sites_or_file_identity(self):
        with patch.object(hooks, "signature_matches", side_effect=AssertionError("capture scan")):
            baseline = self.verify(self.raw)
            for offset in (0x40, 0x88, 0xD8, 0xA8, 0xDE, 0x500, 0xB00):
                changed = self.raw.copy()
                changed[offset] ^= 0x40
                with self.subTest(offset=offset):
                    report = self.verify(changed)
                    self.assertEqual(report["native"], baseline["native"])
                    self.assertEqual(report["compatibility"], "native_contract")
                    self.assertEqual(report["sha256"], hashlib.sha256(changed).hexdigest())
                    self.assertNotIn("hooks", report)
            self.assertEqual(
                self.verify(self.raw + b"unrelated publisher overlay")["native"], baseline["native"]
            )

    def test_resolved_points_and_globals_follow_relocation(self):
        moved, _ = pe_fixture(leaf_rva=0x1060, state_rva=0x3010)
        report = self.verify(moved)
        self.assertEqual(report["font_file_read"], 0x1060)
        self.assertNotIn("font_file_read", report["native"])
        self.assertEqual(report["state"], 0x3010)
        self.assertEqual(report["native"]["main_hook"]["rva"], 0x1000)
        self.assertEqual(report["native"]["main_hook"]["bytes"], moved[0x400:0x410].hex())

    def test_required_instruction_architecture_and_truncated_image_rejected(self):
        changed = self.raw.copy()
        changed[0x40E] ^= 1
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "main"):
            self.verify(changed)
        changed = self.raw.copy()
        struct.pack_into("<H", changed, 0x84, 0x14C)
        with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "64"):
            self.verify(changed)
        for raw in (b"not a PE", self.raw[:200], self.raw[:0x408]):
            with (
                self.subTest(length=len(raw)),
                self.assertRaises(compatibility.ExecutableCompatibilityError),
            ):
                self.verify(raw)

    def test_legacy_capture_has_its_own_capability_contract(self):
        changed = self.raw.copy()
        changed[0x40E] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "sora_2nd.exe"
            exe.write_bytes(changed)
            with patch.object(hooks, "HOOKS", [("dialogue", "55 48 89 e5 c3", 0)]):
                with hooks.verified_target_image(exe, capture=True) as (_pe, report):
                    self.assertEqual(report["compatibility"], "capture_contract")
                    self.assertEqual(report["hooks"][0]["rva"], 0x1050)
                with self.assertRaisesRegex(compatibility.ExecutableCompatibilityError, "main"):
                    hooks.verify_target(exe)

    def test_native_report_uses_one_snapshot_including_diagnostic_identity(self):
        with patch.object(Path, "read_bytes", return_value=self.raw) as read:
            report = native_runtime.native_report(Path("unused.exe"))
        read.assert_called_once()
        self.assertEqual(report["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(report["native"]["main_hook"]["bytes"], self.raw[0x400:0x410].hex())

    def test_resident_revision_tracks_function_contract_not_provenance(self):
        before = native_runtime.native_revision("agent code")
        self.contract["metadata"]["baseline_evidence_sha256"] = "unrelated sample"
        self.assertEqual(native_runtime.native_revision("agent code"), before)
        changed = copy.deepcopy(self.contract)
        changed["functions"]["main"]["variants"][0]["points"]["main_hook"] = 1
        with patch.object(native_contract_data, "CONTRACT", changed):
            self.assertNotEqual(native_runtime.native_revision("agent code"), before)
        self.assertNotEqual(native_runtime.native_revision("changed agent code"), before)

    def test_cli_reports_the_same_successful_snapshot(self):
        verified = self.verify(self.raw)
        with (
            patch("sys.argv", ["compatibility", "--exe", "unused.exe"]),
            patch.object(hooks, "verify_target", return_value=verified) as verify,
            patch.object(Path, "read_bytes", side_effect=AssertionError("second snapshot")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(compatibility.main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["sha256"], verified["sha256"])
        self.assertEqual(result["native_points"], 2)
        verify.assert_called_once()

    def test_failed_snapshot_keeps_digest_and_specific_dependency_diagnostic(self):
        changed = self.raw.copy()
        changed[0x40E] ^= 1
        with patch.object(Path, "read_bytes", return_value=changed) as read:
            with self.assertRaises(compatibility.ExecutableCompatibilityError) as caught:
                hooks.verify_target(Path("unused.exe"))
        read.assert_called_once()
        self.assertEqual(caught.exception.sha256, hashlib.sha256(changed).hexdigest())
        with (
            patch("sys.argv", ["compatibility", "--exe", "unused.exe"]),
            patch.object(hooks, "verify_target", side_effect=caught.exception),
            patch.object(Path, "read_bytes", side_effect=AssertionError("second snapshot")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(compatibility.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["sha256"], caught.exception.sha256)
        self.assertIn("main", result["error"])


if __name__ == "__main__":
    unittest.main()
