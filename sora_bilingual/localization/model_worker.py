"""Fresh-code model preparation for a resident backend. Never attaches games."""

import argparse
import json
import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path
from sora_bilingual.localization.native_catalog import load_entries, ready_model, model_path
from sora_bilingual.localization.model_wire import prepare_wire
from sora_bilingual.config.native_config import normalize_config, write_config
from sora_bilingual.paths import STATE


@contextmanager
def preparation_lock(output):
    """UI prewarm and backend share the catalog; recheck caches after this lock.

    OS ownership releases on process exit, including a killed compiler. Never
    use the game/backend lock: preparing resources must not attach a process.
    """
    output.mkdir(parents=True, exist_ok=True)
    with (output / "model-preparation.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0, 2)
            if not lock.tell():
                lock.write(b"\0")
                lock.flush()
            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def prepare_request(request, output=STATE):
    output = Path(output)
    with preparation_lock(output):
        game = Path(request["game"])
        if request.get("catalog_only"):
            entries, _ = load_entries(game, output)
            return {"stage": "catalog", "records": len(entries)}
        config = normalize_config(request["config"])
        model, signature, _ = ready_model(game, config, output)
        path = model_path(signature, config, output)
        prepare_wire(path, model)
        return {
            "path": str(path),
            "coverage": model.get("coverage", {}),
            "pair_count": len(model.get("pairs", {})),
        }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--result", type=Path, required=True)
    args = p.parse_args()
    request = json.loads(args.request.read_text("utf-8"))
    write_config(prepare_request(request), args.result)
