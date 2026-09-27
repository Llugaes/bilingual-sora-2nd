"""Combine independently validated script and table mappings from local files."""

import json
from pathlib import Path
from sora_bilingual.localization.resources import build_catalog
from sora_bilingual.localization.tables import build_table_entries
from sora_bilingual.localization.dynamic_producers import build_dynamic_entries


def build_all(game_dir, output_dir):
    output = Path(output_dir)
    script = build_catalog(game_dir, output / "scripts")
    tables, audit = build_table_entries(game_dir)
    dynamic, dynamic_audit = build_dynamic_entries(game_dir, script["entries"] + tables)
    result = {
        "version": 1,
        "languages": script["languages"],
        "entries": script["entries"] + tables + dynamic,
    }
    # Publish the combined catalogue only after both builders finish.
    temporary = output / "catalog.json.tmp"
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(output / "catalog.json")
    (output / "table-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "dynamic-audit.json").write_text(
        json.dumps(dynamic_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
