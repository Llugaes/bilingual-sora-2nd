"""Independent full-body extension of the preserved 1256 physical recipe inputs.

Read actual indexed wires without compiling models. The Python adapter restores
the serialized MenuTranslator fields; JS independently uses the native loader.
Every new output is exclusive-create so previous red receipts remain intact.
"""

import argparse
from collections.abc import Mapping
import gc
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import traceback
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.menu_text import MenuTranslator, _format_fields, _format_pattern
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables

GAME = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter")
CONFIGS = (
    ("en", "en", "en", "zh-Hans"),
    ("ja", "ja", "ja", "zh-Hans"),
    ("zh-Hans", "zh-Hans", "zh-Hans", "ja"),
    ("zh-Hant", "zh-Hant", "zh-Hant", "ja"),
    ("en-manual", "en", "ja", "zh-Hans"),
)
MODES = ("primary", "secondary", "annotation")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text("utf8"))


def save_new(path, value):
    with Path(path).open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare_input(path, recipes_path=None):
    recipes_path = recipes_path or ROOT / "generated/r32-recipes-step5-four.json"
    capture_path = ROOT / "generated/r32-live004-ja-recipe-ham-inputs.json"
    red = ROOT / "generated/r32-live004-ja-recipe-ham-readonly.json"
    assert digest(red) == "5c99df46486b57fbca7ab8d966388c83daf6bb79047d47e16ce34e655f08d617"
    recipes = read_json(recipes_path)["cases"]
    source_locales = {c["locale"] for c in recipes}
    assert len(recipes) == 314 * len(source_locales) and len({c["item_id"] for c in recipes}) == 157
    assert all(sum(c["locale"] == locale for c in recipes) == 314 for locale in source_locales)
    if path.exists():
        old = read_json(path)
        assert old["original_recipe_sha256"] == digest(recipes_path)
        assert old["actual_capture_sha256"] == digest(capture_path)
        assert old["preserved_red_sha256"] == digest(red)
        return old
    wanted = {c["item_id"] for c in recipes}
    physical, provenance = {}, {}
    for locale, archive_name in _TABLE_ARCHIVES.items():
        with FpacArchive(GAME / "pac/steam" / archive_name) as archive:
            logical = _logical_tables(archive)
            data = archive.read(logical["table/t_item.tbl"])
        _, start, size, count = next(r for r in sections(data) if r[0] == "ItemTableData")
        rows = {}
        for ordinal in range(count):
            at = start + ordinal * size
            item_id = struct.unpack_from("<I", data, at)[0]
            if item_id not in wanted:
                continue

            def text(offset):
                pointer = struct.unpack_from("<Q", data, at + offset)[0]
                return data[pointer : data.index(b"\0", pointer)].decode("utf8")

            rows[item_id] = {
                "physical": ordinal,
                "name": text(224),
                "body": text(232),
                "category": data[at + 41],
                "slots": [
                    list(struct.unpack_from("<4I", data, at + 60 + slot * 16))
                    for slot in range(5)
                    if struct.unpack_from("<I", data, at + 60 + slot * 16)[0]
                ],
            }
        assert set(rows) == wanted
        physical[locale] = rows
        provenance[locale] = {
            "archive": archive_name,
            "logical_table": "table/t_item.tbl",
            "table_sha256": hashlib.sha256(data).hexdigest(),
            "selected_physical_rows": len(rows),
        }
    cases = []
    for case in recipes:
        assert "\n" not in case["source"]
        item_id, locale = case["item_id"], case["locale"]
        assert case["source"] == case["texts"][locale]
        cases.append(
            {
                "locale": locale,
                "item_id": item_id,
                "join": case["join"],
                "physical": physical[locale][item_id]["physical"],
                "category": physical[locale][item_id]["category"],
                "slots": physical[locale][item_id]["slots"],
                "original_source": case["source"],
                "source": case["source"] + "\n" + physical[locale][item_id]["body"],
                "texts": {
                    language: text + "\n" + physical[language][item_id]["body"]
                    for language, text in case["texts"].items()
                },
                "body_texts": {
                    language: rows[item_id]["body"] for language, rows in physical.items()
                },
            }
        )
    actual = next(
        row
        for row in read_json(capture_path)["rows"]
        if row.get("input_identity_diagnostic", {}).get("caller_rva") == 0x412808
        and "ハムと卵" in row["original"]
    )
    exact = next(
        c for c in cases if c["locale"] == "ja" and c["item_id"] == 2300 and c["join"] == " "
    )
    assert (
        actual["original"] == exact["source"]
        and len(actual["original"].encode("utf-16-le")) // 2 == 75
    )
    result = {
        "schema": 1,
        "original_recipe_path": str(recipes_path),
        "original_recipe_sha256": digest(recipes_path),
        "actual_capture_path": str(capture_path),
        "actual_capture_sha256": digest(capture_path),
        "preserved_red_path": str(red),
        "preserved_red_sha256": digest(red),
        "physical_sources": provenance,
        "original_case_count": len(cases),
        "cases": cases,
        "actual_ja_75_units": actual,
        "input_origin": "unchanged saved physical compact headers plus matching raw official ItemTableData whole body",
        "live_topology_observed": ["ja/2300/space-join"],
        "other_full_body_inputs": "constructor coverage extension, not claimed as captured live inputs",
    }
    save_new(path, result)
    return result


