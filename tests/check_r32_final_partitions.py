"""Run scoped original regression tests; production and expectations are read only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
NODE_TESTS = [
    "tests/test_native_agent.js",
    "tests/test_runtime_text.js",
    "tests/test_runtime_paragraph.js",
    "tests/test_item_help_headers.js",
]
PY_TESTS = [
    "tests.test_effect_units",
    "tests.test_itemhelp_composition",
    "tests.test_itemhelp_aggregates",
]
FILES = [
    *NODE_TESTS,
    *[name.replace(".", "/") + ".py" for name in PY_TESTS],
    "sora_bilingual/game/scripts/runtime_text.js",
    "sora_bilingual/game/scripts/native_agent.js",
    "sora_bilingual/game/scripts/runtime_paragraph.js",
    "sora_bilingual/localization/menu_text.py",
    "sora_bilingual/localization/item_help_headers.py",
    "sora_bilingual/localization/item_help_composition.py",
    "generated/r26-tools-header-regression.json",
]


def hashes():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in FILES
        if (ROOT / name).is_file()
    }


def main():
    before = hashes()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    jobs = [
        (
            "node",
            [
                shutil.which("node"),
                "--require",
                "./tests/check_r32_final_partitions_output.js",
                "--test",
                "--test-reporter=tap",
                *NODE_TESTS,
            ],
        ),
        ("python", [sys.executable, "-X", "utf8", "-m", "unittest", *PY_TESTS, "-v"]),
    ]
    receipt = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_hashes_before": before,
        "production_modified_by_checker": False,
        "expectations_modified": False,
        "game_attached": False,
        "production_model_compiled": False,
        "build_run": False,
        "node_receipt_redirect": {
            "from": "generated/r26-tools-header-regression.json",
            "to": "generated/r32-final-partitions-itemhelp-header.json",
        },
        "checks": [],
    }
    for label, command in jobs:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log = ROOT / "generated" / f"r32-final-partitions-{label}.log"
        log.write_text(result.stdout, encoding="utf-8")
        counts = {}
        if label == "node":
            for key in ("tests", "suites", "pass", "fail", "cancelled", "skipped", "todo"):
                found = re.search(rf"^# {key} (\d+)$", result.stdout, re.M)
                counts[key] = int(found.group(1)) if found else None
        else:
            found = re.search(r"Ran (\d+) tests? in", result.stdout)
            counts["tests"] = int(found.group(1)) if found else None
            for key in ("failures", "errors", "skipped"):
                found = re.search(rf"{key}=(\d+)", result.stdout)
                counts[key] = int(found.group(1)) if found else 0
            counts["success"] = (
                counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
                if counts["tests"] is not None
                else None
            )
        receipt["checks"].append(
            {
                "label": label,
                "command": command,
                "cwd": str(ROOT),
                "exit_code": result.returncode,
                "counts": counts,
                "log": str(log),
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                "failure_classification": "none"
                if result.returncode == 0
                else "unclassified; raw failure preserved",
            }
        )
        print(json.dumps(receipt["checks"][-1], ensure_ascii=False), flush=True)
    receipt["source_hashes_after"] = hashes()
    receipt["unchanged_inputs_and_sources"] = before == receipt["source_hashes_after"]
    output = ROOT / "generated/r32-final-partitions-receipt.json"
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(output),
                "unchanged_inputs_and_sources": receipt["unchanged_inputs_and_sources"],
            }
        ),
        flush=True,
    )
    return (
        0
        if receipt["unchanged_inputs_and_sources"]
        and all(row["exit_code"] == 0 for row in receipt["checks"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
