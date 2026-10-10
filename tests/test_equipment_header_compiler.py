"""Exercise the production compiler with small, constructed semantic tables.

The constants/names are frozen official resource fields. These #TBL fixtures
validate compilation and refusal; they do not execute or reproduce native code.
"""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from sora_bilingual.localization import item_help_headers
from sora_bilingual.localization.menu_tables import record_identity, schema_for, sections


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/equipment-header-compiler.json").read_text("utf8")
)
SOURCE = os.environ.get("EQUIPMENT_HEADER_COMPILER_SOURCE")
if SOURCE:
    spec = importlib.util.spec_from_file_location("equipment_header_reference", SOURCE)
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
else:
    compiler = item_help_headers


def tbl(definitions):
    """Construct descriptors, zero-filled records and their own string pool."""
    end = 8 + 80 * len(definitions)
    places = []
    for kind, stride, records in definitions:
        places.append((kind, end, stride, records))
        end += stride * len(records)
    data = bytearray(end)
    data[:4] = b"#TBL"
    struct.pack_into("<I", data, 4, len(places))
    for section, (kind, start, stride, records) in enumerate(places):
        at = 8 + section * 80
        data[at : at + len(kind)] = kind.encode("ascii")
        struct.pack_into("<III", data, at + 68, start, stride, len(records))
        for index, record in enumerate(records):
            row = start + stride * index
            for offset, (fmt, value) in record.get("scalars", {}).items():
                struct.pack_into("<" + fmt, data, row + offset, value)
            for offset, text in record.get("strings", {}).items():
                struct.pack_into("<Q", data, row + offset, len(data))
                data.extend(text.encode("utf8") + b"\0")
            for offset, (count_offset, values) in record.get("arrays", {}).items():
                struct.pack_into("<Q", data, row + offset, len(data))
                struct.pack_into("<I", data, row + count_offset, len(values))
                data.extend(struct.pack("<" + "I" * len(values), *values))
    return bytes(data)


def item(identity, flags="", roles=(0xFFFF,), *, kind=12, upper_word=0, hp=0):
    return {
        "scalars": {
            0: ("I", identity),
            20: ("I", upper_word),
            40: ("B", kind),
            41: ("B", 9 if kind == 12 else 8),
            0x94: ("i", hp),
        },
        "strings": {24: "", 32: flags, 224: "fixture item", 232: "fixture body"},
        "arrays": {8: (16, roles)},
    }


