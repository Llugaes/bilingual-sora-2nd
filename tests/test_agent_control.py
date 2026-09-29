import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sora_bilingual.game.agent_control import reconnect


class AgentIdentityTests(unittest.TestCase):
    def test_matching_unreachable_agent_never_allows_new_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.json"
            exe = Path(tmp) / "sora_2nd.exe"
            record = dict(pid=42, created=123, exe=str(exe.resolve()), protocol=1)
            path.write_text(json.dumps(record), "utf8")
            with (
                patch("sora_bilingual.game.agent_control.process_identity", return_value=123),
                patch(
                    "sora_bilingual.game.agent_control.AgentClient",
                    side_effect=OSError("unreachable"),
                ) as client,
            ):
                with self.assertRaisesRegex(OSError, "unreachable"):
                    reconnect(42, exe, path)
                client.assert_called_once_with(record)

    def test_pid_reuse_ignores_old_endpoint_and_protocol_mismatch_rejects_reconnect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.json"
            exe = Path(tmp) / "sora_2nd.exe"
            record = dict(pid=42, created=123, exe=str(exe.resolve()), protocol=2)
            path.write_text(json.dumps(record), "utf8")
            with (
                patch("sora_bilingual.game.agent_control.process_identity", return_value=124),
                patch("sora_bilingual.game.agent_control.AgentClient") as client,
            ):
                self.assertIsNone(reconnect(42, exe, path))
                client.assert_not_called()
            with (
                patch("sora_bilingual.game.agent_control.process_identity", return_value=123),
                patch("sora_bilingual.game.agent_control.AgentClient") as client,
            ):
                with self.assertRaisesRegex(ValueError, "不同版本"):
                    reconnect(42, exe, path)
                client.assert_not_called()
