import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from sora_bilingual.game.native_runtime import NativeLabels


class NativeSnapshotTests(unittest.TestCase):
    def test_unsupported_or_disabled_resident_never_requests_full_snapshot(self):
        native = NativeLabels(lambda _: None)
        rpc = Mock()
        native.script = SimpleNamespace(exports_sync=rpc)
        native.control = SimpleNamespace(revision="actual-resident")
        for state, reason in (
            ({}, "resident_unsupported"),
            ({"inputIdentityDiagnostics": {"schema": 2, "enabled": False}}, "diagnostics_disabled"),
        ):
            result = native.snapshot(identity_only=True, state=state)
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["resident_revision"], "actual-resident")
        rpc.snapshot.assert_not_called()

    def test_new_resident_uses_same_rpc_and_explicit_full_snapshot_stays_compatible(self):
        native = NativeLabels(lambda _: None)
        rpc = Mock()
        rpc.snapshot.return_value = {"schema": 2, "rows": []}
        native.script = SimpleNamespace(exports_sync=rpc)
        native.control = SimpleNamespace(revision="new-resident")
        result = native.snapshot(
            identity_only=True, state={"inputIdentityDiagnostics": {"schema": 2, "enabled": True}}
        )
        rpc.snapshot.assert_called_once_with(True)
        self.assertEqual(result["resident_revision"], "new-resident")
        rpc.snapshot.reset_mock()
        native.snapshot()
        rpc.snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
