"""Replay copied save metadata and localized shortcut keys from full resources.

Read-only/offline: never starts or attaches a game. Native surface routing is
covered separately by test_native_agent.js and captured layout paths.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.native_catalog import load_entries
from sora_bilingual.localization.menu_text import MenuTranslator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/saved-source-check.json")
    args = parser.parse_args()
    entries, _ = load_entries(args.game_dir)
    samples = {
        "第８章“混沌大地”",
        "卢安市・北街区",
        "将零力场生成器送去各个协会分部",
        "艾丝蒂尔",
        "约书亚",
        "雪拉扎德",
        "阿加特",
    }
    by_text = {}
    for entry in entries:
        text = entry["texts"].get("zh-Hans")
        if text in samples and entry["key"].startswith(
            (
                "table/t_chapter.tbl/",
                "table/t_place.tbl/",
                "table/t_name.tbl/",
                "table/t_quest.tbl/NaviText/",
            )
        ):
            by_text.setdefault(text, entry)
    assert set(by_text) == samples
    shortcut_keys = [
        "TXT_KEY_HELP_HIDE_UI",
        "TXT_CAMP_COSTUME_KEY_HELP_HIDE_TEXT",
        "TXT_VIEWER_UI_HIDE",
        "TXT_STEAM_OPT_TEXT_HIDE_UI",
        "TXT_STEAM_BUTTON_EVENT_PAUSE_1",
        "TXT_STEAM_BUTTON_EVENT_PAUSE_2",
    ]
    shortcuts = {
        e["key"].split("/")[-1]: e["texts"]
        for e in entries
        if e["key"].startswith("table/t_text.tbl/")
    }
    runner = r"""
const fs=require('fs'),assert=require('assert/strict');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text');
const data=JSON.parse(fs.readFileSync(process.argv[1],'utf8')),r=new RuntimeText(data.model);
const saved=r.scoped.save_summary;let checks=0;
for(const source of ['Elk','Tourist','Bobcat','菲']){
  for(const mode of ['primary','secondary','annotation']){
    assert.equal(saved.render(source,mode).text,source,'ambiguous saved alias '+source);checks++;
  }
}
for(const row of data.cases){
  for(const [mode,target] of [['primary',row.a],['secondary',row.b]]){
    assert.equal(saved.render(row.source,mode).text,target,JSON.stringify(row));checks++;
  }
  const plan=saved.render(row.source,'annotation'),output=plan.text+plan.layers.map(x=>x.text).join('');
  for(const text of [row.a,row.b])assert.ok(output.includes(text),JSON.stringify({row,plan}));checks++;
}
for(const row of data.shortcuts){
  const plan=r.render(row.source,'annotation',row.key);
  const output=plan.text+plan.layers.map(x=>x.text).join('');
  for(const text of [row.a,row.b])assert.ok(output.includes(text),JSON.stringify({row,plan}));checks++;
}
for(const prefix of data.model.save_confirmation_prefixes){
  const source=prefix+data.mixed,plan=saved.render(source,'annotation');
  const output=plan.text+plan.layers.map(x=>x.text).join('');
  for(const text of data.expected)assert.ok(output.includes(text),JSON.stringify({text,plan}));
  for(const token of ['＜Nightmare＞','Lv.86','059:22:58'])assert.ok(output.includes(token));checks++;
}
assert.equal(r.render('艾丝蒂尔','primary').text,'艾丝蒂尔','saved aliases must not enter normal menus');
console.log(JSON.stringify({checks}));
"""
    report = {"game_attached": False, "models": []}
    with tempfile.TemporaryDirectory(prefix="sora-save-check-") as temporary:
        path = Path(temporary) / "replay.json"
        for current, primary, secondary in (("en", "ja", "zh-Hans"), ("ja", "en", "zh-Hans")):
            tr = MenuTranslator(entries, primary, secondary, current)
            cases = []
            for entry in by_text.values():
                for source in entry["texts"].values():
                    cases.append(
                        {
                            "source": source,
                            "a": entry["texts"][primary],
                            "b": entry["texts"][secondary],
                        }
                    )
            mixed = "第８章“混沌大地”\u3000 ＜Nightmare＞\n卢安市・北街区\n将零力场生成器送去各个协会分部\n"
            for language, text in zip(
                ("zh-Hans", "en", "ja", "fr"), ("艾丝蒂尔", "约书亚", "雪拉扎德", "阿加特")
            ):
                mixed += "\u3000·" + by_text[text]["texts"][language] + "\u3000\u3000Lv.86\n"
            mixed += "  Playtime\u3000 059:22:58"
            payload = {
                "model": tr.runtime_model(),
                "cases": cases,
                "mixed": mixed,
                "expected": [e["texts"][l] for e in by_text.values() for l in (primary, secondary)],
                "shortcuts": [
                    {
                        "key": key,
                        "source": shortcuts[key][current],
                        "a": shortcuts[key][primary],
                        "b": shortcuts[key][secondary],
                    }
                    for key in shortcut_keys
                ],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), "utf8")
            result = subprocess.run(
                ["node", "-e", runner, str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf8",
                check=True,
            )
            row = {
                "current_source": current,
                "primary": primary,
                "secondary": secondary,
                "saved_sources": 8,
                **json.loads(result.stdout),
            }
            report["models"].append(row)
            print(json.dumps(row), flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf8")


if __name__ == "__main__":
    main()
