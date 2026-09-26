"""Build per-source-locale font unions, retaining original glyphs and BC7 data."""

import argparse
import hashlib
import json
from pathlib import Path
from sora_bilingual.paths import ROOT
import struct
import lz4.frame

from sora_bilingual.config.locales import LOCALES
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.fonts.font_merge import (
    parse_fnt,
    parse_dds,
    FontFormatError,
    X_OFFSET,
    Y_OFFSET,
    FNT_COUNT_OFFSET,
    FNT_DATA_LENGTH_OFFSET,
    DDS_HEIGHT_OFFSET,
    DDS_LINEAR_SIZE_OFFSET,
)

# Verified bound of the supported game's font decompression buffer, including
# the DDS header. This is an engine contract, not a locale-specific size.
MAX_DECODED_BYTES = 32 * 1024 * 1024
FALLBACK_ROOT = ROOT / "assets/font-fallback"
FALLBACK_SHA256 = {
    "font_0.fnt": "40c0fdabd9600560164911b66e58a3c682d0e5f51ba08d4b1b7d03a332a78fd9",
    "font_0.dds": "67506160cea1a0e5dd9631b6176e7edf9e0c6da7662525b347e3a4ec8cfde7f8",
}


def fallback_dependencies() -> tuple[Path, ...]:
    """Small audited donor files which affect every generated font candidate."""
    return tuple(FALLBACK_ROOT / name for name in (*FALLBACK_SHA256, "PROVENANCE.md"))


def read_fallback_donor():
    """Load the static Noto-derived donor, rejecting altered or malformed data."""
    values = {}
    for name, expected in FALLBACK_SHA256.items():
        path = FALLBACK_ROOT / name
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FontFormatError(f"font fallback is missing: {path}") from exc
        if hashlib.sha256(data).hexdigest() != expected:
            raise FontFormatError(f"font fallback digest mismatch: {path}")
        values[name] = data
    image = parse_dds(values["font_0.dds"])
    font = parse_fnt(values["font_0.fnt"], atlas_width=image.width, atlas_height=image.height)
    if not font.codepoints:
        raise FontFormatError("font fallback contains no glyphs")
    return font, image


