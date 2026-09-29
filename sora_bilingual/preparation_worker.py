"""Process entry point for cancellable preparation. Never attaches a game."""

import argparse
import json
from pathlib import Path

from sora_bilingual.config.native_config import write_config
from sora_bilingual.platform.worker_process import own_worker_job


if __name__ == "__main__":
    worker_job = own_worker_job()
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text("utf-8"))
    if request.get("fonts_only"):
        from sora_bilingual.fonts.font_delivery import prepare

        result = {"path": str(prepare(Path(request["game"])))}
    else:
        from sora_bilingual.localization.model_worker import prepare_request

        result = prepare_request(request)
    write_config(result, args.result)
