"""Real Qt process handoff, isolated configuration and automatic game access off."""

import hashlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix="sora-overlay-update-") as tmp:
        control = Path(tmp) / "config.json"
        status = Path(tmp) / "status.json"
        control.write_text("{}")
        name = "SoraBilingual-" + hashlib.sha256(str(control.resolve()).encode()).hexdigest()[:16]

        def request(command):
            socket = QLocalSocket()
            socket.connectToServer(name)
            if not socket.waitForConnected(200):
                return None
            socket.write(command.encode() + b"\n")
            socket.waitForBytesWritten(500)
            if command != "status":
                socket.disconnectFromServer()
                return None
            if not socket.waitForReadyRead(500):
                return None
            data = bytes(socket.readAll())
            socket.disconnectFromServer()
            return json.loads(data) if data else None

        def wait_for(predicate):
            end = time.monotonic() + 60
            while time.monotonic() < end:
                value = request("status")
                if value and predicate(value):
                    return value
                time.sleep(0.1)
            raise AssertionError("UI handoff timed out")

        first = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "launch.py"),
                "--no-auto-connect",
                "--expanded",
                "--control",
                str(control),
                "--status",
                str(status),
            ],
            cwd=ROOT,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            before = wait_for(lambda v: v["expanded"])
            print("before", before, flush=True)
            request("reload")
            after = wait_for(lambda v: v["pid"] != before["pid"])
            assert after["expanded"] and after["tab"] == before["tab"]
            request("hide")
            hidden = wait_for(lambda v: v["hidden"])
            request("reload")
            restored = wait_for(lambda v: v["pid"] != hidden["pid"])
            assert restored["hidden"] and not restored["expanded"]
            assert not status.exists(), "UI reload must not launch an offline backend"
            result = {
                "before_pid": before["pid"],
                "after_pid": after["pid"],
                "hidden_pid": restored["pid"],
                "state_restored": True,
                "hidden_restored": True,
                "game_attached": False,
            }
            (ROOT / "generated/overlay-update-check.json").write_text(
                json.dumps(result, indent=2), "utf-8"
            )
            print(json.dumps(result), flush=True)
        finally:
            log = control.with_name("overlay-error.log")
            if log.exists():
                print(log.read_text("utf-8", errors="replace")[-2500:], flush=True)
            request("quit")
            try:
                first.wait(timeout=5)
            except subprocess.TimeoutExpired:
                first.terminate()
                first.wait(timeout=5)
            time.sleep(0.2)


if __name__ == "__main__":
    main()
