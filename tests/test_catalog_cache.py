import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sora_bilingual.localization.native_catalog import load_entries, model_path


class CatalogCacheTests(unittest.TestCase):
    def test_ui_locale_labels_do_not_invalidate_resource_or_model_cache(self):
        from sora_bilingual.localization.native_catalog import fingerprint

        original = Path.read_bytes

        def cosmetic(path):
            data = original(path)
            return data + b"\n# changed UI labels only\n" if path.name == "locales.py" else data

        with tempfile.TemporaryDirectory() as temp:
            before = fingerprint(temp)
            with patch.object(Path, "read_bytes", cosmetic):
                self.assertEqual(fingerprint(temp), before)

    def test_verified_legacy_catalog_migrates_without_reparsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "catalog.json").write_text('{"entries":[]}', encoding="utf-8")
            manifest = out / "catalog-signature.json"
            manifest.write_text(
                json.dumps({"resources": [], "code": "old"}, sort_keys=True), encoding="utf-8"
            )

            def stamp(_game, legacy=False):
                return {
                    "resources": [],
                    "catalog_code": "old" if legacy else "new",
                    "code": "model",
                }

            with (
                patch("sora_bilingual.localization.native_catalog.fingerprint", side_effect=stamp),
                patch("sora_bilingual.localization.native_catalog.build_all") as build,
            ):
                load_entries("unused", out)
                build.assert_not_called()
                self.assertEqual(json.loads(manifest.read_text("utf-8"))["code"], "new")

    def test_renderer_change_rebuilds_model_but_reuses_parsed_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            entries = [{"key": "k", "texts": {"ja": "字"}}]
            (out / "catalog.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
            (out / "catalog-signature.json").write_text(
                json.dumps({"resources": [], "code": "parser"}, sort_keys=True), encoding="utf-8"
            )
            stamps = [
                {"resources": [], "catalog_code": "parser", "code": "render1"},
                {"resources": [], "catalog_code": "parser", "code": "render2"},
            ]
            with (
                patch("sora_bilingual.localization.native_catalog.fingerprint", side_effect=stamps),
                patch("sora_bilingual.localization.native_catalog.build_all") as build,
            ):
                a, sa = load_entries("unused", out)
                b, sb = load_entries("unused", out)
                build.assert_not_called()
                self.assertEqual(a, b)
                config = {"primary": "ja", "secondary": "en"}
                self.assertNotEqual(model_path(sa, config, out), model_path(sb, config, out))

    def test_resource_change_requires_archive_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "catalog.json").write_text('{"entries":[]}', encoding="utf-8")
            (out / "catalog-signature.json").write_text(
                json.dumps({"resources": [], "code": "parser"}, sort_keys=True), encoding="utf-8"
            )
            stamp = {
                "resources": [["script.pac", 100, 123]],
                "catalog_code": "parser",
                "code": "render",
            }
            with (
                patch("sora_bilingual.localization.native_catalog.fingerprint", return_value=stamp),
                patch(
                    "sora_bilingual.localization.native_catalog.build_all",
                    return_value={"entries": []},
                ) as build,
            ):
                load_entries("unused", out)
                build.assert_called_once()
