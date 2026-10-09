"""Check every physical rod's whole bait list; no generic comma fallback."""

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator
from sora_bilingual.localization.notebook_composition import compile_fishing_lists
from sora_bilingual.localization.tables import _TABLE_ARCHIVES


def visible(value):
    return re.sub(r"<[^<>]*>", "", value)


def main():
    catalog = ROOT / "generated/r25-production/catalog.json"
    entries = [
        e for e in json.loads(catalog.read_text("utf8"))["entries"] if e["key"].startswith("table/")
    ]
    rods = compile_fishing_lists(
        Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter"),
        entries,
        tuple(_TABLE_ARCHIVES),
    )
    assert len(rods) == 7
    cases, failures, models = [], [], []
    for source in _TABLE_ARCHIVES:
        tr = MenuTranslator(entries + rods, "ja", "zh-Hans", source)
        models.append({"source": source, "model": tr.runtime_model()})
        for row in rods:
            value = row["texts"][source]
            plans = {
                mode: tr.render(value, mode) for mode in ("primary", "secondary", "annotation")
            }
            for mode, target in [("primary", "ja"), ("secondary", "zh-Hans"), ("annotation", "ja")]:
                if visible(plans[mode]["text"]) != row["texts"][target]:
                    failures.append(
                        {
                            "key": row["key"],
                            "source": source,
                            "mode": mode,
                            "actual": plans[mode],
                            "expected": row["texts"][target],
                        }
                    )
            cases.append(
                {
                    "key": row["key"],
                    "source": source,
                    "input": value,
                    "texts": row["texts"],
                    "plans": plans,
                }
            )
        # Changing an opaque control cannot create the same producer identity.
        corrupt = rods[0]["texts"][source] + "<Q>"
        if tr.render(corrupt, "secondary")["text"] != corrupt:
            failures.append(
                {
                    "source": source,
                    "negative": "unknown control",
                    "actual": tr.render(corrupt, "secondary"),
                }
            )
    result = {
        "checks": len(cases) * 3 + len(_TABLE_ARCHIVES),
        "physical_rods": 7,
        "source_languages": list(_TABLE_ARCHIVES),
        "failure_count": len(failures),
        "failures": failures,
        "cases": cases,
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "actual_game_capture": False,
        "input_origin": "CAB62 41B1A9 physical rod ordered slots; verified resource names",
    }
    (ROOT / "generated/r32-fishing-producers.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), "utf8"
    )
    (ROOT / "generated/r32-fishing-component-models.json").write_text(
        json.dumps(models, ensure_ascii=False), "utf8"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in ("failures", "cases")}
        )
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
