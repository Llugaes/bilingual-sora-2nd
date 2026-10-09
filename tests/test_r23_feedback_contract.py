"""Whole reported constructors from PAC fields; no positive owner injection."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from sora_bilingual.localization.item_help_composition import compile_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator

FIXTURE = Path(__file__).parent / "fixtures/r23-resource-constructors.json"


def compiled_entries():
    f = json.loads(FIXTURE.read_text("utf8"))
    grammar = compile_item_help_grammar(
        f["entries"],
        "en",
        f["metadata"],
        f["groups"],
        actual_contexts=f["contexts"],
        connect_groups=f["connect_groups"],
    )
    return f["entries"] + grammar["detail_entries"], grammar


def reported_rows(entries):
    body = "A small doll that breaks when protecting its owner from harm.  "
    breathing = next(
        e["texts"]["en"]
        for e in entries
        if "Rouse the user's spirit via disciplined breathing techniques."
        in e.get("texts", {}).get("en", "")
    )
    rows = []
    for arrow in ("<I270>", "<I271>", "↑", "↑↑"):
        rows.append(
            (
                "DEF_ADF_" + arrow,
                "<c698>DEF/ADF" + arrow + "(5 turns)</C>\n" + breathing,
                ["turns", breathing],
            )
        )
    for arrow in ("<I267>", "<I268>", "↓", "↓↓"):
        rows.append(
            (
                "all_stats_" + arrow,
                "<c698>All Stats" + arrow + "</C>\n" + breathing,
                ["All Stats", breathing],
            )
        )
    for decorated in (False, True):
        atom = (
            "<c698>Remove Debuff</C><c698>/</C><c698>Immunity</C>"
            if decorated
            else "<c698>Remove Debuff/Immunity</C>"
        )
        rows.append(
            (
                "immunity_" + str(decorated),
                atom + "\n" + breathing,
                ["Remove Debuff", "Immunity", breathing],
            )
        )
        event = (
            "<c698>Upon Action</C><c698>, </C><c698>CP+25</C>"
            if decorated
            else "<c698>Upon Action / CP+25</C>"
        )
        rows.append(
            (
                "event_" + str(decorated),
                "[<c698>STR/ATS+100</C> - <c698>SPD+25</C> - " + event + "]\n" + body,
                ["Upon Action", body],
            )
        )
    dolls = [
        e["texts"]["en"]
        for e in entries
        if e.get("key", "").endswith("/description")
        and "doll that breaks when protecting its owner" in e.get("texts", {}).get("en", "")
    ]
    for description in dict.fromkeys(dolls):
        amount, cp = (
            (100, 200)
            if "gold doll" in description
            else (
                (90, 90)
                if "large doll" in description
                else ((10, 10) if "small doll" in description else (30, 30))
            )
        )
        for padding in (True, False):
            displayed = description if padding else description.rstrip(" \t")
            for colored in (True, False):
                header = (
                    "[<c698>DEF/ADF+25</C> - <c698>Recover "
                    + str(amount)
                    + "% HP & EP/CP+"
                    + str(cp)
                    + " before KO</C>]"
                )
                if not colored:
                    header = header.replace("<c698>", "").replace("</C>", "")
                rows.append(
                    (
                        "doll_" + str(amount) + "_" + str(padding) + "_" + str(colored),
                        header + "\n" + displayed,
                        ["before KO", description.rstrip(" \t")],
                    )
                )
    for sex in ("Male Only ", "Female Only "):
        for position in ("inside", "after", "before"):
            header = "[<c698>STR+20</C> - <c698>CRT+20%</C>"
            header = (
                header + " - <c698>" + sex + "</C>]"
                if position == "inside"
                else (header + "] " + sex if position == "after" else sex + header + "]")
            )
            rows.append((sex + position, header + "\n" + body, [sex.rstrip(), body]))
    return rows


def unproven_parameter_rows():
    body = "A small doll that breaks when protecting its owner from harm.  "
    rows = []
    for value in ("10.5", "mystery", "", "NaN", "1e3", "0x10", "--10", "+ 10"):
        for slot in (0, 1):
            values = [value, "10"] if slot == 0 else ["10", value]
            member = f"Recover {values[0]}% HP & EP/CP+{values[1]} before KO"
            for colored in (False, True):
                header = "[DEF/ADF+25 - " + member + "]"
                if colored:
                    header = "[<c698>DEF/ADF+25</C> - <c698>" + member + "</C>]"
                rows.append((f"unproven_{value}_{slot}_{colored}", header + "\n" + body))
    return rows


class R23FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries, cls.grammar = compiled_entries()

    def test_complete_details_three_final_modes_and_javascript_parity(self):
        rendered = []
        for name, source, forbidden in reported_rows(self.entries):
            modes = {}
            for mode in ("primary", "secondary", "annotation"):
                tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
                plan = tr.render(source, mode)
                visible = plan["text"] + "".join(l["text"] for l in plan["layers"])
                for token in forbidden:
                    self.assertNotIn(token, visible, (name, mode, plan))
                self.assertIsNotNone(tr.effect_detail_plan(source, mode), name)
                modes[mode] = plan
            rendered.append({"name": name, "source": source, "modes": modes})
        model = MenuTranslator(self.entries, "ja", "zh-Hans", "en").runtime_model()
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "replay.json"
            data.write_text(
                json.dumps({"model": model, "rows": rendered}, ensure_ascii=False), encoding="utf8"
            )
            result = subprocess.run(
                ["node", "tests/check_r23_feedback.js", str(data)],
                capture_output=True,
                text=True,
                encoding="utf8",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_strict_save_translator_full_titles_party_levels_and_scope(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        saved = tr.scoped["save_summary"]
        chinese_name = next(
            e["texts"]["zh-Hans"]
            for e in self.entries
            if e.get("key", "").startswith("table/t_name.tbl/")
            and e.get("texts", {}).get("en") == "Estelle"
        )
        rows = [
            "Final Chapter: Trails in the Sky [Very Easy]",
            "Final Chapter: Trails in the Sky＜Nightmare＞",
            " [Nightmare]",
            "-Estelle     Lv.90",
            "-Joshua",
            "-Agate",
            "-Scherazard",
            "-" + chinese_name,
        ]
        for source in rows:
            for mode in ("primary", "secondary", "annotation"):
                plan = saved.render(source, mode)
                self.assertNotEqual(plan["text"], source, (source, mode))
                if "Lv.90" in source:
                    self.assertIn("Lv.90", plan["text"])
                self.assertNotIn("Very Easy", plan["text"])
                self.assertNotIn("Nightmare", plan["text"])
        # The display localization belongs only to the strict save surface.
        self.assertNotIn("ナイトメア", tr.translate(" [Nightmare]", "primary"))
        for source in ["-Unknown Hero", "Final Chapter: Trails in the Sky [Mystery]"]:
            self.assertEqual(saved.render(source)["text"], source)

    def test_compound_veto_overflow_unknown_controls_and_parameter_roles(self):
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        for text in ["Recover 2147483648% HP & EP/CP+10 before KO", "Upon Action, CP+2147483648"]:
            self.assertIsNone(tr.details.effect_units(text), text)
        for text in ["Upon Action, mystery+25", "All Stats<I999>", "All Stats↔"]:
            self.assertIsNone(tr.details._effect_unit(text), text)
        for text in ["Upon Action", "before KO"]:
            self.assertIsNone(tr.details._effect_unit(text), text)

    def test_unproven_integer_slots_refuse_final_formatter_and_keep_exact_body(self):
        rendered = []
        tr = MenuTranslator(self.entries, "ja", "zh-Hans", "en")
        for name, source in unproven_parameter_rows():
            header, body = source.split("\n", 1)
            modes = {}
            for mode in ("annotation", "secondary", "primary"):
                plan = tr.render(source, mode)
                expected_body = tr.details.render(body, mode)
                self.assertEqual(plan["text"], header + "\n" + expected_body["text"], (name, mode))
                self.assertNotEqual(expected_body["text"], body)
                self.assertEqual(tr.effect_unit_failures[source], "unproven_effect_parameter")
                modes[mode] = plan
            rendered.append({"name": name, "source": source, "modes": modes})
        for value in ("2147483648", "-2147483649", "9" * 100):
            for slot in (0, 1):
                values = [value, "10"] if slot == 0 else ["10", value]
                member = f"Recover {values[0]}% HP & EP/CP+{values[1]} before KO"
                for colored in (False, True):
                    source = ("<c698>" + member + "</C>") if colored else member
                    modes = {
                        mode: tr.render(source, mode)
                        for mode in ("annotation", "secondary", "primary")
                    }
                    for mode, plan in modes.items():
                        self.assertEqual(
                            plan, {"text": source, "layers": [], "kind": "plain"}, (source, mode)
                        )
                    rendered.append(
                        {"name": "out_of_range_" + str(slot), "source": source, "modes": modes}
                    )
        # Independent unknown text must not be absorbed into a numeric slot.
        body = "A small doll that breaks when protecting its owner from harm.  "
        for source in [
            "[DEF/ADF+25 - Unknown 40%]\n" + body,
            "[Recover 10% HP & EP/CP+10 before KO, Unknown 40%]\n" + body,
        ]:
            modes = {}
            for mode in ("annotation", "primary", "secondary"):
                plan = tr.render(source, mode)
                self.assertIn("Unknown 40%", plan["text"])
                self.assertNotIn("before KO", plan["text"])
                self.assertNotIn(body, plan["text"])
                modes[mode] = plan
            rendered.append({"name": "unknown_text_neighbour", "source": source, "modes": modes})
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "unproven.json"
            data.write_text(
                json.dumps({"model": tr.runtime_model(), "rows": rendered}, ensure_ascii=False),
                encoding="utf8",
            )
            result = subprocess.run(
                ["node", "tests/check_r23_feedback.js", str(data)],
                capture_output=True,
                text=True,
                encoding="utf8",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
