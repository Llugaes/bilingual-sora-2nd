"""Replay the native FORMAT8 boundary inside resource-anchored details."""

import itertools
import json
from pathlib import Path
import re
import subprocess
import unittest

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator


ROOT = Path(__file__).resolve().parents[1]
# Original t_text/t_itemhelp strings. FORMAT8 is distinct from the LINK used
# inside typed aggregates: English/French/German/Spanish use comma-space here.
SEPARATOR = {
    language: ", " if language in ("en", "fr", "de", "es") else "／" for language in LANGUAGES
}
NAMES = [
    dict(zip(LANGUAGES, values))
    for values in (
        (
            "側面特効",
            "Side Attack Bonus",
            "侧面特效",
            "側面特效",
            "측면 특효",
            "Bonus d'attaque de côté",
            "Bonus für Seitenangriff",
            "Bonus de ataque lateral",
        ),
        (
            "背面特効",
            "Back Attack Bonus",
            "背面特效",
            "背面特效",
            "후방 특효",
            "Bonus d'attaque de dos",
            "Bonus für Angriff von hinten",
            "Bonus de ataque trasero",
        ),
        (
            "必中",
            "Sure Hit",
            "必中",
            "必中",
            "반드시 명중",
            "Frappe garantie",
            "Sicherer Treffer",
            "Golpe garantizado",
        ),
    )
]


def fixture():
    entries = [
        {"key": "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8", "texts": SEPARATOR},
        {"key": "table/t_text.tbl/TXT_ITEM_HELP_HITTING", "texts": NAMES[2]},
        {"key": "table/t_itemhelp.tbl/SkillEffectHelpData/side/name", "texts": NAMES[0]},
        {"key": "table/t_itemhelp.tbl/SkillEffectHelpData/back/name", "texts": NAMES[1]},
        {
            "key": "table/t_skill.tbl/skill/description",
            "texts": {l: "Description " + l for l in LANGUAGES},
        },
        # This real script fragment must never become a reusable comma pair.
        {
            "key": "script/tutorial/comma",
            "texts": {"en": ",", "ja": "をセットすると、", "zh-Hans": "后，"},
        },
    ]
    return entries


def phrase(language, members, *, trailing=False):
    separator = SEPARATOR[language]
    return (
        separator
        + separator.join(NAMES[index][language] for index in members)
        + (separator if trailing else "")
    )


