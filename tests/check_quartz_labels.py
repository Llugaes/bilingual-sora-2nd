"""Check label-only quartz rendering with the complete catalog and production JS.

Reads installed resources only. Every source locale and target locale is used;
no game is started, attached, or modified, and no user configuration is written.
"""

import argparse
import gc
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries
from sora_bilingual.localization.item_help_composition import build_item_help_grammar
from sora_bilingual.localization.menu_text import MenuTranslator


RUNNER = r"""
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const runtime=new RuntimeText(data.model), rows=[];
for(const c of data.cases) {
 const start=performance.now(),plan=runtime.render(c.source),ms=performance.now()-start;
 const actual=runtime.translate(c.source,'primary');
 const ruby=[...plan.text.matchAll(/<R>[^<>]*?<\/R([^<>]*)>/g)].map(m=>m[1]);
 const secondary=plan.layers.map(l=>l.text).concat(ruby).join('');
 const pass=actual===c.expected && !secondary.includes('<I') && !secondary.includes('×') &&
  (plan.text.match(/<I/g)||[]).length===(c.source.match(/<I/g)||[]).length &&
  c.secondary.every(term=>secondary.includes(term));
 rows.push({name:c.name,pass,ms,...(pass?{}:{actual,expected:c.expected,plan,secondary})});
}
console.log(JSON.stringify(rows));
"""


def labels(template):
    """Independent expectation from the raw locale's two visible fields."""
    opening = next(c for c in template if c in "【[(")
    name, _, inner = template.partition(opening)
    colon = next(c for c in inner if c in ":：")
    return name.strip(), inner.partition(colon)[0].strip()


def check(game, output):
    entries, _ = load_entries(game)
    catalog = {entry["key"]: entry["texts"] for entry in entries}
    grammar = build_item_help_grammar(game, entries, "zh-Hans")
    all_entries = entries + grammar["status_entries"] + grammar["detail_entries"]
    title_keys = sorted(
        {
            row["key"].rsplit("/label/", 1)[0]
            for row in grammar["detail_entries"]
            if "/label/element" in row["key"]
        }
    )
    assert len(title_keys) == 7
    pairs = [(source, "en" if source != "en" else "zh-Hans") for source in LANGUAGES]
    pairs += [("zh-Hans", target) for target in LANGUAGES if ("zh-Hans", target) not in pairs]
    result = {"game_started": False, "game_attached": False, "targets": [], "all_passed": True}
    description_key = next(
        key
        for key, texts in catalog.items()
        if key.startswith("table/t_item.tbl/")
        and key.endswith("/description")
        and all(texts.get(language) for language in LANGUAGES)
        and all("<" not in text and "%" not in text for text in texts.values())
    )
    for source, primary in pairs:
        start = time.perf_counter()
        translator = MenuTranslator(all_entries, primary, "ja", source)
        cases = []
        for key in title_keys:
            source_template = catalog[key][source]
            source_labels = labels(source_template)
            target_labels = labels(catalog[key][primary])
            secondary_labels = labels(catalog[key]["ja"])
            for payload in ("<I42>×4", "<I42>×3<I45>×3", "<I999>×12"):
                original = source_template.replace("%s", payload)
                expected = original
                for before, after in zip(source_labels, target_labels):
                    expected = expected.replace(before, after, 1)
                for suffix in ("", "\nUNKNOWN", "\n" + catalog[description_key][source]):
                    translated_suffix = (
                        ("\n" + catalog[description_key][primary])
                        if suffix and suffix != "\nUNKNOWN"
                        else suffix
                    )
                    cases.append(
                        {
                            "name": key + ":" + payload + ":" + str(bool(suffix)),
                            "source": "<S32><C1>" + original + "</C>" + suffix,
                            "expected": "<S32><C1>" + expected + "</C>" + translated_suffix,
                            "secondary": [
                                b for a, b in zip(target_labels, secondary_labels) if a != b
                            ],
                        }
                    )
        data = {"model": translator.runtime_model(), "cases": cases}
        compiled = time.perf_counter() - start
        replay = subprocess.run(
            ["node", "-e", RUNNER],
            cwd=ROOT,
            input=json.dumps(data),
            capture_output=True,
            text=True,
            encoding="utf8",
            check=True,
        )
        rows = json.loads(replay.stdout)
        failed = [row for row in rows if not row["pass"]]
        result["targets"].append(
            {
                "source": source,
                "primary": primary,
                "secondary": "ja",
                "cases": len(rows),
                "failed": failed,
                "compile_seconds": round(compiled, 3),
                "max_cold_render_ms": round(max(row["ms"] for row in rows), 3),
            }
        )
        result["all_passed"] &= not failed
        print(json.dumps({"source": source, "primary": primary, "failed": len(failed)}), flush=True)
        del translator, data
        gc.collect()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    assert result["all_passed"], str(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.game, args.output)
