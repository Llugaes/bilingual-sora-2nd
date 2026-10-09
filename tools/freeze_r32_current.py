"""Preserve local1 receipts, then freeze the current release source without touching Git."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-evidence", default="r32-coverage-local1-evidence")
    parser.add_argument(
        "--changed-files",
        nargs="+",
        default=[
            "sora_bilingual/game/scripts/native_agent.js",
            "sora_bilingual/game/scripts/runtime_text.js",
            "sora_bilingual/localization/menu_text.py",
        ],
    )
    args = parser.parse_args()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    target = ROOT / "generated/r32-coverage-source-freeze.json"
    previous = json.loads(target.read_text("utf8"))
    archive = ROOT / "generated" / args.prior_evidence
    assert archive.resolve().is_relative_to((ROOT / "generated").resolve())
    archive.mkdir(exist_ok=True)
    for pattern in (
        "r32-coverage*.json",
        "r32-package-audit.json",
        "r32-packaged-verification-summary.json",
    ):
        for path in (ROOT / "generated").glob(pattern):
            dest = archive / path.name
            if dest.exists():
                assert dest.read_bytes() == path.read_bytes(), path
            else:
                shutil.copy2(path, dest)
    names = sorted(
        set(json.loads((ROOT / "release-files.json").read_text("utf8"))) | {"release-files.json"}
    )
    assert set(names) == set(previous["files"]), "release inventory changed; review before freezing"
    staged = subprocess.check_output(["git", "diff", "--cached", "--binary"], cwd=ROOT)
    assert sha(staged) == previous["staged_diff_sha256"], "user index changed"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert head == previous["source_head"], "HEAD changed"
    files = {name: sha((ROOT / name).read_bytes()) for name in names}
    result = {
        **previous,
        "files": files,
        "snapshot_sha256": sha(json.dumps(files, sort_keys=True).encode()),
        "previous_candidate_snapshot_sha256": previous["snapshot_sha256"],
        "previous_candidate_receipts": str(archive),
        "changes_from_previous": [name for name in names if files[name] != previous["files"][name]],
    }
    assert result["changes_from_previous"] == sorted(args.changed_files), result[
        "changes_from_previous"
    ]
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("snapshot_sha256", "changes_from_previous", "staged_diff_sha256")
            }
        )
    )


if __name__ == "__main__":
    main()
