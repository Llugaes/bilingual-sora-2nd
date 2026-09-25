"""Vendor verified CPython and pinned wheels at build time, never on the user's PC."""

import argparse
import csv
import hashlib
import io
import os
import posixpath
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from sora_bilingual.paths import ROOT
from tools.build_release import build

PYTHON_VERSION = "3.14.7"
# https://www.python.org/downloads/release/python-3147/
PYTHON_SHA256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"

# Widgets-only application. Plugins load dynamically, so they are explicit roots;
# their normal and delayed DLL imports are retained transitively below.
QT_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtNetwork"}
QT_PLUGINS = {
    "platforms",
    "styles",
    "imageformats",
    "iconengines",
    "generic",
    "platforminputcontexts",
    "networkinformation",
    "tls",
}


def runtime_payload(files):
    """Select runtime files, preserving licenses and native dependency closure."""
    import pefile

    qt = "Lib/site-packages/PySide6/"
    dlls = {
        n.rsplit("/", 1)[-1].lower(): n
        for n in files
        if n.startswith(qt) and "/" not in n[len(qt) :] and n.endswith(".dll")
    }
    selected = {}
    for name, data in files.items():
        if name.startswith(qt):
            relative = name[len(qt) :]
            parts = relative.split("/")
            if parts[0] in {
                "qml",
                "include",
                "lib",
                "doc",
                "glue",
                "metatypes",
                "typesystems",
                "scripts",
            }:
                continue
            if parts[0] == "plugins" and parts[1] not in QT_PLUGINS:
                continue
            if name.endswith((".pyi", ".lib", ".exe")):
                continue
            if len(parts) == 1:
                if name.endswith(".pyd") and Path(name).stem not in QT_MODULES:
                    continue
                if name.endswith(".dll") and (
                    parts[0].startswith("Qt6") or parts[0] == "pyside6qml.abi3.dll"
                ):
                    continue
        if name.startswith(
            (
                "Lib/site-packages/pygame/docs/",
                "Lib/site-packages/pygame/examples/",
                "Lib/site-packages/pygame/tests/",
            )
        ):
            # pygame's license lives under docs, not just in wheel metadata.
            if (
                "license" not in name.lower()
                and "copying" not in name.lower()
                and "lgpl" not in name.lower()
            ):
                continue
        selected[name] = data

    queue = [n for n in selected if n.startswith(qt) and n.endswith((".dll", ".pyd"))]
    visited = set()
    while queue:
        name = queue.pop()
        if name in visited:
            continue
        visited.add(name)
        with pefile.PE(data=files[name], fast_load=True) as binary:
            binary.parse_data_directories(
                directories=[
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                    pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
                ]
            )
            for entry in getattr(binary, "DIRECTORY_ENTRY_IMPORT", []) + getattr(
                binary, "DIRECTORY_ENTRY_DELAY_IMPORT", []
            ):
                dependency = dlls.get(entry.dll.decode("ascii").lower())
                if dependency and dependency not in selected:
                    selected[dependency] = files[dependency]
                    queue.append(dependency)
    return dict(sorted(selected.items()))


def canonical_records(files):
    """Exclude removed pip launchers from RECORD; their hashes embed builder paths."""
    for name in files:
        if not name.endswith(".dist-info/RECORD"):
            continue
        site = posixpath.dirname(posixpath.dirname(name))
        rows = csv.reader(io.StringIO(files[name].decode("utf-8")))
        included = [row for row in rows if row and posixpath.normpath(site + "/" + row[0]) in files]
        output = io.StringIO(newline="")
        csv.writer(output, lineterminator="\n").writerows(sorted(included))
        files[name] = output.getvalue().encode("utf-8")


def runtime_files(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(
        Path(__file__).read_bytes() + (ROOT / "requirements.txt").read_bytes()
    ).hexdigest()[:16]
    cached_runtime = cache / ("runtime-" + cache_key + ".zip")
    if cached_runtime.exists():
        with zipfile.ZipFile(cached_runtime) as package:
            files = {n: package.read(n) for n in package.namelist()}
        return next(iter(files)).split("/")[1], files
    archive = cache / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if not archive.exists():
        urllib.request.urlretrieve(
            f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{archive.name}", archive
        )
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError("CPython archive checksum mismatch")
    with tempfile.TemporaryDirectory(dir=cache) as directory:
        stage = Path(directory)
        with zipfile.ZipFile(archive) as package:
            package.extractall(stage)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--no-compile",
                "--target",
                str(stage / "Lib/site-packages"),
                "-r",
                str(ROOT / "requirements.txt"),
            ],
            check=True,
        )
        (stage / "python314._pth").write_text(
            "python314.zip\n.\nLib\\site-packages\n..\\..\nimport site\n", encoding="utf-8"
        )
        files = {
            p.relative_to(stage).as_posix(): p.read_bytes()
            for p in sorted(stage.rglob("*"))
            if p.is_file()
            and "__pycache__" not in p.parts
            and not any(part.startswith(".") for part in p.relative_to(stage).parts)
            and p.relative_to(stage).parts[:3] != ("Lib", "site-packages", "bin")
        }
    files = runtime_payload(files)
    canonical_records(files)
    signature = hashlib.sha256()
    for name, data in files.items():
        signature.update(name.encode() + b"\0" + hashlib.sha256(data).digest())
    runtime_id = signature.hexdigest()[:16]
    files = {f"runtime/{runtime_id}/{name}": data for name, data in files.items()}
    with zipfile.ZipFile(cached_runtime, "w") as package:
        for name, data in files.items():
            package.writestr(name, data)
    return runtime_id, files


def portable(version, repository, output, cache=ROOT / "build/downloads"):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 14):
        raise RuntimeError("Build on Windows x64 with Python 3.14")
    runtime_id, files = runtime_files(cache)
    with tempfile.TemporaryDirectory() as directory:
        exe = Path(directory) / "BilingualSora2nd.exe"
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        subprocess.run(
            [
                str(compiler),
                "/nologo",
                "/codepage:65001",
                "/target:winexe",
                "/platform:x64",
                "/optimize+",
                "/reference:System.Windows.Forms.dll",
                "/reference:System.Web.Extensions.dll",
                f"/out:{exe}",
                f"/win32icon:{ROOT / 'assets/sora-bilingual.ico'}",
                str(ROOT / "tools/launcher.cs"),
            ],
            check=True,
        )
        files[exe.name] = exe.read_bytes()
    files["runtime/current.txt"] = (runtime_id + "\n").encode()
    return build(version, repository, output, extra=files, runtime_id=runtime_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", default="dist")
    args = parser.parse_args()
    package, metadata = portable(args.version, args.repository, args.output)
    print(f"Built {package}: {metadata['size'] / 1048576:.1f} MiB")
