"""Prepare, verify, and transactionally install locally generated game fonts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid

import lz4.frame

from sora_bilingual.config import locales
from sora_bilingual.config.locales import LOCALES
from sora_bilingual.config.native_config import replace_file, write_config
from sora_bilingual.fonts import universal_fonts
from sora_bilingual.fonts import font_merge
from sora_bilingual.fonts.font_merge import parse_dds, parse_fnt
from sora_bilingual.fonts.universal_fonts import MAX_DECODED_BYTES, build
from sora_bilingual.paths import ROOT


LOADER_SHA = "e08a18068a482bb5d187a62023759c0e14ab69d76395b773ef0405d35e2ac8c7"
LOADER = ROOT / "assets/sora2looseload/xinput1_4.dll"
DELIVERY_ROOT = ROOT / "generated/font-delivery"
LEGACY_RECEIPT = ROOT / "generated/font-install.json"
BUILD_DEPENDENCIES = (
    Path(universal_fonts.__file__),
    Path(font_merge.__file__),
    Path(locales.__file__),
)


class FontDeliveryError(RuntimeError):
    """A local font candidate or installation failed validation."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_key(game: Path) -> str:
    return hashlib.sha256(str(game.resolve()).casefold().encode("utf-8")).hexdigest()[:20]


def receipt_path(game: Path, root: Path = DELIVERY_ROOT) -> Path:
    """Keep receipts per game installation; no other installation is trusted."""
    return root / "receipts" / f"{_path_key(game)}.json"


def _source_archives(game: Path) -> tuple[Path, ...]:
    archive = game / "pac/steam"
    suffixes = tuple(dict.fromkeys(locale.font_suffix for locale in LOCALES.values()))
    return tuple(
        archive / name
        for suffix in suffixes
        for name in (f"asset_common_font{suffix}.pac", f"image{suffix}.pac")
    )


def source_fingerprint(game: Path) -> str:
    """Cheap source identity: only archive metadata, never a recurring full read."""
    rows = []
    for path in _source_archives(game):
        try:
            stat = path.stat()
        except OSError as exc:
            raise FontDeliveryError(f"缺少游戏字库档案：{path}") from exc
        rows.append((path.name, stat.st_size, stat.st_mtime_ns))
    for path in BUILD_DEPENDENCIES:
        try:
            rows.append(("builder", path.name, _sha(path.read_bytes())))
        except OSError as exc:
            raise FontDeliveryError(f"字体构建依赖缺失：{path}") from exc
    for path in universal_fonts.fallback_dependencies():
        try:
            rows.append(("fallback", path.name, _sha(path.read_bytes())))
        except OSError as exc:
            raise FontDeliveryError(f"字体回退资源缺失：{path}") from exc
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return _sha(payload)[:24]


def _expected_paths() -> set[str]:
    return {
        f"asset{locale.font_suffix}/{tail}"
        for locale in LOCALES.values()
        for tail in ("common/font/font_0.fnt", "dx11/image/font_0.dds")
    }


def _candidate_manifest(candidate: Path) -> tuple[dict[str, object], dict[str, bytes], str]:
    manifest_path = candidate / "manifest.json"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise FontDeliveryError("字库候选清单无效") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != 2:
        raise FontDeliveryError("字库候选版本不受支持")
    rows = manifest.get("files")
    expected_paths = _expected_paths()
    if not isinstance(rows, list) or len(rows) != len(expected_paths):
        raise FontDeliveryError("字库候选没有覆盖全部语言资源路径")
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if (
        len(paths) != len(rows)
        or any(not isinstance(path, str) for path in paths)
        or len(set(paths)) != len(paths)
        or set(paths) != expected_paths
    ):
        raise FontDeliveryError("字库候选没有覆盖全部语言资源路径")
    files: dict[str, bytes] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise FontDeliveryError("字库候选条目无效")
        relative, expected = row.get("path"), row.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise FontDeliveryError("字库候选摘要无效")
        path = (candidate / relative).resolve()
        if not path.is_relative_to(candidate.resolve()):
            raise FontDeliveryError("字库候选路径越界")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise FontDeliveryError(f"字库候选缺少文件：{relative}") from exc
        if _sha(data) != expected:
            raise FontDeliveryError(f"字库候选摘要不匹配：{relative}")
        files[relative] = data
    glyph_sets = []
    for prefix in {f"asset{locale.font_suffix}" for locale in LOCALES.values()}:
        try:
            dds = lz4.frame.decompress(files[prefix + "/dx11/image/font_0.dds"])
            if len(dds) > MAX_DECODED_BYTES:
                raise FontDeliveryError("字库超过游戏已验证的解压容量")
            image = parse_dds(dds)
            font = parse_fnt(
                files[prefix + "/common/font/font_0.fnt"],
                atlas_width=image.width,
                atlas_height=image.height,
            )
            glyph_sets.append(frozenset(font.codepoints))
        except (FontDeliveryError, ValueError, RuntimeError) as exc:
            if isinstance(exc, FontDeliveryError):
                raise
            raise FontDeliveryError(f"字库候选格式无效：{prefix}") from exc
    if not glyph_sets or any(glyphs != glyph_sets[0] for glyphs in glyph_sets[1:]):
        raise FontDeliveryError("字库候选各语言字形集合不一致")
    if not isinstance(manifest.get("glyphs"), int) or manifest["glyphs"] != len(glyph_sets[0]):
        raise FontDeliveryError("字库候选字形计数不匹配")
    return manifest, files, _sha(raw)


