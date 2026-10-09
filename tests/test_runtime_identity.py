import hashlib
import binascii
import base64
import json
import struct
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from sora_bilingual.localization.runtime_identity import (
    _compile_history_markers,
    _active_speaker_setter_records,
    _dedupe_call_entries,
    _history_marker,
    compile_script_identities,
    compile_table_identities,
    script_signature,
)
from sora_bilingual.localization.resources import Called
from sora_bilingual.localization.menu_text import MenuTranslator
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


class FakeTableArchive:
    entries = {"table_sc/t_text.tbl": (0, 0)}
    data = None

    def __init__(self, *args):
        pass

    def read(self, path):
        if path != "table_sc/t_text.tbl":
            raise AssertionError(path)
        return self.data

    def close(self):
        pass


def text_table(rows):
    """Build the exact TextTableData pointer layout used by t_text.tbl."""
    head = 88 + 16 * len(rows)
    data = bytearray(head)
    struct.pack_into("<4sI64sIIII", data, 0, b"#TBL", 1, b"TextTableData", 0, 88, 16, len(rows))
    cursor = head
    for number, (key, value) in enumerate(rows):
        for field, text in enumerate((key, value)):
            encoded = text.encode("utf-8") + b"\0"
            struct.pack_into("<Q", data, 88 + number * 16 + field * 8, cursor)
            data.extend(encoded)
            cursor += len(encoded)
    return bytes(data)


