"""Sequential explicit-wire replay of the final extracted candidate; no package writes."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil
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
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--label", choices=LABELS)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--run-tag", default="local3")
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "generated/r32-coverage-local2-evidence"
    )
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    product = args.product.resolve()
    cache_path = product / "candidate-cache.json"
    cache = json.loads(cache_path.read_text("utf8"))
    freeze = args.freeze.resolve()
    _, snapshot, renderer_sha = frozen_contract(freeze)
    audit = json.loads(args.audit.read_text("utf8")) if args.audit else None
    if audit:
        assert audit["source_snapshot_sha256"] == snapshot
    namespace = args.run_tag if args.run_tag.startswith("r32-") else "r32-" + args.run_tag
    assert cache["source_snapshot_sha256"] == snapshot
    if args.archive_sha256:
        assert len(args.archive_sha256) == 64 and all(
            c in "0123456789abcdef" for c in args.archive_sha256.lower()
        )
    script_names = (
        "runtime_text.js",
        "native_transport.js",
        "native_agent.js",
        "runtime_paragraph.js",
        "runtime_identity.js",
    )
    package_js_before = {
        name: digest(product / "sora_bilingual/game/scripts" / name) for name in script_names
    }
    assert package_js_before["runtime_text.js"] == renderer_sha
    summary = {
        "product_root": str(product),
        "archive_sha256_supplied_by_root": args.archive_sha256,
        "archive_rehashed_by_this_check": False,
        "source_snapshot_sha256": snapshot,
        "candidate_cache_sha256_before": digest(cache_path),
        "package_js_sha256_before": package_js_before,
        "freeze_path": str(freeze),
        "freeze_sha256": digest(freeze),
        "scope": "actual packaged explicit matrix wire versus current saved Node complete plans in Frida V8",
        "package_audit_repeated": False,
        "node_or_unit_tests_repeated": False,
        "production_model_compiled": False,
        "build_run": False,
        "game_attached": False,
        "semantic_admission_revalidated": False,
        "records": [],
        "complete": False,
    }
    summary["source_audit_path"] = str(args.audit.resolve()) if args.audit else None
    summary["source_audit_sha256"] = digest(args.audit) if args.audit else None
    destination = ROOT / f"generated/{namespace}-packaged-verification-summary.json"
    if args.label and destination.exists():
        previous = json.loads(destination.read_text("utf8"))
        assert (
            previous["product_root"] == str(product)
            and previous["source_snapshot_sha256"] == snapshot
        )
        assert previous["package_js_sha256_before"] == package_js_before
        summary = previous
    for label in (args.label,) if args.label else LABELS:
        receipt_path = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
        replay_path = ROOT / f"generated/r32-coverage-{label}-product-replay.json"
        receipt = json.loads(receipt_path.read_text("utf8"))
        if audit:
            (run,) = [row for row in audit["runs"] if row["label"] == label]
            replay = json.loads(replay_path.read_text("utf8"))
            assert run["wire_sha256"] == receipt["wire_sha256"] == replay["wire_sha256"]
            assert replay["source_audit_sha256"] == digest(args.audit)
        (selected,) = [row for row in cache["config_matrix"] if row["config"] == receipt["config"]]
        wire = product / "generated" / selected["wire_name"]
        wire_before = wire.stat()
        output_path = ROOT / f"generated/{namespace}-packaged-{label}-v8.json"
        assert not output_path.exists(), (
            f"refuse to overwrite previous final packaged evidence: {output_path}"
        )
        command = [
            str(FRIDA_PYTHON),
            "-X",
            "utf8",
            "tests/check_r32_packaged_v8.py",
            "--product",
            str(product),
            "--wire",
            str(wire),
            "--receipt",
            str(receipt_path),
            "--replay",
            str(replay_path),
            "--freeze",
            str(freeze),
            "--output",
            str(output_path),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf8",
            errors="replace",
        )
        log = ROOT / f"generated/{namespace}-packaged-{label}-v8.log"
        if log.exists():
            backup = log.with_name(log.stem + ".before-" + digest(log)[:12] + log.suffix)
            if not backup.exists():
                shutil.copy2(log, backup)
            assert digest(backup) == digest(log)
            for old in summary["records"]:
                if old["log_path"] == str(log) and old["log_sha256"] == digest(backup):
                    old["log_path"] = str(backup)
        log.write_text(result.stdout, encoding="utf8")
        output = json.loads(output_path.read_text("utf8")) if output_path.exists() else None
        wire_after = wire.stat()
        wire_unchanged = (
            wire_before.st_size == wire_after.st_size
            and wire_before.st_mtime_ns == wire_after.st_mtime_ns
        )
        passed = (
            result.returncode == 0
            and output is not None
            and output["parity_failure_count"] == 0
            and wire_unchanged
        )
        record = {
            "label": label,
            "config": receipt["config"],
            "command": command,
            "attempt": 1 + sum(row["label"] == label for row in summary["records"]),
            "exit_code": result.returncode,
            "passed": passed,
            "output_path": str(output_path),
            "output_sha256": digest(output_path) if output_path.exists() else None,
            "log_path": str(log),
            "log_sha256": digest(log),
            "wire_path": str(wire),
            "wire_size": wire_after.st_size,
            "wire_mtime_ns_before": wire_before.st_mtime_ns,
            "wire_mtime_ns_after": wire_after.st_mtime_ns,
            "wire_size_and_mtime_unchanged": wire_unchanged,
            "model_sha256": output["model_sha256"] if output else None,
            "wire_sha256": output["wire_sha256"] if output else None,
            "runtime_text_sha256": output["runtime_text_sha256"] if output else None,
            "complete_mode_plans": output["complete_mode_plans"] if output else None,
            "parity_failure_count": output["parity_failure_count"] if output else None,
            "retained_strict_frame_differences": output["retained_strict_frame_differences"]
            if output
            else None,
            "package_source_code_files_checked": output["package_source_code_files_checked"]
            if output
            else None,
            "non_code_manifest_differences": output["non_code_package_manifest_differences"]
            if output
            else None,
        }
        summary["records"].append(record)
        latest = {row["label"]: row for row in summary["records"]}
        summary["complete_mode_plans"] = sum(
            row["complete_mode_plans"] or 0 for row in latest.values()
        )
        summary["parity_failure_count"] = (
            sum(row["parity_failure_count"] for row in latest.values())
            if all(row["parity_failure_count"] is not None for row in latest.values())
            else None
        )
        summary["retained_strict_frame_differences"] = sum(
            row["retained_strict_frame_differences"] or 0 for row in latest.values()
        )
        summary["retained_failed_attempts"] = sum(not row["passed"] for row in summary["records"])
        summary["complete"] = len(latest) == len(LABELS) and all(
            row["passed"] for row in latest.values()
        )
        summary["package_js_sha256_after"] = {
            name: digest(product / "sora_bilingual/game/scripts" / name) for name in script_names
        }
        summary["candidate_cache_sha256_after"] = digest(cache_path)
        summary["package_js_unchanged"] = (
            summary["package_js_sha256_before"] == summary["package_js_sha256_after"]
        )
        destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
        print(
            json.dumps(
                {
                    key: value
                    for key, value in record.items()
                    if key not in ("non_code_manifest_differences", "command")
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if not passed or not summary["package_js_unchanged"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
