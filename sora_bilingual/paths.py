"""Installation paths shared by UI, workers and release tooling."""

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
STATE = ROOT / "generated"
SCRIPTS = PACKAGE / "game" / "scripts"


def build_label(root: Path = ROOT, version: str | None = None) -> str:
    """Local DEV identity for packaged candidates without changing their version."""
    root = Path(root)
    version = version or json.loads((root / "distribution.json").read_text("utf-8"))["version"]
    development = not (root / "installed-manifest.json").is_file()
    try:
        development |= (root / "generated/development-version.txt").read_text(
            "utf-8"
        ).strip() == version
    except OSError, UnicodeError:
        pass
    return f"DEV {version}" if development else version
