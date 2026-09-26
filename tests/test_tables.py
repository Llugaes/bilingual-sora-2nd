import struct
import tempfile
import unittest
from pathlib import Path

from sora_bilingual.localization.resources import LANGUAGES
from sora_bilingual.localization.tables import build_table_entries
from sora_bilingual.localization.menu_tables import SCHEMAS, record_identity


ARCHIVES = {
    "ja": "table.pac",
    "en": "table_en.pac",
    "zh-Hans": "table_sc.pac",
    "zh-Hant": "table_tc.pac",
    "ko": "table_ko.pac",
    "fr": "table_fr.pac",
    "de": "table_de.pac",
    "es": "table_es.pac",
}


class ActiveVoiceIdentityTests(unittest.TestCase):
    def record(self, padding=0, voice=100, speaker=3, condition=9):
        data = bytearray(128 + padding)
        struct.pack_into("<Q", data, 0, 39)
        for offset, values, width in (
            (8, [speaker], 2),
            (48, [condition], 2),
            (64, [], 2),
            (80, [], 2),
            (96, [voice], 4),
        ):
            struct.pack_into("<QQ", data, offset, len(data), len(values))
            data.extend(b"".join(v.to_bytes(width, "little") for v in values))
        for offset, value in ((24, b"\0"), (40, b"N\0"), (112, b"Localized body\0")):
            struct.pack_into("<Q", data, offset, len(data))
            data.extend(value)
        return data

    def test_addresses_do_not_change_identity_but_conditions_and_voice_do(self):
        schema = SCHEMAS["ActiveVoiceTableData"]
        identity = lambda d: record_identity(d, 0, "ActiveVoiceTableData", schema, 128)
        base = identity(self.record())
        self.assertEqual(base, identity(self.record(padding=31)))
        for change in ({"voice": 101}, {"speaker": 4}, {"condition": 10}):
            self.assertNotEqual(base, identity(self.record(**change)))


def fpac(entries):
    names = [name.encode() + b"\0" for name, _ in entries]
    table_end = 16 + 32 * len(entries)
    name_offsets = []
    cursor = table_end
    for name in names:
        name_offsets.append(cursor)
        cursor += len(name)
    data_at = cursor
    result = bytearray(data_at + sum(len(data) for _, data in entries))
    struct.pack_into("<4sIII", result, 0, b"FPAC", len(entries), data_at, 1)
    for number, ((_, data), name, name_at) in enumerate(zip(entries, names, name_offsets)):
        struct.pack_into("<IIQQQ", result, 16 + 32 * number, 0, 0, name_at, len(data), cursor)
        result[name_at : name_at + len(name)] = name
        result[cursor : cursor + len(data)] = data
        cursor += len(data)
    return bytes(result)


def text_table(pairs):
    rows = 88 + 16 * len(pairs)
    payload = bytearray(rows)
    struct.pack_into("<4sI64sIIII", payload, 0, b"#TBL", 1, b"TextTableData", 0, 88, 16, len(pairs))
    cursor = rows
    for number, (key, text) in enumerate(pairs):
        key = key.encode() + b"\0"
        text = text.encode() + b"\0"
        struct.pack_into("<QQ", payload, 88 + number * 16, cursor, cursor + len(key))
        payload.extend(key)
        payload.extend(text)
        cursor += len(key) + len(text)
    return bytes(payload)


def item_table(item_id, name, description):
    start, row_size = 168, 256
    bundle = start + row_size + 16
    payload = bytearray(bundle)
    struct.pack_into("<4sI64sIIII", payload, 0, b"#TBL", 2, b"ItemTableData", 0, start, row_size, 1)
    struct.pack_into("<64sIIII", payload, 88, b"ItemKindParam2", 0, start + row_size, 16, 1)
    struct.pack_into("<Q", payload, start + 224, bundle)
    struct.pack_into("<Q", payload, start + 232, bundle + len(name.encode()) + 1)
    struct.pack_into("<I", payload, start, item_id)
    payload.extend(name.encode() + b"\0" + description.encode() + b"\0")
    struct.pack_into("<IQ", payload, start + row_size + 4, 7, len(payload))
    payload.extend(("category " + name).encode() + b"\0")
    return bytes(payload)


def help_table(title):
    start, row_size = 88, 24
    payload = bytearray(start + row_size)
    struct.pack_into("<4sI64sIIII", payload, 0, b"#TBL", 1, b"HelpTitle", 0, start, row_size, 1)
    struct.pack_into("<I", payload, start, 1)  # stable, non-localised help id
    struct.pack_into("<Q", payload, start + 8, start + row_size)
    payload.extend(title.encode() + b"\0")
    return bytes(payload)


