"""Optional local-resource integration check, separate from portable unit tests."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.resources import LANGUAGES


def main():
    entries = json.loads((ROOT / "generated/catalog.json").read_text(encoding="utf-8"))["entries"]
    marked = [
        e
        for e in entries
        if set(LANGUAGES) <= e["texts"].keys() and any("<R>" in t for t in e["texts"].values())
    ]
    if not marked:
        raise AssertionError("No complete real ruby fixtures")
    selected = marked[:: max(1, len(marked) // 24)][:24]
    # Cover ordinary tables, numeric templates, multi-line descriptions and
    # source-locale save formats, not only Japanese ruby examples.
    complete = [
        e
        for e in entries
        if set(LANGUAGES) <= e["texts"].keys() and all(e["texts"][l].strip() for l in LANGUAGES)
    ]
    for prefix in (
        "table/t_name.tbl/",
        "table/t_chapter.tbl/",
        "table/t_item.tbl/",
        "table/t_skill.tbl/",
        "table/t_quest.tbl/NaviText/",
    ):
        rows = [e for e in complete if e["key"].startswith(prefix)]
        selected += rows[:: max(1, len(rows) // 8)][:8]
    level = next(e for e in complete if e["key"] == "table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL")
    selected.append(level)
    name = next(
        e
        for e in complete
        if e["key"].startswith("table/t_name.tbl/") and e["key"].endswith("/name")
    )
    selected.append(name)
    batches = []
    for source in LANGUAGES:
        for primary in LANGUAGES:
            for secondary in LANGUAGES:
                tr = MenuTranslator(selected, primary, secondary, source)
                cases = [
                    {
                        "source": e["texts"][source],
                        "mode": mode,
                        "plan": tr.render(e["texts"][source], mode),
                    }
                    for e in selected
                    for mode in ("annotation", "bilingual", "primary", "secondary")
                ]
                composite = " ·" + name["texts"][source] + "  " + level["texts"][source] + "39"
                for mode in ("annotation", "bilingual", "primary", "secondary"):
                    cases.append(
                        {"source": composite, "mode": mode, "plan": tr.render(composite, mode)}
                    )
                for mode, language in (("primary", primary), ("secondary", secondary)):
                    expected = (
                        " ·" + name["texts"][language] + "  " + level["texts"][language] + "39"
                    )
                    assert tr.translate(composite, mode) == expected, (
                        source,
                        primary,
                        secondary,
                        mode,
                    )
                batches.append({"model": tr.runtime_model(), "cases": cases})
    fixture = ROOT / "generated/markup-language-matrix.tmp.json"
    fixture.write_text(json.dumps(batches, ensure_ascii=False), encoding="utf-8")
    code = """const fs=require('fs'),assert=require('assert/strict'),{RuntimeText}=require('./runtime_text');
let n=0;for(const b of JSON.parse(fs.readFileSync(process.argv[1],'utf8'))){const r=new RuntimeText(b.model);
for(const c of b.cases){assert.deepEqual(r.render(c.source,c.mode),c.plan);n++;}}console.log(n);"""
    try:
        run = subprocess.run(
            ["node", "-e", code, str(fixture)], cwd=ROOT, capture_output=True, text=True, check=True
        )
    finally:
        fixture.unlink(missing_ok=True)
    result = {
        "cases": int(run.stdout),
        "language_pairs": len(LANGUAGES) ** 2,
        "source_languages": list(LANGUAGES),
        "real_fixtures": len(selected),
        "game_started": False,
        "game_attached": False,
        "code_sha256": hashlib.sha256(
            (ROOT / "sora_bilingual/localization/menu_text.py").read_bytes()
            + (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
        ).hexdigest(),
    }
    (ROOT / "generated/language-matrix-check.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
