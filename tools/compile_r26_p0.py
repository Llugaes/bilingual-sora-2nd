"""Compile a fresh P0 product wire from signature-compatible raw resources."""

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="r26-p0-local")
    args = parser.parse_args()
    output = ROOT / ("generated/" + args.prefix + "-production")
    output.mkdir(exist_ok=True)
    previous = ROOT / "generated/r25-production"
    game = Path(r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
    frozen = json.loads(
        (ROOT / ("generated/" + args.prefix + "-source-freeze.json")).read_text("utf8")
    )

    def verify_source():
        for name, digest in frozen["files"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name

    verify_source()
    stamp = fingerprint(game)
    raw_signature = json.loads((previous / "catalog-signature.json").read_text("utf8"))
    assert raw_signature == json.loads(
        json.dumps({"resources": stamp["resources"], "code": stamp["catalog_code"]})
    ), "raw catalogue provenance changed"
    for name in ("catalog.json", "catalog-signature.json"):
        shutil.copy2(previous / name, output / name)
    if not (output / "language-facts").exists():
        shutil.copytree(previous / "language-facts", output / "language-facts")
    config = {
        "primary": "ja",
        "secondary": "zh-Hans",
        "game_language": "en",
        "scope": "all",
        "sources": [],
    }
    start = time.perf_counter()
    print(
        json.dumps(
            {
                "phase": "fresh complete product model and wire",
                "source_snapshot": frozen["snapshot_sha256"],
                "old_model_reused": False,
            }
        ),
        flush=True,
    )
    result = prepare_request({"game": str(game), "config": config}, output=output)
    model = Path(result["path"])
    wire = model.with_suffix(".wire.bin")
    verify_source()
    receipt = {
        "seconds": time.perf_counter() - start,
        "config": config,
        "signature": stamp,
        "source_snapshot_sha256": frozen["snapshot_sha256"],
        "model_path": str(model),
        "wire_path": str(wire),
        "wire_sha256": hashlib.sha256(wire.read_bytes()).hexdigest(),
        "result": result,
        "model_preparation": json.loads((output / "model-preparation.json").read_text("utf8")),
        "reused_compatible_raw_catalog": True,
        "old_model_reused": False,
        "game_attached": False,
    }
    (ROOT / ("generated/" + args.prefix + "-production-receipt.json")).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), "utf8"
    )
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in ("seconds", "source_snapshot_sha256", "wire_sha256", "model_path")
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
