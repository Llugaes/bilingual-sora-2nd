"""Build an offline per-user Windows setup from the verified portable payload."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

from sora_bilingual.paths import ROOT
from sora_bilingual.updates.update_installer import package_contents

INNO_VERSION = "6.7.3"
INNO_SHA256 = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"


def compiler():
    directory = ROOT / "build/toolchain"
    directory.mkdir(parents=True, exist_ok=True)
    setup = directory / f"innosetup-{INNO_VERSION}.exe"
    if not setup.exists():
        urllib.request.urlretrieve(
            f"https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/{setup.name}", setup
        )
    if hashlib.sha256(setup.read_bytes()).hexdigest() != INNO_SHA256:
        raise ValueError("Inno Setup checksum mismatch")
    install_dir = directory / f"inno-{INNO_VERSION}"
    executable = install_dir / "ISCC.exe"
    if not executable.exists():
        subprocess.run(
            [
                str(setup),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/CURRENTUSER",
                "/NOICONS",
                f"/DIR={install_dir}",
            ],
            check=True,
        )
    return executable


def build(metadata_path):
    metadata_path = Path(metadata_path).resolve()
    metadata = json.loads(metadata_path.read_text("utf-8"))
    manifest, contents = package_contents(metadata_path.parent / metadata["asset"], metadata)
    exe = compiler()
    with tempfile.TemporaryDirectory(prefix="bilingual-setup-") as temp:
        stage = Path(temp)
        for name, data in contents.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (stage / "installed-manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        subprocess.run(
            [
                str(exe),
                "/Qp",
                f"/DAppVersion={metadata['version']}",
                f"/DPayloadDir={stage}",
                f"/DOutputDir={metadata_path.parent}",
                str(ROOT / "tools/installer.iss"),
            ],
            check=True,
        )
    setup = metadata_path.parent / f"bilingual-sora-2nd-{metadata['version']}-windows-x64-setup.exe"
    metadata["installer"] = {
        "asset": setup.name,
        "size": setup.stat().st_size,
        "sha256": hashlib.sha256(setup.read_bytes()).hexdigest(),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Built {setup.name}: {setup.stat().st_size / 1048576:.1f} MiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    build(parser.parse_args().metadata)
