"""Remember and locate installed game resources without launching any process."""

import json
from pathlib import Path
import re
from sora_bilingual.paths import STATE


LOCATION = STATE / "game-location.json"


def remember_game(game):
    from sora_bilingual.config.native_config import write_config

    write_config({"path": str(Path(game).resolve())}, LOCATION)


def find_game():
    try:
        game = Path(json.loads(LOCATION.read_text("utf-8"))["path"])
        if (game / "sora_2nd.exe").is_file():
            return game
    except OSError, ValueError, KeyError, TypeError:
        pass
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except ImportError, OSError:
        return None
    roots = {steam}
    try:
        data = (steam / "steamapps/libraryfolders.vdf").read_text("utf-8")
        roots.update(Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s*"([^"]+)"', data))
    except OSError:
        pass
    found = []
    for root in roots:
        try:
            found.extend(p.parent for p in (root / "steamapps/common").glob("*/sora_2nd.exe"))
        except OSError:
            continue
    return found[0] if len(found) == 1 else None
