"""Replay reported omissions through full catalog models and production JS.

Requires locally installed game resources. No game process is started or
attached; configuration is read but never changed. Reduced fixtures cannot
replace this check: cross-domain collisions only appear in the full catalog.
"""

import argparse
import gc
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.config.native_config import read_config
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path
from sora_bilingual.localization.menu_text import ITEM_HELP_PERCENT_RECOVERY, display_text
import test_itemhelp_composition as keys

NOTE = "script/scena/mp3010_01.dat/LP_Capel/called/131/assembled_dialogue"
KEY_HINT = "script/scena/mp3010_01.dat/LP_Capel/called/133/assembled_dialogue"
WATER_DESCRIPTION = "table/t_skill.tbl/sha256:8155e2b8257dd080eaef7b50a6a059e1ccd842882cbbabf06cf9f3eea8e67bd9/description"
RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {ScriptIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(data.model,'utf8')),runtime=new RuntimeText(model);
const identities=new ScriptIdentities(model.script_identities),contexts=new Map();
for(const [signature,bucket] of Object.entries(model.script_identities?.scripts||{}))
 for(const script of bucket) for(const path of script.paths)
  for(const [functionName,fn] of Object.entries(script.functions))
   for(const [argumentsToken,call] of Object.entries(fn.calls)) for(const record of call.records) {
    const key=path+'/'+functionName+'/called/'+record+'/assembled_dialogue';
    if(!contexts.has(key))contexts.set(key,[]);
    contexts.get(key).push({signature,sha256:script.sha256,functionName,argumentsToken});
   }
const rows=[];
const padding=t=>t.split('\n').map(line=>line
 .replace(/^((?:<[^<>]*>)*)([ \t\u3000]+)/,'$1')
 .replace(/[ \t\u3000]+(?=(?:<[^<>]*>)*$)/,'')).join('\n');
