import hashlib
import binascii
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from sora_bilingual.localization.runtime_identity import (
    _compile_history_markers,
    _dedupe_call_entries,
    _history_marker,
    compile_script_identities,
    script_signature,
)
from sora_bilingual.localization.resources import Called
from sora_bilingual.config.locales import LANGUAGES


class FakeArchive:
    entries = {"script_sc/scena/test.dat": (0, 512)}
    data = None
    reads = []

    def __init__(self, *args):
        pass

    def read(self, *args):
        self.reads.append(args)
        return self.data

    def close(self):
        pass


class RuntimeIdentityTests(unittest.TestCase):
    def test_history_marker_compiler_keeps_operator_12_and_dynamic_speakers(self):
        static = Called(
            None,
            3,
            (("int", 5), ("int", 0), ("int", 1), ("int", 11), ("int", 101), ("string", "同一。")),
        )
        dynamic = Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 0),
                ("var", None),
                ("int", 12),
                ("int", 102),
                ("string", "动态。"),
            ),
        )
        self.assertEqual(_history_marker(static), 101)
        self.assertEqual(_history_marker(dynamic), 102)
        for speaker in (11, 12):
            self.assertEqual(
                _history_marker(
                    Called(
                        None,
                        3,
                        (
                            ("int", 5),
                            ("int", 0),
                            ("int", speaker),
                            ("int", 11),
                            ("int", 33620),
                            ("string", "同一。"),
                        ),
                    )
                ),
                33620,
            )
        for operand in (11, 12):
            self.assertEqual(
                _history_marker(
                    Called(
                        None,
                        3,
                        (
                            ("int", 5),
                            ("int", 6),
                            ("int", 1),
                            ("int", 14),
                            ("int", 15),
                            ("int", 11),
                            ("int", operand),
                            ("string", "同一。"),
                        ),
                    )
                ),
                operand,
            )
        self.assertEqual(
            _history_marker(
                Called(
                    None,
                    3,
                    (
                        ("int", 5),
                        ("int", 19),
                        ("int", 1),
                        ("int", 11),
                        ("int", 0x10000),
                        ("string", "同一。"),
                    ),
                )
            ),
            0x10000,
        )
        self.assertIsNone(
            _history_marker(
                Called(
                    None,
                    3,
                    (
                        ("int", 5),
                        ("int", 7),
                        ("int", 1),
                        ("int", 11),
                        ("int", 33620),
                        ("string", "同一。"),
                    ),
                )
            )
        )
        self.assertIsNone(
            _history_marker(
                Called(
                    None,
                    3,
                    (
                        ("int", 5),
                        ("int", 0),
                        ("int", 1),
                        ("int", 17),
                        ("int", 11),
                        ("int", 11),
                        ("int", 33620),
                        ("string", "后缀。"),
                    ),
                )
            )
        )
        self.assertIsNone(
            _history_marker(Called(None, 3, (("int", 5), ("int", 0), ("int", 11), ("int", 0))))
        )
        entries = []
        for called, text in enumerate(("同一。", "动态。")):
            entries.append(
                {
                    "key": f"script/scena/test.dat/Talk/called/{called}/assembled_dialogue",
                    "texts": {locale: text for locale in LANGUAGES},
                    "display_role": "dialogue",
                }
            )
        script = SimpleNamespace(functions={"Talk": SimpleNamespace(called=(static, dynamic))})
        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive),
            patch(
                "sora_bilingual.localization.runtime_identity._logical_script_entries",
                return_value={"script/scena/test.dat": "unused"},
            ),
            patch("sora_bilingual.localization.runtime_identity.parse_scp", return_value=script),
            patch(
                "sora_bilingual.localization.speaker_context.read_speaker_names",
                return_value={1: "甲"},
            ),
        ):
            result = _compile_history_markers("unused", entries)
        self.assertEqual(len(result["101"]), len(LANGUAGES))
        self.assertTrue(all(row[2] == "甲" for row in result["101"]))
        self.assertEqual(len(result["102"]), len(LANGUAGES))
        self.assertTrue(all(row[2] is None for row in result["102"]))

    def test_history_marker_compiler_skips_catalog_unreachable_scripts(self):
        call = Called(
            None,
            3,
            (("int", 5), ("int", 0), ("int", 1), ("int", 11), ("int", 101), ("string", "同一。")),
        )
        entry = {
            "key": "script/scena/test.dat/Talk/called/0/assembled_dialogue",
            "texts": {locale: "同一。" for locale in LANGUAGES},
            "display_role": "dialogue",
        }
        script = SimpleNamespace(
            functions={
                "Talk": SimpleNamespace(called=(call,)),
                "Unrelated": SimpleNamespace(called=(call,)),
            }
        )
        FakeArchive.reads = []
        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive),
            patch(
                "sora_bilingual.localization.runtime_identity._logical_script_entries",
                return_value={
                    "script/scena/test.dat": "wanted",
                    "script/scena/unreachable.dat": "unwanted",
                },
            ),
            patch("sora_bilingual.localization.runtime_identity.parse_scp", return_value=script),
            patch(
                "sora_bilingual.localization.speaker_context.read_speaker_names",
                return_value={1: "甲"},
            ),
        ):
            result = _compile_history_markers("unused", [entry])
        self.assertEqual(
            result["101"],
            sorted(([locale, "同一。", "甲", entry["key"], 0] for locale in LANGUAGES), key=repr),
        )
        self.assertEqual(FakeArchive.reads, [("wanted",)] * len(LANGUAGES))

    def test_identical_script_bytes_with_conflicting_localizations_are_quarantined(self):
        _, entries = self.fixture()
        entries += [
            {
                "key": e["key"].replace("/test.dat/", "/clone.dat/"),
                "texts": {**e["texts"], "ja": "Different owner"},
            }
            for e in entries
        ]
        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive),
            patch.object(
                FakeArchive,
                "entries",
                {"script_sc/scena/test.dat": (0, 512), "script_sc/scena/clone.dat": (0, 512)},
            ),
        ):
            model = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        self.assertEqual(model["stats"]["conflicting_function_identities"], 1)
        self.assertTrue(
            all(
                "Talk" not in script["functions"]
                for group in model["scripts"].values()
                for script in group
            )
        )
        self.assertEqual(model["pointer_models"], {})

    def fixture(self, dynamic=False):
        data = bytearray(512)
        struct.pack_into("<4sIIIII", data, 0, b"#scp", 24, 1, 0, 0, 0)
        struct.pack_into("<I", data, 24, 192)
        data[192:201] = bytes((36, 5, 0, 2, 36, 5, 0, 2, 13))
        struct.pack_into("<II", data, 40, 2, 64)
        struct.pack_into("<I", data, 52, 0xC0000000 + 220)
        struct.pack_into("<I", data, 48, ~binascii.crc32(b"Talk") & 0xFFFFFFFF)
        data[220:225] = b"Talk\0"
        for i, offset in enumerate((256, 280)):
            struct.pack_into("<IHHI", data, 64 + i * 12, 0xFFFFFFFF, 3, 4, 88 + i * 40)
            for j, value in enumerate((0x40000005, 0x40000000, 0x40000001, 0xC0000000 + offset)):
                struct.pack_into(
                    "<II",
                    data,
                    88 + i * 40 + j * 8,
                    0 if dynamic and j == 2 else value,
                    2 if dynamic and j == 2 else 0,
                )
            value = "好。".encode() + b"\0"
            data[offset : offset + len(value)] = value
        entries = [
            {
                "key": f"script/scena/test.dat/Talk/called/{i}/arg/3",
                "texts": {"zh-Hans": "好。", "ja": t},
            }
            for i, t in enumerate(("はい。", "よし。"))
        ]
        FakeArchive.data = bytes(data)
        return bytes(data), entries

    def test_source_equality_does_not_merge_distinct_script_offsets(self):
        data, entries = self.fixture()
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        fn = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertNotIn("好。", fn["model"]["pairs"])
        self.assertEqual(
            fn["calls"][f"{0x40000001},{0xC0000000 + 256}"]["model"]["pairs"]["好。"],
            ("好。", "はい。"),
        )
        self.assertEqual(
            fn["calls"][f"{0x40000001},{0xC0000000 + 280}"]["model"]["pairs"]["好。"],
            ("好。", "よし。"),
        )

    def test_style_normalization_conflict_also_gets_a_call_identity(self):
        data, entries = self.fixture()
        data = bytearray(data)
        for i, (offset, style) in enumerate(((256, "<S5>"), (280, "<S5><C2>"))):
            entries[i]["texts"] = {k: style + v for k, v in entries[i]["texts"].items()}
            encoded = entries[i]["texts"]["zh-Hans"].encode() + b"\0"
            data[offset : offset + len(encoded)] = encoded
        FakeArchive.data = bytes(data)
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        fn = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        call = fn["calls"][f"{0x40000001},{0xC0000000 + 256}"]
        self.assertEqual(call["model"]["pairs"]["<S5>好。"], ("<S5>好。", "<S5>はい。"))

    def test_dynamic_arguments_only_wildcard_the_unresolved_value(self):
        data, entries = self.fixture(True)
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        fn = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertEqual(set(fn["calls"]), {f"?,{0xC0000000 + 256}", f"?,{0xC0000000 + 280}"})
        self.assertEqual(result["stats"]["dynamic_calls"], 2)

    def test_empty_localized_source_is_not_a_pointer_translation(self):
        data, entries = self.fixture()
        data = bytearray(data)
        for i, offset in enumerate((256, 280)):
            data[offset] = 0
            entries[i]["texts"]["zh-Hans"] = ""
            entries[i]["texts"]["en"] = "Empty source " + str(i)
        FakeArchive.data = bytes(data)
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "en", "ja", "zh-Hans")
        self.assertNotIn("", result["pointers"])

    def test_script_identity_bounds(self):
        for data in (b"", b"#scp" + bytes(20), b"bad!" + bytes(100)):
            with self.assertRaises(ValueError):
                script_signature(data)

    def test_manifest_keeps_valid_source_script_without_a_translation_resolver(self):
        data, _entries = self.fixture()
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", [], "zh-Hans", "ja", "zh-Hans")
        record = result["manifest"][script_signature(data)][0]
        self.assertEqual(record["size"], len(data))
        self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(record["functions"], ["Talk"])

    def test_call_sites_and_records_exist_even_when_current_language_pairs_are_equal(self):
        data, entries = self.fixture()
        for entry in entries:
            entry["texts"]["ja"] = "はい。"
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        manifest = result["manifest"][script_signature(data)][0]
        sites = manifest["callSites"]["Talk"]
        self.assertEqual(sites["196"]["record"], 0)
        self.assertEqual(sites["200"]["record"], 1)
        fn = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertEqual(set(fn["records"]), {"0", "1"})
        for call in fn["records"].values():
            self.assertEqual(call["model"]["pairs"]["好。"], ("好。", "はい。"))

    def test_nonmatching_instruction_sequence_does_not_invent_pc_alignment(self):
        data, entries = self.fixture()
        data = bytearray(data)
        data[193] = 4
        FakeArchive.data = bytes(data)
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        source = result["manifest"][script_signature(data)][0]
        self.assertEqual(source["callSites"]["Talk"], {})
        self.assertEqual(sorted(source["callRecords"]["Talk"].values()), [[0], [1]])

    def test_called_ids_select_the_source_locales_record(self):
        data, _entries = self.fixture()
        entry = {
            "key": "script/scena/test.dat/Talk/called/0/assembled_dialogue/alignment/shared",
            "texts": {"zh-Hans": "中文。", "ja": "好。", "en": "English."},
            "display_role": "dialogue",
            "called_ids": {"zh-Hans": 0, "ja": 1, "en": 0},
        }
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", [entry], "zh-Hans", "en", "ja")
        function = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertEqual(set(function["records"]), {"1"})
        record_key = "script/scena/test.dat/Talk/called/0/assembled_dialogue"
        self.assertEqual(function["records"]["1"], {"key": record_key})
        pair_index = result["record_pairs"][record_key]
        self.assertEqual(
            result["record_pair_values"][pair_index],
            ("中文。", "English."),
        )
        self.assertEqual(result["source_language"], "ja")
        manifest = result["manifest"][script_signature(data)][0]
        self.assertEqual(
            manifest["recordKeys"]["Talk"]["1"],
            {"key": record_key, "source": "好。"},
        )

        without_target = {**entry, "texts": {"zh-Hans": "中文。", "ja": "好。"}}
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            target_missing = compile_script_identities(
                "unused", [without_target], "zh-Hans", "en", "ja"
            )
        manifest = target_missing["manifest"][script_signature(data)][0]
        self.assertEqual(
            manifest["recordKeys"]["Talk"]["1"],
            {"key": record_key, "source": "好。"},
            "source provenance must not depend on the selected target pair",
        )
        self.assertNotIn(record_key, target_missing["record_pairs"])

        missing = {**entry, "called_ids": {"zh-Hans": 0, "en": 0}}
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", [missing], "zh-Hans", "en", "ja")
        function = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertEqual(function["records"], {}, "missing source ordinals must fail closed")
        self.assertIn(
            record_key,
            result["record_pairs"],
            "a retained old-locale identity still needs its target pair after a source switch",
        )

    def test_two_source_calls_cannot_share_one_canonical_record_key(self):
        data, _entries = self.fixture()
        entries = [
            {
                "key": f"script/scena/test.dat/Talk/called/0/assembled_dialogue/alignment/{call}",
                "texts": {"zh-Hans": "中文。", "ja": "好。", "en": "English."},
                "display_role": "dialogue",
                "called_ids": {"zh-Hans": call, "ja": call, "en": call},
            }
            for call in (0, 1)
        ]
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "en", "ja")
        manifest = result["manifest"][script_signature(data)][0]
        self.assertEqual(manifest.get("recordKeys", {}).get("Talk", {}), {})
        function = result["scripts"][script_signature(data)][0]["functions"]["Talk"]
        self.assertTrue(all("model" in record for record in function["records"].values()))

    def test_called_ids_also_select_the_source_pointer_record(self):
        data, _entries = self.fixture()
        entries = [
            {
                "key": f"script/scena/test.dat/Talk/called/{canonical}/arg/3",
                "texts": {"zh-Hans": primary, "ja": "好。", "en": secondary},
                "called_ids": {"zh-Hans": canonical, "ja": source, "en": canonical},
            }
            for canonical, source, primary, secondary in (
                (0, 1, "中文一。", "English one."),
                (1, 0, "中文二。", "English two."),
            )
        ]
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", entries, "zh-Hans", "en", "ja")
        self.assertEqual(result["pointer_models"][entries[0]["key"]]["source"], "好。")
        pointers = {
            item["key"]: item["offset"] for items in result["pointers"].values() for item in items
        }
        self.assertEqual(pointers[entries[0]["key"]], 280)
        self.assertEqual(pointers[entries[1]["key"]], 256)

    def test_same_call_complete_entry_dominates_its_partial_alignment_row(self):
        partial = {
            "key": "script/scena/test.dat/Talk/called/0/assembled_dialogue/alignment/partial",
            "texts": {"zh-Hans": "好。"},
            "display_role": "dialogue",
        }
        complete = {
            "key": "script/scena/test.dat/Talk/called/0/assembled_dialogue",
            "texts": {"zh-Hans": "好。", "ja": "はい。", "en": "Right."},
            "display_role": "dialogue",
        }
        self.assertEqual(
            _dedupe_call_entries([partial, complete], "zh-Hans", "ja", "zh-Hans"),
            [complete],
        )
