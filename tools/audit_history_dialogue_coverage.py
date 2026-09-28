"""Audit every catalogued dialogue call through ID and old-history resolvers.

This is an offline PAC/catalog audit.  It uses original assembled-dialogue
records as the denominator and executes the shipped JavaScript resolver in
Node; it never starts or attaches to the game.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator, complete_pair, display_text
from sora_bilingual.localization.native_catalog import fingerprint
from sora_bilingual.localization.runtime_identity import compile_script_identities
from sora_bilingual.localization.speaker_context import compile_history_contexts, read_speaker_names


EXPRESSION_PREFIX = re.compile(r"^(?:<#[^<>]*>)+")


RUNNER = r"""
const fs=require('fs');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const data=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const runtime=new RuntimeText({history_contexts:data.history});
const identities=new ScriptIdentities(data.identities);
const visible=s=>String(s||'').replace(/<[^<>]*>/g,'').replace(/\s/g,'');
function annotationExpected(primary,secondary){
 // This is deliberately independent of RuntimeText.needsAnnotation.  A ruby
 // close tag carries its reading (</Rreading>), which is visible secondary
 // content and must not be discarded with ordinary control markup.
 const reading=s=>String(s||'')
   .replace(/<R>[\s\S]*?<\/R([^<>]*)>/g,'$1')
   .replace(/<[^<>]*>/g,'')
   .replace(/[\uff01-\uff5e]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0))
   .trim();
 const left=reading(primary), right=reading(secondary);
 return Boolean(left && right && (left!==right || /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(left)));
}
function annotationPayload(plan,primary){
 // A source may already contain native ruby.  It belongs to the original
 // render lane, rather than an annotation emitted for our secondary text.
 const native=[...String(primary).matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]);
 const added=[];
 for(const match of plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)) {
  const at=native.indexOf(match[1]);
  if(at>=0)native.splice(at,1); else if(match[1]!=='_')added.push(match[1]);
 }
 return plan.layers.map(v=>v.text).join('')+added.join('');
}
function rendered(tr,source,pair){
 try {
  const plan=tr.render(source,'annotation');
  const payload=annotationPayload(plan,pair[0]);
  const expected=annotationExpected(...pair);
  // A multi-line ruby plan deliberately omits lines whose primary and
  // secondary text are already identical. Pair equality is checked by the
  // caller, so final-render validation must verify the emitted plan rather
  // than require every secondary character in its annotation payload.
  if(RuntimeText.needsAnnotation(...pair)!==expected)return false;
  if(!expected)
   return plan.kind==='plain'&&visible(payload)==='';
  return plan.kind!=='plain'&&visible(payload)!=='';
 } catch (_) { return false; }
}
const history=data.historyCases.map(c=>{
 const context=runtime.historyContext(c.name,c.source,c.kind);
 if(!context)return [c.id,'missing',false,null];
 const pair=[context.tr.translate(c.source,'primary'),context.tr.translate(c.source,'secondary')];
 return [c.id,context.fallback?'fallback':'exact',rendered(context.tr,c.source,pair),pair];
});
const ids=data.idCases.map(c=>{
 const identity={source:c.source,recordKey:c.key};
 const local=identities.recordLookup(identity,c.key,c.source);
 if(!local)return [c.id,'missing',false,null];
 const tr=new RuntimeText(local.model),pair=[tr.translate(c.source,'primary'),tr.translate(c.source,'secondary')];
 return [c.id,'resolved',rendered(tr,c.source,pair),pair];
});
process.stdout.write(JSON.stringify({history,ids}));
"""


def _base(entry: dict) -> str:
    return entry["key"].split("/alignment/", 1)[0]


def _dialogue_groups(entries: list[dict]) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        key = _base(entry)
        if entry.get("display_role") == "dialogue" and key.endswith("/assembled_dialogue"):
            rows[key].append(entry)
    return rows


def _all_pairs(rows: list[dict], primary: str, secondary: str) -> set[tuple[str, str]]:
    return {
        pair
        for entry in rows
        if (pair := complete_pair(entry.get("texts", {}), primary, secondary)) is not None
    }


def _source_values(rows: list[dict], locale: str) -> set[str]:
    return {
        display_text(entry["texts"][locale])
        for entry in rows
        if entry.get("texts", {}).get(locale, "").strip()
    }


def _speaker(entry: dict, locale: str, names: dict[str, dict[int, str]]) -> str:
    actor = entry.get("speaker_ids", {}).get(locale)
    return names.get(locale, {}).get(actor, "")


def _history_candidates(
    entries: list[dict], names: dict[str, dict[int, str]], primary: str, secondary: str
):
    """Return raw old-log lookup candidates, keeping physical calls separate."""
    candidates: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
    calls: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for key, rows in _dialogue_groups(entries).items():
        for entry in rows:
            raw_pair = complete_pair(entry.get("texts", {}), primary, secondary)
            if raw_pair is None:
                continue
            # compile_history_contexts keys and pair values use display_text().
            pair = tuple(display_text(value) for value in raw_pair)
            for locale, value in entry["texts"].items():
                body = display_text(value)
                if not body.strip():
                    continue
                name = _speaker(entry, locale, names)
                candidates[("body", name, body)].add(pair)
                candidates[("body", "", body)].add(pair)
                calls[("body", name, body)].add(key)
                calls[("body", "", body)].add(key)
    # t_name is an original table denominator for normal speaker labels.
    for locale, values in names.items():
        for actor, source in values.items():
            pair = tuple(names.get(side, {}).get(actor) for side in (primary, secondary))
            if all(pair):
                candidates[("name", "", source)].add(pair)
                calls[("name", "", source)].add(f"table/t_name.tbl/{locale}/{actor}")
    # Generic setter labels are raw script resources, not t_name rows.
    for entry in entries:
        if entry.get("display_role") != "speaker" or not _base(entry).endswith("/arg/1"):
            continue
        raw_pair = complete_pair(entry.get("texts", {}), primary, secondary)
        if raw_pair is None:
            continue
        pair = tuple(display_text(value) for value in raw_pair)
        for source in entry["texts"].values():
            if source.strip():
                candidates[("name", "", source)].add(pair)
                calls[("name", "", source)].add(_base(entry))
    return candidates, calls


def _run_js(
    history: dict, identities: dict, history_cases: list[dict], id_cases: list[dict]
) -> dict:
    with TemporaryDirectory(prefix="sora-history-coverage-") as temporary:
        payload = Path(temporary) / "input.json"
        payload.write_text(
            json.dumps(
                {
                    "history": history,
                    "identities": identities,
                    "historyCases": history_cases,
                    "idCases": id_cases,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["node", "-e", RUNNER, str(payload)],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
    return json.loads(completed.stdout)


def _model(entries: list[dict], game: Path, names: dict[str, dict[int, str]], target: str) -> dict:
    primary = "zh-Hans"
    translator = MenuTranslator(entries, primary, target, primary)
    identities = compile_script_identities(
        game, entries, primary, target, primary, resolved_pairs=translator.pairs
    )
    return {
        "history": compile_history_contexts(entries, names, primary, target),
        "identities": identities,
    }


def _audit_target(
    entries: list[dict],
    game: Path,
    names: dict[str, dict[int, str]],
    target: str,
    compiled: dict | None = None,
) -> dict:
    primary = "zh-Hans"
    started = perf_counter()
    if compiled is None:
        print(json.dumps({"stage": "compile", "target": target}), flush=True)
        compiled = _model(entries, game, names, target)
    else:
        print(json.dumps({"stage": "checkpoint_loaded", "target": target}), flush=True)
    print(json.dumps({"stage": "replay", "target": target}), flush=True)
    groups = _dialogue_groups(entries)
    id_cases, id_rows, id_counts = [], [], Counter()
    for key, rows in groups.items():
        pairs = _all_pairs(rows, primary, target)
        sources = _source_values(rows, primary)
        base = {"key": key, "pairs": sorted(pairs), "sources": sorted(sources)}
        if not pairs:
            id_counts["missing_resource_pair"] += 1
            id_rows.append({**base, "reason": "missing_resource_pair"})
            continue
        if len(pairs) != 1:
            id_counts["resource_pair_conflict"] += 1
            id_rows.append({**base, "reason": "resource_pair_conflict"})
            continue
        if len(sources) != 1:
            id_counts["source_text_conflict"] += 1
            id_rows.append({**base, "reason": "source_text_conflict"})
            continue
        if key not in compiled["identities"].get("record_pairs", {}):
            id_counts["id_compile_missing"] += 1
            id_rows.append({**base, "reason": "id_compile_missing"})
            continue
        identifier = len(id_cases)
        id_cases.append({"id": identifier, "key": key, "source": next(iter(sources))})
        id_rows.append({**base, "case": identifier})
    history_candidates, history_calls = _history_candidates(entries, names, primary, target)
    history_cases = [
        {"id": index, "kind": kind, "name": name, "source": source}
        for index, (kind, name, source) in enumerate(sorted(history_candidates))
    ]
    replay = _run_js(compiled["history"], compiled["identities"], history_cases, id_cases)
    id_results = {
        index: (status, rendered, tuple(pair) if pair else None)
        for index, status, rendered, pair in replay["ids"]
    }
    for row in id_rows:
        if "case" not in row:
            continue
        status, rendered, pair = id_results[row["case"]]
        # recordLookup stores the expression body and re-applies only the source
        # prefix.  ID cases intentionally supply the display_text source body.
        expected = tuple(EXPRESSION_PREFIX.sub("", value) for value in row["pairs"][0])
        if status != "resolved":
            id_counts["id_runtime_missing"] += 1
            row["reason"] = "id_runtime_missing"
        elif pair != expected:
            id_counts["id_pair_mismatch"] += 1
            row["reason"] = "id_pair_mismatch"
            row["actual"] = pair
        elif not rendered:
            id_counts["id_final_render_failed"] += 1
            row["reason"] = "id_final_render_failed"
        else:
            id_counts["id_final_render_passed"] += 1
            row["reason"] = "id_final_render_passed"
    history_results = {
        index: (status, rendered, tuple(pair) if pair else None)
        for index, status, rendered, pair in replay["history"]
    }
    history_counts, history_rows = Counter(), []
    history_by_kind: dict[str, Counter] = defaultdict(Counter)
    for case in history_cases:
        key = (case["kind"], case["name"], case["source"])
        expected = history_candidates[key]
        status, rendered, pair = history_results[case["id"]]
        calls = sorted(history_calls[key])
        weight = len(calls)
        base = {
            "kind": key[0],
            "speaker": key[1],
            "source": key[2],
            "calls": calls,
            "official_pairs": sorted(expected),
        }
        if status == "missing":
            reason = "history_conflict_unresolved"
        elif pair not in expected:
            reason = f"history_{status}_nonofficial"
        elif not rendered:
            reason = "history_final_render_failed"
        elif status == "fallback":
            reason = "history_fallback_selected"
        else:
            reason = "history_exact_render_passed"
        history_counts[reason] += weight
        history_by_kind[key[0]][reason] += weight
        if reason != "history_exact_render_passed":
            history_rows.append({**base, "reason": reason, "actual": pair})
    return {
        "target": target,
        "compile_seconds": round(perf_counter() - started, 3),
        "raw_dialogue_call_denominator": len(groups),
        "id_counts": dict(id_counts),
        "id_rejections": [row for row in id_rows if row["reason"] != "id_final_render_passed"],
        "history_raw_lookup_denominator": sum(len(value) for value in history_calls.values()),
        "history_counts": dict(history_counts),
        "history_by_kind": {kind: dict(counts) for kind, counts in history_by_kind.items()},
        "history_rejections": history_rows,
        "identity_stats": compiled["identities"].get("stats", {}),
        "history_context_sizes": {
            key: len(value) for key, value in compiled["history"].items() if isinstance(value, dict)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "generated/catalog.json",
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "generated/history-dialogue-coverage.json"
    )
    parser.add_argument("--ja-model", type=Path)
    parser.add_argument("--en-model", type=Path)
    args = parser.parse_args()
    entries = json.loads(args.catalog.read_text(encoding="utf-8"))["entries"]
    print(json.dumps({"stage": "catalog_loaded", "entries": len(entries)}), flush=True)
    names = {locale: read_speaker_names(args.game_dir, locale) for locale in LANGUAGES}
    print(json.dumps({"stage": "names_loaded", "locales": len(names)}), flush=True)
    checkpoints = {}
    for target, path in (("ja", args.ja_model), ("en", args.en_model)):
        if path:
            model = json.loads(path.read_text(encoding="utf-8"))
            checkpoints[target] = {
                "history": model["history_contexts"],
                "identities": model["script_identities"],
            }
    report = {
        "game_started": False,
        "game_attached": False,
        "catalog": str(args.catalog),
        "catalog_entries": len(entries),
        "fingerprint": fingerprint(args.game_dir),
        "targets": [
            _audit_target(entries, args.game_dir, names, target, checkpoints.get(target))
            for target in ("ja", "en")
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            [
                {
                    "target": target["target"],
                    "raw_dialogue_call_denominator": target["raw_dialogue_call_denominator"],
                    "id_counts": target["id_counts"],
                    "history_counts": target["history_counts"],
                }
                for target in report["targets"]
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
