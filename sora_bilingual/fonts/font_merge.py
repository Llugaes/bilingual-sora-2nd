"""Offline merger for the 2nd Chapter Simplified Chinese and Japanese fonts.

The result is deliberately an unpacked FNT/DDS pair.  This module never writes
to a game directory or repacks an archive: installation remains a separate,
reviewable operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FNT_HEADER_SIZE = 40
FNT_RECORD_SIZE = 24
FNT_COUNT_OFFSET = 8
FNT_DATA_LENGTH_OFFSET = 36
FNT_TAG_OFFSET = 32
FNT_TAG = b"FLTI"
CODEPOINT_OFFSET = 0
X_OFFSET = 8
Y_OFFSET = 10
WIDTH_OFFSET = 12
HEIGHT_OFFSET = 14

DDS_HEADER_SIZE = 148
DDS_HEIGHT_OFFSET = 12
DDS_WIDTH_OFFSET = 16
DDS_LINEAR_SIZE_OFFSET = 20
DDS_PIXEL_FORMAT_SIZE_OFFSET = 76
DDS_FOURCC_OFFSET = 84
DX10_FORMAT_OFFSET = 128
DX10_ARRAY_SIZE_OFFSET = 140
DXGI_FORMAT_BC7_UNORM = 98


class FontFormatError(ValueError):
    """Raised when an input is not the documented FNT/DDS shape."""


@dataclass(frozen=True)
class Glyph:
    codepoint: int
    raw: bytes

    @property
    def x(self) -> int:
        return struct.unpack_from("<H", self.raw, X_OFFSET)[0]

    @property
    def y(self) -> int:
        return struct.unpack_from("<H", self.raw, Y_OFFSET)[0]

    @property
    def width(self) -> int:
        return struct.unpack_from("<H", self.raw, WIDTH_OFFSET)[0]

    @property
    def height(self) -> int:
        return struct.unpack_from("<H", self.raw, HEIGHT_OFFSET)[0]


@dataclass(frozen=True)
class FntFont:
    header: bytes
    glyphs: tuple[Glyph, ...]

    @property
    def codepoints(self) -> frozenset[int]:
        return frozenset(glyph.codepoint for glyph in self.glyphs)


@dataclass(frozen=True)
class DdsImage:
    header: bytes
    payload: bytes
    width: int
    height: int
    linear_size: int


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _validate_glyph_bounds(glyph: Glyph, atlas_width: int, atlas_height: int) -> None:
    if glyph.x + glyph.width > atlas_width or glyph.y + glyph.height > atlas_height:
        raise FontFormatError(
            f"U+{glyph.codepoint:04X}: glyph rectangle "
            f"({glyph.x}, {glyph.y}, {glyph.width}, {glyph.height}) outside "
            f"{atlas_width}x{atlas_height} atlas"
        )


def parse_fnt(data: bytes, *, atlas_width: int = 4096, atlas_height: int = 4096) -> FntFont:
    """Parse a verified FCV/FLTI FNT without interpreting opaque fields."""
    if len(data) < FNT_HEADER_SIZE:
        raise FontFormatError("FNT is shorter than its 40-byte header")
    if data[FNT_TAG_OFFSET : FNT_TAG_OFFSET + 4] != FNT_TAG:
        raise FontFormatError("FNT is missing the FLTI header tag")
    count = _u32(data, FNT_COUNT_OFFSET)
    expected_size = FNT_HEADER_SIZE + count * FNT_RECORD_SIZE
    if len(data) != expected_size:
        raise FontFormatError(f"FNT count {count} requires {expected_size} bytes, got {len(data)}")
    if _u32(data, FNT_DATA_LENGTH_OFFSET) != len(data) - FNT_HEADER_SIZE:
        raise FontFormatError("FNT data-length field does not match file size")

    glyphs: list[Glyph] = []
    seen: set[int] = set()
    for index in range(count):
        start = FNT_HEADER_SIZE + index * FNT_RECORD_SIZE
        raw = data[start : start + FNT_RECORD_SIZE]
        codepoint = _u32(raw, CODEPOINT_OFFSET)
        if codepoint in seen:
            raise FontFormatError(f"FNT has duplicate U+{codepoint:04X}")
        glyph = Glyph(codepoint, raw)
        _validate_glyph_bounds(glyph, atlas_width, atlas_height)
        seen.add(codepoint)
        glyphs.append(glyph)
    return FntFont(data[:FNT_HEADER_SIZE], tuple(glyphs))


def merge_fnt(primary: bytes, secondary: bytes) -> bytes:
    """Keep every primary glyph and add only missing secondary glyphs below it."""
    primary_font = parse_fnt(primary)
    secondary_font = parse_fnt(secondary)
    by_codepoint = {glyph.codepoint: glyph.raw for glyph in primary_font.glyphs}
    for glyph in secondary_font.glyphs:
        if glyph.codepoint in by_codepoint:
            continue
        shifted = bytearray(glyph.raw)
        new_y = glyph.y + 4096
        if new_y > 0xFFFF:
            raise FontFormatError(f"U+{glyph.codepoint:04X}: shifted y exceeds u16")
        struct.pack_into("<H", shifted, Y_OFFSET, new_y)
        by_codepoint[glyph.codepoint] = bytes(shifted)

    records = b"".join(by_codepoint[codepoint] for codepoint in sorted(by_codepoint))
    header = bytearray(primary_font.header)
    struct.pack_into("<I", header, FNT_COUNT_OFFSET, len(by_codepoint))
    struct.pack_into("<I", header, FNT_DATA_LENGTH_OFFSET, len(records))
    return bytes(header) + records


def _bc7_payload_size(width: int, height: int, mip_count: int) -> int:
    if mip_count != 1:
        raise FontFormatError(f"DDS mip count {mip_count}; only one mip is supported")
    return ((width + 3) // 4) * ((height + 3) // 4) * 16


def parse_dds(data: bytes) -> DdsImage:
    """Validate the exact DX10/BC7, one-mip DDS contract used by these fonts."""
    if len(data) < DDS_HEADER_SIZE or data[:4] != b"DDS ":
        raise FontFormatError("DDS magic/header is missing")
    if _u32(data, 4) != 124:
        raise FontFormatError("DDS header size is not 124")
    if _u32(data, DDS_PIXEL_FORMAT_SIZE_OFFSET) != 32:
        raise FontFormatError("DDS pixel-format size is not 32")
    if data[DDS_FOURCC_OFFSET : DDS_FOURCC_OFFSET + 4] != b"DX10":
        raise FontFormatError("DDS is not a DX10 texture")
    if _u32(data, DX10_FORMAT_OFFSET) != DXGI_FORMAT_BC7_UNORM:
        raise FontFormatError("DDS is not DXGI_FORMAT_BC7_UNORM (98)")
    if _u32(data, DX10_ARRAY_SIZE_OFFSET) != 1:
        raise FontFormatError("DDS array size is not one")
    width = _u32(data, DDS_WIDTH_OFFSET)
    height = _u32(data, DDS_HEIGHT_OFFSET)
    mip_count = _u32(data, 28)
    if not width or not height:
        raise FontFormatError("DDS dimensions must be non-zero")
    expected_payload = _bc7_payload_size(width, height, mip_count)
    if len(data) != DDS_HEADER_SIZE + expected_payload:
        raise FontFormatError(
            f"DDS payload requires {expected_payload} bytes, got {len(data) - DDS_HEADER_SIZE}"
        )
    linear_size = _u32(data, DDS_LINEAR_SIZE_OFFSET)
    if linear_size != expected_payload:
        raise FontFormatError(
            f"DDS linear size {linear_size} does not match BC7 payload {expected_payload}"
        )
    return DdsImage(data[:DDS_HEADER_SIZE], data[DDS_HEADER_SIZE:], width, height, linear_size)


def merge_dds(primary: bytes, secondary: bytes) -> bytes:
    """Concatenate two 4096-square BC7 atlases vertically without decoding them."""
    primary_image = parse_dds(primary)
    secondary_image = parse_dds(secondary)
    expected_shape = (4096, 4096)
    if (primary_image.width, primary_image.height) != expected_shape:
        raise FontFormatError("primary DDS must be a 4096x4096 atlas")
    if (secondary_image.width, secondary_image.height) != expected_shape:
        raise FontFormatError("secondary DDS must be a 4096x4096 atlas")
    header = bytearray(primary_image.header)
    payload = primary_image.payload + secondary_image.payload
    struct.pack_into("<I", header, DDS_HEIGHT_OFFSET, primary_image.height + secondary_image.height)
    struct.pack_into("<I", header, DDS_LINEAR_SIZE_OFFSET, len(payload))
    return bytes(header) + payload


def crop_dds_to_glyphs(merged_fnt: bytes, merged_dds: bytes) -> bytes:
    """Drop bottom BC7 rows unused by the merged FNT, without changing glyphs."""
    image = parse_dds(merged_dds)
    font = parse_fnt(merged_fnt, atlas_height=0xFFFF)
    max_bottom = max(glyph.y + glyph.height for glyph in font.glyphs)
    crop_height = (max_bottom + 3) // 4 * 4
    if not crop_height or crop_height > image.height:
        raise FontFormatError(
            f"crop height {crop_height} is outside merged DDS height {image.height}"
        )
    # Keep one BC7 block row beyond the last glyph for edge sampling.
    crop_height = min(image.height, crop_height + 4)
    payload_size = _bc7_payload_size(image.width, crop_height, 1)
    header = bytearray(image.header)
    struct.pack_into("<I", header, DDS_HEIGHT_OFFSET, crop_height)
    struct.pack_into("<I", header, DDS_LINEAR_SIZE_OFFSET, payload_size)
    cropped = bytes(header) + image.payload[:payload_size]
    parse_fnt(merged_fnt, atlas_width=image.width, atlas_height=crop_height)
    return cropped


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    primary_fnt: bytes,
    secondary_fnt: bytes,
    primary_dds: bytes,
    secondary_dds: bytes,
    merged_fnt: bytes,
    merged_dds: bytes,
) -> dict[str, object]:
    """Return source/output digests and the coverage decision for review."""
    parsed_primary = parse_fnt(primary_fnt)
    parsed_secondary = parse_fnt(secondary_fnt)
    parsed_merged_dds = parse_dds(merged_dds)
    parsed_merged = parse_fnt(
        merged_fnt, atlas_width=parsed_merged_dds.width, atlas_height=parsed_merged_dds.height
    )
    primary_codes = parsed_primary.codepoints
    secondary_codes = parsed_secondary.codepoints
    return {
        "format": "sc-primary-jp-secondary-v1",
        "coverage": {
            "primary_glyphs": len(parsed_primary.glyphs),
            "secondary_glyphs": len(parsed_secondary.glyphs),
            "primary_wins_conflicts": len(primary_codes & secondary_codes),
            "secondary_added": len(secondary_codes - primary_codes),
            "merged_glyphs": len(parsed_merged.glyphs),
        },
        "atlas": {
            "width": parsed_merged_dds.width,
            "height": parsed_merged_dds.height,
            "format": "DXGI_FORMAT_BC7_UNORM",
            "mips": 1,
        },
        "sha256": {
            "primary_fnt": _sha256(primary_fnt),
            "secondary_fnt": _sha256(secondary_fnt),
            "primary_dds": _sha256(primary_dds),
            "secondary_dds": _sha256(secondary_dds),
            "merged_fnt": _sha256(merged_fnt),
            "merged_dds": _sha256(merged_dds),
        },
    }


def write_merge(
    output_dir: Path,
    primary_fnt: bytes,
    secondary_fnt: bytes,
    primary_dds: bytes,
    secondary_dds: bytes,
) -> dict[str, object]:
    """Write an unpacked review candidate to an explicit non-game output directory."""
    merged_fnt = merge_fnt(primary_fnt, secondary_fnt)
    merged_dds = crop_dds_to_glyphs(merged_fnt, merge_dds(primary_dds, secondary_dds))
    manifest = build_manifest(
        primary_fnt, secondary_fnt, primary_dds, secondary_dds, merged_fnt, merged_dds
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "font_0_sc_plus_jp.fnt").write_bytes(merged_fnt)
    (output_dir / "font_0_sc_plus_jp.dds").write_bytes(merged_dds)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def extract_game_sources(game_dir: Path) -> tuple[bytes, bytes, bytes, bytes]:
    """Read the four source assets from an explicit game directory, without writing it."""
    from sora_bilingual.localization.resources import FpacArchive

    try:
        import lz4.frame
    except ImportError as exc:  # Pure merger/tests do not require lz4.
        raise RuntimeError(
            "game extraction needs lz4.frame; use direct DDS paths otherwise"
        ) from exc

    archive_dir = game_dir / "pac" / "steam"
    if not archive_dir.is_dir():
        archive_dir = game_dir
    with FpacArchive(archive_dir / "asset_common_font_sc.pac") as archive:
        primary_fnt = archive.read("asset_sc/common/font/font_0.fnt")
    with FpacArchive(archive_dir / "asset_common_font.pac") as archive:
        secondary_fnt = archive.read("asset/common/font/font_0.fnt")
    with FpacArchive(archive_dir / "image_sc.pac") as archive:
        primary_dds = lz4.frame.decompress(archive.read("asset_sc/dx11/image/font_0.dds"))
    with FpacArchive(archive_dir / "image.pac") as archive:
        secondary_dds = lz4.frame.decompress(archive.read("asset/dx11/image/font_0.dds"))
    return primary_fnt, secondary_fnt, primary_dds, secondary_dds


def _read_direct_inputs(paths: Iterable[Path]) -> tuple[bytes, bytes, bytes, bytes]:
    values = tuple(path.read_bytes() for path in paths)
    if len(values) != 4:
        raise AssertionError("four direct inputs required")
    return values  # type: ignore[return-value]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an unpacked SC-primary + JP font candidate"
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="explicit output directory (never game directory)",
    )
    parser.add_argument(
        "--game", type=Path, help="explicit game directory to read with FpacArchive"
    )
    parser.add_argument("--primary-fnt", type=Path)
    parser.add_argument("--secondary-fnt", type=Path)
    parser.add_argument("--primary-dds", type=Path)
    parser.add_argument("--secondary-dds", type=Path)
    args = parser.parse_args(argv)
    direct = (args.primary_fnt, args.secondary_fnt, args.primary_dds, args.secondary_dds)
    if args.game and any(path is not None for path in direct):
        parser.error("use either --game or all four direct input paths")
    if args.game:
        if _is_within(args.output, args.game):
            parser.error("--output must be outside --game; this tool never modifies the game")
        sources = extract_game_sources(args.game)
    elif all(path is not None for path in direct):
        sources = _read_direct_inputs(direct)  # type: ignore[arg-type]
    else:
        parser.error("provide --game or all four direct input paths")
    manifest = write_merge(args.output, *sources)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
