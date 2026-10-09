import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.localization.language_cache import LanguageFacts, language_facts, history_script
from sora_bilingual.localization.resources import Called, Function, Script
from sora_bilingual.localization.runtime_identity import _active_speaker_setter_records
from tests.test_resources import make_scp


class LanguageCacheTests(unittest.TestCase):
    def test_notification_metadata_warm_read_keeps_declarations_and_all_call_targets(self):
        from sora_bilingual.localization.language_cache import notification_metadata

        function = Function(
            "F",
            0,
            (1, 2, 5, 9),
            (
                Called("ITEM_ADD_MESSAGE2_EV", 0, (("var", None),)),
                Called(None, 3, (("int", 5),)),
                Called("unknown", 0, ()),
            ),
            (("branch", 1, 0),),
            (),
        )
        raw = Script({"F": function, "Empty": Function("Empty", 0, (), (), (), ())})
        with tempfile.TemporaryDirectory() as temp:
            with (
                language_facts(temp) as cold,
                patch("sora_bilingual.localization.language_cache.parse_scp", return_value=raw),
            ):
                first = notification_metadata(b"raw-notification-script", "en")
            with (
                language_facts(temp) as warm,
                patch(
                    "sora_bilingual.localization.language_cache.parse_scp",
                    side_effect=AssertionError("warm notification metadata reparsed whole SCP"),
                ),
            ):
                second = notification_metadata(b"raw-notification-script", "en")
            self.assertEqual(first, second)
            self.assertEqual(first["F"].argument_types, (1, 2, 5, 9))
            self.assertEqual(first["F"].call_targets, ("ITEM_ADD_MESSAGE2_EV", None, "unknown"))
            self.assertEqual(first["Empty"].call_targets, ())
            # This narrow projection cannot masquerade as a whole parsed
            # function when checking dynamic arguments or branch bytecode.
            self.assertFalse(hasattr(first["F"], "called"))
            self.assertFalse(hasattr(first["F"], "code_shape"))
            self.assertEqual((cold.stats["misses"], warm.stats["hits"]), (1, 1))

    def test_notification_metadata_bytes_locale_rules_and_permission_are_not_reused(self):
        from sora_bilingual.localization.language_cache import notification_metadata

        raw = Script({"F": Function("F", 0, (1,), (Called("helper", 0, ()),), (), ())})
        with (
            tempfile.TemporaryDirectory() as temp,
            patch(
                "sora_bilingual.localization.language_cache.parse_scp", return_value=raw
            ) as parse,
        ):
            with language_facts(temp) as facts:
                notification_metadata(b"a", "en")
                notification_metadata(b"a", "en")
                notification_metadata(b"b", "en")
                notification_metadata(b"a", "ja")
                facts.codes["notification_metadata"] = "changed-generating-rule"
                notification_metadata(b"a", "en")
            self.assertEqual(parse.call_count, 4)
            with (
                language_facts(temp),
                patch.object(Path, "read_text", side_effect=PermissionError("denied")),
            ):
                with self.assertRaises(PermissionError):
                    notification_metadata(b"a", "en")
            self.assertEqual(parse.call_count, 4)

    def test_provenance_cache_reuses_language_local_markers_and_preserves_refusal(self):
        from sora_bilingual.localization.language_cache import history_provenance
        from sora_bilingual.localization.runtime_identity import _history_function_facts

        setter = Called("chr_set_display_name", 0, (("int", 21000), ("string", "Voice")))
        dialogue = Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 6),
                ("int", 21000),
                ("int", 11),
                ("int", 31577),
                ("string", "body"),
            ),
        )
        for middle in (
            (),
            (Called("wait_prompt", 0, ()),),
            (Called("unknown", 0, (("var", None),)),),
            (Called("chr_set_display_name", 0, (("int", 21000), ("var", None))),),
        ):
            for branch in (False, True):
                calls = (setter, *middle, dialogue)
                fn = Function("Talk", 0, (), calls, (("branch", 11, 0),) if branch else (), ())
                record = "record"
                old = _active_speaker_setter_records(
                    fn, {0: ("Voice", ("p", "s"))}, {len(calls) - 1: record}
                )
                projected = _history_function_facts(fn)
                links = projected["speaker_links"]
                self.assertEqual(bool(links), bool(old))
                self.assertEqual(projected["markers"][str(len(calls) - 1)], ["body", 31577, 21000])
                if links:
                    self.assertEqual(links[str(len(calls) - 1)], [0, "Voice"])
        raw = Script({"Talk": fn})
        with tempfile.TemporaryDirectory() as temp:
            with (
                language_facts(temp) as first,
                patch("sora_bilingual.localization.language_cache.parse_scp", return_value=raw),
            ):
                cold = history_provenance(b"raw script bytes", "ja")
                self.assertEqual(first.stats["misses"], 1)
            for locale in ("ja", "ja"):
                with (
                    language_facts(temp) as warm,
                    patch(
                        "sora_bilingual.localization.language_cache.parse_scp",
                        side_effect=AssertionError("reparsed cached language"),
                    ),
                ):
                    self.assertEqual(history_provenance(b"raw script bytes", locale), cold)
                    self.assertEqual(warm.stats["hits"], 1)

    def test_locale_bytes_code_and_corruption_have_independent_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            facts = LanguageFacts(temp)
            calls = []

            def build():
                calls.append(True)
                return {"exact": "原串", "rows": [1, 2]}

            facts.get("ja", "history", b"a", build)
            facts.get("ja", "history", b"a", build)
            self.assertEqual(len(calls), 1)
            facts.get("en", "history", b"a", build)
            facts.get("ja", "history", b"b", build)
            facts.codes["history"] = "changed-rule"
            facts.get("ja", "history", b"a", build)
            self.assertEqual(len(calls), 4)
            path = next(
                p
                for p in Path(temp).rglob("*.json")
                if json.loads(p.read_text("utf-8"))["identity"][2] == "changed-rule"
            )
            record = json.loads(path.read_text("utf-8"))
            record["value"]["exact"] = "错误"
            path.write_text(json.dumps(record), "utf-8")
            self.assertEqual(facts.get("ja", "history", b"a", build)["exact"], "原串")
            self.assertEqual(facts.stats["rejected"], 1)

    def test_projection_preserves_all_calls_dynamic_parameters_and_branch_refusal(self):
        data = make_scp("日本語")
        with tempfile.TemporaryDirectory() as temp:
            for branch in (False, True):
                calls = (
                    Called("chr_set_display_name", 0, (("int", 21000), ("string", "女子的声音"))),
                    Called("unknown", 0, (("var", None), ("expr", None))),
                    Called(
                        None,
                        3,
                        (
                            ("int", 5),
                            ("int", 6),
                            ("int", 21000),
                            ("int", 11),
                            ("int", 31577),
                            ("string", "正文"),
                        ),
                    ),
                )
                fn = Function("Talk", 0, (), calls, (("branch", 11, 0),) if branch else (), ())
                raw = Script({"Talk": fn, "Unused": Function("Unused", 0, (), (), (), ())})
                payload = data + bytes([branch])
                with (
                    language_facts(temp) as first,
                    patch("sora_bilingual.localization.language_cache.parse_scp", return_value=raw),
                ):
                    projected = history_script(payload, "ja")
                    self.assertEqual(first.stats["misses"], 1)
                with (
                    language_facts(temp) as second,
                    patch(
                        "sora_bilingual.localization.language_cache.parse_scp",
                        side_effect=AssertionError("reparse"),
                    ),
                ):
                    projected = history_script(payload, "ja")
                    self.assertEqual(second.stats["hits"], 1)
                self.assertNotIn("Unused", projected.functions)
                value = projected.functions["Talk"]
                self.assertEqual(value.called, fn.called)
                self.assertEqual(value.has_branch, branch)
                setters = {0: ("女子的声音", ("Woman's Voice", "女性の声"))}
                self.assertEqual(
                    _active_speaker_setter_records(value, setters, {2: "record"}),
                    _active_speaker_setter_records(fn, setters, {2: "record"}),
                )
                self.assertEqual(_active_speaker_setter_records(value, setters, {2: "record"}), {})

    def test_denied_cache_read_is_not_rebuilt_or_rerouted(self):
        with tempfile.TemporaryDirectory() as temp:
            facts = LanguageFacts(temp)
            with patch.object(Path, "read_text", side_effect=PermissionError("restricted")):
                with self.assertRaises(PermissionError):
                    facts.get("ja", "history", b"a", lambda: self.fail("must not rebuild"))
