import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sora_bilingual.paths import build_label
from sora_bilingual.updates.update_service import UpdateService


class DevelopmentUpdateIsolationTests(unittest.TestCase):
    def test_packaged_dev_with_receipt_refuses_stable_upgrade_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "generated").mkdir()
            (root / "distribution.json").write_text(
                json.dumps({"version": "0.4.2", "repository": "a/b"}), "utf-8"
            )
            (root / "installed-manifest.json").write_text("{}", "utf-8")
            (root / "generated/development-version.txt").write_text("0.4.2\n", "utf-8")
            (root / "dev-manifest.json").write_text('{"display_version":"1.0.0-dev5-r15"}', "utf-8")
            client = Mock()
            service = UpdateService(root, client=client)
            with patch("sora_bilingual.updates.update_service.install") as install:
                for tag in ("v0.4.4", "v0.4.1"):
                    service._install({"tag_name": tag})
                install.assert_not_called()
            client.release.assert_not_called()
            client.download.assert_not_called()
            self.assertFalse(service.installed)
            self.assertEqual(build_label(root), "DEV 1.0.0-dev5-r15")
            self.assertIn("开发目录", service.message)
