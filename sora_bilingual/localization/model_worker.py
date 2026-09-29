"""Fresh-code model preparation for a resident backend. Never attaches games."""

import argparse
import json
from pathlib import Path
from sora_bilingual.localization.native_catalog import load_entries, ready_model, model_path
from sora_bilingual.localization.model_wire import prepare_wire
from sora_bilingual.config.native_config import normalize_config, write_config
from sora_bilingual.platform.file_lock import preparation_lock
from sora_bilingual.paths import STATE


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
