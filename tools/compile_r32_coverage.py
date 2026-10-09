"""Compile current complete models for four normal source pairs and manual EN."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.native_catalog import fingerprint
from sora_bilingual.localization.model_worker import prepare_request


def main():
    prefix = "r32-coverage"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / f"generated/{prefix}-production")
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous = ROOT / "generated/r25-production"
    game = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    freeze = json.loads((ROOT / f"generated/{prefix}-source-freeze.json").read_text("utf8"))
    sha = lambda data: hashlib.sha256(data).hexdigest()

    def verify():
        for name, digest in freeze["files"].items():
            assert sha((ROOT / name).read_bytes()) == digest, name

    verify()
    stamp = fingerprint(game)
    old = json.loads((previous / "catalog-signature.json").read_text("utf8"))
    assert old == json.loads(
        json.dumps({"resources": stamp["resources"], "code": stamp["catalog_code"]})
    )
    for name in ("catalog.json", "catalog-signature.json"):
        shutil.copy2(previous / name, output / name)
    if not (output / "language-facts").exists():
        shutil.copytree(previous / "language-facts", output / "language-facts")
    results = []
    for label, source, primary, secondary, experimental in (
        ("en", "en", "en", "zh-Hans", False),
        ("ja", "ja", "ja", "zh-Hans", False),
        ("zh-Hans", "zh-Hans", "zh-Hans", "ja", False),
        ("zh-Hant", "zh-Hant", "zh-Hant", "ja", False),
        ("en-manual", "en", "ja", "zh-Hans", True),
    ):
        verify()
        config = {
            "primary": primary,
            "secondary": secondary,
            "game_language": source,
            "experimental_primary": experimental,
            "scope": "all",
            "sources": [],
        }
        start = time.perf_counter()
        print(
            json.dumps(
                {
                    "phase": "compile_current_complete_model",
                    "label": label,
                    "config": config,
                    "source_snapshot": freeze["snapshot_sha256"],
                }
            ),
            flush=True,
        )
        result = prepare_request({"game": str(game), "config": config}, output=output)
        model = Path(result["path"])
        wire = model.with_suffix(".wire.bin")
        verify()
        receipt = {
            "label": label,
            "seconds": time.perf_counter() - start,
            "config": config,
            "signature": stamp,
            "source_snapshot_sha256": freeze["snapshot_sha256"],
            "model_path": str(model),
            "wire_path": str(wire),
            "model_sha256": sha(model.read_bytes()),
            "wire_sha256": sha(wire.read_bytes()),
            "result": result,
            "reused_compatible_raw_catalog": True,
            "old_model_reused": False,
            "game_attached": False,
        }
        (ROOT / f"generated/{prefix}-{label}-production-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), "utf8"
        )
        results.append(receipt)
        print(json.dumps({k: receipt[k] for k in ("label", "seconds", "wire_sha256")}), flush=True)
    (ROOT / f"generated/{prefix}-matrix-receipt.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), "utf8"
    )
    shutil.copy2(
        ROOT / f"generated/{prefix}-en-production-receipt.json",
        ROOT / f"generated/{prefix}-production-receipt.json",
    )


if __name__ == "__main__":
    main()