def merge_fonts(base, donors, max_bytes=MAX_DECODED_BYTES):
    """Copy whole compressed blocks with a sampling border; never re-encode."""
    font, image = base
    width = image.width
    stride = width // 4 * 16
    if width % 4 or image.height % 4:
        raise FontFormatError("unaligned BC7 atlas")
    glyphs = {g.codepoint: g.raw for g in font.glyphs}
    tiles = {}
    for donor_font, donor_image in donors:
        if donor_image.width % 4 or donor_image.height % 4:
            raise FontFormatError("unaligned donor atlas")
        for g in donor_font.glyphs:
            if g.codepoint in glyphs or g.codepoint in tiles:
                continue
            if not g.width or not g.height:
                raw = bytearray(g.raw)
                struct.pack_into("<HH", raw, X_OFFSET, 0, 0)
                glyphs[g.codepoint] = bytes(raw)
                continue
            x0 = max(0, g.x // 4 * 4 - 4)
            y0 = max(0, g.y // 4 * 4 - 4)
            x1 = min(donor_image.width, (g.x + g.width + 3) // 4 * 4 + 4)
            y1 = min(donor_image.height, (g.y + g.height + 3) // 4 * 4 + 4)
            tiles[g.codepoint] = (g, donor_image, x0, y0, x1 - x0, y1 - y0)
    base_height = min(image.height, (max(g.y + g.height for g in font.glyphs) + 3) // 4 * 4 + 4)
    payload = bytearray(image.payload[: base_height // 4 * stride])
    x = 0
    y = base_height
    shelf = 0
    for cp, (g, donor, x0, y0, w, h) in sorted(tiles.items(), key=lambda kv: (-kv[1][5], kv[0])):
        if w > width:
            raise FontFormatError("glyph exceeds destination atlas width")
        if x + w > width:
            x = 0
            y += shelf
            shelf = 0
        bottom = y + h
        required = bottom // 4 * stride
        if bottom > 65535 or len(image.header) + required > max_bytes:
            raise FontFormatError("font union exceeds verified engine buffer")
        if len(payload) < required:
            payload.extend(bytes(required - len(payload)))
        source_stride = (donor.width + 3) // 4 * 16
        for row in range(h // 4):
            src = (y0 // 4 + row) * source_stride + x0 // 4 * 16
            dst = (y // 4 + row) * stride + x // 4 * 16
            payload[dst : dst + w // 4 * 16] = donor.payload[src : src + w // 4 * 16]
        raw = bytearray(g.raw)
        struct.pack_into("<HH", raw, X_OFFSET, x + g.x - x0, y + g.y - y0)
        glyphs[cp] = bytes(raw)
        x += w
        shelf = max(shelf, h)
    records = b"".join(glyphs[k] for k in sorted(glyphs))
    fh = bytearray(font.header)
    dh = bytearray(image.header)
    struct.pack_into("<I", fh, FNT_COUNT_OFFSET, len(glyphs))
    struct.pack_into("<I", fh, FNT_DATA_LENGTH_OFFSET, len(records))
    struct.pack_into("<I", dh, DDS_HEIGHT_OFFSET, len(payload) // stride * 4)
    struct.pack_into("<I", dh, DDS_LINEAR_SIZE_OFFSET, len(payload))
    fnt, dds = bytes(fh) + records, bytes(dh) + payload
    if len(dds) > max_bytes:
        raise FontFormatError("font union exceeds verified engine buffer")
    result = parse_dds(dds)
    parse_fnt(fnt, atlas_width=result.width, atlas_height=result.height)
    return fnt, dds


def read_fonts(game):
    archives = Path(game) / "pac/steam"
    result = {}
    for suffix in dict.fromkeys(l.font_suffix for l in LOCALES.values()):
        prefix = "asset" + suffix
        with FpacArchive(archives / f"asset_common_font{suffix}.pac") as a:
            fnt = a.read(f"{prefix}/common/font/font_0.fnt")
        with FpacArchive(archives / f"image{suffix}.pac") as a:
            dds = lz4.frame.decompress(a.read(f"{prefix}/dx11/image/font_0.dds"))
        image = parse_dds(dds)
        font = parse_fnt(fnt, atlas_width=image.width, atlas_height=image.height)
        result[prefix] = (font, image)
    return result


def build(game, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fonts = read_fonts(game)
    union = set().union(*(f.codepoints for f, _ in fonts.values()))
    fallback = read_fallback_donor()
    fallback_added = fallback[0].codepoints - union
    donors = [*fonts.values(), *([fallback] if fallback_added else [])]
    expected_codepoints = union | fallback_added
    manifest = {
        "version": 2,
        "locales": {l: "asset" + v.font_suffix for l, v in LOCALES.items()},
        "glyphs": len(expected_codepoints),
        "fallback": {
            "available": [f"U+{codepoint:04X}" for codepoint in sorted(fallback[0].codepoints)],
            "added": [f"U+{codepoint:04X}" for codepoint in sorted(fallback_added)],
        },
        "files": [],
        "atlases": [],
    }
    for prefix, base in fonts.items():
        fnt, dds = merge_fonts(base, donors)
        image = parse_dds(dds)
        font = parse_fnt(fnt, atlas_width=image.width, atlas_height=image.height)
        assert font.codepoints == expected_codepoints
        by_cp = {g.codepoint: g.raw for g in font.glyphs}
        assert all(by_cp[g.codepoint] == g.raw for g in base[0].glyphs)
        # The entire original referenced texture prefix stays byte-identical.
        used = min(base[1].height, (max(g.y + g.height for g in base[0].glyphs) + 3) // 4 * 4 + 4)
        count = used // 4 * (base[1].width // 4) * 16
        assert image.payload[:count] == base[1].payload[:count]
        compressed = lz4.frame.compress(
            dds,
            block_size=lz4.frame.BLOCKSIZE_MAX4MB,
            block_linked=False,
            content_checksum=True,
            store_size=True,
        )
        assert lz4.frame.decompress(compressed) == dds
        for target, data in (
            (f"{prefix}/common/font/font_0.fnt", fnt),
            (f"{prefix}/dx11/image/font_0.dds", compressed),
        ):
            path = output / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            manifest["files"].append(
                {"path": target, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            )
        manifest["atlases"].append(
            {
                "asset": prefix,
                "glyphs": len(font.glyphs),
                "width": image.width,
                "height": image.height,
                "decoded_bytes": len(dds),
            }
        )
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/font-universal")
    args = parser.parse_args()
    print(json.dumps(build(args.game, args.output), ensure_ascii=False, indent=2))
