"""Independent raw ConditionHelpData/type17 field oracle across eight locales."""

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.item_help_composition import (
    _condition_parameter_entries,
    _entry_map,
    _record_fields,
    read_item_help_metadata,
)
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


def main():
    game = Path(sys.argv[1])
    entries = json.loads((ROOT / "generated/r20-production/catalog.json").read_text("utf-8"))[
        "entries"
    ]
    metadata, _ = read_item_help_metadata(game)
    records = metadata["SkillEffectHelpData"]
    catalogue = _entry_map(entries)
    fields = {
        identity: _record_fields(catalogue, identity, LANGUAGES)
        for identity in records
        if "table/t_itemhelp.tbl/SkillEffectHelpData/" + identity + "/name" in catalogue
    }
    generated = _condition_parameter_entries(entries, fields, records, LANGUAGES)
    names, templates, inventory = {}, {}, []
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            data = archive.read(_logical_tables(archive)["table/t_itemhelp.tbl"])

        def text(pointer):
            return data[pointer : data.index(b"\0", pointer)].decode("utf-8") if pointer else ""

        _, start, stride, count = next(s for s in sections(data) if s[0] == "ConditionHelpData")
        condition_count = count
        assert stride == 40
        for index in range(count):
            at = start + index * stride
            scalar = data[at : at + 8].hex()
            name = text(struct.unpack_from("<Q", data, at + 16)[0])
            assert locale not in names.setdefault(scalar, {})
            names[scalar][locale] = name
        _, start, stride, count = next(s for s in sections(data) if s[0] == "SkillEffectHelpData")
        assert stride == 88
        for index in range(count):
            at = start + index * stride
            pointer, length = struct.unpack_from("<QI", data, at + 16)
            types = struct.unpack_from("<" + "H" * length, data, pointer) if length else ()
            if types == (17,):
                record_id = struct.unpack_from("<I", data, at)[0]
                templates.setdefault(record_id, {})[locale] = text(
                    struct.unpack_from("<Q", data, at + 8)[0]
                )
        inventory.append(
            {
                "locale": locale,
                "condition_rows": condition_count,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    oracle = {
        tuple(templates[i][l].replace("%s", n[l]) for l in LANGUAGES)
        for i in templates
        for n in names.values()
        if all(n[l] for l in LANGUAGES)
    }
    assert {tuple(r["texts"][l] for l in LANGUAGES) for r in generated} == oracle
    batches, checked = [], 0
    for source in LANGUAGES:
        for target in LANGUAGES:
            tr = MenuTranslator(generated, source, target, source)
            tests = []
            for row in generated:
                for value in (0, 50, 100):
                    original = row["texts"][source].replace("%d", str(value)).replace("%%", "%")
                    expected = row["texts"][target].replace("%d", str(value)).replace("%%", "%")
                    assert tr.translate(original, "secondary") == expected
                    tests.append({"source": original, "expected": expected})
                    checked += 1
            batches.append({"model": tr.runtime_model(), "tests": tests})
    runner = """
const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const batches=JSON.parse(fs.readFileSync(0,'utf8'));let checked=0;
for(const batch of batches){const tr=new RuntimeText(batch.model);for(const c of batch.tests){assert.equal(tr.translate(c.source,'secondary'),c.expected);checked++;}}
console.log(JSON.stringify({checked}));
"""
    js = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(batches),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    assert json.loads(js.stdout)["checked"] == checked
    changed = {k: dict(v) for k, v in records.items()}
    for record in changed.values():
        if record["parameter_types"] == (17,):
            record["parameter_types"] = (1,)
    assert not _condition_parameter_entries(entries, fields, changed, LANGUAGES)
    result = {
        "condition_help_enum_rows": len(names),
        "unique_complete_templates": len(generated),
        "native_type17_records": sorted(templates),
        "language_pairs": len(batches),
        "python_checks": checked,
        "javascript_checks": checked,
        "wrong_type_refused": True,
        "raw_table_inventory": inventory,
        "game_attached": False,
        "live_verified": False,
    }
    (ROOT / "generated/r20-condition-parameter-matrix.json").write_text(
        json.dumps(result, indent=2), "utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "raw_table_inventory"}))


if __name__ == "__main__":
    main()
