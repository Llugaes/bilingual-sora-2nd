"""Replay reported dynamic notifications through complete offline catalog models.

This check reads game PAC/table resources and runs the production JavaScript
resolver.  It never attaches to, starts, or changes the game.  Passing it is
offline catalog/render evidence only; it is not live-game validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES, archive_names
from sora_bilingual.localization.dynamic_producers import (
    _ITEM_CALLEES,
    _RECIPE_ITEM_CLASSES,
    _RECIPE_MAX_ID,
    _RECIPE_MIN_ID,
    _SYSTEM_PATH,
    _item_call_parts,
    _panel_template,
    _read_item_rows,
    _read_scripts,
)
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.localization.resources import (
    FpacArchive,
    _logical_script_entries,
    assembled_dialogue,
)
from sora_bilingual.localization.runtime_identity import script_signature


SOURCE = "zh-Hans"
TARGETS = ("ja", "en")
ITEM_SOURCE = "拿到了<C0><I5></C><C5>竹竿</C>。"
RECIPE_SOURCE = "记住了<C0><I10></C><C5>丰熟咖喱饭</C>的食谱！"
QUEST_SOURCE = "<C1>达成了委托【<C2>艾尔贝周游道的通缉魔兽<C1>】！"

RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const input=JSON.parse(fs.readFileSync(0,'utf8')), model=JSON.parse(fs.readFileSync(input.model,'utf8'));
const runtime=new RuntimeText(model), visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
const rows=input.cases.map(c=>{
 const primary=runtime.translate(c.source,'primary'), secondary=runtime.translate(c.source,'secondary'), plan=runtime.render(c.source,'annotation');
 const payload=plan.layers.map(layer=>layer.text).join('')+ [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 const wholeRuby=plan.kind==='ruby'&&plan.layers.length===0&&plan.text===`<R>${c.primary}</R${c.secondary}>`;
 const pass=primary===c.primary&&secondary===c.secondary&&plan.kind!=='plain'&&(plan.layers.length===1||wholeRuby)&&visible(payload)===visible(c.secondary);
 return {name:c.name,pass,primary,secondary,kind:plan.kind,layers:plan.layers.length,...(pass?{}:{source:c.source,expected:[c.primary,c.secondary],plan})};
});
process.stdout.write(JSON.stringify(rows));
"""

IDENTITY_RUNNER = r"""
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities,LogIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
const identities=new ScriptIdentities(input.scriptIdentities), logs=new LogIdentities();
const rows=input.cases.map((c,index)=>{
 const raw=Uint8Array.from(c.blob), identity=identities.capture(c.signature,n=>raw.slice(0,n),c.helper,c.argumentsToken,{pc:c.pc,group:5,command:8},c.source);
 if(!identity)return {recordKey:c.recordKey,icon:c.icon,pass:false,stage:'capture'};
 logs.commit(index,'id220/'+index,identity);
 const committed=logs.lookup(index,'id220/'+index), selected=identities.lookup(committed,c.source);
 if(!selected)return {recordKey:c.recordKey,icon:c.icon,pass:false,stage:'lookup'};
 const runtime=new RuntimeText(selected.model), plan=runtime.render(c.source,'annotation');
 const payload=plan.layers.map(layer=>layer.text).join('')+ [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 const wholeRuby=plan.kind==='ruby'&&plan.layers.length===0&&plan.text===`<R>${c.primary}</R${c.secondary}>`;
 return {recordKey:c.recordKey,icon:c.icon,pass:runtime.translate(c.source,'primary')===c.primary&&runtime.translate(c.source,'secondary')===c.secondary&&plan.kind!=='plain'&&(plan.layers.length===1||wholeRuby)&&visible(payload)===visible(c.secondary),stage:'render',kind:plan.kind,layers:plan.layers.length};
});
process.stdout.write(JSON.stringify(rows));
"""

ID220_RECORDS = (
    "dynamic/script/scena/mp3000_ev.dat/EV_02_28_00/called/488/item/220",
    "dynamic/script/scena/mp3000_ev.dat/EV_02_28_00_END/called/0/item/220",
)
ID220_SOURCE = "拿到了<C0><I5></C><C5>木门钥匙</C>。"


def _dynamic_case(entries: list[dict], family: str, item_id: int, icon: int, source: str):
    matches = [
        entry
        for entry in entries
        if entry.get("producer_origin", {}).get("family") == family
        and entry.get("producer_origin", {}).get("item_id") == item_id
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{family}/{item_id}: expected one producer record, got {len(matches)}"
        )
    entry = matches[0]
    if not entry.get("dynamic_producer", {}).get("dynamic_icon"):
        raise AssertionError(f"{family}/{item_id}: runtime icon slot is absent")
    texts = {locale: entry["texts"][locale].replace("%d", str(icon)) for locale in LANGUAGES}
    if texts[SOURCE] != source:
        raise AssertionError(f"{family}/{item_id}: producer source differs from captured input")
    return texts


