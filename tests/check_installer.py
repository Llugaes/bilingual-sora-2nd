"""Real silent install, repair, running-process guard and uninstall in an isolated folder."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import winreg

KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{F5F851F5-DB86-45CA-A522-2C5BD87DBF19}_is1"


def check(metadata):
    # Never repoint or remove an actual user's registered installation.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY):
            raise RuntimeError("Installer test requires no existing registered installation")
    except FileNotFoundError:
        pass
    metadata = Path(metadata).resolve()
    descriptor = json.loads(metadata.read_text("utf-8"))["installer"]
    setup = metadata.parent / descriptor["asset"]
    assert hashlib.sha256(setup.read_bytes()).hexdigest() == descriptor["sha256"]
    with tempfile.TemporaryDirectory(prefix="bilingual-install-test-") as temp:
        root = Path(temp).resolve() / "安装工具 with spaces"
        group = "Bilingual Test " + uuid.uuid4().hex[:8]
        command = [
            str(setup),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            f"/DIR={root}",
            f"/GROUP={group}",
            "/MERGETASKS=!desktopicon",
            "/LANG=chinesesimplified",
            f"/LOG={Path(temp) / 'install.log'}",
        ]

        def install():
            return subprocess.run(command, timeout=180).returncode

        child = None
        try:
            assert install() == 0
            manifest = json.loads((root / "installed-manifest.json").read_text("utf-8"))
            assert not [
                n
                for n, h in manifest["files"].items()
                if hashlib.sha256((root / n).read_bytes()).hexdigest() != h
            ]
            config = root / "generated/native-control.json"
            config.parent.mkdir(exist_ok=True)
            config.write_text('{"primary":"de","secondary":"fr"}')
            python = root / "runtime" / manifest["runtime_id"] / "python.exe"
            child = subprocess.Popen(
                [str(python), "-B", "-c", "import time; time.sleep(120)"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            time.sleep(0.5)
            assert install() != 0, "must not install over a running runtime"
            assert child.poll() is None, "setup must not close running processes"
            child.terminate()
            child.wait(10)
            child = None
            assert install() == 0, "repair failed"
            assert json.loads(config.read_text()) == {"primary": "de", "secondary": "fr"}
            distribution = root / "distribution.json"
            original = distribution.read_bytes()
            newer = json.loads(original)
            newer["version"] = "99.0.0"
            distribution.write_text(json.dumps(newer), encoding="utf-8")
            assert install() != 0, "must not silently downgrade a newer installation"
            distribution.write_bytes(original)
            shortcut = (
                Path(os.environ["APPDATA"])
                / "Microsoft/Windows/Start Menu/Programs"
                / group
                / "Bilingual Sora 2nd.lnk"
            )
            assert shortcut.exists(), "\n".join(
                line
                for line in (Path(temp) / "install.log").read_text("utf-8-sig").splitlines()
                if "shortcut" in line.lower() or "group" in line.lower()
            )
        finally:
            if child is not None:
                child.terminate()
                child.wait(10)
            uninstall = root / "unins000.exe"
            if uninstall.exists():
                subprocess.run(
                    [str(uninstall), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                    check=True,
                    timeout=120,
                )
                # The uninstaller's temporary worker can briefly outlive its launcher.
                for _ in range(50):
                    if not (root / "BilingualSora2nd.exe").exists():
                        break
                    time.sleep(0.1)
            assert not (root / "BilingualSora2nd.exe").exists()
            assert not (root / "runtime").exists()
        assert config.exists(), "uninstall must preserve settings"
        print(
            json.dumps(
                {
                    "offline_install": True,
                    "repair_preserves_config": True,
                    "running_process_guard": True,
                    "start_menu_shortcut": True,
                    "uninstall_preserves_config": True,
                    "game_started": False,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    check(parser.parse_args().metadata)