class WireObject(Mapping):
    def __init__(self, reader, count, at):
        self.reader, self.count, self.at = reader, count, at

    def __len__(self):
        return self.count

    def __iter__(self):
        for i in range(self.count):
            yield self.reader.node(struct.unpack_from("<I", self.reader.data, self.at + i * 8)[0])

    def __getitem__(self, key):
        if not isinstance(key, str):
            raise KeyError(key)
        value = 2166136261
        for (unit,) in struct.iter_unpack("<H", key.encode("utf-16-le", "surrogatepass")):
            value = ((value ^ unit) * 16777619) & 0xFFFFFFFF
        lo, hi = 0, self.count
        index_at = self.at + self.count * 8
        while lo < hi:
            mid = (lo + hi) // 2
            (hashed,) = struct.unpack_from("<I", self.reader.data, index_at + mid * 8)
            if hashed < value:
                lo = mid + 1
            else:
                hi = mid
        while lo < self.count:
            hashed, entry = struct.unpack_from("<II", self.reader.data, index_at + lo * 8)
            if hashed != value:
                break
            key_id, value_id = struct.unpack_from("<II", self.reader.data, self.at + entry * 8)
            if self.reader.node(key_id) == key:
                return self.reader.node(value_id)
            lo += 1
        raise KeyError(key)


class IndexedReader:
    def __init__(self, path):
        self.file = Path(path).open("rb")
        self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        magic, schema, self.count, root, self.table_at, self.data_at, length = struct.unpack_from(
            "<8s6I", self.data
        )
        assert magic == b"SORAMOD2" and schema == 2 and length == len(self.data)
        assert self.table_at == 32 and self.data_at == 32 + self.count * 16
        self.cache = {}
        self.model = self.node(root)

    def node(self, identifier):
        if identifier in self.cache:
            return self.cache[identifier]
        assert 0 <= identifier < self.count
        kind, count, offset, size = struct.unpack_from(
            "<4I", self.data, self.table_at + identifier * 16
        )
        at = self.data_at + offset
        assert at + size <= len(self.data)
        if kind == 0:
            value = None
        elif kind == 1:
            value = bool(count)
        elif kind == 2:
            value = struct.unpack_from("<d", self.data, at)[0]
        elif kind == 3:
            value = self.data[at : at + count * 2].decode("utf-16-le", "surrogatepass")
        elif kind == 4:
            value = [self.node(i) for i in struct.unpack_from(f"<{count}I", self.data, at)]
        elif kind == 5:
            value = WireObject(self, count, at)
        else:
            raise ValueError("unknown indexed node type")
        self.cache[identifier] = value
        return value

    def close(self):
        self.cache.clear()
        self.data.close()
        self.file.close()


def restore_python(model):
    """Restore original serialized rules; no compilation or guessed entries."""
    tr = MenuTranslator([], "primary", "secondary", "source", True)
    regex_rows = {
        "numeric",
        "raw_numeric",
        "detail_numeric",
        "detail_inline_icons",
        "producer_numeric",
    }
    regex_lists = {
        "detail_join_numeric",
        "detail_join_blocked_numeric",
        "detail_effect_blocked_numeric",
        "resource_formatter_patterns",
    }
    sets = {
        "ambiguous_display",
        "detail_sources",
        "detail_header_literals",
        "detail_join_literals",
        "detail_join_blocked_literals",
        "detail_effect_blocked_literals",
        "detail_effect_constructor_ids",
    }
    for name in model:
        if name in {"details", "scoped", "keyed"} or not hasattr(tr, name):
            continue
        value = model[name]
        if name in regex_rows:
            value = [(re.compile(row[0]), *row[1:]) for row in value]
        elif name in regex_lists:
            value = [re.compile(row) for row in value]
        elif name in sets:
            value = set(value)
        setattr(tr, name, value)
    tr.details = restore_python(model["details"]) if model.get("details") else None
    if tr.details:
        tr.details.frame_owner = tr
    tr._effect_rules = [(row, re.compile(row["pattern"])) for row in tr.detail_effect_units]
    tr._effect_parameter_guards = [
        (row, _format_pattern(row["source"], _format_fields(row["source"]), parameter_guard=True))
        for row in tr.detail_effect_units
        if any(kind in "diu" for kind in row.get("parameter_kinds", []))
    ]
    tr._effect_direction_guards = [re.compile(p) for p in tr.detail_effect_direction_guards]
    return tr


