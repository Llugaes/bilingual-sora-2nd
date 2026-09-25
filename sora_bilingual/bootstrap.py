"""Recover an interrupted installation before importing the UI or native code."""

from pathlib import Path
import sys


def main():
    from sora_bilingual.paths import ROOT as root

    if sys.stdout is None or sys.stderr is None:
        (root / "generated").mkdir(parents=True, exist_ok=True)
        log = (root / "generated/overlay-error.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log

    try:
        from sora_bilingual.updates.update_installer import recover

        recover(root)
        selector = root / "runtime/current.txt"
        if selector.is_file() and (root / "BilingualSora2nd.exe").is_file():
            import subprocess

            active = selector.read_text("utf-8").strip()
            if Path(sys.executable).parent.name != active:
                # Recovery may have committed a new runtime while using the old one.
                subprocess.Popen(
                    [str(root / "BilingualSora2nd.exe"), *sys.argv[1:]],
                    cwd=root,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return 0
    except Exception as exc:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "更新恢复未完成，请保留 generated/updates 并查看日志。\n" + str(exc),
            "Sora Bilingual",
            0x10,
        )
        return 1
    try:
        from sora_bilingual.app.native_overlay import main as run

        return run()
    except Exception:
        import traceback
        import ctypes

        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(
            None,
            "启动失败 / Startup failed / 起動エラー\n\n"
            "generated/overlay-error.log\n\n"
            "请保留完整解压目录。Keep the full extracted folder. 展開したフォルダー全体を保持してください。",
            "Bilingual Sora 2nd",
            0x10,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
