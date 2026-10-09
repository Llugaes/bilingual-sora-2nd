import itertools
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sora_bilingual.game import native_probe as probe
from sora_bilingual.config.native_config import read_config, write_config


class BackendDiagnosticIsolationTests(unittest.TestCase):
    def run_backend(self, *, snapshot_error=None, export_error=None, business_error=False):
        class FakeNative:
            def __init__(self):
                self.session = object()
                self.exited = threading.Event()
                self.control = object()
                self.eternalized = True
                self.resident_changed = False
                self.snapshots = 0
                self.selections = []
                self.disabled = []
                self.parked = []

            def attach(self, *_, **__):
                pass

            def status(self):
                return {"failed": False, "inputIdentityDiagnostics": {"schema": 2, "enabled": True}}

            def snapshot(self, **_):
                self.snapshots += 1
                if self.snapshots == 1 and snapshot_error is not None:
                    raise snapshot_error
                if self.snapshots >= 2:
                    self.exited.set()
                return {"schema": 2, "rows": []}

            def select(self, mode, enabled):
                self.selections.append((mode, enabled, self.snapshots))
                if business_error and self.snapshots:
                    raise probe.frida.RPCException("business mode RPC")

            def disable(self):
                self.disabled.append(self.snapshots)

            def park(self):
                self.parked.append(self.snapshots)
                return True

        native = FakeNative()

        class FakeInput:
            capture_status = "idle"

            def __init__(self, *_):
                self.polls = 0

            def devices(self):
                return []

            def poll_state(self, *_):
                self.polls += 1
                return SimpleNamespace(held=False, pressed=self.polls == 2)

            def poll_capture(self):
                return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "generated").mkdir()
            control = root / "control.json"
            write_config({"diagnostics": True, "interaction": "annotation"}, control)
            telemetry = []
            exports = []

            def publish(value, path):
                telemetry.append((value, path.name))
                if path.name == "native-input-identities.json":
                    exports.append(value)
                    if export_error is not None:
                        raise export_error
                return True

            class Heartbeat:
                def __init__(self, *_):
                    pass

                def loading(self, *_):
                    pass

                def update(self, index, value):
                    telemetry.append((value, "heartbeat-" + str(index)))

                def close(self):
                    pass

            lock = Mock()
            clock = itertools.count(10, 2)
            monitor = SimpleNamespace(poll=lambda: None, close=lambda: None)
            # This fixture never calls a process reader, creates a resident or
            # installs hooks. It runs the actual backend loop through two ticks.
            with (
                patch.multiple(
                    probe,
                    ROOT=root,
                    CONTROL=control,
                    NativeLabels=lambda _: native,
                    InputManager=FakeInput,
                    BackendLock=lambda: lock,
                    ConnectionHeartbeat=Heartbeat,
                    RuntimeTextTableReader=lambda *_: SimpleNamespace(
                        read=None, close=lambda: None
                    ),
                    SourceLanguageMonitor=lambda *_: monitor,
                    native_report=lambda _: {"text_table_global": 0x100},
                    detect_current_language=lambda *_, **__: SimpleNamespace(
                        language="en", reason="matched"
                    ),
                    prepare_fresh=lambda *_, **__: {"path": "fixture-model.json", "coverage": {}},
                    read_config=lambda: read_config(control),
                    write_config=lambda value, path=None: write_config(value, path or control),
                    write_telemetry=publish,
                    foreground_rect=lambda _: (0, 0, 800, 600),
                    process_path=lambda _: root / "sora_2nd.exe",
                    process_identity=lambda _: 123,
                    ReleaseWatch=lambda: SimpleNamespace(poll=lambda: set()),
                ),
                patch.object(probe.time, "monotonic", side_effect=lambda: next(clock)),
                patch.object(probe.time, "sleep"),
                patch.object(probe.signal, "signal"),
                patch.object(
                    probe.frida,
                    "get_local_device",
                    return_value=SimpleNamespace(
                        enumerate_processes=lambda: [SimpleNamespace(pid=42, name="sora_2nd.exe")]
                    ),
                ),
                patch("sora_bilingual.game.install.remember_game"),
            ):
                if business_error:
                    with self.assertRaisesRegex(probe.frida.RPCException, "business mode RPC"):
                        probe.run(root)
                else:
                    probe.run(root)
            journal = [
                json.loads(line)
                for line in (root / "generated/native-probe.jsonl").read_text("utf-8").splitlines()
            ]
            lock.close.assert_called_once()
        return native, telemetry, journal, exports

    def test_snapshot_rpc_failure_does_not_park_or_disable_before_next_input_and_snapshot(self):
        native, telemetry, journal, _ = self.run_backend(
            snapshot_error=probe.frida.RPCException("x" * 150000)
        )
        self.assertEqual(native.snapshots, 2)
        self.assertEqual(native.disabled, [])
        self.assertEqual(native.parked, [2], "only normal fixture game exit reaches cleanup")
        self.assertIn(("primary", True, 1), native.selections)
        errors = [row for row in journal if row["type"] == "input_diagnostic_error"]
        self.assertTrue(errors)
        self.assertLessEqual(len(errors[0]["message"]), 256)
        self.assertTrue(
            any(
                row.get("input_diagnostic_error")
                for row, name in telemetry
                if name == "heartbeat-1"
            )
        )

    def test_export_serialization_failure_is_diagnostic_only(self):
        native, _, journal, exports = self.run_backend(
            export_error=TypeError("unserializable diagnostic value")
        )
        self.assertEqual(native.snapshots, 2)
        self.assertEqual(native.disabled, [])
        self.assertEqual(native.parked, [2])
        self.assertIn(("primary", True, 1), native.selections)
        self.assertEqual(len(exports), 2)
        self.assertTrue(any(row["type"] == "input_diagnostic_error" for row in journal))

    def test_actual_business_rpc_error_is_not_swallowed_by_diagnostic_guard(self):
        native, _, _, _ = self.run_backend(business_error=True)
        self.assertEqual(native.snapshots, 1)
        self.assertEqual(native.parked, [1])

    def test_export_unavailable_is_reported_without_raising(self):
        native = Mock()
        native.snapshot.return_value = {"rows": []}
        with patch.object(probe, "write_telemetry", return_value=False):
            error = probe.export_input_diagnostics(native, {}, Path("unused.json"))
        self.assertEqual(error["stage"], "export")
        self.assertEqual(error["error_type"], "ExportUnavailable")
        native.disable.assert_not_called()
        native.park.assert_not_called()

    def test_broken_error_message_is_itself_diagnostic_only(self):
        class BrokenMessage(Exception):
            def __str__(self):
                raise RuntimeError("unusable diagnostic message")

        native = Mock()
        native.snapshot.side_effect = BrokenMessage()
        error = probe.export_input_diagnostics(native, {}, Path("unused.json"))
        self.assertEqual(error["stage"], "snapshot")
        self.assertEqual(error["error_type"], "BrokenMessage")
        self.assertEqual(error["message"], "Diagnostic error message unavailable")
        native.disable.assert_not_called()
        native.park.assert_not_called()


if __name__ == "__main__":
    unittest.main()
