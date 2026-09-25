import struct
import unittest
from sora_bilingual.fonts.font_merge import parse_fnt, parse_dds, FontFormatError
from sora_bilingual.fonts.universal_fonts import merge_fonts
from test_font_merge import _fnt


def atlas(seed):
    header = bytearray(148)
    header[:4] = b"DDS "
    for offset, value in (
        (4, 124),
        (12, 32),
        (16, 32),
        (20, 1024),
        (28, 1),
        (76, 32),
        (128, 98),
        (140, 1),
    ):
        struct.pack_into("<I", header, offset, value)
    header[84:88] = b"DX10"
    return parse_dds(bytes(header) + b"".join(bytes([(seed + i) % 256]) * 16 for i in range(64)))


class UniversalFontsTests(unittest.TestCase):
    def test_original_glyphs_and_pixels_stay_exact_added_blocks_keep_sampling_border(self):
        base = parse_fnt(_fnt([(65, 3, 4, 8, 6)]), atlas_width=32, atlas_height=32), atlas(0)
        donor = (
            parse_fnt(_fnt([(65, 0, 0, 4, 4), (66, 7, 9, 6, 5)]), atlas_width=32, atlas_height=32),
            atlas(100),
        )
        fnt, dds = merge_fonts(base, [donor])
        image = parse_dds(dds)
        font = parse_fnt(fnt, atlas_width=32, atlas_height=image.height)
        self.assertEqual(font.codepoints, {65, 66})
        self.assertEqual(font.glyphs[0].raw, base[0].glyphs[0].raw)
        self.assertEqual(image.payload[: 16 // 4 * 128], base[1].payload[: 16 // 4 * 128])
        g = font.glyphs[1]
        src = donor[0].glyphs[1]
        self.assertEqual(g.x % 4, src.x % 4)
        self.assertEqual(g.y % 4, src.y % 4)
        for dy in range(-1, 3):
            for dx in range(-1, 3):
                a = ((g.y // 4 + dy) * 8 + g.x // 4 + dx) * 16
                b = ((src.y // 4 + dy) * 8 + src.x // 4 + dx) * 16
                self.assertEqual(image.payload[a : a + 16], donor[1].payload[b : b + 16])
        with self.assertRaises(FontFormatError):
            merge_fonts(base, [donor], max_bytes=160)


if __name__ == "__main__":
    unittest.main()
