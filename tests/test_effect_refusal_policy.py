"""Shared refusal data must remain identical in Python and embedded V8 code."""

import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from sora_bilingual.localization.menu_text import EFFECT_REFUSAL_POLICY, MenuTranslator
from sora_bilingual.localization.effect_refusal_policy import (
    EFFECT_REFUSAL_POLICY as CANONICAL_POLICY,
)
from sora_bilingual.localization import native_catalog
from sora_bilingual.updates.tool_updates import GROUPS
from sora_bilingual.updates.update_installer import relative_file
from tools.generate_effect_refusal_policy import POLICY, RUNTIME, generate

ROOT = Path(__file__).resolve().parents[1]


class EffectRefusalPolicyTests(unittest.TestCase):
    def test_policy_uses_the_legacy_updater_nested_source_contract(self):
        # 1.0.1 accepts nested Python source files, while its JSON exceptions
        # are fixed. This regression must run without a checkout or Git tags.
        name = POLICY.relative_to(ROOT).as_posix()
        self.assertEqual(POLICY.suffix, ".py")
        self.assertTrue(relative_file(name))
        for rejected in (
            "sora_bilingual/localization/effect_refusal_policy.json",
            "sora_bilingual/localization/other.json",
            "sora_bilingual/game/effect_refusal_policy.json",
        ):
            self.assertFalse(relative_file(rejected), rejected)

    def test_policy_preserves_the_recorded_rule_order_and_values(self):
        reasons = (
            "missing_native_join_contract",
            "unassociated_effect_unit",
            "partial_effect_members",
            "hard_line_or_native_ruby",
            "invalid_separator_style",
            "member_budget",
            "empty_effect_member",
            "partition_budget",
            "different_partition_targets",
            "invalid_effect_parameter",
            "unproven_effect_parameter",
            "unproven_standalone_constructor",
            "unproven_direction_parameter",
            "conflicting_effect_member",
            "unsupported_effect_controls",
            "item_help_header_missing_record_body",
        )
        self.assertEqual(tuple(EFFECT_REFUSAL_POLICY), reasons)
        self.assertEqual(tuple(EFFECT_REFUSAL_POLICY.values()), ("unproved",) * 3 + ("hard",) * 13)

    def test_generated_policy_and_unknown_reason_default(self):
        self.assertTrue(generate(check=True))
        canonical = CANONICAL_POLICY
        self.assertIs(EFFECT_REFUSAL_POLICY, canonical)
        tr = MenuTranslator([], "ja", "zh-Hans", "en")
        tr.effect_unit_failures["unknown"] = "future_reason"
        self.assertTrue(tr._effect_rejected("unknown"))
        script = """
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const r=new RuntimeText({});r.effectUnitFailures.set('unknown','future_reason');
process.stdout.write(JSON.stringify({policy:RuntimeText.effectRefusalPolicy,hard:r.effectRejected('unknown')}));
"""
        output = subprocess.run(
            ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, check=True
        )
        self.assertEqual(json.loads(output.stdout), {"policy": canonical, "hard": True})

    def test_check_rejects_stale_embed_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "runtime_text.js"
            source = RUNTIME.read_text("utf-8").replace(
                '"missing_native_join_contract":"unproved"',
                '"missing_native_join_contract":"hard"',
            )
            target.write_text(source, "utf-8")
            self.assertFalse(generate(runtime_path=target, check=True))
            self.assertEqual(target.read_text("utf-8"), source)
            self.assertTrue(generate(runtime_path=target))
            self.assertTrue(generate(runtime_path=target, check=True))

    def test_data_is_registered_in_package_and_model_fingerprint(self):
        name = POLICY.relative_to(ROOT).as_posix()
        manifest = json.loads((ROOT / "release-files.json").read_text("utf-8"))
        self.assertIn(name, manifest)
        self.assertIn(name, GROUPS["catalog"])
        self.assertTrue(relative_file(name))
        for rejected in (
            "sora_bilingual/localization/other.json",
            "sora_bilingual/game/effect_refusal_policy.json",
            "sora_bilingual/localization/../effect_refusal_policy.json",
            "../sora_bilingual/localization/effect_refusal_policy.json",
        ):
            self.assertFalse(relative_file(rejected), rejected)
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        self.assertNotIn(
            "effect_refusal_policy.json",
            project["tool"]["setuptools"]["package-data"]["sora_bilingual.localization"],
        )
        original = Path.read_bytes

        def changed(path):
            data = original(path)
            return data + b" " if path == POLICY else data

        before = native_catalog._code_fingerprint()
        with patch.object(Path, "read_bytes", changed):
            after = native_catalog._code_fingerprint()
        self.assertNotEqual(before["code"], after["code"])
        self.assertEqual(before["catalog_code"], after["catalog_code"])
