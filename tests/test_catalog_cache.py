import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch
from sora_bilingual.localization.native_catalog import (
    fingerprint,
    load_entries,
    load_model,
    model_path,
    ready_model,
)


class CatalogCacheTests(unittest.TestCase):
    def test_idle_cache_identity_does_not_import_the_compiler(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from sora_bilingual.localization.native_catalog import fingerprint, model_path; assert 'sora_bilingual.localization.menu_text' not in sys.modules; assert 'sora_bilingual.localization.resources' not in sys.modules; assert 'sora_bilingual.localization.catalog_build' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resource_drift_during_content_hash_rejects_the_snapshot(self):
        from sora_bilingual.localization import native_catalog

        with tempfile.TemporaryDirectory() as temp:
            game, pac = self.resource_fixture(Path(temp))
            original = native_catalog.hashlib.file_digest

            def hash_and_change(stream, algorithm):
                digest = original(stream, algorithm)
                pac.write_bytes(b"changed while content digest was being read")
                return digest

            with patch.object(native_catalog.hashlib, "file_digest", hash_and_change):
                with self.assertRaises(native_catalog.ResourceChangedError) as error:
                    fingerprint(game)
            self.assertEqual(error.exception.phase, "resource_content_read")
            self.assertEqual(error.exception.changed_files, ["script.pac"])

    def test_resource_content_read_denial_is_not_treated_as_missing_or_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            game, pac = self.resource_fixture(Path(temp))
            original = Path.open

            def deny_resource(path, *args, **kwargs):
                if path == pac:
                    raise PermissionError("resource content read denied")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", deny_resource):
                with self.assertRaisesRegex(PermissionError, "resource content read denied"):
                    fingerprint(game)

    def test_same_size_resource_change_with_restored_mtime_invalidates_identity(self):
        from sora_bilingual.localization.native_catalog import _verify_resources

        with tempfile.TemporaryDirectory() as temp:
            game, pac = self.resource_fixture(Path(temp))
            before = fingerprint(game)
            stat = pac.stat()
            data = pac.read_bytes()
            pac.write_bytes(bytes([data[0] ^ 1]) + data[1:])
            os.utime(pac, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertEqual(
                (pac.stat().st_size, pac.stat().st_mtime_ns), (stat.st_size, stat.st_mtime_ns)
            )
            self.assertNotEqual(fingerprint(game)["resources"], before["resources"])
            with self.assertRaisesRegex(ValueError, "resource_changed_during_preparation"):
                _verify_resources(game, before["resources"], "same_metadata_content_change")

    def test_model_cache_read_denial_is_not_rebuilt_or_acknowledged_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, _ = self.resource_fixture(root)
            out = root / "output"
            out.mkdir()
            config = {"primary": "ja", "secondary": "en", "game_language": "en"}
            signature = json.dumps(fingerprint(game), sort_keys=True)
            model_path(signature, config, out).write_text("{}", "utf-8")
            with (
                patch.object(Path, "read_text", side_effect=PermissionError("owned model denial")),
                patch(
                    "sora_bilingual.localization.native_catalog.load_entries",
                    side_effect=AssertionError("denied model must not rebuild"),
                ) as catalog,
            ):
                with self.assertRaisesRegex(PermissionError, "owned model denial"):
                    ready_model(game, config, out)
            catalog.assert_not_called()
            self.assertFalse((out / "model-preparation.json").exists())

    def resource_fixture(self, root):
        game = root / "game"
        pac = game / "pac/steam/script.pac"
        pac.parent.mkdir(parents=True)
        pac.write_bytes(b"resource generation one")
        return game, pac

    def test_resource_change_during_catalog_build_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)
            out = root / "output"

            def change(*_):
                pac.write_bytes(b"different resource generation two")
                return {"entries": []}

            with patch("sora_bilingual.localization.catalog_build.build_all", side_effect=change):
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    load_entries(game, out)
            self.assertEqual(error.exception.phase, "catalog_build")
            self.assertEqual(error.exception.changed_files, ["script.pac"])
            self.assertFalse((out / "catalog-signature.json").exists())

    @patch(
        "sora_bilingual.localization.npc_facilities.compile_npc_facilities", new=lambda *_, **__: []
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_fishing_lists",
        new=lambda *_, **__: [],
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_bracer_history",
        new=lambda *_, **__: [],
    )
    def test_resource_change_during_model_compilation_never_publishes_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)
            out = root / "output"
            out.mkdir()
            signature = json.dumps(fingerprint(game), sort_keys=True)
            config = {"primary": "ja", "secondary": "en", "game_language": "en"}
            entries = [{"key": "k", "texts": {"en": "Ready", "ja": "準備完了"}}]

            def change(*_, **__):
                pac.write_bytes(b"different resource generation two")
                return {}

            with (
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_script_identities",
                    side_effect=change,
                ),
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_table_identities",
                    return_value={},
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    load_model(entries, signature, config, out, game=game)
            self.assertEqual(error.exception.phase, "model_publication")
            self.assertFalse(model_path(signature, config, out).exists())
            self.assertFalse((out / "model-preparation.json").exists())

    def test_changed_resources_deny_previous_catalog_before_model_compilation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)
            signature = json.dumps(fingerprint(game), sort_keys=True)
            pac.write_bytes(b"different resource generation two")
            with patch("sora_bilingual.localization.menu_text.MenuTranslator") as translator:
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    load_model(
                        [], signature, {"primary": "ja", "secondary": "en"}, root / "out", game=game
                    )
            self.assertEqual(error.exception.phase, "model_input")
            translator.assert_not_called()

    def test_hot_model_read_does_not_acknowledge_a_mid_read_resource_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)

            def change(*_):
                pac.write_bytes(b"different resource generation two")
                return {"pairs": {}}

            with (
                patch("sora_bilingual.localization.native_catalog.read_model", side_effect=change),
                patch("sora_bilingual.localization.native_catalog.load_entries") as entries,
            ):
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    ready_model(game, {"primary": "ja", "secondary": "en"}, root / "out")
            self.assertEqual(error.exception.phase, "model_read")
            entries.assert_not_called()

    @patch(
        "sora_bilingual.localization.npc_facilities.compile_npc_facilities", new=lambda *_, **__: []
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_fishing_lists",
        new=lambda *_, **__: [],
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_bracer_history",
        new=lambda *_, **__: [],
    )
    def test_changed_resource_generation_explains_a_strict_pointer_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)
            signature = json.dumps(fingerprint(game), sort_keys=True)
            entries = [{"key": "k", "texts": {"en": "Ready", "ja": "準備完了"}}]

            def change(*_, **__):
                pac.write_bytes(b"different resource generation two")
                raise ValueError("Script pointer/catalog disagreement")

            with patch(
                "sora_bilingual.localization.runtime_identity.compile_script_identities",
                side_effect=change,
            ):
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    load_model(
                        entries,
                        signature,
                        {"primary": "ja", "secondary": "en", "game_language": "en"},
                        root / "out",
                        game=game,
                    )
            self.assertEqual(error.exception.phase, "model_compilation")
            self.assertEqual(
                str(error.exception.__context__), "Script pointer/catalog disagreement"
            )

    @patch(
        "sora_bilingual.localization.npc_facilities.compile_npc_facilities", new=lambda *_, **__: []
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_fishing_lists",
        new=lambda *_, **__: [],
    )
    @patch(
        "sora_bilingual.localization.notebook_composition.compile_bracer_history",
        new=lambda *_, **__: [],
    )
    def test_resource_change_during_model_write_is_not_reported_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, pac = self.resource_fixture(root)
            signature = json.dumps(fingerprint(game), sort_keys=True)
            entries = [{"key": "k", "texts": {"en": "Ready", "ja": "準備完了"}}]

            def change(*_):
                pac.write_bytes(b"different resource generation two")

            with (
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_script_identities",
                    return_value={},
                ),
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_table_identities",
                    return_value={},
                ),
                patch(
                    "sora_bilingual.localization.native_catalog.publish_json", side_effect=change
                ) as publish,
            ):
                with self.assertRaisesRegex(
                    ValueError, "resource_changed_during_preparation"
                ) as error:
                    load_model(
                        entries,
                        signature,
                        {"primary": "ja", "secondary": "en", "game_language": "en"},
                        root / "out",
                        game=game,
                    )
            self.assertEqual(error.exception.phase, "model_publication")
            self.assertEqual(
                publish.call_count, 1, "only the stamped cache write, never the ready receipt"
            )

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
                patch("sora_bilingual.localization.catalog_build.build_all") as build,
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
                patch("sora_bilingual.localization.catalog_build.build_all") as build,
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
            game, _pac = self.resource_fixture(out)
            with (
                patch(
                    "sora_bilingual.localization.catalog_build.build_all",
                    return_value={"entries": []},
                ) as build,
            ):
                load_entries(game, out)
                build.assert_called_once()
