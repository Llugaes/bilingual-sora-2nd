"""Explicit member decisions retain the legacy resolver's ordered history."""

import json
from pathlib import Path
import subprocess
import unittest

from sora_bilingual.localization.menu_text import MenuTranslator
from effect_member_sequence_cases import evaluate, inputs

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures/effect-member-sequence-baseline.json"


class EffectMemberResultTests(unittest.TestCase):
    def test_current_decision_is_distinct_from_history(self):
        entries, _ = inputs()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en").details
        self.assertIsNone(tr.effect_units("A, B, C"))
        match = tr._effect_unit_result("A, B, C")
        self.assertEqual(match.status, "Match")
        self.assertEqual(match.scope, "effect_member")
        self.assertIsNone(match.reason)
        self.assertEqual(match.compat_failure_after, "different_partition_targets")
        self.assertEqual(match.unit, tr._effect_unit("A, B, C"))
        tr.effect_unit_failures["Unknown"] = "invalid_effect_parameter"
        no_match = tr._effect_unit_result("Unknown")
        self.assertEqual(no_match.status, "NoMatch")
        self.assertIsNone(no_match.unit)
        self.assertIsNone(no_match.reason)
        self.assertEqual(no_match.compat_failure_after, "invalid_effect_parameter")
        rejection = tr._effect_unit_result("Blind 2147483648%")
        self.assertEqual(rejection.status, "Reject")
        self.assertEqual(rejection.reason, "invalid_effect_parameter")
        self.assertEqual(rejection.compat_failure_after, rejection.reason)

    def test_recursive_match_precedence_and_frame_history(self):
        entries, _ = inputs()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en").details
        joined = "<c698>HP Regen</C>"
        tr.effect_unit_failures[joined] = "conflicting_effect_member"
        match = tr._effect_unit_result("<c698>HP </C><c698>Regen</C>")
        self.assertEqual(match.status, "Match")
        self.assertIsNone(match.reason)
        self.assertIsNone(match.compat_failure_after)
        self.assertEqual(tr.effect_unit_failures[joined], "conflicting_effect_member")
        tr.effect_unit_failures["Blind 30%"] = "unproven_direction_parameter"
        self.assertEqual(tr._effect_unit_result("Blind 30%", True).status, "Match")
        rejected = tr._effect_unit_result("<C2>Blind 30%</C>")
        self.assertEqual(rejected.status, "Reject")
        self.assertEqual(rejected.reason, "unproven_direction_parameter")

    def test_composer_consumes_decisions_without_legacy_wrapper(self):
        entries, _ = inputs()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en").details

        def unexpected(*args):
            raise AssertionError("composer called compatibility wrapper")

        tr._effect_unit = unexpected
        self.assertIsNotNone(tr.effect_units("HP Regen, CP Regen"))
        self.assertIsNotNone(tr.effect_line_units("[HP Regen] - CP Regen", True))

    def test_frozen_legacy_sequences_and_resident_parity(self):
        expected = json.loads(FIXTURE.read_text("utf-8"))
        self.assertEqual(json.loads(json.dumps(evaluate(MenuTranslator))), expected["python"])
        entries, cases = inputs()
        model = MenuTranslator(entries, "ja", "zh-Hans", "en").runtime_model()
        run = subprocess.run(
            ["node", "tests/check_effect_member_sequences.js"],
            cwd=ROOT,
            check=True,
            input=json.dumps({"model": model, "cases": cases}),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(json.loads(run.stdout), expected["javascript"])

    def test_owned_units_do_not_call_member_parser(self):
        entries, _ = inputs()
        tr = MenuTranslator(entries, "ja", "zh-Hans", "en").details
        owned = {"source": "Owned", "pair": ("J", "Z"), "semantic_ids": ["owned"]}

        def unexpected(*args):
            raise AssertionError("owned unit reparsed")

        tr._effect_unit_result = unexpected
        self.assertEqual(tr.effect_units("Owned", owned_units={"Owned": owned}), [owned])
        script = """
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const r=new RuntimeText({detail_join:[', ','、','，']});
r.effectUnitResult=()=>{throw Error('owned unit reparsed');};
const unit={source:'Owned',pair:['J','Z'],semantic_ids:['owned']};
require('node:assert/strict').deepEqual(r.effectUnits('Owned',false,'',null,{Owned:unit}),[unit]);
"""
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True)
