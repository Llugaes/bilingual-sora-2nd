"""Replay the reported recipe screen against eight full source-language models.

Uses installed resource files only. Does not start, attach to, or change a game.
Table-identity checks prove compiler/resolver availability, not live UI provenance.
"""

import argparse
import gc
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries, load_model, model_path

ITEMS = (
    "61f927d3f1cab35b22fa221f58803df5a85bae4378619a69d9033d8cdc603a45",
    "707169783a751d1bb99c6fe0abb39f18db34713b9576ebfd51b1c6cafe573b2a",
    "0f7053a7f679aaeb2957b8caedc1e7d93f9e265b28741357113b836c3d30a430",
    "6b98e8230d124abcd9a2f00b4c4fa294fd7b87741f1f6ed739d48449832dc3be",
    "e60784d2f2adac5237c91d70d454f2c9452b6ea08c0d0cbaffab6a8f4b222407",
)
KEYS = [f"table/t_item.tbl/sha256:{item}/name" for item in ITEMS] + [
    "table/t_text.tbl/TXT_NOTE_COOK_" + suffix for suffix in ("HEADER", "EXECUTE", "HAVE_NUM")
]

RUNNER = r"""
const fs=require('fs'),{RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const {TableIdentities}=require('./sora_bilingual/game/scripts/runtime_identity.js');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const model=JSON.parse(fs.readFileSync(input.path,'utf8'));
const global=new RuntimeText(model),ids=new TableIdentities(model.table_identities);
const rows=[];
for(const c of input.cases) {
 const local=ids.lookup(c.key,c.source),runtime=local?new RuntimeText(local.model):global;
 for(const mode of ['primary','secondary']) {
  const actual=runtime.translate(c.source,mode);
  rows.push({key:c.key,mode,route:local?'table_identity':'global',pass:actual===c[mode],
   ...(actual===c[mode]?{}:{actual,expected:c[mode]})});
 }
 const rendered=runtime.render(c.source,'annotation');
 rows.push({key:c.key,mode:'annotation',pass:rendered.kind!=='plain'});
}
process.stdout.write(JSON.stringify(rows));
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/source-language-models.json"
    )
    args = parser.parse_args()
    entries, signature = load_entries(args.game_dir)
    catalog = {entry["key"]: entry["texts"] for entry in entries}
    report = {"game_started": False, "game_attached": False, "models": []}
    for source in LANGUAGES:
        started = time.perf_counter()
        config = {"primary": "ja", "secondary": "zh-Hans", "game_language": source}
        model = load_model(entries, signature, config, game=args.game_dir)
        path = model_path(signature, config)
        assert model["coverage"]["complete_pair_records"] > 0
        cases = [
            {
                "key": key,
                "source": catalog[key][source],
                "primary": catalog[key]["ja"],
                "secondary": catalog[key]["zh-Hans"],
            }
            for key in KEYS
        ]
        rows = json.loads(
            subprocess.run(
                ["node", "-e", RUNNER],
                input=json.dumps({"path": str(path), "cases": cases}),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                cwd=ROOT,
            ).stdout
        )
        result = {
            "source": source,
            "checks": len(rows),
            "failures": [r for r in rows if not r["pass"]],
            "seconds": round(time.perf_counter() - started, 3),
        }
        report["models"].append(result)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        del model
        gc.collect()
    if any(row["failures"] for row in report["models"]):
        raise SystemExit("source-language model replay failed; inspect report")


if __name__ == "__main__":
    main()
