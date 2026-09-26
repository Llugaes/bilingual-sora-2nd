# Static Noto glyph fallback

This directory contains only a two-glyph donor derived from Noto Sans CJK KR,
not any game font data. `font_0.fnt` has records for `U+C80B` and `U+D591`;
`font_0.dds` is the matching 128×56 DX10/BC7 texture. A verified scan of the
current catalog found those two codepoints absent from the local game-font
union. Runtime code computes the actual union before adding them, so it does
not assume a language pair or a fixed total glyph count.

The donor was built from
[`NotoSansCJKkr-Regular.otf`](https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf)
(SHA-256 `6bcb2a0703aa137e874fc2dffa85f6c21ba9a67fa329e81b8c801663af7e992a`)
under SIL OFL-1.1. `NOTICE.md` preserves the donor font's embedded copyright
record, and `OFL.txt` is the upstream license text. The two glyphs were rendered
as gray signed-distance fields and encoded with Microsoft DirectXTex
May 2026 `texconv.exe` (SHA-256
`dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06`),
using `-nogpu --single-proc -m 1 -f BC7_UNORM -dx10`.

Released donor digests:

- `font_0.fnt`: `40c0fdabd9600560164911b66e58a3c682d0e5f51ba08d4b1b7d03a332a78fd9`
- `font_0.dds`: `67506160cea1a0e5dd9631b6176e7edf9e0c6da7662525b347e3a4ec8cfde7f8`

`tools/build_font_fallback.py` is the offline reproducer. It requires explicit
paths to the Noto OTF, the pinned `texconv.exe`, and a local game directory;
it performs no download and never writes to the game directory.
