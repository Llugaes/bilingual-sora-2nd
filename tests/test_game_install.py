import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from sora_bilingual.game import install


class GameInstallTests(unittest.TestCase):
    def test_remembered_path_is_used_only_while_executable_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / "Game"
            game.mkdir()
            exe = game / "sora_2nd.exe"
            exe.touch()
            with patch.object(install, "LOCATION", Path(tmp) / "location.json"):
                install.remember_game(game)
                self.assertTrue(install.find_game().samefile(game))
                exe.unlink()
                with patch("winreg.OpenKey", side_effect=OSError):
                    self.assertIsNone(install.find_game())

    def test_steam_libraries_are_discovered_without_fixed_drive_or_folder_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "Steam"
            library = root / "OtherLibrary"
            (steam / "steamapps").mkdir(parents=True)
            (steam / "steamapps/libraryfolders.vdf").write_text(
                '"path" ' + json.dumps(str(library)), "utf-8"
            )
            game = library / "steamapps/common/Localized Game Title"
            game.mkdir(parents=True)
            (game / "sora_2nd.exe").touch()
            with (
                patch.object(install, "LOCATION", root / "none.json"),
                patch("winreg.OpenKey", return_value=MagicMock()),
                patch("winreg.QueryValueEx", return_value=(str(steam), 1)),
            ):
                self.assertEqual(install.find_game(), game)
                another = steam / "steamapps/common/SecondCopy"
                another.mkdir(parents=True)
                (another / "sora_2nd.exe").touch()
                self.assertIsNone(install.find_game())

    def test_steam_executable_registry_value_is_used_when_steam_path_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "Steam"
            game = steam / "steamapps/common/Localized Game Title"
            game.mkdir(parents=True)
            (game / "sora_2nd.exe").touch()

            def value(_, name):
                if name == "SteamExe":
                    return str(steam / "steam.exe"), 1
                raise OSError

            with (
                patch.object(install, "LOCATION", root / "none.json"),
                patch("winreg.OpenKey", return_value=MagicMock()),
                patch("winreg.QueryValueEx", side_effect=value),
                patch.object(install, "DEFAULT_STEAM_ROOTS", ()),
            ):
                self.assertEqual(install.find_game(), game)

    def test_machine_install_path_is_used_when_current_user_values_are_missing(self):
        import winreg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "Steam"
            game = steam / "steamapps/common/Localized Game Title"
            game.mkdir(parents=True)
            (game / "sora_2nd.exe").touch()

            class Key:
                def __init__(self, hive, subkey):
                    self.hive = hive
                    self.subkey = subkey

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

            def value(key, name):
                if (
                    key.hive == winreg.HKEY_LOCAL_MACHINE
                    and key.subkey == r"SOFTWARE\WOW6432Node\Valve\Steam"
                    and name == "InstallPath"
                ):
                    return str(steam), 1
                raise OSError

            with (
                patch.object(install, "LOCATION", root / "none.json"),
                patch("winreg.OpenKey", side_effect=Key),
                patch("winreg.QueryValueEx", side_effect=value),
                patch.object(install, "DEFAULT_STEAM_ROOTS", ()),
            ):
                self.assertEqual(install.find_game(), game)

    def test_standard_steam_root_is_used_when_no_registry_location_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            steam = root / "Steam"
            game = steam / "steamapps/common/Localized Game Title"
            game.mkdir(parents=True)
            (game / "sora_2nd.exe").touch()
            with (
                patch.object(install, "LOCATION", root / "none.json"),
                patch.object(install, "_registry_steam_roots", return_value=()),
                patch.object(install, "DEFAULT_STEAM_ROOTS", (steam,)),
            ):
                self.assertEqual(install.find_game(), game)
