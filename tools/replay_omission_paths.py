"""Replay observed model paths offline; input segmentation and live owners stay unknown."""

import argparse
import json
from pathlib import Path
import subprocess

from sora_bilingual.localization.menu_text import MenuTranslator


def replay(catalog_path, model_path, audit_path):
    entries = json.loads(catalog_path.read_text("utf-8"))["entries"]
    audit = json.loads(audit_path.read_text("utf-8"))
    names = [
        e
        for e in entries
        if e["key"].startswith("table/t_mapjump.tbl/") and e["key"].endswith("/name")
    ]
    model = MenuTranslator(names, "zh-Hans", "ja", "en").runtime_model()
    cases = []
    for row in audit["observed_cases"]:
        source = row["source"]
        owners = row["catalog_owners"]
        is_map = any(e["key"].startswith("table/t_mapjump.tbl/") for e in owners)
        full_fields = [
            e["texts"]["en"]
            for e in entries
            if e["key"].startswith("table/t_itemhelp.tbl/")
            and source in e["texts"].get("en", "")
            and source != e["texts"].get("en")
        ]
        cases.append(
            {
                "source": source,
                "map": is_map,
                "owners": row["compiled_table_owners"],
                "full_fields": full_fields,
                "expected_map_pairs": [
                    e["pair"] for e in owners if e["key"].startswith("table/t_mapjump.tbl/")
                ],
            }
        )
    runner = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js'),
{TableIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),old=JSON.parse(fs.readFileSync(input.model_path,'utf8'));
const before=new RuntimeText(old),after=new RuntimeText({...old,scoped:{...old.scoped,map_spot:input.scope}});
const identities=new TableIdentities(old.table_identities);
const plan=(tr,source,scope='')=>{const p=tr.render(source,'annotation','',scope);return {kind:p.kind,text:p.text,layers:p.layers};};
const cases=input.cases.map(c=>({...c,before:plan(before,c.source,c.map?'map_spot':''),
 after:plan(after,c.source,c.map?'map_spot':''),after_pair:c.map?input.scope.pairs[c.source]:null,
 table_local:c.owners.map(key=>{const owner=identities.lookup(key,c.source);return {key,
   pair:owner?.model.pairs[c.source],plan:owner?plan(new RuntimeText(owner.model),c.source):null};}),
 whole_field:c.full_fields.map(source=>({source,plan:plan(before,source)}))}));
process.stdout.write(JSON.stringify(cases));
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(
            {"model_path": str(model_path), "scope": model["scoped"]["map_spot"], "cases": cases},
            ensure_ascii=False,
        ),
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    rows = json.loads(result.stdout)
    for row in rows:
        if row["map"]:
            expected = {tuple(p) for p in row["expected_map_pairs"]}
            assert len(expected) == 1 and tuple(row["after_pair"]) in expected
            assert row["after"]["kind"] != "plain"
        elif len(row["table_local"]) > 1:
            # Different item owners must not become a global text fallback.
            assert row["after"]["kind"] == "plain"
            assert len({tuple(v["pair"]) for v in row["table_local"]}) > 1
            assert all(v["plan"]["kind"] != "plain" for v in row["table_local"])
    return {
        "source": "en",
        "primary": "zh-Hans",
        "secondary": "ja",
        "cases": rows,
        "limits": [
            "Local owner lookup is not live pointer verification.",
            "Actual setter segmentation, node path, and item owner remain uncaptured.",
            "Whole-field success and standalone failure establish model behavior, not actual UI routing.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("catalog", "model", "audit", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = replay(args.catalog, args.model, args.audit)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "cases": len(report["cases"]),
                "map_before_plain": sum(
                    r["map"] and r["before"]["kind"] == "plain" for r in report["cases"]
                ),
                "map_after_plain": sum(
                    r["map"] and r["after"]["kind"] == "plain" for r in report["cases"]
                ),
            }
        )
    )
