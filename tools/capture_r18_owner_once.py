"""Serial product-quit / existing-resident snapshot / unchanged product reopen.

No Frida attach/create_script, no reserve/publish, no model/config changes.
Uses the r18 product modules so its resident revision is unchanged.
"""

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

R18 = Path(__file__).resolve().parents[1] / "dist/comprehensive-1.0.0-dev5-r18/DEV"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "generated"
REVISION = "789ae56bd79a9cff6e73ae668dea6b8e14f458f980e1b021dc1505d79ebbe0c2"
sys.path.insert(0, str(R18))
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalSocket
from sora_bilingual.game.agent_control import reconnect
from sora_bilingual.game.tool_shutdown import backend_alive
from sora_bilingual.config.native_config import BackendLock
from sora_bilingual.platform.win32 import process_identity


def ui_command(command):
    control = R18 / "generated/native-control.json"
    name = "SoraBilingual-" + hashlib.sha256(str(control.resolve()).encode()).hexdigest()[:16]
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(2000):
        raise RuntimeError("Product UI command unavailable")
    socket.write((command + "\n").encode())
    if not socket.waitForBytesWritten(2000):
        raise RuntimeError("Product UI command not delivered")
    value = None
    if command == "status":
        if not socket.waitForReadyRead(2000):
            raise RuntimeError("Product UI status unavailable")
        value = json.loads(bytes(socket.readLine()).decode())
    socket.disconnectFromServer()
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument(
        "--output", type=Path, help="New evidence file; an existing file is never overwritten"
    )
    args = parser.parse_args()
    output = args.output or OUTPUT_DIR / (
        "r19-existing-owner-snapshot-"
        + datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + ".json"
    )
    output = output.resolve()
    if output.parent != OUTPUT_DIR.resolve() or output.exists() or not output.parent.is_dir():
        raise RuntimeError("Evidence output must be a new file in an existing directory")
    app = QCoreApplication([])
    state = R18 / "generated"
    record = json.loads((state / "native-agent.json").read_text("utf-8"))
    if record.get("revision") != REVISION or record.get("pid") != 31480:
        raise RuntimeError("Current resident identity differs; stopping before UI change")
    identity = process_identity(31480)
    if record.get("created") != identity:
        raise RuntimeError("Game lifetime changed; stopping before UI change")
    before = ui_command("status")
    config_before = json.loads((state / "native-control.json").read_text("utf-8"))
    owner_before = json.loads((state / "native-owner.json").read_text("utf-8"))
    result = {
        "resident_revision": REVISION,
        "game_pid": 31480,
        "game_created": identity,
        "captured_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "ui_before": before,
        "owner_before": owner_before,
        "config_before": {
            k: config_before.get(k)
            for k in ("primary", "secondary", "interaction", "diagnostics", "enabled")
        },
        "frida_attach": False,
        "resident_replaced": False,
        "model_loaded": False,
        "game_restarted": False,
        "single_owner_serial": True,
    }
    client = None
    quit_sent = False
    try:
        ui_command("quit")
        quit_sent = True
        deadline = time.monotonic() + 25
        while backend_alive(state):
            if time.monotonic() >= deadline:
                raise RuntimeError("Existing backend did not finish normal shutdown")
            time.sleep(0.1)
        # Hold the same backend mutex throughout the temporary ownership read.
        lock = BackendLock(state / "native-backend.lock")
        try:
            client = reconnect(31480, record["exe"], path=state / "native-agent.json")
            if client is None or client.revision != REVISION:
                raise RuntimeError("Existing resident reconnect unavailable; no install fallback")
            status = client.status()
            if status.get("enabled"):
                raise RuntimeError("Resident is enabled after product shutdown")
            rows = client.snapshot(False)
            pattern = re.compile(
                r"Physical|Debilitate|Impede|Regen|Back Attack|Side Attack|Burn|Confuse|Deathblow|Mute|Freeze|Orbments|Tactical Bonus|Stealing AT|Overdrive|Changing Battle|Book List|Volume 1|recipes|Crystals|terminal"
            )
            selected = [row for row in rows if pattern.search(row.get("original", ""))]
            result.update(
                status=status,
                label_count=len(rows),
                selected_count=len(selected),
                rows=selected,
                all_rows=rows,
                pointer_identity_available=bool(rows) and all("pointer" in row for row in rows),
                path_identity_note="snapshot(False) has no pointer when resident diagnostics is false; external node paths must be evidenced separately, never guessed",
            )
            with output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            if client is not None:
                client.close()
                client = None
            lock.close()
    finally:
        if client is not None:
            client.close()
        if quit_sent:
            subprocess.Popen(
                [str(R18 / "BilingualSora2nd.exe")],
                cwd=R18,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
    if process_identity(31480) != identity:
        raise RuntimeError("Game identity changed unexpectedly")
    print(
        json.dumps(
            {
                "output": str(output),
                **{
                    key: result[key]
                    for key in (
                        "resident_revision",
                        "game_pid",
                        "label_count",
                        "selected_count",
                        "single_owner_serial",
                    )
                },
            }
        )
    )


if __name__ == "__main__":
    main()
