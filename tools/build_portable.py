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
