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
