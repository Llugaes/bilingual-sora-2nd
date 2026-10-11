"""Build the pinned Frida callback fix without changing the installed toolchain."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor/frida"
OUTPUT = ROOT / "build/frida"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args, cwd, env=None, capture=False):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def unpack_contents(archives, destination, msvc_directory):
    destination = destination.resolve()
    # Resolve the final payload first: the compiler uses the newer redist DLLs.
    # Re-extracting an older intermediate DLL can fail while a build uses it.
    with ExitStack() as stack:
        contents = {}
        for archive in archives:
            package = stack.enter_context(zipfile.ZipFile(archive))
            for name in package.namelist():
                if name.startswith("Contents/") and not name.endswith("/"):
                    contents[name.removeprefix("Contents/")] = (package, name)
        redist = f"VC/Redist/MSVC/{msvc_directory}/x64/Microsoft.VC145.CRT/"
        binary = f"VC/Tools/MSVC/{msvc_directory}/bin/Hostx64/x64/"
        for name, member in list(contents.items()):
            if name.startswith(redist) and name.endswith(".dll"):
                contents[binary + name.removeprefix(redist)] = member
        for name, (package, member) in contents.items():
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Toolchain archive escapes its private directory")
            data = package.read(member)
            if target.is_file() and digest(target) == hashlib.sha256(data).hexdigest():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def build(build_root=None, output=OUTPUT):
    if sys.platform != "win32":
        raise RuntimeError("The pinned Frida runtime is built on Windows x64")
    output = Path(output).resolve()
    recipe_path = VENDOR / "build.json"
    recipe = json.loads(recipe_path.read_text("utf-8"))
    patch = VENDOR / "native-callback-weak-handle.patch"
    if digest(patch) != recipe["patch_sha256"]:
        raise ValueError("Frida patch differs from its reviewed recipe")
    identity = hashlib.sha256(Path(__file__).read_bytes() + recipe_path.read_bytes()).hexdigest()
    wheel_name = f"frida-{recipe['wheel_version']}-cp37-abi3-win_amd64.whl"
    wheel = output / wheel_name
    receipt_path = output / "build-receipt.json"
    if wheel.is_file() and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text("utf-8"))
        if receipt.get("recipe") == identity and receipt.get("wheel_sha256") == digest(wheel):
            return wheel

    # A short private build root also avoids nested Git/npm Windows path limits.
    source = Path(build_root or (Path(tempfile.gettempdir()) / "sora-frida-17180")).resolve()
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        run(
            "git",
            "clone",
            "--branch",
            recipe["frida_version"],
            "--depth",
            "1",
            "--filter=blob:none",
            "https://github.com/frida/frida.git",
            source,
            cwd=source.parent,
        )
    head = run("git", "rev-parse", "HEAD", cwd=source, capture=True).stdout.strip()
    if head != recipe["source_commit"]:
        raise ValueError("Frida build root has a different source commit")
    run(
        "git",
        "-c",
        "core.longpaths=true",
        "submodule",
        "update",
        "--init",
        "--depth",
        "1",
        "--recursive",
        "releng",
        "subprojects/frida-gum",
        "subprojects/frida-core",
        "subprojects/frida-python",
        cwd=source,
    )
    gum = source / "subprojects/frida-gum"
    if (
        run("git", "rev-parse", "HEAD", cwd=gum, capture=True).stdout.strip()
        != recipe["gum_commit"]
    ):
        raise ValueError("Frida Gum source differs")
    current = run("git", "diff", "--", cwd=gum, capture=True).stdout
    if current:
        if current != patch.read_text("utf-8"):
            raise ValueError("Preserving unrelated changes in Frida Gum build root")
    else:
        run("git", "apply", "--check", patch, cwd=gum)
        run("git", "apply", patch, cwd=gum)

    compiler = source / "msvc-14.51"
    compiler.mkdir(exist_ok=True)
    archives = []
    for package in recipe["toolchain_packages"]:
        archive = compiler / package["fileName"]
        if not archive.exists():
            urllib.request.urlretrieve(package["url"], archive)
        # VS manifest size estimates differ from the signed VSIX download;
        # its published SHA-256 identifies the exact bytes.
        if digest(archive) != package["sha256"]:
            raise ValueError("Microsoft toolchain payload checksum differs")
        archives.append(archive)
    unpack_contents(archives, compiler, recipe["msvc_directory"])

    python = source / ".venv/Scripts/python.exe"
    if not python.exists():
        run(sys.executable, "-m", "venv", source / ".venv", cwd=source)
    run(
        python,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "setuptools==84.0.0",
        "wheel==0.48.0",
        "packaging==26.3",
        cwd=source,
    )
    shutil.copy2(python, python.with_name("python3.exe"))
    build_dir = source / "build-1451"
    env = {
        **os.environ,
        "PATH": str(python.parent) + os.pathsep + os.environ["PATH"],
        "PYTHONUTF8": "1",
        "VSLANG": "1033",
        "MESON_BUILD_ROOT": str(build_dir),
    }
    if not (build_dir / "build.ninja").exists():
        configure = (
            "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
            "from releng import winenv;winenv.cached_msvs_dir=Path(sys.argv.pop(2));"
            "from releng.meson_configure import main;main()"
        )
        run(
            python,
            "-X",
            "utf8",
            "-c",
            configure,
            source,
            compiler,
            "--disable-frida-tools",
            "--disable-graft-tool",
            "--disable-gadget",
            "--disable-server",
            "--disable-inject",
            "--enable-frida-python",
            "--",
            "-Dfrida-core:compat=disabled",
            "-Dfrida-core:tests=disabled",
            "-Dfrida-gum:tests=disabled",
            "-Dfrida-gum:v8=enabled",
            cwd=source,
            env=env,
        )
    make = "import sys;sys.path.insert(0,sys.argv[1]);from releng.meson_make import main;main()"
    run(python, "-X", "utf8", "-c", make, source, build_dir, cwd=source, env=env)
    package_root = build_dir / "subprojects/frida-python"
    test_env = {**env, "PYTHONPATH": str(package_root)}
    run(python, "-B", "-X", "utf8", ROOT / "tests/check_native_callback.py", cwd=ROOT, env=test_env)
    env.update(
        FRIDA_EXTENSION=str(package_root / "frida/_frida.pyd"),
        FRIDA_VERSION=recipe["wheel_version"],
    )
    run(
        python,
        "-X",
        "utf8",
        "setup.py",
        "bdist_wheel",
        cwd=source / "subprojects/frida-python",
        env=env,
    )
    built = source / "subprojects/frida-python/dist" / wheel_name
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, wheel)
    receipt_path.write_text(
        json.dumps(
            {
                "recipe": identity,
                "source_commit": head,
                "gum_commit": recipe["gum_commit"],
                "patch_sha256": digest(patch),
                "wheel_sha256": digest(wheel),
                "extension_sha256": digest(package_root / "frida/_frida.pyd"),
                "callback_leak_gate": "passed",
                "published": False,
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    return wheel


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(build(args.build_root, args.output))
