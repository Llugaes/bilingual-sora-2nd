"""Offline cold/warm startup benchmark; never starts or attaches to a game."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from sora_bilingual.config.native_config import read_config
from sora_bilingual.game.native_runtime import native_report
from sora_bilingual.localization.native_catalog import load_entries, load_model, ready_model


def check(game, baseline, output, config_path, allow_additions=False):
    if output.exists():
        raise ValueError("Use a new output folder for a real cold-cache measurement")
    config = read_config(config_path)
    start = time.perf_counter()
    entries, signature = load_entries(game, output)
    catalog_seconds = time.perf_counter() - start
    with (output / "catalog.json").open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    with baseline.open("rb") as source:
        expected = hashlib.file_digest(source, "sha256").hexdigest()
    if allow_additions:

        def digest(entry):
            return hashlib.sha256(
                json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
            ).digest()

        current = {digest(e) for e in entries}
        previous = json.loads(baseline.read_text("utf-8"))["entries"]
        assert all(digest(e) in current for e in previous), (
            "Existing aligned records were changed or lost"
        )
        added = len(entries) - len(previous)
        del current, previous
    else:
        assert actual == expected, "Optimized catalog differs from the baseline"
        added = 0
    start = time.perf_counter()
    model = load_model(entries, signature, config, output, game=game)
    model_seconds = time.perf_counter() - start
    del entries, model
    start = time.perf_counter()
    model, _, entries = ready_model(game, config, output)
    warm_seconds = time.perf_counter() - start
    assert entries is None, "Warm startup must not read/rebuild the catalog"
    start = time.perf_counter()
    native_report(game / "sora_2nd.exe")
    verify_seconds = time.perf_counter() - start
    result = {
        "catalog_seconds": round(catalog_seconds, 3),
        "model_seconds": round(model_seconds, 3),
        "warm_model_seconds": round(warm_seconds, 3),
        "exe_verification_seconds": round(verify_seconds, 3),
        "catalog_sha256": actual,
        "catalog_matches_baseline": actual == expected,
        "existing_records_preserved": True,
        "added_records": added,
        "pairs": len(model["pairs"]),
        "game_started": False,
        "game_attached": False,
    }
    (output / "performance.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "baseline", "output", "config"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--allow-additions", action="store_true")
    args = parser.parse_args()
    check(args.game, args.baseline, args.output, args.config, args.allow_additions)
