"""Verify the native kind-16 revive/recovery constructor across all locales."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.item_help_composition import (
    build_item_help_grammar,
    read_item_help_contract,
)
from sora_bilingual.localization.menu_text import MenuTranslator


ROOT = Path(__file__).resolve().parents[1]
REPORTED_DESCRIPTION = (
    "table/t_skill.tbl/"
    "sha256:9b93d1a72469b79f0a010183079daa56e3a93f43d44d0ab3ac5989508996b4b4/"
    "description"
)


def expected(catalogue, fields, language, variant):
    magnitude = {
        "percent": catalogue["table/t_text.tbl/TXT_ITEM_HELP_PERSENT"][language],
        "all": catalogue["table/t_text.tbl/TXT_ITEM_HELP_ALL"][language],
        "small": catalogue["table/t_text.tbl/TXT_ITEM_HELP_SMALL"][language],
        "middle": catalogue["table/t_text.tbl/TXT_ITEM_HELP_MIDDLE"][language],
        "large": catalogue["table/t_text.tbl/TXT_ITEM_HELP_LARGE"][language],
    }[variant]
    first = fields[120]
    last = fields[120 if variant in ("percent", "all") else 121]
    return (
        catalogue[first + "/name"][language]
        + catalogue["table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"][language]
        + catalogue[last + "/format"][language].replace("%s", magnitude)
    )


def concrete(value, amount=5):
    return value.replace("%d", str(amount)).replace("%%", "%")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, default=os.environ.get("SORA_GAME_DIR"))
    parser.add_argument("--catalog", type=Path, default=ROOT / "generated/catalog.json")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/item-help-revive-check.json"
    )
    args = parser.parse_args()
    if args.game_dir is None:
        parser.error("provide --game-dir or SORA_GAME_DIR")

    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    entries = payload["entries"]
    catalogue = {entry["key"]: entry["texts"] for entry in entries}
    metadata, groups, audit = read_item_help_contract(args.game_dir)
    connections = [row for row in audit["_connect_groups"] if row["kind"] == 16]
    assert connections == [{"kind": 16, "ids": [120, 121]}]
    by_id = {
        row["id"]: (identity, tuple(row["parameter_types"]))
        for identity, row in metadata["SkillEffectHelpData"].items()
    }
    assert by_id[120][1] == (0, 0)
    assert by_id[121][1] == (0, 0)
    fields = {
        record_id: "table/t_itemhelp.tbl/SkillEffectHelpData/" + by_id[record_id][0]
        for record_id in (120, 121)
    }
    actual = sorted({tuple(slot) for group in groups for slot in group if slot[0] in (120, 121)})
    assert actual == [
        (120, 5, 0, 0),
        (120, 10, 0, 0),
        (120, 15, 0, 0),
        (120, 20, 0, 0),
        (120, 25, 0, 0),
        (120, 30, 0, 0),
        (120, 40, 0, 0),
        (120, 50, 0, 0),
        (120, 80, 0, 0),
        (120, 100, 0, 0),
        (121, 1750, 25, 0),
        (121, 4500, 25, 0),
    ]
    contexts = [
        row for row in audit["_effect_contexts"] if row["description_key"] == REPORTED_DESCRIPTION
    ]
    assert len(contexts) == 1
    assert tuple(map(tuple, contexts[0]["group"])) == ((121, 1750, 25, 0),)

    grammar = build_item_help_grammar(args.game_dir, entries, "en")
    family = {
        row["item_help_contract"]["variant"]: row
        for row in grammar["detail_entries"]
        if row.get("item_help_contract", {}).get("family") == "revive_recovery"
    }
    variants = ("percent", "all", "small", "middle", "large")
    assert tuple(family) == variants
    for variant in variants:
        assert family[variant]["texts"] == {
            language: expected(catalogue, fields, language, variant) for language in LANGUAGES
        }

    description = next(entry for entry in entries if entry["key"] == REPORTED_DESCRIPTION)
    selected = [description, *family.values()]
    batches = []
    matrix_cases = 0
    percent_amounts = tuple(row[1] for row in actual if row[0] == 120)
    variant_cases = (
        *(("percent", amount) for amount in percent_amounts),
        ("all", 100),
        ("small", 1750),
        # No installed row lands in this interval; the static builder branch
        # still proves its bounded output and is exercised explicitly.
        ("middle", 3000),
        ("large", 4500),
    )
    for source_language in LANGUAGES:
        for primary in LANGUAGES:
            for secondary in LANGUAGES:
                translator = MenuTranslator(selected, primary, secondary, source_language)
                cases = []
                for variant, amount in variant_cases:
                    source = (
                        f"<c698>{concrete(expected(catalogue, fields, source_language, variant), amount)}</C>"
                        f"\n<C0>{description['texts'][source_language]}"
                    )
                    expected_primary = (
                        f"<c698>{concrete(expected(catalogue, fields, primary, variant), amount)}</C>"
                        f"\n<C0>{description['texts'][primary]}"
                    )
                    expected_secondary = (
                        f"<c698>{concrete(expected(catalogue, fields, secondary, variant), amount)}</C>"
                        f"\n<C0>{description['texts'][secondary]}"
                    )
                    assert translator.translate(source, "primary") == expected_primary
                    assert translator.translate(source, "secondary") == expected_secondary
                    cases.append(
                        {
                            "source": source,
                            "primary": expected_primary,
                            "secondary": expected_secondary,
                            "render": translator.render(source),
                        }
                    )
                    matrix_cases += 1
                batches.append({"model": translator.runtime_model(), "cases": cases})

    runner = """
