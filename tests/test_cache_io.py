from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from sora_bilingual.localization.cache_io import publish_json, read_model
from sora_bilingual.localization.native_catalog import fingerprint, load_model, model_path
from sora_bilingual.localization.menu_text import MenuTranslator


class CacheTests(unittest.TestCase):
    def test_three_fresh_processes_reuse_compiler_output_without_resource_work(self):
        config = {"primary": "en", "secondary": "ja", "game_language": "en"}
        model = MenuTranslator(
            [
                {"texts": {"en": "<C4>", "ja": "<C2>"}},
                {"texts": {"en": "Ready", "ja": "準備完了"}},
            ],
            "en",
            "ja",
            "en",
        ).runtime_model()
        model.update(script_identities={}, table_identities={})
        code = """
import sys
from pathlib import Path
from unittest.mock import patch
from sora_bilingual.localization.native_catalog import ready_model
with patch('sora_bilingual.localization.native_catalog.load_entries',
           side_effect=AssertionError('warm start rebuilt resources')):
    model, _, entries = ready_model(Path(sys.argv[1]),
        {'primary':'en','secondary':'ja','game_language':'en'}, Path(sys.argv[1]))
    assert entries is None
    assert model['pairs']['Ready'] == ['Ready', '準備完了']
    assert model['plain_pairs']['<C4>'] == ['', '']
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = model_path(json.dumps(fingerprint(tmp), sort_keys=True), config, tmp)
            publish_json(path, model)
            before = path.stat().st_mtime_ns
            for launch in range(3):
                with self.subTest(launch=launch):
                    subprocess.run(
                        [sys.executable, "-X", "utf8", "-c", code, tmp],
                        capture_output=True,
                        check=True,
                        timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_compiled_format_only_pairs_survive_cache_roundtrip(self):
        entries = [
            {"texts": {"en": "<C4>", "ja": "<C2>"}},
            {"texts": {"en": "Ready", "ja": "準備完了"}},
        ]
        model = MenuTranslator(entries, "en", "ja", "en").runtime_model()
        model.update(script_identities={}, table_identities={})
        self.assertEqual(model["plain_pairs"]["<C4>"], ("", ""))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            publish_json(path, model)
            self.assertEqual(read_model(path), json.loads(path.read_text("utf-8")))

    def test_cache_still_rejects_malformed_pairs(self):
        model = MenuTranslator(
            [{"texts": {"en": "Ready", "ja": "準備完了"}}], "en", "ja", "en"
        ).runtime_model()
        model.update(script_identities={}, table_identities={})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            for key in ("pairs", "plain_pairs"):
                for invalid in (None, ["one"], ["a", "b", "c"], ["a", None], [4, "b"]):
                    with self.subTest(key=key, invalid=invalid):
                        broken = {**model, key: {"Ready": invalid}}
                        publish_json(path, broken)
                        self.assertIsNone(read_model(path))
            for pair in (["", "準備完了"], ["Ready", "  "]):
                publish_json(path, {**model, "pairs": {"Ready": pair}})
                self.assertIsNone(read_model(path))

    def test_unavailable_locale_is_not_acknowledged_as_a_successful_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"primary": "fr", "secondary": "de", "game_language": "es"}
            with self.assertRaisesRegex(ValueError, "可用配对"):
                load_model(
                    [{"texts": {"fr": "Texte", "es": "Texto"}}], "sig", config, tmp, game="unused"
                )
            self.assertFalse(model_path("sig", config, tmp).exists())

    def test_concurrent_publishers_never_share_a_temporary_file_or_truncate_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(
                    pool.map(
                        lambda i: publish_json(path, {"n": i, "values": [i] * 1000}), range(12)
                    )
                )
            result = json.loads(path.read_text())
            self.assertEqual(result["values"], [result["n"]] * 1000)
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_broken_model_cache_rebuilds_from_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"primary": "fr", "secondary": "de", "game_language": "es"}
            path = model_path("sig", config, tmp)
            path.write_text("{")
            entries = [{"texts": {"fr": "Texte", "de": "Text", "es": "Texto"}}]
            with (
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_script_identities",
                    return_value={},
                ),
                patch(
                    "sora_bilingual.localization.runtime_identity.compile_table_identities",
                    return_value={},
                ),
            ):
                value = load_model(entries, "sig", config, tmp, game="unused")
            self.assertEqual(value["pairs"]["Texto"], ("Texte", "Text"))
            self.assertEqual(read_model(path)["pairs"]["Texto"], ["Texte", "Text"])
            for invalid in ("[]", '{"pairs":{}}', '{"pairs":null}'):
                path.write_text(invalid)
                self.assertIsNone(read_model(path))
