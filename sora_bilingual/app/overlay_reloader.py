"""Wait for the old UI to release its singleton, then restore it. No game access."""

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--no-auto-connect", action="store_true")
    args = p.parse_args()
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.OpenProcess(0x100000, False, args.pid)
    if handle:
        try:
            if k.WaitForSingleObject(handle, 60000) != 0:
                return 1
        finally:
            k.CloseHandle(handle)
    from sora_bilingual.paths import ROOT as root

    command = [
        sys.executable,
        str(root / "launch.py"),
        "--control",
        args.control,
        "--status",
        args.status,
        "--restore",
    ]
    if args.no_auto_connect:
        command.append("--no-auto-connect")
    with Path(args.control).with_name("overlay-error.log").open("ab") as log:
        subprocess.Popen(
            command, cwd=root, creationflags=subprocess.CREATE_NO_WINDOW, stdout=log, stderr=log
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
