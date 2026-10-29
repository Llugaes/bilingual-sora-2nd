"""Audit every proved NPC dispatch in the eight original script archives."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import (
    FpacArchive,
    _aligned_call_map,
    _logical_script_entries,
    assembled_dialogue,
    parse_scp,
)


def audit(game):
    counts, differences, failures, npc = {}, [], [], []
    with ExitStack() as stack:
        archives = {
            lang: stack.enter_context(FpacArchive(game / "pac/steam" / name))
            for lang, name in archive_names("script").items()
        }
        paths = {lang: _logical_script_entries(archive) for lang, archive in archives.items()}
        for path in sorted(paths["zh-Hans"]):
            scripts = {
                lang: parse_scp(archive.read(paths[lang][path]))
                for lang, archive in archives.items()
                if path in paths[lang]
            }
            for lang, script in scripts.items():
                for name, function in script.functions.items():
                    if name == "TK_GERVAIS":
                        npc.append(
                            {
                                "locale": lang,
                                "path": path,
                                "cases": function.branch_regions,
                                "text": [
                                    assembled_dialogue(c)
                                    for c in function.called
                                    if assembled_dialogue(c) is not None
                                ],
                            }
                        )
            for lang, script in scripts.items():
                if lang == "zh-Hans":
                    continue
                count = counts.setdefault(lang, Counter())
                count["scripts"] += 1
                for name in scripts["zh-Hans"].functions.keys() & script.functions.keys():
                    left, right = scripts["zh-Hans"].functions[name], script.functions[name]
                    a, b = left.branch_regions, right.branch_regions
                    if a is None and b is None:
                        continue
                    count["dispatch_functions"] += 1
                    pairs = _aligned_call_map(left, right)
                    if a is None or b is None:
                        count["one_side_unproved"] += 1
                        if pairs:
                            failures.append([path, name, lang, "unproved_branch_pair"])
                        continue
                    left_cases = {i: selector for selector, calls in a.items() for i in calls}
                    right_cases = {i: selector for selector, calls in b.items() for i in calls}
                    for i, j in pairs.items():
                        if left_cases.get(i) != right_cases.get(j):
                            failures.append([path, name, lang, i, j, "cross_case_pair"])
                        if assembled_dialogue(left.called[i]) is not None:
                            count["paired_dialogues"] += 1
                    if a.keys() != b.keys():
                        differences.append(
                            {
                                "locale": lang,
                                "path": path,
                                "function": name,
                                "zh_cases": a,
                                "target_cases": b,
                                "paired_calls": pairs,
                            }
                        )
    return {
        "scope": "physical branch selectors and calls; offline resources",
        "counts": counts,
        "case_differences": differences,
        "gervais_resources": npc,
        "failures": failures,
        "passed": not failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.game)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("gervais_resources", "case_differences")},
            ensure_ascii=False,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
