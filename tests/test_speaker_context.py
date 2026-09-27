import unittest
import struct

from sora_bilingual.localization.speaker_context import compile_speaker_contexts, speaker_names


def dialogue(actor, target):
    return {
        "display_role": "dialogue",
        "speaker_ids": {"zh-Hans": actor, "ja": actor},
        "texts": {"zh-Hans": "<#E_0>相同的正文。", "ja": "<#E_0>" + target},
    }


class SpeakerContextTests(unittest.TestCase):
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
