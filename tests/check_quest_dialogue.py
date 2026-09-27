"""Replay one complete quest from raw PAC records through production RuntimeText.

The QS214 family is deliberately selected by its script call chain and quest
table identity.  Screenshot fragments are reported only as locators; they do
not define the coverage denominator.
"""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.menu_tables import (
    record_identity,
    schema_for,
    sections,
)
from sora_bilingual.localization.menu_text import (
    _without_line_padding,
    display_text,
)
from sora_bilingual.localization.native_catalog import (
    load_entries,
    load_model,
    model_path,
)
from sora_bilingual.localization.resources import (
    FpacArchive,
    _logical_script_entries,
    assembled_dialogue,
    parse_scp,
)
from sora_bilingual.localization.runtime_identity import script_signature
from sora_bilingual.localization.tables import _logical_tables


QUEST_SCRIPT_PATHS = (
    "script/scena/mp3000_ev.dat",
    "script/scena/mp3041_02.dat",
)
QUEST_FUNCTION = re.compile(r"^QS214_")
QUEST_ID = 24
QUEST_TABLE_PATH = "table/t_quest_fc.tbl"
QUEST_TABLE_GROUP = 169
REPORTED_RAW = {
    "给我站——住！": "给我站──住！",
    "喂喂！！": "喂─────！",
    "艾丝蒂尔！我们快追上去！": "艾丝蒂尔！　我们快追上去！",
    "了、了解！": "了、了解！",
    "呀啊啊——！": "呀啊啊──！",
    "——看来总算是放弃了。": "──看来总算是放弃了。",
    "稍微惩罚一下吧。": "稍微惩罚一下吧。",
    "这下总算是……": "这下总算是……",
    "是啊，似乎做个了结了。": "是啊，似乎做个了结了。",
}

RUNNER = r"""
const fs=require('fs'),assert=require('node:assert/strict');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
function payload(plan,source) {
 const native=[...source.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]);
 const added=[];
 for(const match of plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)) {
  const at=native.indexOf(match[1]);
  if(at>=0)native.splice(at,1);else if(match[1]!=='_')added.push(match[1]);
 }
 return plan.layers.map(l=>l.text).join('')+added.join('');
}
function checkRender(tr,source,expectedPrimary,expectedSecondary,label) {
 assert.equal(tr.translate(source,'primary'),expectedPrimary,label+' primary translate');
 assert.equal(tr.translate(source,'secondary'),expectedSecondary,label+' secondary translate');
 const plan=tr.render(source,'annotation');
 const secondary=visible(RuntimeText.visualSecondary(expectedSecondary));
 assert.equal(visible(payload(plan,expectedPrimary)),RuntimeText.needsAnnotation(expectedPrimary,expectedSecondary)?secondary:'',label+' render');
}
const full={},fullReport=[],fallback={};
for(const [target,path] of Object.entries(data.models)) {
 const model=JSON.parse(fs.readFileSync(path,'utf8'));
 const ids=new ScriptIdentities(model.script_identities),global=new RuntimeText(model);
 full[target]={model,ids,global};fallback[target]={passed:0,unresolved:[]};
 for(const c of data.dialogues) {
  const blob=Buffer.from(data.blobs[c.sha256],'base64');
  const identity=ids.capture(c.signature,n=>blob.subarray(0,n),c.function,c.token,c.site,c.source);
  assert.ok(identity,c.key+' '+target+' capture');
  assert.equal(identity.callId,c.called,c.key+' '+target+' call ID');
  assert.equal(identity.recordKey,c.record_key,c.key+' '+target+' stable key');
  const local=ids.lookup(identity,c.source);
  assert.ok(local,c.key+' '+target+' record lookup');
  checkRender(new RuntimeText(local.model),c.source,c.source,c.targets[target],c.key+' '+target);
  const history=global.historyContext(c.speaker||'',c.source,'body');
  if(history) {
   const translated=history.tr.translate(c.source,'secondary');
   if(translated===c.targets[target]) {
    checkRender(history.tr,c.source,c.source,c.targets[target],c.key+' '+target+' history');
    fallback[target].passed++;
   } else fallback[target].unresolved.push({key:c.key,reason:'target-mismatch',speaker:c.speaker||'',source:c.source,actual:translated,expected:c.targets[target]});
  } else fallback[target].unresolved.push({key:c.key,reason:'no-unique-context',speaker:c.speaker||'',source:c.source});
  fullReport.push({key:c.key,target,identity:true,history:!!history});
 }
 for(const c of data.table)checkRender(global,c.source,c.source,c.targets[target],c.key+' '+target);
}
let matrix=0;
for(const c of data.all_locale_dialogues)for(const source of data.languages)for(const primary of data.languages)for(const secondary of data.languages) {
 if(primary===secondary)continue;
 const sourceText=c.texts[source],primaryText=c.texts[primary],secondaryText=c.texts[secondary];
 const model={source_language:source,record_pairs:{[c.record_key]:0},record_pair_values:[[primaryText,secondaryText]]};
 const ids=new ScriptIdentities(model);
 const identity={callId:c.called_ids[source],recordKey:c.record_key,source:sourceText,sourceLocale:source};
 const local=ids.lookup(identity,sourceText);
 assert.ok(local,c.record_key+' '+source+'>'+primary+'+'+secondary+' local lookup');
 checkRender(new RuntimeText(local.model),sourceText,primaryText,secondaryText,c.record_key+' '+source+'>'+primary+'+'+secondary);
 matrix++;
}
process.stdout.write(JSON.stringify({full_cases:fullReport.length,identity_local_matrix:matrix,history_fallback:fallback}));
"""


