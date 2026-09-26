"""Offline reproducer for the two-glyph Noto-derived fallback donor.

This is a development tool. It never downloads inputs and rejects an output
directory within the supplied game directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QRawFont

from sora_bilingual.fonts.font_merge import (
    FNT_COUNT_OFFSET,
    FNT_DATA_LENGTH_OFFSET,
    HEIGHT_OFFSET,
    WIDTH_OFFSET,
    X_OFFSET,
    Y_OFFSET,
    parse_dds,
    parse_fnt,
)
from sora_bilingual.fonts.universal_fonts import read_fonts


NOTO_SHA256 = "6bcb2a0703aa137e874fc2dffa85f6c21ba9a67fa329e81b8c801663af7e992a"
TEXCONV_SHA256 = "dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06"
# The generated donor intentionally contains only verified gaps. The actual
# game union is checked below; no language-pair or total-glyph count is assumed.
TARGETS = {0xC80B: 0xC80A, 0xD591: 0xD590}
ATLAS_WIDTH, ATLAS_HEIGHT = 128, 56


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _coverage(font: QRawFont, codepoint: int, width: int, height: int) -> list[int]:
    index = font.glyphIndexesForString(chr(codepoint))[0]
    if not index:
        raise ValueError(f"Noto lacks U+{codepoint:04X}")
    image = font.alphaMapForGlyph(index).convertToFormat(QImage.Format.Format_Grayscale8)
    image = image.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(width, height, QImage.Format.Format_Grayscale8)
    canvas.fill(0)
    left, top = (width - image.width()) // 2, (height - image.height()) // 2
    source, target = image.bits().tobytes(), canvas.bits()
    for y in range(image.height()):
        start = (y + top) * canvas.bytesPerLine() + left
        target[start : start + image.width()] = source[
            y * image.bytesPerLine() : y * image.bytesPerLine() + image.width()
        ]
    return [
        canvas.bits().tobytes()[y * canvas.bytesPerLine() + x]
        for y in range(canvas.height())
        for x in range(canvas.width())
    ]


def _signed_distance(coverage: list[int], width: int, height: int) -> list[int]:
    inside = [value >= 128 for value in coverage]
    result = []
    for index, value in enumerate(inside):
        x, y = index % width, index // width
        distance = min(
            (x - other % width) ** 2 + (y - other // width) ** 2
            for other, other_value in enumerate(inside)
            if other_value != value
        )
        result.append(
            max(0, min(255, 128 + (1 if value else -1) * round(math.sqrt(distance) * 20)))
        )
    return result


def _write_source_png(path: Path, pixels: list[int]) -> None:
    image = QImage(ATLAS_WIDTH, ATLAS_HEIGHT, QImage.Format.Format_RGBA8888)
    data = image.bits()
    for y in range(ATLAS_HEIGHT):
        for x in range(ATLAS_WIDTH):
            value = pixels[y * ATLAS_WIDTH + x]
            offset = y * image.bytesPerLine() + x * 4
            data[offset : offset + 4] = bytes((value, value, value, 255))
    if not image.save(str(path)):
        raise OSError(f"cannot write {path}")


def build(noto: Path, texconv: Path, game: Path, output: Path) -> None:
    noto, texconv, game, output = map(
        lambda path: Path(path).resolve(), (noto, texconv, game, output)
    )
    if output == game or output.is_relative_to(game):
        raise ValueError("output must be outside the game directory")
    if sha256(noto) != NOTO_SHA256:
        raise ValueError("Noto OTF hash does not match the recorded source")
    if sha256(texconv) != TEXCONV_SHA256:
        raise ValueError("texconv.exe hash does not match the recorded DirectXTex asset")
    if not (game / "pac/steam").is_dir():
        raise ValueError("game PAC directory is unavailable")
    app = QGuiApplication.instance() or QGuiApplication([])
    del app
    font = QRawFont(str(noto), 45)
    if not font.isValid():
        raise ValueError("Noto Sans CJK KR did not load")
    fonts = read_fonts(game)
    union = set().union(*(source.codepoints for source, _ in fonts.values()))
    if union & set(TARGETS):
        raise ValueError("a donor codepoint is already in the game-font union")
    templates = {glyph.codepoint: glyph.raw for glyph in fonts["asset_ko"][0].glyphs}
    header = bytearray(fonts["asset_ko"][0].header)
    records, pixels = [], [0] * (ATLAS_WIDTH * ATLAS_HEIGHT)
    x = 4
    for codepoint, template_codepoint in TARGETS.items():
        template = templates.get(template_codepoint)
        if template is None:
            raise ValueError(f"Korean metric template U+{template_codepoint:04X} is absent")
        width = struct.unpack_from("<H", template, WIDTH_OFFSET)[0]
        height = struct.unpack_from("<H", template, HEIGHT_OFFSET)[0]
        values = _signed_distance(_coverage(font, codepoint, width, height), width, height)
        record = bytearray(template)
        struct.pack_into("<I", record, 0, codepoint)
        struct.pack_into("<HH", record, X_OFFSET, x, 4)
        records.append(bytes(record))
        for y in range(height):
            pixels[(4 + y) * ATLAS_WIDTH + x : (4 + y) * ATLAS_WIDTH + x + width] = values[
                y * width : (y + 1) * width
            ]
        x = (x + width + 7) // 4 * 4 + 4
    if x > ATLAS_WIDTH:
        raise ValueError("donor atlas is too narrow")
    struct.pack_into("<I", header, FNT_COUNT_OFFSET, len(records))
    struct.pack_into("<I", header, FNT_DATA_LENGTH_OFFSET, len(records) * 24)
    fnt = bytes(header) + b"".join(records)
    parse_fnt(fnt, atlas_width=ATLAS_WIDTH, atlas_height=ATLAS_HEIGHT)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="font-fallback-") as temporary:
        temporary = Path(temporary)
        source = temporary / "noto-kr-gray-sdf.png"
        _write_source_png(source, pixels)
        subprocess.run(
            [
                str(texconv),
                "-nologo",
                "-y",
                "-nogpu",
                "--single-proc",
                "-m",
                "1",
                "-f",
                "BC7_UNORM",
                "-dx10",
                "-o",
                str(temporary),
                str(source),
            ],
            check=True,
        )
        dds = temporary / "noto-kr-gray-sdf.dds"
        image = parse_dds(dds.read_bytes())
        if (image.width, image.height) != (ATLAS_WIDTH, ATLAS_HEIGHT):
            raise ValueError("texconv changed the donor atlas dimensions")
        (output / "font_0.dds").write_bytes(dds.read_bytes())
    (output / "font_0.fnt").write_bytes(fnt)
    print(
        json.dumps(
            {
                "font_0.fnt": sha256(output / "font_0.fnt"),
                "font_0.dds": sha256(output / "font_0.dds"),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--noto", type=Path, required=True)
    parser.add_argument("--texconv", type=Path, required=True)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.noto, args.texconv, args.game, args.output)


if __name__ == "__main__":
    main()
