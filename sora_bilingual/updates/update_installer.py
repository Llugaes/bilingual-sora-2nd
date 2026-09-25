"""Verified code-only updates with an on-disk rollback journal. Standard library only."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import uuid
import zipfile

PROTECTED = {
    ".git",
    ".github",
    ".venv",
    "generated",
    "logs",
    "dist",
    "build",
    "tests",
    "debug",
    "config.json",
    "installed-manifest.json",
}
INTERNAL = {"installed-manifest.json", "generated/tool-release.json"}


class UpdateBusy(RuntimeError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative_file(name, internal=False):
    if not isinstance(name, str) or "\\" in name or name.startswith("/") or not name:
        return False
    parts = PurePosixPath(name).parts
    if "/".join(parts) != name:
        return False
    for part in parts:
        if (
            part in (".", "..")
            or part.endswith((".", " "))
            or re.search(r'[\x00-\x1f<>:"|?*]', part)
        ):
            return False
        if re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part, re.I):
            return False
    if internal and name in INTERNAL:
        return True
    if parts[0].lower() in PROTECTED or any(p.startswith(".") for p in parts):
        return False
    return (
        (
            len(parts) == 1
            and (
                name == "LICENSE"
                or Path(name).suffix.lower()
                in (".py", ".js", ".json", ".md", ".txt", ".cmd", ".ps1", ".toml")
            )
        )
        or (
            len(parts) >= 2
            and parts[0] == "sora_bilingual"
            and Path(name).suffix.lower() in (".py", ".js")
        )
        or (
            len(parts) == 2
            and parts[0] == "assets"
            and Path(name).suffix.lower() in (".ico", ".svg")
        )
    )


def target(root, name, internal=False):
    if not relative_file(name, internal):
        raise ValueError("更新路径不允许：" + str(name))
    root = Path(root).resolve()
    path = root / name
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)():
            raise ValueError("更新路径不能经过链接或联接")
    if not path.resolve().is_relative_to(root):
        raise ValueError("更新路径越界")
    return path


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False, suffix=".tmp") as out:
        temporary = Path(out.name)
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


class UpdateLease:
    """Same OS lock as native_probe: installing never races live attachment."""

    def __init__(self, root):
        self.path = Path(root) / "generated/native-backend.lock"
        self.file = None

    def __enter__(self):
        import msvcrt

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise UpdateBusy("更新已准备，将在游戏连接结束后自动安装")
        return self

    def __exit__(self, *_):
        self.file.close()


def validate_manifest(manifest):
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != 1
        or manifest.get("application") != "sora-bilingual"
    ):
        raise ValueError("不支持的更新清单")
    from sora_bilingual.updates.github_updates import version_tuple

    version_tuple(manifest.get("version"))
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(manifest.get("repository"))):
        raise ValueError("更新仓库无效")
    if manifest.get("python") != [3, 14] or not re.fullmatch(
        "[0-9a-f]{64}", str(manifest.get("requirements_sha256"))
    ):
        raise ValueError("更新运行环境不兼容")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or len(files) > 500:
        raise ValueError("更新文件清单不合法")
    folded = set()
    for name, value in files.items():
        if (
            not relative_file(name)
            or name.casefold() in folded
            or not re.fullmatch("[0-9a-f]{64}", str(value))
        ):
            raise ValueError("更新路径或摘要不合法")
        folded.add(name.casefold())
    if not {
        "launch.py",
        "sora_bilingual/app/native_overlay.py",
        "distribution.json",
        "requirements.txt",
        "sora_bilingual/bootstrap.py",
    } <= set(files):
        raise ValueError("更新包缺少入口")
    hot = manifest.get("hot_release", {})
    if not isinstance(hot, dict) or set(hot.get("groups", {})) != {
        "ui",
        "logic",
        "catalog",
        "resident",
    }:
        raise ValueError("更新缺少热加载清单")
    if any(not re.fullmatch("[0-9a-f]{64}", str(v)) for v in hot["groups"].values()):
        raise ValueError("热加载摘要不合法")
    if not re.fullmatch("[0-9a-f]{16}", str(hot.get("version"))):
        raise ValueError("热加载版本不合法")
    return manifest


def package_contents(package, expected):
    if Path(package).stat().st_size > 128 * 1024 * 1024:
        raise ValueError("更新包过大")
    raw = Path(package).read_bytes()
    if len(raw) != expected["size"] or digest(raw) != expected["sha256"]:
        raise ValueError("更新包校验失败")
    with zipfile.ZipFile(package) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > 501:
            raise ValueError("更新包文件过多")
        if len(names) != len(set(n.casefold() for n in names)):
            raise ValueError("更新包存在重复路径")
        if sum(e.file_size for e in entries) > 128 * 1024 * 1024:
            raise ValueError("更新包展开过大")
        for e in entries:
            if e.is_dir() or stat.S_ISLNK(e.external_attr >> 16) or (e.external_attr & 0x400):
                raise ValueError("更新包不允许链接或特殊目录")
            if e.filename != "installed-manifest.json" and not relative_file(e.filename):
                raise ValueError("更新包含受保护路径")
        manifest = validate_manifest(json.loads(archive.read("installed-manifest.json")))
        if (
            manifest["version"] != expected["version"]
            or manifest.get("repository") != expected["repository"]
        ):
            raise ValueError("更新包版本或仓库不匹配")
        if set(names) != set(manifest["files"]) | {"installed-manifest.json"}:
            raise ValueError("更新包文件与清单不一致")
        contents = {name: archive.read(name) for name in manifest["files"]}
        if any(digest(data) != manifest["files"][name] for name, data in contents.items()):
            raise ValueError("更新文件摘要不匹配")
        distribution = json.loads(contents["distribution.json"])
        if distribution.get("version") != manifest["version"] or distribution.get(
            "repository"
        ) != manifest.get("repository"):
            raise ValueError("安装版本信息不一致")
        return manifest, contents


def _journal(root):
    return Path(root) / "generated/updates/transaction.json"


def _recover_locked(root):
    root = Path(root)
    journal = _journal(root)
    if not journal.exists():
        return None
    state = json.loads(journal.read_text("utf-8"))
    token = state.get("id", "")
    if not re.fullmatch("[0-9a-f]{32}", token):
        raise ValueError("更新恢复记录不合法")
    backup = root / "generated/updates" / ("backup-" + token)
    if state.get("phase") == "committed":
        manifest = validate_manifest(
            json.loads((root / "installed-manifest.json").read_text("utf-8"))
        )
        write_json(target(root, "generated/tool-release.json", True), manifest["hot_release"])
        result = "committed"
    else:
        for name, previous in state["previous"].items():
            path = target(root, name, True)
            if previous is None:
                if path.exists():
                    if digest(path.read_bytes()) != state["next"].get(name):
                        raise ValueError("回滚遇到外部修改，已保留现场：" + name)
                    path.unlink()
            else:
                saved = backup / name
                if digest(saved.read_bytes()) != previous:
                    raise ValueError("回滚备份损坏：" + name)
                if path.exists() and digest(path.read_bytes()) not in (
                    previous,
                    state["next"].get(name),
                ):
                    raise ValueError("回滚遇到外部修改，已保留现场：" + name)
                atomic_bytes(path, saved.read_bytes())
        result = "rolled_back"
    journal.unlink()
    (root / "generated/update-installing.json").unlink(missing_ok=True)
    return result


def recover(root):
    if not _journal(root).exists():
        return None
    with UpdateLease(root):
        return _recover_locked(root)


def install(root, package, expected):
    root = Path(root).resolve()
    manifest, contents = package_contents(package, expected)
    recover(root)
    receipt = root / "installed-manifest.json"
    if not receipt.is_file():
        raise ValueError("当前为开发目录，更新不会覆盖本地源码；发行包安装后可自动更新")
    old = validate_manifest(json.loads(receipt.read_text("utf-8")))
    from sora_bilingual.updates.github_updates import version_tuple

    if version_tuple(manifest["version"]) <= version_tuple(old["version"]):
        raise ValueError("不安装相同或更旧的版本")
    if old.get("repository") != manifest.get("repository"):
        raise ValueError("更新来源与安装来源不一致")
    if manifest.get("python") != list(sys.version_info[:2]):
        raise ValueError("此更新需要不同的 Python 运行环境，请按发行说明升级")
    if digest((root / "requirements.txt").read_bytes()) != manifest.get("requirements_sha256"):
        raise ValueError("此更新改变了运行依赖，请按发行说明升级运行环境")
    with UpdateLease(root):
        _recover_locked(root)
        current = validate_manifest(json.loads(receipt.read_text("utf-8")))
        if current != old:
            raise ValueError("安装状态已改变，请重新检查更新")
        for name, value in old["files"].items():
            path = target(root, name)
            if not path.is_file() or digest(path.read_bytes()) != value:
                raise ValueError("检测到本地文件修改，已停止覆盖：" + name)
        for name in set(contents) - set(old["files"]):
            if target(root, name).exists():
                raise ValueError("新文件与本地文件冲突：" + name)
        updates = {
            **contents,
            "installed-manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        }
        names = set(old["files"]) | set(updates) | {"generated/tool-release.json"}
        token = uuid.uuid4().hex
        backup = root / "generated/updates" / ("backup-" + token)
        previous = {}
        for name in names:
            path = target(root, name, True)
            if path.exists():
                data = path.read_bytes()
                atomic_bytes(backup / name, data)
                previous[name] = digest(data)
            else:
                previous[name] = None
        state = {
            "id": token,
            "phase": "prepared",
            "previous": previous,
            "next": {k: digest(v) for k, v in updates.items()},
        }
        write_json(_journal(root), state)
        write_json(root / "generated/update-installing.json", {"version": manifest["version"]})
        try:
            for name, data in updates.items():
                atomic_bytes(target(root, name, True), data)
            for name in set(old["files"]) - set(contents):
                target(root, name).unlink()
            state["phase"] = "committed"
            write_json(_journal(root), state)
            _recover_locked(root)
        except Exception:
            _recover_locked(root)
            raise
    return manifest["version"]
