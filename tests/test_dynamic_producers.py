import unittest
import weakref
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.dynamic_producers import build_dynamic_entries
from sora_bilingual.localization.resources import Called, Function, Script


class ProducerPermissionTests(unittest.TestCase):
    def test_compiler_consumes_each_script_batch_before_reading_the_next(self):
        from sora_bilingual.localization import dynamic_producers as producers

        batch_alive = []

        def batches(*_):
            for number in range(4):
                # One yielded family may still be referenced by the caller
                # during generator advancement; earlier families must be free.
                self.assertLessEqual(sum(ref() is not None for ref in batch_alive), 1)
                script = Script({})
                batch_alive.append(weakref.ref(script))
                yield {"en": {f"script/{number}.dat": script}}

        with (
            patch.object(producers, "_script_batches", side_effect=batches),
            patch.object(producers, "_read_item_rows", return_value={}),
            patch.object(producers, "_read_book_ids", return_value={}),
        ):
            entries, _ = build_dynamic_entries("fixture", [])
        self.assertEqual(entries, [])
        self.assertTrue(all(ref() is None for ref in batch_alive))

    def test_reader_releases_validated_bytecode_but_keeps_complete_call_contracts(self):
        from sora_bilingual.localization.dynamic_producers import _read_scripts

        class BytecodePayload:
            pass

        payloads = []
        calls = (Called("helper", 0, (("int", 7),)), _panel("item", 17, "tail"))

        def parse(_):
            payload = BytecodePayload()
            payloads.append(weakref.ref(payload))
            return Script({"f": Function("f", 9, (1,), calls, ((payload,),), ("unused",))})

        with (
            patch(
                "sora_bilingual.localization.dynamic_producers.archive_names",
                return_value={"en": "test.pac"},
            ),
            patch.object(Path, "is_file", return_value=True),
            patch("sora_bilingual.localization.dynamic_producers.FpacArchive") as archive,
            patch(
                "sora_bilingual.localization.dynamic_producers._logical_script_entries",
                return_value={"a.dat": "a", "b.dat": "b"},
            ),
            patch(
                "sora_bilingual.localization.dynamic_producers.parse_scp", side_effect=parse
            ) as parser,
        ):
            scripts = _read_scripts(Path("fixture"), {"diagnostics": [], "counters": Counter()})
        self.assertEqual(parser.call_count, 2, "Every complete script must still be validated")
        self.assertTrue(
            all(ref() is None for ref in payloads),
            "Unconsumed bytecode must not accumulate across archives",
        )
        for script in scripts["en"].values():
            function = script.functions["f"]
            self.assertEqual(
                (function.flags, function.arg_types, function.called), (9, (1,), calls)
            )

    def test_book_domain_permission_is_not_a_missing_locale(self):
        from sora_bilingual.localization.dynamic_producers import _read_book_ids

        audit = {"diagnostics": []}
        with patch(
            "sora_bilingual.localization.dynamic_producers.FpacArchive",
            side_effect=PermissionError("owned fixture archive denied"),
        ) as archive:
            with self.assertRaisesRegex(PermissionError, "owned fixture archive denied"):
                _read_book_ids(Path("unused-owned-fixture"), audit)
            archive.assert_called_once()
        self.assertEqual(audit["diagnostics"], [])


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
                "RegisterBook": _function(
                    "RegisterBook",
                    (Called(None, 0, ()), Called(None, 0, ()), _panel("", 17, " registered!")),
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


def _build(scripts, items, books=None):
    with (
        patch(
            "sora_bilingual.localization.dynamic_producers._script_batches",
            side_effect=lambda *_: iter([scripts]),
        ),
        patch("sora_bilingual.localization.dynamic_producers._read_item_rows", return_value=items),
        patch(
            "sora_bilingual.localization.dynamic_producers._read_book_ids", return_value=books or {}
        ),
    ):
        return build_dynamic_entries("unused", [{"texts": {"zh-Hans": "wrong accepted catalog"}}])


class DynamicProducerTests(unittest.TestCase):
    def test_removal_helper_family_keeps_localized_prefix_and_suffix(self):
        from sora_bilingual.localization.dynamic_producers import _item_call_parts

        for family in ("EV", "TK"):
            for split in (False, True):
                args = (
                    (("int", 4202), ("string", "before "), ("string", " after"))
                    if split
                    else (("int", 4202), ("string", " after"))
                )
                helper = "ITEM_SUB_MESSAGE" + ("2" if split else "") + "_" + family
                call = Called(helper, 0, args)
                self.assertEqual(
                    _item_call_parts(call), (4202, "before " if split else "", " after", ())
                )
                scripts = _scripts(item_call=call)
                rows, _ = _build(scripts, _items())
                messages = [
                    r
                    for r in rows
                    if r.get("producer_origin", {}).get("family") == "item_add_message"
                ]
                self.assertEqual(len(messages), 1)
                for language in LANGUAGES:
                    self.assertEqual(
                        messages[0]["texts"][language],
                        ("before " if split else "")
                        + f"<C0><I%d></C><C5>{language} quartz</C> after",
                    )

    def test_literal_item_panel_keeps_full_localized_outer_text_and_item_order(self):
        def panel(prefix, suffix):
            return Called(
                None,
                3,
                (
                    ("int", 5),
                    ("int", 8),
                    ("int", 65535),
                    ("int", 16),
                    ("string", prefix),
                    ("int", 17),
                    ("int", 4202),
                    ("int", 10),
                    ("string", suffix),
                ),
            )

        scripts = _scripts()
        for language in LANGUAGES:
            scripts[language]["script/scena/gift.dat"] = Script(
                {
                    "Gift": _function(
                        "Gift",
                        (
                            panel(
                                "Handed over " if language == "en" else "",
                                "." if language == "en" else "渡した。",
                            ),
                        ),
                    )
                }
            )
        rows, audit = _build(scripts, _items())
        panels = [
            r for r in rows if r.get("producer_origin", {}).get("family") == "static_item_panel"
        ]
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0]["texts"]["en"], "Handed over <C0><I%d></C><C5>en quartz</C>\n.")
        self.assertEqual(panels[0]["texts"]["ja"], "<C0><I%d></C><C5>ja quartz</C>\n渡した。")
        self.assertEqual(panels[0]["called_ids"], {l: 0 for l in LANGUAGES})
        self.assertEqual(panels[0]["dynamic_producer"]["numbers"]["ja"], ["ascii"])

    def test_item_panel_rejects_unknown_dynamic_operand_and_changed_item_identity(self):
        scripts = _scripts()
        for language in LANGUAGES:
            operand = (
                ("int", 4202)
                if language not in {"ja", "ko"}
                else (("var", None) if language == "ja" else ("int", 2100))
            )
            call = Called(
                None,
                3,
                (
                    ("int", 5),
                    ("int", 8),
                    ("int", 65535),
                    ("int", 16),
                    ("string", "Handed "),
                    ("int", 17),
                    operand,
                    ("string", "."),
                ),
            )
            scripts[language]["script/scena/gift.dat"] = Script(
                {"Gift": _function("Gift", (call,))}
            )
        rows, _ = _build(scripts, _items())
        panels = [
            r for r in rows if r.get("producer_origin", {}).get("family") == "static_item_panel"
        ]
        self.assertEqual(len(panels), 1)
        self.assertNotIn("ja", panels[0]["texts"])
        self.assertNotIn("ko", panels[0]["texts"])

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
        self.assertEqual(audit["counters"]["unlock_recipe_items_emitted"], 1)

    def test_book_notification_uses_inventory_name_for_the_actual_book_item_id(self):
        items = _items()
        for language, rows in items.items():
            rows[360] = (f"{language} volume", 527618)
            rows[361] = (f"{language} unrelated", 527618)
        entries, audit = _build(_scripts(), items, {language: {360} for language in LANGUAGES})
        books = [
            e for e in entries if e.get("producer_origin", {}).get("family") == "register_book"
        ]
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["producer_origin"]["item_id"], 360)
        self.assertEqual(books[0]["texts"]["en"], "<C0><I%d></C><C5>en volume</C> registered!")
        self.assertEqual(audit["counters"]["register_book_items_emitted"], 1)

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
                "sora_bilingual.localization.dynamic_producers._script_batches",
                side_effect=lambda *_: iter([_scripts()]),
            ),
            patch(
                "sora_bilingual.localization.dynamic_producers._read_item_rows",
                return_value=_items(),
            ),
            patch(
                "sora_bilingual.localization.dynamic_producers._item_template_entries",
                side_effect=[
                    [
                        next(
                            entry
                            for entry in entries
                            if entry.get("producer_origin", {}).get("family") == "unlock_recipe"
                        ),
                        duplicate,
                    ],
                    [],
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
