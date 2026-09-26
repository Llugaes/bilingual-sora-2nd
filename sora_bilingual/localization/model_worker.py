"""Fresh-code model preparation for a resident backend. Never attaches games."""

import argparse
import json
from pathlib import Path
from sora_bilingual.localization.native_catalog import ready_model, model_path
from sora_bilingual.config.native_config import normalize_config, write_config


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--result", type=Path, required=True)
    args = p.parse_args()
    request = json.loads(args.request.read_text("utf-8"))
    config = normalize_config(request["config"])
    model, signature, _ = ready_model(Path(request["game"]), config)
    path = model_path(signature, config)
    from sora_bilingual.localization.model_wire import prepare_wire

    prepare_wire(path, model)
    write_config({"path": str(path), "coverage": model.get("coverage", {})}, args.result)
