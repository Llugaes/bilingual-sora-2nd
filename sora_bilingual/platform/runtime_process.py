"""Choose the packaged, visibly named interpreter; retain source-checkout support."""

from pathlib import Path
import sys


def runtime_executable(role):
    names = {"ui": "UI", "backend": "Backend", "worker": "Worker"}
    directory = Path(sys.executable).parent
    named = directory / f"BilingualSora2nd.{names[role]}.exe"
    if named.is_file():
        return str(named)
    fallback = directory / "pythonw.exe" if role != "worker" else Path(sys.executable)
    return str(fallback if fallback.is_file() else Path(sys.executable))