def primary_text(text):
    return re.sub(r"<R>(.*?)</R[^<>]*>", r"\1", text, flags=re.S)


def secondary_text(plan):
    if not plan["layers"]:
        return re.sub(
            r"<R>(.*?)</R([^<>]*)>", lambda m: m[2] if m[1] else "", plan["text"], flags=re.S
        )
    value, at = plan["text"], 0
    for layer in plan["layers"]:
        anchor = value.find("<R></R_>", at)
        if anchor < 0 or not value.startswith(layer["primary"], anchor + 8):
            raise AssertionError("layer anchor/primary mismatch")
        value = value[:anchor] + layer["text"] + value[anchor + 8 + len(layer["primary"]) :]
        at = anchor + len(layer["text"])
    return primary_text(value)


def semantics(text):
    parts = re.split(r"(\r\n|\n|\\n)", unicodedata.normalize("NFKC", text))
    parts[0] = re.sub(r"\s+-\s+", "", parts[0])
    parts[0] = re.sub(r"[\[\]()【】:：/・･、]", "", parts[0])
    return re.sub(r"\s", "", re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", "".join(parts)))


def verify_plan(source, plan, mode, expected):
    primary = primary_text(plan["text"])
    secondary = secondary_text(plan) if mode == "annotation" else None
    pairs = [(primary, expected["secondary"] if mode == "secondary" else expected["primary"])]
    if secondary is not None:
        pairs.append((secondary, expected["secondary"]))
    strict = all(a == b for a, b in pairs)
    semantic = all(semantics(a) == semantics(b) for a, b in pairs)
    return {
        "strict_equal": strict,
        "complete_semantics_equal": semantic,
        "classification": "exact"
        if strict
        else "retained_native_frame"
        if semantic
        else "semantic_or_field_mismatch",
        "actual_primary": primary,
        "actual_secondary": secondary,
        "expected_primary": expected["primary"],
        "expected_secondary": expected["secondary"],
    }


def select_wire(args, label, config):
    if args.product:
        cache_path = args.product / "candidate-cache.json"
        (selected,) = [r for r in read_json(cache_path)["config_matrix"] if r["config"] == config]
        return (
            args.product / "generated" / selected["wire_name"],
            selected["wire_sha256"],
            str(cache_path),
        )
    receipt_path = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
    receipt = read_json(receipt_path)
    assert receipt["config"] == config
    return Path(receipt["wire_path"]), receipt["wire_sha256"], str(receipt_path)


def node_only(args, fixture):
    output = ROOT / f"generated/{args.run_tag}-recipe-full-body-node-summary.json"
    assert not output.exists(), "never overwrite previous evidence"
    freeze_path = ROOT / "generated/r32-coverage-source-freeze.json"
    freeze = read_json(freeze_path)
    script_path = args.runtime_root / "sora_bilingual/game/scripts/runtime_text.js"
    script_sha = digest(script_path)
    if not args.product:
        assert script_sha == freeze["files"]["sora_bilingual/game/scripts/runtime_text.js"]
    summary = {
        "schema": 1,
        "run_tag": args.run_tag,
        "source_snapshot_sha256": freeze["snapshot_sha256"],
        "runtime_text_sha256": script_sha,
        "runtime_root": str(args.runtime_root),
        "input_path": str(args.input),
        "input_sha256": digest(args.input),
        "preserved_red_sha256": fixture["preserved_red_sha256"],
        "runs": [],
        "production_compiled": False,
        "build_run": False,
        "game_attached": False,
        "checker_python_sha256": digest(__file__),
        "checker_js_sha256": digest(ROOT / "tests/check_r32_recipe_full_body.js"),
    }
    for label, source, primary, secondary in CONFIGS:
        if label not in args.labels:
            continue
        config = {
            "primary": primary,
            "secondary": secondary,
            "game_language": source,
            "experimental_primary": label == "en-manual",
            "scope": "all",
            "sources": [],
        }
        wire, wire_sha, provenance = select_wire(args, label, config)
        receipt = read_json(provenance) if not args.product else None
        if receipt:
            assert receipt["source_snapshot_sha256"] == freeze["snapshot_sha256"]
            assert digest(receipt["model_path"]) == receipt["model_sha256"]
        destination = ROOT / f"generated/{args.run_tag}-recipe-full-body-node-{label}.json"
        command = [
            shutil.which("node"),
            str(ROOT / "tests/check_r32_recipe_full_body.js"),
            "--input",
            str(args.input),
            "--wire",
            str(wire),
            "--wire-sha256",
            wire_sha,
            "--runtime-root",
            str(args.runtime_root),
            "--label",
            label,
            "--output",
            str(destination),
        ]
        if args.callbacks and label == "ja":
            command.append("--callbacks")
        if args.focus_item_ids:
            command.extend(["--only-item-ids", ",".join(map(str, args.focus_item_ids))])
        result = subprocess.run(
            command,
            cwd=ROOT,
            encoding="utf8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log = ROOT / f"generated/{args.run_tag}-recipe-full-body-node-{label}.log"
        with log.open("x", encoding="utf8") as stream:
            stream.write(result.stdout)
        actual = read_json(destination) if destination.exists() else None
        record = {
            "label": label,
            "config": config,
            "wire_path": str(wire),
            "wire_sha256": wire_sha,
            "provenance_path": provenance,
            "provenance_sha256": digest(provenance),
            "production_model_sha256": receipt["model_sha256"] if receipt else None,
            "receipt_source_snapshot_sha256": receipt["source_snapshot_sha256"]
            if receipt
            else None,
            "command": command,
            "exit_code": result.returncode,
            "output": str(destination),
            "output_sha256": digest(destination) if actual else None,
            "log": str(log),
            "counts": {
                k: actual.get(k, 0)
                for k in (
                    "mode_plan_count",
                    "strict_failure_count",
                    "semantic_failure_count",
                    "normal_primary_source_failure_count",
                    "negative_failure_count",
                    "body_proof_negative_failure_count",
                    "callback_failure_count",
                )
            }
            if actual
            else None,
            "callback_mode_plans": len(actual.get("callback_checks", [])) if actual else 0,
        }
        summary["runs"].append(record)
        print(json.dumps(record), flush=True)
    summary["failure_count"] = sum(
        (
            r["counts"]["semantic_failure_count"]
            + r["counts"]["negative_failure_count"]
            + r["counts"]["normal_primary_source_failure_count"]
            + r["counts"]["body_proof_negative_failure_count"]
            + r["counts"]["callback_failure_count"]
            if r["counts"]
            else 1
        )
        for r in summary["runs"]
    )
    summary["complete_mode_plans"] = sum(
        r["counts"]["mode_plan_count"] for r in summary["runs"] if r["counts"]
    )
    summary["strict_failure_count"] = sum(
        r["counts"]["strict_failure_count"] for r in summary["runs"] if r["counts"]
    )
    assert digest(script_path) == script_sha
    save_new(output, summary)
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": digest(output),
                "mode_plans": summary["complete_mode_plans"],
                "strict_failure_count": summary["strict_failure_count"],
                "failure_count": summary["failure_count"],
            }
        )
    )
    return bool(summary["failure_count"])


