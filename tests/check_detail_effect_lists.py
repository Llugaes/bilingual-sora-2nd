"""Replay FORMAT8 effect lists against the complete installed resource catalog.

The numeric inputs exercise proven parser contracts, not claims that every
permutation occurs in the game. No game is started, attached, or modified.
"""

import argparse
from collections import Counter
import gc
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator, plain
from sora_bilingual.localization.native_catalog import load_entries


DESCRIPTION = (
    "table/t_skill.tbl/"
    "sha256:220b336432dab4bc8c7095fff8a9d47a4ea4ff384694b824b5a6928eec8b973e/description"
)
FLAGS = {"DEBUFF_CANCEL", "DELAY_SHORT", "HITTING", "STUN_L", "STUN_LL"}
FORMAT = re.compile(r"%%|%[-+ #0]*\d*(?:\.\d+)?[diuoxXfFeEgGcs]")
RUNNER = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8')),runtime=new RuntimeText(data.model);
const {RuntimeText:Baseline}=require(data.baseline),previous=new Baseline(data.model);
let maxCold=0;
for(const row of data.cases) {
 const start=performance.now(),plan=runtime.render(row.source),ms=performance.now()-start;
 maxCold=Math.max(maxCold,ms);
 assert.equal(runtime.translate(row.source,'primary'),row.primary,row.name+' primary');
 assert.equal(runtime.translate(row.source,'secondary'),row.secondary,row.name+' secondary');
 assert.deepEqual(plan,row.render,row.name+' render parity');
 if(row.readings.length) {
  const visible=(plan.text+plan.layers.map(l=>l.text).join(''))
    .replace(/<\/R([^<>]*)>/g,'$1').replace(/<[^<>]*>/g,'');
  for(const term of row.readings) assert.ok(visible.includes(term.replace(/<[^<>]*>/g,'')),JSON.stringify({name:row.name,term,visible}));
 }
}
for(const row of data.negatives) {
 assert.equal(runtime.translate(row.source,'secondary'),row.expected,'negative parity');
 assert.equal(runtime.translate(row.source,'secondary'),previous.translate(row.source,'secondary'),'global behavior changed');
}
console.log(JSON.stringify({cases:data.cases.length,max_cold_render_ms:maxCold}));
"""


def concrete(text):
    """Use a fixed value for numeric slots; never substitute an opaque %s."""
    fields = FORMAT.findall(text)
    if "%%" in text and not any(field != "%%" for field in fields):
        return None
    if any(field.endswith(("s", "c")) for field in fields if field != "%%"):
        return None
    return plain(FORMAT.sub(lambda m: "%" if m.group() == "%%" else "30", text))


def effect_rows(entries):
    return [
        row
        for row in entries
        if row.get("key", "").startswith("table/t_itemhelp.tbl/SkillEffectHelpData/")
        or row.get("item_help_contract")
        or row.get("key", "").removeprefix("table/t_text.tbl/TXT_ITEM_HELP_") in FLAGS
    ]


def fold_width(text):
    return re.sub(r"[\uff01-\uff5e]", lambda m: chr(ord(m[0]) - 0xFEE0), text)


def check(game, output, baseline):
    entries, signature = load_entries(game)
    catalog = {row["key"]: row["texts"] for row in entries}
    separators = catalog["table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"]
    description = catalog[DESCRIPTION]
    result = {
        "game_started": False,
        "game_attached": False,
        "catalog_records": len(entries),
        "resource_signature_sha256": hashlib.sha256(signature.encode()).hexdigest(),
        "numeric_probe_value": 30,
        "combinations_are_contract_closure": True,
        "targets": [],
        "all_passed": False,
        "member_checks": "every raw field and proven typed row, preserving rejections",
        "render_checks": "representatives of each family, field role and numeric parameter shape",
    }
    for source in LANGUAGES:
        grammar = build_item_help_grammar(game, entries, source)
        all_entries = entries + grammar["status_entries"] + grammar["detail_entries"]
        raw_rows = effect_rows(all_entries)
        for secondary in LANGUAGES:
            start = time.perf_counter()
            translator = MenuTranslator(all_entries, source, secondary, source)
            details = translator.details
            rejected = Counter()
            width_equivalents = 0
            atoms = {}
            representatives = {}
            for row in raw_rows:
                if not all(row["texts"].get(l) for l in (source, secondary)):
                    rejected["missing_language"] += 1
                    continue
                values = tuple(concrete(row["texts"][l]) for l in (source, secondary))
                if any(value is None for value in values):
                    rejected["unbound_string_or_raw_format"] += 1
                    continue
                if not all(any(c.isalnum() for c in value) for value in values):
                    rejected["punctuation_only"] += 1
                    continue
                # A candidate may be ambiguous in the complete catalog. Keep
                # that denominator rather than treating rejected rows as passes.
                pair = details._detail_join_pair(separators[source] + values[0])
                if pair is None:
                    rejected["not_admitted_or_conflicting"] += 1
                    continue
                expected = (separators[source] + values[0], separators[secondary] + values[1])
                if pair != expected:
                    assert pair[0] == expected[0] and fold_width(pair[1]) == fold_width(
                        expected[1]
                    ), (
                        row["key"],
                        source,
                        secondary,
                        pair,
                        expected,
                    )
                    width_equivalents += 1
                    values = (values[0], pair[1][len(separators[secondary]) :])
                atoms.setdefault(values, row["key"])
                shape = (
                    row.get("item_help_contract", {}).get("family", row["key"].split("/")[2]),
                    row["key"].rsplit("/", 1)[-1] if not row.get("item_help_contract") else "typed",
                    tuple(FORMAT.findall(row["texts"][source])),
                    values[0].count(separators[source]),
                    values[0].count(catalog["table/t_text.tbl/TXT_ITEM_HELP_LINK"][source]),
                    values[0].count("\n"),
                )
                representatives.setdefault(shape, values)
            admitted = list(atoms)
            assert len(admitted) > 100, (source, secondary, rejected)
            samples = list(dict.fromkeys(representatives.values()))
            cases = []
            for index, values in enumerate(samples):
                for length in (2, 3, 5):
                    members = [samples[(index + offset) % len(samples)] for offset in range(length)]
                    # Rotate through both padded native fragments and complete
                    # headers, including the comma clipped at a style boundary.
                    prefix = index % 2 == 0
                    suffix = index % 3 == 0
                    bodies = [
                        (separators[l] if prefix else "")
                        + separators[l].join(member[side] for member in members)
                        + (separators[l] if suffix else "")
                        for side, l in enumerate((source, secondary))
                    ]
                    if suffix and index % 2 and separators[source] != separators[source].rstrip():
                        bodies = [body.rstrip() for body in bodies]
                    texts = [
                        "<c698>" + body + "</C>\n<C0>" + description[l]
                        for l, body in zip((source, secondary), bodies)
                    ]
                    actual = translator.translate(texts[0], "secondary")
                    assert actual == texts[1], (source, secondary, index, length, actual, texts[1])
                    assert translator.translate(texts[0], "primary") == texts[0]
                    cases.append(
                        {
                            "name": f"{index}:{length}",
                            "source": texts[0],
                            "primary": texts[0],
                            "secondary": texts[1],
                            "render": translator.render(texts[0]),
                            "readings": [member[1] for member in members]
                            if source != secondary
                            else [],
                        }
                    )
            # The narrow constructor does not grant unknown members, arbitrary
            # menu strings, or a standalone separator any reusable identity.
            for bad in (
                separators[source],
                separators[source] + "UNKNOWN",
                "UNKNOWN" + separators[source] + admitted[0][0],
            ):
                assert details._detail_join_pair(bad) is None
            for atom in admitted[:3]:
                unanchored = separators[source] + atom[0]
                assert translator._detail_join_pair(unanchored) is None
            assert translator.detail_join is None
            negatives = [
                {"source": text, "expected": translator.translate(text, "secondary")}
                for text in [
                    separators[source],
                    ",",
                    *(separators[source] + atom[0] for atom in admitted[:3]),
                ]
            ]
            data = {
                "model": translator.runtime_model(),
                "cases": cases,
                "negatives": negatives,
                "baseline": str(baseline),
            }
            compiled = time.perf_counter() - start
            replay = subprocess.run(
                ["node", "-e", RUNNER],
                cwd=ROOT,
                input=json.dumps(data, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf8",
            )
            assert replay.returncode == 0, replay.stderr[-12000:]
            row = {
                "source": source,
                "primary": source,
                "secondary": secondary,
                "raw_effect_fields_and_typed_rows": len(raw_rows),
                "admitted_unique_members": len(admitted),
                "render_representatives": len(samples),
                "rejected_rows": dict(rejected),
                "existing_width_equivalent_target_spellings": width_equivalents,
                "detail_numeric_rules": len(details.detail_join_numeric),
                "compile_and_python_replay_seconds": round(compiled, 3),
                **json.loads(replay.stdout),
            }
            result["targets"].append(row)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
            print(json.dumps(row, ensure_ascii=False), flush=True)
            del translator, details, data, cases
            gc.collect()
        del all_entries
        gc.collect()
    assert len(result["targets"]) == len(list(itertools.product(LANGUAGES, repeat=2)))
    result["all_passed"] = True
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        baseline = Path(temporary) / "runtime_text.js"
        baseline.write_bytes(
            subprocess.check_output(
                ["git", "show", "v0.4.2:sora_bilingual/game/scripts/runtime_text.js"], cwd=ROOT
            )
        )
        check(args.game, args.output, baseline)
