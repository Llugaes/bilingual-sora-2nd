"""Offline replay: capture source IDs with Japanese, resolve them after switching language."""

import argparse
import base64
from collections import defaultdict
import gc
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.localization.resources import (
    FpacArchive,
    _ARCHIVES,
    _logical_script_entries,
    _utf8z,
)
from sora_bilingual.localization.runtime_identity import script_signature

# Same actor/source body, but different official English translations.
CALLS = [
    ("mp3010_01.dat", "QS210_04_00", 48),
    ("mp3010_01.dat", "TK_FEY", 6),
    ("mp3010_01.dat", "QS212_00_00", 94),
    ("mp3010_08.dat", "QS300_02_00", 157),
]
RUNNER = r"""
const fs=require('fs'),assert=require('node:assert/strict');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const before=JSON.parse(fs.readFileSync(data.models.ja,'utf8'));
const capture=new ScriptIdentities(before.script_identities);
// Provenance remains usable even when the active pair needs no local resolver.
const manifestOnly=new ScriptIdentities({
 source_language:before.script_identities.source_language,
 manifest:before.script_identities.manifest,
});
const saved=data.cases.map(c=>{
 const blob=Buffer.from(c.blob,'base64');
 const identity=capture.capture(c.signature,n=>blob.subarray(0,n),c.fn,c.token,c.site,c.source);
 assert.ok(identity,c.key+' captures identity');
 assert.equal(identity.callId,c.called,'canonical called-record ID');
 assert.deepEqual(identity,manifestOnly.capture(c.signature,n=>blob.subarray(0,n),c.fn,c.token,c.site,c.source));
 return {c,identity};
});
const report=[];
for(const [locale,path] of Object.entries(data.models)) {
 const model=JSON.parse(fs.readFileSync(path,'utf8'));
 assert.deepEqual(model.script_identities.manifest,before.script_identities.manifest,'source manifest is language-independent');
 const ids=new ScriptIdentities(model.script_identities),global=new RuntimeText(model);
 for(const {c,identity} of saved) {
  const local=ids.lookup(identity,c.source),tr=local?new RuntimeText(local.model):global;
  const expected=c.targets[locale];
  assert.equal(tr.translate(c.source,'secondary'),expected,c.key+' '+locale);
  const plan=tr.render(c.source,'annotation');
  const payload=plan.layers.map(l=>l.text).join('')+
   [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
  const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
  assert.equal(visible(payload),visible(RuntimeText.visualSecondary(expected)),c.key+' annotation '+locale);
  report.push({key:c.key,locale,pass:true,local_lookup:!!local});
 }
}
process.stdout.write(JSON.stringify(report));
"""


