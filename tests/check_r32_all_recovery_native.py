"""Focused native ALL fixtures and current Python component; no model build or game.

The official-record oracle was reconstructed independently from CAB62 kind13
format/stat instructions and physical PAC fields. Historical wrong fixtures
remain byte-exact. A component pass does not endorse a new compiled product.
"""

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization import item_help_composition as current


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "tests/fixtures/r32-all-recovery-native-producers.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "generated/r32-live008-all-recovery-native-component.json",
    )
    parser.add_argument(
        "--baseline-product",
        type=Path,
        default=ROOT / "dist/r32-coverage-local8/DEV",
    )
    args = parser.parse_args()
    assert not args.out.exists(), "preserve previous receipts"
    fixture = json.loads(args.fixture.read_text("utf8"))
    raw_path = ROOT / fixture["source_evidence"]["resources_path"]
    raw = json.loads(raw_path.read_text("utf8"))["locales"]
    languages = tuple(raw)
    rows, failures, checks = [], [], []

    def check(name, actual, expected):
        entry = {"name": name, "actual": actual, "expected": expected, "passed": actual == expected}
        checks.append(entry)
        if not entry["passed"]:
            failures.append(entry)

    for key, value in fixture["source_evidence"].items():
        if key.endswith("_path"):
            check(
                "preserved-evidence/" + key,
                digest(ROOT / value),
                fixture["source_evidence"][key[:-5] + "_sha256"],
            )
    for name, value in fixture["old_wrong_oracles_preserved"].items():
        check("old-wrong-oracle-byte-exact/" + name, digest(ROOT / "generated" / name), value)

    baseline_source = args.baseline_product / "sora_bilingual/localization/item_help_composition.py"
    spec = importlib.util.spec_from_file_location(
        "r32_local8_all_recovery_baseline", baseline_source
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    catalogue = {
        "table/t_text.tbl/TXT_ITEM_HELP_" + key: {
            locale: data["constants"][key] for locale, data in raw.items()
        }
        for key in ("ALL", "PERSENT", "LINK")
    }
    fields = {}
    for identifier in (123, 125):
        identities = {data["effects"][str(identifier)]["identity"] for data in raw.values()}
        check(f"physical-record-alignment/{identifier}", len(identities), 1)
        identity = next(iter(identities))
        fields[identity] = {
            field: {locale: data["effects"][str(identifier)][field] for locale, data in raw.items()}
            for field in ("name", "stat", "format")
        }
        all_result = current._recovery_group(
            catalogue,
            fields,
            (identity,),
            languages,
            magnitude=catalogue["table/t_text.tbl/TXT_ITEM_HELP_ALL"],
        )
        percent_result = current._recovery_group(catalogue, fields, (identity,), languages)
        baseline_percent = baseline._recovery_group(catalogue, fields, (identity,), languages)
        for locale in languages:
            expected = next(
                row
                for row in fixture["native_units"]
                if row["effect_id"] == identifier and row["locale"] == locale
            )
            check(
                f"native-kind13-ALL/{identifier}/{locale}",
                all_result[locale],
                expected["native_phrase"],
            )
            check(
                f"existing-percent-unchanged/{identifier}/{locale}",
                percent_result[locale],
                baseline_percent[locale],
            )
            rows.append(
                {
                    "locale": locale,
                    "effect_id": identifier,
                    "record_identity": identity,
                    "all_actual": all_result[locale],
                    "all_expected": expected["native_phrase"],
                    "original_name_ALL": expected["old_name_phrase"],
                    "percent_template": percent_result[locale],
                }
            )

    for locale, data in raw.items():
        first_kind = next(
            row["kind"] for row in data["recovery_connection_rows"] if 123 in row["ids"]
        )
        check(f"first-physical-connection/123/{locale}", first_kind, 13)
        first_kind = next(
            row["kind"] for row in data["recovery_connection_rows"] if 125 in row["ids"]
        )
        check(f"first-physical-connection/125/{locale}", first_kind, 13)
        hp = next(
            row["all_actual"] for row in rows if row["locale"] == locale and row["effect_id"] == 123
        )
        icon = data["effects"]["123"]["icon"]
        fortune = data["effects"]["1202"]
        duration = next(slot[1] for slot in data["mom"]["item"]["slots"] if slot[0] == 1206)
        fortune_unit = (
            f"<C9><I{fortune['icon']}></C>" + fortune["stat"] + fortune["format"] % duration
        )
        for join, expected_by_locale in fixture["mom_complete_compact_texts"].items():
            full = (
                data["mom"]["prefix"]
                + f"<C9><I{icon}></C>"
                + hp
                + join
                + fortune_unit
                + data["mom"]["close"]
            )
            check(f"complete-physical-Mom/{locale}/{join!r}", full, expected_by_locale[locale])
            check(
                f"complete-physical-Mom-body/{locale}/{join!r}",
                full + "\n" + data["mom"]["item"]["body"],
                fixture["mom_complete_with_body_texts"][join][locale],
            )
    check(
        "actual-complete-setter-source-byte-exact",
        fixture["mom_complete_compact_texts"][" - "]["en"],
        fixture["actual_complete_setter_row"]["original"],
    )

    def mode1_branch(source):
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_compile_p0_producers"
        )
        branch = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.If)
            and ast.dump(node.test) == ast.dump(ast.parse("identifier == 120", mode="eval").body)
        )
        return ast.dump(branch, include_attributes=False)

    current_source = Path(current.__file__).read_text("utf8")
    check(
        "kind16-mode1-and-permanent-branches-unchanged",
        mode1_branch(current_source),
        mode1_branch(baseline_source.read_text("utf8")),
    )

    import pefile

    executable = Path("D:/Steam/steamapps/common/Trails in the Sky 2nd Chapter/sora_2nd.exe")
    check(
        "actual-CAB62-image",
        digest(executable),
        "cab62e5872222efb2aaf272be47f14263db4e7132ad7df5255db8efbee9959ea",
    )
    pe = pefile.PE(str(executable))
    for rva, expected in (
        (0x34D6E3, "6683f80d"),
        (0x34DB97, "488b5728"),
        (0x34DBC1, "83f864"),
        (0x34DD05, "488b5720"),
        (0x4127E1, "41b901000000"),
        (0x347D6C, "41b901000000"),
    ):
        check(
            f"bounded-native-instruction/{rva:x}",
            pe.get_data(rva, len(expected) // 2).hex(),
            expected,
        )
    for rva, target in ((0x4127F6, 0x347B70), (0x347D83, 0x34BE70), (0x412803, 0x5892C0)):
        code = pe.get_data(rva, 5)
        check(
            f"actual-direct-CALL/{rva:x}",
            (code[0], rva + 5 + struct.unpack_from("<i", code, 1)[0]),
            (0xE8, target),
        )

    report = {
        "scope": "Current Python kind13 ALL component against independently reconstructed physical/native fixtures; no complete model/wire or game acceptance",
        "reference_sealed_snapshot_sha256": fixture["reference_source_snapshot_sha256"],
        "current_item_help_composition_sha256": digest(current.__file__),
        "baseline_source_sha256": digest(baseline_source),
        "fixture_path": str(args.fixture),
        "fixture_sha256": digest(args.fixture),
        "checker_sha256": digest(__file__),
        "native_units": rows,
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "kind13_physical_context_count": len(fixture["kind13_contexts"]),
        "kind16_physical_context_count_separate": len(fixture["kind16_contexts_separate"]),
        "old_wrong_oracles_modified": False,
        "complete_production_model_compiled": False,
        "new_product_endorsed": False,
        "build_run": False,
        "game_attached": False,
        "production_written": False,
        "actual_callback_entry": False,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "sha256": digest(args.out),
                "check_count": len(checks),
                "failure_count": len(failures),
                "failures": failures,
            },
            ensure_ascii=False,
        )
    )
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