def tips_table(language):
    row_size, count, start = 56, 3, 88
    payload = bytearray(start + row_size * count)
    struct.pack_into(
        "<4sI64sIIII", payload, 0, b"#TBL", 1, b"TipsTableData", 0, 88, row_size, count
    )
    cursor = len(payload)
    for row, marker in enumerate((0, 0, 1)):
        title = f"{language} duplicate {row}" if row < 2 else f"{language} unique"
        body = f"{language} body {row}"
        at = start + row * row_size
        struct.pack_into("<I", payload, at, marker)
        struct.pack_into("<QQ", payload, at + 40, cursor, cursor + len(title.encode()) + 1)
        payload.extend(title.encode() + b"\0" + body.encode() + b"\0")
        cursor += len(title.encode()) + len(body.encode()) + 2
    return bytes(payload)


def note_history_table(rows):
    start, row_size = 88, 8
    payload = bytearray(start + row_size * len(rows))
    struct.pack_into(
        "<4sI64sIIII", payload, 0, b"#TBL", 1, b"NoteMainHistory", 0, start, row_size, len(rows)
    )
    cursor = len(payload)
    for number, text in enumerate(rows):
        encoded = text.encode() + b"\0"
        struct.pack_into("<Q", payload, start + number * row_size, cursor)
        payload.extend(encoded)
        cursor += len(encoded)
    return bytes(payload)


def dlc_table(dlc_id, name, description, item_ids=(0x0BAA,), quantities=(1,), pool_prefix=b""):
    if len(item_ids) != len(quantities):
        raise ValueError("DLC item ids and quantities must have equal length")
    start, row_size = 88, 64
    payload = bytearray(start + row_size)
    struct.pack_into("<4sI64sIIII", payload, 0, b"#TBL", 1, b"DLCTableData", 0, start, row_size, 1)
    struct.pack_into("<II", payload, start, dlc_id, dlc_id)
    payload.extend(pool_prefix)
    cursor = len(payload)
    for offset, values in ((8, item_ids), (24, quantities)):
        struct.pack_into("<QQ", payload, start + offset, cursor, len(values))
        payload.extend(struct.pack(f"<{len(values)}I", *values))
        cursor += 4 * len(values)
    encoded_name = name.encode() + b"\0"
    encoded_description = description.encode() + b"\0"
    struct.pack_into(
        "<QQQ",
        payload,
        start + 40,
        cursor,
        cursor + len(encoded_name),
        cursor + len(encoded_name) + len(encoded_description),
    )
    payload.extend(encoded_name + encoded_description + b"\0")
    return bytes(payload)


def write_game(root, missing_en=False, history=False):
    folder = root / "pac" / "steam"
    folder.mkdir(parents=True)
    for language, archive in ARCHIVES.items():
        entries = [(f"table_{language}/t_text.tbl", text_table([("MENU_OK", f"{language} OK")]))]
        entries.append(
            (
                f"table_{language}/t_dlc.tbl",
                dlc_table(
                    9001,
                    f"{language} DLC name",
                    f"{language} DLC description",
                    pool_prefix=language.encode() * 3,
                ),
            )
        )
        if not (missing_en and language == "en"):
            entries.append(
                (
                    f"table_{language}/t_item.tbl",
                    item_table(0x1B7000, f"{language} item", f"{language} desc"),
                )
            )
        unknown = bytearray(88)
        struct.pack_into("<4sI64sIIII", unknown, 0, b"#TBL", 1, b"SkillParam", 0, 88, 4, 0)
        entries.append((f"table_{language}/t_skill.tbl", bytes(unknown)))
        entries.append((f"table_{language}/t_help.tbl", help_table(f"{language} help")))
        entries.append((f"table_{language}/t_tips.tbl", tips_table(language)))
        if history:
            rows = [f"{language} history {number}" for number in range(3)]
            if language == "zh-Hans":
                rows = [
                    "【游击士协会规章·基本三原则】",
                    "第一条“基本理念”",
                    " 游击士应跨越国家藩篱，",
                ]
            elif language == "ja":
                rows = [
                    "【遊撃士協会規約・基本三項目】",
                    "第一項『基本理念』",
                    " 遊撃士は、国家の枠組みを越えて",
                ]
            entries.append((f"table_{language}/t_notemenu.tbl", note_history_table(rows)))
        (folder / archive).write_bytes(fpac(entries))


