"""Raw-resource counterexamples, complete final modes and Python/JS parity."""

import json
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from sora_bilingual.localization.item_help_composition import (
    ItemHelpContractError,
    compile_item_help_grammar,
)
from sora_bilingual.localization.menu_text import MenuTranslator


FIXTURE = Path(__file__).parent / "fixtures/r25-raw-help-constructors.json"


def build():
    raw = json.loads(FIXTURE.read_text("utf8"))
    # Retain blank physical fields in the fixture/oracle; production catalogue
    # input omits a field only when it is blank in every locale.
    catalogue = [e for e in raw["entries"] if any(e["texts"].values())]
    grammar = compile_item_help_grammar(
        catalogue,
        "en",
        raw["metadata"],
        raw["groups"],
        actual_contexts=raw["contexts"],
        connect_groups=raw["connect_groups"],
    )
    entries = catalogue + grammar["status_entries"] + grammar["detail_entries"]
    fields = {e["key"]: e["texts"] for e in raw["entries"]}
    metadata = {v["id"]: k for k, v in raw["metadata"]["SkillEffectHelpData"].items()}
    return raw, grammar, entries, fields, metadata


def visible(value):
    return re.sub(r"<[^<>]*>", "", re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", value, flags=re.S))


class R25ProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.grammar, cls.entries, cls.fields, cls.metadata = build()
        cls.js_proofs = []

    def field(self, identifier, field, language):
        return self.fields[
            f"table/t_itemhelp.tbl/SkillEffectHelpData/{self.metadata[identifier]}/{field}"
        ][language]

    def constant(self, key, language):
        return self.fields["table/t_text.tbl/TXT_ITEM_HELP_" + key][language]

    def body(self, contains):
        return next(
            e["texts"]
            for e in self.raw["entries"]
            if contains in e["texts"].get("en", "") and e["key"].startswith("table/t_skill.tbl/")
        )

    def test_optional_self_constant_preserves_legacy_catalogues_and_locale_rejection(self):
        key = "table/t_text.tbl/TXT_ITEM_HELP_SELF"
        catalogue = [e for e in self.raw["entries"] if any(e["texts"].values()) and e["key"] != key]
        grammar = compile_item_help_grammar(
            catalogue,
            "en",
            self.raw["metadata"],
            self.raw["groups"],
            actual_contexts=self.raw["contexts"],
            connect_groups=self.raw["connect_groups"],
        )
        self.assertFalse(
            any(
                e["item_help_contract"]["family"] == "self_direction_constructor"
                for e in grammar["detail_entries"]
                if "item_help_contract" in e
            )
        )
        self.assertEqual(
            [e for e in grammar["detail_entries"]],
            [
                e
                for e in self.grammar["detail_entries"]
                if e.get("item_help_contract", {}).get("family") != "self_direction_constructor"
            ],
        )
        partial = next(e for e in self.raw["entries"] if e["key"] == key)
        partial = {**partial, "texts": {l: t for l, t in partial["texts"].items() if l != "ja"}}
        with self.assertRaisesRegex(ItemHelpContractError, "incomplete constructor constant"):
            compile_item_help_grammar(
                catalogue + [partial],
                "en",
                self.raw["metadata"],
                self.raw["groups"],
                actual_contexts=self.raw["contexts"],
                connect_groups=self.raw["connect_groups"],
            )

    def test_native_type12_empty_stat_complete_headers_boundaries_and_three_modes(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        body = self.body("Slightly heal one ally's HP")
        prefix = next(
            e["texts"]
            for e in self.raw["entries"]
            if e["key"].startswith("table/t_itemhelp.tbl/SkillTextArrayData/")
        )
        target = next(
            e["texts"]
            for e in self.raw["entries"]
            if e["key"].endswith("/label") and e["texts"].get("en") == "Ally - Single"
        )
        cases = []
        for amount in (0, 2999, 3000, 4499, 4500, 2147483647):
            magnitude = "SMALL" if amount < 3000 else "MIDDLE" if amount < 4500 else "LARGE"
            texts = {
                l: prefix[l]
                + "<I299><C3>"
                + target[l]
                + "</C>"
                + self.constant("FORMAT6", l)
                + "<c698>"
                + self.field(128, "name", l).replace("%s", self.constant(magnitude, l))
                + "</C>\n<C0>"
                + body[l]
                for l in ("en", "ja", "zh-Hans")
            }
            modes = {}
            for mode, language in (
                ("primary", "ja"),
                ("secondary", "zh-Hans"),
                ("annotation", "ja"),
            ):
                plan = tr.render(texts["en"], mode)
                self.assertEqual(
                    visible(plan["text"]), visible(texts[language]), (amount, mode, plan)
                )
                if mode == "annotation":
                    roles = [
                        l
                        for l in plan["layers"]
                        if any(
                            "/recovery_magnitude_single/128/" in key
                            for key in l.get("semantic_ids", [])
                        )
                    ]
                    self.assertEqual(len(roles), 1, plan)
                    self.assertEqual(
                        visible(roles[0]["text"]),
                        visible(
                            self.field(128, "name", "zh-Hans").replace(
                                "%s", self.constant(magnitude, "zh-Hans")
                            )
                        ),
                    )
                modes[mode] = plan
            cases.append({"source": texts["en"], "modes": modes})
        self.js_parity(tr, cases)
        self.assertEqual(
            {
                r["item_help_contract"]["magnitude_constant"]
                for r in self.grammar["detail_entries"]
                if r.get("item_help_contract", {}).get("family") == "recovery_magnitude_single"
            },
            {"SMALL", "MIDDLE", "LARGE"},
        )
        for source in ("Heal (unknown) HP", "Heal (XS) HP", "Heal NaN HP"):
            self.assertIsNone(tr.details._effect_unit(source))

    def test_internal_rejected_partition_cannot_poison_revive_and_valid_neighbour(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        bodies = [self.body("prayer filled with love"), self.body("even more life by striking")]
        cases = []
        for amount, body, neighbour in ((100, bodies[0], "shield"), (50, bodies[1], "debuff")):
            texts = {}
            for language in ("en", "ja", "zh-Hans"):
                modifier = (
                    self.constant("ALL", language)
                    if amount == 100
                    else self.constant("PERSENT", language)
                    .replace("%d", str(amount))
                    .replace("%%", "%")
                )
                revive = (
                    self.field(120, "name", language)
                    + self.constant("FORMAT8", language)
                    + self.field(120, "format", language).replace("%s", modifier)
                )
                tail = (
                    self.field(225, "name", language).replace(
                        "%s", self.constant("LARGE", language)
                    )
                    if neighbour == "shield"
                    else self.constant("DEBUFF_CANCEL", language)
                )
                texts[language] = (
                    "<c698>"
                    + revive
                    + self.constant("FORMAT8", language)
                    + tail
                    + "</C>\n"
                    + body[language]
                )
            modes = {}
            for mode, language in (
                ("primary", "ja"),
                ("secondary", "zh-Hans"),
                ("annotation", "ja"),
            ):
                plan = tr.render(texts["en"], mode)
                self.assertEqual(
                    visible(plan["text"]), visible(texts[language]), (amount, mode, plan)
                )
                if mode == "annotation":
                    roles = [l for l in plan["layers"] if l.get("semantic_ids")]
                    self.assertEqual(len(roles), 2, plan)
                    self.assertTrue(
                        any("/revive_recovery/120/" in k for k in roles[0]["semantic_ids"])
                    )
                modes[mode] = plan
            cases.append({"source": texts["en"], "modes": modes})
        # A malformed parameter still refuses the entire unproved header while
        # its independently known exact body keeps its existing rendering.
        for value in ("NaN", "50.5", "1e3", "2147483648"):
            source = "<c698>Revive, Heal " + value + "% HP, Remove Debuff</C>\n" + bodies[1]["en"]
            for mode in ("primary", "secondary", "annotation"):
                plan = tr.render(source, mode)
                self.assertIn("Heal " + value + "% HP", plan["text"])
                self.assertNotIn(bodies[1]["en"], plan["text"])
        self.js_parity(tr, cases)

    def test_complete_raw_coloured_category_hint_is_a_standalone_node(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        for e in self.raw["entries"]:
            if not e["key"].startswith("table/t_itemhelp.tbl/ItemKindHelpData/") or not e[
                "key"
            ].endswith("/description"):
                continue
            texts = {
                l: re.findall(r"<[Cc][0-9a-fA-F]+>([^<>]+)</[Cc]>", e["texts"][l])[0]
                for l in ("en", "ja", "zh-Hans")
            }
            for wrapper in ("%s", "<c698>%s</C>", "[<c698>%s</C>]"):
                source = wrapper % texts["en"]
                modes = {}
                for mode, language in (
                    ("primary", "ja"),
                    ("secondary", "zh-Hans"),
                    ("annotation", "ja"),
                ):
                    plan = tr.render(source, mode)
                    self.assertEqual(
                        visible(plan["text"]), visible(wrapper % texts[language]), plan
                    )
                    self.assertNotIn(texts["en"], plan["text"])
                    modes[mode] = plan
                cases.append({"source": source, "modes": modes})
        self.js_parity(tr, cases)
        self.assertEqual(tr.render("Can be accessed")["text"], "Can be accessed")
        self.assertEqual(tr.render("Used in shops")["text"], "Used in shops")

    def test_other_base_language_uses_the_same_type12_contract(self):
        body = self.body("Slightly heal one ally's HP")
        for source_language in ("ja", "zh-Hans", "fr", "de"):
            catalogue = [e for e in self.raw["entries"] if any(e["texts"].values())]
            grammar = compile_item_help_grammar(
                catalogue,
                source_language,
                self.raw["metadata"],
                self.raw["groups"],
                actual_contexts=self.raw["contexts"],
                connect_groups=self.raw["connect_groups"],
            )
            tr = MenuTranslator(
                catalogue + grammar["status_entries"] + grammar["detail_entries"],
                "ja",
                "zh-Hans",
                source_language,
            )
            source = (
                "<c698>"
                + self.field(128, "name", source_language).replace(
                    "%s", self.constant("SMALL", source_language)
                )
                + "</C>\n"
                + body[source_language]
            )
            for mode, target in (("primary", "ja"), ("secondary", "zh-Hans"), ("annotation", "ja")):
                expected = (
                    "<c698>"
                    + self.field(128, "name", target).replace("%s", self.constant("SMALL", target))
                    + "</C>\n"
                    + body[target]
                )
                self.assertEqual(
                    visible(tr.render(source, mode)["text"]),
                    visible(expected),
                    (source_language, mode),
                )

    def test_complete_category_prefix_and_own_body_keep_all_final_modes(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        headers = [
            e
            for e in self.raw["entries"]
            if e["key"].startswith("table/t_itemhelp.tbl/ItemKindHelpData/")
            and e["key"].endswith("/description")
        ]
        bodies = [
            e
            for e in self.raw["entries"]
            if e["key"].startswith("table/t_item.tbl/") and e["key"].endswith("/description")
        ]
        cases = []
        for needle in (
            "Special Report - Royal Capital Prepares",
            "Used in shops for quartz & item enhancements",
        ):
            header = next(
                e
                for e in headers
                if ("Book List" if needle.startswith("Special") else "Used in shops")
                in e["texts"]["en"]
            )
            body = (
                next(e for e in bodies if e["texts"]["en"].startswith("Special Report"))
                if needle.startswith("Special")
                else bodies[1]
            )
            texts = {
                l: header["texts"][l] + "\n" + body["texts"][l] for l in ("en", "ja", "zh-Hans")
            }
            modes = {}
            for mode, language in (
                ("primary", "ja"),
                ("secondary", "zh-Hans"),
                ("annotation", "ja"),
            ):
                plan = tr.render(texts["en"], mode)
                self.assertEqual(
                    visible(plan["text"]), visible(texts[language]), (needle, mode, plan)
                )
                self.assertNotIn("Book List", plan["text"])
                self.assertNotIn("Used in shops", plan["text"])
                self.assertNotIn("Books", plan["text"])
                self.assertFalse(
                    any(layer.get("semantic_ids") for layer in plan["layers"]),
                    "A category prefix is not an effect unit",
                )
                if mode == "annotation":
                    self.assertTrue(
                        any(
                            visible(layer["text"]) == visible(body["texts"]["zh-Hans"])
                            for layer in plan["layers"]
                        ),
                        "The rich header and complete body need independently owned secondary lanes",
                    )
                modes[mode] = plan
            cases.append({"source": texts["en"], "modes": modes})
        self.js_parity(tr, cases)
        # A category word or an unknown suffix cannot grant a detail entrance.
        self.assertIsNone(tr._detail_header("Books\nUnproved body"))
        self.assertIsNone(tr._detail_header(headers[0]["texts"]["en"] + " unknown\nUnproved body"))

    def test_complete_conflicting_names_do_not_borrow_npc_or_partial_aliases(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        for source in ("Prometheus", "Guard", "Bobcat", "Kloe - Light Brown Hair\u3000"):
            modes = {}
            for mode in ("primary", "secondary", "annotation"):
                plan = tr.render(source, mode)
                self.assertEqual(plan["text"], source)
                self.assertEqual(plan["layers"], [])
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
        self.js_parity(tr, cases)
        # The existing proved item-name scope retains its own exact resource.
        item = next(
            e
            for e in self.raw["entries"]
            if e["key"].startswith("table/t_item.tbl/") and e["texts"].get("en") == "Prometheus"
        )
        for mode, language in (("primary", "ja"), ("secondary", "zh-Hans")):
            self.assertEqual(
                tr.scoped["item_name"].render("Prometheus", mode)["text"], item["texts"][language]
            )

    def test_distinct_complete_styled_names_keep_previous_final_outputs(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        for source in ("<C9>Single", "<C9>Marking", "<C9>Absorb EP"):
            entry = next(
                e
                for e in self.raw["entries"]
                if e["key"].startswith("table/t_skill.tbl/")
                and e["key"].endswith("/name")
                and e["texts"].get("en") == source
            )
            modes = {}
            for mode, language in (
                ("primary", "ja"),
                ("secondary", "zh-Hans"),
                ("annotation", "ja"),
            ):
                plan = tr.render(source, mode)
                self.assertEqual(visible(plan["text"]), visible(entry["texts"][language]))
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
        self.js_parity(tr, cases)
        # "Attack 2" is also a distinct viewer motion (circled digit). A global
        # numeric template cannot erase that conflict. Its real item-name
        # scope keeps the official quartz pair without importing an owner.
        self.assertEqual(tr.render("Attack 2")["text"], "Attack 2")
        quartz = next(
            e
            for e in self.raw["entries"]
            if e["key"].startswith("table/t_item.tbl/") and e["texts"].get("en") == "Attack 2"
        )
        for mode, language in (("primary", "ja"), ("secondary", "zh-Hans")):
            self.assertEqual(
                tr.scoped["item_name"].render("Attack 2", mode)["text"], quartz["texts"][language]
            )

    def test_complete_native_constructors_with_empty_body_keep_roles_and_refuse_partial(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        sources = {
            "Max HP+25%": {
                l: self.field(1001, "name", l).replace("%d", "25").replace("%%", "%")
                for l in ("ja", "zh-Hans")
            },
            "CP+20, STR<I270>(3 turns)": {
                l: self.field(126, "name", l).replace("%d", "20")
                + self.constant("FORMAT8", l)
                + self.field(80, "name", l).replace("%d", "3").replace("%s", "<I270>")
                for l in ("ja", "zh-Hans")
            },
            "STR+15%, DEF-3%": {
                l: self.field(1004, "name", l).replace("%d", "15").replace("%%", "%")
                + self.constant("FORMAT8", l)
                + self.field(1010, "name", l).replace("%d", "3").replace("%%", "%")
                for l in ("ja", "zh-Hans")
            },
        }
        for source, targets in sources.items():
            source = "<c698>" + source + "</C>\n"
            modes = {}
            for mode, language in (
                ("primary", "ja"),
                ("secondary", "zh-Hans"),
                ("annotation", "ja"),
            ):
                plan = tr.render(source, mode)
                self.assertEqual(
                    visible(plan["text"]),
                    visible("<c698>" + targets[language] + "</C>\n"),
                    (source, mode, plan),
                )
                if (
                    mode == "annotation"
                    and language == "ja"
                    and targets["ja"] != targets["zh-Hans"]
                ):
                    self.assertTrue(any(layer.get("semantic_ids") for layer in plan["layers"]))
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
        for bad in ("CP+20, UNKNOWN", "STR<I270>(NaN turns)", "Max HP+NaN%", "Max HP+2147483648%"):
            source = "<c698>" + bad + "</C>\n"
            for mode in ("primary", "secondary", "annotation"):
                self.assertEqual(tr.render(source, mode)["text"], source)
        # A complete ordinary sentence followed by LF keeps its normal route.
        body = self.body("Slightly heal one ally's HP")
        for mode, language in (("primary", "ja"), ("secondary", "zh-Hans")):
            self.assertEqual(tr.render(body["en"] + "\n", mode)["text"], body[language] + "\n")
        self.js_parity(tr, cases)

    def reconstruct_secondary(self, plan):
        if not plan["layers"]:
            return re.sub(
                r"<R>(.*?)</R([^<>]*)>", lambda m: m[2] if m[1] else "", plan["text"], flags=re.S
            )
        text, at = plan["text"], 0
        for layer in plan["layers"]:
            anchor = text.find("<R></R_>", at)
            self.assertGreaterEqual(anchor, 0, plan)
            self.assertTrue(text.startswith(layer["primary"], anchor + 8), plan)
            text = text[:anchor] + layer["text"] + text[anchor + 8 + len(layer["primary"]) :]
            at = anchor + len(layer["text"])
        return text

    def assert_complete_modes(self, translator, texts, family, cases):
        modes = {}
        icons = re.findall(r"<I\d+>", texts["en"])
        for mode, language in (("primary", "ja"), ("secondary", "zh-Hans"), ("annotation", "ja")):
            plan = translator.render(texts["en"], mode)
            self.assertEqual(
                visible(plan["text"]), visible(texts[language]), (texts["en"], mode, plan)
            )
            self.assertEqual(re.findall(r"<I\d+>", plan["text"]), icons, (texts["en"], mode, plan))
            if mode == "annotation":
                self.assertEqual(
                    visible(self.reconstruct_secondary(plan)), visible(texts["zh-Hans"]), plan
                )
                self.assertTrue(
                    any(
                        "/" + family + "/" in key
                        for layer in plan["layers"]
                        for key in layer.get("semantic_ids", [])
                    ),
                    plan,
                )
            modes[mode] = plan
        cases.append({"source": texts["en"], "modes": modes})

    def test_self_native_groups_complete_resource_outputs_and_three_modes(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        for ids in ((80, 81), (83, 84)):
            context = next(
                c for c in self.raw["contexts"] if tuple(s[0] for s in c["group"]) == ids
            )
            body = self.fields[context["description_key"]]
            for level in (1, 2, 3):
                for arrow in (f"<I{269 + level}>", "↑" * level):
                    texts = {}
                    for language in ("en", "ja", "zh-Hans"):
                        joined = self.constant("LINK", language).join(
                            self.field(i, "stat", language) for i in ids
                        )
                        template = self.field(ids[0], "name", language).replace(
                            self.field(ids[0], "stat", language), joined, 1
                        )
                        value = template.replace("%s", arrow).replace("%d", "4").rstrip()
                        if language == "en":
                            value = (
                                joined
                                + arrow
                                + self.field(ids[0], "turns", language).replace("%d", "4")
                            )
                        texts[language] = (
                            self.constant("SELF", language) + "<c698>" + value + "</C>"
                        )
                    for display_space in (False, True):
                        variant = dict(texts)
                        if display_space:
                            variant["en"] = variant["en"].replace(
                                self.constant("SELF", "en"), self.constant("SELF", "en") + " ", 1
                            )
                        for suffix in ("", "body"):
                            complete = {
                                l: t + "\n" + (body[l] if suffix else "")
                                for l, t in variant.items()
                            }
                            self.assert_complete_modes(
                                tr, complete, "self_direction_constructor", cases
                            )
        self.js_parity(tr, cases)

    def test_hate_type9_upward_domain_self_frame_body_and_three_modes(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        body = self.fields[
            next(c["description_key"] for c in self.raw["contexts"] if c["group"][0][0] == 101)
        ]
        cases = []
        for level in (1, 2, 3):
            for arrow in (f"<I{269 + level}>", "↑" * level):
                for self_target in (False, True):
                    for display_space in (False, True) if self_target else (False,):
                        texts = {
                            l: (
                                self.constant("SELF", l)
                                + (" " if display_space and l == "en" else "")
                                if self_target
                                else ""
                            )
                            + "<c698>"
                            + self.field(101, "name", l).replace("%s", arrow)
                            + "</C>"
                            for l in ("en", "ja", "zh-Hans")
                        }
                        for suffix in ("", "body"):
                            complete = {
                                l: t + "\n" + (body[l] if suffix else "") for l, t in texts.items()
                            }
                            self.assert_complete_modes(
                                tr,
                                complete,
                                "self_direction_constructor"
                                if self_target
                                else "direction_single_up",
                                cases,
                            )
        self.js_parity(tr, cases)
        contracts = [
            e["item_help_contract"]
            for e in self.grammar["detail_entries"]
            if e.get("item_help_contract", {}).get("family") == "direction_single_up"
        ]
        self.assertEqual({c["strength_level"] for c in contracts}, {1, 2, 3})
        self.assertTrue(all(c["record_ids"] == [101] for c in contracts))

    def test_self_constructor_all_eight_source_languages_keep_native_english_target(self):
        for source_language in self.fields["table/t_text.tbl/TXT_ITEM_HELP_SELF"]:
            catalogue = [e for e in self.raw["entries"] if any(e["texts"].values())]
            grammar = compile_item_help_grammar(
                catalogue,
                source_language,
                self.raw["metadata"],
                self.raw["groups"],
                actual_contexts=self.raw["contexts"],
                connect_groups=self.raw["connect_groups"],
            )
            tr = MenuTranslator(
                catalogue + grammar["status_entries"] + grammar["detail_entries"],
                "en",
                "ja",
                source_language,
            )
            cases = []
            for ids in ((80, 81), (83, 84)):
                texts = {}
                for language in (source_language, "en", "ja"):
                    joined = self.constant("LINK", language).join(
                        self.field(i, "stat", language) for i in ids
                    )
                    value = self.field(ids[0], "name", language).replace(
                        self.field(ids[0], "stat", language), joined, 1
                    )
                    value = value.replace("%s", "<I271>").replace("%d", "4").rstrip()
                    if language == "en":
                        value = (
                            joined
                            + "<I271>"
                            + self.field(ids[0], "turns", language).replace("%d", "4")
                        )
                    texts[language] = self.constant("SELF", language) + "<c698>" + value + "</C>\n"
                modes = {}
                for mode, language in (
                    ("primary", "en"),
                    ("secondary", "ja"),
                    ("annotation", "en"),
                ):
                    plan = tr.render(texts[source_language], mode)
                    self.assertEqual(
                        visible(plan["text"]),
                        visible(texts[language]),
                        (source_language, mode, plan),
                    )
                    if mode == "annotation":
                        self.assertEqual(
                            visible(self.reconstruct_secondary(plan)), visible(texts["ja"]), plan
                        )
                    modes[mode] = plan
                cases.append({"source": texts[source_language], "modes": modes})
            self.js_parity(tr, cases)

    def test_actual_blank_body_recovery_sequences_survive_parameter_label_homographs(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        self.assertIsNone(tr._whole_effect_pair("CP Regen"))
        self.assertIsNone(tr._whole_effect_pair("EP Regen"))
        rows = [r for r in self.raw["complete_effect_gap_cases"] if r["source"].endswith("\n")]
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assert_complete_modes(tr, row["texts"], "native_mixed_effect_sequence", cases)
        self.js_parity(tr, cases)

    def test_native_direction_join_known_neighbour_is_not_a_bad_arrow(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        for arrow in ("<I271>", "↑↑"):
            for self_target in (False, True):
                texts = {
                    l: "<c698>"
                    + (self.constant("SELF", l) if self_target else "")
                    + self.field(101, "name", l).replace("%s", arrow)
                    + self.constant("FORMAT8", l)
                    + self.field(126, "name", l).replace("%d", "20")
                    + "</C>\n"
                    for l in ("en", "ja", "zh-Hans")
                }
                # Native SELF sits before its own colour run, not inside it.
                if self_target:
                    texts = {
                        l: self.constant("SELF", l)
                        + "<c698>"
                        + self.field(101, "name", l).replace("%s", arrow)
                        + "</C>"
                        + self.constant("FORMAT8", l)
                        + "<c698>"
                        + self.field(126, "name", l).replace("%d", "20")
                        + "</C>\n"
                        for l in ("en", "ja", "zh-Hans")
                    }
                for mode, language in (
                    ("primary", "ja"),
                    ("secondary", "zh-Hans"),
                    ("annotation", "ja"),
                ):
                    plan = tr.render(texts["en"], mode)
                    self.assertEqual(
                        visible(plan["text"]), visible(texts[language]), (texts["en"], mode, plan)
                    )
                    if mode == "annotation":
                        self.assertEqual(
                            visible(self.reconstruct_secondary(plan)),
                            visible(texts["zh-Hans"]),
                            plan,
                        )
                cases.append(
                    {
                        "source": texts["en"],
                        "modes": {
                            m: tr.render(texts["en"], m)
                            for m in ("primary", "secondary", "annotation")
                        },
                    }
                )
        self.js_parity(tr, cases)

    def test_refused_direction_keeps_exact_independent_body_but_later_whole_veto_wins(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        joined = self.constant("LINK", "en").join(self.field(i, "stat", "en") for i in (83, 84))
        header = (
            "<c698>"
            + joined
            + "<I273>"
            + self.field(83, "turns", "en").replace("%d", "4")
            + "</C>\n"
        )
        body = self.body("Slightly heal one ally's HP")
        source = header + "<C0>" + body["en"]
        self.assertIsNone(tr.raw_pair(source))
        cases = []
        for mode in ("primary", "secondary", "annotation"):
            expected_body = tr.details.render(body["en"], mode)
            plan = tr.render(source, mode)
            self.assertEqual(plan["text"], header + "<C0>" + expected_body["text"])
            self.assertEqual(
                plan["layers"],
                [
                    dict(l, offset=l["offset"] + len((header + "<C0>").encode("utf8")))
                    for l in expected_body["layers"]
                ],
            )
            self.assertEqual(tr.translate(source, mode), plan["text"])
        cases.append(
            {
                "source": source,
                "modes": {m: tr.render(source, m) for m in ("primary", "secondary", "annotation")},
            }
        )
        self.js_parity(tr, cases)
        veto_source = self.constant("DEBUFF_CANCEL", "en")
        veto = {
            "key": "table/t_itemhelp.tbl/generated/r25-review-veto",
            "detail_authority": True,
            "texts": {"en": veto_source, "ja": "資源拒否候補", "zh-Hans": "资源拒绝候选"},
        }
        refused = MenuTranslator(self.entries + [veto], "ja", "zh-Hans", "en")
        source = header + veto_source + "\n<C0>" + body["en"]
        self.assertIsNotNone(refused._detail_body_boundary(source))
        self.assertIn(veto_source, refused.details.detail_effect_blocked_literals)
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(
                refused.render(source, mode), {"text": source, "layers": [], "kind": "plain"}
            )
            self.assertEqual(refused.translate(source, mode), source)
        self.js_parity(
            refused,
            [
                {
                    "source": source,
                    "modes": {
                        m: refused.render(source, m) for m in ("primary", "secondary", "annotation")
                    },
                }
            ],
        )

    def test_protected_native_reading_keeps_independently_compiled_outer_role(self):
        from test_effect_units import entries as established_contract

        tr = MenuTranslator(established_contract(), "ja", "zh-Hans", "en")
        cases = []
        for native in ("<R>HP Regen</R[reading]>", "<R>XYZ</R[reading]>"):
            source = native + "<c698>CP Regen</C>\n<C0>Official description"
            modes = {}
            for mode, target in (
                ("primary", "CP徐々上昇"),
                ("secondary", "CP逐渐上升"),
                ("annotation", "CP徐々上昇"),
            ):
                plan = tr.render(source, mode)
                self.assertTrue(plan["text"].startswith(native), plan)
                self.assertIn(target, plan["text"])
                if mode == "annotation":
                    roles = [l for l in plan["layers"] if l.get("semantic_ids")]
                    self.assertEqual(len(roles), 1, plan)
                    self.assertEqual(
                        roles[0]["semantic_ids"],
                        ["table/t_itemhelp.tbl/SkillEffectHelpData/cp/name"],
                    )
                    self.assertTrue(
                        all("XYZ" not in l["primary"] + l["text"] for l in plan["layers"])
                    )
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
            self.assertIsNone(tr.effect_detail_plan(native + ", CP Regen"))
            missing_body = native + ", CP Regen"
            for mode in ("primary", "secondary", "annotation"):
                self.assertEqual(tr.render(missing_body, mode)["text"], missing_body)
                self.assertEqual(tr.render(missing_body, mode)["layers"], [])
        self.js_parity(tr, cases)
        malformed = "<R>XYZ<c698>CP Regen</C>\n<C0>Official description"
        cases = []
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(tr.render(malformed, mode)["text"], malformed)
            self.assertEqual(tr.render(malformed, mode)["layers"], [])
        cases.append(
            {
                "source": malformed,
                "modes": {
                    m: tr.render(malformed, m) for m in ("primary", "secondary", "annotation")
                },
            }
        )
        self.js_parity(tr, cases)
        source = "<R>XYZ</R[reading]><c698>CP Regen</C>\n<C0>Official description"
        conflict = [
            {
                "key": "table/t_item.tbl/r25-conflict-" + str(i) + "/name",
                "texts": {"en": source, "ja": "全体候補" + str(i), "zh-Hans": "整句候选" + str(i)},
            }
            for i in (1, 2)
        ]
        denied = MenuTranslator(established_contract() + conflict, "ja", "zh-Hans", "en")
        self.assertTrue(denied.whole_conflict(source))
        for mode in ("primary", "secondary", "annotation"):
            self.assertEqual(denied.render(source, mode)["text"], source)
            self.assertEqual(denied.render(source, mode)["layers"], [])
        self.js_parity(
            denied,
            [
                {
                    "source": source,
                    "modes": {
                        m: denied.render(source, m) for m in ("primary", "secondary", "annotation")
                    },
                }
            ],
        )

    def test_whole_numeric_admission_cannot_erase_source_string_slots(self):
        # Numeric construction checks both field count and ordered kinds.
        # A source %s cannot be admitted with fixed or numeric-only targets.
        for pair in (("固定", "固定"), ("数%d", "数%d")):
            tr = MenuTranslator(
                [
                    {
                        "key": "table/t_text.tbl/r25-mismatch",
                        "texts": {"en": "Slot %s", "ja": pair[0], "zh-Hans": pair[1]},
                    }
                ],
                "ja",
                "zh-Hans",
                "en",
            )
            self.assertEqual(tr.numeric, [])
            self.assertIsNone(tr._whole_effect_pair("Slot Alice"))
        tr = MenuTranslator(
            [
                {
                    "key": "table/t_text.tbl/r25-valid-string-slot",
                    "texts": {"en": "Slot %s", "ja": "欄%s", "zh-Hans": "栏%s"},
                }
            ],
            "ja",
            "zh-Hans",
            "en",
        )
        self.assertTrue(tr.numeric)
        self.assertIsNone(tr._whole_effect_pair("Slot Alice"))

    def test_bare_native_direction_group_invalid_strength_refuses_three_modes(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        cases = []
        joined = self.constant("LINK", "en").join(self.field(i, "stat", "en") for i in (83, 84))
        turns = self.field(83, "turns", "en").replace("%d", "4")
        for source in (
            "<c698>" + joined + "<I273>" + turns + "</C>",
            "<c698>" + joined + "↑↑↑↑" + turns + "</C>",
            "<c698>" + joined + "<I273>" + turns + "</C>\n",
        ):
            modes = {}
            for mode in ("primary", "secondary", "annotation"):
                plan = tr.render(source, mode)
                self.assertEqual(plan["text"], source, (source, mode, plan))
                self.assertEqual(plan["layers"], [], plan)
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
        self.js_parity(tr, cases)

    def test_self_hate_unknown_neighbours_parameters_and_whole_conflicts_refuse(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        valid = "(Self)<c698>Hate<I271></C>\n"
        negatives = [
            "(Self)<c698>Hate<I273></C>\n",
            "(Self)<c698>Hate<I268></C>\n",
            "Hate<I273>",
            "HateNaN",
            "(Self)Hate<I273>",
            "<c698>Hate<I273></C>",
            "(Self)<c698>Hate↑↑↑↑</C>\n",
            "(Self)<c698>HateNaN</C>\n",
            "(Self)<c698>STR&DEF<I271>(NaN turns)</C>\n",
            "(Self)<c698>STR&DEF<I271>(4 turns), UNKNOWN</C>\n",
            "Foreign" + valid,
            "(Self)  <c698>Hate<I271></C>\n",
        ]
        cases = []
        for source in negatives:
            modes = {}
            for mode in ("primary", "secondary", "annotation"):
                plan = tr.render(source, mode)
                self.assertEqual(plan["text"], source, (source, mode, plan))
                self.assertEqual(plan["layers"], [], (source, mode, plan))
                modes[mode] = plan
            cases.append({"source": source, "modes": modes})
        self.js_parity(tr, cases)
        collision = {
            "key": "table/t_item.tbl/whole-conflict/name",
            "texts": {"en": valid, "ja": "別の全体候補", "zh-Hans": "另一个整句候选"},
        }
        admitted = next(e for e in self.grammar["detail_entries"] if e["texts"]["en"] == valid[:-1])
        complete = {
            "key": "table/t_skill.tbl/whole-owner/description",
            "texts": {l: t + "\n" for l, t in admitted["texts"].items()},
        }
        denied = MenuTranslator(self.entries + [complete, collision], "ja", "zh-Hans", "en")
        modes = {}
        for mode in ("primary", "secondary", "annotation"):
            self.assertIsNone(denied.effect_detail_plan(valid, mode))
            plan = denied.render(valid, mode)
            self.assertEqual(plan["text"], valid, plan)
            self.assertEqual(plan["layers"], [], plan)
            modes[mode] = plan
        self.js_parity(denied, [{"source": valid, "modes": modes}])

    def js_parity(self, translator, cases):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r25-replay.json"
            path.write_text(
                json.dumps(
                    {"model": translator.runtime_model(), "rows": cases}, ensure_ascii=False
                ),
                encoding="utf8",
            )
            result = subprocess.run(
                ["node", "tests/check_r23_feedback.js", str(path)],
                capture_output=True,
                text=True,
                encoding="utf8",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            proof = json.loads(result.stdout.splitlines()[-1])
            runtime = Path("sora_bilingual/game/scripts/runtime_text.js").resolve()
            self.assertEqual(Path(proof["runtime_path"]).resolve(), runtime)
            self.assertEqual(
                proof["runtime_sha256"], hashlib.sha256(runtime.read_bytes()).hexdigest()
            )
            self.js_proofs.append(proof)


if __name__ == "__main__":
    unittest.main()
