import unittest
import struct
import json
import os
from pathlib import Path
import subprocess
import sys

from sora_bilingual.localization.speaker_context import (
    compile_history_contexts,
    compile_speaker_contexts,
    speaker_names,
)


def dialogue(actor, target):
    return {
        "display_role": "dialogue",
        "speaker_ids": {"zh-Hans": actor, "ja": actor},
        "texts": {"zh-Hans": "<#E_0>相同的正文。", "ja": "<#E_0>" + target},
    }


def speaker(label, target, key="script/a.dat/Talk/called/1/arg/1", **texts):
    return {
        "key": key,
        "display_role": "speaker",
        "texts": {"zh-Hans": label, "ja": target, **texts},
    }


class SpeakerContextTests(unittest.TestCase):
    def test_history_model_bytes_are_stable_without_sorting_expected(self):
        source = """
import json
from sora_bilingual.localization.speaker_context import compile_history_contexts
entries = [{"key": "script/a.dat/Talk/called/1/arg/1", "display_role": "speaker",
    "texts": {"en": "Voice", "ja": "声", "zh-Hans": "声音", "zh-Hant": "聲音", "fr": "Voix", "de": "Stimme"}},
    {"key": "script/b.dat/Talk/called/1/arg/1", "display_role": "speaker",
    "texts": {"en": "Other voice", "ja": "他の声", "zh-Hans": "声音", "zh-Hant": "聲音"}}]
print(json.dumps(compile_history_contexts(entries, {}, "en", "ja"), ensure_ascii=False))
"""
        outputs = [
            subprocess.run(
                [sys.executable, "-B", "-X", "utf8", "-c", source],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "PYTHONHASHSEED": str(seed)},
                capture_output=True,
                check=True,
                encoding="utf-8",
            ).stdout
            for seed in range(1, 11)
        ]
        self.assertTrue(
            all(value == outputs[0] for value in outputs[1:]),
            "native model bytes must be deterministic before any sorted test serialization",
        )
        model = json.loads(outputs[0])
        self.assertEqual(model["names"]["声音"], -1)
        self.assertIn("声音", model["fallback_names"])

    def test_old_history_keeps_all_source_locales_with_shared_target_pairs(self):
        texts = {
            "zh-Hans": "<#E_4>欢迎来到中央工房。",
            "zh-Hant": "<#E_4>歡迎來到中央工房。",
            "ja": "<#E_4>ようこそ中央工房。",
        }
        names = {"zh-Hans": {12: "埃里克"}, "zh-Hant": {12: "艾瑞克"}, "ja": {12: "エイリク"}}
        entry = {
            "display_role": "dialogue",
            "texts": texts,
            "speaker_ids": {locale: 12 for locale in texts},
        }
        old = compile_speaker_contexts([entry], names["zh-Hans"], "zh-Hans", "ja", "zh-Hans")
        self.assertNotIn("艾瑞克", old, "previous current-source lookup missed traditional history")
        model = compile_history_contexts([entry], names, "zh-Hans", "ja")
        expected = ("欢迎来到中央工房。", "ようこそ中央工房。")
        for value in texts.values():
            self.assertEqual(model["pairs"][model["texts"][value.split(">", 1)[1]]], expected)
        self.assertEqual(model["pairs"][model["names"]["艾瑞克"]], ("埃里克", "エイリク"))
        self.assertEqual(len(model["pairs"]), 2)

    def test_cross_locale_conflicts_stay_ambiguous_and_speakers_only_narrow(self):
        names = {
            "zh-Hans": {2: "甲", 5: "乙"},
            "zh-Hant": {2: "甲", 5: "乙"},
            "ja": {2: "A", 5: "B"},
        }
        first = dialogue(2, "第一句")
        first["texts"]["zh-Hant"] = "共同文字"
        first["speaker_ids"]["zh-Hant"] = 2
        second = dialogue(5, "另一句")
        second["texts"]["zh-Hans"] = "共同文字"
        model = compile_history_contexts([first, second], names, "zh-Hans", "ja")
        self.assertEqual(model["texts"]["共同文字"], -1)
        self.assertEqual(model["pairs"][model["speakers"]["甲"]["共同文字"]][1], "第一句")
        second["speaker_ids"]["zh-Hans"] = 2
        model = compile_history_contexts([first, second], names, "zh-Hans", "ja")
        self.assertEqual(model["speakers"]["甲"]["共同文字"], -1)

    def test_history_missing_target_cannot_borrow_another_calls_translation(self):
        names = {"zh-Hans": {2: "甲"}, "ja": {2: "A"}}
        first = dialogue(2, "別の呼び出し")
        first["key"] = "script/a.dat/Talk/called/3/assembled_dialogue"
        missing = {
            "key": "script/a.dat/Talk/called/4/assembled_dialogue",
            "display_role": "dialogue",
            "texts": {"zh-Hans": first["texts"]["zh-Hans"]},
            "speaker_ids": {"zh-Hans": 2},
        }
        model = compile_history_contexts([first, missing], names, "zh-Hans", "ja")
        self.assertEqual(model["texts"]["相同的正文。"], -1)
        self.assertEqual(model["speakers"]["甲"]["相同的正文。"], -1)
        # A partial alignment row from the SAME physical call is instead
        # dominated by that call's complete row, even if ordinals changed.
        missing["called_ids"] = {"zh-Hans": 3}
        model = compile_history_contexts([first, missing], names, "zh-Hans", "ja")
        self.assertEqual(model["pairs"][model["texts"]["相同的正文。"]][1], "別の呼び出し")

    def test_actor_identity_is_explicit_id_not_row_number_or_duplicate_costume(self):
        rows = [
            (2, "雪拉扎德"),
            (5, "阿加特"),
            (108, "理查德"),
            (108, "理查德"),
            (65535, "无固定角色"),
        ]
        data = bytearray(88 + 104 * len(rows))
        data[:4] = b"#TBL"
        struct.pack_into("<I", data, 4, 1)
        data[8:21] = b"NameTableData"
        struct.pack_into("<III", data, 76, 88, 104, len(rows))
        for number, (identity, name) in enumerate(rows):
            at = 88 + 104 * number
            struct.pack_into("<I", data, at, identity)
            struct.pack_into("<Q", data, at + 8, len(data))
            data.extend(name.encode("utf-8") + b"\0")
        self.assertEqual(speaker_names(bytes(data)), {2: "雪拉扎德", 5: "阿加特"})

    def test_names_narrow_complete_records_but_never_resolve_same_speaker_conflict(self):
        entries = [dialogue(2, "女性の台詞。"), dialogue(5, "男性の台詞。")]
        result = compile_speaker_contexts(
            entries, {2: "雪拉扎德", 5: "阿加特"}, "zh-Hans", "ja", "zh-Hans"
        )
        self.assertEqual(result["雪拉扎德"]["pairs"]["<#E_0>相同的正文。"][1], "<#E_0>女性の台詞。")
        conflicting = compile_speaker_contexts(
            entries + [dialogue(2, "異なる台詞。")],
            {2: "雪拉扎德", 5: "阿加特"},
            "zh-Hans",
            "ja",
            "zh-Hans",
        )
        self.assertNotIn("雪拉扎德", conflicting)
        renamed = compile_speaker_contexts(
            entries, {2: "同名", 5: "同名"}, "zh-Hans", "ja", "zh-Hans"
        )
        self.assertEqual(renamed, {})

    def test_unknown_or_locale_mismatched_actor_cannot_supply_a_context(self):
        mismatch = dialogue(2, "台詞。")
        mismatch["speaker_ids"]["ja"] = 5
        result = compile_speaker_contexts(
            [mismatch, dialogue(65535, "台詞。")], {2: "雪拉扎德"}, "zh-Hans", "ja", "zh-Hans"
        )
        self.assertEqual(result, {})

    def test_direct_generic_speaker_setter_supplies_history_name_pair(self):
        model = compile_history_contexts(
            [speaker("女子的声音", "女性の声", en="Woman's Voice")],
            {},
            "en",
            "ja",
        )
        self.assertEqual(
            model["pairs"][model["names"]["女子的声音"]], ("Woman's Voice", "女性の声")
        )

    def test_generic_speaker_rejects_conflicting_or_unproven_physical_setters(self):
        complete = speaker("女子的声音", "女性の声", en="Woman's Voice")
        same_setter_partial = {
            "key": complete["key"] + "/alignment/partial",
            "display_role": "speaker",
            "texts": {"zh-Hans": "女子的声音"},
        }
        model = compile_history_contexts([complete, same_setter_partial], {}, "en", "ja")
        self.assertEqual(
            model["pairs"][model["names"]["女子的声音"]], ("Woman's Voice", "女性の声")
        )
        conflict = speaker(
            "女子的声音",
            "女の声",
            "script/a.dat/Talk/called/2/arg/1",
            en="Woman's Voice",
        )
        model = compile_history_contexts([complete, conflict], {}, "en", "ja")
        self.assertEqual(model["names"]["女子的声音"], -1)
        not_a_setter = speaker(
            "旁白",
            "ナレーション",
            "script/a.dat/Talk/called/3/arg/2",
            en="Narration",
        )
        model = compile_history_contexts([not_a_setter], {}, "en", "ja")
        self.assertNotIn("旁白", model["names"])

    def test_old_history_fallback_prefers_same_speaker_and_ignores_incomplete_claims(self):
        names = {"zh-Hans": {2: "甲"}, "ja": {2: "A"}}
        first = dialogue(2, "甲訳")
        first["key"] = "script/a.dat/Talk/called/3/assembled_dialogue"
        second = dialogue(2, "乙訳")
        second["key"] = "script/a.dat/Talk/called/4/assembled_dialogue"
        partial = {
            "key": "script/a.dat/Talk/called/5/assembled_dialogue",
            "display_role": "dialogue",
            "texts": {"zh-Hans": first["texts"]["zh-Hans"]},
            "speaker_ids": {"zh-Hans": 2},
        }
        model = compile_history_contexts([second, partial, first], names, "zh-Hans", "ja")
        body = "相同的正文。"
        self.assertEqual(model["texts"][body], -1)
        self.assertEqual(model["speakers"]["甲"][body], -1)
        selected = model["pairs"][model["fallback_speakers"]["甲"][body]]
        self.assertEqual(selected, ("相同的正文。", "乙訳"))
        self.assertEqual(model["pairs"][model["fallback_texts"][body]], selected)
        reversed_model = compile_history_contexts([first, partial, second], names, "zh-Hans", "ja")
        self.assertEqual(
            reversed_model["pairs"][reversed_model["fallback_speakers"]["甲"][body]], selected
        )
        only_partial = compile_history_contexts([partial], names, "zh-Hans", "ja")
        self.assertNotIn(body, only_partial["fallback_texts"])
        self.assertNotIn("甲", only_partial["fallback_speakers"])
