"""Recover an interrupted installation before importing the UI or native code."""

from pathlib import Path
import sys


def main():
    from sora_bilingual.paths import ROOT as root

    try:
        from sora_bilingual.updates.update_installer import recover

        recover(root)
    except Exception as exc:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "更新恢复未完成，请保留 generated/updates 并查看日志。\n" + str(exc),
            "Sora Bilingual",
            0x10,
        )
        return 1
    from sora_bilingual.app.native_overlay import main as run

    return run()


if __name__ == "__main__":
    sys.exit(main())
