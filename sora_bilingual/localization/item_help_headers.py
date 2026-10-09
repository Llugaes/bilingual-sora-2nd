"""Compile complete Tools headers from the reviewed kind-three constructor.

A category/range prefix only owns its selected physical record's body. Effects
remain subject to the existing typed parser; no category or range word becomes
a standalone alias. Native flag letters are enum inputs, not translated words.
"""

import re
import struct
import json
from collections import Counter, defaultdict
from pathlib import Path

from sora_bilingual.localization.resources import FpacArchive
from sora_bilingual.localization.tables import _TABLE_ARCHIVES, _logical_tables
from sora_bilingual.localization.menu_tables import sections, schema_for, record_identity


# Destinations of the reviewed ItemFlags parser's ASCII jump table.
_FLAG_BITS = dict(zip("ABCDEFGHI", (21, 18, 16, 24, 13, 12, 23, 28, 17)))
_FLAG_BITS.update(dict(zip("LMNOPQRSTXb", (27, 19, 26, 22, 25, 29, 15, 14, 20, 30, 31))))


def _range_id(target, flags, first_effect):
    """The two identical kind-three range-selection branches in native code."""
    ally = (flags >> 12) & 1
    if target == 0xA6:
        return 18 if first_effect == 0x8D else 16 + ally
    if target in (0x101, 0x109):
        if flags & 0x5000 == 0x5000:
            return 3
        if flags & 0x4000:
            return 4
        return 2 + ally if target == 0x101 else 1 + 2 * ally
    return {
        0x115: 12,
        0x116: 11,
        0x11E: 10,
        0x125: 13 + ally,
        0x126: 8 + ally,
        0x12D: 15,
        0x1124: 7,
    }.get(target, 0)