class DetailEffectListTests(unittest.TestCase):
    def test_inline_icon_stays_inside_the_complete_member(self):
        entries = fixture() + [
            {
                "key": "table/t_itemhelp.tbl/generated/typed/turn_stat_inline_icon/test",
                "texts": {"ja": "%dターンSTR<I270>", "en": "STR<I270> (%d turns)"},
                "item_help_contract": {"family": "turn_stat_inline_icon"},
                "detail_authority": True,
                "detail_only": True,
            }
        ]
        translator = MenuTranslator(entries, "ja", "en", "ja")
        source = "<c698>／側面特効／30ターンSTR<I270>／背面特効</C>\n<C0><C9>Description ja"
        expected = "<c698>, Side Attack Bonus, STR<I270> (30 turns), Back Attack Bonus</C>\n<C0><C9>Description en"
        self.assertEqual(translator.translate(source, "primary"), source)
        self.assertEqual(translator.translate(source, "secondary"), expected)
        self.assertEqual(expected.count("<I270>"), 1)
        self.assertIsNone(translator.details._detail_join_pair("／30ターンSTR<I999>"))
        runner = """
const data=JSON.parse(require('fs').readFileSync(0,'utf8'));
const assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const r=new RuntimeText(data.model);
assert.equal(r.translate(data.source,'secondary'),data.expected);
assert.deepEqual(r.render(data.source),data.render);
"""
        subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                {
                    "model": translator.runtime_model(),
                    "source": source,
                    "expected": expected,
                    "render": translator.render(source),
                }
            ).encode(),
            cwd=ROOT,
            check=True,
        )

    def test_complete_typed_member_keeps_its_official_wording(self):
        entries = fixture() + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/revive/name",
                "texts": {"ja": "復活", "en": "Revive"},
            },
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/recovery/format",
                "texts": {"ja": "HP%d％回復", "en": "Recover %d%% HP"},
            },
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/freeform/format",
                "texts": {"ja": "%s回復", "en": "Recover %s"},
            },
            {
                "key": "table/t_itemhelp.tbl/generated/typed/revive_recovery/120/test",
                "texts": {"ja": "復活／HP%d％回復", "en": "Revive, Heal %d%% HP"},
                "item_help_contract": {"family": "revive_recovery"},
                "detail_authority": True,
                "detail_only": True,
            },
        ]
        translator = MenuTranslator(entries, "ja", "en", "ja")
        source = "<c698>／復活／HP30％回復／側面特効</C>\n<C0>Description ja"
        expected = "<c698>, Revive, Heal 30% HP, Side Attack Bonus</C>\n<C0>Description en"
        self.assertEqual(translator.translate(source, "secondary"), expected)
        reverse = MenuTranslator(entries, "en", "ja", "en")
        self.assertEqual(reverse.translate(expected, "secondary"), source)
        runner = """
const fs=require('fs'),assert=require('assert/strict');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
for(const row of JSON.parse(fs.readFileSync(0,'utf8'))) {
 const r=new RuntimeText(row.model);
 assert.equal(r.translate(row.source,'secondary'),row.expected);
 assert.deepEqual(r.render(row.source),row.render);
}
"""
        subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                [
                    {
                        "model": translator.runtime_model(),
                        "source": source,
                        "expected": expected,
                        "render": translator.render(source),
                    },
                    {
                        "model": reverse.runtime_model(),
                        "source": expected,
                        "expected": source,
                        "render": reverse.render(expected),
                    },
                ]
            ).encode(),
            cwd=ROOT,
            check=True,
        )

    def test_conflicting_or_incomplete_effect_identity_is_not_reused(self):
        conflict = {
            "key": "table/t_itemhelp.tbl/generated/other-label",
            "texts": {"en": "Side Attack Bonus", "ja": "Different official label"},
            "detail_only": True,
            "detail_authority": True,
        }
        incomplete = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/incomplete/name",
            "texts": {"en": "Side Attack Bonus"},
        }
        for added in (conflict, incomplete):
            translator = MenuTranslator(fixture() + [added], "en", "ja", "en")
            self.assertIsNone(translator.details._detail_join_pair(", Side Attack Bonus"))
            text = "<c698>, Side Attack Bonus</C>\n<C0>Description en"
            self.assertEqual(
                translator.translate(text, "secondary"),
                "<c698>, Side Attack Bonus</C>\n<C0>Description ja",
            )
        escaped = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/escaped/turns",
            "texts": {"en": "90%% chance", "ja": "90%の確率"},
        }
        translator = MenuTranslator(fixture() + [escaped], "ja", "en", "ja")
        self.assertIsNone(translator.details._detail_join_pair("／90%の確率"))
        incompatible = {
            "key": "table/t_itemhelp.tbl/SkillEffectHelpData/incompatible/format",
            "texts": {"en": "Resist", "ja": "防止%d％"},
        }
        translator = MenuTranslator(fixture() + [incompatible], "en", "ja", "en")
        self.assertIsNone(translator.details._detail_join_pair(", Resist"))

    def test_rejected_numeric_template_cannot_reenter_through_a_wider_one(self):
        entries = fixture() + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/narrow/format",
                "texts": {"en": "Power+%d", "ja": "出力＋%d"},
            },
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/wide/format",
                "texts": {"en": "Power%d", "ja": "力%d"},
            },
            {
                "key": "table/t_itemhelp.tbl/generated/status-authority",
                "texts": {"en": "Power+%d", "ja": "力+%d"},
                "detail_only": True,
                "detail_authority": True,
            },
        ]
        translator = MenuTranslator(entries, "en", "ja", "en")
        self.assertIsNone(translator.details._detail_join_pair(", Power+30"))
        self.assertIsNone(translator.details._detail_join_pair(", Power+30, Side Attack Bonus"))
        text = "<c698>, Power+30, Side Attack Bonus</C>\n<C0>Description en"
        expected = "<c698>, Power+30, Side Attack Bonus</C>\n<C0>Description ja"
        self.assertEqual(translator.translate(text, "secondary"), expected)
        runner = """
const data=JSON.parse(require('fs').readFileSync(0,'utf8'));
const assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
assert.equal(new RuntimeText(data.model).translate(data.source,'secondary'),data.expected);
"""
        subprocess.run(
            ["node", "-e", runner],
            input=json.dumps(
                {"model": translator.runtime_model(), "source": text, "expected": expected}
            ).encode(),
            cwd=ROOT,
            check=True,
        )

    def test_numeric_effects_brackets_and_non_effect_header_roles(self):
        entries = fixture() + [
            {
                "key": "table/t_itemhelp.tbl/SkillEffectHelpData/cp/name",
                "texts": {l: "CP+%d" for l in LANGUAGES},
            },
            {
                "key": "table/t_itemhelp.tbl/SkillRangeHelpData/single/label",
                "texts": {l: "Range " + l for l in LANGUAGES},
            },
        ]
        translator = MenuTranslator(entries, "en", "ja", "en")
        source = "<c698>[CP+30, Side Attack Bonus, Back Attack Bonus]</C>\n<C0>Description en"
        expected = "<c698>[CP+30／側面特効／背面特効]</C>\n<C0>Description ja"
        self.assertEqual(translator.translate(source, "secondary"), expected)
        reverse = MenuTranslator(entries, "ja", "en", "ja")
        self.assertEqual(reverse.translate(expected, "secondary"), source)
        header = "<c698>Range ja／側面特効</C>\n<C0>Description ja"
        self.assertEqual(
            reverse.translate(header, "secondary"),
            "<c698>Range en／Side Attack Bonus</C>\n<C0>Description en",
        )

    def test_all_language_pairs_lists_and_final_annotation(self):
        batches = []
        for source, primary, secondary in itertools.product(LANGUAGES, repeat=3):
            translator = MenuTranslator(fixture(), primary, secondary, source)
            cases = []
            for members in ((0,), (1,), (2,), (0, 1), (2, 0, 1), (1, 2, 0, 2, 1)):
                for trailing in (False, True):
                    text = (
                        "<c698>"
                        + phrase(source, members, trailing=trailing)
                        + "</C>\n<C0>Description "
                        + source
                    )
                    expected = [
                        "<c698>"
                        + phrase(language, members, trailing=trailing)
                        + "</C>\n<C0>Description "
                        + language
                        for language in (primary, secondary)
                    ]
                    self.assertEqual(translator.translate(text, "primary"), expected[0])
                    self.assertEqual(translator.translate(text, "secondary"), expected[1])
                    plan = translator.render(text)
                    if primary != secondary:
                        payload = plan["text"] + "".join(layer["text"] for layer in plan["layers"])
                        payload = re.sub(r"</R([^<>]*)>", r"\1", payload)
                        payload = re.sub(r"<[^<>]*>", "", payload)
                        for index in members:
                            self.assertIn(NAMES[index][secondary], payload)
                    cases.append(
                        {
                            "source": text,
                            "primary": expected[0],
                            "secondary": expected[1],
                            "render": plan,
                        }
                    )
            batches.append({"model": translator.runtime_model(), "cases": cases})
        runner = """
const fs=require('fs'),assert=require('assert/strict');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
for(const batch of JSON.parse(fs.readFileSync(0,'utf8'))) {
 const r=new RuntimeText(batch.model);
 for(const c of batch.cases) {
  assert.equal(r.translate(c.source,'primary'),c.primary);
  assert.equal(r.translate(c.source,'secondary'),c.secondary);
  assert.deepEqual(r.render(c.source,'annotation'),c.render);
 }
}
"""
        subprocess.run(
            ["node", "-e", runner], input=json.dumps(batches).encode(), cwd=ROOT, check=True
        )

    def test_scope_unknown_members_and_punctuation_stay_closed(self):
        translator = MenuTranslator(fixture(), "en", "ja", "en")
        for text in (
            ", Side Attack Bonus",
            "Side Attack Bonus, Back Attack Bonus",
            ", ,",
            "Slot, Unknown",
        ):
            self.assertEqual(translator.translate(text, "secondary"), text)
        for text in (
            ", Unknown, Side Attack Bonus",
            ", Side Attack Bonus, Unknown",
            ", , Side Attack Bonus",
        ):
            anchored = "<c698>" + text + "</C>\n<C0>Description en"
            self.assertEqual(
                translator.translate(anchored, "secondary").split("</C>")[0], "<c698>" + text
            )
        self.assertEqual(translator.details.translate(",", "secondary"), ",")
        self.assertEqual(translator.component(",", "secondary"), ",")

    def test_native_boundary_padding_keeps_primary_bytes(self):
        translator = MenuTranslator(fixture(), "en", "ja", "en")
        source = "<c698>, Sure Hit,</C>\n<C0>Description en"
        self.assertEqual(translator.translate(source, "primary"), source)
        self.assertEqual(
            translator.translate(source, "secondary"), "<c698>／必中／</C>\n<C0>Description ja"
        )


if __name__ == "__main__":
    unittest.main()
