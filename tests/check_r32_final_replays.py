"""Copy exact current audited mode plans into canonical Frida replay inputs."""

import hashlib
import json
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("en", "ja", "zh-Hans", "zh-Hant", "en-manual")
DEFAULT_FREEZE = ROOT / "generated/r32-coverage-source-freeze.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_contract(path=DEFAULT_FREEZE):
    freeze = json.loads(Path(path).read_text("utf8"))
    return (
        freeze,
        freeze["snapshot_sha256"],
        freeze["files"]["sora_bilingual/game/scripts/runtime_text.js"],
    )


def preserve_file(source, evidence_dir):
    source, evidence_dir = Path(source), Path(evidence_dir)
    if not source.exists():
        return None
    relative = source.relative_to(ROOT)
    if relative.parts[0] == "generated":
        relative = relative.relative_to("generated")
    target = evidence_dir / relative
    if target.exists() and digest(target) != digest(source):
        target = target.with_name(target.stem + ".before-" + digest(source)[:12] + target.suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    assert digest(target) == digest(source), "existing evidence must never be overwritten"
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument(
        "--audit", type=Path, default=ROOT / "generated/r32-complete-wire-final-root.json"
    )
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "generated/r32-coverage-local2-evidence"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r32-final-replay-preparation.json"
    )
    args = parser.parse_args()
    audit_path = args.audit.resolve()
    audit = json.loads(audit_path.read_text("utf8"))
    freeze, snapshot, renderer_sha = frozen_contract(args.freeze)
    renderer = ROOT / "sora_bilingual/game/scripts/runtime_text.js"
    assert audit["source_snapshot_sha256"] == snapshot
    assert digest(renderer) == renderer_sha
    assert audit["summary"]["mode_checks"] == 10485
    assert audit["summary"]["strict_failure_count"] == 674
    records = []
    for label in LABELS:
        (run,) = [row for row in audit["runs"] if row["label"] == label]
        receipt_path = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
        receipt = json.loads(receipt_path.read_text("utf8"))
        assert digest(receipt_path) == run["receipt_sha256"]
        assert receipt["source_snapshot_sha256"] == run["source_snapshot_sha256"] == snapshot
        assert run["source_files"]["sora_bilingual/game/scripts/runtime_text.js"] == renderer_sha
        assert digest(Path(receipt["wire_path"])) == receipt["wire_sha256"] == run["wire_sha256"]
        assert digest(Path(receipt["model_path"])) == receipt["model_sha256"] == run["model_sha256"]
        assert run["actual_wire_loaded"] and run["runtime_source_unchanged"]
        assert len(run["cases"]) == 699 and run["mode_checks"] == 2097
        assert all(
            set(row["modes"]) == {"primary", "secondary", "annotation"} for row in run["cases"]
        )
        assert run["known_frame_semantic_failure_count"] == 0
        assert run["strict_failure_count"] == (674 if label == "en" else 0)
        assert len(run["failures"]) == run["strict_failure_count"]
        destination = ROOT / f"generated/r32-coverage-{label}-product-replay.json"
        previous = digest(destination) if destination.is_file() else None
        backup = preserve_file(destination, args.evidence_dir)
        rows = [{"name": f"{row['domain']}/{i}", **row} for i, row in enumerate(run["cases"])]
        replay = {
            "failure_count": 0,
            "failure_count_scope": "saved Node plan parity baseline; semantic admission is a separate audit",
            "purpose": "current indexed-wire Node versus Frida V8 complete plan parity",
            "source_snapshot_sha256": snapshot,
            "runtime_text_sha256": renderer_sha,
            "wire_sha256": run["wire_sha256"],
            "source_audit": str(audit_path),
            "source_audit_sha256": digest(audit_path),
            "receipt_sha256": digest(receipt_path),
            "strict_failure_count": run["strict_failure_count"],
            "retained_strict_frame_differences": run["retained_source_formatting_count"],
            "semantic_admission_failure_count": run["known_frame_semantic_failure_count"],
            "semantic_normalization_rules": audit["semantic_normalization_rules"],
            "strict_failures": run["failures"],
            "rows": rows,
        }
        destination.write_text(
            json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
        )
        loaded = json.loads(destination.read_text("utf8"))
        assert [{k: v for k, v in row.items() if k != "name"} for row in loaded["rows"]] == run[
            "cases"
        ]
        records.append(
            {
                "label": label,
                "path": str(destination),
                "sha256": digest(destination),
                "row_count": len(rows),
                "mode_plans": 2097,
                "strict_failure_count": run["strict_failure_count"],
                "semantic_admission_failure_count": run["known_frame_semantic_failure_count"],
                "old_backup": str(backup) if backup else None,
                "old_backup_sha256": digest(backup) if backup else None,
                "previous_canonical_sha256": previous,
            }
        )
        print(json.dumps(records[-1], ensure_ascii=False), flush=True)
    assert digest(renderer) == renderer_sha
    result = {
        "source_snapshot_sha256": snapshot,
        "runtime_text_sha256": renderer_sha,
        "source_audit_sha256": digest(audit_path),
        "plans_copied_without_changes": True,
        "game_attached": False,
        "build_run": False,
        "records": records,
    }
    preserve_file(args.output, args.evidence_dir)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