def compile_item_help_headers(game, entries, primary, secondary, language):
    catalogue = defaultdict(list)
    for entry in entries:
        if entry.get("key", "").startswith(
            ("table/t_item.tbl/", "table/t_itemhelp.tbl/", "table/t_text.tbl/TXT_ITEM_HELP_")
        ):
            catalogue[entry["key"]].append(entry.get("texts", {}))
    locales = (language, primary, secondary)
    audit, rows, compact_rows, attack_rows = Counter(), [], [], []
    archive = FpacArchive(Path(game) / "pac/steam" / _TABLE_ARCHIVES[language])
    try:
        logical = _logical_tables(archive)
        item = archive.read(logical["table/t_item.tbl"])
        help_data = archive.read(logical["table/t_itemhelp.tbl"])
        skill_data = archive.read(logical["table/t_skill.tbl"])
    finally:
        archive.close()

    def table(data, path, kind):
        layout = sections(data)
        matches = [row for row in layout if row[0] == kind]
        schema = schema_for(path, kind)
        if len(matches) != 1 or matches[0][2] != schema.size:
            raise ValueError("item header physical section changed: " + kind)
        return matches[0][1:], schema, max(at + stride * n for _, at, stride, n in layout)

    it, isc, it_floor = table(item, "table/t_item.tbl", "ItemTableData")
    ht, hsc, h_floor = table(help_data, "table/t_itemhelp.tbl", "ItemKindHelpData")
    rt, rsc, _ = table(help_data, "table/t_itemhelp.tbl", "SkillRangeHelpData")
    st, ssc, _ = table(help_data, "table/t_itemhelp.tbl", "SkillTextArrayData")
    pt, _psc, _ = table(skill_data, "table/t_skill.tbl", "SkillPowerIcon")

    def string(data, at, floor):
        pointer = struct.unpack_from("<Q", data, at)[0]
        if not floor <= pointer < len(data):
            raise ValueError("item header pointer outside pool")
        end = data.find(b"\0", pointer, min(pointer + 2048, len(data)))
        if end < 0:
            raise ValueError("item header string exceeds budget")
        return data[pointer:end].decode("utf8", "strict")

    def field(key, source, allow_empty=False):
        candidates = catalogue.get(key, [])
        if not candidates and source == "":
            return ["", "", ""]
        tuples = {tuple(texts.get(locale) for locale in locales) for texts in candidates}
        if len(tuples) != 1:
            raise ValueError("missing or ambiguous item header alignment")
        values = next(iter(tuples))
        if values[0] != source or any(
            value is None or (not allow_empty and not value.strip()) for value in values
        ):
            raise ValueError("incomplete or different item header source")
        return list(values)

    def constant(name, specs):
        key = "table/t_text.tbl/TXT_ITEM_HELP_" + name
        candidates = catalogue.get(key, [])
        if len(candidates) != 1:
            raise ValueError("missing or ambiguous Tools format")
        values = [candidates[0].get(locale, "") for locale in locales]
        if any(re.findall(r"%%|%[^%]*?[a-zA-Z]", value) != specs for value in values):
            raise ValueError("Tools printf field sequence changed")
        return key, values

    # Only invoked for actual production help resources, never minimal fixtures.
    f1_key, f1 = constant("FORMAT1", ["%03d", "%s"])
    f5_key, f5 = constant("FORMAT5", [])
    f6_key, f6 = constant("FORMAT6", [])
    f7_key, f7 = constant("FORMAT7", ["%s"] * 4)
    tails = [value.split("%s") for value in f7]
    if any(
        chunks[:3] != ["", "", ""] or not chunks[3].endswith("\n") or chunks[4] for chunks in tails
    ):
        raise ValueError("Tools final argument order changed")
    close = [chunks[3][:-1] for chunks in tails]
    if any(not value or any(sep in value for sep in ("\n", "\r", "\\n")) for value in close):
        raise ValueError("Tools close is not one line")
    selectors = [struct.unpack_from("<HHI", help_data, ht[0] + j * ht[1]) for j in range(ht[2])]
    ranges = [struct.unpack_from("<H", help_data, rt[0] + j * rt[1])[0] for j in range(rt[2])]

    def skill_format(mode, kind):
        selected = [
            st[0] + j * st[1]
            for j in range(st[2])
            if struct.unpack_from("<HH", help_data, st[0] + j * st[1]) == (mode, kind)
        ]
        if len(selected) != 1:
            raise ValueError("ambiguous compact attack format selector")
        at = selected[0]
        key = (
            "table/t_itemhelp.tbl/SkillTextArrayData/"
            + record_identity(help_data, at, "SkillTextArrayData", ssc, h_floor)
            + "/format"
        )
        return key, field(key, string(help_data, at + 8, h_floor), True)

    for physical in range(it[2]):
        audit["physical_items"] += 1
        at = it[0] + physical * it[1]
        mode, category, third = struct.unpack_from("<BBH", item, at + 40)
        selected = next(
            (
                j
                for j, (a, b, c) in enumerate(selectors)
                if a == mode and b == category and (c == 0 or c == third)
            ),
            None,
        )
        if selected is None:
            audit["no_selector"] += 1
            continue
        ha = ht[0] + selected * ht[1]
        if struct.unpack_from("<I", help_data, ha + 16)[0] != 3:
            audit["other_kind"] += 1
            continue
        audit["kind3_items"] += 1
        if mode == 1 and category == 32:
            # The attack-food branch uses the same physical SkillTextArray,
            # PowerIcon and RangeHelp fields as 0x34a200. Compile the finite
            # selected item prefixes, including their exact power/range icons.
            source_flags = string(item, at + 24, it_floor)
            mask = sum(1 << _FLAG_BITS[c] for c in set(source_flags) if c in _FLAG_BITS)
            target = struct.unpack_from("<H", item, at + 48)[0]
            first, amount = struct.unpack_from("<II", item, at + 60)
            if first not in (12, 15):
                raise ValueError("compact attack kind changed")
            range_id = _range_id(target, mask, first)
            if range_id not in (11, 13):
                raise ValueError("compact attack range branch uncovered")
            radius = struct.unpack_from("<f", item, at + 56)[0]
            measure, limits = (
                (radius * radius, (2.25, 9, 36)) if range_id == 13 else (radius, (2, 3, 4))
            )
            size = next(
                (name for name, limit in zip(("S", "M", "L"), limits) if measure <= limit), "LL"
            )
            size_key, size_values = constant("RANGE_" + size, [])
            ra = rt[0] + ranges.index(range_id) * rt[1]
            range_key = (
                "table/t_itemhelp.tbl/SkillRangeHelpData/"
                + record_identity(help_data, ra, "SkillRangeHelpData", rsc, h_floor)
                + "/label"
            )
            labels = field(range_key, string(help_data, ra + 8, h_floor))
            range_icon = struct.unpack_from("<I", help_data, ra + 16)[0]
            power_icon = 0
            for j in range(pt[2]):
                threshold, icon = struct.unpack_from("<iI", skill_data, pt[0] + j * pt[1])
                if amount < threshold:
                    break
                power_icon = icon
            head_key = (
                "table/t_itemhelp.tbl/ItemKindHelpData/"
                + record_identity(help_data, ha, "ItemKindHelpData", hsc, h_floor)
                + "/description"
            )
            head = field(head_key, string(help_data, ha + 8, h_floor))
            start_key, start_values = skill_format(0, 0)
            kind_key, kind_values = skill_format(1, 16 if first == 12 else 17)
            end_key, end_values = skill_format(2, 0)
            if any(
                value.count("%s") != 1 or "%" in value.replace("%s", "")
                for value in [*kind_values, *end_values]
            ):
                raise ValueError("compact attack printf changed")

            def part(values, key=None):
                return {
                    "source": values[0],
                    "pair": values[1:],
                    **({"semantic_ids": [key], "parameters": []} if key else {"opaque": True}),
                }

            power = f"<C9><I{power_icon}></C>" if power_icon else ""
            range_token = f"<C9><I{range_icon:03d}></C>" if range_icon else ""
            kinds, ends = [v.split("%s") for v in kind_values], [v.split("%s") for v in end_values]
            parts = [
                part(head, head_key),
                part(start_values, start_key),
                part([v[0] for v in kinds], kind_key),
                part([power] * 3),
                part([v[1] for v in kinds], kind_key),
                part([v[0] for v in ends], end_key),
                part([range_token] * 3),
                {
                    "source": labels[0] + size_values[0],
                    "pair": [label + size for label, size in zip(labels[1:], size_values[1:])],
                    "semantic_ids": [range_key, size_key],
                    "parameters": [],
                },
                part([v[1] for v in ends], end_key),
            ]
            attack_rows.append(
                {
                    "physical": physical,
                    "item_id": struct.unpack_from("<I", item, at)[0],
                    "parts": parts,
                    "prefix": "".join(p["source"] for p in parts),
                    "power_icon": power_icon,
                    "range_id": range_id,
                    "format_keys": [start_key, kind_key, end_key],
                }
            )
            audit["compact_attack_items"] += 1
        # CAB62 0x347d88..0x347f0c is the r9=1 cooking notebook branch.
        # It emits category + FORMAT5 + the complete typed effect list +
        # FORMAT6, without the ordinary range or record body. Compile that
        # constructor explicitly; a missing Tools body cannot borrow it.
        if mode == 1 and category in (3, 4):
            head_key = (
                "table/t_itemhelp.tbl/ItemKindHelpData/"
                + record_identity(help_data, ha, "ItemKindHelpData", hsc, h_floor)
                + "/description"
            )
            head = field(head_key, string(help_data, ha + 8, h_floor))
            parts = [
                {"source": head[0], "pair": head[1:], "semantic_ids": [head_key], "parameters": []},
                {"source": f5[0], "pair": f5[1:], "opaque": True},
            ]
            compact_rows.append(
                {
                    "physical": physical,
                    "item_id": struct.unpack_from("<I", item, at)[0],
                    "help_row": selected,
                    "prefix": head[0] + f5[0],
                    "parts": parts,
                    "close": f6,
                    "format_keys": [f5_key, f6_key],
                }
            )
            audit["compact_items"] += 1
        if mode != 1 or category not in (1, 2, 3, 4, 31):
            audit["other_kind3_branch"] += 1
            continue
        try:
            source_flags = string(item, at + 24, it_floor)
            mask = 0
            for char in source_flags.encode("ascii", "strict").decode("ascii"):
                if char in _FLAG_BITS:
                    mask |= 1 << _FLAG_BITS[char]
            target = struct.unpack_from("<H", item, at + 48)[0]
            first = struct.unpack_from("<H", item, at + 60)[0]
            if first == 0x9B:
                raise ValueError("extra-body effect branch uncovered")
            range_id = _range_id(target, mask, first)
            if range_id not in ranges:
                raise ValueError("no selected range record")
            ra = rt[0] + ranges.index(range_id) * rt[1]
            head_key = (
                "table/t_itemhelp.tbl/ItemKindHelpData/"
                + record_identity(help_data, ha, "ItemKindHelpData", hsc, h_floor)
                + "/description"
            )
            range_key = (
                "table/t_itemhelp.tbl/SkillRangeHelpData/"
                + record_identity(help_data, ra, "SkillRangeHelpData", rsc, h_floor)
                + "/short_label"
            )
            body_key = (
                "table/t_item.tbl/"
                + record_identity(item, at, "ItemTableData", isc, it_floor)
                + "/description"
            )
            head = field(head_key, string(help_data, ha + 8, h_floor))
            short = field(range_key, string(help_data, ra + 24, h_floor))
            body = field(body_key, string(item, at + 232, it_floor))
            if any("%" in value.replace("%%", "") for value in body):
                raise ValueError("body printf arguments uncovered")
            body = [value.replace("%%", "%") for value in body]
            icon = struct.unpack_from("<I", help_data, ra + 16)[0]
            parts = [
                {"source": head[0], "pair": head[1:], "semantic_ids": [head_key], "parameters": []}
            ]
            chunks = [value.replace("%03d", str(icon).zfill(3)).split("%s") for value in f1]
            # Keep the icon bytes in an opaque lane, independent of typography.
            icon_token = "<I" + str(icon).zfill(3) + ">"
            before_icon = [value[0].split(icon_token) for value in chunks]
            if any(len(value) != 2 for value in before_icon):
                raise ValueError("Tools icon placement changed")
            parts.extend(
                (
                    {
                        "source": before_icon[0][0],
                        "pair": [v[0] for v in before_icon[1:]],
                        "opaque": True,
                    },
                    {"source": icon_token, "pair": [icon_token, icon_token], "opaque": True},
                    {
                        "source": before_icon[0][1],
                        "pair": [v[1] for v in before_icon[1:]],
                        "opaque": True,
                    },
                    {
                        "source": short[0],
                        "pair": short[1:],
                        "semantic_ids": [range_key],
                        "parameters": [],
                    },
                    {"source": chunks[0][1], "pair": [v[1] for v in chunks[1:]], "opaque": True},
                )
            )
            prefix = "".join(part["source"] for part in parts)
            if (
                any(sep in prefix for sep in ("\n", "\r", "\\n"))
                or len((prefix + body[0]).encode("utf8")) > 4096
            ):
                raise ValueError("Tools prefix/body exceeds bounded contract")
            rows.append(
                {
                    "physical": physical,
                    "help_row": selected,
                    "range_id": range_id,
                    "body_key": body_key,
                    "body": body[0],
                    "body_pair": body[1:],
                    "prefix": prefix,
                    "frame_prefix": head[0] + before_icon[0][0],
                    "parts": parts,
                    "close": close,
                    "format_keys": [f1_key, f7_key],
                }
            )
            audit["admitted"] += 1
        except (ValueError, UnicodeDecodeError) as error:
            audit[str(error)] += 1
    bodies = defaultdict(set)
    for row in rows:
        bodies[row["body"]].add(tuple(row["body_pair"]))
    # A repeated body cannot identify an item by itself. Bind it only when
    # its complete physical effect sequence also agrees, including amounts,
    # icon order and kind10's late append. This does not create native IDs.
    et, esc, _ = table(help_data, "table/t_itemhelp.tbl", "SkillEffectHelpData")
    effect_rows = {
        struct.unpack_from("<I", help_data, et[0] + j * et[1])[0]: et[0] + j * et[1]
        for j in range(et[2])
    }
    from sora_bilingual.localization.item_help_composition import _read_connect_groups

    connection_kinds = {}
    for connection in _read_connect_groups(help_data):
        for identifier in connection["ids"]:
            connection_kinds.setdefault(identifier, connection["kind"])
    all_key, all_values = constant("ALL", [])
    for row in rows:
        at = it[0] + row["physical"] * it[1]
        slots = [struct.unpack_from("<4I", item, at + 60 + 16 * j) for j in range(5)]
        owned = {}
        for identifier, amount, turns, strength in slots:
            if (
                identifier not in (123, 125)
                or amount != 100
                or connection_kinds.get(identifier) != 13
            ):
                continue
            ea = effect_rows[identifier]
            ptr, n, mode = struct.unpack_from("<QII", help_data, ea + 16)
            if mode != 0 or struct.unpack_from(f"<{n}I", help_data, ptr) != (4,):
                raise ValueError("kind13 ALL parameter contract changed")
            identity = record_identity(help_data, ea, "SkillEffectHelpData", esc, h_floor)
            stem = "table/t_itemhelp.tbl/SkillEffectHelpData/" + identity
            stat = field(stem + "/stat", string(help_data, ea + 32, h_floor))
            form = field(stem + "/format", string(help_data, ea + 40, h_floor))
            if any("%" in value for value in stat) or any(
                re.findall(r"%%|%[^%]*?[a-zA-Z]", value) != ["%s"] for value in form
            ):
                raise ValueError("kind13 ALL fields changed")
            icon = struct.unpack_from("<I", help_data, ea + 64)[0]
            colour = string(help_data, ea + 48, h_floor)
            if not re.fullmatch(r"<[Cc][0-9a-fA-F]+>", colour):
                raise ValueError("kind13 ALL colour changed")
            phrases = [
                s + (" " if locale == "ko" else "") + f.replace("%s", magnitude)
                if locale in ("ja", "zh-Hans", "zh-Hant", "ko")
                else f.replace("%s", magnitude) + s
                for locale, s, f, magnitude in zip(locales, stat, form, all_values)
            ]
            variants = [f"<C9><I{icon}></C>%s", colour + f"<C9><I{icon}></C>%s</C>"]
            # A complete physical item frame owns both native icon styling
            # and its plain projection. The legacy standalone name contract
            # remains unchanged outside this proven frame.
            variants.append(f"<I{icon}>%s")
            for template in variants:
                values = [template.replace("%s", phrase) for phrase in phrases]
                owned[values[0]] = {
                    "source": values[0],
                    "pair": values[1:],
                    "semantic_ids": [stem + "/stat", stem + "/format", all_key],
                    "parameters": [],
                    "atomic": True,
                }
        if owned:
            row["owned_effect_units"] = owned
            audit["kind13_all_item_frames"] += 1
    for row in rows:
        if len(bodies[row["body"]]) < 2:
            continue
        at = it[0] + row["physical"] * it[1]
        slots = [
            struct.unpack_from("<4I", item, at + 60 + 16 * j)
            for j in range(5)
            if struct.unpack_from("<I", item, at + 60 + 16 * j)[0]
        ]
        ordinary, deferred = [[], []], [[], []]
        valid = True
        for identifier, amount, turns, strength in slots:
            ea = effect_rows.get(identifier)
            if ea is None or identifier not in (95, 96, 122, 124):
                valid = False
                break
            mode = struct.unpack_from("<I", help_data, ea + 28)[0]
            ptr, n = struct.unpack_from("<QI", help_data, ea + 16)
            types = struct.unpack_from(f"<{n}I", help_data, ptr)
            if mode != 0 or types != (() if identifier in (95, 96) else (1,)):
                valid = False
                break
            name = string(help_data, ea + 8, h_floor)
            if identifier in (122, 124):
                if re.findall(r"%%|%[^%]*?[a-zA-Z]", name) != ["%d"]:
                    valid = False
                    break
                name = name.replace("%d", str(amount))
            elif "%" in name or sum(s[0] in (95, 96) for s in slots) != 1:
                valid = False
                break
            icon = struct.unpack_from("<I", help_data, ea + 64)[0]
            colour = string(help_data, ea + 48, h_floor)
            if not re.fullmatch(r"<[Cc][0-9a-fA-F]+>", colour):
                valid = False
                break
            dest = deferred if identifier in (95, 96) else ordinary
            dest[0].append(f"<I{icon:03d}>" + name)
            dest[1].append(f"<I{icon:03d}>" + colour + name + "</C>")
        if valid:
            row["body_effect_sources"] = [" - ".join(ordinary[i] + deferred[i]) for i in range(2)]
            audit["ambiguous_body_effect_bound"] += 1
        else:
            audit["ambiguous_body_unproved_effects"] += 1

    # CAB62's ordinary item constructor uses the literal " - %s%s" between
    # effects. FORMAT8 is the separate comma/slash connection domain.
    # This join is admitted only behind the complete item prefix + body proof.
    def distinct_constructors(values):
        result = {}
        for row in values:
            signature = json.dumps([row["prefix"], row["parts"], row.get("close")], sort_keys=True)
            if signature not in result:
                result[signature] = {**row, "item_ids": [], "physical_items": []}
            result[signature]["item_ids"].append(row["item_id"])
            result[signature]["physical_items"].append(row["physical"])
        return list(result.values())

    return {
        "schema": 2,
        "rows": rows,
        "compact_rows": distinct_constructors(compact_rows),
        "attack_rows": distinct_constructors(attack_rows),
        "audit": dict(audit),
        "native_effect_join": [" - ", " - ", " - "],
    }
