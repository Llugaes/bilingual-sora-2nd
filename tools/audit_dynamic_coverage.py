"""Join raw unassembled calls to compiled producers without discarding unknowns.

Compilation coverage is separate from final rendering and native reachability.
Inputs are private PAC-derived audit files; output contains identities, not text.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def audit(inventory, entries, source, target):
    index = defaultdict(list)
    for entry in entries:
        if source not in entry.get("texts", {}):
            continue
        producer = entry.get("dynamic_producer")
        origin = entry.get("producer_origin", {})
        if producer:
            signature = producer.get("signature") or origin.get("signature", {})
            if not {"path", "function", "called"} <= signature.keys():
                continue
            # Aligned physical ordinals take priority over reference-locale IDs.
            called = entry.get("called_ids", {}).get(source, signature["called"])
            key = f"{signature['path']}/{signature['function']}/called/{called}"
            family = producer["family"]
        elif entry.get("control_dialogue"):
            path, rest = entry["key"].split(".dat/", 1)
            called = entry.get("called_ids", {}).get(source)
            if called is None:
                continue
            key = f"{path}.dat/{rest.split('/')[0]}/called/{called}"
            family = "finite_control"
        else:
            continue
        index[key].append((family, entry["key"], bool(entry["texts"].get(target, "").strip())))
    rows = []
    for call in inventory["scripts"]["unassembled_text_calls"]:
        if call["language"] != source:
            continue
        compiled = index.get(call["key"], [])
        status = (
            "unclassified"
            if not compiled
            else "compiled_with_target_gap"
            if any(not row[2] for row in compiled)
            else "compiled_route"
        )
        rows.append(
            {
                "key": call["key"],
                "raw_reason": call["reason"],
                "status": status,
                "families": sorted({row[0] for row in compiled}),
                "records": sorted({row[1] for row in compiled}),
            }
        )
    counts = dict(Counter(row["status"] for row in rows))
    return {
        "scope": "raw unassembled-call compilation coverage; not runtime or final-render proof",
        "source": source,
        "target": target,
        "raw_call_denominator": len(rows),
        "counts": counts,
        "rows": rows,
        "all_classified": not counts.get("unclassified")
        and not counts.get("compiled_with_target_gap"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default="zh-Hans")
    parser.add_argument("--target", default="ja")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes())
    raw = args.catalog.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if inventory["catalog_sha256"] != digest:
        raise ValueError("Inventory and catalog differ; regenerate the raw inventory")
    report = audit(inventory, json.loads(raw)["entries"], args.source, args.target)
    report["catalog_sha256"] = digest
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}))


if __name__ == "__main__":
    main()
