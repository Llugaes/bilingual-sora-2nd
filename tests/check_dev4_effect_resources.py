"""Independent physical table fields/constructor oracle; final shipped JS replay.

Reads raw descriptor offsets, not the production effect grammar or translator,
to make expected locale strings. No game/UI/backend/font access.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


def descriptors(data):
    assert data[:4] == b"#TBL"
    count = struct.unpack_from("<I", data, 4)[0]
    return [
        (
            data[8 + i * 80 : 8 + i * 80 + 64].split(b"\0")[0].decode("ascii"),
            *struct.unpack_from("<III", data, 8 + i * 80 + 68),
        )
        for i in range(count)
    ]


def string(data, record, offset):
    at = struct.unpack_from("<Q", data, record + offset)[0]
    return "" if not at else data[at : data.index(b"\0", at)].decode("utf-8")


def plain(text):
    return re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", text)


def collect(game):
    tables, rows, groups, description_rows, receipts, connections = {}, {}, {}, {}, [], {}
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            paths = _logical_tables(archive)
            help_data = archive.read(paths["table/t_itemhelp.tbl"])
            text_data = archive.read(paths["table/t_text.tbl"])
            skill_data = archive.read(paths["table/t_skill.tbl"])
        effects = {}
        kind, start, stride, count = next(
            s for s in descriptors(help_data) if s[0] == "SkillEffectHelpData"
        )
        assert stride == 88
        for physical in range(count):
            at = start + physical * stride
            ident = struct.unpack_from("<I", help_data, at)[0]
            assert ident not in effects
            ptr, n = struct.unpack_from("<QI", help_data, at + 16)
            assert n <= 16 and (not n or ptr + n * 2 <= len(help_data))
            types = list(struct.unpack_from("<" + "H" * n, help_data, ptr)) if n else []
            effects[ident] = {
                "physical_row": physical,
                "record_at": at,
                "id": ident,
                "types": types,
                **{
                    field: string(help_data, at, offset)
                    for field, offset in [
                        ("name", 8),
                        ("stat", 32),
                        ("format", 40),
                        ("turns", 72),
                        ("value", 80),
                    ]
                },
            }
        _, connect_at, connect_stride, connect_count = next(
            s for s in descriptors(help_data) if s[0] == "SkillConnectListData"
        )
        assert connect_stride == 24
        kinds = {}
        for i in range(connect_count):
            at = connect_at + i * connect_stride
            kind = struct.unpack_from("<I", help_data, at)[0]
            ptr, n = struct.unpack_from("<QI", help_data, at + 8)
            assert n <= 204
            for ident in struct.unpack_from("<" + "H" * n, help_data, ptr):
                kinds.setdefault(ident, set()).add(kind)
        connections[locale] = {ident: sorted(values) for ident, values in kinds.items()}
        text_kind, text_at, text_stride, text_count = next(
            s for s in descriptors(text_data) if s[0] == "TextTableData"
        )
        assert text_stride == 16
        labels = {
            string(text_data, text_at + i * 16, 0): string(text_data, text_at + i * 16, 8)
            for i in range(text_count)
        }
        _, skill_at, skill_stride, skill_count = next(
            s for s in descriptors(skill_data) if s[0] == "SkillParam"
        )
        assert skill_stride == 176
        descriptions, native_groups = {}, []
        for i in range(skill_count):
            at = skill_at + i * skill_stride
            ident = struct.unpack_from("<I", skill_data, at)[0]
            descriptions[ident] = {
                "text": string(skill_data, at, 168),
                "record_at": at,
                "physical_row": i,
            }
            slots = [struct.unpack_from("<4I", skill_data, at + 0x30 + j * 16) for j in range(5)]
            native_groups.append(
                {"skill_id": ident, "physical_row": i, "slots": [list(s) for s in slots if s[0]]}
            )
        tables[locale] = labels
        rows[locale] = effects
        description_rows[locale] = descriptions
        groups[locale] = native_groups
        receipts.append(
            {
                "locale": locale,
                "effect_rows": count,
                "text_rows": text_count,
                "skill_rows": skill_count,
                "help_sha256": hashlib.sha256(help_data).hexdigest(),
                "text_sha256": hashlib.sha256(text_data).hexdigest(),
                "skill_sha256": hashlib.sha256(skill_data).hexdigest(),
            }
        )
    assert all(set(rows[l]) == set(rows["en"]) for l in rows)
    description_id = next(
        i
        for i, r in description_rows["en"].items()
        if r["text"] == "<C9>Shower the enemy with scorching flames."
    )
    description = {l: r[description_id]["text"] for l, r in description_rows.items()}
    assert all(description.values())
    cells = []
    for ident in sorted(rows["en"]):
        for field in ("name", "stat", "format", "turns", "value"):
            cells.append(
                {
                    "physical_id": f"table/t_itemhelp.tbl/SkillEffectHelpData/id:{ident}/{field}",
                    "id": ident,
                    "field": field,
                    "types": rows["en"][ident]["types"],
                    "texts": {l: r[ident][field] for l, r in rows.items()},
                    "records": {
                        l: {k: r[ident][k] for k in ("physical_row", "record_at")}
                        for l, r in rows.items()
                    },
                }
            )
    flags = ["DEBUFF_CANCEL", "DELAY_SHORT", "HITTING", "STUN_L", "STUN_LL"]
    for flag in flags:
        key = "TXT_ITEM_HELP_" + flag
        cells.append(
            {
                "physical_id": "table/t_text.tbl/" + key,
                "field": "native_extra_effect",
                "texts": {l: t[key] for l, t in tables.items()},
                "types": [],
            }
        )
    # Parameter binding is explicit and independent of generated grammar:
    # native type16 has %s for the verified inline icon and %d for turns.
    typed = []
    literal_aliases = []
    for ident, row in rows["en"].items():
        siblings = [r[ident] for r in rows.values()]
        if (
            not row["types"]
            and set(connections["en"].get(ident, ())) & {11, 12}
            and all(
                r["stat"]
                and r["format"].strip()
                and "%" not in r["name"] + r["stat"] + r["format"]
                and r["name"].count(r["stat"]) == 1
                for r in siblings
            )
        ):
            literal_aliases.append(
                {
                    "physical_id": f"table/t_itemhelp.tbl/SkillEffectHelpData/id:{ident}/native_stat_format",
                    "field": "native_literal_constructor",
                    "id": ident,
                    "connection_kinds": connections["en"][ident],
                    "texts": {
                        l: (r[ident]["stat"] + r[ident]["format"]).rstrip() for l, r in rows.items()
                    },
                }
            )
        if row["types"] != [16]:
            continue
        values = {
            l: r[ident]["name"].replace("%s", "<I270>").replace("%d", "5").rstrip()
            for l, r in rows.items()
        }
        assert all("%" not in value for value in values.values())
        typed.append(
            {
                "physical_id": f"table/t_itemhelp.tbl/SkillEffectHelpData/id:{ident}/native_type16",
                "id": ident,
                "field": "native_type16",
                "texts": values,
                "parameters": ["5"],
                "constructor_contract": {"name_arg_string": "<I270>", "turn_arg": 5},
                "types": [16],
            }
        )
    hp = next(c for c in cells if c["field"] == "name" and c["texts"]["en"] == "HP Regen")
    cp = next(c for c in cells if c["field"] == "name" and c["texts"]["en"] == "CP Regen")
    debuff = next(c for c in cells if c["physical_id"].endswith("/TXT_ITEM_HELP_DEBUFF_CANCEL"))
    return {
        "receipts": receipts,
        "cells": cells,
        "typed": typed,
        "literal_constructor_aliases": literal_aliases,
        "description_id": description_id,
        "description": description,
        "description_records": {l: r[description_id] for l, r in description_rows.items()},
        "separators": {l: t["TXT_ITEM_HELP_FORMAT8"] for l, t in tables.items()},
        "mixed": [hp, cp, debuff],
        "raw_skill_effect_groups": groups,
    }


RUNNER = r"""
const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const {RuntimeText}=require(path.join(input.dev,'sora_bilingual/game/scripts/runtime_text.js'));
const raw=JSON.parse(fs.readFileSync(input.fixtures,'utf8')),model=JSON.parse(fs.readFileSync(input.model.path,'utf8'));
const tr=new RuntimeText(model),cfg=input.model.config,base=cfg.game_language,p=cfg.primary,s=cfg.secondary;
const rows=[],failures=[],rejected=[],roles=new Map(),counts={fields:0,accepted:0,plain_equal:0,typed:0,mixed:0,standalone_admitted:0,standalone_refused:0,negatives:0};
const plain=t=>t.replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,'');
const eligible=c=>['name','stat','native_extra_effect'].includes(c.field)&&Object.values(c.texts).some(Boolean)&&
    !Object.values(c.texts).some(t=>t.includes('%'));
