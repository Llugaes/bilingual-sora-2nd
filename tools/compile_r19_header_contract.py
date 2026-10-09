"""Compile constructor-only metadata from the complete actual r18 catalogue."""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from sora_bilingual.localization.menu_text import MenuTranslator, skill_help_header_contract
from sora_bilingual.localization.item_help_composition import build_item_help_grammar

catalog = root / "dist/comprehensive-1.0.0-dev5-r18/DEV/generated/catalog.json"
entries = json.loads(catalog.read_text("utf-8"))["entries"]
contract = skill_help_header_contract(entries, "ja", "zh-Hans", "en")
(root / "generated/r19-skill-header-contract.json").write_text(
    json.dumps(contract, ensure_ascii=False, indent=2), "utf-8"
)
grammar = build_item_help_grammar(
    Path(r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter"),
    entries,
    "en",
    languages=("en", "ja", "zh-Hans"),
)
single = [
    e
    for e in grammar["detail_entries"]
    if e.get("item_help_contract", {}).get("family") == "chance_single"
]
role_entries = [
    e
    for e in entries
    if e.get("key", "").startswith(("table/t_itemhelp.tbl/", "table/t_text.tbl/TXT_ITEM_HELP_"))
]
tr = MenuTranslator(role_entries + single, "ja", "zh-Hans", "en")
sources = {e["texts"]["en"] for e in single}
delta = {
    "entries": single,
    "units": [r for r in tr.details.detail_effect_units if r["source"] in sources],
    "rejections": [r for r in tr.details.detail_effect_rejections if r["source"] in sources],
    "audit": grammar["audit"],
}
(root / "generated/r19-effect-contract-delta.json").write_text(
    json.dumps(delta, ensure_ascii=False, indent=2), "utf-8"
)
print(
    json.dumps(
        {
            "formats": len(contract["formats"]),
            "ranges": len(contract["ranges"]),
            "chance_single": len(single),
            "units": len(delta["units"]),
        }
    )
)
