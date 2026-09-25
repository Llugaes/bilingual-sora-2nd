from __future__ import annotations

import os
import struct
import tempfile
import unittest
from pathlib import Path

from sora_bilingual.fonts.font_merge import (
    DDS_HEADER_SIZE,
    FontFormatError,
    crop_dds_to_glyphs,
    merge_dds,
    merge_fnt,
    parse_dds,
    parse_fnt,
)
from sora_bilingual.localization.resources import FpacArchive


GAME_DIR = Path(os.environ.get("SORA_GAME_DIR", "generated/missing-game-fixture"))
RESEARCH_DIR = Path(os.environ.get("SORA_RESEARCH_DIR", "generated/missing-font-fixture"))


def _has_actual_sources() -> bool:
    archive_dir = GAME_DIR / "pac" / "steam"
    return (
        (archive_dir / "asset_common_font_sc.pac").is_file()
        and (archive_dir / "asset_common_font.pac").is_file()
        and (RESEARCH_DIR / "samples/font_sc.dds").is_file()
        and (RESEARCH_DIR / "samples/font.dds").is_file()
    )


def _read_fnt(archive_name: str, entry: str) -> bytes:
    with FpacArchive(GAME_DIR / "pac" / "steam" / archive_name) as archive:
        return archive.read(entry)


def _fnt(records: list[tuple[int, int, int, int, int]]) -> bytes:
    header = bytearray(40)
    header[32:36] = b"FLTI"
    struct.pack_into("<I", header, 8, len(records))
    struct.pack_into("<I", header, 36, len(records) * 24)
    payload = bytearray()
    for codepoint, x, y, width, height in records:
        record = bytearray(24)
        struct.pack_into("<I", record, 0, codepoint)
        struct.pack_into("<HHHH", record, 8, x, y, width, height)
        payload.extend(record)
    return bytes(header + payload)


@unittest.skipUnless(_has_actual_sources(), "requires local game FNTs and research DDS fixtures")
class ActualFontMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sc_fnt = _read_fnt("asset_common_font_sc.pac", "asset_sc/common/font/font_0.fnt")
        cls.jp_fnt = _read_fnt("asset_common_font.pac", "asset/common/font/font_0.fnt")
        cls.sc_dds = (RESEARCH_DIR / "samples/font_sc.dds").read_bytes()
        cls.jp_dds = (RESEARCH_DIR / "samples/font.dds").read_bytes()

    def test_actual_fnt_merge_preserves_primary_and_adds_japanese_only(self) -> None:
        primary = parse_fnt(self.sc_fnt)
        secondary = parse_fnt(self.jp_fnt)
        merged = parse_fnt(merge_fnt(self.sc_fnt, self.jp_fnt), atlas_height=8192)
        original_primary = {glyph.codepoint: glyph.raw for glyph in primary.glyphs}
        result = {glyph.codepoint: glyph for glyph in merged.glyphs}
        self.assertEqual(len(primary.glyphs), 9026)
        self.assertEqual(len(secondary.glyphs), 11809)
        self.assertEqual(len(merged.glyphs), 11900)
        self.assertEqual(set(original_primary), set(result) & set(original_primary))
        self.assertTrue(
            all(result[codepoint].raw == raw for codepoint, raw in original_primary.items())
        )
        for character in ("雫", "霊"):
            glyph = result[ord(character)]
            self.assertGreaterEqual(glyph.y, 4096)
            self.assertLessEqual(glyph.y + glyph.height, 8192)

    def test_actual_bc7_payloads_are_concatenated_byte_for_byte(self) -> None:
        primary = parse_dds(self.sc_dds)
        secondary = parse_dds(self.jp_dds)
        merged = parse_dds(merge_dds(self.sc_dds, self.jp_dds))
        raw = merge_dds(self.sc_dds, self.jp_dds)
        self.assertEqual((merged.width, merged.height), (4096, 8192))
        self.assertEqual(merged.linear_size, primary.linear_size + secondary.linear_size)
        self.assertEqual(
            raw[DDS_HEADER_SIZE : DDS_HEADER_SIZE + len(primary.payload)], primary.payload
        )
        self.assertEqual(raw[DDS_HEADER_SIZE + len(primary.payload) :], secondary.payload)

    def test_write_merge_crops_unused_rows_without_changing_glyphs_or_blocks(self) -> None:
        from sora_bilingual.fonts.font_merge import write_merge

        full_fnt = merge_fnt(self.sc_fnt, self.jp_fnt)
        full_dds = merge_dds(self.sc_dds, self.jp_dds)
        with tempfile.TemporaryDirectory() as directory:
            write_merge(Path(directory), self.sc_fnt, self.jp_fnt, self.sc_dds, self.jp_dds)
            final_fnt = Path(directory, "font_0_sc_plus_jp.fnt").read_bytes()
            final_dds = Path(directory, "font_0_sc_plus_jp.dds").read_bytes()
        parsed_dds = parse_dds(final_dds)
        parsed_font = parse_fnt(final_fnt, atlas_height=parsed_dds.height)
        self.assertEqual(final_fnt, full_fnt)
        self.assertEqual(parsed_dds.height, 7264)
        self.assertLessEqual(len(final_dds), 33_554_432)
        self.assertEqual(
            final_dds[DDS_HEADER_SIZE:],
            full_dds[DDS_HEADER_SIZE : DDS_HEADER_SIZE + len(parsed_dds.payload)],
        )
        self.assertLess(len(final_dds), len(full_dds))
        self.assertTrue(
            all(glyph.y + glyph.height <= parsed_dds.height for glyph in parsed_font.glyphs)
        )

    def test_crop_height_beyond_dds_fails_closed(self) -> None:
        oversized_fnt = _fnt([(65, 0, 8190, 8, 8)])
        with self.assertRaisesRegex(FontFormatError, "crop height.*outside"):
            crop_dds_to_glyphs(oversized_fnt, self.sc_dds)


class FormatFailureTests(unittest.TestCase):
    def test_duplicate_codepoint_fails_closed(self) -> None:
        duplicate = _fnt([(65, 0, 0, 8, 8), (65, 8, 0, 8, 8)])
        with self.assertRaisesRegex(FontFormatError, "duplicate"):
            parse_fnt(duplicate)

    def test_out_of_bounds_glyph_fails_closed(self) -> None:
        with self.assertRaisesRegex(FontFormatError, "outside"):
            parse_fnt(_fnt([(65, 4090, 0, 8, 8)]))

    def test_fnt_mismatched_header_fails_closed(self) -> None:
        malformed = bytearray(_fnt([(65, 0, 0, 8, 8)]))
        struct.pack_into("<I", malformed, 36, 0)
        with self.assertRaisesRegex(FontFormatError, "data-length"):
            parse_fnt(bytes(malformed))

    def test_mismatched_dds_header_fails_closed(self) -> None:
        valid = (
            bytearray((RESEARCH_DIR / "samples/font_sc.dds").read_bytes())
            if (RESEARCH_DIR / "samples/font_sc.dds").is_file()
            else bytearray(148)
        )
        if len(valid) == 148:
            self.skipTest("DDS fixture unavailable")
        struct.pack_into("<I", valid, 16, 2048)
        with self.assertRaises(FontFormatError):
            merge_dds((RESEARCH_DIR / "samples/font_sc.dds").read_bytes(), bytes(valid))


if __name__ == "__main__":
    unittest.main()