for(const c of [...raw.cells.filter(eligible),...raw.literal_constructor_aliases]) {
    const source=plain(c.texts[base]),pair=JSON.stringify([plain(c.texts[p]),plain(c.texts[s])]);
    if(!source.trim())continue;
    if(!roles.has(source))roles.set(source,new Set());roles.get(source).add(pair);
}
const visible=t=>RuntimeText.visualSecondary(t).replace(/<[^<>]*>/g,'').replace(/\s/g,'');
function replay(c,styled=false) {
    counts.fields++;
    const source=plain(c.texts[base]);
    if(!source||!c.texts[p]||!c.texts[s]||roles.get(source)?.size>1) {
        const reason=!source?'blank_source':!c.texts[p]||!c.texts[s]?'missing_language':'ambiguous_role';
        rejected.push({physical_id:c.physical_id,source,reason});
        if(reason==='ambiguous_role') {
            try {assert.equal(tr.details.effectUnits(source),null,'independent raw constructor collision must reject');counts.negatives++;}
            catch(e){failures.push({physical_id:c.physical_id,source,reason:e.message});}
        }
        return;
    }
    const prefix=styled?'<c698>':'',suffix=styled?'</C>':'';
    const member=prefix+source+suffix,full=member+'\n<C0>'+raw.description[base];
    try {
        const units=tr.details.effectUnits(member);assert.ok(units,'missing effect-role contract');
        const unit=units.find(u=>!u.separator);assert.ok(unit.semantic_ids.length);
        assert.equal(plain(unit.pair[0]),plain(prefix+c.texts[p]+suffix));
        assert.equal(plain(unit.pair[1]),plain(prefix+c.texts[s]+suffix));
        assert.equal(tr.translate(full,'primary'),prefix+plain(c.texts[p])+suffix+'\n<C0>'+raw.description[p]);
        assert.equal(tr.translate(full,'secondary'),prefix+plain(c.texts[s])+suffix+'\n<C0>'+raw.description[s]);
        const plan=tr.render(full),effectLayers=plan.layers.filter(l=>l.semantic_ids);
        if(RuntimeText.needsAnnotation(unit.pair[0],unit.pair[1])) {
            assert.equal(effectLayers.length,1);assert.equal(visible(effectLayers[0].text),visible(c.texts[s]));
        } else {assert.equal(effectLayers.length,0);counts.plain_equal++;}
        assert.deepEqual(tr.render(full),plan,'hot renderer drift');
        rows.push({physical_id:c.physical_id,source:member,primary:unit.pair[0],secondary:unit.pair[1],
                   semantic_ids:unit.semantic_ids,parameters:unit.parameters,kind:plan.kind,effect_layers:effectLayers});
        counts.accepted++;if(c.field==='native_type16')counts.typed++;
    } catch(e) {failures.push({physical_id:c.physical_id,input:full,reason:e.message});}
}
for(const c of raw.cells.filter(eligible)){replay(c);replay(c,true);}
for(const c of raw.typed){replay(c);replay(c,true);}
for(const group of [raw.mixed,[raw.typed[0],...raw.mixed.slice(1)]])for(const spanning of [false,true]) {
    const sep=raw.separators[base],wrap=t=>'<c698>'+plain(t)+'</C>';
    const line=spanning?wrap(group.map(c=>c.texts[base]).join(sep)):group.map(c=>wrap(c.texts[base])).join(sep);
    const full=line+'\n<C0>'+raw.description[base];
    try {
        const plan=tr.render(full),layers=plan.layers.filter(l=>l.semantic_ids);
        assert.equal(tr.translate(full,'primary'),spanning?wrap(group.map(c=>plain(c.texts[p])).join(raw.separators[p]))+'\n<C0>'+raw.description[p]:
            group.map(c=>wrap(c.texts[p])).join(raw.separators[p])+'\n<C0>'+raw.description[p]);
        assert.equal(layers.length,group.filter(c=>RuntimeText.needsAnnotation(c.texts[p],c.texts[s])).length);
        assert.ok(layers.every(l=>!l.semantic_ids.some(id=>id.includes('/turns'))));
        rows.push({physical_id:group.map(c=>c.physical_id),input:full,primary:tr.translate(full,'primary'),
                   secondary:tr.translate(full,'secondary'),effect_layers:layers});counts.mixed++;
        const expected=[p,s].map(locale=>spanning?wrap(group.map(c=>plain(c.texts[locale])).join(raw.separators[locale])):
            group.map(c=>wrap(c.texts[locale])).join(raw.separators[locale]));
        const complete=tr.rawPair(line)||tr.pair(plain(line),true);
        const admitted=complete&&complete.every((target,side)=>plain(target)===plain(expected[side]));
        if(admitted) {
            const standalone=tr.render(line),effectLayers=standalone.layers.filter(layer=>layer.semantic_ids);
            assert.equal(effectLayers.length,group.filter(c=>RuntimeText.needsAnnotation(c.texts[p],c.texts[s])).length,
                'complete standalone admission lost semantic granularity');
            assert.equal(visible(effectLayers.map(l=>l.text).join('')),visible(group.map(c=>c.texts[s]).join('')),
                'standalone secondary effects or punctuation leaked');
            rows.push({physical_id:group.map(c=>c.physical_id),input:line,complete_admission:complete,
                       standalone_effect_layers:effectLayers,actual_control_hook:'pending'});counts.standalone_admitted++;
        } else {
            counts.standalone_refused++;
            rejected.push({physical_id:group.map(c=>c.physical_id),input:line,
                reason:complete?'standalone_global_role_disagreement':'standalone_whole_identity_unproven',
                actual_control_hook:'pending'});
        }
    } catch(e){failures.push({physical_id:group.map(c=>c.physical_id),input:full,reason:e.message});}
    for(const bad of [line+sep+'UNKNOWN EFFECT','<UNKNOWN>'+line,'<R>'+line+'</Rnative>']) {
        try {assert.equal(tr.details.effectUnits(bad),null);counts.negatives++;}
        catch(e){failures.push({input:bad,reason:'negative:'+e.message});}
    }
}
const roleRejections=tr.details.model.detail_effect_rejections||[];
process.stdout.write(JSON.stringify({config:cfg,counts,rows,rejected,compiled_role_rejections:roleRejections,failures,passed:!failures.length}));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--dev-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--model-index", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    out = args.evidence_dir.resolve()
    assert out.is_relative_to(PROJECT) and out != PROJECT
    out.mkdir(parents=True, exist_ok=True)
    fixtures = collect(args.game_dir)
    fixture_path = out / "independent-effect-fixtures.json"
    fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), "utf-8")
    models = json.loads((args.model_index or out / "full-model-builds.json").read_text("utf-8"))
    if args.limit:
        models = models[: args.limit]
    summaries = []
    for model in models:
        run = subprocess.run(
            ["node", "--max-old-space-size=6144", "-e", RUNNER],
            cwd=PROJECT,
            input=json.dumps(
                {"dev": str(args.dev_dir.resolve()), "fixtures": str(fixture_path), "model": model}
            ),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        if run.returncode:
            (out / "runner-error.log").write_text(run.stderr, "utf-8")
            raise RuntimeError(run.stderr)
        report = json.loads(run.stdout)
        cfg = model["config"]
        name = (
            "effects-"
            + cfg["game_language"]
            + "-"
            + cfg["primary"]
            + "-"
            + cfg["secondary"]
            + ".json"
        )
        report.update(
            model_sha256=model["sha256"],
            renderer_sha256=hashlib.sha256(
                (args.dev_dir / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
            ).hexdigest(),
            game_attached=False,
            live_user_scene="pending",
            oracle="independent raw table field offsets/type16 argument binding",
        )
        (out / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        summary = {
            "config": cfg,
            "counts": report["counts"],
            "failures": report["failures"],
            "report": name,
            "passed": report["passed"],
        }
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (out / "effect-resource-summary.json").write_text(
        json.dumps(
            {
                "models": summaries,
                "physical_fields": len(fixtures["cells"]),
                "typed16_records": len(fixtures["typed"]),
                "raw_receipts": fixtures["receipts"],
                "game_attached": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    assert all(r["passed"] for r in summaries), "final package effect resource regressions failed"


if __name__ == "__main__":
    main()
