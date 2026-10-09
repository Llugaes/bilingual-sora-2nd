"""Bounded EN→JA/SC status formatter oracle from raw PAC fields, not model decisions."""

from pathlib import Path
import argparse, hashlib, json, struct, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _logical_tables
from sora_bilingual.localization.menu_tables import sections
from sora_bilingual.config.locales import archive_names


def raw_inventory(game):
    out = {"effects": {}, "condition_help": {}, "condition_info": {}, "constants": {}, "tables": []}
    for language in ("en", "ja", "zh-Hans"):
        with FpacArchive(game / "pac/steam" / archive_names("table")[language]) as archive:
            for table in ("table/t_itemhelp.tbl", "table/t_condition_info.tbl", "table/t_text.tbl"):
                data = archive.read(_logical_tables(archive)[table])
                out["tables"].append(
                    {
                        "language": language,
                        "table": table,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )

                def text(at):
                    p = struct.unpack_from("<Q", data, at)[0]
                    return data[p : data.index(b"\0", p)].decode("utf-8") if p else ""

                for kind, start, stride, count in sections(data):
                    if kind == "TextTableData":
                        assert stride == 16
                        for i in range(count):
                            at = start + i * stride
                            key = text(at)
                            if key.startswith("TXT_ITEM_HELP_"):
                                out["constants"].setdefault(key, {})[language] = text(at + 8)
                    if kind == "SkillEffectHelpData":
                        assert stride == 88
                        for i in range(count):
                            at = start + i * stride
                            ident = struct.unpack_from("<I", data, at)[0]
                            p, n = struct.unpack_from("<QI", data, at + 16)
                            types = list(struct.unpack_from("<" + "H" * n, data, p)) if n else []
                            row = out["effects"].setdefault(
                                str(ident), {"parameter_types": types, "texts": {}}
                            )
                            assert row["parameter_types"] == types
                            row["texts"][language] = {
                                name: text(at + offset)
                                for name, offset in [
                                    ("name", 8),
                                    ("stat", 32),
                                    ("format", 40),
                                    ("color", 48),
                                    ("turns", 72),
                                    ("value", 80),
                                ]
                            }
                    if kind == "ConditionHelpData":
                        assert stride == 40
                        for i in range(count):
                            at = start + i * stride
                            key = data[at : at + 8].hex()
                            out["condition_help"].setdefault(key, {})[language] = {
                                "format": text(at + 8),
                                "condition": text(at + 16),
                                "rate": text(at + 24),
                                "next_condition": text(at + 32),
                            }
                    if kind == "ConditionInfoTableData":
                        assert stride == 88
                        for i in range(count):
                            at = start + i * stride
                            scalar = bytearray(data[at : at + stride])
                            scalar[8:16] = b"\0" * 8
                            scalar[80:88] = b"\0" * 8
                            name = text(at + 8)
                            if name:
                                out["condition_info"].setdefault(bytes(scalar).hex(), {})[
                                    language
                                ] = name
    return out


def oracle_rows(p):
    langs = ("en", "ja", "zh-Hans")
    cases = []
    missing = []

    def printf(template, *arguments):
        for arg in arguments:
            token = "%s" if isinstance(arg, str) else "%d"
            template = template.replace(token, str(arg), 1)
        return template.replace("%%", "%")

    def add(family, key, values, color=None):
        if any(not values.get(l) for l in langs):
            missing.append({"family": family, "key": key})
            return
        forms = [("", "")]
        if color:
            forms.append((color, "</C>"))
        for prefix, suffix in forms:
            cases.append(
                {
                    "family": family,
                    "key": key,
                    "source": prefix + values["en"] + suffix,
                    "expected_primary": prefix + values["ja"] + suffix,
                    "expected_secondary": prefix + values["zh-Hans"] + suffix,
                    "level": "independent raw-resource formatter oracle; not captured game original",
                    "wrapper": "raw resource color field" if prefix else "none",
                }
            )

    for ident, row in p["effects"].items():
        if row["parameter_types"] == [17]:
            color = row["texts"]["en"]["color"]
            assert all(row["texts"][l]["color"] == color for l in langs)
            for key, name in p["condition_help"].items():
                if any(not name[l]["condition"] for l in langs):
                    continue
                add(
                    "condition_parameter_type17",
                    ident + "/" + key,
                    {l: printf(row["texts"][l]["name"], name[l]["condition"], 50) for l in langs},
                    color,
                )
    for key, name in p["condition_help"].items():
        if all("%d" in name[l]["format"] for l in langs):
            add(
                "ConditionHelpData_format_probability",
                key,
                {l: printf(name[l]["format"], 50) for l in langs},
                p["effects"]["1089"]["texts"]["en"]["color"],
            )
    condition_names = {
        n["en"]["condition"] for n in p["condition_help"].values() if n["en"]["condition"]
    }
    for key, row in p["effects"].items():
        if row["parameter_types"] == [1] and row["texts"]["en"]["stat"] in condition_names:
            add(
                "SkillEffectHelpData_condition_probability",
                key,
                {l: printf(row["texts"][l]["name"], 50) for l in langs},
                row["texts"]["en"]["color"],
            )
    constants = p["constants"]
    templates = p["effects"]["98"]["texts"]
    for key, name in p["condition_info"].items():
        if any(l not in name for l in langs):
            missing.append({"family": "condition_resist_mask_type10", "key": key})
            continue
        add(
            "condition_resist_mask_type10",
            key,
            {
                l: templates[l]["name"].replace(
                    "%s", name[l] + " " + printf(constants["TXT_ITEM_HELP_PERSENT"][l], 100)
                )
                for l in langs
            },
            templates["en"]["color"],
        )
    # Keep the two previously reported complete lists, not a comma split or name alias.
    for desired in [("Mute", "Freeze"), ("Burn", "Confuse", "Deathblow")]:
        names = [
            next(row for row in p["condition_info"].values() if row.get("en") == word)
            for word in desired
        ]
        add(
            "condition_resist_reported_list",
            "/".join(desired),
            {
                l: templates[l]["name"].replace(
                    "%s",
                    constants["TXT_ITEM_HELP_LINK"][l].join(n[l] for n in names)
                    + " "
                    + printf(constants["TXT_ITEM_HELP_PERSENT"][l], 100),
                )
                for l in langs
            },
            templates["en"]["color"],
        )
    return {
        "cases": cases,
        "missing": missing,
        "raw_inventory": "generated/r21-status-raw-inventory.json",
        "actual_game_inputs": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    args = parser.parse_args()
    inventory = raw_inventory(args.game)
    inputs = oracle_rows(inventory)

    def save(name, data):
        (ROOT / "generated" / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save("r21-status-raw-inventory.json", inventory)
    save("r21-status-oracle-inputs.json", inputs)
    if inputs["missing"]:
        raise AssertionError(
            "Raw status family has incomplete locale peers: " + str(inputs["missing"])
        )
    subprocess.run(
        ["node", str(ROOT / "tests/check_r21_status_oracle_render.js")], cwd=ROOT, check=True
    )


if __name__ == "__main__":
    main()