const words=t=>/[\p{L}\p{N}]/u.test(t.replace(/<[^<>]*>/g,''));
for(const c of data.cases) for(const mode of ['primary','secondary']) {
 const actual=runtime.translate(c.source,mode),expected=c[mode];
 const verdict=actual===expected?'exact':
  !words(actual)&&!words(expected)?'nonlinguistic_decoration':
  padding(actual)===padding(expected)?'line_padding_only':'failed';
 const row={name:c.name,mode,pass:verdict!=='failed',verdict,...(c.expectation?{expectation:c.expectation}:{}),
  ...(verdict==='failed'?{actual,expected}:{})};
 if(verdict==='failed'&&c.name.startsWith('panel:')) {
  // A separate result: copied log text may lack this resource identity.
  // Never turn a global miss into a pass based on offline context availability.
  const candidates=contexts.get(c.name.slice(6))||[];
  const values=candidates.map(id=>{
   const selected=identities.lookup(id);
   return selected?new RuntimeText(selected.model).translate(c.source,mode):null;
  });
  row.context_candidates=values.length;
  row.context_pass=values.length>0&&values.every(value=>value===expected);
 }
 rows.push(row);
}
// Translation-only checks miss a renderer that drops a known display body
// after its dynamic emotion header changed. Check the owned payload itself.
const visible=t=>t.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
for(const c of data.cases) {
 if(!c.name.startsWith('reported_log_slot_')&&!c.annotation_terms)continue;
 const plan=runtime.render(c.source,'annotation');
 const payload=plan.layers.map(layer=>layer.text).join('')+
  [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
 const needed=!model.same_language&&!c.expectation&&RuntimeText.needsAnnotation(c.primary,c.secondary);
 let pass=needed?plan.kind!=='plain':plan.kind==='plain'&&plan.text===c.primary;
 if(needed&&c.name.startsWith('reported_log_slot_'))pass&&=visible(payload)===visible(c.secondary);
 if(needed&&c.annotation_terms)for(const [a,b] of c.annotation_terms)
  if(visible(a)!==visible(b))pass&&=visible(payload).includes(visible(b));
 const verdict=!pass?'failed':c.expectation?'preserve_ambiguous_complete_display':
  model.same_language?'same_language_plain':needed?'owned_secondary_payload':'no_distinct_annotation_required';
 rows.push({name:c.name,mode:'annotation',pass,verdict,
  kind:plan.kind,layers:plan.layers.length,...(c.expectation?{expectation:c.expectation}:{}),
  ...(pass?{}:{actual:plan,expected:c.secondary})});
}
process.stdout.write(JSON.stringify(rows));
"""


def cases(catalog, language, panel_keys=()):
    def text(key):
        return catalog[key][language]

    def modifier(name):
        return text("table/t_text.tbl/TXT_ITEM_HELP_" + name)

    result = {
        "full_screen_note": text(NOTE),
        "centered_key_hint_with_repeated_controls": text(KEY_HINT),
        "static_reward_after_dynamic_items": text(
            "script/scena/mp6010_01.dat/EV_00_06_00/called/93/assembled_dialogue"
        ),
        "colored_skill_header": (
            f"<C3></C>【{text(keys.ARTS_ATTACK)}<I278>／<I295><C3>"
            f"{text(keys.TARGET_RANGE)}{modifier('RANGE_S')}</C>】<c698>"
            f"{text(keys.DELAY).removesuffix('%s')}<c698>{modifier('MIDDLE')}</C></C>"
            f"<c698>／</C><c698>{text(keys.FREEZE).replace('%d', '40').replace('%%', '%')}</C>\n"
            f"<C0>{text(keys.SKILL_DESCRIPTION)}"
        ),
        "self_range": (
            f"<C3>{text(keys.SELF_RANGE)}{modifier('RANGE_L')}</C>\n<C0>{text(keys.SKILL_DESCRIPTION)}"
        ),
        "item_enhance": (
            f"{text(keys.ITEM_KIND_HELP)}【<I299>{text(keys.SINGLE_RANGE)}："
            f"<c698>{text(keys.STATUS_BASE + '/stat')}</C> - <I378><c698>"
            f"{text(keys.STATUS_BASE + '/format').replace('%d', '20')}</C>】\n"
            f"{text(keys.ITEM_DESCRIPTION)}"
        ),
    }
    result.update({"panel:" + key: text(key) for key in panel_keys})
    for number, head in ((6, "<#E_E#M_4#B_0>"), (8, "<#E_0#M_4#B_0>"), (10, "<#E_8#M_4#B_0>")):
        key = f"script/scena/mp3010_01.dat/TK_FEY/called/{number}/assembled_dialogue"
        result[f"reported_log_slot_{898 + (number - 6) // 2}"] = head + display_text(text(key))
    header = text(
        "table/t_itemhelp.tbl/SkillTextArrayData/sha256:0ff0b8e463a2230e063ea3156b3ff047d345a821bf25275d0f5f3585d9f256ca/format"
    )
    area = text(keys.RANGE) + modifier("RANGE_LL")
    effect = native_recovery(catalog, language, ITEM_HELP_PERCENT_RECOVERY[0], 30)
    # The resource description begins with <C9>; preserve it after <C0>.
    result["reported_full_water_recovery_detail"] = (
        f"<C3></C>{header}<I300><C3>{area}</C>】<c698>{effect}</C><c698>／</C><c698>{modifier('DEBUFF_CANCEL')}</C>\n<C0>{text(WATER_DESCRIPTION)}"
    )
    return result


def native_recovery(catalog, language, base, amount, prefix=""):
    """Expected native order, independent of generated runtime patterns."""
    stat, form = catalog[base + "/stat"][language], catalog[base + "/format"][language]
    if prefix:
        stat = catalog["table/t_text.tbl/TXT_ITEM_HELP_" + prefix][language] + stat
    value = catalog["table/t_text.tbl/TXT_ITEM_HELP_" + ("ALL" if amount == 100 else "PERSENT")][
        language
    ]
    phrase = form.replace("%s", value.replace("%d", str(amount)).replace("%%", "%"))
    return (
        stat + (" " if language == "ko" else "") + phrase
        if language in ("ja", "zh-Hans", "zh-Hant", "ko")
        else phrase + stat
    )


def item_help_family_cases(catalog, language):
    """Resource probes and proven native inputs are different coverage scopes."""
    result, excluded = {}, []
    suffix = "\n<C0>" + catalog[WATER_DESCRIPTION][language]
    for key, texts in catalog.items():
        if not key.startswith("table/t_text.tbl/TXT_ITEM_HELP_"):
            continue
        missing = [l for l in LANGUAGES if not texts.get(l, "").strip()]
        if missing:
            excluded.append({"key": key, "reason": "missing_or_blank_locale", "locales": missing})
        elif key.rsplit("_", 1)[-1] in ("SELF", "FRIEND", "PERSENT"):
            excluded.append(
                {
                    "key": key,
                    "reason": "constructor_component_verified_in_recovery_not_independent_effect",
                    "native_rva": "0x34cf9f/0x34d45b; 0x34d08d/0x34d15b",
                }
            )
        elif key.endswith("_LINK"):
            excluded.append(
                {
                    "key": key,
                    "reason": "multi_stat_constructor_component_grouping_not_yet_verified",
                    "native_rva": "0x34cfcf/0x34d48b",
                }
            )
        elif any("%" in t for t in texts.values()):
            excluded.append({"key": key, "reason": "format_requires_separate_argument_contract"})
        elif not any(any(c.isalpha() for c in t) for t in texts.values()):
            excluded.append(
                {"key": key, "reason": "nonlinguistic_constructor_or_decoration_not_effect"}
            )
        else:
            result["item_help_component_probe:" + key] = (
                "<c698>" + texts[language] + "</C>" + suffix
            )
    for base in ITEM_HELP_PERCENT_RECOVERY:
        for prefix in ("", "SELF", "FRIEND"):
            for amount in (0, 1, 30, 99, 100, 150):
                effect = native_recovery(catalog, language, base, amount, prefix)
                result[f"item_help_recovery:{base}:{prefix}:{amount}"] = (
                    "<c698>" + effect + "</C>" + suffix
                )
    return result, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", default=os.environ.get("SORA_GAME_DIR"), type=Path)
    parser.add_argument("--source", choices=LANGUAGES, default="zh-Hans")
    parser.add_argument("--secondary", choices=LANGUAGES, default="ja")
    parser.add_argument("--targets", nargs="+", choices=LANGUAGES, default=LANGUAGES)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/reported-texts-check.json")
    parser.add_argument(
        "--panel-audit", type=Path, help="replay every verified key from audit_static_panels"
    )
    parser.add_argument(
        "--item-help-audit",
        action="store_true",
        help="replay every direct item-help text and verified recovery constructor",
    )
    args = parser.parse_args()
    if args.game_dir is None:
        parser.error("provide --game-dir or SORA_GAME_DIR")
    entries, signature = load_entries(args.game_dir)
    catalog = {entry["key"]: entry["texts"] for entry in entries}
    panel_keys = ()
    if args.panel_audit:
        panel_report = json.loads(args.panel_audit.read_text(encoding="utf-8"))
        if panel_report.get("source_language") != args.source:
            parser.error("panel audit source does not match --source")
        panel_keys = panel_report["verified_keys"]
        if not panel_keys:
            parser.error("panel audit contains no verified keys")
    source, secondary = (
        cases(catalog, args.source, panel_keys),
        cases(catalog, args.secondary, panel_keys),
    )
    family_excluded = []
    if args.item_help_audit:
        family, family_excluded = item_help_family_cases(catalog, args.source)
        source.update(family)
        secondary.update(item_help_family_cases(catalog, args.secondary)[0])
    config = {
        **read_config(),
        "game_language": args.source,
        "secondary": args.secondary,
        "scope": "all",
    }
    report = {
        "scope": "full production catalog and JS; exact resource-derived expected text",
        "game_attached": False,
        "signature": json.loads(signature),
        "source": args.source,
        "secondary": args.secondary,
        "entries": len(entries),
        "panel_cases": len(panel_keys),
        "item_help_family_raw_fields": sum(
            key.startswith("table/t_text.tbl/TXT_ITEM_HELP_") for key in catalog
        )
        if args.item_help_audit
        else None,
        "item_help_scope": "component probes test isolated resource lookup, not proof of independent native display; recovery cases use verified single-stat order, prefixes, and percent/all branches; LINK multi-stat aggregation is not covered",
        "item_help_family_excluded": family_excluded,
        "targets": [],
        "all_passed": True,
        "all_reported_inputs_passed": True,
        "all_verified_recovery_passed": True,
        "context_scope": "compiled resource identity only; availability in live controls/logs is not proven",
        "all_resolvable_with_compiled_context": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for target in args.targets:
        start = time.monotonic()
        config["primary"] = target
        model = load_model(entries, signature, config, game=args.game_dir)
        coverage = model.get("coverage")
        del model
        gc.collect()
        primary = cases(catalog, target, panel_keys)
        if args.item_help_audit:
            primary.update(item_help_family_cases(catalog, target)[0])
        # Slot 898 has two complete script identities with different Western
        # dialogue. With no script identity on copied log text, preserve it.
        body = display_text(source["reported_log_slot_898"])
        conflicts = [
            {
                "key": e["key"],
                "primary": display_text(e["texts"][target]),
                "secondary": display_text(e["texts"][args.secondary]),
            }
            for e in entries
            if e.get("display_role") == "dialogue"
            and display_text(e["texts"].get(args.source, "")) == body
            and e["texts"].get(target)
            and e["texts"].get(args.secondary)
        ]
        ambiguous_log = len({(c["primary"], c["secondary"]) for c in conflicts}) > 1
        data = {
            "model": str(model_path(signature, config)),
            "cases": [
                {
                    "name": name,
                    "source": value,
                    "primary": value
                    if ambiguous_log and name == "reported_log_slot_898"
                    else primary[name],
                    "secondary": value
                    if ambiguous_log and name == "reported_log_slot_898"
                    else secondary[name],
                    **(
                        {"expectation": "preserve_ambiguous_complete_display"}
                        if ambiguous_log and name == "reported_log_slot_898"
                        else {}
                    ),
                    **(
                        {
                            "annotation_terms": list(
                                zip(
                                    re.findall(r"<c698>([^<>]+)</C>", primary[name]),
                                    re.findall(r"<c698>([^<>]+)</C>", secondary[name]),
                                )
                            )
                        }
                        if name == "reported_full_water_recovery_detail"
                        or name.startswith("item_help_recovery:")
                        else {}
                    ),
                }
                for name, value in source.items()
            ],
        }
        result = subprocess.run(
            ["node", "-e", RUNNER],
            cwd=ROOT,
            input=json.dumps(data, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        rows = json.loads(result.stdout)
        passed = all(row["pass"] for row in rows)
        reported_passed = all(
            row["pass"] for row in rows if not row["name"].startswith("item_help_")
        )
        recovery_passed = all(
            row["pass"] for row in rows if row["name"].startswith("item_help_recovery:")
        )
        with_context = all(row["pass"] or row.get("context_pass", False) for row in rows)
        report["targets"].append(
            {
                "target": target,
                "seconds": round(time.monotonic() - start, 3),
                "coverage": coverage,
                "rows": rows,
                "all_passed": passed,
                "all_reported_inputs_passed": reported_passed,
                "all_verified_recovery_passed": recovery_passed,
                "ambiguous_log_898_records": conflicts if ambiguous_log else [],
                "all_resolvable_with_compiled_context": with_context,
            }
        )
        report["all_passed"] &= passed
        report["all_reported_inputs_passed"] &= reported_passed
        report["all_verified_recovery_passed"] &= recovery_passed
        report["all_resolvable_with_compiled_context"] &= with_context
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(target, "PASS" if passed else "FAIL", flush=True)
    if not report["all_passed"]:
        raise AssertionError(f"Full-model omissions remain; see {args.output}")


if __name__ == "__main__":
    main()
