"""Copy only sealed candidate payload into a new autonomous test installation."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=ROOT / "generated/r32-live002-startup.json")
    args = parser.parse_args()
    source, destination = args.candidate.resolve(), args.live.resolve()
    assert source != destination and not destination.exists()
    manifest = json.loads((source / "dev-manifest.json").read_text("utf8"))
    cache = json.loads((source / "candidate-cache.json").read_text("utf8"))
    expected = {**manifest["files"], **cache["files"]}
    destination.mkdir(parents=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    for name, digest in expected.items():
        original, target = source / name, destination / name
        assert original.resolve().is_relative_to(source) and target.resolve().is_relative_to(
            destination
        )
        assert sha(original.read_bytes()) == digest, name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        assert sha(target.read_bytes()) == digest, name
    for name in ("dev-manifest.json", "candidate-cache.json", "installed-manifest.json"):
        shutil.copy2(source / name, destination / name)
    # This sealed candidate marker is outside the installed payload manifest.
    # Preserve it so the isolated live installation keeps its actual DEV label.
    marker = source / "generated/development-version.txt"
    version = json.loads((source / "distribution.json").read_text("utf8"))["version"]
    assert marker.read_text("utf8").strip() == version
    shutil.copy2(marker, destination / "generated/development-version.txt")
    config = json.loads((ROOT / "generated/r32-live001-startup.json").read_text("utf8"))["config"]
    assert config["game_language"] == config["primary"] == "en" and config["secondary"] == "zh-Hans"
    assert config["experimental_primary"] is False
    (destination / "generated/native-control.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), "utf8"
    )
    result = {
        "candidate": str(source),
        "live_root": str(destination),
        "verified_files": len(expected),
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "config": config,
        "development_marker_sha256": sha(marker.read_bytes()),
        "copied_agent_tokens": False,
        "copied_font_receipts": False,
        "game_started": False,
        "game_setting_temporary_navigation": True,
        "game_setting_exact_original_backup": str(
            ROOT / "generated/r32-game-setting-before-mouse-navigation.json"
        ),
    }
    assert not args.receipt.exists(), "refuse to replace an earlier live installation receipt"
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(json.dumps({k: v for k, v in result.items() if k != "config"}))


if __name__ == "__main__":
    main()
