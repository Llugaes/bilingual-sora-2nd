import unittest
from unittest.mock import patch

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.dynamic_producers import build_dynamic_entries
from sora_bilingual.localization.resources import Called, Function, Script


def _panel(prefix, opcode, suffix):
    return Called(
        None,
        3,
        (
            ("int", 5),
            ("int", 8),
            ("int", 65535),
            ("int", 16),
            ("string", prefix),
            ("int", opcode),
            ("var", None),
            ("string", suffix),
        ),
    )


def _function(name, calls):
    return Function(name, 0, (), tuple(calls), (), ())


def _scripts(*, bad_bp=None, item_call=None):
    result = {}
    for language in LANGUAGES:
        bp = _panel("BP <C2>", 18, "<C0>!")
        if language == bad_bp:
            bp = _panel("BP <C2>", 23, "<C0>!")
        rest_opcode = 23 if language in {"ja", "zh-Hans", "zh-Hant", "ko"} else 18
        system = Script(
            {
                "OnQuestAddBP": _function(
                    "OnQuestAddBP",
                    (Called(None, 0, ()), Called(None, 0, ()), Called(None, 0, ()), bp),
                ),
                "RestShopProcess": _function(
                    "RestShopProcess",
                    (
                        Called(None, 0, ()),
                        Called(None, 0, ()),
                        Called(None, 0, ()),
                        _panel("Pay ", rest_opcode, " mira"),
                    ),
                ),
                "UnLockRecipe": _function(
                    "UnLockRecipe",
                    (Called(None, 0, ()), Called(None, 0, ()), _panel("Recipe ", 17, "!")),
                ),
            }
        )
        paths = {"script/scena/system.dat": system}
        if item_call:
            paths["script/scena/reward.dat"] = Script({"Reward": _function("Reward", (item_call,))})
        result[language] = paths
    return result


def _items():
    return {
        language: {2100: (f"{language} dish", 787457), 4202: (f"{language} quartz", 265)}
        for language in LANGUAGES
    }


def _build(scripts, items):
    with (
        patch("sora_bilingual.localization.dynamic_producers._read_scripts", return_value=scripts),
        patch("sora_bilingual.localization.dynamic_producers._read_item_rows", return_value=items),
    ):
        return build_dynamic_entries("unused", [{"texts": {"zh-Hans": "wrong accepted catalog"}}])