def _quest_case(entries: list[dict]):
    matches = [entry for entry in entries if entry.get("texts", {}).get(SOURCE) == QUEST_SOURCE]
    complete = [
        entry for entry in matches if all(entry["texts"].get(locale) for locale in LANGUAGES)
    ]
    pairs = {tuple(entry["texts"][locale] for locale in LANGUAGES) for entry in complete}
    if len(pairs) != 1:
        raise AssertionError(f"quest completion source has {len(pairs)} complete catalog pairs")
    return dict(zip(LANGUAGES, pairs.pop(), strict=True)), len(matches), len(complete)


def _raw_quest_denominator(game: Path):
    audit = {"diagnostics": [], "counters": Counter()}
    scripts = _read_scripts(game, audit)
    counts = {}
    for locale in LANGUAGES:
        function = scripts[locale]["script/scena/system.dat"].functions.get("OnQuestEnd")
        if function is None:
            raise AssertionError(f"OnQuestEnd missing for {locale}")
        counts[locale] = sum(assembled_dialogue(call) is not None for call in function.called)
    if len(set(counts.values())) != 1:
        raise AssertionError(f"OnQuestEnd locale denominator differs: {counts}")
    return {"per_locale": counts, "diagnostics": audit["diagnostics"]}


def _runtime_operations(call: object) -> list[int]:
    """Return command-8 operator codes immediately followed by a VM value."""
    args = getattr(call, "args", ())
    if getattr(call, "kind", None) != 3 or len(args) < 6:
        return []
    if args[:4] != (("int", 5), ("int", 8), ("int", 65535), ("int", 16)):
        return []
    return [
        int(value)
        for (kind, value), following in zip(args[4:], args[5:])
        if kind == "int" and isinstance(value, int) and following == ("var", None)
    ]


def _raw_producer_denominator(game: Path):
    """Classify every raw notification-shaped operation without inferring text."""
    audit = {"diagnostics": [], "counters": Counter()}
    scripts = _read_scripts(game, audit)
    items = _read_item_rows(game, audit)
    known = {
        (_SYSTEM_PATH, "OnQuestAddBP", 3): ("on_quest_add_bp", frozenset((18,))),
        (_SYSTEM_PATH, "RestShopProcess", 3): ("rest_shop_process", frozenset((18, 23))),
        (_SYSTEM_PATH, "UnLockRecipe", 2): ("unlock_recipe", frozenset((17,))),
    }
    per_locale = {}
    unknown: list[dict[str, object]] = []
    for language in LANGUAGES:
        rows = Counter()
        recipe_ids = []
        for path, script in scripts.get(language, {}).items():
            for function_name, function in script.functions.items():
                for called, call in enumerate(function.called):
                    location = (path, function_name, called)
                    if getattr(call, "target", None) in _ITEM_CALLEES:
                        rows["item_message_raw_calls"] += 1
                        candidate = _item_call_parts(call)
                        if candidate is None:
                            rows["item_message_rejected_shape"] += 1
                            unknown.append(
                                {
                                    "reason": "item_message_rejected_shape",
                                    "language": language,
                                    "path": path,
                                    "function": function_name,
                                    "called": called,
                                }
                            )
                        elif candidate[0] in items.get(language, {}):
                            rows["item_message_static_id_instances"] += 1
                        else:
                            rows["item_message_unknown_item_id"] += 1
                            unknown.append(
                                {
                                    "reason": "item_message_unknown_item_id",
                                    "language": language,
                                    "path": path,
                                    "function": function_name,
                                    "called": called,
                                    "item_id": candidate[0],
                                }
                            )
                    operations = _runtime_operations(call)
                    if not operations:
                        continue
                    rows["command8_runtime_operations"] += len(operations)
                    expected = known.get(location)
                    if expected is not None:
                        family, allowed = expected
                        decoded = _panel_template(call, allowed_opcodes=allowed)
                        if decoded is None:
                            rows[f"{family}_rejected_format"] += 1
                            unknown.append(
                                {
                                    "reason": "known_family_rejected_format",
                                    "family": family,
                                    "language": language,
                                    "path": path,
                                    "function": function_name,
                                    "called": called,
                                    "opcodes": operations,
                                }
                            )
                        else:
                            rows[f"{family}_template"] += 1
                            if family == "unlock_recipe":
                                recipe_ids = sorted(
                                    item_id
                                    for item_id, (_name, item_class) in items.get(
                                        language, {}
                                    ).items()
                                    if _RECIPE_MIN_ID <= item_id <= _RECIPE_MAX_ID
                                    and item_class in _RECIPE_ITEM_CLASSES
                                )
                                rows["unlock_recipe_static_id_instances"] = len(recipe_ids)
                        continue
                    rows["unknown_command8_runtime_operation"] += len(operations)
                    unknown.append(
                        {
                            "reason": "unknown_command8_runtime_operation",
                            "language": language,
                            "path": path,
                            "function": function_name,
                            "called": called,
                            "opcodes": operations,
                        }
                    )
        per_locale[language] = dict(sorted(rows.items()))
        if recipe_ids:
            per_locale[language]["unlock_recipe_static_id_min"] = recipe_ids[0]
            per_locale[language]["unlock_recipe_static_id_max"] = recipe_ids[-1]
    reasons = Counter(row["reason"] for row in unknown)
    return {
        "per_locale": per_locale,
        "unknown_or_rejected": unknown,
        "unknown_or_rejected_by_reason": dict(sorted(reasons.items())),
        "resource_read_diagnostics": audit["diagnostics"],
    }