def _called_from_key(entry: dict, language: str) -> int:
    called_ids = entry.get("called_ids")
    if called_ids is not None:
        return called_ids[language]
    return int(entry["key"].split("/called/", 1)[1].split("/", 1)[0])


def _canonical_key(entry: dict) -> str:
    return entry["key"].split("/alignment/", 1)[0]


def _physical_call(entry: dict, language: str) -> str:
    canonical = _canonical_key(entry)
    prefix, separator, suffix = canonical.partition("/called/")
    if not separator or not suffix.split("/", 1)[0].isdigit():
        return canonical
    called = entry.get("called_ids", {}).get(language, int(suffix.split("/", 1)[0]))
    return f"{prefix}/called/{called}"


def _history_unresolved_audit(entries, models, runtime, names_by_locale):
    """Explain every identity-less history rejection from the complete catalog."""
    selected = [entry for entry in entries if entry.get("display_role") == "dialogue"]
    result = {}
    for target, state in runtime["history_fallback"].items():
        history = models[target]["history_contexts"]
        audited = []
        for unresolved in state["unresolved"]:
            body = display_text(unresolved["source"])
            speaker = unresolved["speaker"]
            claims = defaultdict(lambda: {"pairs": set(), "incomplete": set(), "speaker": ""})
            for entry in selected:
                texts = entry["texts"]
                pair = tuple(
                    display_text(texts[language]) if language in texts else None
                    for language in ("zh-Hans", target)
                )
                for language, value in texts.items():
                    if display_text(value) != body:
                        continue
                    physical = (_physical_call(entry, language), language)
                    actor = entry.get("speaker_ids", {}).get(language)
                    name = names_by_locale.get(language, {}).get(actor, "")
                    if name:
                        claims[physical]["speaker"] = name
                    bucket = "pairs" if all(pair) else "incomplete"
                    claims[physical][bucket].add(pair)

            candidates = []
            speaker_pairs = set()
            unknown_incomplete = False
            for (physical, language), claim in sorted(claims.items()):
                remaining = {
                    incomplete
                    for incomplete in claim["incomplete"]
                    if not any(
                        not any(
                            value is not None and value != complete[index]
                            for index, value in enumerate(incomplete)
                        )
                        for complete in claim["pairs"]
                    )
                }
                relevant = claim["speaker"] == speaker or (remaining and not claim["speaker"])
                if not relevant:
                    continue
                if claim["speaker"] == speaker:
                    speaker_pairs.update(claim["pairs"])
                    if remaining:
                        speaker_pairs.add(None)
                elif remaining:
                    unknown_incomplete = True
                candidates.append(
                    {
                        "physical": physical,
                        "source_locale": language,
                        "speaker": claim["speaker"],
                        "complete_pairs": sorted(claim["pairs"]),
                        "undominated_incomplete": sorted(
                            remaining, key=lambda value: tuple(part or "" for part in value)
                        ),
                    }
                )
            if unknown_incomplete:
                speaker_pairs.add(None)
            exact_pairs = {pair for pair in speaker_pairs if pair is not None}
            normalized = {
                tuple(_without_line_padding(value) for value in pair) for pair in exact_pairs
            }
            global_index = history["texts"].get(body)
            speaker_map = history.get("speakers", {}).get(speaker, {}) if speaker else {}
            speaker_index = speaker_map.get(body)
            reasons = []
            if body not in history["texts"]:
                reasons.append("body-missing-from-global-index")
            if len(normalized) > 1:
                reasons.append("same-speaker-real-wording-conflict")
            elif len(exact_pairs) > 1:
                reasons.append("edge-padding-only-variants")
            if None in speaker_pairs:
                reasons.append("undominated-incomplete-physical-candidate")
            if global_index == -1 and speaker_index is None:
                reasons.append("speaker-narrowing-index-missing")
            elif speaker_index == -1:
                reasons.append("speaker-narrowing-remains-ambiguous")
            elif isinstance(speaker_index, int) and speaker_index >= 0:
                reasons.append("runtime-rejected-valid-speaker-index")
            audited.append(
                {
                    "key": unresolved["key"],
                    "body": body,
                    "speaker": speaker,
                    "global_index": global_index,
                    "speaker_index": speaker_index,
                    "reasons": reasons,
                    "normalized_pair_variants": len(normalized),
                    "candidates": candidates,
                }
            )
        result[target] = audited
    return result