def _safe_cache_remove(path: Path, root: Path) -> None:
    resolved_root = Path(root).resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
        raise FontDeliveryError("拒绝清理字体缓存目录外的文件")
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path)
    else:
        resolved_path.unlink(missing_ok=True)


def _replace_candidate(stage: Path, candidate: Path, root: Path) -> None:
    """Replace only this delivery cache entry, retaining a recoverable backup."""
    resolved_root = Path(root).resolve()
    if not stage.resolve().is_relative_to(
        resolved_root
    ) or not candidate.parent.resolve().is_relative_to(resolved_root):
        raise FontDeliveryError("字体缓存路径越界")
    if not candidate.exists():
        stage.replace(candidate)
        return
    quarantine = candidate.parent / f".{candidate.name}.invalid-{uuid.uuid4().hex}"
    candidate.replace(quarantine)
    try:
        stage.replace(candidate)
    except Exception:
        quarantine.replace(candidate)
        raise
    _safe_cache_remove(quarantine, root)


def prepare(game: Path, *, root: Path = DELIVERY_ROOT, builder=build) -> Path:
    """Build once per local source fingerprint, without touching the game directory."""
    game = Path(game).resolve()
    fingerprint = source_fingerprint(game)
    candidate = root / _path_key(game) / fingerprint
    try:
        manifest, _, _ = _candidate_manifest(candidate)
        if manifest.get("source_fingerprint") == fingerprint:
            return candidate
    except FontDeliveryError:
        pass
    candidate.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="font-stage-", dir=candidate.parent))
    try:
        manifest = builder(game, stage)
        manifest["source_fingerprint"] = fingerprint
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _candidate_manifest(stage)
        _replace_candidate(stage, candidate, root)
        return candidate
    finally:
        if stage.exists():
            _safe_cache_remove(stage, root)


def _read_receipt(game: Path, root: Path = DELIVERY_ROOT) -> tuple[dict[str, object] | None, bool]:
    for path, legacy in ((receipt_path(game, root), False), (LEGACY_RECEIPT, True)):
        try:
            value = json.loads(path.read_text("utf-8"))
        except OSError, ValueError:
            continue
        if isinstance(value, dict) and Path(str(value.get("game", ""))).resolve() == game.resolve():
            return value, legacy
    return None, False


