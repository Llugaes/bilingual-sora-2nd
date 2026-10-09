"""Original map destination records and formatter through the production renderer."""

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
from sora_bilingual.localization.menu_text import MenuTranslator, MAP_NAME_FORMATTERS
from sora_bilingual.localization.resources import FpacArchive, FormatError
from sora_bilingual.localization.tables import _logical_tables
from tools.audit_title_name_families import raw_sections, raw_text


def destinations(data):
    headers = raw_sections(data)
    floor = max(s + z * n for _, s, z, n in headers)
    result, occurrences = {}, Counter()
    for kind, start, stride, count in headers:
        if kind != "MapJumpSpotData":
            continue
        assert stride == 152
        for number in range(count):
            at = start + stride * number
            scalar = bytearray(data[at : at + stride])
            resources = tuple(
                raw_text(data, struct.unpack_from("<Q", data, at + p)[0], floor)
                for p in (32, 56, 88, 104, 144)
            )
            conditions = []
            for p in (112, 128):
                pointer, size = struct.unpack_from("<QQ", data, at + p)
                if size > 4096 or size and not floor <= pointer <= len(data) - size * 2:
                    raise FormatError("map destination condition outside pool")
                conditions.append(tuple(struct.unpack_from(f"<{size}H", data, pointer)))
            for p in (16, 32, 56, 88, 104, 112, 128, 144):
                scalar[p : p + 8] = bytes(8)
            identity = (bytes(scalar).hex(), resources, tuple(conditions))
            # Exact duplicate native records are legal. Preserve their physical
            # multiplicity, then compare the same complete payload in all PACs.
            occurrences[identity] += 1
            result[(identity, occurrences[identity])] = raw_text(
                data, struct.unpack_from("<Q", data, at + 16)[0], floor
            )
    return result


RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));let checked=0,rejected=0;const failures=[];
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const row of rows){const tr=new RuntimeText(row.model);
 for(const c of row.cases){const p=tr.translate(c.source,'primary'),s=tr.translate(c.source,'secondary'),plan=tr.render(c.source);
  if(!c.pair){if(p!==c.source||s!==c.source)failures.push({...c,p,s,stage:'rejected_owner'});rejected++;continue;}
  const payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
  if(p!==c.pair[0]||s!==c.pair[1]||!row.model.same_language&&RuntimeText.needsAnnotation(...c.pair)&&visible(payload)!==visible(c.pair[1]))failures.push({...c,p,s,plan,stage:'render'});
  checked++;
 }
}
process.stdout.write(JSON.stringify({checked,rejected,failures}));
"""


def check(game, catalog):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    family = [
        e
        for e in entries
        if e["key"].startswith("table/t_mapjump.tbl/MapJumpSpotData/")
        and e["key"].endswith("/name")
    ]
    templates = [e for e in entries if e["key"] in MAP_NAME_FORMATTERS]
    raw, formats = {}, {}
    for language, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_tables(archive)
            raw[language] = destinations(archive.read(logical["table/t_mapjump.tbl"]))
            data = archive.read(logical["table/t_text.tbl"])
        headers = raw_sections(data)
        floor = max(s + z * n for _, s, z, n in headers)
        rows = {}
        for _, start, stride, count in headers:
            assert stride == 16
            for n in range(count):
                key = raw_text(data, struct.unpack_from("<Q", data, start + stride * n)[0], floor)
                if "table/t_text.tbl/" + key in MAP_NAME_FORMATTERS:
                    rows["table/t_text.tbl/" + key] = raw_text(
                        data, struct.unpack_from("<Q", data, start + stride * n + 8)[0], floor
                    )
        formats[language] = rows
    assert all(set(v) == set(raw["en"]) for v in raw.values())
    assert all(set(v) == set(MAP_NAME_FORMATTERS) for v in formats.values())
    assert Counter(tuple(raw[l][key] for l in raw) for key in raw["en"]) == Counter(
        tuple(e["texts"].get(l) for l in raw) for e in family
    )
    assert all(
        next(e for e in templates if e["key"] == key)["texts"][l] == formats[l][key]
        for l in raw
        for key in MAP_NAME_FORMATTERS
    )
    # Include the competing Tips family; the prompt owns destinations, not titles.
    related = (
        family
        + templates
        + [
            e
            for e in entries
            if e["key"].startswith("table/t_tips.tbl/") and e["key"].endswith("/title")
        ]
    )
    actor = {
        "key": "table/t_name.tbl/unrelated-actor/name",
        "texts": {l: "__unrelated_actor_" + l + "__" for l in raw},
    }
    related.append(actor)
    configs = [(s, s, t) for s in raw for t in raw] + [("en", "zh-Hans", "ja")]
    models, counts = [], []
    for source, primary, secondary in configs:
        tr = MenuTranslator(related, primary, secondary, source)
        expected = defaultdict(set)
        for identity, name in raw[source].items():
            for key in MAP_NAME_FORMATTERS:
                source_text = formats[source][key].replace("%s", name)
                pair = tuple(
                    formats[l][key].replace("%s", raw[l][identity]) for l in (primary, secondary)
                )
                expected[source_text].add(pair)
        cases = [
            {"source": text, "pair": next(iter(pairs)) if len(pairs) == 1 else None}
            for text, pairs in expected.items()
        ]
        cases.append(
            {
                "source": formats[source][MAP_NAME_FORMATTERS[1]].replace(
                    "%s", actor["texts"][source]
                ),
                "pair": None,
            }
        )
        models.append({"model": tr.runtime_model(), "cases": cases})
        counts.append(
            {"source": source, "primary": primary, "secondary": secondary, "cases": len(cases)}
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
    example = next(key for key, name in raw["en"].items() if name == "Zeiss Central Factory")
    key = MAP_NAME_FORMATTERS[1]
    observed = {
        "source": formats["en"][key].replace("%s", raw["en"][example]),
        "pair": [formats[l][key].replace("%s", raw[l][example]) for l in ("zh-Hans", "ja")],
    }
    return {
        "raw_destination_records": len(raw["en"]),
        "configs": counts,
        "render": rendered,
        "observed": observed,
        "limits": [
            "Independent identity uses complete masked scalars, resource strings and condition payloads; no model-generated targets.",
            "Static constructor and rendered buffer do not establish current game's notification label path or pixels.",
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
                "records": report["raw_destination_records"],
                "configs": len(report["configs"]),
                **report["render"],
            }
        )
    )
