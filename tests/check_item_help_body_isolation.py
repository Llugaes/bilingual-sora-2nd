"""Offline P0 Tools refusal/authority guard; generated r25/P0 resource fixtures required.

The complete-authority annotation translate discrepancy is pre-existing and kept
separate from whole-conflict rejection and Tools body-isolation parity.
"""

import pathlib, json, sys, copy

R = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R))
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.item_help_composition import build_item_help_grammar

game = pathlib.Path(r"D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
entries = [
    e
    for e in json.loads((R / "generated/r25-production/catalog.json").read_text(encoding="utf8"))[
        "entries"
    ]
    if e["key"].startswith("table/")
]
grammar = build_item_help_grammar(
    game, entries, "en", languages=("en", "ja", "zh-Hans", "zh-Hant", "ko", "fr", "de", "es")
)
entries += grammar["status_entries"] + grammar["detail_entries"]
c = next(
    r["contract"]
    for r in json.loads(
        (R / "generated/r26-tools-header-contracts.json").read_text(encoding="utf8")
    )
    if r["locale"] == "en"
)
tr = MenuTranslator(entries, "ja", "zh-Hans", "en", item_help_headers=c)
base = MenuTranslator(entries, "ja", "zh-Hans", "en")
rows = json.loads((R / "generated/r26-p0-python-body-isolation.json").read_text(encoding="utf8"))[
    "cases"
]
out = []
checks = 0
for row in rows:
    source = row["source"]
    head = source.split("\n")[0]
    inner = head[
        len(
            next(
                r["prefix"]
                for r in c["rows"]
                if r["body"] == "A capsule containing orbal energy. Fully restores EP."
            )
        ) : -len(c["rows"][0]["close"][0])
    ]
    for mode in ("primary", "secondary", "annotation"):
        plan = tr.render(source, mode)
        translated = tr.translate(source, mode)
        assert plan["text"] == translated
        assert plan["text"].startswith(head + "\n")
        checks += 1
        for bad in (head, head + "\nUnowned resource body"):
            assert tr.render(bad, mode) == {"text": bad, "layers": [], "kind": "plain"}
            assert tr.translate(bad, mode) == bad
            checks += 1
    authoritative = ("完全な優先翻訳", "完整优先译文")
    tr.pairs[source] = authoritative
    base.pairs[source] = authoritative
    for mode in ("primary", "secondary", "annotation"):
        assert tr.render(source, mode) == base.render(source, mode)
        assert tr.translate(source, mode) == base.translate(source, mode)
        if mode in ("primary", "secondary"):
            assert tr.translate(source, mode) == authoritative[0 if mode == "primary" else 1]
        checks += 1
    tr.ambiguous_display.add(source)
    for mode in ("primary", "secondary", "annotation"):
        assert tr.render(source, mode) == {"text": source, "layers": [], "kind": "plain"}
        assert tr.translate(source, mode) == source
        checks += 1
    tr.ambiguous_display.remove(source)
    del tr.pairs[source]
    del base.pairs[source]
    out.append(
        {
            "source": source,
            "unowned_headers_preserved": True,
            "complete_authority_render_respected": True,
            "whole_conflict_refused": True,
        }
    )
receipt = {
    "python_checks": checks,
    "body_refusal_render_translate_equal": True,
    "unowned_body_refused": True,
    "tools_does_not_change_complete_authority_baseline": True,
    "complete_authority_primary_secondary_and_render_respected": True,
    "whole_conflict_not_bypassed": True,
    "known_preexisting_limitation": "translate(annotation) can decompose a complete authority pair while render(annotation) uses it; unchanged with Tools contract disabled",
    "cases": out,
    "game_attached": False,
}
(
    pathlib.Path(sys.argv[1])
    if len(sys.argv) > 1
    else R / "generated/r26-p0-body-authority-python.json"
).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(receipt, ensure_ascii=False)[:500])
