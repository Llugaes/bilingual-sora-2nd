import unittest

from sora_bilingual.localization.menu_text import MenuTranslator
from tools.audit_dialogue_coverage import audit, dialogue_records


def entry(number, source, secondary):
    texts = {"zh-Hans": source}
    if secondary is not None:
        texts["ja"] = secondary
    return {
        "key": f"script/test.dat/Talk/called/{number}/assembled_display",
        "display_role": "dialogue",
        "texts": texts,
    }


def model(entries):
    result = MenuTranslator(entries, "zh-Hans", "ja").runtime_model()
    result["script_identities"] = {
        "scripts": {
            "fixture": [
                {
                    "paths": ["script/test.dat"],
                    "functions": {
                        "Talk": {
                            "calls": {
                                str(i): {
                                    "records": [i],
                                    "model": MenuTranslator([e], "zh-Hans", "ja").runtime_model(),
                                }
                                for i, e in enumerate(entries)
                            }
                        }
                    },
                }
            ]
        }
    }
    return result


class DialogueCoverageTests(unittest.TestCase):
    def test_equal_punctuation_is_not_a_translation_gap(self):
        e = entry(0, "！！！", "!!!")
        result = audit([e], {})
        self.assertEqual(result["counts"]["no_secondary_needed_records"], 1)
        self.assertEqual(result["risks"], [])

    def test_conflicting_branches_remain_a_log_risk_even_with_valid_call_models(self):
        entries = [entry(0, "相同的对白。", "違う台詞。"), entry(1, "相同的对白。", "別の台詞。")]
        result = audit(entries, model(entries))
        self.assertEqual(result["counts"]["call_identity_required_records"], 2)
        self.assertEqual(result["counts"]["text_only_conflicting_sources"], 1)
        self.assertTrue(
            all(r["reason"] == "requires_call_identity_not_text_alone" for r in result["risks"])
        )

    def test_fragments_and_raw_display_duplicates_are_not_reported_as_missing_dialogue(self):
        display = entry(0, "完整对白。", "台詞。")
        raw = {**display, "key": display["key"].replace("assembled_display", "assembled_dialogue")}
        fragment = {"key": "script/test.dat/Talk/code/1", "texts": {"zh-Hans": "碎片"}}
        self.assertEqual(list(dialogue_records([raw, display, fragment])), [display])
        result = audit([raw, display, fragment], model([display]))
        self.assertEqual(result["counts"]["direct_global_pair_records"], 1)
        self.assertEqual(result["risks"], [])

    def test_missing_locale_is_not_mistaken_for_a_context_conflict(self):
        e = entry(0, "未配对白。", None)
        result = audit([e], model([e]))
        self.assertEqual(result["counts"]["missing_locale_records"], 1)
        self.assertEqual(result["risks"][0]["missing_locales"], ["ja"])

    def test_other_calls_cannot_resolve_this_record(self):
        entries = [entry(10, "相同的对白。", "違う台詞。"), entry(11, "相同的对白。", "別の台詞。")]
        result = audit(entries, model(entries))  # fixture only supplies calls 0 and 1
        self.assertEqual(result["counts"]["without_exact_resolver_route_records"], 2)
        self.assertNotIn("call_identity_required_records", result["counts"])
