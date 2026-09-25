import os

"""Build every ordered language pair from the full catalog, using all sources.

The full 8x8x8 render matrix is checked separately. Here the expensive native
identity compiler is exercised for all 64 pairs, rotating the source locale.
Models live in a temporary directory and are deleted as each case completes.
"""
import gc
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.config.native_config import read_config

GAME = Path(os.environ["SORA_GAME_DIR"])


def main():
    entries, signature = load_entries(GAME)
    report = {
        "game_started": False,
        "game_attached": False,
        "code_sha256": hashlib.sha256(
            b"".join(
                (ROOT / f).read_bytes()
                for f in (
                    "sora_bilingual/localization/resources.py",
                    "sora_bilingual/localization/tables.py",
                    "sora_bilingual/localization/menu_tables.py",
                    "sora_bilingual/localization/menu_text.py",
                    "sora_bilingual/localization/runtime_identity.py",
                    "sora_bilingual/localization/native_catalog.py",
                )
            )
        ).hexdigest(),
        "models": [],
    }
    with tempfile.TemporaryDirectory(prefix="sora-model-matrix-") as tmp:
        for i, primary in enumerate(LANGUAGES):
            for j, secondary in enumerate(LANGUAGES):
                source = LANGUAGES[(i + j) % len(LANGUAGES)]
                config = {
                    **read_config(),
                    "primary": primary,
                    "secondary": secondary,
                    "game_language": source,
                    "scope": "all",
                }
                start = time.perf_counter()
                try:
                    model = load_model(entries, signature, config, tmp, game=GAME)
                    assert model["pairs"] and model["plain_pairs"]
                    assert all(
                        s.strip() and all(t.strip() for t in pair)
                        for s, pair in model["pairs"].items()
                    )
                    assert model["same_language"] == (primary == secondary)
                    result = {
                        "primary": primary,
                        "secondary": secondary,
                        "source": source,
                        "ok": True,
                        "pairs": len(model["pairs"]),
                        "seconds": round(time.perf_counter() - start, 3),
                    }
                    result["quarantined_functions"] = model["script_identities"]["stats"].get(
                        "conflicting_function_identities", 0
                    )
                    del model
                except Exception as exc:
                    result = {
                        "primary": primary,
                        "secondary": secondary,
                        "source": source,
                        "ok": False,
                        "error": repr(exc),
                    }
                finally:
                    model_path(signature, config, tmp).unlink(missing_ok=True)
                    gc.collect()
                report["models"].append(result)
                print(json.dumps(result), flush=True)
                (ROOT / "generated/all-models-check.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
                )
    if not all(v["ok"] for v in report["models"]):
        raise AssertionError("model compilation failures; see report")


if __name__ == "__main__":
    main()
