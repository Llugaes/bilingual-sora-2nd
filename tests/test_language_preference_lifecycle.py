"""Display choices survive source detection and process lifetimes."""

import tempfile
import unittest
from pathlib import Path

from sora_bilingual.app.native_settings import update_control
from sora_bilingual.config.native_config import (
    LANGUAGE_DEFAULTS_PENDING,
    apply_pending_language_defaults,
    normalize_config,
    read_config,
    write_config,
)
from sora_bilingual.config.locales import LOCALES


class LanguagePreferenceLifecycleTests(unittest.TestCase):
    def test_saved_legacy_pairs_survive_every_new_game_and_base(self):
        for primary, secondary in (("fr", "de"), ("en", "ja"), ("ja", "zh-Hans")):
            with self.subTest(pair=(primary, secondary)), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "control.json"
                write_config(
                    dict(
                        primary=primary,
                        secondary=secondary,
                        backend_token="keep",
                        experimental_primary=True,
                    ),
                    path,
                )
                for base in LOCALES:
                    # Tool restart reads the persisted legacy pair; game restart
                    # changes PID/creation time; a base change may collide with secondary.
                    config = read_config(path)
                    result = apply_pending_language_defaults(config, base)
                    write_config(result, path)
                    self.assertEqual((result["primary"], result["secondary"]), (primary, secondary))
                    self.assertEqual(result["backend_token"], "keep")

    def test_new_default_is_initialized_once_including_japanese(self):
        for base in LOCALES:
            with self.subTest(base=base), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "control.json"
                pending = read_config(path)
                self.assertTrue(pending[LANGUAGE_DEFAULTS_PENDING])
                expected = (base, "en" if base == "ja" else "ja")
                first = apply_pending_language_defaults(pending, base)
                self.assertEqual((first["primary"], first["secondary"]), expected)
                self.assertNotIn(LANGUAGE_DEFAULTS_PENDING, first)
                write_config(first, path)
                for source in ("en", "ja"):
                    saved = read_config(path)
                    after = apply_pending_language_defaults(saved, source)
                    self.assertEqual((after["primary"], after["secondary"]), expected)

    def test_manual_selection_during_first_probe_cancels_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            write_config(normalize_config({LANGUAGE_DEFAULTS_PENDING: True}), path)
            update_control({"secondary": "de"}, path)
            chosen = read_config(path)
            after = apply_pending_language_defaults(chosen, "ja")
            self.assertEqual((after["primary"], after["secondary"]), ("zh-Hans", "de"))
            self.assertNotIn(LANGUAGE_DEFAULTS_PENDING, after)

    def test_existing_empty_file_is_not_new_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            path.write_text("{}", encoding="utf-8")
            config = read_config(path)
            self.assertNotIn(LANGUAGE_DEFAULTS_PENDING, config)
            result = apply_pending_language_defaults(config, "ja")
            self.assertEqual((result["primary"], result["secondary"]), ("zh-Hans", "ja"))

    def test_deliberate_selection_of_same_displayed_defaults_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "control.json"
            write_config(normalize_config({LANGUAGE_DEFAULTS_PENDING: True}), path)
            # The UI's user-only activated signal commits this minimal state,
            # even if currentIndexChanged did not fire.
            update_control({LANGUAGE_DEFAULTS_PENDING: False}, path)
            chosen = read_config(path)
            result = apply_pending_language_defaults(chosen, "en")
            self.assertEqual((result["primary"], result["secondary"]), ("zh-Hans", "ja"))
