"""Preserve previous candidate evidence byte-for-byte before new gate output."""

import argparse
import json
from pathlib import Path
from check_r32_final_replays import (
    ROOT,
    LABELS,
    DEFAULT_FREEZE,
    digest,
    frozen_contract,
    preserve_file,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument(
        "--evidence-dir", type=Path, default=ROOT / "generated/r32-coverage-local2-evidence"
    )
    args = parser.parse_args()
    freeze, snapshot, _ = frozen_contract(args.freeze)
    previous = freeze.get("previous_candidate_snapshot_sha256")
    assert previous and previous != snapshot
    paths = set((ROOT / "generated").glob("r32-final-*.json")) | set(
        (ROOT / "generated").glob("r32-final-*.log")
    )
    paths.add(ROOT / "generated/r32-complete-wire-final-root.json")
    for label in LABELS:
        for suffix in ("product-replay", "production-frida", "production-receipt"):
            paths.add(ROOT / f"generated/r32-coverage-{label}-{suffix}.json")
        paths.add(ROOT / f"generated/r32-callbacks-{label}.json")
    for name in (
        "r32-final-v8-prior-evidence",
        "r32-final-callbacks-prior-evidence",
        "r32-final-replay-preoverwrite",
    ):
        folder = ROOT / "generated" / name
        if folder.exists():
            paths.update(p for p in folder.rglob("*") if p.is_file())
    for name in (
        "check_r32_final_replays.py",
        "check_r32_final_wire_gate.py",
        "check_r32_final_packaged_gate.py",
    ):
        paths.add(ROOT / "tests" / name)
    records, skipped = [], []
    for source in sorted(paths):
        if not source.is_file():
            continue
        if source.suffix == ".json":
            try:
                data = json.loads(source.read_text("utf8"))
                if data.get("source_snapshot_sha256") == snapshot:
                    skipped.append(str(source))
                    continue
            except ValueError, UnicodeDecodeError:
                pass  # Failed/empty raw receipts are evidence too.
        before = digest(source)
        backup = preserve_file(source, args.evidence_dir)
        assert digest(source) == before == digest(backup)
        records.append(
            {
                "source": str(source),
                "backup": str(backup),
                "sha256": before,
                "bytes": source.stat().st_size,
            }
        )
    output = args.evidence_dir / "r32-final-archive-manifest.json"
    preserve_file(output, args.evidence_dir) if output.exists() else None
    output.write_text(
        json.dumps(
            {
                "previous_candidate_snapshot_sha256": previous,
                "next_candidate_snapshot_sha256": snapshot,
                "byte_exact": True,
                "records": records,
                "current_snapshot_files_not_archived_as_old": skipped,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    print(
        json.dumps(
            {
                "manifest": str(output),
                "sha256": digest(output),
                "preserved_files": len(records),
                "bytes": sum(row["bytes"] for row in records),
                "skipped_current_files": len(skipped),
            }
        )
    )


if __name__ == "__main__":
    main()
