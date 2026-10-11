import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.localization.cache_io import publish_catalog


class CatalogPublicationTests(unittest.TestCase):
    def test_complete_bytes_and_order_at_batch_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            for count in (0, 1, 127, 128, 129, 257):
                catalog = {
                    "version": 1,
                    "languages": ["zh-Hans", "ja", "en"],
                    "entries": [
                        {
                            "key": str(n),
                            "texts": {"zh-Hans": "中\n文", "ja": '𠮷\u0000\\"', "en": "x" * 20000},
                        }
                        for n in range(count)
                    ],
                    "after_entries": {"preserved": True},
                }
                with self.subTest(count=count):
                    publish_catalog(path, catalog)
                    self.assertEqual(
                        path.read_bytes(),
                        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode(),
                    )
                    self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_encoder_and_replace_failure_preserve_previous_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_bytes(b"previous")
            catalog = {"entries": [{"value": n} for n in range(129)]}
            catalog["entries"][-1]["value"] = object()
            with self.assertRaises(TypeError):
                publish_catalog(path, catalog)
            self.assertEqual(path.read_bytes(), b"previous")
            with patch(
                "sora_bilingual.localization.cache_io.replace_file", side_effect=OSError("denied")
            ):
                with self.assertRaisesRegex(OSError, "denied"):
                    publish_catalog(path, {"entries": []})
            self.assertEqual(path.read_bytes(), b"previous")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
