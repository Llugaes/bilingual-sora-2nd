"""Compare physical map area/spot names with the copied-name renderer in eight languages."""

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


def check(game, catalog):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    spots = [
        e
        for e in entries
        if e["key"].startswith("table/t_mapjump.tbl/") and e["key"].endswith("/name")
    ]
    raw, missing, checks, models, raw_names, shapes = {}, {}, [], [], {}, {}
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_mapjump.tbl"])
        names = []
        shapes[language] = []
        for kind, start, stride, count in sections(data):
            if kind not in ("MapJumpAreaData", "MapJumpSpotData"):
                continue
            # Independent disk field contract, not the production extractor's schema.
            assert stride == (56 if kind == "MapJumpAreaData" else 152)
            shapes[language].append((kind, count))
            for index in range(count):
                at = struct.unpack_from(
                    "<Q", data, start + index * stride + (8 if kind == "MapJumpAreaData" else 16)
                )[0]
                names.append(data[at : data.index(b"\0", at)].decode("utf-8"))
        raw_names[language] = names
        raw[language] = {
            "records": len(names),
            "nonempty": sum(bool(n.strip()) for n in names),
            "unique": len(set(names)),
        }
        missing[language] = sorted(
            set(names) - {e["texts"][language] for e in spots if language in e["texts"]}
        )
        for target in archive_names("table"):
            tr = MenuTranslator(spots, language, target, language)
            models.append({"source": language, "target": target, "model": tr.runtime_model()})
            inputs = sorted({n.replace("\n", "") for n in names if n.strip()})
            pairs = tr.scoped["map_spot"].pairs
            checks.append(
                {
                    "source": language,
                    "target": target,
                    "inputs": len(inputs),
                    "missing": [s for s in inputs if s not in pairs],
                }
            )
    # Expected target strings come from the other original PAC at the same
    # physical family/occurrence/row, not from the renderer's returned pair.
    # Section shape and scalar/resource identity alignment are separately audited.
    oracle_failures = []
    for row in models:
        source, target = row["source"], row["target"]
        assert shapes[source] == shapes[target]
        expected = {}
        for left, right in zip(raw_names[source], raw_names[target], strict=True):
            left, right = left.replace("\n", ""), right.replace("\n", "")
            if left.strip():
                expected.setdefault(left, set()).add((left, right))
        actual = row["model"]["scoped"]["map_spot"]["pairs"]
        for text, pairs in expected.items():
            result = tuple(actual.get(text, ()))
            if (len(pairs) == 1 and result not in pairs) or (len(pairs) > 1 and result):
                oracle_failures.append(
                    {
                        "source": source,
                        "target": target,
                        "text": text,
                        "expected": sorted(pairs),
                        "actual": result,
                    }
                )
    # Keep the reported cross-table conflict in a complete production model;
    # the all-language family sweep alone cannot prove global isolation.
    complete = MenuTranslator(entries, "zh-Hans", "ja", "zh-Hans")
    assert "神秘森林" not in complete.pairs
    assert complete.scoped["map_spot"].pairs["神秘森林"] == ("神秘森林", "ミストヴァルト")
    models.append({"source": "zh-Hans", "target": "ja", "model": complete.runtime_model()})
    runner = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const models=JSON.parse(fs.readFileSync(0,'utf8'));let checked=0;const failures=[];
for(const {source,target,model} of models){
 const tr=new RuntimeText(model);
 for(const [text,pair] of Object.entries(model.scoped.map_spot.pairs)){
  const primary=tr.translate(text,'primary','','map_spot'),secondary=tr.translate(text,'secondary','','map_spot');
  const plan=tr.render(text,'annotation','','map_spot');
  const payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
  const clean=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
  if(primary!==pair[0]||secondary!==pair[1]||(!model.same_language&&RuntimeText.needsAnnotation(...pair)&&clean(payload)!==clean(pair[1])))failures.push({source,target,text,primary,secondary,plan});
  checked++;
 }
}
process.stdout.write(JSON.stringify({checked,failures}));
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(models, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        check=True,
    )
    report = {
        "raw": raw,
        "catalog_records": len(spots),
        "missing_raw_names": missing,
        "language_pairs": checks,
        "render": json.loads(result.stdout),
        "complete_catalog_pair": ["zh-Hans", "ja"],
        "raw_target_oracle_failures": oracle_failures,
    }
    report["missing_counts"] = dict(
        Counter({language: len(rows) for language, rows in missing.items()})
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/map-spots-audit.json")
    args = parser.parse_args()
    report = check(args.game_dir, args.catalog)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "records": report["catalog_records"],
                "language_pairs": len(report["language_pairs"]),
                "rendered": report["render"]["checked"],
                "failures": len(report["render"]["failures"]),
            },
            ensure_ascii=False,
        )
    )
    assert not any(report["missing_raw_names"].values())
    assert not any(row["missing"] for row in report["language_pairs"])
    assert not report["render"]["failures"]
    assert not report["raw_target_oracle_failures"]