def _receipt_files(receipt: dict[str, object] | None, game: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not receipt:
        return result
    for row in receipt.get("files", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            continue
        try:
            relative = Path(row["path"]).resolve().relative_to(game.resolve()).as_posix()
        except ValueError:
            continue
        if isinstance(row.get("sha256"), str):
            result[relative] = row["sha256"]
    return result


def _game_target(game: Path, relative: str) -> Path:
    target = (game / relative).resolve()
    if not target.is_relative_to(game.resolve()):
        raise FontDeliveryError("安装目标越出游戏目录")
    return target


def health(game: Path, candidate: Path, *, loader: Path = LOADER, root: Path = DELIVERY_ROOT):
    """Return an inspectable state; this function never writes either directory."""
    game = Path(game).resolve()
    manifest, fonts, manifest_sha = _candidate_manifest(Path(candidate))
    try:
        loader_data = Path(loader).read_bytes()
    except OSError as exc:
        raise FontDeliveryError("内置松散文件加载器缺失") from exc
    if _sha(loader_data) != LOADER_SHA:
        raise FontDeliveryError("内置松散文件加载器摘要不匹配")
    files = {"xinput1_4.dll": loader_data, **fonts}
    receipt, legacy = _read_receipt(game, root)
    owned = _receipt_files(receipt, game)
    missing, conflicts, replaceable = [], [], []
    for relative, expected in files.items():
        target = _game_target(game, relative)
        if not target.exists():
            missing.append(relative)
        elif not target.is_file():
            conflicts.append(relative)
        else:
            actual = _sha(target.read_bytes())
            if actual == _sha(expected):
                continue
            if owned.get(relative) == actual:
                replaceable.append(relative)
            else:
                conflicts.append(relative)
    state = "healthy" if not missing and not conflicts and not replaceable else "repairable"
    if conflicts:
        state = "conflict"
    return {
        "state": state,
        "game": str(game),
        "candidate": str(candidate),
        "manifest_sha256": manifest_sha,
        "files": files,
        "missing": missing,
        "replaceable": replaceable,
        "conflicts": conflicts,
        "legacy_receipt": legacy,
        "receipt": receipt,
        "glyphs": manifest.get("glyphs"),
    }


def _replace_bytes(path: Path, data: bytes) -> None:
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp")
    try:
        with handle:
            handle.write(data)
        replace_file(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def _create_bytes(path: Path, data: bytes, register_owned) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        # `xb` is the ownership boundary. Register before the first write so
        # partial writes roll back, but never claim a competing file that
        # caused the exclusive open to fail.
        register_owned()
        stream.write(data)


def _write_receipt(game: Path, value: dict[str, object], root: Path) -> None:
    path = receipt_path(game, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_config(value, path)


def ensure(
    game: Path,
    candidate: Path,
    *,
    game_running: bool,
    is_game_running=None,
    root: Path = DELIVERY_ROOT,
    loader: Path = LOADER,
):
    """Install only owned or byte-identical files; rollback every game write on failure."""
    game = Path(game).resolve()
    report = health(game, candidate, loader=loader, root=root)
    files: dict[str, bytes] = report.pop("files")  # type: ignore[assignment]
    if report["state"] == "conflict":
        return report
    receipt = {
        "version": 2,
        "game": str(game),
        "manifest_sha256": report["manifest_sha256"],
        "candidate": str(candidate),
        "files": [
            {"path": str(game / relative), "size": len(data), "sha256": _sha(data)}
            for relative, data in sorted(files.items())
        ],
    }
    if report["state"] == "healthy":
        _write_receipt(game, receipt, root)
        return {**report, "state": "healthy", "adopted": True}

    def game_is_running() -> bool:
        if is_game_running is None:
            return game_running
        try:
            return bool(is_game_running())
        except Exception:
            # A failed process query must never permit a game-file mutation.
            return True

    if game_is_running():
        return {**report, "state": "restart-required", "staged": True}

    from sora_bilingual.game.hooks import verify_target

    verify_target(game / "sora_2nd.exe")
    # `health` and executable validation can take time. Query immediately
    # before opening the transaction instead of trusting an earlier snapshot.
    if game_is_running():
        return {**report, "state": "restart-required", "staged": True}
    created: list[Path] = []
    originals: dict[Path, bytes] = {}
    replaceable = set(report["replaceable"])
    owned = _receipt_files(report.get("receipt"), game)
    try:
        for relative, data in sorted(files.items()):
            target = _game_target(game, relative)
            if relative in replaceable:
                original = target.read_bytes()
                if _sha(original) != owned.get(relative):
                    raise FontDeliveryError(f"拒绝覆盖安装后被修改的文件：{target}")
                originals[target] = original
                created.append(target)
                _replace_bytes(target, data)
            elif target.exists():
                # A changed source may alter only some assets. Exact existing
                # bytes are safe to retain even if another asset is replaced.
                if _sha(target.read_bytes()) == _sha(data):
                    continue
                raise FontDeliveryError(f"拒绝覆盖未知文件：{target}")
            else:
                _create_bytes(target, data, lambda: created.append(target))
            if _sha(target.read_bytes()) != _sha(data):
                raise FontDeliveryError(f"字库安装校验失败：{target}")
        _write_receipt(game, receipt, root)
    except Exception:
        for target in reversed(created):
            if target in originals:
                _replace_bytes(target, originals[target])
            else:
                target.unlink(missing_ok=True)
        raise
    return {**report, "state": "installed", "receipt": receipt}
