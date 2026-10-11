import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.localization import model_worker, native_catalog, model_wire
from sora_bilingual.localization.cache_io import publish_json
from sora_bilingual.localization.menu_text import MenuTranslator


class PreparedReuseTests(unittest.TestCase):
    def prepare(self, root):
        config = {"primary": "en", "secondary": "ja", "game_language": "en"}
        request = {"game": str(root), "config": config}
        config = model_worker.normalize_config(config)
        signature = json.dumps(native_catalog.fingerprint(root), sort_keys=True)
        source = native_catalog.model_path(signature, config, root)
        model = MenuTranslator(
            [{"texts": {"en": "Ready", "ja": "準備"}}], "en", "ja", "en"
        ).runtime_model()
        model.update(script_identities={}, table_identities={}, coverage={"source_records": 1})
        publish_json(source, model)
        result = model_worker.prepare_request(request, root)
        return request, source, result

    def test_warm_request_reuses_verified_transport_without_loading_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _, first = self.prepare(root)
            with patch.object(
                model_worker, "ready_model", side_effect=AssertionError("model expanded")
            ):
                self.assertEqual(model_worker.prepare_request(request, root), first)

    def test_same_size_corruption_of_either_file_rejects_fast_path(self):
        for corrupt_wire in (False, True):
            with self.subTest(wire=corrupt_wire), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                request, source, _ = self.prepare(root)
                target = model_wire.wire_path(source) if corrupt_wire else source
                before = target.stat()
                content = bytearray(target.read_bytes())
                content[0] ^= 1
                target.write_bytes(content)
                os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
                with patch.object(
                    model_worker, "ready_model", side_effect=RuntimeError("fallback")
                ):
                    with self.assertRaisesRegex(RuntimeError, "fallback"):
                        model_worker.prepare_request(request, root)

    def test_warm_resource_change_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _, _ = self.prepare(root)
            with patch.object(
                native_catalog,
                "_resource_snapshot",
                side_effect=[[], [("script.pac", 1, 2, "changed")]],
            ):
                with self.assertRaises(native_catalog.ResourceChangedError):
                    model_worker.prepare_request(request, root)

    def test_denied_model_is_not_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, source, _ = self.prepare(root)
            original = Path.open

            def denied(path, *args, **kwargs):
                if path == source:
                    raise PermissionError("source denied")
                return original(path, *args, **kwargs)

            with (
                patch.object(Path, "open", denied),
                patch.object(model_worker, "ready_model") as rebuild,
            ):
                with self.assertRaisesRegex(PermissionError, "source denied"):
                    model_worker.prepare_request(request, root)
                rebuild.assert_not_called()

    def test_old_or_malformed_summary_falls_back(self):
        for summary in (None, [], {"coverage": {}, "pair_count": -1}):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                request, source, _ = self.prepare(root)
                wire = model_wire.wire_path(source)
                stamp = wire.with_name(wire.name + ".stamp.json")
                saved = json.loads(stamp.read_text("utf-8"))
                if summary is None:
                    saved.pop("summary")
                else:
                    saved["summary"] = summary
                publish_json(stamp, saved)
                with patch.object(
                    model_worker, "ready_model", side_effect=RuntimeError("fallback")
                ):
                    with self.assertRaisesRegex(RuntimeError, "fallback"):
                        model_worker.prepare_request(request, root)
