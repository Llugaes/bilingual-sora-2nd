"""Fresh audit-only source-language models; never mutate the sealed candidate."""

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


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    audit = ROOT / "generated/r27-association-audit"
    build = audit / "builds/build001"
    if build.exists():
        raise ValueError("build ID already exists; retain it and use a new build ID")
    build.mkdir(parents=True)
    seed = ROOT / "generated/r26-p0-local-production"
    freeze = json.loads((ROOT / "generated/r26-p0-local-source-freeze.json").read_text("utf8"))
    previous = json.loads(
        (ROOT / "generated/r26-p0-local-production-receipt.json").read_text("utf8")
    )
    candidate = ROOT / "dist/comprehensive-1.0.0-dev5-r26-p0-local3/DEV"
    cache = json.loads((candidate / "candidate-cache.json").read_text("utf8"))
    game = Path(r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")

    def verify():
        for name, sha in freeze["files"].items():
            assert digest(ROOT / name) == sha, name

    verify()
    stamp = fingerprint(game)
    assert json.loads(json.dumps(stamp)) == previous["signature"]
    assert json.loads((seed / "catalog-signature.json").read_text("utf8")) == json.loads(
        json.dumps({"resources": stamp["resources"], "code": stamp["catalog_code"]})
    )
    receipts = [
        {
            "source_language": "en",
            "config": cache["config"],
            "config_sha256": hashlib.sha256(
                json.dumps(cache["config"], sort_keys=True).encode()
            ).hexdigest(),
            "source_snapshot_sha256": freeze["snapshot_sha256"],
            "wire_path": str(candidate / "generated" / cache["wire_name"]),
            "model_path": str(candidate / "generated" / cache["model_name"]),
            "wire_sha256": cache["wire_sha256"],
            "model_sha256": digest(candidate / "generated" / cache["model_name"]),
            "reused_sealed_en_wire": True,
        }
    ]
    index = build / "receipts.json"
    index.write_text(json.dumps(receipts, indent=2), "utf8")
    for language in ("ja", "zh-Hans", "zh-Hant", "ko", "fr", "de", "es"):
        output = build / language
        output.mkdir()
        for name in ("catalog.json", "catalog-signature.json"):
            shutil.copy2(seed / name, output / name)
        shutil.copytree(seed / "language-facts", output / "language-facts")
        config = {
            "primary": "ja",
            "secondary": "zh-Hans",
            "game_language": language,
            "scope": "all",
            "sources": [],
        }
        print(
            json.dumps({"phase": "building", "build_id": "build001", "source_language": language}),
            flush=True,
        )
        start = time.perf_counter()
        result = prepare_request({"game": str(game), "config": config}, output=output)
        model = Path(result["path"])
        wire = model.with_suffix(".wire.bin")
        verify()
        record = {
            "source_language": language,
            "config": config,
            "config_sha256": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()
            ).hexdigest(),
            "source_snapshot_sha256": freeze["snapshot_sha256"],
            "model_path": str(model),
            "model_sha256": digest(model),
            "wire_path": str(wire),
            "wire_sha256": digest(wire),
            "signature": stamp,
            "seconds": time.perf_counter() - start,
            "reused_compatible_raw_catalog": True,
            "old_model_reused": False,
            "game_attached": False,
        }
        (output / "build-receipt.json").write_text(json.dumps(record, indent=2), "utf8")
        receipts.append(record)
        index.write_text(json.dumps(receipts, indent=2), "utf8")
        print(
            json.dumps(
                {
                    "phase": "complete",
                    "source_language": language,
                    "seconds": record["seconds"],
                    "wire_sha256": record["wire_sha256"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