RECIPE_V8 = r"""
rpc.exports={
 load(model){globalThis.tr=new RuntimeText(model);return{runtime:Script.runtime,retiredIdentityEmitted:!!model.item_help_identities};},
 recipereplay(rows){let positive=0,negative=0;const failures=[],plans=[];
  for(const row of rows){const conflict=row.kind==='whole_conflict_runtime_guard';
   if(conflict){tr.ambiguousDisplay.add(row.source);tr.planCache.clear();}
   for(const mode of ['primary','secondary','annotation']){const actual=tr.render(row.source,mode),expected=row.modes[mode];
    if(row.category==='positive')positive++;else negative++;
    if(JSON.stringify(actual)!==JSON.stringify(expected))failures.push({name:row.name,source:row.source,mode,expected,actual});
    plans.push({name:row.name,category:row.category,mode,actual});}
   if(conflict){tr.ambiguousDisplay.delete(row.source);tr.planCache.clear();}
  }
  return{positive,negative,failures,plans};
 }
};
"""


def packaged_v8(args, fixture):
    """Bounded actual-package replay; no warm/ZIP/source-audit repetition."""
    assert args.product and args.audit and args.oracle
    namespace = args.run_tag if args.run_tag.startswith("r32-") else "r32-" + args.run_tag
    output = ROOT / f"generated/{namespace}-recipe-full-body-packaged-v8.json"
    assert not output.exists(), "never overwrite previous V8 evidence"
    product = args.product.resolve()
    freeze = read_json(args.freeze)
    audit, oracle = read_json(args.audit), read_json(args.oracle)
    cache_path = product / "candidate-cache.json"
    cache = read_json(cache_path)
    snapshot = freeze["snapshot_sha256"]
    assert (
        snapshot
        == audit["source_snapshot_sha256"]
        == oracle["source_snapshot_sha256"]
        == cache["source_snapshot_sha256"]
    )
    assert audit["native_agent_matches_frozen_bytes"] and audit["warm_entry_without_cold_compile"]
    assert (
        audit["wire_bytes_and_mtime_unchanged"]
        and not audit["actual_attach_called"]
        and not audit["game_attached"]
    )
    assert oracle["complete_mode_plans"] == 4710
    names = (
        "runtime_text.js",
        "native_transport.js",
        "native_agent.js",
        "runtime_paragraph.js",
        "runtime_identity.js",
    )
    scripts = {name: digest(product / "sora_bilingual/game/scripts" / name) for name in names}
    assert all(
        value == freeze["files"]["sora_bilingual/game/scripts/" + name]
        for name, value in scripts.items()
    )
    assert cache["renderer_sha256"] == scripts["runtime_text.js"] == oracle["runtime_text_sha256"]
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(args.temp_dir.resolve())
    import frida

    report = {
        "schema": 1,
        "kind": "actual_package_recipe_full_body_frida_v8",
        "source_snapshot_sha256": snapshot,
        "product_root": str(product),
        "package_archive_sha256_from_root_audit": audit["package_sha256"],
        "root_audit_path": str(args.audit),
        "root_audit_sha256": digest(args.audit),
        "oracle_path": str(args.oracle),
        "oracle_sha256": digest(args.oracle),
        "input_path": str(args.input),
        "input_sha256": digest(args.input),
        "preserved_red_sha256": fixture["preserved_red_sha256"],
        "package_js_sha256_before": scripts,
        "candidate_cache_sha256_before": digest(cache_path),
        "process_level_TMP_TEMP": str(args.temp_dir.resolve()),
        "complete_positive_mode_plans": 0,
        "negative_mode_plans": 0,
        "parity_failures": [],
        "records": [],
        "complete": False,
        "full_gate_failure_count_retained": oracle["failure_count"],
        "positive_semantic_failure_count_retained": sum(
            r["counts"]["semantic_failure_count"] for r in oracle["runs"]
        ),
        "strict_refusal_failure_count_retained": sum(
            r["counts"]["negative_failure_count"] for r in oracle["runs"]
        ),
        "strict_full_gate_failure_count_retained": oracle["strict_failure_count"],
        "game_attached": False,
        "build_run": False,
        "production_compiled": False,
        "host_kind": "self-created hidden Python, actual Frida V8, never game",
        "selection": "all original complete physical recipe cases"
        if args.all_positive
        else "first three original full-body fixtures, exact ham space-join, first attack, both conflicting-description items and actual ALL recovery Mom",
        "checker_sha256": digest(__file__),
    }
    for node_record in oracle["runs"]:
        label, config = node_record["label"], node_record["config"]
        if label not in args.labels:
            continue
        (selected,) = [r for r in cache["config_matrix"] if r["config"] == config]
        receipt_path = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
        receipt = read_json(receipt_path)
        assert receipt["config"] == config and receipt["source_snapshot_sha256"] == snapshot
        wire, model = (
            product / "generated" / selected["wire_name"],
            product / "generated" / selected["model_name"],
        )
        assert wire.resolve().is_relative_to(
            product / "generated"
        ) and model.resolve().is_relative_to(product / "generated")
        assert (
            digest(wire)
            == selected["wire_sha256"]
            == receipt["wire_sha256"]
            == node_record["wire_sha256"]
        )
        assert digest(model) == receipt["model_sha256"] == node_record["production_model_sha256"]
        assert cache["files"]["generated/" + wire.name] == receipt["wire_sha256"]
        assert cache["files"]["generated/" + model.name] == receipt["model_sha256"]
        node_path = Path(node_record["output"])
        assert digest(node_path) == node_record["output_sha256"]
        node = read_json(node_path)
        assert node["script_sha256"]["runtime_text"] == scripts["runtime_text.js"]
        picked = list(node["cases"]) if args.all_positive else node["cases"][:3]
        if not args.all_positive:
            for item_id in (2300, 2116, 2160, 2316):
                picked.append(
                    next(c for c in node["cases"] if c["item_id"] == item_id and c["join"] == " ")
                )
            attack = next(
                c
                for c in fixture["cases"]
                if c["locale"] == config["game_language"] and c["category"] == 32
            )
            picked.append(next(c for c in node["cases"] if c["source"] == attack["source"]))
        cases, seen = [], set()
        for row in picked:
            # Full physical coverage includes identical complete strings from
            # the two original join cases; preserve that original denominator.
            if not args.all_positive and row["source"] in seen:
                continue
            seen.add(row["source"])
            cases.append(
                {
                    "name": f"{label}/{row['item_id']}/{row['join']!r}",
                    "category": "positive",
                    "source": row["source"],
                    "modes": {mode: row["modes"][mode]["plan"] for mode in MODES},
                    "oracle_comparisons": {
                        mode: row["modes"][mode]["comparison"] for mode in MODES
                    },
                }
            )
        if args.all_positive:
            assert len(cases) == len(node["cases"]) == 314
        for kind in sorted({r["kind"] for r in node["negative_cases"]}):
            rows = [r for r in node["negative_cases"] if r["kind"] == kind]
            assert len(rows) == 3 and len({r["source"] for r in rows}) == 1
            cases.append(
                {
                    "name": label + "/" + kind,
                    "category": "negative",
                    "kind": kind,
                    "source": rows[0]["source"],
                    "modes": {r["mode"]: r["actual"] for r in rows},
                    "original_strict_refusal_failures_retained": sum(
                        not r["header_remains_exact"] for r in rows
                    ),
                }
            )
        for kind in sorted({r["kind"] for r in node.get("body_proof_negative_cases", [])}):
            rows = [r for r in node["body_proof_negative_cases"] if r["kind"] == kind]
            assert len(rows) == 3
            cases.append(
                {
                    "name": label + "/" + kind,
                    "category": "negative",
                    "kind": kind,
                    "source": rows[0]["source"],
                    "modes": {r["mode"]: r["actual"] for r in rows},
                    "original_strict_refusal_failures_retained": sum(
                        not r["ambiguous_body_remains_exact"] for r in rows
                    ),
                }
            )
        before = wire.stat()
        record = {
            "label": label,
            "config": config,
            "wire_path": str(wire),
            "wire_sha256": receipt["wire_sha256"],
            "model_path": str(model),
            "model_sha256": receipt["model_sha256"],
            "matrix_wire_name": selected["wire_name"],
            "wire_mtime_ns_before": before.st_mtime_ns,
            "cases": cases,
            "phase": "host_create",
            "passed": False,
        }
        host, session = None, None
        try:
            host = subprocess.Popen(
                [sys.executable, "-c", "import sys;sys.stdin.buffer.read()"],
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            record["host_pid"] = host.pid
            record["phase"] = "frida_attach_owned_host"
            session = frida.attach(host.pid)
            record["phase"] = "script_create_v8"
            script = session.create_script(
                (product / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf8")
                + RECIPE_V8
                + (product / "sora_bilingual/game/scripts/native_transport.js").read_text("utf8"),
                runtime="v8",
            )
            script.load()
            loaded = script.exports_sync.modelpackedfile(str(wire))
            assert loaded == {"runtime": "V8", "retiredIdentityEmitted": False}
            record["phase"] = "replay_complete_plans"
            actual = script.exports_sync.recipereplay(cases)
            record["actual_v8"] = actual
            report["complete_positive_mode_plans"] += actual["positive"]
            report["negative_mode_plans"] += actual["negative"]
            report["parity_failures"].extend(actual["failures"])
            record["passed"] = not actual["failures"]
            record["phase"] = "complete"
        except Exception:
            record["exception"] = traceback.format_exc()
            report["parity_failures"].append(
                {"label": label, "phase": record["phase"], "exception": record["exception"]}
            )
        finally:
            if session is not None:
                session.detach()
            if host is not None:
                host.stdin.close()
                host.wait(timeout=5)
        after = wire.stat()
        record["wire_size_mtime_unchanged"] = (before.st_size, before.st_mtime_ns) == (
            after.st_size,
            after.st_mtime_ns,
        )
        assert record["wire_size_mtime_unchanged"]
        report["records"].append(record)
        print(
            json.dumps({k: record[k] for k in ("label", "wire_sha256", "phase", "passed")}),
            flush=True,
        )
        if not record["passed"]:
            break
    report["package_js_sha256_after"] = {
        name: digest(product / "sora_bilingual/game/scripts" / name) for name in names
    }
    assert (
        report["package_js_sha256_after"] == scripts
        and digest(cache_path) == report["candidate_cache_sha256_before"]
    )
    report["complete"] = (
        len(report["records"]) == len(args.labels) and not report["parity_failures"]
    )
    report["parity_failure_count"] = len(report["parity_failures"])
    save_new(output, report)
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": digest(output),
                "complete": report["complete"],
                "positive_plans": report["complete_positive_mode_plans"],
                "negative_plans": report["negative_mode_plans"],
                "parity_failure_count": report["parity_failure_count"],
            }
        )
    )
    return not report["complete"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "generated/r32-recipe-full-body-input.json"
    )
    parser.add_argument("--recipes", type=Path)
    parser.add_argument("--product", type=Path)
    parser.add_argument("--runtime-root", type=Path, default=ROOT)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--labels", nargs="+", default=[c[0] for c in CONFIGS])
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--node-only", action="store_true")
    parser.add_argument("--callbacks", action="store_true")
    parser.add_argument("--packaged-v8", action="store_true")
    parser.add_argument(
        "--all-positive",
        action="store_true",
        help="Replay every complete physical recipe in packaged V8",
    )
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "generated/r32-coverage-source-freeze.json"
    )
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--oracle", type=Path)
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=ROOT / "generated/r32-recipe-v8-tmp",
    )
    parser.add_argument("--focus-item-ids", type=int, nargs="+")
    args = parser.parse_args()
    fixture = prepare_input(args.input, args.recipes)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "input": str(args.input),
                    "sha256": digest(args.input),
                    "cases": len(fixture["cases"]),
                }
            )
        )
        return 0
    if args.node_only:
        return node_only(args, fixture)
    if args.packaged_v8:
        return packaged_v8(args, fixture)
    output = ROOT / f"generated/{args.run_tag}-recipe-full-body-summary.json"
    assert not output.exists(), "never overwrite previous evidence"
    python_path = ROOT / "sora_bilingual/localization/menu_text.py"
    python_sha = digest(python_path)
    summary = {
        "schema": 1,
        "run_tag": args.run_tag,
        "input_path": str(args.input),
        "input_sha256": digest(args.input),
        "python_code_sha256": python_sha,
        "runtime_root": str(args.runtime_root),
        "wire_product": str(args.product) if args.product else None,
        "mixed_code_and_model": bool(
            args.product and args.runtime_root.resolve() != args.product.resolve()
        ),
        "preserved_red_sha256": fixture["preserved_red_sha256"],
        "runs": [],
        "production_compiled": False,
        "build_run": False,
        "game_attached": False,
        "normalization": [
            "strict failures retained unchanged",
            "NFKC and remove layout whitespace",
            "remove only color/size controls",
            "first line only: remove known native []()【】colon/slash/middle-dot/comma and space-hyphen-space frames",
            "retain all words/numbers/icons in original order and all body punctuation",
        ],
    }
    for label, source_locale, primary, secondary in CONFIGS:
        if label not in args.labels:
            continue
        config = {
            "primary": primary,
            "secondary": secondary,
            "game_language": source_locale,
            "experimental_primary": label == "en-manual",
            "scope": "all",
            "sources": [],
        }
        wire, wanted_sha, provenance = select_wire(args, label, config)
        before = wire.stat().st_mtime_ns
        assert digest(wire) == wanted_sha
        reader = IndexedReader(wire)
        tr = restore_python(reader.model)
        run = {
            "label": label,
            "config": config,
            "wire_path": str(wire),
            "wire_sha256": wanted_sha,
            "wire_provenance": provenance,
            "python_code_sha256": python_sha,
            "cases": [],
            "failures": [],
            "strict_failure_count": 0,
            "semantic_failure_count": 0,
            "mode_plan_count": 0,
            "normal_primary_source_failure_count": 0,
            "negative_cases": [],
        }
        selected = [c for c in fixture["cases"] if c["locale"] == source_locale]
        assert len(selected) == 314
        run["original_source_case_denominator"] = len(selected)
        if args.focus_item_ids:
            selected = [c for c in selected if c["item_id"] in args.focus_item_ids]
        run["selected_source_case_denominator"] = len(selected)
        run["focus_item_ids"] = args.focus_item_ids
        for case in selected:
            expected = {"primary": case["texts"][primary], "secondary": case["texts"][secondary]}
            record = {
                "item_id": case["item_id"],
                "join": case["join"],
                "source": case["source"],
                "modes": {},
            }
            for mode in MODES:
                plan = tr.render(case["source"], mode)
                checked = verify_plan(case["source"], plan, mode, expected)
                record["modes"][mode] = {"plan": plan, "comparison": checked}
                run["mode_plan_count"] += 1
                run["strict_failure_count"] += not checked["strict_equal"]
                run["semantic_failure_count"] += not checked["complete_semantics_equal"]
                if label != "en-manual" and mode in ("primary", "annotation"):
                    run["normal_primary_source_failure_count"] += (
                        primary_text(plan["text"]) != case["source"]
                    )
                if not checked["strict_equal"]:
                    run["failures"].append(
                        {
                            "item_id": case["item_id"],
                            "join": case["join"],
                            "source": case["source"],
                            "mode": mode,
                            "actual": plan,
                            **checked,
                        }
                    )
            run["cases"].append(record)
        seed = next(
            c
            for c in fixture["cases"]
            if c["locale"] == source_locale and c["item_id"] == 2300 and c["join"] == " "
        )
        head, body = seed["source"].split("\n", 1)
        negatives = [
            ("unknown_body", head + "\n" + body + " R32_UNKNOWN_BODY"),
            ("unknown_header_control", head.replace("<C9>", "<X998><C9>", 1) + "\n" + body),
            ("wrong_prefix", "R32_WRONG_PREFIX" + head + "\n" + body),
        ]
        for kind, source in negatives:
            for mode in MODES:
                plan = tr.render(source, mode)
                secondary_value = secondary_text(plan) if mode == "annotation" else plan["text"]
                passed = secondary_value.split("\n", 1)[0] == source.split("\n", 1)[0]
                run["negative_cases"].append(
                    {
                        "kind": kind,
                        "mode": mode,
                        "source": source,
                        "actual": plan,
                        "header_remains_exact": passed,
                        "body_translation_permitted_only_if_whole_official_body": kind
                        != "unknown_body",
                    }
                )
        run["body_proof_negative_cases"] = []
        if source_locale in ("zh-Hans", "zh-Hant"):
            ambiguous = next(
                c
                for c in fixture["cases"]
                if c["locale"] == source_locale and c["item_id"] == 2116 and c["join"] == " "
            )
            a_head, a_body = ambiguous["source"].split("\n", 1)
            opening = a_head[: a_head.index("<C9>")]
            inner = a_head[len(opening) : -1]
            members = tr.details.effect_units(inner, False, a_body, [" "] * 3)
            units = [u["source"] for u in members if not u.get("separator")]
            assert len(units) == 2
            mutations = [
                ("body_proof_wrong_amount", a_head.replace("150", "151", 1)),
                ("body_proof_reordered_effects", opening + " ".join(reversed(units)) + a_head[-1]),
                ("body_proof_extra_known_effect", opening + inner + " " + units[0] + a_head[-1]),
            ]
            for kind, mutated in mutations:
                source = mutated + "\n" + a_body
                for mode in MODES:
                    plan = tr.render(source, mode)
                    value = secondary_text(plan) if mode == "annotation" else plan["text"]
                    run["body_proof_negative_cases"].append(
                        {
                            "kind": kind,
                            "mode": mode,
                            "source": source,
                            "actual": plan,
                            "ambiguous_official_body": a_body,
                            "physical_constructor_is_not_claimed": True,
                            "ambiguous_body_remains_exact": value.split("\n", 1)[1] == a_body,
                        }
                    )
        run["body_proof_negative_failure_count"] = sum(
            not c["ambiguous_body_remains_exact"] for c in run["body_proof_negative_cases"]
        )
        tr.ambiguous_display.add(seed["source"])
        for mode in MODES:
            plan = tr.render(seed["source"], mode)
            run["negative_cases"].append(
                {
                    "kind": "whole_conflict_runtime_guard",
                    "mode": mode,
                    "source": seed["source"],
                    "actual": plan,
                    "header_remains_exact": plan["text"] == seed["source"] and not plan["layers"],
                    "guard_fixture": "test-only ambiguous display set; actual wire bytes unchanged",
                }
            )
        run["negative_failure_count"] = sum(
            not c["header_remains_exact"] for c in run["negative_cases"]
        )
        run["wire_mtime_unchanged"] = before == wire.stat().st_mtime_ns
        python_output = ROOT / f"generated/{args.run_tag}-recipe-full-body-python-{label}.json"
        save_new(python_output, run)
        del tr, run
        reader.close()
        del reader
        gc.collect()
        node_output = ROOT / f"generated/{args.run_tag}-recipe-full-body-node-{label}.json"
        command = [
            shutil.which("node"),
            str(ROOT / "tests/check_r32_recipe_full_body.js"),
            "--input",
            str(args.input),
            "--wire",
            str(wire),
            "--wire-sha256",
            wanted_sha,
            "--runtime-root",
            str(args.runtime_root),
            "--label",
            label,
            "--output",
            str(node_output),
        ]
        if args.focus_item_ids:
            command.extend(["--only-item-ids", ",".join(map(str, args.focus_item_ids))])
        node = subprocess.run(
            command,
            cwd=ROOT,
            encoding="utf8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        log = ROOT / f"generated/{args.run_tag}-recipe-full-body-node-{label}.log"
        with log.open("x", encoding="utf8") as stream:
            stream.write(node.stdout)
        py = read_json(python_output)
        js = read_json(node_output) if node_output.exists() else None
        item = {
            "label": label,
            "wire_sha256": wanted_sha,
            "python_output": str(python_output),
            "python_output_sha256": digest(python_output),
            "node_output": str(node_output),
            "node_output_sha256": digest(node_output) if js else None,
            "node_command": command,
            "node_exit_code": node.returncode,
            "node_log": str(log),
            "python_counts": {
                k: py[k]
                for k in (
                    "mode_plan_count",
                    "strict_failure_count",
                    "semantic_failure_count",
                    "normal_primary_source_failure_count",
                    "negative_failure_count",
                    "body_proof_negative_failure_count",
                )
            },
            "node_counts": {
                k: js[k]
                for k in (
                    "mode_plan_count",
                    "strict_failure_count",
                    "semantic_failure_count",
                    "normal_primary_source_failure_count",
                    "negative_failure_count",
                    "body_proof_negative_failure_count",
                )
            }
            if js
            else None,
        }
        summary["runs"].append(item)
        print(json.dumps(item), flush=True)
    assert digest(python_path) == python_sha, "production Python changed during check"
    summary["python_code_unchanged"] = True
    summary["failure_count"] = sum(
        r["python_counts"]["semantic_failure_count"]
        + r["python_counts"]["negative_failure_count"]
        + r["python_counts"]["body_proof_negative_failure_count"]
        + (
            r["node_counts"]["semantic_failure_count"]
            + r["node_counts"]["negative_failure_count"]
            + r["node_counts"]["body_proof_negative_failure_count"]
            if r["node_counts"]
            else 1
        )
        for r in summary["runs"]
    )
    save_new(output, summary)
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": digest(output),
                "failure_count": summary["failure_count"],
            }
        )
    )
    return bool(summary["failure_count"])


if __name__ == "__main__":
    raise SystemExit(main())
