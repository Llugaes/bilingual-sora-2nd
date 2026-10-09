import struct
import unittest
from unittest.mock import patch

from sora_bilingual.localization.menu_tables import record_identity, schema_for
from sora_bilingual.localization.runtime_identity import compile_table_identities


class TipsPostloadCompilerTests(unittest.TestCase):
    def test_compiler_marks_only_proven_tips_title_body_records(self):
        data = bytearray(144)
        struct.pack_into("<4sI64sIIII", data, 0, b"#TBL", 1, b"TipsTableData", 0, 88, 56, 1)
        struct.pack_into("<HHI", data, 88, 7, 107, 16031)
        for off, value in [(8, ""), (24, "NP"), (40, "Shared"), (48, "Body")]:
            struct.pack_into("<Q", data, 88 + off, len(data))
            data.extend(value.encode() + b"\0")
        raw = bytes(data)
        schema = schema_for("table/t_tips.tbl", "TipsTableData")
        key = "table/t_tips.tbl/" + record_identity(raw, 88, "TipsTableData", schema, 144)

        class Archive:
            entries = {"table_en/t_tips.tbl": (0, len(raw))}

            def __init__(self, *_):
                pass

            def read(self, *_):
                return raw

            def close(self):
                pass

        entries = [
            {"key": key + "/" + field, "texts": {"en": source, "ja": target}}
            for field, source, target in [("title", "Shared", "Title"), ("body", "Body", "Text")]
        ]
        with patch("sora_bilingual.localization.runtime_identity.FpacArchive", Archive):
            model = compile_table_identities(".", entries, "en", "ja", "en", resolved_pairs={})
        for source in ("Shared", "Body"):
            candidates = model["sources"][source]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["record_kind"], "TipsTableData")
            self.assertEqual(candidates[0]["record_transform"], "tips_u16_flag_add7400_cap7799_v1")
            self.assertEqual(bytes.fromhex(candidates[0]["record"])[2:4], struct.pack("<H", 107))


if __name__ == "__main__":
    unittest.main()