class DynamicProducerTests(unittest.TestCase):
    def test_compiles_only_full_typed_numeric_and_exact_recipe_entries(self):
        entries, audit = _build(_scripts(), _items())
        by_family = {
            entry["dynamic_producer"]["family"]: entry
            for entry in entries
            if "dynamic_producer" in entry
        }
        self.assertEqual(by_family["on_quest_add_bp"]["texts"]["zh-Hans"], "BP <C2>%d<C0>!")
        self.assertEqual(
            by_family["rest_shop_process"]["dynamic_producer"]["numbers"]["ja"], ["fullwidth"]
        )
        self.assertEqual(
            by_family["rest_shop_process"]["dynamic_producer"]["numbers"]["en"], ["ascii"]
        )
        recipe = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "unlock_recipe"
        )
        self.assertEqual(recipe["texts"]["zh-Hans"], "Recipe <C0><I%d></C><C5>zh-Hans dish</C>!")
        self.assertNotIn("%s", recipe["texts"]["zh-Hans"])
        self.assertTrue(recipe["dynamic_producer"]["dynamic_icon"])
        self.assertEqual(audit["counters"]["recipe_items_emitted"], 1)

    def test_rejects_unknown_bp_opcode_only_for_that_locale(self):
        entries, audit = _build(_scripts(bad_bp="zh-Hans"), _items())
        bp = next(
            entry
            for entry in entries
            if entry.get("dynamic_producer", {}).get("family") == "on_quest_add_bp"
        )
        self.assertNotIn("zh-Hans", bp["texts"])
        self.assertIn("ja", bp["texts"])
        self.assertTrue(
            any(
                item["reason"] == "producer_rejected" and item.get("language") == "zh-Hans"
                for item in audit["diagnostics"]
            )
        )

    def test_compiles_static_item_message_by_raw_item_id_not_existing_catalog_text(self):
        item_call = Called(
            "ITEM_ADD_MESSAGE2_EV",
            0,
            (("int", 4202), ("string", "Received "), ("string", "."), ("int", 2)),
        )
        entries, _audit = _build(_scripts(item_call=item_call), _items())
        item = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "item_add_message"
        )
        self.assertEqual(item["texts"]["zh-Hans"], "Received <C0><I%d></C><C5>zh-Hans quartz</C>.")
        self.assertEqual(item["producer_origin"]["item_id"], 4202)
        self.assertTrue(item["dynamic_producer"]["dynamic_icon"])

    def test_accepts_the_verified_japanese_suffix_only_item_message_arity(self):
        item_call = Called(
            "ITEM_ADD_MESSAGE2_EV",
            0,
            (("int", 4202), ("string", "Received "), ("string", "."), ("int", 0)),
        )
        scripts = _scripts(item_call=item_call)
        scripts["ja"]["script/scena/reward.dat"].functions["Reward"] = _function(
            "Reward",
            (
                Called(
                    "ITEM_ADD_MESSAGE_EV", 0, (("int", 4202), ("string", "を貰った。"), ("int", 0))
                ),
            ),
        )
        entries, _audit = _build(scripts, _items())
        item = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "item_add_message"
        )
        self.assertEqual(item["texts"]["ja"], "<C0><I%d></C><C5>ja quartz</C>を貰った。")

    def test_accepts_talk_item_message_variants_with_a_runtime_icon_slot(self):
        item_call = Called(
            "ITEM_ADD_MESSAGE2_TK",
            0,
            (("int", 4202), ("string", "Received "), ("string", ".")),
        )
        scripts = _scripts(item_call=item_call)
        scripts["ja"]["script/scena/reward.dat"].functions["Reward"] = _function(
            "Reward",
            (Called("ITEM_ADD_MESSAGE_TK", 0, (("int", 4202), ("string", "を受け取った。"))),),
        )
        entries, _audit = _build(scripts, _items())
        item = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "item_add_message"
        )
        self.assertEqual(item["texts"]["ja"], "<C0><I%d></C><C5>ja quartz</C>を受け取った。")
        self.assertEqual(item["texts"]["en"], "Received <C0><I%d></C><C5>en quartz</C>.")

    def test_source_conflict_is_audited_without_erasing_another_locale_pair(self):
        entries, audit = _build(_scripts(), _items())
        duplicate = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "unlock_recipe"
        )
        duplicate = {
            **duplicate,
            "key": "duplicate",
            "texts": {**duplicate["texts"], "zh-Hans": "BP <C2>%d<C0>!"},
        }
        with (
            patch(
                "sora_bilingual.localization.dynamic_producers._read_scripts",
                return_value=_scripts(),
            ),
            patch(
                "sora_bilingual.localization.dynamic_producers._read_item_rows",
                return_value=_items(),
            ),
            patch(
                "sora_bilingual.localization.dynamic_producers._recipe_entries",
                return_value=[
                    next(
                        entry
                        for entry in entries
                        if entry.get("producer_origin", {}).get("family") == "unlock_recipe"
                    ),
                    duplicate,
                ],
            ),
        ):
            conflicted, conflicted_audit = build_dynamic_entries("unused", [])
        self.assertEqual(len(conflicted), len(entries) + 1)
        self.assertGreater(conflicted_audit["counters"]["dynamic_source_conflicts"], 0)
        self.assertTrue(
            any(
                item["reason"] == "dynamic_source_conflict"
                for item in conflicted_audit["diagnostics"]
            )
        )

    def test_missing_unrelated_locale_keeps_verified_partial_pairs(self):
        item_call = Called(
            "ITEM_ADD_MESSAGE2_EV", 0, (("int", 4202), ("string", "Received "), ("string", "."))
        )
        scripts, items = _scripts(item_call=item_call), _items()
        scripts.pop("de")
        items.pop("de")
        entries, audit = _build(scripts, items)
        numeric = next(
            entry
            for entry in entries
            if entry.get("dynamic_producer", {}).get("family") == "on_quest_add_bp"
        )
        recipe = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "unlock_recipe"
        )
        item = next(
            entry
            for entry in entries
            if entry.get("producer_origin", {}).get("family") == "item_add_message"
        )
        self.assertNotIn("de", numeric["texts"])
        self.assertNotIn("de", recipe["texts"])
        self.assertNotIn("de", item["texts"])
        self.assertTrue(
            any(item["reason"] == "producer_missing_locales" for item in audit["diagnostics"])
        )
        self.assertTrue(
            any(item["reason"] == "item_message_missing_locales" for item in audit["diagnostics"])
        )
