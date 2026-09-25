"""Installation paths shared by UI, workers and release tooling."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
STATE = ROOT / "generated"
SCRIPTS = PACKAGE / "game" / "scripts"