class TableTests(unittest.TestCase):
    def test_table_keys_do_not_require_a_japanese_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root)
            (root / "pac/steam" / ARCHIVES["ja"]).unlink()
            entries, _ = build_table_entries(root)
            row = next(e for e in entries if e["key"] == "table/t_text.tbl/MENU_OK")
            self.assertIn("fr", row["texts"])
            self.assertIn("de", row["texts"])
            self.assertNotIn("ja", row["texts"])

    def test_text_keys_and_item_ids_are_stable_not_ordinals(self):
        with tempfile.TemporaryDirectory() as temp:
            write_game(Path(temp))
            entries, audit = build_table_entries(temp)
        keyed = {entry["key"]: entry["texts"] for entry in entries}
        self.assertEqual(keyed["table/t_text.tbl/MENU_OK"]["zh-Hans"], "zh-Hans OK")
        item_name = next(
            key
            for key in keyed
            if key.endswith("/name") and key.startswith("table/t_item.tbl/sha256:")
        )
        item_description = item_name.removesuffix("/name") + "/description"
        self.assertEqual(keyed[item_name]["en"], "en item")
        self.assertEqual(keyed[item_description]["ja"], "ja desc")
        self.assertTrue(
            any(row["path"] == "table/t_skill.tbl" for row in audit["unsupported_tables"])
        )
        help_entry = next(
            entry
            for entry in entries
            if entry["key"].startswith("table/t_help.tbl/sha256:")
            and entry["key"].endswith("/title")
        )
        self.assertEqual(help_entry["texts"]["en"], "en help")
        category = next(e for e in entries if "/ItemKindParam2/" in e["key"])
        self.assertEqual(category["texts"]["ja"], "category ja item")
        self.assertEqual(category["texts"]["zh-Hans"], "category zh-Hans item")

    def test_missing_item_locale_does_not_drop_other_valid_locales(self):
        with tempfile.TemporaryDirectory() as temp:
            write_game(Path(temp), missing_en=True)
            entries, _audit = build_table_entries(temp)
        item = next(
            entry
            for entry in entries
            if entry["key"].startswith("table/t_item.tbl/") and entry["key"].endswith("/name")
        )
        self.assertNotIn("en", item["texts"])
        self.assertIn("zh-Hant", item["texts"])

    def test_dlc_payload_identity_aligns_all_languages_despite_localized_string_offsets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_game(root)
            entries, _audit = build_table_entries(root)
        dlc_entries = [entry for entry in entries if entry["key"].startswith("table/t_dlc.tbl/")]
        self.assertEqual(len(dlc_entries), 2)
        for entry in dlc_entries:
            self.assertEqual(set(entry["texts"]), set(LANGUAGES))
        self.assertEqual(
            next(entry for entry in dlc_entries if entry["key"].endswith("/name"))["texts"],
            {language: f"{language} DLC name" for language in LANGUAGES},
        )

    def test_dlc_identity_retains_item_payload_not_its_addresses(self):
        schema = SCHEMAS["DLCTableData"]
        first = dlc_table(9001, "short", "short", (10, 20), (1, 2))
        moved_addresses = dlc_table(
            9001,
            "a much longer localized name",
            "description",
            (10, 20),
            (1, 2),
            b"preceding translated pool data\0",
        )
        changed_payload = dlc_table(9001, "short", "short", (10, 21), (1, 2))
        identity = lambda data: record_identity(data, 88, "DLCTableData", schema, 152)
        self.assertEqual(identity(first), identity(moved_addresses))
        self.assertNotEqual(identity(first), identity(changed_payload))

    def test_missing_archive_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                build_table_entries(Path(temp))

    def test_ambiguous_duplicate_groups_are_dropped_without_dropping_table(self):
        with tempfile.TemporaryDirectory() as temp:
            write_game(Path(temp))
            entries, audit = build_table_entries(temp)
        tips = [entry for entry in entries if entry["key"].startswith("table/t_tips.tbl/")]
        self.assertEqual(len(tips), 2)  # the unique title/body record survives
        self.assertTrue(
            any(row["path"] == "table/t_tips.tbl" for row in audit["ambiguous_duplicate_groups"])
        )

    def test_ordered_note_history_uses_its_stable_row_resource_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            write_game(Path(temp), history=True)
            entries, audit = build_table_entries(temp)

        history = {
            entry["key"]: entry["texts"]
            for entry in entries
            if entry["key"].startswith("table/t_notemenu.tbl/row:")
        }
        self.assertEqual(len(history), 3)
        self.assertEqual(
            history["table/t_notemenu.tbl/row:0/body"]["zh-Hans"],
            "【游击士协会规章·基本三原则】",
        )
        self.assertEqual(
            history["table/t_notemenu.tbl/row:0/body"]["ja"],
            "【遊撃士協会規約・基本三項目】",
        )
        self.assertEqual(
            history["table/t_notemenu.tbl/row:2/body"]["ja"],
            " 遊撃士は、国家の枠組みを越えて",
        )
        self.assertFalse(
            any(
                row["path"] == "table/t_notemenu.tbl" for row in audit["ambiguous_duplicate_groups"]
            )
        )


if __name__ == "__main__":
    unittest.main()
