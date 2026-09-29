import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sora_bilingual.game.native_runtime import exact_dictionary


class NativeDictionaryTests(unittest.TestCase):
    def test_exit_closes_owner_and_detaches_eternalized_session_when_disable_ack_is_lost(self):
        from sora_bilingual.game.native_runtime import NativeLabels
        from unittest.mock import Mock

        native = NativeLabels(lambda _: None)
        native.control = Mock()
        native.eternalized = True
        native.control.disable.side_effect = OSError("lost ACK")
        native.session = Mock()
        client, session = native.control, native.session
        native.script = SimpleNamespace(
            exports_sync=SimpleNamespace(disable=Mock(side_effect=OSError("lost ACK")))
        )
        with self.assertRaisesRegex(OSError, "lost ACK"):
            native.park()
        client.close.assert_called_once()
        session.detach.assert_called_once()
        self.assertIsNone(native.control)
        self.assertIsNone(native.session)

    def test_cancelled_connection_never_attaches_to_game(self):
        from sora_bilingual.game.native_runtime import NativeLabels
        from concurrent.futures import CancelledError
        import threading

        cancel = threading.Event()
        cancel.set()
        with patch("sora_bilingual.game.native_runtime.frida.attach") as attach:
            with self.assertRaises(CancelledError):
                NativeLabels(lambda _: None).attach(42, "sora_2nd.exe", cancel=cancel)
            attach.assert_not_called()

    def test_auto_attach_waits_for_text_manager_before_installing_hooks(self):
        from sora_bilingual.game.native_runtime import NativeLabels

        calls = []
        ready = iter((False, False, True))

        def readiness():
            calls.append("ready")
            return next(ready)

        probe = SimpleNamespace(
            load=lambda: calls.append("probe_load"),
            unload=lambda: calls.append("probe_unload"),
            exports_sync=SimpleNamespace(ready=readiness),
        )
        agent = SimpleNamespace(
            on=lambda *_: None,
            load=lambda: calls.append("agent_load"),
            eternalize=lambda: calls.append("eternalize"),
            exports_sync=SimpleNamespace(configure=lambda *_: calls.append("configure")),
        )
        scripts = iter((probe, agent))
        session = SimpleNamespace(
            on=lambda *_: None, create_script=lambda _, **kwargs: next(scripts)
        )
        with (
            patch(
                "sora_bilingual.game.native_runtime.native_report",
                return_value={"text_table_global": 1},
            ),
            patch("sora_bilingual.game.native_runtime.frida.attach", return_value=session),
            patch("sora_bilingual.game.agent_control.reconnect", return_value=None),
            patch("sora_bilingual.game.agent_control.publish", return_value=agent.exports_sync),
            patch("sora_bilingual.game.agent_control.reserve"),
        ):
            NativeLabels(lambda _: None).attach(42, "unused")
        self.assertEqual(
            calls,
            [
                "probe_load",
                "ready",
                "ready",
                "ready",
                "probe_unload",
                "agent_load",
                "eternalize",
                "configure",
            ],
        )

    def test_partial_startup_releases_backend_without_unloading_resident_script(self):
        from sora_bilingual.game.native_runtime import NativeLabels
        from unittest.mock import Mock

        script, session = Mock(), Mock()
        session.create_script.return_value = script
        native = NativeLabels(lambda _: None)
        with (
            patch("sora_bilingual.game.native_runtime.frida.attach", return_value=session),
            patch("sora_bilingual.game.agent_control.reconnect", return_value=None),
            patch("sora_bilingual.game.agent_control.reserve"),
            patch(
                "sora_bilingual.game.agent_control.publish", side_effect=OSError("endpoint failed")
            ),
        ):
            with self.assertRaisesRegex(OSError, "endpoint failed"):
                native.attach(42, "unused", report={})
        script.eternalize.assert_called_once()
        self.assertTrue(native.park())
        script.exports_sync.disable.assert_called()
        session.detach.assert_called_once()
        script.unload.assert_not_called()

    def test_conflicting_translation_is_not_injected(self):
        entries = [{"texts": {"ja": "a", "zh-Hans": "一"}}, {"texts": {"ja": "b", "zh-Hans": "一"}}]
        self.assertNotIn("一", exact_dictionary(entries, "zh-Hans", "ja"))

    def test_missing_language_cannot_borrow_another_keys_pair(self):
        entries = [
            {"texts": {"ja": "a", "zh-Hans": "一"}},
            {"texts": {"en": "one", "zh-Hans": "一"}},
        ]
        self.assertNotIn("一", exact_dictionary(entries, "zh-Hans", "ja"))

    def test_preserves_native_markup_and_freely_reverses_pair(self):
        entries = [{"texts": {"ja": "<C1>薬", "zh-Hans": "<C1>药", "en": "Medicine"}}]
        self.assertEqual(exact_dictionary(entries, "ja", "zh-Hans")["Medicine"], "<C1>薬\n<C1>药")

    def test_annotation_rejects_nested_tags_and_newlines(self):
        entries = [
            {"texts": {"ja": "ティアの薬", "zh-Hans": "回复药"}},
            {"texts": {"ja": "<R>薬</Rくすり>", "zh-Hans": "药"}},
            {"texts": {"ja": "一\n二", "zh-Hans": "一二"}},
        ]
        result = exact_dictionary(entries, "zh-Hans", "ja", "annotation")
        self.assertEqual(result["回复药"], "<R>回复药</Rティアの薬>")
        self.assertNotIn("药", result)
        self.assertNotIn("一二", result)

    def test_missing_worker_cache_never_commits_a_null_model(self):
        from sora_bilingual.game.native_runtime import NativeLabels

        calls = []
        native = NativeLabels(lambda _: None)
        native.script = SimpleNamespace(
            exports_sync=SimpleNamespace(modelbegin=lambda *_: calls.append("begin"))
        )
        with patch(
            "sora_bilingual.localization.model_wire.prepare_wire", side_effect=ValueError("missing")
        ):
            with self.assertRaises(ValueError):
                native.load(None, {"enabled": True}, "annotation", cache_path="missing.json")
        self.assertEqual(calls, [])
