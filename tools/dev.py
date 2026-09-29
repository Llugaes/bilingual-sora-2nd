"""One reproducible entry for local and CI verification."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "test", "format", "publish-local", "preview"])
    command = parser.parse_args().command
    if command == "format":
        run(sys.executable, "-m", "ruff", "format", ".")
    elif command in {"check", "test"}:
        if command == "check":
            run(sys.executable, "-m", "ruff", "check", ".")
            run(sys.executable, "-m", "ruff", "format", "--check", ".")
        run(sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-q")
        run(
            "node",
            "--test",
            "tests/test_native_agent.js",
            "tests/test_runtime_identity.js",
            "tests/test_runtime_text.js",
            "tests/test_runtime_paragraph.js",
            "tests/test_runtime_fonts.js",
            "tests/test_native_transport.js",
        )
        if sys.platform == "win32":
            # Exercise the compiled native helper in a self-created hidden
            # process. This must never attach to a running game.
            run(sys.executable, "-X", "utf8", "tests/check_runtime_text_engine.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_control.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_fonts.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_geometry.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_parser.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_size_hook.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_size_metrics.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_log_inset.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_measure.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_nested_ruby.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_reentry.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_log_activation.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_log_commit.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_dynamic_identity.py")
            run(sys.executable, "-X", "utf8", "tests/check_native_refresh.py")
    elif command == "publish-local":
        run(sys.executable, "-m", "sora_bilingual.updates.tool_updates")
    elif command == "preview":
        run(sys.executable, "tests/render_overlay_preview.py")


if __name__ == "__main__":
    main()
