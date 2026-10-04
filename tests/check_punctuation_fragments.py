"""Replay nonlinguistic catalog fragments without borrowing their call identity."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.menu_text import MenuTranslator

RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(0,'utf8')),rows=[];
for(const mode of data.modes) {
 const tr=new RuntimeText(mode.model),failures=[];
 for(const source of mode.sources) {
  const wrapped='<c698>'+source+'</C>';
  for(const side of ['primary','secondary']) {
   if(tr.component(source,side)!==source)failures.push({source,side,stage:'component'});
   if(tr.literalArgument(source,side==='primary'?0:1)!==source)failures.push({source,side,stage:'argument'});
   if(tr.translate(wrapped,side)!==wrapped)failures.push({source,side,stage:'translate'});
  }
  const plan=tr.render(wrapped);
  if(plan.text!==wrapped||plan.layers.length)failures.push({source,stage:'render',plan});
 }
 rows.push({source:mode.source,target:mode.target,cases:mode.sources.length,failures});
}
process.stdout.write(JSON.stringify(rows));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "generated/catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries = json.loads(args.catalog.read_text("utf-8"))["entries"]
    modes, inventory, failures = [], [], []
    for source in LANGUAGES:
        selected = [
            e
            for e in entries
            if (value := e["texts"].get(source, "")).strip()
            and not any(char.isalnum() for char in value)
            and "<" not in value
            and ">" not in value
        ]
        # Every raw source remains in the denominator, including ambiguous
        # fragments that are already excluded from the global dictionary.
        sources = sorted({e["texts"][source] for e in selected})
        inventory.append({"source": source, "records": len(selected), "sources": sources})
        for target in LANGUAGES:
            if source == target:
                continue
            tr = MenuTranslator(selected, source, target, source)
            for value in sources:
                wrapped = "<c698>" + value + "</C>"
                for side in ("primary", "secondary"):
                    if (
                        tr.component(value, side) != value
                        or tr.literal_argument(value, int(side == "secondary")) != value
                        or tr.translate(wrapped, side) != wrapped
                    ):
                        failures.append(
                            {"source": source, "target": target, "value": value, "side": side}
                        )
                plan = tr.render(wrapped)
                if plan["text"] != wrapped or plan["layers"]:
                    failures.append(
                        {"source": source, "target": target, "value": value, "stage": "render"}
                    )
            modes.append(
                {
                    "source": source,
                    "target": target,
                    "sources": sources,
                    "model": tr.runtime_model(),
                }
            )
    run = subprocess.run(
        ["node", "-e", RUNNER],
        input=json.dumps({"modes": modes}, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=ROOT,
        check=True,
    )
    reports = json.loads(run.stdout)
    result = {
        "game_attached": False,
        "inventory": inventory,
        "python_failures": failures,
        "javascript": reports,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    total = sum(row["cases"] for row in reports)
    failed = len(failures) + sum(len(row["failures"]) for row in reports)
    print(json.dumps({"modes": len(modes), "cases": total, "failures": failed}))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
