"""Command-line entry point for the safe local font delivery service."""

import argparse
import json
from pathlib import Path

from sora_bilingual.fonts.font_delivery import LOADER, LOADER_SHA, ensure, prepare


def _game_running() -> bool:
    import frida

    return any(
        process.name.lower() == "sora_2nd.exe"
        for process in frida.get_local_device().enumerate_processes()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--loader", type=Path, default=LOADER)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--update", action="store_true", help="accepted for compatibility")
    args = parser.parse_args()
    candidate = args.candidate or prepare(args.game)
    result = ensure(
        args.game,
        candidate,
        game_running=not args.install,
        is_game_running=_game_running if args.install else None,
        loader=args.loader,
    )
    if args.install and result["state"] == "restart-required":
        raise RuntimeError("请先正常退出游戏，再安装字库文件。")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
