"""Audit complete dialogue records and context-loss risks without attaching to a game.

This is a resource/resolver audit, not proof of in-game surface coverage. In
particular, a compiled call identity is useful only while the native caller
actually supplies that identity; a log's copied text alone cannot recover it.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from sora_bilingual.localization.menu_text import complete_pair, needs_annotation, plain


def dialogue_records(entries):
    """Prefer the displayed block; don't count bytecode fragments as missing UI."""
    entries = list(entries)
    keys = {entry.get("key") for entry in entries}
    for entry in entries:
        key = entry.get("key", "")
        if entry.get("display_role") != "dialogue":
            continue
        if "/assembled_display" in key:
            yield entry
        elif (
            "/assembled_dialogue" in key
            and key.replace("/assembled_dialogue", "/assembled_display") not in keys
        ):
            yield entry


def _matches(model, source, expected):
    actual = model.get("pairs", {}).get(source)
    if actual is not None and tuple(actual) == expected:
        return True
    actual = model.get("plain_pairs", {}).get(plain(source))
    return actual is not None and tuple(actual) == tuple(plain(t) for t in expected)


def audit(entries, model, primary="zh-Hans", secondary="ja", source_language="zh-Hans"):
    calls = defaultdict(list)
    scripts = model.get("script_identities", {})
    for bucket in scripts.get("scripts", {}).values():
        for script in bucket:
            for path in script["paths"]:
                for function, context in script["functions"].items():
                    for call in context.get("calls", {}).values():
                        for number in call["records"]:
                            calls[f"{path}/{function}/called/{number}"].append(call["model"])

    counts = Counter()
    sources = defaultdict(set)
    risks = []
    for entry in dialogue_records(entries):
        counts["complete_dialogue_records"] += 1
        texts = entry["texts"]
        source = texts.get(source_language)
        if not source or not source.strip():
            counts["without_source_language"] += 1
            continue
        counts["source_records"] += 1
        expected = complete_pair(texts, primary, secondary)
        missing = [
            language
            for language in dict.fromkeys((primary, secondary))
            if not texts.get(language, "").strip()
        ]
        reason = None
        if missing:
            counts["missing_locale_records"] += 1
            reason = "missing_locale"
        else:
            counts["complete_pair_records"] += 1
            sources[source].add(expected)
            if not needs_annotation(*expected):
                counts["no_secondary_needed_records"] += 1
                continue
            if _matches(model, source, expected):
                counts["direct_global_pair_records"] += 1
                continue
            key = entry["key"]
            call_key = key.split("/assembled_", 1)[0]
            contexts = calls.get(call_key, [])
            if contexts and all(_matches(context, source, expected) for context in contexts):
                counts["call_identity_required_records"] += 1
                reason = "requires_call_identity_not_text_alone"
            else:
                counts["without_exact_resolver_route_records"] += 1
                reason = "no_exact_pair_or_call_route"
        risks.append(
            {
                "key": entry["key"],
                "source": source,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "reason": reason,
                "missing_locales": missing,
            }
        )
    counts["distinct_complete_sources"] = len(sources)
    counts["text_only_conflicting_sources"] = sum(len(pairs) > 1 for pairs in sources.values())
    return {
        "scope": "complete dialogue blocks; resource/resolver routes, not observed UI coverage",
        "primary": primary,
        "secondary": secondary,
        "source_language": source_language,
        "counts": dict(counts),
        "risks": risks,
        "game_started": False,
        "game_attached": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("generated/catalog.json"))
    parser.add_argument("--model", type=Path, required=True, help="matching prepared runtime model")
    parser.add_argument("--primary", default="zh-Hans")
    parser.add_argument("--secondary", default="ja")
    parser.add_argument("--source-language", default="zh-Hans")
    parser.add_argument("--out", type=Path, default=Path("generated/dialogue-coverage.json"))
    args = parser.parse_args()
    entries = json.loads(args.catalog.read_text(encoding="utf-8"))["entries"]
    model = json.loads(args.model.read_text(encoding="utf-8"))
    result = audit(entries, model, args.primary, args.secondary, args.source_language)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in result.items() if k != "risks"}, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
