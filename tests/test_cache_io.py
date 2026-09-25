from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sora_bilingual.localization.cache_io import publish_json, read_model
from sora_bilingual.localization.native_catalog import load_model, model_path


class CacheTests(unittest.TestCase):
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
