import binascii
import json
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from sora_bilingual.localization import resources


class SpeakerRecordAlignmentTests(unittest.TestCase):
    def test_speaker_keeps_each_locales_physical_called_id_across_proven_gap(self):
        def function(text, extra=False):
            calls = (resources.Called("chr_set_display_name", 0, (("int", 133), ("string", text))),)
            if extra:
                calls = (resources.Called("wait_prompt", 0, ()),) + calls
            return resources.Function("Scene", 0, (), calls, (), ())

        rows = resources.align_functions(
            "script/a.dat",
            "Scene",
            {
                "en": function("Man's Voice", True),
                "ja": function("男性の声"),
            },
            {"counters": Counter()},
        )
        speaker = next(row for row in rows if row.get("display_role") == "speaker")
        self.assertEqual(speaker["called_ids"], {"en": 1, "ja": 0})
        self.assertIn("/called/1/arg/1", speaker["key"])

    def test_proven_speaker_prefix_survives_later_unrelated_locale_difference(self):
        def name(text, actor=133):
            return resources.Called("chr_set_display_name", 0, (("int", actor), ("string", text)))

        def function(*calls):
            return resources.Function("Scene", 0, (), calls, (), ())

        reward_a = resources.Called(
            "ITEM_ADD_MESSAGE_EV", 0, (("int", 228), ("string", "を受け取った。"))
        )
        reward_b = resources.Called(
            "ITEM_ADD_MESSAGE2_EV", 0, (("int", 228), ("string", "拿到了"), ("string", "。"))
        )
        rows = resources.align_functions(
            "script/a.dat",
            "Scene",
            {
                "ja": function(name("男性の声"), reward_a),
                "zh-Hans": function(name("男子的声音"), reward_b),
            },
            {"counters": Counter()},
        )
        speakers = [row for row in rows if row.get("display_role") == "speaker"]
        self.assertEqual(len(speakers), 1)
        self.assertEqual(speakers[0]["texts"], {"ja": "男性の声", "zh-Hans": "男子的声音"})
        self.assertEqual(speakers[0]["called_ids"], {"ja": 0, "zh-Hans": 0})
        for left, right in [
            (function(name("男性の声", 134), reward_a), function(name("男子的声音"), reward_b)),
            (
                function(reward_a, name("男性の声")),
                function(
                    resources.Called(
                        "ITEM_ADD_MESSAGE2_EV",
                        0,
                        (("int", 229), ("string", "拿到了"), ("string", "。")),
                    ),
                    name("男子的声音"),
                ),
            ),
        ]:
            rejected = resources.align_functions(
                "script/a.dat", "Scene", {"ja": left, "zh-Hans": right}, {"counters": Counter()}
            )
            self.assertFalse([row for row in rejected if row.get("display_role") == "speaker"])

        rows = resources.align_functions(
            "script/a.dat",
            "Scene",
            {
                "ja": function(reward_a, name("男性の声")),
                "zh-Hans": function(reward_b, name("男子的声音")),
            },
            {"counters": Counter()},
        )
        self.assertTrue(any(row.get("display_role") == "speaker" for row in rows))

    def test_setter_flag_preserves_name_payload_but_not_different_actor(self):
        def fn(text, tail=(), actor=65534):
            call = resources.Called(
                "chr_set_display_name", 0, (("int", actor), ("string", text)) + tail
            )
            return resources.Function("Init", 0, (), (call,), (), ())

        for tail, actor, accepted in [
            ((("int", 1),), 65534, True),
            ((("int", 2),), 65534, False),
            ((("int", 1),), 65533, False),
        ]:
            rows = resources.align_functions(
                "script/a.dat",
                "Init",
                {"zh-Hans": fn("名称"), "ja": fn("名前", tail, actor)},
                {"counters": Counter()},
            )
            self.assertEqual(any(row.get("display_role") == "speaker" for row in rows), accepted)


def make_scp(
    text: str = "<b>Hello</b>",
    *,
    alternate_argument: bool = False,
    opcode: int = 13,
    code: bytes | None = None,
) -> bytes:
    """A minimal, valid one-function SCP with one called text argument."""
    func_at, called_at, args_at, name_at, text_at, code_at = 24, 56, 68, 100, 112, 160
    code = bytes((opcode,)) if code is None else code
    data = bytearray(code_at + len(code))
    struct.pack_into("<4sIIIII", data, 0, b"#scp", func_at, 1, called_at, 0, 0)
    name = "Talk".encode()
    crc = ~binascii.crc32(name) & 0xFFFFFFFF
    struct.pack_into(
        "<IBHBIIIIII",
        data,
        func_at,
        code_at,
        0,
        0,
        0,
        0,
        0,
        1,
        called_at,
        crc,
        0xC0000000 | name_at,
    )
    struct.pack_into("<IHHI", data, called_at, 0, 0, 1, args_at)
    if alternate_argument:
        struct.pack_into("<II", data, args_at, 0, 1)  # a nested-call argument
    else:
        struct.pack_into("<II", data, args_at, 0xC0000000 | text_at, 0)
    data[name_at : name_at + len(name) + 1] = name + b"\0"
    encoded = text.encode()
    data[text_at : text_at + len(encoded) + 1] = encoded + b"\0"
    data[code_at:] = code
    return bytes(data)


