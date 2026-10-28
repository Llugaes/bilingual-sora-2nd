import unittest

from tools.audit_dynamic_coverage import audit


class DynamicCoverageAuditTests(unittest.TestCase):
    def test_raw_unknowns_and_missing_targets_survive_aligned_compiler_join(self):
        root = "script/scena/test.dat/Talk/called/"
        raw = {
            "scripts": {
                "unassembled_text_calls": [
                    {"language": "zh-Hans", "key": root + str(i), "reason": "dynamic_operand"}
                    for i in range(3)
                ]
            }
        }
        entries = [
            {
                "key": "dynamic/" + root + str(i),
                "texts": {"zh-Hans": "Source", **({"ja": "Target"} if i == 0 else {})},
                "dynamic_producer": {"family": "static_item_panel"},
                "producer_origin": {
                    "signature": {
                        "path": "script/scena/test.dat",
                        "function": "Talk",
                        "called": 20 + i,
                    }
                },
                "called_ids": {"zh-Hans": i},
            }
            for i in range(2)
        ]
        result = audit(raw, entries, "zh-Hans", "ja")
        self.assertEqual(result["raw_call_denominator"], 3)
        self.assertEqual(
            result["counts"],
            {
                "compiled_route": 1,
                "compiled_with_target_gap": 1,
                "unclassified": 1,
            },
        )
        self.assertFalse(result["all_classified"])
        self.assertEqual(result["rows"][2]["key"], root + "2")
