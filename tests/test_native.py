import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sora_bilingual.game.native_runtime import exact_dictionary


class NativeDictionaryTests(unittest.TestCase):
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
        ):
            NativeLabels(lambda _: None).attach(42, "unused")
        self.assertEqual(
            calls,
            ["probe_load", "ready", "ready", "ready", "probe_unload", "agent_load", "configure"],
        )

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
