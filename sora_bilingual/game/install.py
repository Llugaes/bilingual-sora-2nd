"""Remember and locate installed game resources without launching any process."""

import json
import os
from pathlib import Path
import re
from sora_bilingual.paths import STATE


LOCATION = STATE / "game-location.json"
DEFAULT_STEAM_ROOTS = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
)


def remember_game(game):
    from sora_bilingual.config.native_config import write_config

    write_config({"path": str(Path(game).resolve())}, LOCATION)


def _registry_steam_roots():
    """Read Steam's registered install locations without changing any settings."""
    try:
        import winreg
    except ImportError:
        return ()

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", ("SteamPath", "SteamExe")),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            ("InstallPath", "SteamPath", "SteamExe"),
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Valve\Steam",
            ("InstallPath", "SteamPath", "SteamExe"),
        ),
    )
    roots = []
    for hive, subkey, values in locations:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for value in values:
                    try:
                        raw = winreg.QueryValueEx(key, value)[0]
                    except OSError:
                        continue
                    if not isinstance(raw, str) or not raw.strip():
                        continue
                    path = Path(raw)
                    roots.append(path.parent if value == "SteamExe" else path)
        except OSError:
            continue
    return tuple(roots)


def _steam_library_roots(steam):
    roots = [Path(steam)]
    try:
        data = (Path(steam) / "steamapps/libraryfolders.vdf").read_text("utf-8")
        roots.extend(Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s*"([^"]+)"', data))
    except OSError:
        pass
    return roots


def find_game():
    """Locate one installed copy without launching a game or choosing among copies."""
    try:
        game = Path(json.loads(LOCATION.read_text("utf-8"))["path"])
        if (game / "sora_2nd.exe").is_file():
            return game
    except OSError, ValueError, KeyError, TypeError:
        pass

    roots = []
    seen_roots = set()
    for steam in (*_registry_steam_roots(), *DEFAULT_STEAM_ROOTS):
        try:
            key = str(Path(steam).resolve()).casefold()
        except OSError:
            key = str(steam).casefold()
        if key in seen_roots:
            continue
        seen_roots.add(key)
        roots.extend(_steam_library_roots(steam))

    found = []
    for root in roots:
        try:
            found.extend(p.parent for p in (root / "steamapps/common").glob("*/sora_2nd.exe"))
        except OSError:
            continue
    unique = {}
    for game in found:
        try:
            key = str(game.resolve()).casefold()
        except OSError:
            key = str(game).casefold()
        unique[key] = game
    return next(iter(unique.values())) if len(unique) == 1 else None
