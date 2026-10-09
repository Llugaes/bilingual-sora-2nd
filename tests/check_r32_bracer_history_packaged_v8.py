"""Actual sealed package Bracer History scoped plans in owned hidden Frida V8 hosts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from check_r32_bracer_history_component import constructor, expected_plan, selected_ordinals, digest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_NAMES = (
    "runtime_text.js",
    "native_transport.js",
    "native_agent.js",
    "runtime_paragraph.js",
    "runtime_identity.js",
)
NATIVE = r"""
function historyCanonical(v){return Array.isArray(v)?v.map(historyCanonical):v&&typeof v==='object'
 ?Object.fromEntries(Object.keys(v).sort().map(k=>[k,historyCanonical(v[k])])):v;}
rpc.exports={
 load(model){globalThis.tr=new RuntimeText(model);return {runtime:Script.runtime,hasHistory:!!model.scoped?.bracer_history,
  retiredIdentityEmitted:!!model.item_help_identities};},
 historymetadata(){const s=tr.model.scoped?.bracer_history;return{bracer_history_frame:s?.bracer_history_frame??null,
  pairs_count:Object.keys(s?.pairs||{}).length,scope_json:JSON.stringify(historyCanonical(s??null)),
  pairs_json:JSON.stringify(historyCanonical(s?.pairs??null))};},
 historyrun(rows){let positive=0,refusal=0;const failures=[],plans=[];
  for(const row of rows)for(const mode of ['primary','secondary','annotation']){
   const actual=tr.render(row.source,mode,'','bracer_history'),expected=row.modes[mode];
   if(row.category==='positive')positive++;else refusal++;
   if(JSON.stringify(actual)!==JSON.stringify(expected))failures.push({name:row.name,category:row.category,mode,
    source:row.source,expected,actual});
   plans.push({name:row.name,category:row.category,mode,actual});
  }
  return{positive,refusal,failures,plans};
 }
};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument(
        "--freeze", type=Path, default=ROOT / "generated/r32-coverage-source-freeze.json"
    )
    parser.add_argument(
        "--audit", type=Path, default=ROOT / "generated/r32-local4-package-audit.json"
    )
    parser.add_argument(
        "--oracle",
        type=Path,
        default=ROOT / "generated/r32-bracer-history-component-full-wire-summary.json",
    )
    parser.add_argument(
        "--input", type=Path, default=ROOT / "generated/r32-bracer-history-component-input.json"
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=ROOT / "generated/r32-bracer-history-v8-tmp",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "generated/r32-local4-bracer-history-packaged-v8.json"
    )
    args = parser.parse_args()
    assert not args.output.exists(), "never overwrite a previous packaged V8 attempt"
    product = args.product.resolve()
    frozen = json.loads(args.freeze.read_text("utf8"))
    audit = json.loads(args.audit.read_text("utf8"))
    oracle = json.loads(args.oracle.read_text("utf8"))
    inputs = json.loads(args.input.read_text("utf8"))
    cache_path = product / "candidate-cache.json"
    cache = json.loads(cache_path.read_text("utf8"))
    snapshot = frozen["snapshot_sha256"]
    assert (
        snapshot
        == audit["source_snapshot_sha256"]
        == oracle["source_snapshot_sha256"]
        == inputs["source_snapshot_sha256"]
        == cache["source_snapshot_sha256"]
    )
    assert oracle["failure_count"] == 0 and oracle["complete_mode_plans"] == 15345
    # Root's audit is the prerequisite; this helper does not rerun ZIP/warm/full-source audit.
    code_count = sum(Path(name).suffix in (".py", ".js") for name in frozen["files"])
    assert audit["source_code_files_match_frozen_bytes"] == code_count
    assert audit["native_agent_matches_frozen_bytes"] is True
    assert audit["native_identity_and_contract_files_exact_r25"] is True
    assert (
        audit["warm_entry_without_cold_compile"] is True
        and audit["wire_bytes_and_mtime_unchanged"] is True
    )
    assert audit["actual_attach_called"] is False and audit["game_attached"] is False
    assert len(audit["warm_models"]) == len(cache["config_matrix"]) == len(oracle["records"]) == 5
    assert len(audit["package_sha256"]) == 64
    scripts_before = {
        name: digest(product / "sora_bilingual/game/scripts" / name) for name in SCRIPT_NAMES
    }
    for name, value in scripts_before.items():
        assert value == frozen["files"]["sora_bilingual/game/scripts/" + name]
    assert cache["renderer_sha256"] == scripts_before["runtime_text.js"]
    args.temp_dir.mkdir(parents=True, exist_ok=True)
    # Process-local only; set before importing Frida and inherit in our hidden hosts.
    os.environ["TMP"] = os.environ["TEMP"] = str(args.temp_dir.resolve())
    import frida

    rows, flags = inputs["physical_rows"], inputs["flags"]
    report = {
        "schema": 1,
        "kind": "actual_packaged_bracer_history_frida_v8",
        "source_snapshot_sha256": snapshot,
        "product_root": str(product),
        "package_archive_sha256_from_root_audit": audit["package_sha256"],
        "package_archive_rehashed": False,
        "root_package_audit_path": str(args.audit.resolve()),
        "root_package_audit_sha256": digest(args.audit),
        "root_package_audit_prerequisites_passed": True,
        "oracle_path": str(args.oracle.resolve()),
        "oracle_sha256": digest(args.oracle),
        "physical_input_path": str(args.input.resolve()),
        "physical_input_sha256": digest(args.input),
        "checker_sha256": digest(Path(__file__)),
        "freeze_sha256": digest(args.freeze),
        "candidate_cache_sha256_before": digest(cache_path),
        "package_js_sha256_before": scripts_before,
        "process_level_TMP_TEMP": str(args.temp_dir.resolve()),
        "serial_hidden_host_execution": True,
        "host_kind": "self-created hidden Python; actual Frida V8; never game",
        "game_attached": False,
        "build_run": False,
        "production_model_compiled": False,
        "whole_callback_matrix_repeated": False,
        "positive_constructors_per_configuration": [1, 512, 1023],
        "configuration_count": 5,
        "complete_positive_mode_plans": 0,
        "strict_refusal_mode_plans": 0,
        "failures": [],
        "records": [],
        "complete": False,
        "limits": [
            "This validates package data and actual embedded V8 plans, not game pixels or story reachability."
        ],
    }
    for node_record in oracle["records"]:
        label, config = node_record["label"], node_record["config"]
        receipt_path = ROOT / f"generated/r32-coverage-{label}-production-receipt.json"
        receipt = json.loads(receipt_path.read_text("utf8"))
        assert receipt["source_snapshot_sha256"] == snapshot and receipt["config"] == config
        (selected,) = [item for item in cache["config_matrix"] if item["config"] == config]
        (warmed,) = [item for item in audit["warm_models"] if item["config"] == config]
        wire = product / "generated" / selected["wire_name"]
        package_model = product / "generated" / selected["model_name"]
        assert wire.resolve().is_relative_to(
            product / "generated"
        ) and package_model.resolve().is_relative_to(product / "generated")
        assert (
            digest(wire)
            == selected["wire_sha256"]
            == receipt["wire_sha256"]
            == node_record["wire_sha256"]
            == warmed["wire_sha256"]
        )
        assert digest(package_model) == receipt["model_sha256"] == node_record["model_sha256"]
        assert cache["files"]["generated/" + selected["wire_name"]] == receipt["wire_sha256"]
        assert cache["files"]["generated/" + selected["model_name"]] == receipt["model_sha256"]
        node_path = Path(node_record["node_check_receipt_path"])
        assert digest(node_path) == node_record["node_check_receipt_sha256"]
        node = json.loads(node_path.read_text("utf8"))
        assert node["failure_count"] == 0 and node["three_mode_plan_count"] == 3069
        replay_path = ROOT / f"generated/r32-bracer-history-component-node-v8-replay-{label}.json"
        replay = json.loads(replay_path.read_text("utf8"))
        assert replay["failure_count"] == 0 and replay["three_mode_plan_count"] == 9
        assert replay["source_snapshot_sha256"] == snapshot
        (replay_wire,) = replay["formal_wire_records"]
        assert replay_wire["wire_sha256"] == node_record["wire_sha256"]
        assert (
            replay_wire["scope_map_sha256_canonical"] == node_record["scope_map_sha256_canonical"]
        )
        source_locale, a_locale, b_locale = (
            config["game_language"],
            config["primary"],
            config["secondary"],
        )
        cases = []
        for mask in (1, 512, 1023):
            indices = selected_ordinals(rows, flags, mask)
            source = constructor(rows, indices, source_locale, source_locale)
            a = constructor(rows, indices, source_locale, a_locale)
            b = constructor(rows, indices, source_locale, b_locale)
            expected_modes = {
                mode: expected_plan(a, b, mode) for mode in ("primary", "secondary", "annotation")
            }
            (saved,) = [item for item in replay["replay_rows"] if item["mask"] == mask]
            assert saved["source"] == source and saved["ordinals"] == indices
            modes = saved["modes"]
            assert modes == expected_modes, (
                "current full-wire Node plan differs from independent physical oracle"
            )
            if mask == 1023:
                for mode, expected in modes.items():
                    (sample,) = [item for item in node["complete_samples"] if item["mode"] == mode]
                    assert (
                        sample["source"] == source
                        and sample["actual"] == sample["expected"] == expected
                    )
            cases.append(
                {
                    "name": f"{label}/flags:{mask}",
                    "category": "positive",
                    "mask": mask,
                    "ordinals": indices,
                    "source": source,
                    "modes": modes,
                }
            )
        full = cases[-1]["source"]
        for name, source in (
            ("unknown_suffix", full + "UNREGISTERED"),
            ("unknown_control", full + "<Q>"),
            ("shared_flag_ordinal9_alone", constructor(rows, [9], source_locale, source_locale)),
            ("shared_flag_ordinal10_alone", constructor(rows, [10], source_locale, source_locale)),
        ):
            plain = {"text": source, "layers": [], "kind": "plain"}
            cases.append(
                {
                    "name": label + "/" + name,
                    "category": "refusal",
                    "source": source,
                    "modes": {mode: plain for mode in ("primary", "secondary", "annotation")},
                }
            )
        before = wire.stat()
        record = {
            "label": label,
            "config": config,
            "wire_path": str(wire),
            "wire_sha256": receipt["wire_sha256"],
            "model_path": str(package_model),
            "model_sha256": receipt["model_sha256"],
            "matrix_wire_name": selected["wire_name"],
            "source_node_wire_receipt": str(node_path),
            "source_node_wire_receipt_sha256": digest(node_path),
            "wire_mtime_ns_before": before.st_mtime_ns,
            "saved_node_plan_replay_path": str(replay_path),
            "saved_node_plan_replay_sha256": digest(replay_path),
            "wire_size_before": before.st_size,
            "cases": cases,
            "passed": False,
            "phase": "host_create",
        }
        host = subprocess.Popen(
            [sys.executable, "-c", "import sys;sys.stdin.buffer.read()"],
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        record["host_pid"] = host.pid
        session = None
        try:
            record["phase"] = "frida_attach_own_hidden_host"
            session = frida.attach(host.pid)
            script = session.create_script(
                (product / "sora_bilingual/game/scripts/runtime_text.js").read_text("utf8")
                + NATIVE
                + (product / "sora_bilingual/game/scripts/native_transport.js").read_text("utf8"),
                runtime="v8",
            )
            record["phase"] = "v8_load_actual_package_wire"
            script.load()
            loaded = script.exports_sync.modelpackedfile(str(wire))
            assert loaded == {
                "runtime": "V8",
                "hasHistory": True,
                "retiredIdentityEmitted": False,
            }, loaded
            record["loaded"] = loaded
            metadata = script.exports_sync.historymetadata()
            scope_hash = hashlib.sha256(metadata.pop("scope_json").encode("utf8")).hexdigest()
            pairs_hash = hashlib.sha256(metadata.pop("pairs_json").encode("utf8")).hexdigest()
            record["metadata"] = dict(
                metadata,
                scope_map_sha256_canonical=scope_hash,
                scope_pairs_sha256_canonical=pairs_hash,
            )
            assert metadata == {"bracer_history_frame": True, "pairs_count": 1023}, metadata
            assert (
                scope_hash == node_record["scope_map_sha256_canonical"]
                and pairs_hash == node_record["scope_pairs_sha256_canonical"]
            )
            record["phase"] = "v8_complete_scoped_plan_replay"
            result = script.exports_sync.historyrun(cases)
            assert result["positive"] == 9 and result["refusal"] == 12
            record["complete_positive_mode_plans"] = result["positive"]
            record["strict_refusal_mode_plans"] = result["refusal"]
            record["actual_plans"] = result["plans"]
            record["failures"] = result["failures"]
            report["complete_positive_mode_plans"] += result["positive"]
            report["strict_refusal_mode_plans"] += result["refusal"]
            report["failures"].extend(result["failures"])
            after = wire.stat()
            record["wire_mtime_ns_after"] = after.st_mtime_ns
            record["wire_size_after"] = after.st_size
            record["wire_size_and_mtime_unchanged"] = (
                before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
            )
            assert record["wire_size_and_mtime_unchanged"]
            record["passed"] = not result["failures"]
            record["phase"] = "complete"
        except Exception as error:
            record["error_type"] = type(error).__name__
            record["error"] = str(error)
            record["original_traceback"] = traceback.format_exc()
            report["failures"].append(
                {
                    "label": label,
                    "phase": record["phase"],
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
        finally:
            try:
                if session is not None:
                    session.detach()
            finally:
                host.stdin.close()
                host.wait(timeout=5)
        report["records"].append(record)
        print(
            json.dumps(
                {
                    key: record.get(key)
                    for key in (
                        "label",
                        "passed",
                        "phase",
                        "complete_positive_mode_plans",
                        "strict_refusal_mode_plans",
                        "error",
                    )
                }
            ),
            flush=True,
        )
        if not record["passed"]:
            break
    report["candidate_cache_sha256_after"] = digest(cache_path)
    report["package_js_sha256_after"] = {
        name: digest(product / "sora_bilingual/game/scripts" / name) for name in SCRIPT_NAMES
    }
    assert report["candidate_cache_sha256_before"] == report["candidate_cache_sha256_after"]
    assert report["package_js_sha256_before"] == report["package_js_sha256_after"]
    report["failure_count"] = len(report["failures"])
    report["complete"] = len(report["records"]) == 5 and all(
        record["passed"] for record in report["records"]
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": digest(args.output),
                "source_snapshot_sha256": snapshot,
                "complete_positive_mode_plans": report["complete_positive_mode_plans"],
                "strict_refusal_mode_plans": report["strict_refusal_mode_plans"],
                "failure_count": report["failure_count"],
                "complete": report["complete"],
            }
        ),
        flush=True,
    )
    return not report["complete"]


if __name__ == "__main__":
    raise SystemExit(main())
