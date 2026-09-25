import binascii
import json
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from sora_bilingual.localization import resources


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
    def test_unrelated_reward_format_does_not_block_verified_dialogue_sequence(self):
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
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["texts"], {"en": "Continue", "fr": "Proceed"})
        self.assertEqual(rows[0]["display_role"], "dialogue")
        # A different speaker/voice, reordered calls or added calls cannot
        # borrow the neighbouring dialogue's translation.
        for slot in (2, 4):
            args = list(b.called[1].args)
            args[slot] = ("int", 99)
            self.assertFalse(
                align(replace(b, called=(b.called[0], replace(talk, args=tuple(args)))))
            )
        self.assertFalse(align(replace(b, called=tuple(reversed(b.called)))))
        self.assertFalse(align(replace(b, called=b.called + (reward,))))

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

        # Wrapping is the only relaxation: changing the speaker/voice, using
        # a dynamic value, or inserting a non-newline command breaks alignment.
        from dataclasses import replace

        original = functions["fr"]
        args = original.called[0].args
        for altered in (
            (("int", 99),) + args[1:],
            args[:2] + (("int", 99),) + args[3:],
            args[:4] + (("int", 99),) + args[5:],
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