class EquipmentHeaderCompilerTests(unittest.TestCase):
    def compile(
        self,
        items,
        *,
        language="zh-Hans",
        switch=0,
        alternate=False,
        statuses=True,
        conflict=False,
        missing_target=False,
        constants=None,
        hp_fields=None,
        missing_hp_target=False,
    ):
        constants = deepcopy(constants or FIXTURE["constants"])
        entries = [
            {
                "key": "table/t_text.tbl/TXT_ITEM_HELP_" + name,
                "texts": {
                    locale: values[name] for locale, values in constants.items() if name in values
                },
            }
            for name in constants[language]
        ]
        name_record = {
            "scalars": {0: ("I", 6), 72: ("H", switch)},
            "strings": {
                8: "deliberately different NameTable display",
                64: "chr5006p",
                80: "chr5006_alt" if alternate else "",
            },
        }
        status_definitions = []
        for section in range(2):
            records = []
            if statuses:
                for key in ("chr5006p", "chr5006_alt") if alternate else ("chr5006p",):
                    display = (
                        FIXTURE["role_names"][language] if key == "chr5006p" else "ALT-" + language
                    )
                    if conflict and section == 1:
                        display = "conflicting status name"
                    records.append({"strings": {0: key, 408: display}})
            status_definitions.append(("StatusParam", 424, records))
        status = tbl(status_definitions)
        floor = max(start + stride * count for _, start, stride, count in sections(status))
        for section, (_, start, stride, count) in enumerate(sections(status)):
            path = "table/t_status.tbl" if section == 0 else "table/t_status.tbl/StatusParam/1"
            for index in range(count):
                at = start + stride * index
                identity = record_identity(
                    status,
                    at,
                    "StatusParam",
                    schema_for("table/t_status.tbl", "StatusParam"),
                    floor,
                )
                model_key = "chr5006p" if index == 0 else "chr5006_alt"
                texts = {
                    locale: name if model_key == "chr5006p" else "ALT-" + locale
                    for locale, name in FIXTURE["role_names"].items()
                }
                if conflict and section == 1:
                    texts = dict.fromkeys(texts, "conflicting status name")
                if missing_target:
                    del texts["ja"]
                entries.append({"key": path + "/" + identity + "/name", "texts": texts})
        kinds = [
            {"scalars": {0: ("H", 12), 2: ("H", 9), 16: ("I", 6)}},
            {"scalars": {0: ("H", 11), 2: ("H", 8), 16: ("I", 4)}},
        ]
        hp_fields = deepcopy(hp_fields or FIXTURE["hp_status_fields"])
        hp = hp_fields[language]
        help_data = tbl(
            [
                ("ItemKindHelpData", 32, kinds),
                ("SkillRangeHelpData", 40, []),
                ("SkillTextArrayData", 24, []),
                ("SkillEffectHelpData", 88, []),
                ("SkillConnectListData", 24, []),
                (
                    "SkillItemStatusData",
                    48,
                    [
                        {
                            "scalars": {0: ("I", 0)},
                            "strings": {
                                8: hp["format"],
                                16: hp["name"],
                                24: hp["value"],
                                40: hp["colour"],
                            },
                        }
                    ],
                ),
            ]
        )
        layout = sections(help_data)
        _, hp_at, _, _ = next(row for row in layout if row[0] == "SkillItemStatusData")
        identity = record_identity(
            help_data,
            hp_at,
            "SkillItemStatusData",
            schema_for("table/t_itemhelp.tbl", "SkillItemStatusData"),
            max(start + stride * count for _, start, stride, count in layout),
        )
        hp_texts = {locale: fields["format"] for locale, fields in hp_fields.items()}
        if missing_hp_target:
            del hp_texts["ja"]
        entries.append(
            {
                "key": "table/t_itemhelp.tbl/SkillItemStatusData/" + identity + "/format",
                "texts": hp_texts,
            }
        )
        tables = {
            "table/t_item.tbl": tbl([("ItemTableData", 256, items)]),
            "table/t_itemhelp.tbl": help_data,
            "table/t_skill.tbl": tbl([("SkillPowerIcon", 16, [])]),
            "table/t_name.tbl": tbl([("NameTableData", 104, [name_record])]),
            "table/t_status.tbl": status,
        }

        class Archive:
            def __init__(self, _path):
                self.entries = tables

            def read(self, path):
                return tables[path]

            def close(self):
                pass

        with patch.object(compiler, "FpacArchive", Archive):
            return compiler.compile_item_help_headers(
                "unused-fixture-game", entries, "zh-Hans", "ja", language
            )

    def test_official_locales_preserve_prefix_and_frame_padding(self):
        for language in FIXTURE["constants"]:
            with self.subTest(language=language):
                result = self.compile(
                    [item(101, "DLM"), item(102, "DLF"), item(103, "DL", (6,))], language=language
                )
                rows = {row["item_id"]: row for row in result["compact_rows"]}
                self.assertEqual(set(rows), {101, 102, 103})
                for identity, name in ((101, "male"), (102, "female"), (103, "role")):
                    row = rows[identity]
                    self.assertEqual(row["prefix"], FIXTURE["expected"][language][name])
                    self.assertEqual(
                        row["close"],
                        [
                            FIXTURE["expected"][locale]["close"]
                            for locale in (language, "zh-Hans", "ja")
                        ],
                    )
                    self.assertEqual(
                        row["format_keys"],
                        [
                            "table/t_text.tbl/TXT_ITEM_HELP_FORMAT2",
                            "table/t_text.tbl/TXT_ITEM_HELP_FORMAT4",
                        ],
                    )
                    for target, locale in enumerate(("zh-Hans", "ja")):
                        self.assertEqual(
                            "".join(part["pair"][target] for part in row["parts"]),
                            FIXTURE["expected"][locale][name],
                        )
                self.assertNotIn("deliberately different", rows[103]["prefix"])
                self.assertEqual(rows[103]["parts"][0]["parameters"], ["6"])
                self.assertTrue(
                    all(row["family"] == "equipment_qualification" for row in rows.values())
                )

    def test_gender_priority_and_independent_role_append(self):
        result = self.compile(
            [
                item(101, "MF"),
                item(102, "M", (6,)),
                item(103, "F", (6,)),
                item(104, "", (6,), upper_word=0x1234),
            ]
        )
        rows = {row["item_id"]: row for row in result["compact_rows"]}
        self.assertEqual(rows[101]["prefix"], "男性专用【 ")
        self.assertEqual(rows[102]["prefix"], "男性专用缇妲专用【 ")
        self.assertEqual(rows[103]["prefix"], "女性专用缇妲专用【 ")
        self.assertEqual(rows[104]["prefix"], "缇妲专用【 ")

    def test_only_is_not_generated_for_other_kind_multiple_ids_or_sentinel(self):
        result = self.compile(
            [
                item(101, "", (6,), kind=11),
                item(102, "", (6, 7)),
                item(103),
                item(104, "", ()),
                item(105, "M", (6, 7)),
                item(106, "M", (7,)),
            ]
        )
        self.assertEqual(len(result["compact_rows"]), 1)
        row = result["compact_rows"][0]
        self.assertEqual(row["item_ids"], [105])
        self.assertEqual(row["prefix"], "男性专用【 ")
        self.assertNotIn(
            "table/t_text.tbl/TXT_ITEM_HELP_ONLY",
            {semantic for part in row["parts"] for semantic in part.get("semantic_ids", [])},
        )

    def test_alternate_switch_and_missing_or_conflicting_status_refuse_whole_role(self):
        for switch, expected in (
            (0, {"缇妲专用【 "}),
            (32768, {"缇妲专用【 "}),
            (1, {"缇妲专用【 ", "ALT-zh-Hans专用【 "}),
        ):
            with self.subTest(switch=switch):
                result = self.compile([item(101, "", (6,))], switch=switch, alternate=True)
                self.assertEqual({row["prefix"] for row in result["compact_rows"]}, expected)
        for options in ({"statuses": False}, {"conflict": True}, {"missing_target": True}):
            with self.subTest(options=options):
                result = self.compile([item(101, "M", (6,))], **options)
                self.assertEqual(result["compact_rows"], [])
                self.assertTrue(
                    any(key.startswith("equipment_rejected:") for key in result["audit"])
                )

    def test_unknown_printf_fields_and_invalid_frame_boundaries_are_rejected(self):
        for name, value in (
            ("FORMAT2", "[%sTAIL"),
            ("FORMAT2", "[%d"),
            ("FORMAT4", "%s] %s"),
            ("FORMAT4", "prefix%s]\n%s"),
            ("FORMAT4", "%s]\n%s%s"),
            ("ONLY", "%s%d"),
            ("MAIL_ONLY", "%x"),
        ):
            with self.subTest(name=name, value=value):
                constants = deepcopy(FIXTURE["constants"])
                constants["zh-Hans"][name] = value
                if name in ("ONLY", "MAIL_ONLY"):
                    result = self.compile([item(101, "M", (6,))], constants=constants)
                    self.assertEqual(result["compact_rows"], [])
                else:
                    with self.assertRaises(ValueError):
                        self.compile([item(101, "M", (6,))], constants=constants)
        for name, flag in (("MAIL_ONLY", "M"), ("FEMAIL_ONLY", "F")):
            for missing in (True, False):
                with self.subTest(gender=name, missing_target=missing):
                    constants = deepcopy(FIXTURE["constants"])
                    if missing:
                        del constants["ja"][name]
                    else:
                        constants["ja"][name] = " \t "
                    result = self.compile([item(101, flag, (6,))], constants=constants)
                    self.assertEqual(result["compact_rows"], [])
                    self.assertEqual(
                        result["audit"].get(
                            "equipment_rejected: equipment gender translation is missing"
                        ),
                        1,
                    )

    def test_positive_hp_uses_native_format_and_merges_only_physical_values(self):
        for language in FIXTURE["constants"]:
            with self.subTest(language=language):
                result = self.compile(
                    [
                        item(1052, "", (6,), hp=1500),
                        item(1053, "", (6,), hp=3000),
                        item(101, "M"),
                        item(102, "", (7,), hp=4500),
                        item(103, "", (0xFFFF,), hp=6000),
                    ],
                    language=language,
                )
                row = next(row for row in result["compact_rows"] if row["item_ids"] == [1052, 1053])
                owned = row["owned_effect_units"]
                self.assertEqual(
                    set(owned),
                    {FIXTURE["hp_status_fields"][language][str(amount)] for amount in (1500, 3000)},
                )
                for amount in (1500, 3000):
                    unit = owned[FIXTURE["hp_status_fields"][language][str(amount)]]
                    self.assertEqual(
                        unit["pair"],
                        [
                            FIXTURE["hp_status_fields"][locale][str(amount)]
                            for locale in ("zh-Hans", "ja")
                        ],
                    )
                    self.assertEqual(unit["parameters"], [str(amount)])
                    self.assertEqual(unit["semantic_ids"], [FIXTURE["semantic_hp_format_key"]])
                self.assertFalse(
                    next(row for row in result["compact_rows"] if row["item_ids"] == [101]).get(
                        "owned_effect_units"
                    )
                )
        for fields in ("%s", "%d%d", "%f"):
            with self.subTest(hp_format=fields):
                hp_fields = deepcopy(FIXTURE["hp_status_fields"])
                hp_fields["zh-Hans"]["format"] = fields
                result = self.compile([item(1052, "", (6,), hp=1500)], hp_fields=hp_fields)
                self.assertEqual(result["compact_rows"], [])
        result = self.compile([item(1052, "", (6,), hp=1500)], missing_hp_target=True)
        self.assertEqual(result["compact_rows"], [])


if __name__ == "__main__":
    unittest.main()
