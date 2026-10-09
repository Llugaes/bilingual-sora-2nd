"""Execute existing final V8/callback checks, preserving previous canonical receipts."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from check_r32_final_replays import (
    ROOT,
    LABELS,
    DEFAULT_FREEZE,
    digest,
    frozen_contract,
    preserve_file,
)

FRIDA_PYTHON = Path(sys.executable)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("v8", "callbacks"))
    parser.add_argument("--label", choices=LABELS)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--run-tag", default="local3")
    parser.add_argument("--recipes", type=Path)
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "generated/r32-coverage-local2-evidence"
    )
    args = parser.parse_args()
    labels = (args.label,) if args.label else LABELS
    freeze, snapshot, renderer_sha = frozen_contract(args.freeze)
    execution_path = ROOT / f"generated/r32-{args.run_tag}-{args.stage}-execution.json"
    prior = json.loads(execution_path.read_text("utf8")) if execution_path.exists() else None
    assert not prior or prior["source_snapshot_sha256"] == snapshot, (
        "output namespace belongs to another freeze"
    )
    records = prior["records"] if prior else []
    for label in labels:
        receipt = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
        replay = ROOT / f"generated/r32-coverage-{label}-product-replay.json"
        source_receipt = json.loads(receipt.read_text("utf8"))
        assert source_receipt["source_snapshot_sha256"] == snapshot
        assert digest(ROOT / "sora_bilingual/game/scripts/runtime_text.js") == renderer_sha
        script_names = (
            "runtime_text.js",
            "native_transport.js",
            "native_agent.js",
            "runtime_paragraph.js",
            "runtime_identity.js",
        )
        source_files_before = {
            "sora_bilingual/game/scripts/" + name: digest(
                ROOT / "sora_bilingual/game/scripts" / name
            )
            for name in script_names
        }
        assert all(value == freeze["files"][name] for name, value in source_files_before.items())
        if args.stage == "v8":
            destination = ROOT / f"generated/r32-coverage-{label}-production-frida.json"
            command = [
                str(FRIDA_PYTHON),
                "-X",
                "utf8",
                "tests/check_r26_p0_v8.py",
                "--receipt",
                str(receipt),
                "--replay",
                str(replay),
                "--output",
                str(destination),
            ]
        else:
            destination = ROOT / f"generated/r32-callbacks-{label}.json"
            command = [
                shutil.which("node"),
                "--expose-gc",
                "tests/check_r32_callbacks.js",
                ".",
                label,
                source_receipt["wire_path"],
            ]
            if args.recipes:
                command.append(str(args.recipes.resolve()))
        previous = digest(destination) if destination.exists() else None
        backup = preserve_file(destination, args.evidence_dir)
        result = subprocess.run(
            command,
            cwd=ROOT,
            encoding="utf8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log = ROOT / f"generated/r32-{args.run_tag}-{args.stage}-{label}.log"
        preserve_file(log, args.evidence_dir)
        log.write_text(result.stdout, encoding="utf8")
        output = json.loads(destination.read_text("utf8")) if result.returncode == 0 else None
        unchanged = digest(ROOT / "sora_bilingual/game/scripts/runtime_text.js") == renderer_sha
        source_files_after = {name: digest(ROOT / name) for name in source_files_before}
        unchanged = unchanged and source_files_before == source_files_after
        valid = result.returncode == 0 and unchanged
        if valid:
            assert output["wire_sha256"] == source_receipt["wire_sha256"]
            assert output["source_snapshot_sha256"] == snapshot
            if args.stage == "v8":
                assert (
                    output["runtime_text_sha256"] == renderer_sha
                    and output["complete_mode_plans"] == 2097
                )
            else:
                assert output["production_scripts"]["runtime_text.js"] == renderer_sha
                assert all(
                    value == source_files_before["sora_bilingual/game/scripts/" + name]
                    for name, value in output["production_scripts"].items()
                )
                assert output["input_count"] == 699 and output["failure_count"] == 0
        item = {
            "label": label,
            "command": command,
            "exit_code": result.returncode,
            "receipt": str(destination),
            "receipt_sha256": digest(destination) if output else None,
            "source_receipt_sha256": digest(receipt),
            "replay_sha256": digest(replay),
            "wire_sha256": source_receipt["wire_sha256"],
            "renderer_unchanged": unchanged,
            "source_files_before": source_files_before,
            "source_files_after": source_files_after,
            "log": str(log),
            "log_sha256": digest(log),
            "previous_receipt_sha256": previous,
            "previous_backup": str(backup) if backup else None,
            "passed": valid,
            "counts": output.get("counts") if output else None,
            "complete_mode_plans": output.get("complete_mode_plans") if output else None,
            "failure_count": (0 if args.stage == "v8" else output["failure_count"])
            if valid
            else None,
        }
        records.append(item)
        execution_path.write_text(
            json.dumps(
                {
                    "source_snapshot_sha256": snapshot,
                    "runtime_text_sha256": renderer_sha,
                    "stage": args.stage,
                    "scope": "plan parity"
                    if args.stage == "v8"
                    else "actual callbacks with simulated native pointers",
                    "game_attached": False,
                    "build_run": False,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf8",
        )
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if not valid:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
