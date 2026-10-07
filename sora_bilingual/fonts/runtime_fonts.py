"""Verified cache resources for an already-running game's native font loader."""

import hashlib
from pathlib import Path

import lz4.frame

from sora_bilingual.config.locales import LOCALES
from sora_bilingual.fonts.font_delivery import (
    DELIVERY_ROOT,
    LOADER_SHA,
    FontDeliveryError,
    _candidate_manifest,
    _game_target,
    _path_key,
    _read_receipt,
)
from sora_bilingual.fonts.font_merge import parse_dds
from sora_bilingual.localization.resources import FpacArchive


def _owned_source_fonts(game: Path, files: dict[str, bytes], root: Path) -> dict[str, str]:
    """Accept one complete prior installation, never discover arbitrary caches."""
    installed = {}
    for relative in files:
        target = _game_target(game, relative)
        if target.exists():
            installed[relative] = target.read_bytes()
    if not installed or installed == files:
        return {}
    receipt, legacy = _read_receipt(game, root)
    if not receipt or legacy or receipt.get("version") != 2:
        raise FontDeliveryError("旧松散字库缺少本安装的完整受管收据")
    previous = receipt.get("candidate")
    if not isinstance(previous, str) or not Path(previous).is_absolute():
        raise FontDeliveryError("旧字库候选路径无效")
    previous = Path(previous).resolve()
    owner = (Path(root) / _path_key(game)).resolve()
    if (
        previous.parent != owner
        or not owner.is_relative_to(Path(root).resolve())
        or len(previous.name) != 24
        or any(char not in "0123456789abcdef" for char in previous.name)
    ):
        raise FontDeliveryError("旧字库候选不属于本安装的受管缓存")
    manifest, old_files, digest = _candidate_manifest(previous)
    if (
        manifest.get("source_fingerprint") != previous.name
        or receipt.get("manifest_sha256") != digest
    ):
        raise FontDeliveryError("旧字库候选身份与受管收据不符")
    rows = receipt.get("files")
    expected = {**old_files, "xinput1_4.dll": None}
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise FontDeliveryError("旧字库收据必须覆盖全部字体及已审核加载器")
    checked = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise FontDeliveryError("旧字库收据条目无效")
        target = Path(row["path"])
        if not target.is_absolute():
            raise FontDeliveryError("旧字库收据目标路径无效")
        target = target.resolve()
        try:
            relative = target.relative_to(game).as_posix()
        except ValueError as exc:
            raise FontDeliveryError("旧字库收据目标越出本安装") from exc
        if relative not in expected or relative in checked:
            raise FontDeliveryError("旧字库收据存在未知或重复条目")
        checked.add(relative)
        data = target.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        known = (
            LOADER_SHA
            if relative == "xinput1_4.dll"
            else hashlib.sha256(old_files[relative]).hexdigest()
        )
        if (
            actual != known
            or actual != row.get("sha256")
            or type(row.get("size")) is not int
            or len(data) != row["size"]
        ):
            raise FontDeliveryError("当前旧字库与完整受管候选或收据不符")
    if installed != old_files:
        raise FontDeliveryError("当前松散字库已变化，拒绝混用或过时收据")
    return {
        relative: hashlib.sha256(data).hexdigest()
        for relative, data in old_files.items()
        if relative.endswith(".fnt")
    }


def runtime_manifest(game: Path, candidate: Path, *, root: Path = DELIVERY_ROOT) -> dict:
    """Identify actual loaded faces by FNT content, never by guessed UI language.

    Candidate validation checks every metrics/atlas pair. Original identity
    reads only the small FNT archives; it does not reopen the large image PACs.
    This runs in the cancellable preparation worker, not the render/input loop.
    """
    candidate = Path(candidate).resolve()
    game = Path(game).resolve()
    _, files, digest = _candidate_manifest(candidate)
    try:
        owned = _owned_source_fonts(game, files, root)
    except OSError as exc:
        raise FontDeliveryError("无法完整验证本安装的旧字库") from exc
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
                "source_sha256": owned.get(fnt, hashlib.sha256(original).hexdigest()),
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
