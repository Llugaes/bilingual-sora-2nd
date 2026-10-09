"""ActiveVoice display alignment retains independent native replay metadata."""

from collections import Counter
import struct
import unittest

from sora_bilingual.localization.menu_tables import SCHEMAS, record_identity, sections
from sora_bilingual.localization.table_alignment import align_record_sections


def voice_table(replay=(300,), *, speaker=0, condition=7, voice=800, group=39):
    data = bytearray(88 + 128 * 4)
    struct.pack_into("<4sI64sIIII", data, 0, b"#TBL", 1, b"ActiveVoiceTableData", 0, 88, 128, 4)
    for ordinal in range(4):
        at = 88 + ordinal * 128
        struct.pack_into("<I", data, at, group)
        for offset, values, width in (
            (8, (speaker,), 2),
            (48, (condition,), 2),
            (64, (), 2),
            (80, replay if not ordinal else (), 2),
            (96, (voice + ordinal,), 4),
        ):
            struct.pack_into("<QQ", data, at + offset, len(data), len(values))
            for value in values:
                data.extend(value.to_bytes(width, "little"))
        for offset, text in ((24, ""), (40, ""), (112, f"body {ordinal}")):
            struct.pack_into("<Q", data, at + offset, len(data))
            data.extend(text.encode() + b"\0")
    return bytes(data)


def align(left, right):
    files = {"ja": left, "zh-Hans": right}
    audit = {"counters": Counter(), "diagnostics": []}
    return align_record_sections(
        files,
        {l: sections(d) for l, d in files.items()},
        SCHEMAS["ActiveVoiceTableData"],
        path="table/t_active_voice.tbl",
        prefix="table/t_active_voice.tbl",
        kind="ActiveVoiceTableData",
        occurrence=0,
        audit=audit,
    ), audit


class ActiveVoiceAlignmentTests(unittest.TestCase):
    def test_replay_flags_do_not_split_the_whole_display_sequence(self):
        left, right = voice_table(), voice_table((301,))
        self.assertNotEqual(
            record_identity(left, 88, "ActiveVoiceTableData", SCHEMAS["ActiveVoiceTableData"], 600),
            record_identity(
                right, 88, "ActiveVoiceTableData", SCHEMAS["ActiveVoiceTableData"], 600
            ),
        )
        entries, audit = align(left, right)
        self.assertEqual(len(entries), 4)
        self.assertTrue(all(set(e["texts"]) == {"ja", "zh-Hans"} for e in entries))
        self.assertNotEqual(
            entries[0]["table_record_identities"]["ja"],
            entries[0]["table_record_identities"]["zh-Hans"],
        )
        self.assertTrue(any(d["reason"] == "localized_replay_flags" for d in audit["diagnostics"]))

    def test_replay_flag_count_is_non_display_but_bounds_are_still_checked(self):
        entries, _ = align(voice_table(), voice_table((301, 302)))
        self.assertEqual(len(entries), 4)
        broken = bytearray(voice_table())
        struct.pack_into("<Q", broken, 88 + 80, 1)
        with self.assertRaises(ValueError):
            align(voice_table(), bytes(broken))

    def test_other_conditions_actors_voices_and_conversations_stay_distinct(self):
        for change in ({"speaker": 1}, {"condition": 8}, {"voice": 801}, {"group": 40}):
            with self.subTest(change=change):
                entries, audit = align(voice_table(), voice_table(**change))
                self.assertEqual(entries, [])
                self.assertTrue(audit["diagnostics"])

    def test_partial_language_sequence_has_an_observable_missing_peer(self):
        files = {"ja": voice_table(), "en": voice_table(), "zh-Hans": voice_table(condition=8)}
        audit = {"counters": Counter(), "diagnostics": []}
        entries = align_record_sections(
            files,
            {l: sections(d) for l, d in files.items()},
            SCHEMAS["ActiveVoiceTableData"],
            path="table/t_active_voice.tbl",
            prefix="table/t_active_voice.tbl",
            kind="ActiveVoiceTableData",
            occurrence=0,
            audit=audit,
        )
        self.assertEqual(len(entries), 4)
        missing = [
            d for d in audit["diagnostics"] if d["reason"] == "ordered_record_missing_languages"
        ]
        self.assertEqual(len(missing), 4)
        self.assertTrue(all(d["missing_languages"] == ["zh-Hans"] for d in missing))


if __name__ == "__main__":
    unittest.main()