def make_scp_calls(texts: tuple[str, ...], *, first_argument_is_call: bool = False) -> bytes:
    """A minimal SCP whose complete called sequence can be varied."""
    func_at, called_at = 24, 56
    args_at, name_at, text_at, code_at = called_at + len(texts) * 12, 128, 160, 512
    data = bytearray(code_at + 1)
    struct.pack_into("<4sIIIII", data, 0, b"#scp", func_at, 1, called_at, 0, 0)
    name = b"Talk"
    struct.pack_into(
        "<IBHBIIIIII",
        data,
        func_at,
        code_at,
        0,
        0,
        0,
        0,
        0,
        len(texts),
        called_at,
        ~binascii.crc32(name) & 0xFFFFFFFF,
        0xC0000000 | name_at,
    )
    data[name_at : name_at + len(name) + 1] = name + b"\0"
    cursor = text_at
    for index, text in enumerate(texts):
        arg_at = args_at + index * 8
        struct.pack_into("<IHHI", data, called_at + index * 12, 0, 0, 1, arg_at)
        encoded = text.encode()
        if first_argument_is_call and index == 0:
            struct.pack_into("<II", data, arg_at, 0, 1)
        else:
            struct.pack_into("<II", data, arg_at, 0xC0000000 | cursor, 0)
        data[cursor : cursor + len(encoded) + 1] = encoded + b"\0"
        cursor += len(encoded) + 1
    data[code_at] = 13
    return bytes(data)


def make_fpac(path: str, contents: bytes) -> bytes:
    name = path.encode() + b"\0"
    name_at = 48
    data_at = name_at + len(name)
    result = bytearray(data_at + len(contents))
    struct.pack_into("<4sIII", result, 0, b"FPAC", 1, data_at, 1)
    struct.pack_into("<IIQQQ", result, 16, 0, 0, name_at, len(contents), data_at)
    result[name_at:data_at] = name
    result[data_at:] = contents
    return bytes(result)


def write_game(
    root: Path,
    overrides: dict[str, bytes] | None = None,
    path: str = "script/scena/c0000.dat",
) -> None:
    folder = root / "pac" / "steam"
    folder.mkdir(parents=True)
    overrides = overrides or {}
    for language, archive in resources._ARCHIVES.items():
        scp = overrides.get(language, make_scp(f"<{language}>raw</{language}>"))
        (folder / archive).write_bytes(make_fpac(path, scp))