class RuntimeIdentityTests(unittest.TestCase):
    def test_manifest_helper_argument_count_is_not_the_function_flags(self):
        data, _entries = self.fixture()
        data = bytearray(data)
        function_at = struct.unpack_from("<I", data, 4)[0]
        self.assertEqual(data[function_at + 4], 0)
        struct.pack_into("<H", data, function_at + 5, 1)
        FakeArchive.data = bytes(data)
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive):
            result = compile_script_identities("unused", [], "zh-Hans", "ja", "zh-Hans")
        record = result["manifest"][script_signature(data)][0]
        self.assertEqual(record["functions"], ["Talk"])
        self.assertEqual(sorted(record["callSites"]["Talk"]), ["196", "200"])

    def test_invalid_manifest_keeps_reason_and_never_enters_source_resolver(self):
        data, entries = self.fixture()
        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive),
            patch(
                "sora_bilingual.localization.runtime_identity._script_manifest_entry",
                side_effect=ValueError("bad declaration"),
            ),
        ):
            result = compile_script_identities("unused", entries, "zh-Hans", "ja", "zh-Hans")
        self.assertFalse(result["scripts"])
        self.assertEqual(result["stats"]["manifest_invalid_scripts"], 1)
        self.assertEqual(
            result["manifest_rejections"],
            [
                {
                    "path": "script/scena/test.dat",
                    "language": "zh-Hans",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "reason": "invalid_script_manifest",
                    "detail": "bad declaration",
                }
            ],
        )

    def test_active_speaker_setter_requires_branch_free_provenance(self):
        setter = ("女子的声音", ("Woman's Voice", "女性の声"))
        dialogue = Called(
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
        )
        wait = Called("wait_prompt", 0, ())
        function = SimpleNamespace(
            called=(
                Called("chr_set_display_name", 0, (("int", 21000), ("string", "女子的声音"))),
                dialogue,
                wait,
                dialogue,
            ),
            code_shape=(),
        )
        self.assertEqual(
            _active_speaker_setter_records(
                function, {0: setter}, {1: "record/one", 3: "record/two"}
            ),
            {"record/one": {setter}, "record/two": {setter}},
        )
        changed = SimpleNamespace(
            called=(
                function.called[0],
                Called("chr_set_display_name", 0, (("int", 21000), ("string", "女の声"))),
                dialogue,
            ),
            code_shape=(),
        )
        self.assertEqual(_active_speaker_setter_records(changed, {0: setter}, {2: "record"}), {})
        unknown = SimpleNamespace(
            called=(function.called[0], Called("unknown", 0, ()), dialogue), code_shape=()
        )
        self.assertEqual(_active_speaker_setter_records(unknown, {0: setter}, {2: "record"}), {})
        branched = SimpleNamespace(called=function.called, code_shape=(("branch", 11, 0),))
        self.assertEqual(
            _active_speaker_setter_records(branched, {0: setter}, {1: "record/one"}), {}
        )

    def test_text_table_pointer_identities_keep_stable_keys_and_same_source_variants(self):
        FakeTableArchive.data = text_table(
            (
                ("TXT_USE_HEAL_MACHINE", "休息"),
                ("TXT_TEST_A", "同文"),
                ("TXT_TEST_B", "同文"),
            )
        )
        entries = [
            {
                "key": "table/t_text.tbl/TXT_USE_HEAL_MACHINE",
                "texts": {"zh-Hans": "休息", "en": "Rest", "ja": "休憩する"},
            },
            {
                "key": "table/t_text.tbl/TXT_TEST_A",
                "texts": {"zh-Hans": "同文", "en": "First", "ja": "甲"},
            },
            {
                "key": "table/t_text.tbl/TXT_TEST_B",
                "texts": {"zh-Hans": "同文", "en": "Second", "ja": "乙"},
            },
            {
                "key": "script/scena/unpaired_rest/code/0",
                "texts": {"zh-Hans": "休息"},
            },
        ]
        global_model = MenuTranslator(entries, "en", "ja", "zh-Hans")
        self.assertNotIn("休息", global_model.pairs, "a source-only fallback must not guess")
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeTableArchive):
            model = compile_table_identities(
                "unused", entries, "en", "ja", "zh-Hans", resolved_pairs=global_model.pairs
            )
        rest = "table/t_text.tbl/TXT_USE_HEAL_MACHINE"
        self.assertEqual(model["models"][rest]["model"]["pairs"]["休息"], ("Rest", "休憩する"))
        self.assertEqual(
            {row["key"] for row in model["sources"]["同文"]},
            {"table/t_text.tbl/TXT_TEST_A", "table/t_text.tbl/TXT_TEST_B"},
        )
        self.assertEqual(
            model["models"]["table/t_text.tbl/TXT_TEST_A"]["model"]["pairs"]["同文"],
            ("First", "甲"),
        )
        self.assertEqual(
            model["models"]["table/t_text.tbl/TXT_TEST_B"]["model"]["pairs"]["同文"],
            ("Second", "乙"),
        )
        runner = r"""
const fs=require('fs');
const {TableIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),base=0x10000000,data=Buffer.from(input.data,'base64');
for(let at=88;at<88+16*input.rows;at+=16)for(const field of [0,8]) {
  const offset=Number(data.readBigUInt64LE(at+field));data.writeBigUInt64LE(BigInt(base+offset),at+field);
}
class P {
  constructor(address){this.address=address;}
  add(value){return new P(this.address+value);}
  equals(other){return this.address===other.address;}
  toString(){return this.address.toString(16);}
  readByteArray(size){const at=this.address-base;if(at<0||at+size>data.length)throw Error('unmapped');return Uint8Array.from(data.subarray(at,at+size)).buffer;}
  readPointer(){return new P(Number(data.readBigUInt64LE(this.address-base)));}
}
const ids=new TableIdentities(input.model),out={};
for(const {source,key} of input.checks) {
  const candidate=input.model.sources[source].find(row=>row.key===key);
  const context=ids.select(new P(base+candidate.offset),source);
  if(!context)throw Error('missing '+key);
  const tr=new RuntimeText(context.model);out[key]=[tr.translate(source,'primary'),tr.translate(source,'secondary'),tr.render(source,'annotation').text];
}
process.stdout.write(JSON.stringify(out));
"""
        completed = subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                {
                    "model": model,
                    "data": base64.b64encode(FakeTableArchive.data).decode(),
                    "rows": 3,
                    "checks": [
                        {"source": "休息", "key": rest},
                        {"source": "同文", "key": "table/t_text.tbl/TXT_TEST_A"},
                        {"source": "同文", "key": "table/t_text.tbl/TXT_TEST_B"},
                    ],
                },
                ensure_ascii=False,
            ),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        resolved = json.loads(completed.stdout)
        self.assertEqual(resolved[rest], ["Rest", "休憩する", "<R>Rest</R休憩する>"])
        self.assertEqual(resolved["table/t_text.tbl/TXT_TEST_A"], ["First", "甲", "<R>First</R甲>"])
        self.assertEqual(
            resolved["table/t_text.tbl/TXT_TEST_B"], ["Second", "乙", "<R>Second</R乙>"]
        )

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
        script = SimpleNamespace(
            functions={"Talk": SimpleNamespace(called=(static, dynamic), code_shape=())}
        )
        with (
            patch("sora_bilingual.localization.runtime_identity.FpacArchive", FakeArchive),
            patch(
                "sora_bilingual.localization.runtime_identity._logical_script_entries",
                return_value={"script/scena/test.dat": "unused"},
            ),
            patch("sora_bilingual.localization.language_cache.parse_scp", return_value=script),
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
                "Talk": SimpleNamespace(called=(call,), code_shape=()),
                "Unrelated": SimpleNamespace(called=(call,), code_shape=()),
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
            patch("sora_bilingual.localization.language_cache.parse_scp", return_value=script),
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
