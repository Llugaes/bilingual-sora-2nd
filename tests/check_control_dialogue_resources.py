"""Independent raw-SCP denominator and full-model control-dialogue replay.

Reads all installed script archives. Never starts/attaches to the game. The
renderer replay includes real PCs/raw arguments, capture without a resolver,
canonical-key language reload, and changed dynamic-output negative controls.
"""

import argparse
import base64
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.control_dialogue import control_dialogue_contract
from sora_bilingual.localization.resources import FpacArchive, _logical_script_entries, parse_scp
from sora_bilingual.localization.runtime_identity import _script_manifest_entry

RUNNER = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')),models=[{...input.model,model:JSON.parse(fs.readFileSync(input.model.path,'utf8'))}];
const rows=[],failures=[];
const visible=s=>RuntimeText.visualSecondary(s).replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const c of input.cases) {
 try {
  const loaded=models[0].model.script_identities;
  if(c.locale!==models[0].config.game_language)continue;
  const full=new ScriptIdentities(loaded),manifestOnly=new ScriptIdentities({source_language:loaded.source_language,manifest:loaded.manifest});
  const blob=Buffer.from(c.blob,'base64'),read=n=>blob.subarray(0,n);
  const identity=full.capture(c.signature,read,c.fn,c.token,c.site,c.source);
  assert.ok(identity);assert.equal(identity.callId,c.called);assert.equal(identity.recordKey,c.key);
  assert.equal(identity.controlDialogue,true);assert.deepEqual(identity,manifestOnly.capture(c.signature,read,c.fn,c.token,c.site,c.source));
  for(const r of models) {
   const selected=new ScriptIdentities(r.model.script_identities).lookup(identity,c.source);
   if(!c.texts[r.config.primary]||!c.texts[r.config.secondary]) {
    assert.equal(selected,null,'missing target must refuse');rows.push({key:c.key,source_locale:c.locale,reason:'missing_target_language'});continue;
   }
   assert.ok(selected,'canonical identity missing');
   const tr=new RuntimeText(selected.model),plan=tr.render(c.source);
   assert.equal(tr.translate(c.source,'primary'),c.texts[r.config.primary]);
   assert.equal(tr.translate(c.source,'secondary'),c.texts[r.config.secondary]);
   const payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
   assert.equal(visible(payload),visible(c.texts[r.config.secondary]),'final secondary omitted');
   rows.push({key:c.key,source_locale:c.locale,target:r.config,identity,plan});
  }
  const bad=[
   {token:c.token,source:c.source+' runtime actor',site:c.site},
   {token:c.token,source:/<K[0-9]*>/.test(c.source)?c.source.replace(/<K[0-9]*>/,'<K987>'):c.source+'<K987>',site:c.site},
   {token:c.token.split(',').map((v,i)=>i===c.controlSlot?'17':v).join(','),source:c.source,site:c.site},
   {token:c.token,source:c.source,site:{...c.site,pc:c.site.pc+1}},
  ];
  for(const probe of bad) {
   const rejected=full.capture(c.signature,read,c.fn,probe.token,probe.site,probe.source);
   assert.notEqual(rejected?.recordKey,c.key,'unproved source must not own the canonical identity');
   assert.ok(!rejected||rejected.rejection,'rejection must remain observable');
   assert.equal(full.lookup(rejected,probe.source),null);
  }
 } catch(error) {failures.push({key:c.key,locale:c.locale,reason:error.message,stack:error.stack});}
}
process.stdout.write(JSON.stringify({rows,negative_cases:input.cases.length*4,failures,passed:!failures.length}));
"""


def raw_candidates(data):
    """Inspect physical called descriptors without the production SCP parser."""
    if data[:4] != b"#scp":
        return []
    start, count = struct.unpack_from("<II", data, 4)
    rows = []
    for f in range(count):
        at = start + f * 32
        name_at = struct.unpack_from("<I", data, at + 28)[0] & 0x3FFFFFFF
        name = data[name_at : data.index(b"\0", name_at)].decode("utf-8")
        called_count, called_at = struct.unpack_from("<II", data, at + 16)
        for called in range(called_count):
            _, kind, argc, args_at = struct.unpack_from("<IHHI", data, called_at + 12 * called)
            args = [struct.unpack_from("<II", data, args_at + i * 8) for i in range(argc)]
            if (
                kind == 3
                and argc >= 4
                and args[0] == (0x40000005, 0)
                and any(tag == 2 for _, tag in args[3:])
            ):
                rows.append((name, called))
    return rows


def raw_dialogue(data, function, called, control_slot, control_value):
    """Literal oracle from physical descriptors, independent of SCP assembly.

    The finite control value still requires the separately checked VM proof;
    no arbitrary runtime value is erased or guessed here.
    """
    start, count = struct.unpack_from("<II", data, 4)
    matches = []
    for number in range(count):
        at = start + number * 32
        ptr = struct.unpack_from("<I", data, at + 28)[0] & 0x3FFFFFFF
        if data[ptr : data.index(b"\0", ptr)].decode("utf-8") == function:
            matches.append(at)
    assert len(matches) == 1
    at = matches[0]
    length, calls_at = struct.unpack_from("<II", data, at + 16)
    assert 0 <= called < length
    descriptor = calls_at + 12 * called
    _, kind, argc, args_at = struct.unpack_from("<IHHI", data, descriptor)
    args = [struct.unpack_from("<II", data, args_at + i * 8) for i in range(argc)]
    assert kind == 3 and args[0] == (0x40000005, 0)
    assert args[control_slot] == (0, 2)
    parts, physical = [], []
    for index, (value, tag) in enumerate(args[3:], 3):
        physical.append({"slot": index, "at": args_at + index * 8, "value": value, "tag": tag})
        if index == control_slot:
            parts.append(control_value)
        elif tag == 0 and value >> 30 == 3:
            ptr = value & 0x3FFFFFFF
            parts.append(data[ptr : data.index(b"\0", ptr)].decode("utf-8"))
        elif (value, tag) == (0x4000000A, 0):
            parts.append("\n")
        elif (
            tag == 0
            and value >> 30 == 1
            and (value & 0x3FFFFFFF) in (7, 8, 9, 13, 14, 15, 16, 19, 20, 22, 24, 25, 26, 28)
        ):
            pass
        else:
            raise AssertionError(("unproved raw builder operand", index, value, tag))
    return "".join(parts), {"called_descriptor_at": descriptor, "arguments": physical}


def check(game, directory, dev=ROOT, catalog_directory=None):
    catalog_directory = (
        Path(catalog_directory) if catalog_directory is not None else directory / "full"
    )
    catalog = json.loads((catalog_directory / "catalog.json").read_text("utf-8"))["entries"]
    audit = json.loads((catalog_directory / "scripts/audit.json").read_text("utf-8"))
    diagnostics = [r for r in audit["diagnostics"] if "control_dialogue" in r.get("reason", "")]
    indexed = {(r["language"], r["path"], r["function"], r["called"]): r for r in diagnostics}
    controls = [e for e in catalog if e.get("control_dialogue")]
    proven_paths = {e["key"].split("/called/")[0].rsplit("/", 1)[0] for e in controls}
    denominators, proofs, cases, manifests, raw_texts = {}, [], [], {}, {}
    seen = set()
    models = json.loads((directory / "full-model-builds.json").read_text("utf-8"))
    for locale, filename in archive_names("script").items():
        counts = Counter()
        with FpacArchive(game / "pac/steam" / filename) as archive:
            paths = _logical_script_entries(archive)
            for path, physical in sorted(paths.items()):
                data = archive.read(physical)
                counts["physical_scripts"] += 1
                for fn, called in raw_candidates(data):
                    identity = (locale, path, fn, called)
                    seen.add(identity)
                    assert identity in indexed, ("raw candidate silently omitted", identity)
                    counts[indexed[identity]["status"]] += 1
                if path not in proven_paths:
                    continue
                script = parse_scp(data)
                signature, manifest = _script_manifest_entry(data)
                for entry in controls:
                    prefix, tail = entry["key"].split("/called/")
                    entry_path, fn = prefix.rsplit("/", 1)
                    if entry_path != path:
                        continue
                    if locale not in entry.get("called_ids", {}):
                        continue
                    called = entry["called_ids"][locale]
                    function = script.functions[fn]
                    proof = control_dialogue_contract(function, called)
                    assert (
                        proof
                        and proof["variants"][entry["control_dialogue"]["value"]]
                        == entry["texts"][locale]
                    )
                    literal, raw_evidence = raw_dialogue(
                        data, fn, called, proof["control_slot"], entry["control_dialogue"]["value"]
                    )
                    assert literal == entry["texts"][locale], (
                        "independent raw literal oracle differs"
                    )
                    raw_texts.setdefault(entry["key"], {})[locale] = literal
                    # Mutate the real producer's decoded IR to visible text.
                    # This is an offline negative, not a changed game binary.
                    changed = replace(
                        function,
                        code_strings=tuple(
                            "runtime actor" if s in proof["variants"] else s
                            for s in function.code_strings
                        ),
                    )
                    assert control_dialogue_contract(changed, called) is None
                    proofs.append(
                        {
                            "locale": locale,
                            "key": entry["key"],
                            "proof": proof,
                            "raw_literal_oracle": raw_evidence,
                            "visible_replacement_rejected": True,
                        }
                    )
                    if locale not in {m["config"]["game_language"] for m in models}:
                        continue
                    pc, site = next(
                        (pc, s)
                        for pc, s in manifest["callSites"][fn].items()
                        if s["record"] == called and "controlVariants" in s
                    )
                    value = entry["control_dialogue"]["value"]
                    variant = next(
                        v
                        for v in site["controlVariants"]
                        if v["source"] == proof["variants"][value]
                    )
                    token = site["token"].split(",")
                    token[site["controlSlot"]] = str(variant["token"])
                    cases.append(
                        {
                            "locale": locale,
                            "blob": base64.b64encode(data).decode(),
                            "signature": signature,
                            "fn": fn,
                            "called": called,
                            "controlSlot": site["controlSlot"],
                            "site": {"pc": int(pc), "group": 5, "command": site["command"]},
                            "token": ",".join(token),
                            "source": entry["texts"][locale],
                            "key": entry["key"],
                            "texts": entry["texts"],
                        }
                    )
                    manifests.setdefault(locale, {})[fn] = {
                        "sites": manifest["callSites"][fn],
                        "records": manifest["callRecords"][fn],
                    }
        denominators[locale] = dict(counts)
    assert set(indexed) == seen, ("audit/raw denominator differs", len(indexed), len(seen))
    for case in cases:
        case["source"] = raw_texts[case["key"]][case["locale"]]
        case["texts"] = raw_texts[case["key"]]
    replay = {"rows": [], "failures": [], "negative_cases": 0, "passed": True}
    for model in models:
        selected_cases = [c for c in cases if c["locale"] == model["config"]["game_language"]]
        result = subprocess.run(
            ["node", "--max-old-space-size=6144", "-e", RUNNER],
            cwd=dev,
            input=json.dumps({"model": model, "cases": selected_cases}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        part = json.loads(result.stdout)
        replay["rows"].extend(part["rows"])
        replay["failures"].extend(part["failures"])
        replay["negative_cases"] += part["negative_cases"]
        replay["passed"] &= part["passed"]
    report = {
        "game_attached": False,
        "live_screenshot_raw_source_verified": False,
        "oracle": "independent physical called descriptors/literal strings plus separately checked finite VM control proof",
        "raw_denominators": denominators,
        "candidate_calls": len(seen),
        "classifications": dict(Counter(r["reason"] for r in diagnostics)),
        "diagnostics": diagnostics,
        "proofs": proofs,
        "full_model_replay": replay,
    }
    (directory / "control-dialogue-resources.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    (directory / "joshua-control-manifest.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2), "utf-8"
    )
    (directory / "control-dialogue-raw-cases.json").write_text(
        json.dumps(cases, ensure_ascii=False), "utf-8"
    )
    print(
        json.dumps(
            {
                "candidate_calls": len(seen),
                "proven_locale_variants": len(proofs),
                "renderer_cases": len(replay["rows"]),
                "negative_cases": replay["negative_cases"],
                "failures": replay["failures"],
            }
        ),
        flush=True,
    )
    assert replay["passed"], str(directory / "control-dialogue-resources.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--dev-dir", type=Path, default=ROOT)
    parser.add_argument("--catalog-dir", type=Path)
    args = parser.parse_args()
    output = args.evidence_dir.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError("evidence output must be inside project")
    check(args.game_dir, output, args.dev_dir.resolve(), args.catalog_dir)