def canonical_record_audit(entries):
    calls_by_key = defaultdict(set)
    keys_by_call = defaultdict(set)
    for entry in entries:
        key = entry.get("key", "").split("/alignment/", 1)[0]
        if not key.endswith("/assembled_dialogue") or "/called/" not in key:
            continue
        prefix, tail = key.rsplit("/called/", 1)
        canonical = tail.split("/", 1)[0]
        if not canonical.isdigit():
            continue
        for locale in entry["texts"]:
            called_ids = entry.get("called_ids")
            actual = called_ids.get(locale) if called_ids is not None else int(canonical)
            if not isinstance(actual, int):
                continue
            physical = (locale, prefix, actual)
            calls_by_key[locale, key].add(physical)
            keys_by_call[physical].add(key)
    merged_calls = {
        f"{locale}:{key}": sorted(values)
        for (locale, key), values in calls_by_key.items()
        if len(values) > 1
    }
    multiple_keys = {
        ":".join(map(str, physical)): sorted(values)
        for physical, values in keys_by_call.items()
        if len(values) > 1
    }
    return {
        "canonical_records": len(calls_by_key),
        "physical_calls": len(keys_by_call),
        "canonical_keys_merging_independent_calls": merged_calls,
        "physical_calls_with_multiple_canonical_keys": multiple_keys,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/history-identity-check.json"
    )
    args = parser.parse_args()
    entries, signature = load_entries(args.game_dir)
    canonical_audit = canonical_record_audit(entries)
    assert not canonical_audit["canonical_keys_merging_independent_calls"]
    indexed = {e["key"]: e for e in entries}
    cases, raw_sources = [], {}
    archive = FpacArchive(args.game_dir / "pac/steam" / _ARCHIVES["zh-Hans"])
    try:
        logical = _logical_script_entries(archive)
        for name, fn, call in CALLS:
            path = "script/scena/" + name
            blob = archive.read(logical[path])
            start, count = struct.unpack_from("<II", blob, 4)
            at = next(
                start + i * 32
                for i in range(count)
                if _utf8z(blob, struct.unpack_from("<I", blob, start + i * 32 + 28)[0] & 0x3FFFFFFF)
                == fn
            )
            call_count, calls_at = struct.unpack_from("<II", blob, at + 16)
            assert call < call_count
            _, kind, argc, arg_at = struct.unpack_from("<IHHI", blob, calls_at + call * 12)
            values = [struct.unpack_from("<II", blob, arg_at + i * 8) for i in range(argc)]
            assert kind == 3 and all(k == 0 for _, k in values)
            # Independently locate this real VM instruction from its complete
            # reversed literal argument pushes, not the metadata ordinal.
            instruction = b"".join(
                b"\x00\x04" + struct.pack("<I", v) for v, _ in reversed(values[2:])
            )
            command = values[1][0] - 0x40000000
            instruction += bytes((36, 5, command, argc - 2))
            instruction_at = blob.find(instruction)
            assert instruction_at >= 0 and blob.find(instruction, instruction_at + 1) < 0
            key = f"{path}/{fn}/called/{call}/assembled_dialogue"
            entry = indexed[key]
            cases.append(
                {
                    "key": key,
                    "source": entry["texts"]["zh-Hans"],
                    "targets": entry["texts"],
                    "fn": fn,
                    "token": ",".join(str(v) for v, _ in values[2:]),
                    "called": call,
                    "site": {
                        "pc": instruction_at + len(instruction),
                        "group": 5,
                        "command": command,
                    },
                    "blob": base64.b64encode(blob).decode(),
                    "signature": script_signature(blob),
                }
            )
        # Independent raw archive denominator, including scripts not selected by any resolver.
        for path, physical in logical.items():
            if path.endswith(".dat"):
                blob = archive.read(physical)
                raw_sources[hashlib.sha256(blob).hexdigest()] = (path, len(blob))
    finally:
        archive.close()
    models, manifest, model_metrics = {}, None, {}
    for locale in ("ja", "en"):
        config = {
            "game_language": "zh-Hans",
            "primary": "zh-Hans",
            "secondary": locale,
            "scope": "all",
        }
        model = load_model(entries, signature, config, game=args.game_dir)
        current = model["script_identities"]["manifest"]
        assert manifest is None or manifest == current
        manifest = current
        path = model_path(signature, config)
        models[locale] = str(path)
        identities = model["script_identities"]
        mapped = [
            row
            for bucket in identities["manifest"].values()
            for candidate in bucket
            for records in candidate.get("recordKeys", {}).values()
            for row in records.values()
        ]
        mapped_with_pair = sum(row["key"] in identities["record_pairs"] for row in mapped)
        model_metrics[locale] = {
            "bytes": path.stat().st_size,
            "record_pairs": len(identities["record_pairs"]),
            "record_pair_values": len(identities["record_pair_values"]),
            "manifest_record_keys": len(mapped),
            "manifest_record_keys_with_pair": mapped_with_pair,
            "record_index_bytes": len(
                json.dumps(
                    {
                        "record_pairs": identities["record_pairs"],
                        "record_pair_values": identities["record_pair_values"],
                    },
                    ensure_ascii=False,
                ).encode()
            ),
        }
        del model
        gc.collect()
    captured = {c["sha256"] for bucket in manifest.values() for c in bucket}
    assert captured == raw_sources.keys(), "Every raw source script must be represented"
    result = subprocess.run(
        ["node", "-e", RUNNER],
        cwd=ROOT,
        input=json.dumps({"cases": cases, "models": models}, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    report = {
        "game_attached": False,
        "all_passed": True,
        "raw_unique_scripts": len(raw_sources),
        "manifest_bytes": len(json.dumps(manifest, ensure_ascii=False).encode()),
        "max_script_bytes": max(size for _, size in raw_sources.values()),
        "canonical_record_audit": canonical_audit,
        "models": model_metrics,
        "checks": json.loads(result.stdout),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}))


if __name__ == "__main__":
    main()