def _number_text(entry: dict, locale: str, value: int) -> str:
    styles = entry["dynamic_producer"]["numbers"][locale]
    rendered = str(value)
    for style in styles:
        if style == "fullwidth":
            rendered = rendered.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
        elif style != "ascii":
            raise AssertionError(f"unknown numeric style: {style}")
    return entry["texts"][locale].replace("%d", rendered)


def _all_producer_cases(entries: list[dict], secondary: str):
    """Expand every admitted producer record into complete rendered sources.

    Values are formatting probes, not invented game events. Item/recipe IDs
    are fixed raw arguments; their icon number remains an opaque native slot.
    """
    cases, excluded = [], []
    values = {
        "on_quest_add_bp": (-2147483648, -1, 0, 2, 200, 2147483647),
        "rest_shop_process": (-2147483648, -1, 0, 2, 200, 2147483647),
        "unlock_recipe": (5, 10, 110, 2147483647),
        "item_add_message": (5, 10, 110, 2147483647),
    }
    rows = [entry for entry in entries if entry.get("dynamic_producer")]
    for entry in rows:
        family = entry["dynamic_producer"].get("family")
        if family not in values:
            excluded.append(
                {"key": entry["key"], "reason": "unknown_producer_family", "family": family}
            )
            continue
        needed = (SOURCE, secondary)
        if any(not entry["texts"].get(language) for language in needed):
            excluded.append({"key": entry["key"], "reason": "missing_selected_locale"})
            continue
        for value in values[family]:
            cases.append(
                {
                    "name": f"{entry['key']}/value/{value}",
                    "source": _number_text(entry, SOURCE, value),
                    "primary": _number_text(entry, SOURCE, value),
                    "secondary": _number_text(entry, secondary, value),
                    "family": family,
                    "value": value,
                    "singleLane": True,
                }
            )
    return cases, excluded, Counter(entry["dynamic_producer"]["family"] for entry in rows)


