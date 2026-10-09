"""Classify preserved replay results, without changing inputs, plans or expectations."""

import hashlib
import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated/r27-association-audit"
LANGUAGES = ["en", "ja", "zh-Hans", "zh-Hant", "ko", "fr", "de", "es"]


def read(path):
    return json.loads(Path(path).read_text("utf8"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def visible(text):
    return re.sub(r"<[^<>]*>", "", re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", text, flags=re.S))


def line_geometry(text):
    # Only line separators and their alignment padding. Never collapse ordinary word spaces.
    return re.sub(r"[ \t]*(?:\r\n|\n|\\n)[ \t]*", "", text)


def ascii_width(text):
    return text.translate(
        {value: value - 0xFEE0 for value in range(0xFF01, 0xFF5F)} | {0x3000: 0x20}
    )


def presentation_class(row):
    comparisons = [
        (result["visible_actual"], result["visible_expected"]) for result in row["results"].values()
    ]
    annotation = row["results"]["annotation"]
    if annotation.get("secondary_required"):
        if annotation.get("secondary_visible") is None:
            return None
        comparisons.append((annotation["secondary_visible"], annotation["secondary_expected"]))
    if all(ascii_width(actual) == ascii_width(expected) for actual, expected in comparisons):
        return "official_ascii_width_difference_only"
    if all(line_geometry(actual) == line_geometry(expected) for actual, expected in comparisons):
        return "line_geometry_difference_only"
    if all(
        ascii_width(line_geometry(actual)) == ascii_width(line_geometry(expected))
        for actual, expected in comparisons
    ):
        return "ascii_width_and_line_geometry_difference_only"
    return None


def comparable(row, language):
    texts = row["texts"]
    return (
        row["layer"] != "unqualified_tools_inner_effect_probe"
        and row["input_class"] != "template_resource"
        and all(
            isinstance(texts.get(key), str) and texts[key].strip()
            for key in (language, "ja", "zh-Hans")
        )
        and not row.get("ambiguous_locales", {}).get("ja")
        and not row.get("ambiguous_locales", {}).get("zh-Hans")
    )


def main():
    target = OUT / "classification001"
    if target.exists():
        raise FileExistsError("classification ID exists; retain previous outputs")
    target.mkdir()
    packet = read(OUT / "inputs.json")
    supplement_path = OUT / "supplement001/inputs.json"
    supplement = read(supplement_path)
    replacements = {row["id"]: row for row in supplement["records"] if not row.get("sanity_only")}
    packet["records"] = [replacements.get(row["id"], row) for row in packet["records"]]
    summaries = {}
    for language in LANGUAGES:
        location = OUT / "replay001" / language
        if not (location / "summary.json").exists():
            location = OUT / "replay002" / language
        summaries[language] = (location, read(location / "summary.json"))
    final, coverage_refs, examples = {}, {}, defaultdict(list)
    for language, (location, summary) in summaries.items():
        groups = defaultdict(lambda: defaultdict(list))
        for row in packet["records"]:
            if comparable(row, language):
                pair = (visible(row["texts"]["ja"]), visible(row["texts"]["zh-Hans"]))
                groups[row["texts"][language]][pair].append(row)
        ambiguity, lexical_ambiguity = set(), set()
        with (target / f"{language}-source-ambiguities.jsonl").open("w", encoding="utf8") as output:
            for source, variants in groups.items():
                if len(variants) < 2:
                    continue
                ambiguity.add(source)
                lexical = (
                    len(
                        {
                            tuple(ascii_width(line_geometry(value)) for value in pair)
                            for pair in variants
                        }
                    )
                    > 1
                )
                if lexical:
                    lexical_ambiguity.add(source)
                output.write(
                    json.dumps(
                        {
                            "source_language": language,
                            "source": source,
                            "variant_kind": "official_visible_target_conflict"
                            if lexical
                            else "official_target_line_geometry_variants",
                            "variants": [
                                {
                                    "official_primary_visible": pair[0],
                                    "official_secondary_visible": pair[1],
                                    "resource_keys": sorted({r["resource_key"] for r in rows}),
                                    "record_ids": [r["id"] for r in rows],
                                }
                                for pair, rows in variants.items()
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        counts, unique, layer_counts, all_failed_sources = (
            Counter(),
            defaultdict(set),
            defaultdict(Counter),
            set(),
        )
        main_misses = location / "unassociated.jsonl"
        supplement_misses = OUT / "supplement001/replay001" / language / "unassociated.jsonl"
        with (target / f"{language}-classified-unassociated.jsonl").open(
            "w", encoding="utf8"
        ) as output:
            lines = (
                line
                for file in (main_misses, supplement_misses)
                for line in file.read_text("utf8").splitlines()
            )
            for line in lines:
                row = json.loads(line)
                if row["layer"] == "unqualified_tools_inner_effect_probe":
                    classification = "unqualified_probe_result"
                elif presentation_class(row):
                    classification = presentation_class(row)
                elif row["source"] in lexical_ambiguity:
                    classification = "source_has_multiple_official_lexical_targets"
                elif row["source"] in ambiguity:
                    classification = "model_conflict_from_official_presentation_variants"
                elif row["reason"] == "whole_source_conflict_requires_proven_context":
                    classification = (
                        "model_conflict_without_complete_target_variant_in_this_denominator"
                    )
                else:
                    classification = "unresolved_full_text_in_empty_context_product_renderer"
                counts[classification] += 1
                unique[classification].add(row["source"])
                layer_counts[row["layer"]][classification] += 1
                if classification != "unqualified_probe_result":
                    all_failed_sources.add(row["source"])
                row["audit_classification"] = classification
                row["expectations_and_plans_unchanged"] = True
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                if len(examples[classification]) < 8:
                    examples[classification].append(
                        {
                            "source_language": language,
                            "record_id": row["id"],
                            "resource_key": row["resource_key"],
                            "source": row["source"],
                            "reason": row["reason"],
                            "physical": row["physical"],
                        }
                    )
        # Categories can overlap for the same source's physical aliases. Partition deterministically.
        partition = Counter()
        for source in all_failed_sources:
            if source in unique["source_has_multiple_official_lexical_targets"]:
                kind = "source_has_multiple_official_lexical_targets"
            elif source in unique["model_conflict_from_official_presentation_variants"]:
                kind = "model_conflict_from_official_presentation_variants"
            elif (
                source
                in unique["model_conflict_without_complete_target_variant_in_this_denominator"]
            ):
                kind = "model_conflict_without_complete_target_variant_in_this_denominator"
            elif source in unique["unresolved_full_text_in_empty_context_product_renderer"]:
                kind = "unresolved_full_text_in_empty_context_product_renderer"
            elif source in unique["ascii_width_and_line_geometry_difference_only"]:
                kind = "ascii_width_and_line_geometry_difference_only"
            elif source in unique["official_ascii_width_difference_only"]:
                kind = "official_ascii_width_difference_only"
            else:
                kind = "line_geometry_difference_only"
            partition[kind] += 1
        supplement_summary = read(OUT / "supplement001/replay001" / language / "summary.json")
        corrected_mode_counts = copy.deepcopy(summary["counts"])
        for layer, delta in supplement_summary["counts"].items():
            destination = corrected_mode_counts[layer]
            destination["template"] -= delta["records"] - delta["source_absent"] - delta["blank"]
            for key in ("unpaired", "comparable", "associated_all_modes", "unassociated_any_mode"):
                destination[key] += delta[key]
            for mode, statuses in delta["modes"].items():
                for status, count in statuses.items():
                    destination["modes"].setdefault(mode, {}).setdefault(status, 0)
                    destination["modes"][mode][status] += count
            assert (
                sum(
                    destination[key]
                    for key in ("blank", "source_absent", "template", "unpaired", "comparable")
                )
                == destination["records"]
            )
        final[language] = {
            "cross_layer_comparable_unique_sources": len(groups),
            "exact_full_plan_mismatch_unique_sources": len(all_failed_sources),
            "official_target_conflict_sources": len(ambiguity),
            "lexical_target_conflict_sources": len(lexical_ambiguity),
            "official_target_line_geometry_variant_sources": len(ambiguity - lexical_ambiguity),
            "unassociated_record_classifications": dict(counts),
            "unique_source_partition": dict(partition),
            "layer_classifications": {
                layer: dict(counts) for layer, counts in layer_counts.items()
            },
            "replay_summary": str((location / "summary.json").relative_to(ROOT)),
            "replay_summary_sha256": digest(location / "summary.json"),
            "binding": summary["binding"],
            "denominator_and_mode_counts": summary["counts"],
            "sanity_failed_modes": summary["sanity_failed_modes"],
            "r25_difference_counts": summary["r25_difference_counts"],
            "supplement_counts": supplement_summary["counts"],
            "effective_denominator_and_mode_counts": corrected_mode_counts,
        }
        coverage_refs[language] = digest(location / "unassociated.jsonl")
    inventory = read(OUT / "inventory-extraction-diff.json")
    records = {
        r["resource_key"]: r
        for r in packet["records"]
        if r["layer"] == "physical_item_skill_help_field"
    }
    absent = [r for r in inventory["raw_field_membership"] if r["missing_locales"]]
    nonempty_absent = [
        r
        for r in absent
        if any(
            records[r["key"]]["texts"].get(language, "").strip()
            for language in r["missing_locales"]
        )
    ]
    assert not nonempty_absent, "nonblank raw field extraction miss must be reported"
    # Independent coordinator counts are a check only, never the source denominator.
    independent_path = OUT / "coordinator-comparable-denominators.json"
    independent = read(independent_path) if independent_path.exists() else None
    old = read(ROOT / "generated/r25-producer-denominator.json")
    unknown = {
        "physical_item_skill_entities": len(old["entities"]),
        "old_slot_contexts": len(old["contexts"]),
        "old_claimed_complete_effect_groups": sum(
            bool(r["complete_effect_input_reconstructed"]) for r in old["contexts"]
        ),
        "full_outer_producer_entry_proof": "Legacy groups and category/colour fixtures are not certified complete SetText inputs; each must bind the raw full selector, native icon/format branch and actual styling/parameters.",
        "contexts": old["contexts"],
        "raw_unknown_sections": inventory["historical_inventory"]["unknown_item_skill_sections"],
        "dynamic_script_families": 114,
        "dynamic_script_locale_instances": 912,
        "dynamic_script_evidence": "generated/r27-association-audit/dynamic-script-producers.json",
        "full_game_unique_display_input_total": None,
        "reason_total_unknown": "Runtime variables, native UI constructors, save-dependent rank/style, unrecognized resource sections and on-screen reachability remain unenumerated.",
    }
    (target / "unresolved-producer-families.json").write_text(
        json.dumps(unknown, ensure_ascii=False, indent=2), "utf8"
    )
    result = {
        "schema": 1,
        "source_snapshot_sha256": packet["provenance"]["source_snapshot_sha256"],
        "input_packet_sha256": digest(OUT / "inputs.json"),
        "classifier_sha256": digest(Path(__file__)),
        "primary": "ja",
        "secondary": "zh-Hans",
        "languages": final,
        "cross_language_counts_are_not_additive": True,
        "raw_field_inventory": {
            "physical_fields_including_blanks": 5111,
            "blank_or_absent_not_catalogued": len(absent),
            "nonempty_fields_not_catalogued": len(nonempty_absent),
        },
        "unknown_full_game_total": True,
        "no_production_or_candidate_changes": True,
        "game_attached": False,
        "live_fps_evidence": False,
        "classification_preserves_all_raw_exact_mismatches": True,
        "replay_miss_file_sha256": coverage_refs,
        "supplement_input_sha256": digest(supplement_path),
        "denominator_correction": supplement["supplement_lineage"],
        "independent_denominator_receipt": str(independent_path)
        if independent is not None
        else None,
        "examples": dict(examples),
    }
    (target / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(
        json.dumps(
            {
                language: {
                    key: row[key]
                    for key in (
                        "cross_layer_comparable_unique_sources",
                        "exact_full_plan_mismatch_unique_sources",
                        "official_target_conflict_sources",
                        "unique_source_partition",
                    )
                }
                for language, row in final.items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