def _quest_dialogue_entries(entries: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for entry in entries:
        key = entry.get("key", "")
        if (
            not any(key.startswith(path + "/QS214_") for path in QUEST_SCRIPT_PATHS)
            or "/assembled_dialogue" not in key
            or set(entry["texts"]) != set(LANGUAGES)
        ):
            continue
        canonical = _canonical_key(entry)
        current = result.get(canonical)
        if current is not None and current["texts"] != entry["texts"]:
            raise AssertionError(f"conflicting complete quest record: {canonical}")
        result[canonical] = entry
    return result


def _manifest_case(model: dict, blob: bytes, function: str, called: int) -> dict:
    identities = model["script_identities"]
    signature = script_signature(blob)
    digest = hashlib.sha256(blob).hexdigest()
    candidates = identities["manifest"][signature]
    candidate = next(item for item in candidates if item["sha256"] == digest)
    sites = [
        (pc, site)
        for pc, site in candidate["callSites"][function].items()
        if site["record"] == called
    ]
    if len(sites) != 1:
        raise AssertionError(f"{function}/{called}: expected one native call site, got {sites}")
    pc, site = sites[0]
    return {
        "signature": signature,
        "sha256": digest,
        "token": site["token"],
        "site": {"pc": int(pc), "group": site["group"], "command": site["command"]},
    }


def _read_scripts(game: Path):
    archives = {
        language: FpacArchive(game / "pac/steam" / archive_names("script")[language])
        for language in LANGUAGES
    }
    try:
        logical = {language: _logical_script_entries(a) for language, a in archives.items()}
        discovered = {
            path
            for path, physical in logical["zh-Hans"].items()
            if b"QS214" in archives["zh-Hans"].read(physical)
        }
        if discovered != set(QUEST_SCRIPT_PATHS):
            raise AssertionError(f"QS214 script scope changed: {sorted(discovered)}")
        blobs = {
            language: {
                path: archives[language].read(logical[language][path])
                for path in QUEST_SCRIPT_PATHS
            }
            for language in LANGUAGES
        }
        parsed = {
            language: {path: parse_scp(data) for path, data in by_path.items()}
            for language, by_path in blobs.items()
        }
        return blobs, parsed
    finally:
        for archive in archives.values():
            archive.close()


def _read_quest_table(game: Path, catalog: dict[str, dict]):
    archives = {
        language: FpacArchive(game / "pac/steam" / archive_names("table")[language])
        for language in LANGUAGES
    }
    try:
        found = defaultdict(dict)
        raw_rows = defaultdict(dict)
        for language, archive in archives.items():
            data = archive.read(_logical_tables(archive)[QUEST_TABLE_PATH])
            all_sections = sections(data)
            text_floor = max(start + size * count for _, start, size, count in all_sections)
            for kind, start, size, count in all_sections:
                if kind not in ("QuestTitle", "QuestText"):
                    continue
                schema = schema_for(QUEST_TABLE_PATH, kind)
                for row in range(count):
                    at = start + row * size
                    if struct.unpack_from("<H", data, at)[0] != QUEST_TABLE_GROUP:
                        continue
                    identity = record_identity(data, at, kind, schema, text_floor)
                    fields = {}
                    for field, offset in schema.fields:
                        pointer = struct.unpack_from("<Q", data, at + offset)[0]
                        if pointer:
                            end = data.find(b"\0", pointer)
                            value = data[pointer:end].decode("utf-8")
                            if value:
                                fields[field] = value
                    found[kind, row][language] = identity
                    raw_rows[kind, row][language] = fields
        title_rows = {row for kind, row in found if kind == "QuestTitle"}
        text_rows = {row for kind, row in found if kind == "QuestText"}
        if title_rows != {18} or text_rows != set(range(200, 213)):
            raise AssertionError("quest table group 169 row scope changed")
        cases = []
        for (kind, row), by_language in sorted(raw_rows.items()):
            identities = set(found[kind, row].values())
            if len(identities) != 1 or set(by_language) != set(LANGUAGES):
                raise AssertionError(f"{kind}/{row}: locale identity mismatch")
            identity = next(iter(identities))
            fields = set.intersection(*(set(value) for value in by_language.values()))
            for field in sorted(fields):
                key = f"{QUEST_TABLE_PATH}/{kind}/{identity}/{field}"
                entry = catalog[key]
                texts = {language: by_language[language][field] for language in LANGUAGES}
                if entry["texts"] != texts:
                    raise AssertionError(f"{key}: catalog differs from raw table")
                cases.append({"key": key, "texts": texts})
        return cases
    finally:
        for archive in archives.values():
            archive.close()


def _native_default_speaker_evidence(game: Path) -> dict:
    import pefile

    executable = game / "sora_2nd.exe"
    data = executable.read_bytes()
    pe = pefile.PE(data=data, fast_load=True)
    expected = {
        0x4AE2DB: "4533ff",
        0x4AE2DE: "bb00000040",
        0x4AE2E9: "8bc3",
        0x4AE30D: "8d3c85",
        0x4AE32F: "418bff",
        0x4AE332: "8bd7",
    }
    actual = {}
    for rva, prefix in expected.items():
        offset = pe.get_offset_from_rva(rva)
        actual[hex(rva)] = data[offset : offset + len(bytes.fromhex(prefix))].hex()
        if actual[hex(rva)] != prefix:
            raise AssertionError(f"native command-0 contract changed at {rva:#x}")
    pointer_at = pe.get_offset_from_rva(0xB12418)
    callback = struct.unpack_from("<Q", data, pointer_at)[0] - pe.OPTIONAL_HEADER.ImageBase
    if callback != 0x4B02D0:
        raise AssertionError("talk callback vtable changed")
    return {
        "exe_sha256": hashlib.sha256(data).hexdigest(),
        "talk_handler_rva": "0x4ae2a0",
        "talk_callback_rva": hex(callback),
        "proof_bytes": actual,
        "contract": (
            "No argument and a non-numeric first argument both initialize speaker to zero; "
            "an explicit tagged integer zero decodes to the same value before speaker lookup."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/quest-dialogue-check.json")
    args = parser.parse_args()
    entries, signature = load_entries(args.game_dir)
    indexed = {entry["key"]: entry for entry in entries}
    complete = _quest_dialogue_entries(entries)
    blobs, parsed = _read_scripts(args.game_dir)

    functions = sorted(
        {
            name
            for by_path in parsed["zh-Hans"].values()
            for name in by_path.functions
            if QUEST_FUNCTION.match(name)
        }
    )
    denominator = []
    signature_mismatches = []
    quest_end = []
    for path in QUEST_SCRIPT_PATHS:
        names = {
            name
            for script in parsed["zh-Hans"][path].functions.values()
            for name in (script.name,)
            if QUEST_FUNCTION.match(name)
        }
        for name in sorted(names):
            family = {language: parsed[language][path].functions[name] for language in LANGUAGES}
            if len({(function.flags, function.arg_types) for function in family.values()}) != 1:
                signature_mismatches.append(f"{path}/{name}")
            counts = {
                language: sum(assembled_dialogue(call) is not None for call in function.called)
                for language, function in family.items()
            }
            denominator.append({"path": path, "function": name, "dialogues": counts})
            for language, function in family.items():
                for called, call in enumerate(function.called):
                    if call.target == "QUEST_END":
                        quest_end.append(
                            {
                                "language": language,
                                "path": path,
                                "function": name,
                                "called": called,
                                "args": call.args,
                            }
                        )
    if signature_mismatches:
        raise AssertionError(f"quest function signatures differ: {signature_mismatches}")
    if len(quest_end) != len(LANGUAGES) or any(
        item["function"] != "QS214_04_00_END" or item["args"] != (("int", QUEST_ID),)
        for item in quest_end
    ):
        raise AssertionError(f"QUEST_END({QUEST_ID}) call chain changed")

    expected_records = sum(item["dialogues"]["zh-Hans"] for item in denominator)
    if expected_records != 437 or len(complete) != expected_records:
        raise AssertionError(
            f"quest denominator mismatch: raw={expected_records}, catalog={len(complete)}"
        )

    models = {}
    loaded_models = {}
    for target in ("ja", "en"):
        config = {
            "primary": "zh-Hans",
            "secondary": target,
            "game_language": "zh-Hans",
            "scope": "all",
            "sources": [],
        }
        loaded_models[target] = load_model(entries, signature, config, game=args.game_dir)
        models[target] = str(model_path(signature, config))

    source_model = loaded_models["ja"]
    from sora_bilingual.localization.speaker_context import read_speaker_names

    names_by_locale = {
        language: read_speaker_names(args.game_dir, language) for language in LANGUAGES
    }
    speaker_names = names_by_locale["zh-Hans"]
    node_dialogues = []
    node_all_locales = []
    node_blobs = {}
    reported = defaultdict(list)
    physical = defaultdict(set)
    for record_key, entry in sorted(complete.items()):
        texts = entry["texts"]
        called_ids = {language: _called_from_key(entry, language) for language in LANGUAGES}
        path, rest = record_key.split(".dat/", 1)
        path += ".dat"
        function = rest.split("/", 1)[0]
        source_called = called_ids["zh-Hans"]
        source = texts["zh-Hans"]
        blob = blobs["zh-Hans"][path]
        manifest = _manifest_case(source_model, blob, function, source_called)
        node_blobs[manifest["sha256"]] = base64.b64encode(blob).decode()
        speaker_id = entry.get("speaker_ids", {}).get("zh-Hans")
        node_dialogues.append(
            {
                "key": record_key,
                "record_key": record_key,
                "function": function,
                "called": source_called,
                "source": source,
                "speaker": speaker_names.get(speaker_id, ""),
                "targets": {target: texts[target] for target in models},
                **manifest,
            }
        )
        node_all_locales.append(
            {"record_key": record_key, "called_ids": called_ids, "texts": texts}
        )
        for language, called in called_ids.items():
            physical[language, path, function, called].add(record_key)
        for label, raw in REPORTED_RAW.items():
            if raw in source:
                reported[label].append(
                    {
                        "path": path,
                        "function": function,
                        "called_ids": called_ids,
                        "raw_source": source,
                        "ja": texts["ja"],
                        "en": texts["en"],
                    }
                )
    if set(reported) != set(REPORTED_RAW):
        raise AssertionError(
            f"reported lines not in quest scope: {set(REPORTED_RAW) - set(reported)}"
        )
    merged = {str(key): values for key, values in physical.items() if len(values) != 1}
    if merged:
        raise AssertionError(f"stable key merges/splits physical calls: {merged}")

    table_cases = _read_quest_table(args.game_dir, indexed)
    node = subprocess.run(
        ["node", "-e", RUNNER],
        cwd=ROOT,
        input=json.dumps(
            {
                "models": models,
                "blobs": node_blobs,
                "dialogues": node_dialogues,
                "all_locale_dialogues": node_all_locales,
                "table": [
                    {
                        "key": case["key"],
                        "source": case["texts"]["zh-Hans"],
                        "targets": {target: case["texts"][target] for target in models},
                    }
                    for case in table_cases
                ],
                "languages": LANGUAGES,
            },
            ensure_ascii=False,
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if node.returncode:
        raise AssertionError(node.stderr)
    runtime = json.loads(node.stdout)
    history_unresolved = _history_unresolved_audit(entries, loaded_models, runtime, names_by_locale)
    result = {
        "version": 1,
        "scope": {
            "quest_id": QUEST_ID,
            "script_paths": QUEST_SCRIPT_PATHS,
            "functions": functions,
            "quest_table": QUEST_TABLE_PATH,
            "quest_table_group": QUEST_TABLE_GROUP,
        },
        "native_default_speaker": _native_default_speaker_evidence(args.game_dir),
        "script_denominator": denominator,
        "script_records_per_locale": expected_records,
        "quest_end_calls": quest_end,
        "quest_table": {
            "title_fields": sum("/QuestTitle/" in case["key"] for case in table_cases),
            "text_fields": sum("/QuestText/" in case["key"] for case in table_cases),
            "records": table_cases,
        },
        "reported_lines": dict(reported),
        "models": models,
        "runtime": runtime,
        "history_unresolved_audit": history_unresolved,
        "unsupported": {
            "script_ja": 0,
            "script_en": 0,
            "quest_table_ja": 0,
            "quest_table_en": 0,
            "function_signature_mismatches": signature_mismatches,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), **runtime}, ensure_ascii=False))


if __name__ == "__main__":
    main()
