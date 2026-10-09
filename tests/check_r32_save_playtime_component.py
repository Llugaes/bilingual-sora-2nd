"""Bounded Playtime display-caption fixture; not a production-wire verdict.

Run: python -B tests/check_r32_save_playtime_component.py
Reads the four official t_text excerpts already preserved in the readonly receipt.
The captured nine-line source and the original SaveLocalization tests stay intact.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator

FIXTURE = ROOT / "tests/fixtures/r32-save-summary-live002-en.json"
FIXTURE_SHA = "8c670bc315546a83290f620835db54f7a20f5cf36306829427482d9485eb43dc"
OLD_TEST = ROOT / "tests/test_save_localization.py"
OLD_TEST_SHA = "0a14aa5b145f31b8ab92811b991be3cce2542e8f133204fec7a16ed27637319d"
SOURCE_SHA = "02787564d420b4dfce1c33c578bf0d02eb614587f059cc3e33dbbfbea742e3cd"
CAPTIONS = {"en": "Playtime", "ja": "プレイ時間", "zh-Hans": "游玩时间", "zh-Hant": "遊玩時間"}
CONFIGURATIONS = [("en", "zh-Hans"), ("ja", "zh-Hans"), ("zh-Hans", "ja"), ("zh-Hant", "ja")]
MODES = ("primary", "secondary", "annotation")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_line(primary, secondary, mode):
    a, b = CAPTIONS[primary], CAPTIONS[secondary]
    caption = a if mode == "primary" else b if mode == "secondary" else f"<R>{a}</R{b}>"
    return "  " + caption + "\u3000\u3000 075:16:39"


def expected_caption(primary, secondary, mode, padding):
    a, b = padding + CAPTIONS[primary], padding + CAPTIONS[secondary]
    return a if mode == "primary" else b if mode == "secondary" else f"<R>{a}</R{b}>"


def main():
    assert digest(FIXTURE) == FIXTURE_SHA
    assert digest(OLD_TEST) == OLD_TEST_SHA
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = fixture["row"]["original"]
    assert hashlib.sha256(source.encode()).hexdigest() == SOURCE_SHA
    assert len(source.split("\n")) == 9
    original_line = source.split("\n")[-1]
    assert original_line == "  Playtime\u3000\u3000 075:16:39"
    unknown_full_input = "\n".join(["Unknown saved input", *source.split("\n")[1:]])
    evidence = json.loads(
        (ROOT / "generated/r32-save-summary-readonly.json").read_text(encoding="utf-8")
    )
    entries = evidence["official_resources"]["entries"]
    raw = next(e for e in entries if e["key"] == "table/t_text.tbl/TXT_SAVE_DETAIL_PLAYTIME")
    assert raw["texts"] == {lang: "  Playtime" for lang in CAPTIONS}
    report = {
        "schema": 1,
        "evidence": "component models built only from preserved official t_text excerpts; current Python/JS and production callback pointer fixture; no current full production model, package or game acceptance",
        "fixture_sha256": digest(FIXTURE),
        "original_test_sha256": digest(OLD_TEST),
        "source_utf8_sha256": SOURCE_SHA,
        "game_attached": False,
        "declared_display_caption_contract": CAPTIONS,
        "python": [],
        "source_sha256": {},
    }
    for name in [
        "sora_bilingual/localization/save_summary.py",
        "sora_bilingual/localization/menu_text.py",
        "sora_bilingual/game/scripts/runtime_text.js",
        "sora_bilingual/game/scripts/native_agent.js",
    ]:
        report["source_sha256"][name] = digest(ROOT / name)
    payload = {
        "source": source,
        "original_line": original_line,
        "unknown_full_input": unknown_full_input,
        "cases": [],
    }
    python_mode_cases = 0
    for primary, secondary in CONFIGURATIONS:
        tr = MenuTranslator(entries, primary, secondary, primary)
        saved = tr.scoped["save_summary"]
        modes = {}
        for mode in MODES:
            expected = expected_line(primary, secondary, mode)
            complete = saved.translate(source, mode)
            assert complete.split("\n")[-1] == expected, (primary, mode, complete)
            assert len(complete.split("\n")) == 9
            for index in range(4, 8):
                assert complete.split("\n")[index] == source.split("\n")[index], (
                    "unprovided party names/levels must retain the exact captured whitespace"
                )
            assert saved.translate(original_line, mode) == expected
            for padding in ("", "  "):
                assert saved.translate(padding + "Playtime", mode) == expected_caption(
                    primary, secondary, mode, padding
                )
            if primary == "en" and mode == "primary":
                assert complete == source, "captured primary EN input must remain byte-exact"
            # Normal menus retain the original shared resource caption.
            for outside in ("Playtime", "  Playtime", original_line, unknown_full_input):
                assert tr.translate(outside, mode) == outside, (primary, mode, outside)
            assert (
                saved.translate("Unknown saved input 075:16:39", mode)
                == "Unknown saved input 075:16:39"
            )
            modes[mode] = {
                "expected_last_line": expected,
                "actual_last_line": complete.split("\n")[-1],
                "full_input": complete,
            }
            python_mode_cases += 1
        # Missing official target text must not be supplied by caption constants.
        missing = json.loads(json.dumps(entries, ensure_ascii=False))
        next(e for e in missing if e["key"] == raw["key"])["texts"].pop(secondary)
        missing_saved = MenuTranslator(missing, primary, secondary, primary).scoped["save_summary"]
        for mode in MODES:
            assert missing_saved.translate(original_line, mode) == original_line
        report["python"].append(
            {
                "primary": primary,
                "secondary": secondary,
                "modes": modes,
                "missing_target_refusals": 3,
            }
        )
        payload["cases"].append(
            {
                "primary": primary,
                "secondary": secondary,
                "model": tr.runtime_model(),
                "missing_model": MenuTranslator(
                    missing, primary, secondary, primary
                ).runtime_model(),
                "expected": {mode: expected_line(primary, secondary, mode) for mode in MODES},
                "caption_expected": {
                    mode: [
                        expected_caption(primary, secondary, mode, padding)
                        for padding in ("", "  ")
                    ]
                    for mode in MODES
                },
            }
        )
    runner = r"""
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8')),root=process.cwd();
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
let code=fs.readFileSync(path.join(root,'tests/test_native_agent.js'),'utf8'),m={exports:{}};
new Function('require','__dirname','module',code.slice(0,code.indexOf('\ntest('))+'\nmodule.exports={makeRuntime};')(require,path.join(root,'tests'),m);
let modeCases=0;const cases=[];
for(const row of input.cases){
 const global=new RuntimeText(row.model),saved=global.scoped.save_summary,r=m.exports.makeRuntime(null,true);
 r.api.load(row.model,'annotation',true,1);
 const parent=r.label(0xf10000,''),label=r.label(0xf11000,'');parent.name='root';label.name='text';label.parent=parent;r.registerLayout(parent,8);
 const detail={primary:row.primary,secondary:row.secondary,modes:{}};
 for(const mode of ['primary','secondary','annotation']){
  const plan=saved.render(input.source,mode);assert.equal(plan.text.split('\n').at(-1),row.expected[mode]);assert.equal(plan.text.split('\n').length,9);
  for(let i=4;i<8;i++)assert.equal(plan.text.split('\n')[i],input.source.split('\n')[i]);
  if(row.primary==='en'&&mode==='primary')assert.equal(plan.text,input.source);
  assert.equal(saved.translate(input.original_line,mode),row.expected[mode]);
  for(const [i,padding] of ['', '  '].entries())assert.equal(saved.translate(padding+'Playtime',mode),row.caption_expected[mode][i]);
  for(const outside of ['Playtime','  Playtime',input.original_line,input.unknown_full_input])assert.equal(global.translate(outside,mode),outside);
  r.api.select(mode,true);r.registerLayout(parent,8);r.externalSet(label,input.source);
  const snap=r.api.snapshot().find(v=>v.original===input.source);assert.equal(snap.scope,'save_summary');assert.equal(label.text().split('\n').at(-1),row.expected[mode]);assert.equal(label.text().split('\n').length,9);
  // The same text under a different layout cannot receive save-caption aliases.
  r.registerLayout(parent,7);r.externalSet(label,input.source);assert.equal(label.text().split('\n').at(-1),input.original_line);
  r.registerLayout(parent,8);const unknown=input.unknown_full_input;r.externalSet(label,unknown);assert.equal(label.text(),unknown);
  const unknownRow=r.api.snapshot().find(v=>v.original===unknown);assert.notEqual(unknownRow.scope,'save_summary');
  const missing=new RuntimeText(row.missing_model).scoped.save_summary;assert.equal(missing.translate(input.original_line,mode),input.original_line);
  detail.modes[mode]={expected_last_line:row.expected[mode],pure_plan:plan,callback_scope:snap.scope,
    outside_layout_last_line:input.original_line,unknown_complete_input:unknown,missing_target_refused:true};modeCases++;
 }
 assert.equal(r.api.status().failed,false);r.api.disable();cases.push(detail);
}
console.log(JSON.stringify({cases,mode_cases:modeCases,indented_and_bare_caption_cases:24,production_callback_cases:12,unknown_popup_refusals:12,outside_layout_caption_retention:12,missing_target_refusals:12}));
"""
    run = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps(payload, ensure_ascii=False),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if run.returncode:
        raise AssertionError(run.stderr)
    report["javascript"] = json.loads(run.stdout)
    assert digest(FIXTURE) == FIXTURE_SHA
    assert digest(OLD_TEST) == OLD_TEST_SHA
    for name, value in report["source_sha256"].items():
        assert digest(ROOT / name) == value, (
            "production source changed during component audit: " + name
        )
    report["python_mode_cases"] = python_mode_cases
    report["checker_sha256"] = digest(Path(__file__))
    output = ROOT / "generated/r32-save-playtime-component-after.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": digest(output),
                "python_mode_cases": python_mode_cases,
                "javascript_mode_cases": report["javascript"]["mode_cases"],
                "full_input_configurations": 4,
                "production_callback_cases": 12,
                "passed": True,
            }
        )
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