def _identity_cases(entries: list[dict], model_path: Path, secondary: str, game: Path):
    """Exercise production capture, history commit and lookup for ID 220."""
    by_key = {entry["key"]: entry for entry in entries}
    path = "script/scena/mp3000_ev.dat"
    with FpacArchive(game / "pac" / "steam" / archive_names("script")[SOURCE]) as archive:
        blob = archive.read(_logical_script_entries(archive)[path])
    digest = hashlib.sha256(blob).hexdigest()
    signature = script_signature(blob)
    helper = "ITEM_ADD_MESSAGE2_EV"
    # Use the persisted production model wholesale.  The identity test must
    # exercise its real manifest and its installed dynamic-producer index,
    # rather than a hand-built size/SHA/function candidate.
    script_identities = json.loads(model_path.read_text(encoding="utf-8")).get("script_identities")
    if not isinstance(script_identities, dict):
        raise AssertionError("final model has no script identity model")
    identities = script_identities.get("dynamic_producers")
    if not isinstance(identities, dict):
        raise AssertionError("final model has no dynamic producer identities")
    indexed = identities.get("scripts", {}).get(digest, {}).get(helper, {})
    manifest = script_identities.get("manifest", {}).get(signature, [])
    if not any(
        row.get("size") == len(blob)
        and row.get("sha256") == digest
        and helper in row.get("functions", [])
        for row in manifest
        if isinstance(row, dict)
    ):
        raise AssertionError("final model manifest does not admit the actual mp3000 blob")
    cases = []
    for key in ID220_RECORDS:
        entry = by_key.get(key)
        if entry is None:
            raise AssertionError(f"ID 220 catalog row missing: {key}")
        primary = entry["texts"][SOURCE]
        expected = entry["texts"][secondary]
        row = next((row for row in indexed.values() if row["recordKey"] == key), None)
        if row is None:
            raise AssertionError(f"ID 220 identity row missing: {key}")
        for icon in (5, 10, 110, 2147483647):
            source = primary.replace("%d", str(icon))
            if icon == 5 and source != ID220_SOURCE:
                raise AssertionError(f"ID 220 source differs: {key}")
            cases.append(
                {
                    "recordKey": key,
                    "icon": icon,
                    "blob": list(blob),
                    "signature": signature,
                    "helper": helper,
                    "argumentsToken": next(
                        token for token, value in indexed.items() if value is row
                    ),
                    "pc": row["pc"],
                    "source": source,
                    "primary": source,
                    "secondary": expected.replace("%d", str(icon)),
                }
            )
    completed = subprocess.run(
        ["node", "-e", IDENTITY_RUNNER],
        cwd=ROOT,
        input=json.dumps(
            {"scriptIdentities": script_identities, "cases": cases}, ensure_ascii=False
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    rows = json.loads(completed.stdout)
    return rows, all(row["pass"] for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--targets", choices=LANGUAGES, nargs="+", default=TARGETS)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/notification-omissions.json"
    )
    parser.add_argument(
        "--existing-catalog-dir",
        type=Path,
        help="reuse a prior load_entries output directory without extracting the PAC catalog again",
    )
    parser.add_argument(
        "--keep-models",
        type=Path,
        help="directory for reusable final models and diagnostic-134-model-{ja,en}.json copies",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        help="reuse final diagnostic-134-model-{ja,en}.json files instead of compiling models",
    )
    parser.add_argument(
        "--model-path",
        action="append",
        default=[],
        metavar="LANG=PATH",
        help="reuse one final model path per target, for example ja=generated/runtime-....json",
    )
    parser.add_argument(
        "--all-producers",
        action="store_true",
        help="render every admitted producer instance and classify all raw notification operations",
    )
    args = parser.parse_args()
    if SOURCE in args.targets:
        raise ValueError("targets must be secondary languages, not zh-Hans")
    explicit_models = {}
    for value in args.model_path:
        language, separator, path = value.partition("=")
        if (
            not separator
            or language not in args.targets
            or language in explicit_models
            or not Path(path).is_file()
        ):
            raise ValueError(f"invalid --model-path: {value}")
        explicit_models[language] = Path(path)

    temporary = None
    if args.existing_catalog_dir:
        work = args.existing_catalog_dir
        if not (work / "catalog.json").is_file():
            raise FileNotFoundError(f"catalog.json is absent: {work}")
    else:
        temporary = tempfile.TemporaryDirectory(prefix="sora-notification-check-")
        work = Path(temporary.name)
    try:
        if args.existing_catalog_dir:
            entries = json.loads((work / "catalog.json").read_text(encoding="utf-8"))["entries"]
            signature = None
        else:
            entries, signature = load_entries(args.game_dir, work)
        item = _dynamic_case(entries, "item_add_message", 483, 5, ITEM_SOURCE)
        recipe = _dynamic_case(entries, "unlock_recipe", 2130, 10, RECIPE_SOURCE)
        quest, quest_matches, quest_complete = _quest_case(entries)
        raw_quest = _raw_quest_denominator(args.game_dir)
        raw_producers = _raw_producer_denominator(args.game_dir) if args.all_producers else None
        producers = Counter(
            entry.get("producer_origin", {}).get("family")
            for entry in entries
            if entry.get("producer_origin")
        )
        report = {
            "game_attached": False,
            "validation": "offline full-catalog JavaScript render; live-game validation remains required",
            "source": SOURCE,
            "targets": [],
            "raw_denominator": {
                "dynamic_entries_by_family": dict(sorted(producers.items())),
                "on_quest_end": raw_quest,
                "quest_source_records": {"all": quest_matches, "complete": quest_complete},
                "item_dynamic_identity_by_target": {},
            },
            "all_passed": True,
        }
        if raw_producers is not None:
            report["raw_denominator"]["producer_operations"] = raw_producers
            report["raw_classification_complete"] = not raw_producers["unknown_or_rejected"]
            report["all_passed"] &= report["raw_classification_complete"]
        model_output = args.keep_models or work
        if args.keep_models:
            args.keep_models.mkdir(parents=True, exist_ok=True)
        for secondary in args.targets:
            config = {
                "game_language": SOURCE,
                "primary": SOURCE,
                "secondary": secondary,
                "scope": "all",
            }
            if secondary in explicit_models:
                model = explicit_models[secondary]
            elif args.model_dir:
                model = args.model_dir / f"diagnostic-134-model-{secondary}.json"
                if not model.is_file():
                    raise FileNotFoundError(f"final diagnostic model is absent: {model}")
            else:
                load_model(entries, signature, config, output=model_output, game=args.game_dir)
                model = model_path(signature, config, output=model_output)
                if args.keep_models:
                    shutil.copy2(model, args.keep_models / f"diagnostic-134-model-{secondary}.json")
            cases = [
                {
                    "name": "item_add/483/icon-5",
                    "source": ITEM_SOURCE,
                    "primary": item[SOURCE],
                    "secondary": item[secondary],
                },
                {
                    "name": "unlock_recipe/2130/icon-10",
                    "source": RECIPE_SOURCE,
                    "primary": recipe[SOURCE],
                    "secondary": recipe[secondary],
                },
                {
                    "name": "quest_complete/on-quest-end",
                    "source": QUEST_SOURCE,
                    "primary": quest[SOURCE],
                    "secondary": quest[secondary],
                },
            ]
            excluded = []
            producer_counts = Counter()
            if args.all_producers:
                cases, excluded, producer_counts = _all_producer_cases(entries, secondary)
                cases.extend(
                    [
                        {
                            "name": "item_add/483/icon-5",
                            "source": ITEM_SOURCE,
                            "primary": item[SOURCE],
                            "secondary": item[secondary],
                        },
                        {
                            "name": "unlock_recipe/2130/icon-10",
                            "source": RECIPE_SOURCE,
                            "primary": recipe[SOURCE],
                            "secondary": recipe[secondary],
                        },
                        {
                            "name": "quest_complete/on-quest-end",
                            "source": QUEST_SOURCE,
                            "primary": quest[SOURCE],
                            "secondary": quest[secondary],
                        },
                    ]
                )
            completed = subprocess.run(
                ["node", "-e", RUNNER],
                cwd=ROOT,
                input=json.dumps(
                    {"model": str(model), "cases": cases},
                    ensure_ascii=False,
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
            )
            rows = json.loads(completed.stdout)
            passed = all(row["pass"] for row in rows)
            global_id220_cases = []
            for key in ID220_RECORDS:
                entry = next(entry for entry in entries if entry["key"] == key)
                global_id220_cases.append(
                    {
                        "name": key,
                        "source": ID220_SOURCE,
                        "primary": entry["texts"][SOURCE].replace("%d", "5"),
                        "secondary": entry["texts"][secondary].replace("%d", "5"),
                    }
                )
            global_completed = subprocess.run(
                ["node", "-e", RUNNER],
                cwd=ROOT,
                input=json.dumps(
                    {"model": str(model), "cases": global_id220_cases}, ensure_ascii=False
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
            )
            global_id220 = json.loads(global_completed.stdout)
            identity_rows, identity_passed = _identity_cases(
                entries, model, secondary, args.game_dir
            )
            persisted_model = json.loads(model.read_text(encoding="utf-8"))
            identity_stats = persisted_model["script_identities"]["dynamic_producers"]["stats"]
            report["raw_denominator"]["item_dynamic_identity_by_target"][secondary] = identity_stats
            model_rows = len(persisted_model.get("producer_numeric", []))
            expected_rows = sum(producer_counts.values()) if args.all_producers else None
            if expected_rows is not None and model_rows != expected_rows:
                passed = False
            report["targets"].append(
                {
                    "secondary": secondary,
                    "passed": passed,
                    "rows": rows,
                    "id220_global_lookup": global_id220,
                    "id220_identity_lookup": identity_rows,
                    "id220_identity_passed": identity_passed,
                    "id220_identity_stats": identity_stats,
                    "excluded": excluded,
                    "producer_catalog_entries": dict(sorted(producer_counts.items())),
                    "producer_model_rules": model_rows,
                    "producer_model_rule_count_matches_catalog": (
                        None if expected_rows is None else model_rows == expected_rows
                    ),
                }
            )
            report["all_passed"] &= passed
    finally:
        if temporary is not None:
            temporary.cleanup()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"output": str(args.output), "all_passed": report["all_passed"]}, ensure_ascii=False
        )
    )
    if not report["all_passed"]:
        raise AssertionError(f"notification omissions remain: {args.output}")


if __name__ == "__main__":
    main()
