import unittest
from unittest.mock import Mock, patch

from sora_bilingual.app.native_settings import load_cjk_font


class UIFontTests(unittest.TestCase):
    def test_selects_first_font_without_registering_unused_collections(self):
        app = Mock()
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("PySide6.QtGui.QFontDatabase.addApplicationFont", return_value=7) as register,
            patch(
                "PySide6.QtGui.QFontDatabase.applicationFontFamilies", return_value=["Chosen CJK"]
            ),
        ):
            load_cjk_font(app)
        self.assertEqual(register.call_count, 1)
        self.assertEqual(app.setFont.call_args.args[0].family(), "Chosen CJK")

    def test_failed_font_still_tries_the_next_available_collection(self):
        app = Mock()
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "PySide6.QtGui.QFontDatabase.addApplicationFont", side_effect=[-1, 7]
            ) as register,
            patch(
                "PySide6.QtGui.QFontDatabase.applicationFontFamilies", return_value=["Fallback CJK"]
            ),
        ):
            load_cjk_font(app)
        self.assertEqual(register.call_count, 2)
        self.assertEqual(app.setFont.call_args.args[0].family(), "Fallback CJK")
