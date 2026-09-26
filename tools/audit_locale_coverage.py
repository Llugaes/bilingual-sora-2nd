"""Offline resource coverage audit; it never estimates on-screen translation coverage."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from sora_bilingual.config.locales import LANGUAGES


def complete_texts(entry):
    texts = entry.get("texts", {})
    return all(
        isinstance(texts.get(language), str) and texts[language].strip() for language in LANGUAGES
    )


def scoped_records(entries):
    display = {e["key"] for e in entries if "/assembled_display" in e.get("key", "")}
    dialogue, table = [], []
    for entry in entries:
        key = entry.get("key", "")
        if key.startswith("table/"):
            table.append(entry)
        elif "/assembled_display" in key or (
            "/assembled_dialogue" in key
            and key.replace("/assembled_dialogue", "/assembled_display") not in display
        ):
            dialogue.append(entry)
    return {"complete_dialogue": dialogue, "table_entries": table}


def conflict_summary(records, limit=100):
    groups = defaultdict(lambda: defaultdict(list))
    for entry in records:
        if not complete_texts(entry):
            continue
        for source_language in LANGUAGES:
            groups[source_language][entry["texts"][source_language]].append(entry)
    examples, affected, values = [], 0, 0
    for language, by_value in groups.items():
        for source, rows in by_value.items():
            variants = defaultdict(list)
            for row in rows:
                variants[tuple(row["texts"][target] for target in LANGUAGES)].append(row["key"])
            if len(variants) > 1:
                values += 1
                affected += len(rows)
                if len(examples) < limit:
                    examples.append(
                        {
                            "source_language": language,
                            "source": source,
                            "variants": [
                                {"targets": dict(zip(LANGUAGES, target)), "keys": keys[:10]}
                                for target, keys in variants.items()
                            ],
                        }
                    )
    return {
        "source_values": values,
        "affected_records": affected,
        "examples": examples,
        "examples_truncated": values > len(examples),
    }


def audit(entries):
    scopes = {}
    for name, records in scoped_records(entries).items():
        missing = Counter()
        missing_examples = []
        for entry in records:
            absent = [
                language
                for language in LANGUAGES
                if not isinstance(entry.get("texts", {}).get(language), str)
                or not entry["texts"][language].strip()
            ]
            missing.update(absent)
            if absent and len(missing_examples) < 100:
                missing_examples.append({"key": entry["key"], "missing_locales": absent})
        scopes[name] = {
            "records": len(records),
            "complete_all_8": len(records)
            - sum(
                1
                for entry in records
                if any(
                    not isinstance(entry.get("texts", {}).get(l), str)
                    or not entry["texts"][l].strip()
                    for l in LANGUAGES
                )
            ),
            "missing_any_locale": sum(
                1
                for entry in records
                if any(
                    not isinstance(entry.get("texts", {}).get(l), str)
                    or not entry["texts"][l].strip()
                    for l in LANGUAGES
                )
            ),
            "missing_by_locale": dict(missing),
            "missing_examples": missing_examples,
            "same_source_different_targets": conflict_summary(records),
        }
    return {
        "scope": "resource records only: complete dialogue and table entries; bytecode/script argument fragments are excluded",
        "not_screen_untranslated_count": True,
        "languages": list(LANGUAGES),
        "scopes": scopes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "generated/catalog.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "generated/locale-coverage-audit.json",
    )
    args = parser.parse_args()
    report = audit(json.loads(args.catalog.read_text(encoding="utf-8"))["entries"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                name: {
                    "records": item["records"],
                    "complete_all_8": item["complete_all_8"],
                    "missing_any_locale": item["missing_any_locale"],
                    "conflicts": item["same_source_different_targets"]["source_values"],
                }
                for name, item in report["scopes"].items()
            }
        )
    )


if __name__ == "__main__":
    main()
