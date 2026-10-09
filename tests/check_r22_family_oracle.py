"""Raw resource/native family oracle; fresh final render is the first resolver call."""

from pathlib import Path
import json, re, sys, subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from sora_bilingual.localization.item_help_composition import read_item_help_contract
from check_r21_status_oracle import raw_inventory

game = Path(r"D:\Steam\steamapps\common\Trails in the Sky 2nd Chapter")
p = raw_inventory(game)
_metadata, groups, audit = read_item_help_contract(game, languages=("en", "ja", "zh-Hans"))
langs = ("en", "ja", "zh-Hans")
rows = []


def printf(s, *args):
    for a in args:
        s = s.replace("%s" if isinstance(a, str) else "%d", str(a), 1)
    return s.replace("%%", "%")


def add(family, ids, texts):
    for color in (False, True):
        wrapped = {l: ("<c698>" + texts[l] + "</C>" if color else texts[l]) for l in langs}
        rows.append(
            {
                "family": family,
                "ids": ids,
                "source": "[Support] " + wrapped["en"],
                "primary_member": wrapped["ja"],
                "secondary_member": wrapped["zh-Hans"],
                "level": "raw PAC fields plus audited native constructor; not actual setter",
            }
        )


for ident, row in p["effects"].items():
    names = {l: row["texts"][l]["name"] for l in langs}
    if row["parameter_types"] == [1] and all(
        re.findall(r"%[sdiu]", s) == ["%d"] and "%" not in s.replace("%d", "").replace("%%", "")
        for s in names.values()
    ):
        add("numeric_type1", [int(ident)], {l: printf(names[l], 50) for l in langs})
    if row["parameter_types"] == [13] and all(
        re.findall(r"%[sdiu]", s) == ["%s"] for s in names.values()
    ):
        for constant in ("MOSTSMALL", "SMALL", "MIDDLE", "LARGE", "MOSTLARGE"):
            add(
                "magnitude_type13",
                [int(ident)],
                {
                    l: printf(names[l], p["constants"]["TXT_ITEM_HELP_" + constant][l])
                    for l in langs
                },
            )
    if row["parameter_types"] == [4] and all(
        row["texts"][l]["stat"] and row["texts"][l]["format"].count("%s") == 1 for l in langs
    ):
        add(
            "single_percent_type4",
            [int(ident)],
            {
                l: (
                    row["texts"][l]["stat"]
                    + printf(
                        row["texts"][l]["format"],
                        printf(p["constants"]["TXT_ITEM_HELP_PERSENT"][l], 30),
                    )
                    if l != "en"
                    else printf(
                        row["texts"][l]["format"],
                        printf(p["constants"]["TXT_ITEM_HELP_PERSENT"][l], 30),
                    )
                    + row["texts"][l]["stat"]
                )
                for l in langs
            },
        )
for connection in audit["_connect_groups"]:
    if connection["kind"] == 1:
        # Independent native forward scan; no compiler-generated rows are used.
        members = set(connection["ids"])
        sequences = {(i,) for i in members}
        for group in groups:
            used = set()
            for at, slot in enumerate(group):
                if at in used or slot[0] not in members:
                    continue
                chosen = []
                for index in range(at, len(group)):
                    other = group[index]
                    if index not in used and other[0] in members and other[1:] == slot[1:]:
                        chosen.append(other[0])
                        used.add(index)
                sequences.add(tuple(chosen))
        for ids in sorted(sequences):
            texts = {}
            for l in langs:
                fields = [p["effects"][str(i)]["texts"][l] for i in ids]
                names = p["constants"]["TXT_ITEM_HELP_LINK"][l].join(f["stat"] for f in fields)
                texts[l] = (
                    fields[0]["format"] + " " + names + " 100%"
                    if l == "en"
                    else "「" + names + "」" + printf(fields[0]["format"], 100)
                )
            add("resist_native_kind1", list(ids), texts)
    if connection["kind"] == 4:
        for ident in connection["ids"]:
            row = p["effects"][str(ident)]
            if row["parameter_types"] != [16]:
                continue
            for strength in (1, 2, 3):
                icon = "<I" + str(269 + strength) + ">"
                for gap in ("", " "):
                    texts = {
                        l: printf(row["texts"][l]["name"], icon, 5)
                        if l == "en"
                        else printf(row["texts"][l]["name"], 5, icon)
                        for l in langs
                    }
                    texts["en"] = (
                        row["texts"]["en"]["stat"]
                        + icon
                        + gap
                        + printf(row["texts"]["en"]["turns"], 5)
                    )
                    add("turn_kind4_icon" + str(strength) + "_gap" + str(len(gap)), [ident], texts)
(ROOT / "generated/r22-family-oracle-inputs.json").write_text(
    json.dumps(
        {"tables": p["tables"], "rows": rows, "actual_game_inputs": False},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
result = subprocess.run(["node", str(ROOT / "tests/check_r22_family_oracle.js")], cwd=ROOT)
sys.exit(result.returncode)
