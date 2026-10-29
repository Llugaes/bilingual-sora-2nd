"""Search undeclared table pointer fields, including ASCII-only strings.

This is a second raw-resource search, not a screen-coverage assertion. It
reports every candidate and refuses newly different fields without a reason.
The independent CJK-candidate report supplies typed/native evidence.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
import unicodedata

from sora_bilingual.config.locales import archive_names
from sora_bilingual.localization.menu_tables import SCHEMAS, schema_for, sections
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables


RESOURCE_SELECTORS = {
    ("BooksText", 16),
    ("HelpPage", 8),
    ("HelpIconList", 48),
}


def scan(game):
    fields = defaultdict(dict)
    for locale, filename in archive_names("table").items():
        with FpacArchive(game / "pac/steam" / filename) as archive:
            for path, physical in _logical_tables(archive).items():
                data = archive.read(physical)
                records = sections(data)
                floor = max([8 + 80 * len(records)] + [s + z * n for _, s, z, n in records])
                occurrences = Counter()
                for kind, start, size, count in records:
                    occurrence = occurrences[kind]
                    occurrences[kind] += 1
                    emitted = (
                        {o for _, o in schema_for(path, kind).fields} if kind in SCHEMAS else set()
                    )
                    if kind == "TextTableData":
                        emitted |= {0, 8}
                    for offset in range(0, size - 7, 8):
                        if offset in emitted:
                            continue
                        values = []
                        for row in range(count):
                            pointer = struct.unpack_from("<Q", data, start + size * row + offset)[0]
                            value = None
                            if floor <= pointer < len(data) and (
                                pointer == floor or data[pointer - 1] == 0
                            ):
                                end = data.find(b"\0", pointer)
                                if pointer <= end <= pointer + 10000:
                                    try:
                                        text = data[pointer:end].decode("utf-8")
                                        if all(ord(c) >= 32 or c in "\r\n\t" for c in text):
                                            value = text
                                    except UnicodeDecodeError:
                                        pass
                            values.append(value)
                        if any(values):
                            fields[path, kind, occurrence, offset][locale] = values
    return fields


def classify(fields, candidate_report):
    reasons = {
        (r["path"], r["kind"], r["offset"]): r["reason"] for r in candidate_report["classified"]
    }
    rows, unresolved = [], []
    for key, locales in sorted(fields.items()):
        path, kind, occurrence, offset = key
        different = len({json.dumps(v, ensure_ascii=False) for v in locales.values()}) > 1
        reason = reasons.get((path, kind, offset))
        if different and reason is None and (kind, offset) in RESOURCE_SELECTORS:
            reason = "declared_non_display_resource_selector"
        if different and reason is None and (kind, offset) == ("SkillParam", 160):
            if all(
                unicodedata.normalize("NFKC", v or "") in ("", "0", "---")
                for values in locales.values()
                for v in values
            ):
                reason = "numeric_or_dash_placeholder_only"
        row = {
            "path": path,
            "kind": kind,
            "occurrence": occurrence,
            "offset": offset,
            "locales": list(locales),
            "different": different,
            "reason": reason,
            "rows": {locale: len(values) for locale, values in locales.items()},
            "samples": {locale: [v for v in values if v][:3] for locale, values in locales.items()},
        }
        rows.append(row)
        if different and reason is None:
            unresolved.append(row)
    return {
        "scope": "undeclared aligned 64-bit pointer leads, including ASCII; not runtime reachability",
        "candidate_groups": len(rows),
        "different_groups": sum(r["different"] for r in rows),
        "unresolved_different_fields": unresolved,
        "fields": rows,
        "passed": not unresolved and candidate_report["all_classified"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(scan(args.game), json.loads(args.candidate_report.read_bytes()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "fields"}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
