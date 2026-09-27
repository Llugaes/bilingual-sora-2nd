"""Replay old source-language history from the complete installed catalog."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sora_bilingual.config.locales import LANGUAGES
from sora_bilingual.localization.native_catalog import load_entries
from sora_bilingual.localization.speaker_context import compile_history_contexts, read_speaker_names

CALLS = (
    ("mp3010_01.dat", "QS213_00_00", 40),
    ("mp3010_01.dat", "QS213_00_00", 42),
    ("mp3041_02.dat", "QS214_00_00", 236),
    ("mp3041_02.dat", "QS214_00_00", 252),
    ("mp3041_02.dat", "QS214_00_00", 258),
)
RUNNER = r"""
const fs=require('fs'),{performance}=require('perf_hooks');
const {RuntimeText}=require('./sora_bilingual/game/scripts/runtime_text.js');
const data=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const runtime=new RuntimeText({pairs:{},plain_pairs:{},history_contexts:data.model});
const visible=s=>s.replace(/<[^<>]*>/g,'').replace(/\s/g,'');
const results=[];
for(const c of data.cases) {
 const start=performance.now(),context=runtime.historyContext(c.speaker,c.source),tr=context?.tr;
 const primary=tr?.translate(c.source,'primary'),secondary=tr?.translate(c.source,'secondary');
 const plan=tr?.render(c.source,'annotation');
 const payload=plan?plan.layers.map(l=>l.text).join('')+
  [...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join(''):'';
 const expectedPayload=RuntimeText.needsAnnotation(...c.expected)?visible(c.expected[1]):'';
 results.push({key:c.key,source_locale:c.locale,pass:primary===c.expected[0]&&secondary===c.expected[1]&&
  visible(payload)===expectedPayload,primary,secondary,expected:c.expected,annotation:payload,
  cold_ms:performance.now()-start});
}
process.stdout.write(JSON.stringify(results));
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "generated/mixed-history-check.json")
    args = parser.parse_args()
    entries, _ = load_entries(args.game_dir)
    names = {locale: read_speaker_names(args.game_dir, locale) for locale in LANGUAGES}
    reports = []
    for target in ("ja", "en"):
        start = time.perf_counter()
        model = compile_history_contexts(entries, names, "zh-Hans", target)
        seconds = time.perf_counter() - start
        cases = []
        for path, function, call in CALLS:
            key = f"script/scena/{path}/{function}/called/{call}/assembled_dialogue"
            matches = [
                entry
                for entry in entries
                if entry["key"].split("/alignment/")[0] == key
                and all(locale in entry["texts"] for locale in LANGUAGES)
            ]
            if len(matches) != 1:
                raise AssertionError(f"Expected one full aligned record for {key}: {len(matches)}")
            entry = matches[0]
            for locale in LANGUAGES:
                cases.append(
                    {
                        "key": key,
                        "locale": locale,
                        "source": entry["texts"][locale],
                        "speaker": names[locale].get(entry.get("speaker_ids", {}).get(locale), ""),
                        "expected": [entry["texts"]["zh-Hans"], entry["texts"][target]],
                    }
                )
        payload = json.dumps({"model": model, "cases": cases}, ensure_ascii=False)
        with TemporaryDirectory(prefix="sora-history-") as temporary:
            path = Path(temporary) / "model.json"
            path.write_text(payload, encoding="utf-8")
            run = subprocess.run(
                ["node", "-e", RUNNER, str(path)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        results = json.loads(run.stdout)
        reports.append(
            {
                "target": target,
                "compile_seconds": seconds,
                "bytes": len(payload.encode()),
                "source_bodies": len(model["texts"]),
                "shared_pairs": len(model["pairs"]),
                "passed": sum(row["pass"] for row in results),
                "total": len(results),
                "cases": results,
            }
        )
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            [{key: value for key, value in report.items() if key != "cases"} for report in reports]
        )
    )
    return int(any(report["passed"] != report["total"] for report in reports))


if __name__ == "__main__":
    raise SystemExit(main())