class ResourcesTests(unittest.TestCase):
    def test_command8_consecutive_style_controls_preserve_complete_panel(self):
        # Real LP_Capel/called/133: centered orange key hint follows the
        # signboard note, but has two style controls before its first string.
        call = resources.Called(
            None,
            3,
            tuple(("int", n) for n in (5, 8, 65535, 16, 26))
            + (
                ("string", "<c930>"),
                ("string", "\u3000"),
                ("int", 10),
                ("string", "\u3000\u3000────────────────────\u3000\u3000"),
                ("int", 10),
                ("string", "\u3000\u3000\u3000第三把钥匙再次回到城市里。\u3000\u3000"),
                ("int", 10),
                ("string", "\u3000\u3000抬头仰望“尖帽子的三兄弟”吧。\u3000"),
            ),
        )
        self.assertEqual(
            resources.assembled_dialogue(call),
            "<c930>\u3000\n\u3000\u3000────────────────────\u3000\u3000\n"
            "\u3000\u3000\u3000第三把钥匙再次回到城市里。\u3000\u3000\n"
            "\u3000\u3000抬头仰望“尖帽子的三兄弟”吧。\u3000",
        )

    def test_command8_literal_rich_text_assembles_but_dynamic_tail_is_rejected(self):
        actual = resources.Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 8),
                ("int", 65535),
                ("int", 26),
                ("string", "<c930>"),
                ("string", ""),
                ("int", 10),
                ("string", "项目：游击士协会招牌"),
                ("int", 10),
                ("string", "怪盗绅士布卢布兰施展天才本领、从无能的游击士协会"),
                ("int", 10),
                ("string", "蔡斯分部的屋檐上取走的金属制招牌。几乎没有经济价"),
                ("int", 10),
                ("string", "值，却能给予协会相关人士难以估计的打击，读到这里"),
                ("int", 10),
                ("string", "的各位想必也正因这份屈辱而浑身颤抖吧。噢，话先说"),
                ("int", 10),
                ("string", "到这。差不多该提示下一把钥匙的所在地了。"),
            ),
        )
        self.assertEqual(
            resources.assembled_dialogue(actual),
            "<c930>\n项目：游击士协会招牌\n怪盗绅士布卢布兰施展天才本领、从无能的游击士协会\n蔡斯分部的屋檐上取走的金属制招牌。几乎没有经济价\n值，却能给予协会相关人士难以估计的打击，读到这里\n的各位想必也正因这份屈辱而浑身颤抖吧。噢，话先说\n到这。差不多该提示下一把钥匙的所在地了。",
        )
        from dataclasses import replace

        self.assertIsNone(
            resources.assembled_dialogue(replace(actual, args=actual.args[:-1] + (("var", None),)))
        )
        # mp0054_01/EV_07_05_00_END/called/2: command-8 locale metadata
        # may end at args[2], leaving the colour markup as the first text arg.
        colour_at_arg3 = resources.Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 8),
                ("int", 65535),
                ("string", "<C1>"),
                ("string", "由于约书亚正式回归到队伍中，"),
                ("int", 10),
                ("string", "勇猛攻击“爆裂猛攻”"),
                ("int", 10),
                ("string", "已强化为“<C2>全面爆裂猛攻<C1>”。"),
            ),
        )
        self.assertEqual(
            resources.assembled_dialogue(colour_at_arg3),
            "<C1>由于约书亚正式回归到队伍中，\n勇猛攻击“爆裂猛攻”\n已强化为“<C2>全面爆裂猛攻<C1>”。",
        )
        self.assertIsNone(
            resources.assembled_dialogue(
                replace(colour_at_arg3, args=colour_at_arg3.args + (("int", 17),))
            )
        )
        for dynamic_prefix in (("var", None), ("call", None)):
            self.assertIsNone(
                resources.assembled_dialogue(
                    replace(
                        colour_at_arg3,
                        args=colour_at_arg3.args[:2] + (dynamic_prefix,) + colour_at_arg3.args[3:],
                    )
                )
            )
        self.assertIsNone(
            resources.assembled_dialogue(
                replace(colour_at_arg3, args=colour_at_arg3.args[:2] + colour_at_arg3.args[3:])
            )
        )

    def test_command8_integer_item_references_before_literal_are_not_metadata(self):
        # Actual JA mp6010_01/EV_00_06_00/called/83: item references produce
        # visible text before the final literal. Never admit only its suffix.
        args = tuple(("int", n) for n in (5, 8, 65535, 16, 17, 500, 10, 17, 1000, 10, 17, 1100))
        call = resources.Called(None, 3, args + (("string", "を装備した。"),))
        self.assertIsNone(resources.assembled_dialogue(call))
        for style in (13, 16, 26, 28):
            call = resources.Called(
                None, 3, tuple(("int", n) for n in (5, 8, 65535, style)) + (("string", "Text"),)
            )
            self.assertEqual(resources.assembled_dialogue(call), "Text")

    def test_command8_window_controls_and_voice_do_not_become_display_text(self):
        # Native message builder 0x4ad670 and command-8 callback 0x4affd0 consume
        # voice IDs and window flags without appending to the text buffer.
        for prefix in ((26, 22), (16, 26, 22), (22, 16, 28), (19, 13), (11, 30138, 19, 13)):
            with self.subTest(prefix=prefix):
                call = resources.Called(
                    None,
                    3,
                    tuple(("int", n) for n in (5, 8, 65535, *prefix))
                    + (("string", "First"), ("int", 10), ("string", "Second"), ("int", 16)),
                )
                self.assertEqual(resources.assembled_dialogue(call), "First\nSecond")
        # A known non-text opcode does not license skipping arbitrary ints,
        # an unresolved operand, or an item/number interpolation.
        for suffix in (
            (("int", 11),),
            (("int", 11), ("var", None)),
            (("int", 17), ("int", 500)),
            (("int", 99),),
        ):
            call = resources.Called(
                None,
                3,
                tuple(("int", n) for n in (5, 8, 65535, 16)) + (("string", "Text"),) + suffix,
            )
            self.assertIsNone(resources.assembled_dialogue(call))

    def test_talk_static_tail_flags_do_not_discard_complete_dialogue(self):
        # Actual command-0 tails use 25; command-6 tails use 14/15. Both
        # handlers call 0x4ad670 and callbacks only set flags for these codes.
        for command, flags in ((0, (25,)), (6, (14, 15)), (19, (25,))):
            call = resources.Called(
                None,
                3,
                tuple(("int", n) for n in (5, command, 134, 11, 29815))
                + (("string", "First"),)
                + tuple(("int", n) for n in flags)
                + (("int", 10), ("string", "Second")),
            )
            with self.subTest(command=command):
                self.assertEqual(resources.assembled_dialogue(call), "First\nSecond")

    def test_talk_dynamic_text_prefix_is_not_mistaken_for_speaker_metadata(self):
        for command, prefix in ((0, ()), (6, (("int", 11), ("int", 40603)))):
            args = (("int", 5), ("int", command), ("int", 4))
            call = resources.Called(None, 3, args + prefix + (("var", None), ("string", "suffix")))
            self.assertIsNone(resources.assembled_dialogue(call))
        # The actual speaker slot is not part of the text argument stream.
        call = resources.Called(
            None, 3, (("int", 5), ("int", 0), ("var", None), ("string", "text"))
        )
        self.assertEqual(resources.assembled_dialogue(call), "text")

    def test_dynamic_item_prefix_cannot_poison_neighbouring_static_reward_alignment(self):
        # Real pattern in mp6010_01: JA item names occur before the first
        # literal; EN interleaves them with strings. Neither is static text.
        jp_dynamic = resources.Called(
            None,
            3,
            tuple(("int", n) for n in (5, 8, 65535, 16, 17, 500)) + (("string", "を装備した。"),),
        )
        en_dynamic = resources.Called(
            None,
            3,
            (
                ("int", 5),
                ("int", 8),
                ("int", 65535),
                ("int", 16),
                ("string", "Equipped "),
                ("int", 17),
                ("int", 500),
                ("string", "."),
            ),
        )
        prefix = tuple(("int", n) for n in (5, 8, 65535, 16))
        functions = {
            language: resources.Function(
                "Reward",
                0,
                (),
                (dynamic, resources.Called(None, 3, prefix + (("string", text),))),
                (),
                (),
            )
            for language, dynamic, text in (
                ("ja", jp_dynamic, "<C5>１０００ミラ<C0>を手に入れた。"),
                ("en", en_dynamic, "Obtained <C5>1,000 mira<C0>."),
            )
        }
        rows = resources.align_functions(
            "script/a.dat", "Reward", functions, {"counters": Counter()}
        )
        assembled = [row for row in rows if "/assembled_dialogue" in row["key"]]
        self.assertEqual(len(assembled), 1)
        self.assertTrue(assembled[0]["key"].endswith("called/1/assembled_dialogue"))
        self.assertEqual(
            assembled[0]["texts"],
            {"ja": "<C5>１０００ミラ<C0>を手に入れた。", "en": "Obtained <C5>1,000 mira<C0>."},
        )

    def test_static_command8_and_talk_align_when_command8_chunking_differs(self):
        from dataclasses import replace

        talk = resources.Called(
            None,
            3,
            (("int", 5), ("int", 6), ("int", 9), ("int", 11), ("int", 10), ("string", "Continue")),
        )
        reward = resources.Called(
            None, 3, (("int", 5), ("int", 8), ("int", 65535), ("string", "<C1>Reward"))
        )
        a = resources.Function("Scene", 0, (), (reward, talk), (), ())
        b = replace(
            a,
            called=(
                replace(reward, args=reward.args[:-1] + (("string", "<C1>"), ("string", "Gift"))),
                replace(talk, args=talk.args[:-1] + (("string", "Proceed"),)),
            ),
        )

        def align(other):
            return resources.align_functions(
                "script/a.dat", "Scene", {"en": a, "fr": other}, {"counters": Counter()}
            )

        rows = align(b)
        self.assertEqual(
            [(row["key"].split("/Scene/")[1], row["texts"]) for row in rows],
            [
                (
                    "called/0/assembled_dialogue",
                    {"en": "<C1>Reward", "fr": "<C1>Gift"},
                ),
                ("called/1/assembled_dialogue", {"en": "Continue", "fr": "Proceed"}),
                ("called/1/arg/5", {"en": "Continue", "fr": "Proceed"}),
            ],
        )
        self.assertTrue(all(row["display_role"] == "dialogue" for row in rows[:2]))
        self.assertNotIn("speaker_ids", rows[0])  # command 8 has a window ID, not an actor
        self.assertEqual(rows[1]["speaker_ids"], {"en": 9, "fr": 9})
        self.assertNotIn("speaker_ids", rows[2])  # a fragment cannot identify a whole dialogue
        # A different speaker/voice rejects that dialogue while preserving the
        # other exact native ordinals.
        for slot in (2, 4):
            args = list(b.called[1].args)
            args[slot] = ("int", 99)
            rows = align(replace(b, called=(b.called[0], replace(talk, args=tuple(args)))))
            self.assertEqual(
                [row["texts"] for row in rows if row.get("called_ids")],
                [{"en": "<C1>Reward", "fr": "<C1>Gift"}],
            )
        self.assertFalse(align(replace(b, called=tuple(reversed(b.called)))))
        rows = align(replace(b, called=b.called + (reward,)))
        self.assertEqual(len([row for row in rows if row.get("called_ids")]), 2)

    def test_dialogue_records_align_only_across_proven_call_segments(self):
        from dataclasses import replace

        def talk(text, speaker=9):
            prefix = (("int", 5), ("int", 0))
            if speaker is not None:
                prefix += (("int", speaker),)
            return resources.Called(None, 3, prefix + (("string", text),))

        wait = resources.Called("wait_prompt", 0, ())

        def function(*calls):
            return resources.Function("Scene", 0, (), calls, (), ())

        # Command 0's explicit default actor 0 and an omitted actor are the
        # same native input, but only when the complete call sequence proves
        # there was no insertion, deletion, or other metadata difference.
        equal_length = {
            "en": function(talk("A"), talk("Reject", 0), talk("C")),
            "ja": function(talk("甲"), talk("除外", None), talk("丙")),
        }
        rows = resources.align_functions(
            "script/a.dat", "Scene", equal_length, {"counters": Counter()}
        )
        aligned = [row for row in rows if row.get("called_ids")]
        self.assertEqual(
            [(row["called_ids"], row["texts"]) for row in aligned],
            [
                ({"en": 0, "ja": 0}, {"en": "A", "ja": "甲"}),
                ({"en": 1, "ja": 1}, {"en": "Reject", "ja": "除外"}),
                ({"en": 2, "ja": 2}, {"en": "C", "ja": "丙"}),
            ],
        )
        self.assertEqual(aligned[1]["speaker_ids"], {"en": 0})

        # A non-default actor remains identity-bearing.  It may preserve later
        # ordinals, but the mismatched dialogue itself is never paired.
        non_default = {
            "en": function(talk("A"), talk("Reject", 9), talk("C")),
            "ja": function(talk("甲"), talk("除外", None), talk("丙")),
        }
        rows = resources.align_functions(
            "script/a.dat", "Scene", non_default, {"counters": Counter()}
        )
        aligned = [row for row in rows if row.get("called_ids")]
        self.assertEqual(
            [(row["called_ids"], row["texts"]) for row in aligned],
            [
                ({"en": 0, "ja": 0}, {"en": "A", "ja": "甲"}),
                ({"en": 2, "ja": 2}, {"en": "C", "ja": "丙"}),
            ],
        )

        # Even default-zero equivalence is rejected when another call makes
        # the complete sequence non-identical.
        unknown_tail = resources.Called("unknown", 0, ())
        not_whole = {
            "en": function(talk("A"), talk("Reject", 0), unknown_tail),
            "ja": function(talk("甲"), talk("除外", None), wait),
        }
        rows = resources.align_functions(
            "script/a.dat", "Scene", not_whole, {"counters": Counter()}
        )
        self.assertEqual(
            [row["texts"] for row in rows if row.get("called_ids")],
            [{"en": "A", "ja": "甲"}],
        )

        # Function flags and argument signatures are part of every partial
        # mapping contract, including exact prefixes and removable gaps.
        for changed in (
            replace(not_whole["ja"], flags=1),
            replace(not_whole["ja"], arg_types=(1,)),
        ):
            rows = resources.align_functions(
                "script/a.dat",
                "Scene",
                {"en": not_whole["en"], "ja": changed},
                {"counters": Counter()},
            )
            self.assertFalse(any(row.get("called_ids") for row in rows))

        # A unique inserted non-display call gives one exact ordinal offset.
        inserted = resources.Called("chr_look_pos", 0, (("int", 4), ("float", 123), ("float", 456)))
        shifted = {
            "en": function(talk("Before"), wait, talk("After")),
            "ja": function(talk("前"), inserted, wait, talk("後")),
        }
        forward = resources.align_functions(
            "script/a.dat", "Scene", shifted, {"counters": Counter()}
        )
        reverse = resources.align_functions(
            "script/a.dat",
            "Scene",
            dict(reversed(tuple(shifted.items()))),
            {"counters": Counter()},
        )
        forward = [row for row in forward if row.get("called_ids")]
        reverse = [row for row in reverse if row.get("called_ids")]
        self.assertEqual(forward, reverse, "locale iteration order must not choose the mapping")
        self.assertEqual(
            [(row["called_ids"], row["texts"]) for row in forward],
            [
                ({"en": 0, "ja": 0}, {"en": "Before", "ja": "前"}),
                ({"en": 2, "ja": 3}, {"en": "After", "ja": "後"}),
            ],
        )

    def test_dialogue_record_alignment_rejects_missing_or_reordered_display_calls(self):
        def talk(text):
            return resources.Called(None, 3, (("int", 5), ("int", 0), ("int", 9), ("string", text)))

        def local(name):
            return resources.Called(name, 0, ())

        def function(*calls):
            return resources.Function("Scene", 0, (), calls, (), ())

        # Japanese has no counterpart for the two later display calls.  Only
        # the exact common prefix is admitted.
        missing = {
            "en": function(
                talk("A"),
                local("TALK_BEGIN"),
                talk("B"),
                local("wait"),
                talk("C"),
                local("TALK_END"),
            ),
            "ja": function(talk("甲"), local("TALK_END")),
        }
        rows = resources.align_functions("script/a.dat", "Scene", missing, {"counters": Counter()})
        aligned = [row for row in rows if row.get("called_ids")]
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["called_ids"], {"en": 0, "ja": 0})

        # Equal lengths do not justify fishing out later equal shapes after an
        # insertion/deletion or unknown non-display mismatch.
        reordered = {
            "en": function(talk("A"), local("left"), talk("B"), local("tail"), talk("C")),
            "ja": function(talk("甲"), local("inserted"), local("left"), talk("乙"), talk("丙")),
        }
        rows = resources.align_functions(
            "script/a.dat", "Scene", reordered, {"counters": Counter()}
        )
        aligned = [row for row in rows if row.get("called_ids")]
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["called_ids"], {"en": 0, "ja": 0})

    def test_parallel_catalog_matches_serial_including_invalid_and_missing_locales(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_game(root, {"en": make_scp("Same"), "fr": make_scp("Same"), "ja": b"bad"})
            (root / "pac/steam" / resources._ARCHIVES["ko"]).unlink()
            serial = resources.build_catalog(root, root / "serial", workers=1)
            parallel = resources.build_catalog(root, root / "parallel", workers=2)
            self.assertEqual(serial, parallel)
            self.assertEqual(
                (root / "serial/audit.json").read_bytes(),
                (root / "parallel/audit.json").read_bytes(),
            )

    def test_identical_locale_scripts_are_parsed_once_without_losing_locales(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_game(root, {l: make_scp("Same") for l in resources.LANGUAGES})
            with patch.object(resources, "parse_scp", wraps=resources.parse_scp) as parse:
                catalog = resources.build_catalog(root, root / "out", workers=1)
                self.assertEqual(parse.call_count, 1)
            self.assertEqual(set(catalog["entries"][0]["texts"]), set(resources.LANGUAGES))

    def test_dialogue_wrapping_does_not_discard_an_entire_scene(self):
        def talk(parts, voice=10):
            return resources.Called(
                None, 3, (("int", 5), ("int", 6), ("int", 9), ("int", 11), ("int", voice)) + parts
            )

        functions = {
            lang: resources.Function(
                "Scene",
                0,
                (),
                (
                    talk(parts),
                    resources.Called("chr_set_display_name", 0, (("int", 9), ("string", name))),
                    talk((("string", text),), voice=11),
                ),
                (),
                (),
            )
            for lang, parts, name, text in (
                ("en", (("string", "One"), ("int", 10), ("string", "two")), "Speaker", "Next"),
                ("fr", (("string", "Un deux"),), "Personnage", "Suite"),
                ("de", (("string", "<S3>"), ("string", "Eins zwei")), "Figur", "Weiter"),
            )
        }
        entries = resources.align_functions(
            "script/a.dat", "Scene", functions, {"counters": Counter()}
        )
        assembled = next(e for e in entries if "/called/0/assembled_dialogue" in e["key"])
        self.assertEqual(
            assembled["texts"], {"en": "One\ntwo", "fr": "Un deux", "de": "<S3>Eins zwei"}
        )
        name = next(e for e in entries if "/called/1/arg/1" in e["key"])
        self.assertEqual(set(name["texts"]), set(functions))
        self.assertFalse(any("/called/0/arg/" in e["key"] for e in entries))

        # Actor/voice metadata rejects only that dialogue. Unknown controls or
        # dynamic values still break the alignment at that point.
        from dataclasses import replace

        original = functions["fr"]
        args = original.called[0].args
        for altered in (
            args[:2] + (("int", 99),) + args[3:],
            args[:4] + (("int", 99),) + args[5:],
        ):
            bad = replace(original.called[0], args=altered)
            functions["fr"] = replace(original, called=(bad,) + original.called[1:])
            rows = resources.align_functions(
                "script/a.dat", "Scene", functions, {"counters": Counter()}
            )
            self.assertFalse(any("fr" in e["texts"] and "/called/0/" in e["key"] for e in rows))
            self.assertTrue(any("fr" in e["texts"] and "/called/2/" in e["key"] for e in rows))
        for altered in (
            (("int", 99),) + args[1:],
            args + (("var", None),),
            args + (("int", 11),),
        ):
            bad = replace(original.called[0], args=altered)
            functions["fr"] = replace(original, called=(bad,) + original.called[1:])
            rows = resources.align_functions(
                "script/a.dat", "Scene", functions, {"counters": Counter()}
            )
            self.assertTrue(rows)
            self.assertTrue(all("fr" not in e["texts"] for e in rows))

    def test_null_then_integer_is_not_a_prepare_local_call(self):
        code = (
            b"\x00\x04"
            + struct.pack("<I", 0)
            + b"\x00\x04"
            + struct.pack("<I", 0x40000001)
            + b"\x0d"
        )
        result = resources.parse_scp(make_scp(code=code))
        self.assertEqual(
            result.functions["Talk"].code_shape[:2], (("push", "special", 0), ("push", "int", 1))
        )

    def test_build_catalog_preserves_markup_and_all_eight_languages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root)
            catalog = resources.build_catalog(root, root / "out")
            self.assertEqual(catalog["languages"], list(resources.LANGUAGES))
            self.assertEqual(len(catalog["entries"]), 1)
            entry = catalog["entries"][0]
            self.assertEqual(entry["key"], "script/scena/c0000.dat/Talk/called/0/arg/0")
            self.assertEqual(entry["texts"]["zh-Hans"], "<zh-Hans>raw</zh-Hans>")
            audit = json.loads((root / "out" / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["counters"]["functions_aligned_zh-Hans"], 1)

    def test_build_catalog_includes_non_scenario_scp_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root, path="script/battle/b0000.dat")
            catalog = resources.build_catalog(root, root / "out")
            self.assertEqual(len(catalog["entries"]), 1)
            self.assertEqual(
                catalog["entries"][0]["key"], "script/battle/b0000.dat/Talk/called/0/arg/0"
            )
            audit = json.loads((root / "out" / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["counters"]["script_files_common"], 1)

    def test_cross_language_argument_shape_mismatch_omits_only_that_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root, {"en": make_scp(alternate_argument=True)})
            catalog = resources.build_catalog(root, root / "out")
            self.assertEqual(len(catalog["entries"]), 1)
            self.assertNotIn("en", catalog["entries"][0]["texts"])
            self.assertIn("zh-Hans", catalog["entries"][0]["texts"])
            audit = json.loads((root / "out" / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["counters"]["functions_mismatch_en"], 1)

    def test_unknown_bytecode_is_diagnosed_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root, {"ja": make_scp(opcode=255)})
            catalog = resources.build_catalog(root, root / "out")
            self.assertTrue(catalog["entries"])
            self.assertNotIn("ja", catalog["entries"][0]["texts"])
            self.assertIn("en", catalog["entries"][0]["texts"])
            self.assertIn("fr", catalog["entries"][0]["texts"])
            audit = json.loads((root / "out" / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["counters"]["scp_invalid_ja"], 1)
            self.assertIn("unknown SCP opcode", audit["diagnostics"][0]["reason"])

    def test_non_reference_locales_form_their_own_valid_structural_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overrides = {
                l: make_scp_calls(("id", l + " target"), first_argument_is_call=l in ("en", "fr"))
                for l in resources.LANGUAGES
            }
            write_game(root, overrides)
            catalog = resources.build_catalog(root, root / "out")
            pair = next(e for e in catalog["entries"] if e["texts"].get("en") == "en target")
            self.assertEqual(pair["texts"], {"en": "en target", "fr": "fr target"})
            self.assertEqual(len({e["key"] for e in catalog["entries"]}), len(catalog["entries"]))

    def test_missing_unrelated_archive_does_not_block_installed_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_game(root)
            (root / "pac/steam" / resources._ARCHIVES["ja"]).unlink()
            catalog = resources.build_catalog(root, root / "out")
            self.assertIn("en", catalog["entries"][0]["texts"])
            self.assertNotIn("ja", catalog["entries"][0]["texts"])

    def test_different_debug_line_numbers_still_align(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = b"\x26" + struct.pack("<H", 10) + b"\x0d"
            second = b"\x26" + struct.pack("<H", 900) + b"\x0d"
            write_game(root, {"en": make_scp(code=second)})
            # Make every other locale use the same semantic code as Japanese.
            for language, archive in resources._ARCHIVES.items():
                if language != "en":
                    (root / "pac" / "steam" / archive).write_bytes(
                        make_fpac("script/scena/c0000.dat", make_scp(code=first))
                    )
            catalog = resources.build_catalog(root, root / "out")
            self.assertIn("en", catalog["entries"][0]["texts"])

    def test_different_executable_numeric_parameter_rejects_code_text_but_not_validated_calls(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            string_push = b"\x00\x04" + struct.pack("<I", 0xC0000000 | 112)
            code_one = string_push + b"\x00\x04" + struct.pack("<I", 0x40000001) + b"\x0d"
            code_two = string_push + b"\x00\x04" + struct.pack("<I", 0x40000002) + b"\x0d"
            write_game(root, {"en": make_scp(code=code_two)})
            for language, archive in resources._ARCHIVES.items():
                if language != "en":
                    (root / "pac" / "steam" / archive).write_bytes(
                        make_fpac("script/scena/c0000.dat", make_scp(code=code_one))
                    )
            catalog = resources.build_catalog(root, root / "out")
            called = next(entry for entry in catalog["entries"] if "/called/" in entry["key"])
            code = next(entry for entry in catalog["entries"] if "/code/" in entry["key"])
            self.assertIn("en", called["texts"])
            self.assertNotIn("en", code["texts"])

    def test_branch_targets_are_normalised_to_instruction_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code_at = 160
            string_push = b"\x00\x04" + struct.pack("<I", 0xC0000000 | 112)
            forward = string_push + b"\x0b" + struct.pack("<I", code_at + 11) + b"\x0d"
            loop = string_push + b"\x0b" + struct.pack("<I", code_at) + b"\x0d"
            write_game(root, {"en": make_scp(code=loop)})
            for language, archive in resources._ARCHIVES.items():
                if language != "en":
                    (root / "pac" / "steam" / archive).write_bytes(
                        make_fpac("script/scena/c0000.dat", make_scp(code=forward))
                    )
            catalog = resources.build_catalog(root, root / "out")
            called = next(entry for entry in catalog["entries"] if "/called/" in entry["key"])
            code = next(entry for entry in catalog["entries"] if "/code/" in entry["key"])
            self.assertIn("en", called["texts"])
            self.assertNotIn("en", code["texts"])

    def test_called_text_requires_the_complete_ordered_called_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(
                root, {"en": make_scp_calls(("first", "target"), first_argument_is_call=True)}
            )
            for language, archive in resources._ARCHIVES.items():
                if language != "en":
                    (root / "pac" / "steam" / archive).write_bytes(
                        make_fpac("script/scena/c0000.dat", make_scp_calls(("first", "target")))
                    )
            catalog = resources.build_catalog(root, root / "out")
            target = next(entry for entry in catalog["entries"] if entry["texts"]["ja"] == "target")
            self.assertNotIn("en", target["texts"])
            audit = json.loads((root / "out" / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["counters"]["functions_called_mismatch_en"], 1)

    def test_external_call_identifiers_are_part_of_code_shape(self) -> None:
        def code(namespace: str, function: str) -> bytes:
            data = bytearray(256)
            data[0] = 34
            struct.pack_into("<I", data, 1, 0xC0000000 | 128)
            struct.pack_into("<I", data, 5, 0xC0000000 | 160)
            data[9] = 0
            data[10] = 13
            data[128 : 128 + len(namespace) + 1] = namespace.encode() + b"\0"
            data[160 : 160 + len(function) + 1] = function.encode() + b"\0"
            return bytes(data)

        first, _ = resources._parse_code(code("ui", "show"), 0, 11, 0, (), ())
        second, _ = resources._parse_code(code("ui", "hide"), 0, 11, 0, (), ())
        self.assertEqual(first[0], ("external-call", 34, "ui", "show", 0))
        self.assertNotEqual(first, second)

    def test_fpac_rejects_out_of_bounds_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.pac"
            archive.write_bytes(b"FPAC" + struct.pack("<III", 1, 48, 1) + b"\0" * 32)
            with self.assertRaises(resources.FormatError):
                resources.FpacArchive(archive)


if __name__ == "__main__":
    unittest.main()
