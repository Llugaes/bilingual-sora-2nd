import unittest
from pathlib import Path
from unittest.mock import patch

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.game import source_language
from sora_bilingual.game.source_language import (
    SourceLanguageReferences,
    classify_runtime_values,
    detect_current_language,
    read_runtime_values,
)


def references():
    keys = ("TXT_A", "TXT_B", "TXT_C", "TXT_D")
    return SourceLanguageReferences(
        keys,
        tuple((key, tuple(f"{language}:{key}" for language in LANGUAGES)) for key in keys),
    )


class SourceLanguageTests(unittest.TestCase):
    def test_reference_cache_reuses_unchanged_eight_archive_stamp(self):
        stamp = tuple((language, f"{language}.pac", 1, 1) for language in LANGUAGES)
        rows = {
            language: {key: f"{language}:{key}" for key in ("TXT_A", "TXT_B", "TXT_C", "TXT_D")}
            for language in LANGUAGES
        }
        source_language._REFERENCE_CACHE.clear()
        try:
            with (
                patch.object(source_language, "_archive_stamp", return_value=stamp),
                patch.object(
                    source_language,
                    "_read_text_table",
                    side_effect=lambda path: rows[Path(path).stem],
                ) as read_table,
            ):
                first = source_language.load_references("game")
                second = source_language.load_references("game")
            self.assertIs(first, second)
            self.assertEqual(read_table.call_count, len(LANGUAGES))
        finally:
            source_language._REFERENCE_CACHE.clear()

    def test_unique_three_key_match_identifies_language(self):
        ref = references()
        values = {key: f"en:{key}" for key in ref.keys[:3]}
        self.assertEqual(classify_runtime_values(ref, values).language, "en")

    def test_multilingual_same_value_is_rejected(self):
        ref = SourceLanguageReferences(
            ("TXT_A", "TXT_B", "TXT_C"),
            (
                ("TXT_A", ("same", "same", "z", "h", "k", "f", "d", "s")),
                ("TXT_B", tuple(f"{language}:b" for language in LANGUAGES)),
                ("TXT_C", tuple(f"{language}:c" for language in LANGUAGES)),
            ),
        )
        result = classify_runtime_values(ref, {"TXT_A": "same", "TXT_B": "en:b", "TXT_C": "en:c"})
        self.assertEqual((result.language, result.reason), (None, "ambiguous_value"))

    def test_conflicting_key_votes_are_rejected(self):
        ref = references()
        result = classify_runtime_values(
            ref, {"TXT_A": "en:TXT_A", "TXT_B": "ja:TXT_B", "TXT_C": "en:TXT_C"}
        )
        self.assertEqual((result.language, result.reason), (None, "inconsistent_samples"))

    def test_missing_values_are_not_a_language_guess(self):
        result = classify_runtime_values(references(), {"TXT_A": "en:TXT_A"})
        self.assertEqual((result.language, result.reason), (None, "insufficient_samples"))

    def test_unready_probe_unloads_and_detaches_without_hooks(self):
        calls = []

        class Script:
            exports_sync = type("Exports", (), {"read": lambda self: {"state": "unready"}})()

            def load(self):
                calls.append("load")

            def unload(self):
                calls.append("unload")

        class Session:
            def create_script(self, source, **_):
                self.source = source
                return Script()

            def detach(self):
                calls.append("detach")

        session = Session()
        self.assertIsNone(
            read_runtime_values(
                4,
                {"text_table_global": 0x100},
                ("TXT_A",),
                attach=lambda _: session,
                wait_seconds=0,
            )
        )
        self.assertEqual(calls, ["load", "unload", "detach"])
        self.assertNotIn("Interceptor", session.source)
        self.assertNotIn("NativeFunction", session.source)

    def test_unready_table_retries_in_one_no_hook_session(self):
        calls = []

        class Script:
            exports_sync = None

            def __init__(self):
                self.reads = 0

                def read(_):
                    self.reads += 1
                    calls.append("read")
                    return (
                        {"state": "unready"}
                        if self.reads == 1
                        else {"state": "ready", "values": {"TXT_A": "ok"}}
                    )

                self.exports_sync = type(
                    "Exports",
                    (),
                    {"read": read},
                )()

            def load(self):
                calls.append("load")

            def unload(self):
                calls.append("unload")

        class Session:
            def create_script(self, source, **_):
                self.source = source
                calls.append("script")
                return Script()

            def detach(self):
                calls.append("detach")

        self.assertEqual(
            read_runtime_values(
                4,
                {"text_table_global": 0x100},
                ("TXT_A",),
                attach=lambda _: Session(),
                wait_seconds=1,
                sleep=lambda _: None,
            ),
            {"TXT_A": "ok"},
        )
        self.assertEqual(calls.count("script"), 1)
        self.assertEqual(calls.count("read"), 2)
        self.assertEqual(calls[-2:], ["unload", "detach"])

    def test_unverified_exe_does_not_attach(self):
        attached = []
        with (
            patch.object(source_language, "load_references", return_value=references()),
            patch.object(source_language, "native_report", side_effect=ValueError("wrong version")),
        ):
            result = detect_current_language(
                "game", 4, "wrong.exe", attach=lambda _: attached.append(1)
            )
        self.assertEqual((result.language, result.reason), (None, "unverified_exe"))
        self.assertEqual(attached, [])

    def test_missing_runtime_table_does_not_attach(self):
        attached = []
        with (
            patch.object(source_language, "load_references", return_value=references()),
            patch.object(source_language, "native_report", return_value={}),
        ):
            result = detect_current_language(
                "game", 4, "game.exe", attach=lambda _: attached.append(1)
            )
        self.assertEqual((result.language, result.reason), (None, "table_unready"))
        self.assertEqual(attached, [])


if __name__ == "__main__":
    unittest.main()
