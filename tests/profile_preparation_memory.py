"""Measure the production preparation entry in an owned child; never attach games."""

import argparse
import ctypes
from ctypes import wintypes
import functools
import json
import os
from pathlib import Path
import subprocess
import sys
import time


class Counters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "peak_rss",
            "rss",
            "peak_paged",
            "paged",
            "peak_nonpaged",
            "nonpaged",
            "pagefile",
            "peak_pagefile",
            "private",
        )
    ]


def counters(handle):
    value = Counters()
    value.cb = ctypes.sizeof(value)
    read = ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not read(handle, ctypes.byref(value), value.cb):
        raise ctypes.WinError()
    return {key: getattr(value, key) / 1024**2 for key in ("rss", "private", "peak_rss")}


def worker(args):
    sys.path.insert(0, str(args.root.resolve()))
    from sora_bilingual.localization import model_worker, native_catalog, catalog_build
    from sora_bilingual.localization import resources, tables, dynamic_producers

    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = wintypes.HANDLE

    def event(phase):
        print(
            json.dumps(
                {
                    "phase": phase,
                    "pid": os.getpid(),
                    "at": time.time(),
                    "cpu": time.process_time(),
                    **counters(current()),
                }
            ),
            flush=True,
        )

    def wrap(module, name):
        if not hasattr(module, name):
            return
        original = getattr(module, name)

        @functools.wraps(original)
        def measured(*a, **kw):
            event(name + ":begin")
            result = original(*a, **kw)
            event(name + ":end")
            return result

        setattr(module, name, measured)

    for module, name in (
        (catalog_build, "build_catalog"),
        (catalog_build, "build_table_entries"),
        (catalog_build, "build_dynamic_entries"),
        (native_catalog, "build_all"),
        (native_catalog, "_load_model"),
        (model_worker, "prepare_wire"),
    ):
        wrap(module, name)
    event("prepare:begin")
    if args.kind == "dynamic":
        result, audit = dynamic_producers.build_dynamic_entries(args.game, [])
        event("dynamic:end")
        args.cache.mkdir(parents=True, exist_ok=True)
        (args.cache / "dynamic.json").write_text(
            json.dumps({"entries": result, "audit": audit}, ensure_ascii=False), "utf-8"
        )
        return
    config = dict(
        primary=args.locale,
        secondary="ja" if args.locale == "zh-Hans" else "zh-Hans",
        game_language=args.locale,
        scope="all",
        sources=[],
    )
    request = {"game": str(args.game), "config": config}
    if args.kind == "catalog":
        request["catalog_only"] = True
    result = model_worker.prepare_request(request, output=args.cache)
    event("prepare:end")
    print(json.dumps({"result": result}), flush=True)
    time.sleep(2)
    event("idle:end")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kind", choices=("catalog", "model", "dynamic"), default="catalog")
    parser.add_argument("--locale", default="zh-Hans")
    parser.add_argument("--max-private-mib", type=float, default=2048)
    parser.add_argument("--stop-private-mib", type=float, default=4096)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Use a new evidence filename")
    started = time.monotonic()
    samples = []
    stopped = None
    log = args.output.with_suffix(".jsonl")
    with log.open("w", encoding="utf-8") as stream:
        child = subprocess.Popen(
            [sys.executable, "-X", "utf8", __file__, *sys.argv[1:], "--worker"],
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        open_process = ctypes.windll.kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        handle = open_process(0x1000 | 0x10, False, child.pid)
        target_pid = child.pid
        try:
            while child.poll() is None:
                # A Windows venv launcher starts the actual interpreter as a
                # descendant. Follow the PID emitted by our own worker, not
                # just the small launcher returned by Popen.
                if target_pid == child.pid:
                    for line in log.read_text("utf-8").splitlines():
                        try:
                            target_pid = json.loads(line).get("pid", child.pid)
                        except ValueError:
                            continue
                        if target_pid != child.pid:
                            ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                            ctypes.windll.kernel32.CloseHandle(handle)
                            handle = open_process(0x1000 | 0x10 | 1, False, target_pid)
                            break
                row = {"seconds": time.monotonic() - started, **counters(handle)}
                samples.append(row)
                if row["private"] > args.stop_private_mib or row["seconds"] > 900:
                    ctypes.windll.kernel32.TerminateProcess.argtypes = [
                        wintypes.HANDLE,
                        wintypes.UINT,
                    ]
                    ctypes.windll.kernel32.TerminateProcess(handle, 1)
                    child.terminate()  # Only our preparation child, never the game or user's tool.
                    stopped = "Owned preparation exceeded diagnostic safety bound"
                    break
                time.sleep(0.1)
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait()
            ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            ctypes.windll.kernel32.CloseHandle(handle)
    events = []
    for line in log.read_text("utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    peak = max(row["private"] for row in samples)
    peak_rss = max(
        [row["peak_rss"] for row in samples] + [event.get("peak_rss", 0) for event in events]
    )
    report = dict(
        root=str(args.root),
        cache=str(args.cache),
        kind=args.kind,
        stopped=stopped,
        seconds=time.monotonic() - started,
        exit_code=child.returncode,
        peak_private_mib=peak,
        limit_private_mib=args.max_private_mib,
        peak_working_set_mib=peak_rss,
        passed=child.returncode == 0 and peak <= args.max_private_mib,
        game_started=False,
        game_attached=False,
        events=events,
        samples=samples,
    )
    args.output.write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("samples", "events")}))
    print(json.dumps(events))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
