"""Audit a local catalog against every prepared font without touching the game."""

import argparse
import json
from pathlib import Path
import re
import unicodedata

from sora_bilingual.fonts.font_delivery import _candidate_manifest
from sora_bilingual.fonts.font_merge import parse_fnt


def audit(catalog, candidate):
    manifest, files, manifest_sha = _candidate_manifest(candidate)
    supported = set.intersection(
        *(
            set(parse_fnt(data, atlas_height=65535).codepoints)
            for name, data in files.items()
            if name.endswith(".fnt")
        )
    )
    used = {}
    entries = json.loads(catalog.read_text("utf-8"))["entries"]
    for entry in entries:
        for language, source in entry.get("texts", {}).items():
            # Native ruby payloads contain visible glyphs inside closing tags.
            source = re.sub(r"</R([^<>]*)>", r"\1", source)
            source = re.sub(r"<[^<>]*>", "", source)
            used.setdefault(language, set()).update(
                ord(char)
                for char in source
                if not char.isspace() and not unicodedata.category(char).startswith("C")
            )
    return {
        "entries": len(entries),
        "glyphs": manifest["glyphs"],
        "manifest_sha256": manifest_sha,
        "languages": {
            language: {
                "used": len(chars),
                "missing": [f"U+{cp:04X}" for cp in sorted(chars - supported)],
            }
            for language, chars in sorted(used.items())
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.catalog, args.candidate)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", "utf-8")
    print(output)
    return int(any(row["missing"] for row in result["languages"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
