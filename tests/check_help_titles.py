"""Raw eight-locale Tips/Help titles through bounded production models and JS."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables
from tools.audit_title_name_families import raw_tips, raw_sections, raw_text
from tools.inspect_status_sprite_layout import Layout


RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));let checked=0,rejections=0;const failures=[];
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const row of rows){const tr=new RuntimeText(row.model);
 for(const c of row.cases){const local=tr.scoped[c.scope],pair=local.model.pairs[c.source];
  if(!c.pair){if(pair)failures.push({...c,stage:'ambiguous_admission'});rejections++;continue;}
  if(JSON.stringify(pair)!==JSON.stringify(c.pair)){failures.push({...c,actual:pair,stage:'raw_target_oracle'});continue;}
  const p=tr.translate(c.source,'primary','',c.scope),s=tr.translate(c.source,'secondary','',c.scope),plan=tr.render(c.source,'annotation','',c.scope);
  const payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
  if(p!==c.pair[0]||s!==c.pair[1]||!row.model.same_language&&RuntimeText.needsAnnotation(...c.pair)&&visible(payload)!==visible(c.pair[1]))failures.push({...c,p,s,plan,stage:'render'});
  checked++;
 }
}
process.stdout.write(JSON.stringify({checked,rejections,failures}));
"""


def check(game, catalog):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    titles = [
        e
        for e in entries
        if (
            e["key"].startswith("table/t_tips.tbl/")
            or e["key"].startswith("table/t_help.tbl/")
            and len(e["key"].split("/")) == 4
        )
        and e["key"].endswith("/title")
    ]
    raw, shapes = {}, {}
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_tables(archive)
            tips = raw_tips(archive.read(logical["table/t_tips.tbl"]))
            values = {("tips", identity): row["title"] for identity, row in tips.items()}
            data = archive.read(logical["table/t_help.tbl"])
        headers = raw_sections(data)
        floor = max(s + z * n for _, s, z, n in headers)
        shape = []
        for kind, start, stride, count in headers:
            if kind != "HelpTitle":
                continue
            offset = 16 if kind == "HelpPage" else 8
            masks = {"HelpTitle": (8,), "HelpPage": (8, 16, 24), "HelpIconList": (8, 24, 40, 48)}[
                kind
            ]
            shape.append((kind, stride, count))
            for number in range(count):
                at = start + stride * number
                scalar = bytearray(data[at : at + stride])
                for p in masks:
                    scalar[p : p + 8] = b"\0" * 8
                key = ("help", kind, number, bytes(scalar).hex())
                values[key] = raw_text(data, struct.unpack_from("<Q", data, at + offset)[0], floor)
        raw[language], shapes[language] = values, shape
    assert all(set(rows) == set(raw["en"]) for rows in raw.values())
    assert all(shape == shapes["en"] for shape in shapes.values())
    # Count entire payload multiplicity, including two differently-conditioned
    # Tips records with identical display payloads. Never make IDs unique by row.
    raw_payloads = Counter(tuple(raw[l][key] for l in raw) for key in raw["en"])
    catalog_payloads = Counter(tuple(e["texts"].get(l) for l in raw) for e in titles)
    assert raw_payloads == catalog_payloads
    models, pair_counts = [], []
    locales = list(raw)
    configs = [(source, source, target) for source in locales for target in locales]
    configs.append(("en", "zh-Hans", "ja"))
    for source, primary, secondary in configs:
        tr = MenuTranslator(titles, primary, secondary, source)
        cases = []
        for scope in ("note_help_title", "tips_title"):
            expected = defaultdict(set)
            for key, text in raw[source].items():
                if text.strip() and (scope != "tips_title" or key[0] == "tips"):
                    expected[text].add((raw[primary][key], raw[secondary][key]))
            for text, pairs in expected.items():
                cases.append(
                    {
                        "scope": scope,
                        "source": text,
                        "pair": next(iter(pairs)) if len(pairs) == 1 else None,
                    }
                )
        models.append({"model": tr.runtime_model(), "cases": cases})
        pair_counts.append(
            {
                "source": source,
                "primary": primary,
                "secondary": secondary,
                "inputs": len(cases),
                "ambiguous": sum(c["pair"] is None for c in cases),
            }
        )
    result = subprocess.run(
        ["node", "-e", RUNNER],
        input=json.dumps(models, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        check=True,
    )
    rendered = json.loads(result.stdout)
    assert not rendered["failures"], rendered["failures"][:2]
    paths = {}
    with FpacArchive(game / "pac/steam/layout.pac") as archive:
        for path in ("layout/note_help.lay", "layout/help.lay"):
            # These serialization keys are specific to these two original packs.
            layout = Layout(archive.read(path), path, (103, 342))
            nodes = layout.all_nodes()
            children = {c for n in nodes for c in layout.node_children(n)}
            found = []

            def walk(n, parents):
                chain = parents + [layout.node_name(n)]
                if chain[-1] in ("title", "text"):
                    found.append(chain)
                for child in layout.node_children(n):
                    walk(child, chain)

            for node in nodes:
                if node not in children:
                    walk(node, [])
            paths[path] = found
    assert ["list_root", "item_template", "text"] in paths["layout/note_help.lay"]
    assert ["list_root", "tab_root", "item_template", "text"] in paths["layout/note_help.lay"]
    assert ["tips_contents", "title"] in paths["layout/help.lay"]
    return {
        "raw_title_records": len(raw["en"]),
        "tips_title_records": len(tips),
        "locale_configs": pair_counts,
        "render": rendered,
        "raw_node_paths": paths,
        "limits": [
            "Tips oracle uses complete metadata/resource/condition tuples; Help uses physical rows plus invariant masked scalar bytes.",
            "Disk paths and callback simulation do not confirm live pixels or actual current label ancestry.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    report = check(a.game, a.catalog)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "records": report["raw_title_records"],
                "configs": len(report["locale_configs"]),
                **report["render"],
            }
        )
    )
