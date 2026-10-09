"""Bounded condition formatter replay, including conflicting item homographs."""

import argparse
import json
from pathlib import Path
import subprocess
import hashlib
import struct

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.tables import _logical_tables
from sora_bilingual.localization.item_help_composition import (
    _condition_list_entries,
    _entry_map,
    read_item_help_metadata,
)
from sora_bilingual.localization.menu_text import MenuTranslator


def check(game, catalog, old_model):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    metadata, audit = read_item_help_metadata(game)
    contracts = _condition_list_entries(
        entries, _entry_map(entries), metadata["SkillEffectHelpData"], LANGUAGES
    )
    assert len(contracts) == 1
    raw = contracts[0]["condition_list_contract"]
    # Independent field/peer oracle: explicit physical layout and scalar bytes,
    # not production identity keys or the renderer's returned names.
    peer, inventory = {}, []
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_condition_info.tbl"])
        rows = [s for s in sections(data) if s[0] == "ConditionInfoTableData"]
        assert len(rows) == 1 and rows[0][2] == 88
        _, start, stride, count = rows[0]
        nonempty = 0
        for i in range(count):
            at = start + i * stride
            pointer = struct.unpack_from("<Q", data, at + 8)[0]
            if not pointer:
                continue
            name = data[pointer : data.index(b"\0", pointer)].decode("utf-8")
            if not name:
                continue
            scalar = bytearray(data[at : at + stride])
            scalar[8:16] = b"\0" * 8
            scalar[80:88] = b"\0" * 8
            key = bytes(scalar).hex()
            assert locale not in peer.setdefault(key, {})
            peer[key][locale] = name
            nonempty += 1
        inventory.append(
            {
                "locale": locale,
                "records": count,
                "nonempty_names": nonempty,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    oracle = {tuple(row.get(l) for l in LANGUAGES) for row in peer.values()}
    assert {tuple(row.get(l) for l in LANGUAGES) for row in raw["names"]} == oracle
    batches = []
    for source in LANGUAGES:
        for target in LANGUAGES:
            translator = MenuTranslator(contracts, source, target, source)
            tests = []
            for length in (1, 2, 3):
                for start in range(len(raw["names"]) - length + 1):
                    names = raw["names"][start : start + length]
                    for rate in (0, 100):

                        def text(language):
                            return raw["templates"][language].replace(
                                "%s",
                                raw["links"][language].join(n[language] for n in names)
                                + " "
                                + raw["percent"][language]
                                .replace("%d", str(rate))
                                .replace("%%", "%"),
                            )

                        before, expected = text(source), text(target)
                        for prefix, suffix in (("", ""), ("<c698>", "</C>"), ("<s30><C5>", "</C>")):
                            argument = prefix + before + suffix
                            pair = (argument, prefix + expected + suffix)
                            actual = translator.condition_list_pair(argument)
                            assert actual == pair, (source, target, argument, actual, pair)
                            tests.append({"source": argument, "expected": pair})
            # Unknown, mixed roles, malformed/missing rate, and wrong separators
            # must not gain condition identity from the title alone.
            name = raw["names"][0][source]
            negatives = [
                raw["templates"][source].replace("%s", value)
                for value in (
                    "unowned condition 100%",
                    name + "/unowned condition 100%",
                    name,
                    name + " 101%",
                    name + "/" + name + " 100%",
                    "<I5>" + name + " 100%",
                )
            ]
            assert all(translator.condition_list_pair(s) is None for s in negatives)
            batches.append(
                {
                    "source": source,
                    "target": target,
                    "model": translator.runtime_model(),
                    "tests": tests,
                    "negative": negatives,
                }
            )
    actual = MenuTranslator(contracts, "zh-Hans", "ja", "en").runtime_model()
    observed = ["Resist Mute/Freeze 100%", "Resist Burn/Confuse/Deathblow 100%"]
    runner = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8'));let checked=0,negative=0;const failures=[];
for(const batch of input.batches){const tr=new RuntimeText(batch.model);
 for(const c of batch.tests){const actual=tr.conditionListPair(c.source),plan=tr.render(c.source,'annotation');
  const clean=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,''),payload=plan.layers.map(l=>l.text).join('')+
   [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
  if(JSON.stringify(actual)!==JSON.stringify(c.expected)||tr.translate(c.source,'secondary')!==c.expected[1]||
   (batch.source!==batch.target&&RuntimeText.needsAnnotation(...c.expected)&&clean(payload)!==clean(c.expected[1])))failures.push({source:batch.source,target:batch.target,input:c.source,actual,expected:c.expected,plan});checked++;}
 for(const s of batch.negative){if(tr.conditionListPair(s)!==null)failures.push({negative:s});negative++;}}
const old=JSON.parse(fs.readFileSync(input.old_model,'utf8')),before=new RuntimeText(old),after=new RuntimeText({...old,condition_lists:input.actual.condition_lists});
const observed=input.observed.map(source=>({source,before:[before.translate(source,'primary'),before.translate(source,'secondary')],
 after:[after.translate(source,'primary'),after.translate(source,'secondary')],plan:after.render(source,'annotation')}));
process.stdout.write(JSON.stringify({checked,negative,failures,observed}));
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(
            {
                "batches": batches,
                "old_model": str(old_model),
                "actual": actual,
                "observed": observed,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
        capture_output=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    report = json.loads(result.stdout)
    assert not report["failures"], report["failures"][:1]
    # Assert each observed parameter member, not merely a bilingual line/header.
    for row in report["observed"]:
        expected = MenuTranslator(contracts, "zh-Hans", "ja", "en").condition_list_pair(
            row["source"]
        )
        assert tuple(row["after"]) == expected and row["after"] != row["before"]
    return {
        "contract_id": 98,
        "parameter_types": [10],
        "condition_names": len(raw["names"]),
        "language_pairs": len(batches),
        "metadata_audit": audit,
        "raw_condition_fields": inventory,
        **report,
        "limits": [
            "Offline complete formatter evidence; actual label routing remains unobserved.",
            "Only known condition members under the verified formatter are admitted.",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "model", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    report = check(a.game, a.catalog, a.model)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("condition_names", "language_pairs", "checked", "negative", "failures")
            }
        )
    )
