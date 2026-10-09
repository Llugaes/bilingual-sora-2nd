"""Reproduce UI choices interleaving with backend startup/default writes."""

from concurrent.futures import CancelledError
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from sora_bilingual.app.native_settings import update_control
from sora_bilingual.config.native_config import (
    LANGUAGE_DEFAULTS_PENDING,
    read_config,
    apply_pending_language_defaults,
    update_config,
    write_config,
)
from sora_bilingual.game import native_probe as probe


class ControlInterleavingTests(unittest.TestCase):
    def test_manual_selection_after_backend_read_survives_startup_and_detection(self):
        for read_number in (1, 2):
            with self.subTest(read_number=read_number), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                control = root / "generated/native-control.json"
                write_config({LANGUAGE_DEFAULTS_PENDING: True}, control)
                reads = 0
                prepared = []

                def backend_update(change, path):
                    nonlocal reads
                    # A formerly-read snapshot may already be stale before the
                    # transaction starts. The backend must read again inside it.
                    read_config(control)
                    reads += 1
                    if reads == read_number:
                        update_control(
                            {
                                "primary": "fr",
                                "secondary": "de",
                                "line_gap": 9,
                                "experimental_primary": True,
                            },
                            control,
                        )
                    return update_config(change, path)

                def prepare(_game, config, **_):
                    prepared.append(config)
                    raise CancelledError()

                with (
                    patch.multiple(
                        probe,
                        ROOT=root,
                        CONTROL=control,
                        BackendLock=lambda: Mock(),
                        native_report=lambda _: {},
                        detect_current_language=lambda *a, **k: SimpleNamespace(
                            language="en", reason="matched"
                        ),
                        prepare_fresh=prepare,
                        read_config=lambda: read_config(control),
                        update_config=backend_update,
                        write_config=lambda value, path=None: write_config(value, path or control),
                        write_telemetry=lambda *a: True,
                        process_path=lambda _: root / "sora_2nd.exe",
                        process_identity=lambda _: 123,
                    ),
                    patch.object(
                        probe.frida,
                        "get_local_device",
                        return_value=SimpleNamespace(
                            enumerate_processes=lambda: [
                                SimpleNamespace(pid=42, name="sora_2nd.exe")
                            ]
                        ),
                    ),
                    patch.object(probe.signal, "signal"),
                    patch("sora_bilingual.game.install.remember_game"),
                ):
                    probe.run(root)
                persisted = read_config(control)
                self.assertEqual((persisted["primary"], persisted["secondary"]), ("fr", "de"))
                self.assertEqual(persisted["line_gap"], 9)
                self.assertEqual((prepared[0]["primary"], prepared[0]["secondary"]), ("fr", "de"))

    def test_ui_write_during_default_transaction_waits_then_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            write_config({LANGUAGE_DEFAULTS_PENDING: True}, path)
            snapshot_read, ui_started, ui_done, release = (threading.Event() for _ in range(4))
            errors = []

            def defaults(latest):
                snapshot_read.set()
                if not release.wait(2):
                    raise TimeoutError("test transaction did not release")
                return apply_pending_language_defaults(latest, "en")

            def backend():
                try:
                    update_config(defaults, path)
                except Exception as exc:
                    errors.append(exc)

            def ui():
                ui_started.set()
                try:
                    update_control(
                        {
                            "primary": "fr",
                            "secondary": "de",
                            "line_gap": 9,
                            "experimental_primary": True,
                        },
                        path,
                    )
                except Exception as exc:
                    errors.append(exc)
                finally:
                    ui_done.set()

            first = threading.Thread(target=backend)
            second = threading.Thread(target=ui)
            first.start()
            try:
                self.assertTrue(snapshot_read.wait(1))
                second.start()
                self.assertTrue(ui_started.wait(1))
                self.assertFalse(
                    ui_done.wait(0.05),
                    "UI read/merge/write must share the backend transaction lock",
                )
            finally:
                release.set()
                first.join(2)
                if second.ident is not None:
                    second.join(2)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertFalse(errors)
            persisted = read_config(path)
            self.assertEqual((persisted["primary"], persisted["secondary"]), ("fr", "de"))
            self.assertEqual(persisted["line_gap"], 9)
