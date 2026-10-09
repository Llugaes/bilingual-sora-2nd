"""Offline production compilation; reuse only signature-compatible raw catalogue."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from sora_bilingual.localization.native_catalog import (
    fingerprint,
    load_entries,
    load_model,
    model_path,
)
from sora_bilingual.localization.model_wire import prepare_wire

source = root / "dist/comprehensive-1.0.0-dev5-r18/DEV/generated"
game = Path(r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter")
output = root / "generated/r19-production"
output.mkdir(parents=True, exist_ok=True)
start = time.perf_counter()
stamp = fingerprint(game)
expected = json.dumps(
    {"resources": stamp["resources"], "code": stamp["catalog_code"]}, sort_keys=True
)
raw_stamp = (source / "catalog-signature.json").read_text("utf-8")
if raw_stamp != expected:
    raise RuntimeError(
        "r18 raw catalogue signature is not compatible with current parser/resources"
    )
if not (output / "catalog.json").exists():
    shutil.copyfile(source / "catalog.json", output / "catalog.json")
    (output / "catalog-signature.json").write_text(raw_stamp, "utf-8")
snapshot = json.loads((root / "generated/r19-existing-owner-snapshot.json").read_text("utf-8"))
source_language = snapshot["status"]["inputIdentityDiagnostics"]["source_language"]
config = {
    "primary": snapshot["config_before"]["primary"],
    "secondary": snapshot["config_before"]["secondary"],
    "game_language": source_language,
    "scope": "all",
    "sources": [],
}
print(json.dumps({"stage": "raw_catalogue_verified", "config": config}), flush=True)
entries, signature = load_entries(game, output)
print(json.dumps({"stage": "production_model", "records": len(entries)}), flush=True)
model = load_model(entries, signature, config, output, game=game)
path = model_path(signature, config, output)
print(json.dumps({"stage": "indexed_wire", "model": path.name}), flush=True)
wire = prepare_wire(path, model)
receipt = {
    "compiled_at": time.time(),
    "seconds": time.perf_counter() - start,
    "config": config,
    "signature": json.loads(signature),
    "raw_catalogue_reused": True,
    "model_reused_from_r18": False,
    "model_path": str(path),
    "wire_path": str(wire),
    "wire_bytes": wire.stat().st_size,
    "wire_sha256": hashlib.sha256(wire.read_bytes()).hexdigest(),
    "header_formats": len(model["skill_help_headers"]["formats"]),
    "effect_units": len(model["details"]["detail_effect_units"]),
    "atomic_units": sum(bool(r.get("atomic")) for r in model["details"]["detail_effect_units"]),
    "typed_parameter_units": sum(
        bool(r.get("parameter_kinds")) for r in model["details"]["detail_effect_units"]
    ),
    "model_preparation": json.loads((output / "model-preparation.json").read_text("utf-8")),
    "deployed": False,
    "live_verified": False,
}
(root / "generated/r19-production-receipt.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2), "utf-8"
)
print(
    json.dumps(
        {
            k: receipt[k]
            for k in (
                "seconds",
                "wire_bytes",
                "wire_sha256",
                "header_formats",
                "effect_units",
                "atomic_units",
                "typed_parameter_units",
            )
        }
    ),
    flush=True,
)
