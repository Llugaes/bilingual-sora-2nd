"""Verified cache resources for an already-running game's native font loader."""

import hashlib
from pathlib import Path

import lz4.frame

from sora_bilingual.config.locales import LOCALES
from sora_bilingual.fonts.font_delivery import _candidate_manifest
from sora_bilingual.fonts.font_merge import parse_dds
from sora_bilingual.localization.resources import FpacArchive


def runtime_manifest(game: Path, candidate: Path) -> dict:
    """Identify actual loaded faces by FNT content, never by guessed UI language.

    Candidate validation checks every metrics/atlas pair. Original identity
    reads only the small FNT archives; it does not reopen the large image PACs.
    This runs in the cancellable preparation worker, not the render/input loop.
    """
    candidate = Path(candidate).resolve()
    _, files, digest = _candidate_manifest(candidate)
    faces = []
    for suffix in sorted({locale.font_suffix for locale in LOCALES.values()}):
        prefix = f"asset{suffix}"
        fnt = prefix + "/common/font/font_0.fnt"
        dds = prefix + "/dx11/image/font_0.dds"
        if any(len(str(candidate / path).encode("utf-8")) >= 510 for path in (fnt, dds)):
            raise ValueError("字体缓存路径超过游戏文件读取长度限制")
        original = FpacArchive(Path(game) / "pac/steam" / f"asset_common_font{suffix}.pac").read(
            fnt
        )
        image = parse_dds(lz4.frame.decompress(files[dds]))
        image_digest = hashlib.sha256(files[dds]).hexdigest()
        faces.append(
            {
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "sha256": hashlib.sha256(files[fnt]).hexdigest(),
                "path": str(candidate / fnt),
                "alias": "sora_font_" + image_digest,
                "image": {
                    "path": str(candidate / dds),
                    "sha256": image_digest,
                    "width": image.width,
                    "height": image.height,
                },
            }
        )
    return {"version": 1, "candidate": digest, "faces": faces}
