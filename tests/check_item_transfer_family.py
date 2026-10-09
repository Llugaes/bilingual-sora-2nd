"""Raw delivery/receipt helpers -> producer -> VM identity -> slot -> final render."""

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.dynamic_producers import _item_entries, _read_item_rows
from sora_bilingual.localization.dynamic_identity import compile_dynamic_identities, _helper_site
from sora_bilingual.localization.resources import FpacArchive, _logical_script_entries, parse_scp
from sora_bilingual.localization.runtime_identity import script_signature


def check(game, catalog):
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    seeds = [
        e
        for e in entries
        if e["texts"].get("en") == "Handed over " and e["key"].startswith("script/")
    ]
    paths = sorted({e["key"].split(".dat/")[0] + ".dat" for e in seeds})
    assert paths
    scripts, blobs, helpers = {}, {}, []
    for locale, filename in archive_names("script").items():
        scripts[locale], blobs[locale] = {}, {}
        with FpacArchive(game / "pac/steam" / filename) as archive:
            logical = _logical_script_entries(archive)
            for path in paths:
                data = archive.read(logical[path])
                blobs[locale][path] = data
                scripts[locale][path] = parse_scp(data)
                targets = {
                    c.target
                    for fn in scripts[locale][path].functions.values()
                    for c in fn.called
                    if c.target and c.target.startswith(("ITEM_ADD_MESSAGE", "ITEM_SUB_MESSAGE"))
                }
                for helper in targets:
                    pc, program = _helper_site(data, helper)
                    helpers.append(
                        {
                            "locale": locale,
                            "path": path,
                            "helper": helper,
                            "pc": pc,
                            "program": program,
                        }
                    )
    audit = {"counters": Counter(), "diagnostics": []}
    producers = _item_entries(scripts, _read_item_rows(game, audit), audit)
    cases, models, encoded = [], {}, {}
    for locale in ("en", "zh-Hans", "ja"):
        dynamic = compile_dynamic_identities(game, producers, "zh-Hans", "ja", locale)
        manifest = {}
        for path, data in blobs[locale].items():
            digest = hashlib.sha256(data).hexdigest()
            encoded[digest] = base64.b64encode(data).decode("ascii")
            helpers_for_blob = dynamic["scripts"].get(digest, {})
            manifest[script_signature(data)] = [
                {"size": len(data), "sha256": digest, "functions": list(helpers_for_blob)}
            ]
            for helper, tokens in helpers_for_blob.items():
                for token, claim in tokens.items():
                    entry = next(e for e in producers if e["key"] == claim["recordKey"])
                    for icon in (5, 110, 2147483647):
                        source = entry["texts"][locale].replace("%d", str(icon))
                        cases.append(
                            {
                                "locale": locale,
                                "signature": script_signature(data),
                                "digest": digest,
                                "helper": helper,
                                "token": token,
                                "pc": claim["pc"],
                                "source": source,
                                "key": entry["key"],
                                "expected": [
                                    entry["texts"][l].replace("%d", str(icon))
                                    for l in ("zh-Hans", "ja")
                                ],
                            }
                        )
        models[locale] = {
            "source_language": locale,
            "manifest": manifest,
            "scripts": {},
            "dynamic_producers": dynamic,
        }
    runner = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js'),
{ScriptIdentities,LogIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),resolvers=Object.fromEntries(Object.entries(input.models).map(([k,v])=>[k,new ScriptIdentities(v)]));
let checked=0;const failures=[],log=new LogIdentities();
for(const c of input.cases){const tr=resolvers[c.locale],data=Buffer.from(input.blobs[c.digest],'base64'),
 identity=tr.capture(c.signature,n=>data.slice(0,n),c.helper,c.token,{pc:c.pc,group:5,command:8},c.source);
 log.commit(checked%1600,c.source,identity);const owner=log.lookup(checked%1600,c.source),local=owner&&tr.lookup(owner,c.source);
 const r=local&&new RuntimeText(local.model),actual=r&&[r.translate(c.source,'primary'),r.translate(c.source,'secondary')],plan=r&&r.render(c.source,'annotation');
 if(JSON.stringify(actual)!==JSON.stringify(c.expected)||(RuntimeText.needsAnnotation(...c.expected)&&plan?.kind==='plain'))failures.push({key:c.key,locale:c.locale,stage:!identity?'capture':!local?'lookup':'render',actual});
 // Same bytes without the verified VM origin cannot recover a slot identity.
 log.commit(checked%1600,c.source,null);if(log.lookup(checked%1600,c.source)!==null)failures.push({stage:'unowned_slot'});checked++;}
process.stdout.write(JSON.stringify({checked,failures}));
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"models": models, "cases": cases, "blobs": encoded}, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    render = json.loads(result.stdout)
    assert not render["failures"], render["failures"][:3]
    new_removals = [
        e
        for e in producers
        if any(
            "ITEM_SUB_" in c.target
            for locale in scripts
            for fn in [
                scripts[locale][e["producer_origin"]["signature"]["path"]].functions[
                    e["producer_origin"]["signature"]["function"]
                ]
            ]
            for c in [fn.called[e["producer_origin"]["signature"]["called"]]]
            if c.target
        )
    ]
    old_keys = {e["key"] for e in entries}
    return {
        "paths": paths,
        "helper_contracts": helpers,
        "producer_records": len(producers),
        "removal_records": len(new_removals),
        "new_removal_records": sum(e["key"] not in old_keys for e in new_removals),
        "removal_owners": [
            {"key": e["key"], "texts": e["texts"], "origin": e["producer_origin"]}
            for e in new_removals
        ],
        "stats": {l: m["dynamic_producers"]["stats"] for l, m in models.items()},
        "audit": audit,
        **render,
        "limits": [
            "Bounded raw seed paths include every item-message call in those scripts, not all game events.",
            "Actual screenshot call, VM output lifetime and label carrier are unobserved.",
            "No live process, native host attachment, UI, or game was launched.",
        ],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "catalog", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    report = check(a.game, a.catalog)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "producer_records",
                    "removal_records",
                    "new_removal_records",
                    "checked",
                    "failures",
                )
            }
        )
    )