const fs = require('fs');
const assert = require('assert/strict');
const {RuntimeText} = require('./sora_bilingual/game/scripts/runtime_text.js');
for (const batch of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  const runtime = new RuntimeText(batch.model);
  for (const row of batch.cases) {
    assert.strictEqual(runtime.translate(row.source, 'primary'), row.primary);
    assert.strictEqual(runtime.translate(row.source, 'secondary'), row.secondary);
    assert.deepStrictEqual(runtime.render(row.source), row.render);
  }
}
"""
    replay = subprocess.run(
        ["node", "-e", runner],
        cwd=ROOT,
        input=json.dumps(batches, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert replay.returncode == 0, replay.stderr

    # The compact matrix proves the constructor; this full catalogue replay
    # separately proves that unrelated entries do not make the reported pair
    # conflict or disappear.
    full = MenuTranslator(
        entries + grammar["status_entries"] + grammar["detail_entries"], "en", "ja", "en"
    )
    reported = "<c698>Revive, Heal (S) HP</C>\n<C0>" + description["texts"]["en"]
    reported_secondary = "<c698>復活／HP小回復</C>\n<C0>" + description["texts"]["ja"]
    assert full.translate(reported, "primary") == reported
    assert full.translate(reported, "secondary") == reported_secondary
    full_batch = {
        "model": full.runtime_model(),
        "source": reported,
        "primary": reported,
        "secondary": reported_secondary,
        "render": full.render(reported),
    }
    replay = subprocess.run(
        [
            "node",
            "-e",
            runner.replace(
                "for (const batch of JSON.parse(fs.readFileSync(0, 'utf8'))) {",
                "for (const batch of [JSON.parse(fs.readFileSync(0, 'utf8'))]) {",
            ),
        ],
        cwd=ROOT,
        input=json.dumps({"model": full_batch["model"], "cases": [full_batch]}, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert replay.returncode == 0, replay.stderr

    report = {
        "game_process_touched": False,
        "catalog": str(args.catalog),
        "catalog_entries": len(entries),
        "connection": connections[0],
        "parameter_types": {str(record_id): list(by_id[record_id][1]) for record_id in (120, 121)},
        "actual_slots": [list(row) for row in actual],
        "reported_description": REPORTED_DESCRIPTION,
        "reported_group": [list(row) for row in contexts[0]["group"]],
        "variants": list(variants),
        "percent_amounts": list(percent_amounts),
        "locale_configurations": len(batches),
        "python_and_js_cases": matrix_cases,
        "full_catalog_en_en_ja_render": full_batch["render"],
        "passed": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
