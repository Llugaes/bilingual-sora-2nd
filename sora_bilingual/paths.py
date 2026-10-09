"""Installation paths shared by UI, workers and release tooling."""

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
STATE = ROOT / "generated"
SCRIPTS = PACKAGE / "game" / "scripts"


def build_label(root: Path = ROOT, version: str | None = None) -> str:
    """Local DEV identity for packaged candidates without changing their version."""
    root = Path(root)
    if version is None:
        try:
            version = json.loads((root / "distribution.json").read_text("utf-8"))["version"]
        except OSError, ValueError, KeyError, TypeError:
            version = ""
    development = not (root / "installed-manifest.json").is_file()
    try:
        development |= (root / "generated/development-version.txt").read_text(
            "utf-8"
        ).strip() == version
    except OSError, UnicodeError:
        pass
    if development:
        try:
            manifest = json.loads((root / "dev-manifest.json").read_text("utf-8"))
            label = manifest.get("display_version") if isinstance(manifest, dict) else None
        except OSError, ValueError:
            label = None
        if isinstance(label, str) and re.fullmatch(
            r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}-dev[0-9]{1,4}(?:-r[0-9]{1,4})?", label
        ):
            return "DEV " + label
        return f"DEV {version}" if version else "DEV"
    return version
