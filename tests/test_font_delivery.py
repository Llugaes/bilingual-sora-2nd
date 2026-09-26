import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import lz4.frame

from sora_bilingual.config.locales import LOCALES
from sora_bilingual.fonts import font_delivery
from sora_bilingual.updates.update_installer import relative_file


def _fnt(codepoint: int) -> bytes:
    header = bytearray(40)
    header[32:36] = b"FLTI"
    struct.pack_into("<I", header, 8, 1)
    struct.pack_into("<I", header, 36, 24)
    glyph = bytearray(24)
    struct.pack_into("<I", glyph, 0, codepoint)
    struct.pack_into("<HHHH", glyph, 8, 0, 0, 4, 4)
    return bytes(header + glyph)


def _dds() -> bytes:
    header = bytearray(148)
    header[:4] = b"DDS "
    for offset, value in (
        (4, 124),
        (12, 4),
        (16, 4),
        (20, 16),
        (28, 1),
        (76, 32),
        (128, 98),
        (140, 1),
    ):
        struct.pack_into("<I", header, offset, value)
    header[84:88] = b"DX10"
    return bytes(header) + bytes(16)


def _candidate(root: Path, codepoint: int) -> dict[str, object]:
    fnt = _fnt(codepoint)
    dds = lz4.frame.compress(_dds())
    files = []
    prefixes = {f"asset{locale.font_suffix}" for locale in LOCALES.values()}
    for prefix in sorted(prefixes):
        for tail, data in (("common/font/font_0.fnt", fnt), ("dx11/image/font_0.dds", dds)):
            path = root / prefix / tail
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files.append(
                {
                    "path": f"{prefix}/{tail}",
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
            )
    manifest = {"version": 2, "glyphs": 1, "files": files, "atlases": []}
    (root / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return manifest


class FontDeliveryTests(unittest.TestCase):
    def test_release_accepts_only_the_audited_loader_assets(self):
        self.assertTrue(relative_file("assets/sora2looseload/xinput1_4.dll"))
        self.assertTrue(relative_file("assets/sora2looseload/LICENSE"))
        self.assertTrue(relative_file("assets/sora2looseload/PROVENANCE.md"))
        self.assertTrue(relative_file("assets/font-fallback/font_0.fnt"))
        self.assertTrue(relative_file("assets/font-fallback/font_0.dds"))
        self.assertTrue(relative_file("assets/font-fallback/OFL.txt"))
        self.assertTrue(relative_file("assets/font-fallback/PROVENANCE.md"))
        self.assertFalse(relative_file("assets/sora2looseload/other.dll"))
        self.assertFalse(relative_file("assets/font-fallback/other.dds"))

    def make_game(self, root: Path) -> Path:
        game = root / "game"
        (game / "pac/steam").mkdir(parents=True)
        (game / "sora_2nd.exe").write_bytes(b"fixture")
        for archive in font_delivery._source_archives(game):
            archive.write_bytes(b"A")
        return game

    def prepare(self, game: Path, state: Path):
        def builder(source, output):
            self.assertTrue(source.samefile(game), f"builder source differs: {source} != {game}")
            return _candidate(output, (source / "pac/steam/asset_common_font.pac").read_bytes()[0])

        return font_delivery.prepare(game, root=state, builder=builder)

    def test_cold_prepare_install_adopts_and_reuses_cached_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            candidate = self.prepare(game, state)
            self.assertEqual(candidate, self.prepare(game, state))
            with patch("sora_bilingual.game.hooks.verify_target"):
                installed = font_delivery.ensure(game, candidate, game_running=False, root=state)
                repeated = font_delivery.ensure(game, candidate, game_running=False, root=state)
            self.assertEqual(installed["state"], "installed")
            self.assertEqual(repeated["state"], "healthy")
            self.assertTrue(font_delivery.receipt_path(game, state).is_file())
            self.assertEqual(font_delivery.health(game, candidate, root=state)["state"], "healthy")

    def test_unknown_existing_mod_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            (game / "xinput1_4.dll").write_bytes(b"another mod")
            result = font_delivery.ensure(
                game, self.prepare(game, state), game_running=False, root=state
            )
            self.assertEqual(result["state"], "conflict")
            self.assertEqual((game / "xinput1_4.dll").read_bytes(), b"another mod")

    def test_failed_receipt_write_rolls_back_every_new_game_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            candidate = self.prepare(game, state)
            with (
                patch("sora_bilingual.game.hooks.verify_target"),
                patch(
                    "sora_bilingual.fonts.font_delivery._write_receipt",
                    side_effect=OSError("disk full"),
                ),
                self.assertRaises(OSError),
            ):
                font_delivery.ensure(game, candidate, game_running=False, root=state)
            self.assertFalse((game / "xinput1_4.dll").exists())
            self.assertFalse((game / "asset/common/font/font_0.fnt").exists())

    def test_changed_source_rebuilds_and_replaces_only_receipted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            first = self.prepare(game, state)
            with patch("sora_bilingual.game.hooks.verify_target"):
                font_delivery.ensure(game, first, game_running=False, root=state)
            (game / "pac/steam/asset_common_font.pac").write_bytes(b"B")
            second = self.prepare(game, state)
            self.assertNotEqual(first, second)
            with patch("sora_bilingual.game.hooks.verify_target"):
                result = font_delivery.ensure(game, second, game_running=False, root=state)
            self.assertEqual(result["state"], "installed")

    def test_running_game_stages_without_any_game_file_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            result = font_delivery.ensure(
                game, self.prepare(game, state), game_running=True, root=state
            )
            self.assertEqual(result["state"], "restart-required")
            self.assertTrue(result["staged"])
            self.assertFalse((game / "xinput1_4.dll").exists())

    def test_starting_during_validation_defers_the_write_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            started = [False]

            def validation_completes(_):
                started[0] = True

            with patch("sora_bilingual.game.hooks.verify_target", side_effect=validation_completes):
                result = font_delivery.ensure(
                    game,
                    self.prepare(game, state),
                    game_running=False,
                    is_game_running=lambda: started[0],
                    root=state,
                )
            self.assertEqual(result["state"], "restart-required")
            self.assertFalse((game / "xinput1_4.dll").exists())

    def test_partial_new_file_write_is_rolled_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"

            def partial_write(path, data, register_owned):
                path.parent.mkdir(parents=True, exist_ok=True)
                register_owned()
                path.write_bytes(data[:1])
                raise OSError("disk full")

            with (
                patch("sora_bilingual.game.hooks.verify_target"),
                patch(
                    "sora_bilingual.fonts.font_delivery._create_bytes", side_effect=partial_write
                ),
                self.assertRaises(OSError),
            ):
                font_delivery.ensure(
                    game, self.prepare(game, state), game_running=False, root=state
                )
            self.assertFalse((game / "asset/common/font/font_0.fnt").exists())

    def test_competing_new_file_is_not_claimed_or_removed_on_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            competing_target = game / "asset/common/font/font_0.fnt"

            def competing_create(path, _data, _register_owned):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"third party")
                raise FileExistsError("another mod won the race")

            with (
                patch("sora_bilingual.game.hooks.verify_target"),
                patch(
                    "sora_bilingual.fonts.font_delivery._create_bytes",
                    side_effect=competing_create,
                ),
                self.assertRaises(FileExistsError),
            ):
                font_delivery.ensure(
                    game, self.prepare(game, state), game_running=False, root=state
                )
            self.assertEqual(competing_target.read_bytes(), b"third party")

    def test_receipted_file_changed_after_health_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            first = self.prepare(game, state)
            with patch("sora_bilingual.game.hooks.verify_target"):
                font_delivery.ensure(game, first, game_running=False, root=state)
            (game / "pac/steam/asset_common_font.pac").write_bytes(b"B")
            second = self.prepare(game, state)
            target = game / "asset/common/font/font_0.fnt"
            original_health = font_delivery.health

            def mutate_after_health(*args, **kwargs):
                result = original_health(*args, **kwargs)
                target.write_bytes(b"third party")
                return result

            with (
                patch("sora_bilingual.game.hooks.verify_target"),
                patch("sora_bilingual.fonts.font_delivery.health", side_effect=mutate_after_health),
                self.assertRaises(font_delivery.FontDeliveryError),
            ):
                font_delivery.ensure(game, second, game_running=False, root=state)
            self.assertEqual(target.read_bytes(), b"third party")

    def test_prepare_replaces_a_corrupt_same_fingerprint_cache_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game, state = self.make_game(root), root / "state"
            candidate = self.prepare(game, state)
            (candidate / "manifest.json").write_text("not json", "utf-8")
            repaired = self.prepare(game, state)
            self.assertEqual(repaired, candidate)
            self.assertEqual(font_delivery._candidate_manifest(repaired)[0]["glyphs"], 1)

    def test_candidate_rejects_duplicate_paths_and_divergent_glyph_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._assert_invalid_candidate(
                root, lambda manifest, _: manifest["files"].append(manifest["files"][0])
            )
            self._assert_invalid_candidate(
                root, lambda manifest, _: manifest["files"][0].__setitem__("path", [])
            )

            def different_glyph(manifest, candidate):
                row = next(row for row in manifest["files"] if row["path"].endswith("font_0.fnt"))
                data = _fnt(2)
                path = candidate / row["path"]
                path.write_bytes(data)
                row["sha256"] = hashlib.sha256(data).hexdigest()

            self._assert_invalid_candidate(root, different_glyph)
            self._assert_invalid_candidate(
                root, lambda manifest, _: manifest.__setitem__("glyphs", 2)
            )

    def _assert_invalid_candidate(self, root, mutate):
        candidate = root / "candidate"
        manifest = _candidate(candidate, 1)
        mutate(manifest, candidate)
        (candidate / "manifest.json").write_text(json.dumps(manifest), "utf-8")
        with self.assertRaises(font_delivery.FontDeliveryError):
            font_delivery._candidate_manifest(candidate)

    def test_source_fingerprint_tracks_all_font_build_contract_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = self.make_game(root)
            dependency = root / "builder.py"
            dependency.write_bytes(b"one")
            with patch.object(font_delivery, "BUILD_DEPENDENCIES", (dependency,)):
                first = font_delivery.source_fingerprint(game)
                dependency.write_bytes(b"two")
                second = font_delivery.source_fingerprint(game)
            self.assertNotEqual(first, second)

    def test_source_fingerprint_tracks_the_static_fallback_manifest_and_donor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = self.make_game(root)
            fallback = root / "fallback"
            fallback.write_bytes(b"one")
            with patch(
                "sora_bilingual.fonts.universal_fonts.fallback_dependencies",
                return_value=(fallback,),
            ):
                first = font_delivery.source_fingerprint(game)
                fallback.write_bytes(b"two")
                second = font_delivery.source_fingerprint(game)
            self.assertNotEqual(first, second)

    def test_game_target_rejects_a_path_outside_the_game_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = self.make_game(Path(tmp))
            with self.assertRaises(font_delivery.FontDeliveryError):
                font_delivery._game_target(game, "../outside.dll")


if __name__ == "__main__":
    unittest.main()
