"""Run a release EXE with no Python on PATH; exercise real UI process handoff."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket


def staged_update(package, output):
    """Create a local next-version fixture, keeping the real DLLs byte-identical."""
    with zipfile.ZipFile(package) as original:
        manifest = json.loads(original.read("installed-manifest.json"))
        parts = list(map(int, manifest["version"].split(".")))
        parts[-1] += 1
        version = ".".join(map(str, parts))
        distribution = json.loads(original.read("distribution.json"))
        distribution["version"] = version
        replacements = {
            "distribution.json": json.dumps(distribution).encode(),
            "pyproject.toml": re.sub(
                r'(?m)^version = "[^"]+"\r?$',
                f'version = "{version}"',
                original.read("pyproject.toml").decode(),
            ).encode(),
        }
        manifest["version"] = version
        for name, data in replacements.items():
            manifest["files"][name] = hashlib.sha256(data).hexdigest()
        hot = manifest["hot_release"]
        hot["groups"]["ui"] = hashlib.sha256(version.encode()).hexdigest()
        hot["version"] = hashlib.sha256(json.dumps(hot["groups"]).encode()).hexdigest()[:16]
        replacements["installed-manifest.json"] = json.dumps(manifest).encode()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as target:
            for entry in original.infolist():
                target.writestr(
                    entry.filename, replacements.get(entry.filename, original.read(entry))
                )
    return {
        "version": version,
        "repository": manifest["repository"],
        "size": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def check(package):
    app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="bilingual-portable-") as temp:
        root = (Path(temp) / "游戏工具 with spaces").resolve()
        with zipfile.ZipFile(package) as archive:
            archive.extractall(root)
        runtime_id = (root / "runtime/current.txt").read_text().strip()
        python = root / "runtime" / runtime_id / "python.exe"
        environment = {
            **os.environ,
            "PATH": os.environ["SystemRoot"] + r"\System32",
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONPATH": "does-not-exist",
        }
        result = subprocess.run(
            [
                str(python),
                "-B",
                "-X",
                "utf8",
                "-c",
                """
import sys, frida, lz4.frame, pygame, pefile
from PySide6 import QtWidgets, QtNetwork
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage, QImageReader, QIcon
from sora_bilingual.paths import ROOT
app = QtWidgets.QApplication([])
formats = {bytes(f) for f in QImageReader.supportedImageFormats()}
assert {b'ico', b'png', b'svg'} <= formats, formats
assert not QIcon(str(ROOT / 'assets/sora-bilingual.ico')).isNull()
assert not QImage.fromData(QByteArray(b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="red"/></svg>'), 'svg').isNull()
for style in QtWidgets.QStyleFactory.keys():
    assert QtWidgets.QStyleFactory.create(style) is not None, style
assert QtNetwork.QSslSocket.supportsSsl()
pygame.display.init()
pygame.joystick.init()
pygame.event.pump()
pygame.joystick.get_count()
pygame.quit()
print(ROOT)
print(sys.version)
""",
            ],
            cwd=temp,
            env=environment,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        assert str(root) in result.stdout
        control = root / "generated/native-control.json"
        control.parent.mkdir(exist_ok=True)
        control.write_text('{"ui_language":"en"}', encoding="utf-8")
        name = "SoraBilingual-" + hashlib.sha256(str(control.resolve()).encode()).hexdigest()[:16]

        def request(command):
            socket = QLocalSocket()
            socket.connectToServer(name)
            if not socket.waitForConnected(200):
                return None
            socket.write(command.encode() + b"\n")
            socket.waitForBytesWritten(500)
            if command == "status" and socket.waitForReadyRead(500):
                return json.loads(bytes(socket.readAll()))
            socket.waitForDisconnected(2000)
            return None

        def wait_for(predicate):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = request("status")
                if state and predicate(state):
                    return state
                time.sleep(0.1)
            log = root / "generated/overlay-error.log"
            raise AssertionError(
                log.read_text("utf-8") if log.exists() else "EXE startup timed out"
            )

        # Simulate power loss after switching the selector to an incomplete runtime.
        # The EXE must choose the previous runtime to safely roll back before importing Qt.
        token = "c" * 32
        update_dir = root / "generated/updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        # Keep this offline integration test independent of GitHub/network timing.
        (update_dir / "preferences.json").write_text('{"policy":"off"}')
        backup = update_dir / ("backup-" + token) / "runtime/current.txt"
        backup.parent.mkdir(parents=True)
        previous = (runtime_id + "\n").encode()
        backup.write_bytes(previous)
        next_selector = ("f" * 16 + "\n").encode()
        (root / "runtime/current.txt").write_bytes(next_selector)
        (update_dir / "transaction.json").write_text(
            json.dumps(
                {
                    "id": token,
                    "phase": "prepared",
                    "recovery_runtime": runtime_id,
                    "previous": {"runtime/current.txt": hashlib.sha256(previous).hexdigest()},
                    "next": {"runtime/current.txt": hashlib.sha256(next_selector).hexdigest()},
                }
            ),
            encoding="utf-8",
        )

        started = time.monotonic()
        subprocess.run(
            [str(root / "BilingualSora2nd.exe"), "--no-auto-connect", "--expanded"],
            cwd=temp,
            env=environment,
            check=True,
            timeout=10,
        )
        try:
            before = wait_for(lambda state: state["expanded"])
            print("started", before, flush=True)
            seconds = time.monotonic() - started
            assert not before["auto_connect"]
            assert (root / "runtime/current.txt").read_text().strip() == runtime_id
            assert not (update_dir / "transaction.json").exists()
            fixture = Path(temp) / "next.zip"
            metadata = staged_update(package, fixture)
            metadata_path = Path(temp) / "metadata.json"
            metadata_path.write_text(json.dumps(metadata))
            install = subprocess.run(
                [
                    str(python),
                    "-B",
                    "-X",
                    "utf8",
                    "-c",
                    "import json,sys; from sora_bilingual.updates.update_installer import install; "
                    "print(install(sys.argv[1], sys.argv[2], json.load(open(sys.argv[3]))))",
                    str(root),
                    str(fixture),
                    str(metadata_path),
                ],
                cwd=temp,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            assert install.returncode == 0, install.stderr
            print("installed", install.stdout.strip(), flush=True)
            upgraded = wait_for(lambda state: state["pid"] != before["pid"])
            assert upgraded["expanded"]
            assert json.loads(control.read_text())["ui_language"] == "en"
            before = upgraded
            request("hide")
            wait_for(lambda state: state["hidden"])
            request("reload")
            after = wait_for(lambda state: state["pid"] != before["pid"])
            assert after["hidden"] and not after["expanded"]
            subprocess.run(
                [str(root / "BilingualSora2nd.exe"), "--no-auto-connect"],
                cwd=temp,
                env=environment,
                check=True,
                timeout=10,
            )
            restored = wait_for(lambda state: state["expanded"])
            assert restored["pid"] == after["pid"], "relaunch created a duplicate UI"
            assert not (root / "generated/native-status.json").exists()
            print(
                json.dumps(
                    {
                        "exe_start_seconds": round(seconds, 3),
                        "runtime_id": runtime_id,
                        "no_system_python": True,
                        "unicode_path": True,
                        "reload": True,
                        "single_instance": True,
                        "interrupted_update_recovered": True,
                        "live_install_with_loaded_dlls": True,
                        "game_attached": False,
                    }
                ),
                flush=True,
            )
        finally:
            request("quit")
            # Windows releases loaded Qt/runtime DLLs asynchronously at process exit.
            time.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    check(parser.parse_args().package)
