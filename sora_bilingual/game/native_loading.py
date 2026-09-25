"""Prepare locale data off the input loop; keep honest connection heartbeats."""

from copy import deepcopy
from queue import Queue, Empty
import threading
import time


def prepare_fresh(game, config):
    """Isolate compiler updates from already-imported resident Python modules."""
    import json, subprocess, sys, tempfile
    from pathlib import Path
    from sora_bilingual.localization.cache_io import read_model
    from sora_bilingual.paths import ROOT as root

    with tempfile.TemporaryDirectory(prefix="sora-prepare-") as tmp:
        request = Path(tmp) / "request.json"
        result = Path(tmp) / "result.json"
        request.write_text(json.dumps({"game": str(game), "config": config}), "utf-8")
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "sora_bilingual.localization.model_worker",
                "--request",
                str(request),
                "--result",
                str(result),
            ],
            cwd=root,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if process.returncode:
            raise RuntimeError(
                process.stderr.decode("utf-8", errors="replace")[-1500:] or "索引准备进程失败"
            )
        model = read_model(json.loads(result.read_text("utf-8"))["path"])
        if model is None:
            raise ValueError("准备后的模型校验失败")
        return model


class ModelPreparation:
    """One build at a time. Superseded results never reach the live renderer."""

    def __init__(self, loader, identity):
        self.loader = loader
        self.identity = identity
        self.desired = None
        self.active = False
        self.results = Queue()
        self.generation = 0

    def request(self, config):
        self.generation += 1
        self.desired = deepcopy(config)
        self._start()

    def _start(self):
        if self.active or self.desired is None:
            return
        config = deepcopy(self.desired)
        self.active = True
        generation = self.generation

        def build():
            try:
                self.results.put((generation, config, self.loader(config), None))
            except Exception as exc:
                self.results.put((generation, config, None, exc))

        threading.Thread(target=build, name="locale-prepare", daemon=True).start()

    def poll(self):
        try:
            generation, config, result, error = self.results.get_nowait()
        except Empty:
            return None
        self.active = False
        if generation != self.generation:
            self._start()
            return None
        self.desired = None
        return config, result, error


class ConnectionHeartbeat:
    """No native calls here. Publish only last acknowledged state plus phase.

    In particular, model preparation/serialization is not a lost connection and
    the requested languages must not be shown as active before native.load ACK.
    """

    def __init__(self, writer, live_path, status_path, pid, interval=0.25):
        self.writer = writer
        self.paths = (live_path, status_path)
        self.interval = interval
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.values = [
            {"running": True, "pid": pid, "enabled": False},
            {"running": True, "pid": pid},
        ]
        self.phase = "connecting"
        self.reload_error = None
        self.thread = threading.Thread(target=self._run, name="connection-heartbeat", daemon=True)
        self.thread.start()

    def update(self, index, value):
        with self.lock:
            self.values[index] = dict(value)
        self.wake.set()

    def loading(self, phase, error=None):
        with self.lock:
            self.phase = phase
            self.reload_error = error
        self.wake.set()

    def _run(self):
        while not self.stop.is_set():
            with self.lock:
                values = [
                    dict(
                        v, updated_at=time.time(), phase=self.phase, reload_error=self.reload_error
                    )
                    for v in self.values
                ]
            for path, value in zip(self.paths, values):
                self.writer(value, path)
            self.wake.wait(self.interval)
            self.wake.clear()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join()
