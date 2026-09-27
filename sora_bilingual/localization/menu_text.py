"""Resolve complete menu strings and their explicit formatted components.

No fuzzy translation or character-substring replacement: a component must be
an entire indexed string or an unambiguous numeric printf instance. Native
icons, colours and separators are copied literally around translated runs.
"""

import re
from sora_bilingual.config.locales import DEFAULT_PRIMARY

TOKEN = re.compile(r"(<[^<>]*>|\r\n|\n|\\n)")
STYLE = re.compile(r"</?[Cc][0-9a-fA-F]*>|<s\d+>")
FORMAT = re.compile(r"%(?:\d+\$)?[-+0 #]*(?:\d+)?(?:\.\d+)?[dius]")
FORMAT_TOKEN = re.compile(r"%%|" + FORMAT.pattern)
SEPARATORS = re.compile(
    r"(\r\n|\n|\\n|[【】「」：:／/]| - |[ \u3000]{2,}|^[ \u3000]*[·・][ \u3000]*)"
)
LINE_BREAK = re.compile(r"\r\n|\n|\\n")
LINE_START_PUNCTUATION = frozenset("、。！？）】》〉」』〕］｝")


def _format_remainder(value):
    """Remove supported printf fields and escaped literal percent signs."""
    return FORMAT_TOKEN.sub("", value)


def _format_fields(value):
    return [match for match in FORMAT_TOKEN.finditer(value) if match.group() != "%%"]


def _render_format(template, values):
    return FORMAT_TOKEN.sub(lambda match: "%" if match.group() == "%%" else next(values), template)


def _latin_word_character(value):
    return (
        "A" <= value <= "Z"
        or "a" <= value <= "z"
        or "0" <= value <= "9"
        or "\u00c0" <= value <= "\u024f"
    )


def _secondary_text(lines):
    """Join wrapped source lines while retaining word boundaries in Latin text."""
    result = []
    for line in lines:
        if (
            result
            and result[-1]
            and line
            and _latin_word_character(result[-1][-1])
            and _latin_word_character(line[0])
        ):
            result.append(" ")
        result.append(line)
    return "".join(result)


def _secondary_units(text):
    result = []
    at = 0
    while at < len(text):
        if text.startswith("<R>", at):
            close = text.find("</R", at + 3)
            if close < 0:
                return None
            end = text.find(">", close)
            if end < 0:
                return None
            value = text[at : end + 1]
            base = text[at + 3 : close]
            result.append((value, sum(not char.isspace() for char in base), False))
            at = end + 1
            continue
        if text[at] == "<":
            tag = re.match(r"<[^<>]*>", text[at:])
            if not tag or not re.fullmatch(r"</?[Cc][0-9a-fA-F]*>|</?B>|<[sS]\d+>|<I\d+>", tag[0]):
                return None
            result.append((tag[0], 0, True))
            at += len(tag[0])
            continue
        end = at + 1
        if _latin_word_character(text[at]):
            while end < len(text) and _latin_word_character(text[end]):
                end += 1
            while (
                end + 1 < len(text) and text[end] in "'’‐-" and _latin_word_character(text[end + 1])
            ):
                end += 2
                while end < len(text) and _latin_word_character(text[end]):
                    end += 1
        value = text[at:end]
        result.append((value, sum(not char.isspace() for char in value), False))
        at = end
    return result


def _reflow_secondary_paragraph(text, capacities):
    units = _secondary_units(text)
    if units is None:
        return None
    result = []
    state = {"colours": [], "bold": False, "size": ""}

    def update(tag):
        if re.fullmatch(r"<[Cc][0-9a-fA-F]*>", tag):
            state["colours"].append(tag)
        elif tag == "</C>":
            if state["colours"]:
                state["colours"].pop()
        elif tag == "<B>":
            state["bold"] = True
        elif tag == "</B>":
            state["bold"] = False
        elif re.fullmatch(r"<[sS]\d+>", tag):
            state["size"] = tag

    def prefix():
        return "".join(state["colours"]) + ("<B>" if state["bold"] else "") + state["size"]

    def close():
        return ("</B>" if state["bold"] else "") + "</C>" * len(state["colours"])

    def starts_punctuation():
        for value, width, _ in units:
            if width:
                return value[0] in LINE_START_PUNCTUATION
        return False

    def append(line):
        value, width, tag = units.pop(0)
        line.append(value)
        if tag:
            update(value)
        return width

    for number, capacity in enumerate(capacities):
        if not capacity:
            # A pure icon/control line has no annotation anchor. Carry its
            # style state forward without spending a translated character.
            line = [prefix()]
            while units and units[0][2]:
                append(line)
            result.append("".join(line) + close())
            continue
        if not any(capacities[number + 1 :]):
            line = [prefix()]
            while units:
                append(line)
            result.append("".join(line) + close())
            continue
        while result and units and units[0][1] and units[0][0].isspace():
            result[-1] += units.pop(0)[0]
        line = [prefix()]
        used = 0
        remaining_capacity = sum(capacities[number:])
        remaining_text = sum(width for _, width, _ in units)
        target = max(1, -(-remaining_text * capacity // remaining_capacity))
        while units and (not line or used < target):
            used += append(line)
        while units and units[0][2] and units[0][0] in ("</C>", "</B>"):
            append(line)
        while units and starts_punctuation():
            used += append(line)
        result.append("".join(line) + close())
    return result


def reflow_annotation_lines(primary, secondary):
    """Return secondary payload lines aligned to primary lines with safe display markup.

    Localized book pages often retain different physical wraps. Paragraphs are
    paired by blank-line boundaries, then their secondary text is repartitioned
    across the available primary lines. Dialogue controls in the primary are
    zero-width. Ruby is atomic, and active color/bold/size context is closed
    and reopened for each independent annotation payload. Unknown or malformed
    tags return ``None`` so callers retain their conservative fallback.
    """
    left = LINE_BREAK.split(primary)
    right = LINE_BREAK.split(secondary)
    result = [""] * len(left)

    def paragraphs(lines):
        groups, current = [], []
        for index, line in enumerate(lines):
            if line.strip():
                if current and line[0].isspace():
                    groups.append(current)
                    current = []
                current.append((index, line))
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        return groups

    left_groups = paragraphs(left)
    right_groups = paragraphs(right)
    if not left_groups:
        return result
    if len(left_groups) == len(right_groups):
        groups = zip(left_groups, right_groups)
    else:
        groups = [(sum(left_groups, []), sum(right_groups, []))]
    for left_group, right_group in groups:
        text = _secondary_text([line for _, line in right_group])
        capacities = [
            sum(not char.isspace() for char in re.sub(r"<[^<>]*>", "", line))
            for _, line in left_group
        ]
        reflowed = _reflow_secondary_paragraph(text, capacities)
        if reflowed is None:
            return None
        for (index, _), value in zip(left_group, reflowed):
            result[index] = value
    return result


def complete_pair(texts, primary, secondary):
    values = (texts.get(primary), texts.get(secondary))
    return values if all(isinstance(t, str) and t.strip() for t in values) else None


def visual_secondary(text):
    """Keep display markup; never replay dialogue timing/event commands."""
    return re.sub(
        r"<[^<>]*>",
        lambda m: (
            m[0]
            if re.fullmatch(r"<R>|</R[^<>]*>|</?[Cc][0-9a-fA-F]*>|</?B>|<[sS]\d+>|<I\d+>", m[0])
            else ""
        ),
        text,
    )


def close_colours(text):
    depth = 0
    for tag in re.findall(r"</?[Cc][0-9a-fA-F]*>", text):
        depth = max(0, depth - 1) if tag.startswith("</") else depth + 1
    return "</C>" * depth


def annotation_plan(primary, secondary):
    """An independent native annotation lane, with the primary bytes intact.

    The empty ruby is only an anchor. The native adapter supplies its payload
    separately and suppresses its cursor/line compensation. It must NOT be
    rendered by a bare game parser without that adapter.
    """
    lines = re.split(r"(\r\n|\n|\\n)", primary)
    visible = visual_secondary(secondary)
    right = re.split(r"\r\n|\n|\\n", visible)
    left_count = (len(lines) + 1) // 2
    needs_reflow = left_count != len(right) or any(
        bool(a.strip()) != bool(b.strip()) for a, b in zip(lines[::2], right)
    )
    if needs_reflow or "<" in visible:
        reflowed = reflow_annotation_lines(primary, visible)
        if reflowed is not None:
            right = reflowed
        elif needs_reflow:
            # Markup can carry state across lines, so do not repartition it.
            # Keep the complete secondary paragraph in one annotation lane.
            payload = " ".join(right)
            right = [""] * left_count
            anchor = next((i for i, line in enumerate(lines[::2]) if line.strip()), 0)
            right[anchor] = payload
    out = ""
    layers = []
    for i, part in enumerate(lines):
        if i % 2:
            out += part
            continue
        payload = right[i // 2]
        if needs_annotation(part, payload):
            layers.append(
                {
                    "offset": len(out.encode("utf-8")) + 6,
                    "text": payload,
                    "primary": part,
                    "protected": "<R>" in primary or "<R>" in secondary,
                }
            )
            out += "<R></R_>"
        out += part
    return {"text": out, "layers": layers, "kind": "layered"}


def plain(text):
    """Remove colour/size controls, never icons or unknown commands."""
    return STYLE.sub("", text)


def display_text(text):
    return re.sub(r"^(?:<#[^<>]*>)+", "", text)


def _without_line_padding(text):
    """Compare full display records without their line-edge alignment spaces.

    Keep every interior word boundary, line break, punctuation mark and tag.
    This is an ambiguity check, never a rewrite of the chosen display text.
    """
    result = []
    for line in text.split("\n"):
        line = re.sub(r"^((?:<[^<>]*>)*)([ \t\u3000]+)", r"\1", line)
        line = re.sub(r"[ \t\u3000]+(?=(?:<[^<>]*>)*$)", "", line)
        result.append(line)
    return "\n".join(result)


def ruby(primary, secondary):
    if not primary or not secondary:
        return primary
    if not needs_annotation(primary, secondary):
        return primary
    identical_cjk = primary == secondary and bool(
        re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", primary)
    )
    if primary == secondary and not identical_cjk:
        return primary
    # A ruby body cannot contain nested tags. Controls live outside its runs.
    if "<" in primary + secondary or ">" in primary + secondary:
        return None
    p = re.split(r"(\r\n|\n)", primary.replace("\\n", "\n"))
    s = re.split(r"\r\n|\n", secondary.replace("\\n", "\n"))
    if (len(p) + 1) // 2 != len(s):
        return None  # needs independent annotation lanes
    out = []
    for i, a in enumerate(p):
        if i % 2:
            out.append(a)
            continue
        b = s[i // 2]
        if bool(a.strip()) != bool(b.strip()):
            return None
        out.append("<R>" + a + "</R" + b + ">" if needs_annotation(a, b) else a)
    return "".join(out)


def needs_annotation(a, b):
    def visible(value):
        value = re.sub(r"<[^<>]*>", "", value)
        return re.sub(r"[\uff01-\uff5e]", lambda m: chr(ord(m[0]) - 0xFEE0), value).strip()

    left, right = visible(a), visible(b)
    if not left or not right:
        return False
    if left != right:
        return True
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", left))


def overdrive_descriptions(entries):
    """Expand the game's six-slot template using one validated table record.

    This is not a word-level match: a displayed description must equal a
    complete assembled record. Empty optional fields stay empty.
    """
    template = next(
        (
            e["texts"]
            for e in entries
            if e.get("key") == "table/t_text.tbl/TXT_CAMP_STATUS_OVERDRIVE_INFO_TEMPLATE"
        ),
        None,
    )
    if not template:
        return []
    rows = {}
    for e in entries:
        if e.get("key", "").startswith("table/t_condition_info.tbl/OverDriveEffect/"):
            record, field = e["key"].rsplit("/", 1)
            rows.setdefault(record, {})[field] = e["texts"]
    result = []
    slots = ("common_effect", "accuracy", "critical", "effect_1", "effect_2", "effect_3")
    for key, fields in rows.items():
        texts = {}
        for lang in fields.get("name", {}):
            pattern = template.get(lang, "")
            if pattern.count("%s") != 6 or "%" in pattern.replace("%s", ""):
                continue
            texts[lang] = pattern % tuple(fields.get(field, {}).get(lang, "") for field in slots)
        if texts:
            result.append({"key": key + "/assembled_description", "texts": texts})
            result.append(
                {
                    "key": key + "/assembled_description_trimmed",
                    "texts": {k: v.rstrip() for k, v in texts.items()},
                }
            )
    return result


# Verified SkillRangeHelpData labels whose localized text reserves a trailing
# size slot in all eight archives. Fixed ranges and short_label fields do not.
ITEM_HELP_SIZED_RANGE_LABELS = {
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:13a1faa6d4288b2afaeb29863719e1929285152bee56b5943ea806442b6fff7b/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:19510ff635267619528cd597284f4a27a4051bb07c1a9ed8a0b320811e6b310b/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:27305a59b8f293e11d3712075fef8ced814a6acd60f6a8d4b81c5a7a9d963dca/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:2a2c762e0d6517c7db916fe291eb0c21a61dbb9804f6b0c338a115132e4962f9/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:2f8d4eacb3b590c7e88136642ff0cf2812b5b296dec70f6533e462527cd441f5/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:5b40935541146eb96f3ddffaf699e2fe36b1489a9fe9b1691fabdbe19b699e70/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:69edb917c527c1cd62e5da007c513cc9a9247ac40194c275e1fc333e6d059dce/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:6a15f570d7d4b310463cc8eb627186cd7e4586d9ab2b87e663ebb1e538c2d090/label",
    "table/t_itemhelp.tbl/SkillRangeHelpData/sha256:d3740e2d93482a970bdc5c805bb0e4ef863b2ca6ce6809551f3f17f1784c3783/label",
}

# This name has no /stat field, but captured native output proves that its %s
# receives TXT_ITEM_HELP_* magnitude text. Other stat-less %s names can take an
# attribute or another argument kind and are deliberately excluded.
ITEM_HELP_GRADE_NAMES = {
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:93e17b497b0a5e2d8a6b21a7b66f0a4f5ccf0c6c214838a10ff8a55793b9898f/name",
}


# SkillEffectHelpData IDs 123/125 are the HP/EP percentage recovery records.
# Native builder 0x34d016..0x34d1de composes stat + format + percentage;
# 0x34d347..0x34d4c0 puts stat last for the Western locale group.
ITEM_HELP_PERCENT_RECOVERY = (
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:cc311d9666993ad7471edb97a4292bd44de5cac259718aab39db45a6008a99a8",
    "table/t_itemhelp.tbl/SkillEffectHelpData/sha256:9792ad85797c0b1a6ea1d3a7efb83d51b75a2d47d37d762623d852392fa0595e",
)


def item_help_recovery_entries(entries):
    """Verified numeric/all-value recovery templates, for anchored details only."""
    named = {e["key"]: e["texts"] for e in entries if "key" in e}
    result = []
    for base in ITEM_HELP_PERCENT_RECOVERY:
        stats, formats = named.get(base + "/stat", {}), named.get(base + "/format", {})
        # The first stat may carry SELF/FRIEND (0x34cf9f, 0x34d45b).
        # LINK belongs to the multi-stat aggregation loop, not a prefix.
        for prefix in ("", "SELF", "FRIEND"):
            prefixes = named.get("table/t_text.tbl/TXT_ITEM_HELP_" + prefix, {})
            for modifier in ("PERSENT", "ALL"):
                values = named.get("table/t_text.tbl/TXT_ITEM_HELP_" + modifier, {})
                combined = {}
                for language, form in formats.items():
                    stat, value = stats.get(language), values.get(language)
                    if (
                        not stat
                        or not value
                        or form.count("%s") != 1
                        or "%" in form.replace("%s", "")
                        or (prefix and not prefixes.get(language))
                    ):
                        continue
                    stat = prefixes.get(language, "") + stat
                    phrase = form.replace("%s", value)
                    combined[language] = (
                        stat + (" " if language == "ko" else "") + phrase
                        if language in ("ja", "zh-Hans", "zh-Hant", "ko")
                        else phrase + stat
                    )
                if combined:
                    result.append(
                        {
                            "key": base + "/native_recovery/" + prefix + "/" + modifier,
                            "texts": combined,
                            "detail_authority": True,
                        }
                    )
    return result


def item_help_components(entries):
    """Index the resource-defined combinations built by the item-help UI.

    Audited geometric labels concatenate a localized size. Effect names with
    a non-empty sibling /stat field substitute a localized magnitude, as does
    the one stat-less delay record observed in native output. Never cross
    format/attribute/numeric slots with these modifiers. Missing locales and
    collisions retain the normal pair-admission checks.
    """
    named = {e["key"]: e["texts"] for e in entries if "key" in e}
    ranges = [
        (key, texts)
        for key, texts in named.items()
        if key.startswith("table/t_text.tbl/TXT_ITEM_HELP_RANGE_")
        and key.rsplit("_", 1)[-1] in {"S", "M", "L", "LL"}
    ]
    magnitudes = [
        (key, texts)
        for key, texts in named.items()
        if key.removeprefix("table/t_text.tbl/TXT_ITEM_HELP_")
        in {"MOSTSMALL", "SMALL", "MIDDLE", "LARGE", "MOSTLARGE"}
    ]
    result = []
    for key, texts in named.items():
        is_range = key in ITEM_HELP_SIZED_RANGE_LABELS
        base = key.removesuffix("/name")
        stat = named.get(base + "/stat") if key.endswith("/name") else None
        is_effect = key in ITEM_HELP_GRADE_NAMES or bool(
            stat and any(value.strip() for value in stat.values())
        )
        if not (is_range or is_effect):
            continue
        for modifier_key, modifiers in ranges if is_range else magnitudes:
            combined = {}
            for language, value in texts.items():
                modifier = modifiers.get(language)
                if not value.strip() or not modifier or not modifier.strip():
                    continue
                if is_range:
                    if "%" not in value + modifier:
                        combined[language] = value + modifier
                elif value.count("%s") == 1 and "%" not in value.replace("%s", "") + modifier:
                    combined[language] = value.replace("%s", modifier)
            if combined:
                result.append(
                    {"key": key + "/composed/" + modifier_key.rsplit("/", 1)[-1], "texts": combined}
                )
    return result


def item_help_detail_entries(entries):
    """Return exact aliases used only inside an anchored item/skill detail.

    Native colour tags can split an effect template around its magnitude. A
    fragment is safe only when every locale has one string slot at the same
    outer edge. Magnitudes are scoped here because values such as ``中`` are
    ambiguous outside item help.
    """
    named = {e["key"]: e["texts"] for e in entries if "key" in e}
    magnitudes = [
        (key, texts)
        for key, texts in named.items()
        if key.removeprefix("table/t_text.tbl/TXT_ITEM_HELP_")
        in {"MOSTSMALL", "SMALL", "MIDDLE", "LARGE", "MOSTLARGE"}
    ]
    # Constructor formats and punctuation are not independently translated
    # effects. Their argument/order contracts must be generated explicitly.
    result = [
        e
        for e in entries
        if e.get("key", "").startswith("table/t_text.tbl/TXT_ITEM_HELP_")
        and all("%" not in t for t in e["texts"].values())
        and any(any(c.isalpha() for c in plain(t)) for t in e["texts"].values())
    ]
    result += item_help_recovery_entries(entries)
    result += [
        {
            "key": "table/t_itemhelp.tbl/generated/magnitude/" + key.rsplit("/", 1)[-1],
            "texts": texts,
        }
        for key, texts in magnitudes
    ]
    result.extend(
        {
            "key": key + "/detail_authority",
            "texts": texts,
            "detail_authority": True,
        }
        for key, texts in named.items()
        if key.startswith("table/t_itemhelp.tbl/SkillRangeHelpData/") and key.endswith("/label")
    )
    for key, texts in named.items():
        if not key.endswith("/name"):
            continue
        stat = named.get(key.removesuffix("/name") + "/stat")
        if key not in ITEM_HELP_GRADE_NAMES and not (
            stat and any(value.strip() for value in stat.values())
        ):
            continue
        if not texts or any(
            value.count("%s") != 1 or "%" in value.replace("%s", "") for value in texts.values()
        ):
            continue
        edges = {
            "prefix" if value.endswith("%s") else "suffix" if value.startswith("%s") else None
            for value in texts.values()
        }
        if len(edges) != 1 or None in edges:
            continue
        edge = next(iter(edges))
        fragments = {language: value.replace("%s", "") for language, value in texts.items()}
        if all(value.strip() for value in fragments.values()):
            result.append(
                {
                    "key": key + "/fragment/" + edge,
                    "texts": fragments,
                    "detail_authority": True,
                }
            )
    return result


class MenuTranslator:
    def __init__(
        self, entries, primary, secondary, source_language=DEFAULT_PRIMARY, _details_only=False
    ):
        entries = list(entries)
        detail_aliases = []
        if not _details_only:
            detail_aliases = item_help_detail_entries(entries)
            entries += overdrive_descriptions(entries)
            entries += item_help_components(entries)
            # The game appends a numeric level to this localized resource.
            # Its prefix, punctuation and spaces all come from that locale.
            entries += [
                {
                    "key": e["key"] + "/formatted",
                    "texts": {l: t + "%d" for l, t in e["texts"].items()},
                }
                for e in entries
                if e.get("key") == "table/t_text.tbl/TXT_SAVE_DETAIL_LEVEL"
            ]
        self.same_language = primary == secondary
        self.scoped = {}
        self.detail_sources = set()
        self.details = None
        if not _details_only:
            for scope, prefix in [
                ("support", "table/t_support_ability.tbl/"),
                ("overdrive", "table/t_condition_info.tbl/OverDriveEffect/"),
                ("item_name", "table/t_item.tbl/"),
            ]:
                selected = [
                    e
                    for e in entries
                    if e.get("key", "").startswith(prefix)
                    and (scope != "item_name" or e["key"].endswith("/name"))
                ]
                if selected:
                    self.scoped[scope] = MenuTranslator(
                        selected, primary, secondary, source_language, True
                    )
            item_help_headers = {
                e["texts"][source_language]
                for e in entries
                if e.get("key", "").startswith("table/t_itemhelp.tbl/ItemKindHelpData/")
                and e.get("key", "").endswith("/description")
                and source_language in e["texts"]
            }
            detail_entries = [
                e
                for e in entries
                if e.get("key", "").startswith(
                    (
                        "table/t_item.tbl/",
                        "table/t_itemhelp.tbl/",
                        "table/t_skill.tbl/",
                        "table/t_support_ability.tbl/",
                    )
                )
                and not (
                    e.get("key", "").startswith("table/t_item.tbl/ItemKindParam2/")
                    and e.get("texts", {}).get(source_language) in item_help_headers
                )
            ]
            detail_entries += detail_aliases
            descriptions = {
                e["texts"][source_language]
                for e in detail_entries
                if e.get("key", "").endswith("/description") and source_language in e["texts"]
            }
            self.detail_sources = descriptions | {"<C0>" + value for value in descriptions}
            if detail_entries:
                self.details = MenuTranslator(
                    detail_entries, primary, secondary, source_language, True
                )
        self.keyed = []
        candidates = {}
        display_candidates = {}
        detail_authority = {}
        for entry in entries:
            texts = entry["texts"]
            pair = complete_pair(texts, primary, secondary)
            display_record = entry.get("display_role") in ("dialogue", "speaker")
            prefix = "table/t_text.tbl/"
            if pair and source_language in texts and entry.get("key", "").startswith(prefix):
                self.keyed.append((entry["key"][len(prefix) :], texts[source_language], pair))
            for value in {texts[source_language]} if source_language in texts else set():
                for source in {value, plain(value)}:
                    if source.strip():
                        candidates.setdefault(source, set()).add(pair)
                        if entry.get("detail_authority") and pair:
                            detail_authority.setdefault(source, set()).add(pair)
                        if display_record and pair:
                            display_candidates.setdefault(source, set()).add(pair)
                # Native dialogue controls may be consumed before SetText.
                # Keep a separate complete display variant, not a substring match.
                visible = display_text(value)
                if visible != value and visible.strip():
                    candidates.setdefault(visible, set()).add(
                        tuple(display_text(t) for t in pair) if pair else None
                    )
                    if display_record and pair:
                        display_candidates.setdefault(visible, set()).add(
                            tuple(display_text(t) for t in pair)
                        )
        # Complete, structurally aligned display records are stronger evidence
        # than an unpaired bytecode fragment. Missing fragments are not a second
        # translation. Actual conflicting translations remain quarantined.
        self.ambiguous_display = set()
        for source, pairs in display_candidates.items():
            if len(pairs) == 1 and candidates[source] - {None} == pairs:
                candidates[source] = pairs
            elif len(pairs) > 1:
                # Airport signs reuse the same source paragraph with only
                # localized centering spaces changed between map instances.
                # Those are not different translations. Pick one complete
                # original pair deterministically; never remove its padding.
                complete = candidates[source] - {None}
                normalized_pairs = {
                    tuple(_without_line_padding(value) for value in pair) for pair in complete
                }
                if len(normalized_pairs) == 1:
                    candidates[source] = {min(pairs, key=lambda pair: (sum(map(len, pair)), pair))}
                else:
                    self.ambiguous_display.add(source)
        # Name/status records are the display-name authority. Script voice
        # identifiers can reuse the same source while omitting a locale (or
        # retaining its Japanese identifier in the English slot). Only exact
        # complete names get this fallback; conflicting name tables stay denied.
        names = {}
        for entry in entries:
            key = entry.get("key", "")
            texts = entry["texts"]
            if (
                key.startswith(("table/t_name.tbl/", "table/t_status.tbl/"))
                and key.endswith("/name")
                and source_language in texts
            ):
                pair = complete_pair(texts, primary, secondary)
                names.setdefault(texts[source_language], set()).add(pair)
        for source, pairs in names.items():
            if len(pairs) == 1 and None not in pairs:
                candidates[source] = pairs
                self.ambiguous_display.discard(source)
        # Resource-generated fragments are valid only in the already-anchored
        # detail model. Prefer their spacing over a colliding standalone stat
        # record when native colour tags split the original name template.
        for source, pairs in detail_authority.items():
            if len(pairs) == 1:
                candidates[source] = pairs
                self.ambiguous_display.discard(source)
        self.pairs = {
            s: next(iter(p)) for s, p in candidates.items() if len(p) == 1 and None not in p
        }
        # Formatting-only differences do not make a translation ambiguous.
        normalized = {}
        for source, pairs in candidates.items():
            p = {None if v is None else (plain(v[0]), plain(v[1])) for v in pairs}
            if len(p) == 1 and None not in p:
                normalized[source] = next(iter(p))
        self.plain_pairs = normalized
        self.numeric = []
        self.raw_numeric = []
        self.detail_numeric = []
        for source, pair, is_raw in [(s, p, False) for s, p in normalized.items()] + [
            (s, p, True) for s, p in self.pairs.items() if "<" in s
        ]:
            matches = _format_fields(source)
            if (
                not matches
                or len(matches) > 4
                or any("%" in _format_remainder(t) for t in (source, *pair))
            ):
                continue
            # Number arguments retain order unless explicit positional slots are
            # available; reject mismatched placeholder contracts.
            if any(len(_format_fields(t)) != len(matches) for t in pair):
                continue
            if any("$" in m.group() for t in (source, *pair) for m in _format_fields(t)):
                continue
            kinds = [m.group()[-1] for m in matches]
            if any([m.group()[-1] for m in _format_fields(t)] != kinds for t in pair):
                continue
            if "s" in kinds and len(_format_remainder(source).strip()) < 2:
                continue
            chunks = []
            at = 0
            for m in matches:
                chunks.extend(
                    (
                        re.escape(source[at : m.start()].replace("%%", "%")),
                        r"([^<>\r\n]{1,512}?)" if m.group()[-1] == "s" else r"([+-]?\d+)",
                    )
                )
                at = m.end()
            chunks.append(re.escape(source[at:].replace("%%", "%")))
            rule = (re.compile("".join(chunks)), pair)
            (self.raw_numeric if is_raw else self.numeric).append(rule)
            if not is_raw and source in detail_authority and "s" not in kinds:
                self.detail_numeric.append(rule)

    def raw_pair(self, source):
        if source in self.pairs:
            return self.pairs[source]
        if "<" not in source:
            return None
        matches = set()
        for pattern, pair in self.raw_numeric:
            m = pattern.fullmatch(source)
            if not m:
                continue
            rendered = []
            for side, target in enumerate(pair):
                values = iter(self.plain_pairs.get(v, (v, v))[side] for v in m.groups())
                rendered.append(_render_format(target, values))
            matches.add(tuple(rendered))
        return next(iter(matches)) if len(matches) == 1 else None

    def pair(self, source):
        if source in self.plain_pairs:
            return self.plain_pairs[source]
        # An audited detail constructor is more precise than a free-form %s
        # name/format that can also consume the whole numeric effect phrase.
        authoritative = set()
        for pattern, pair in self.detail_numeric:
            m = pattern.fullmatch(source)
            if m:
                authoritative.add(tuple(_render_format(t, iter(m.groups())) for t in pair))
        if authoritative:
            return next(iter(authoritative)) if len(authoritative) == 1 else None
        matches = set()
        for pattern, pair in self.numeric:
            m = pattern.fullmatch(source)
            if m:
                rendered = []
                for side, target in enumerate(pair):
                    # Name arguments are translated only by an exact known pair;
                    # unknown player-defined values are preserved verbatim.
                    values = iter(self.plain_pairs.get(v, (v, v))[side] for v in m.groups())
                    rendered.append(_render_format(target, values))
                matches.add(tuple(rendered))
        return next(iter(matches)) if len(matches) == 1 else None

    def component(self, source, mode):
        pair = self.pair(source)
        if pair:
            a, b = pair
            if mode == "primary":
                return a
            if mode == "secondary":
                return b
            value = ruby(a, b)
            if value is not None:
                return value
        # Whitespace and punctuation delimit complete indexed components.
        stripped = source.strip()
        if stripped != source and stripped:
            inner = self.component(stripped, mode)
            if inner != stripped:
                start = source.index(stripped)
                return source[:start] + inner + source[start + len(stripped) :]
        parts = SEPARATORS.split(source)
        if len(parts) > 1:
            return "".join(
                self.component(p, mode) if i % 2 == 0 else p for i, p in enumerate(parts)
            )
        return source

    def translate(self, source, mode="annotation"):
        if mode == "bilingual":
            mode = "annotation"
        if self.same_language and mode == "annotation":
            mode = "primary"
        # The game's item/skill description constructor appends the complete
        # database description after an effect header. That exact suffix is an
        # anchor for resolving header terms within the item/skill tables, where
        # a word like 强化 means 強化 rather than the shop command 強化する.
        if self.details and "\n" in source:
            for at, c in enumerate(source):
                if c == "\n" and source[at + 1 :] in self.detail_sources:
                    return self.details.translate(source, mode)
        # A real complete-dialogue conflict must not re-enter via a generic
        # printf template or smaller fragments after its exact pair was denied.
        if source in self.ambiguous_display or display_text(source) in self.ambiguous_display:
            return source
        pair = self.raw_pair(source)
        if pair and mode in ("primary", "secondary"):
            return pair[0 if mode == "primary" else 1]
        controls = re.match(r"^(?:<#[^<>]*>)+", source)
        if controls:
            # Live emotion state can differ from the script's literal header.
            # Resolve the complete display body before splitting its lines.
            return controls[0] + self.translate(source[controls.end() :], mode)
        if "<R>" in source:
            # Dialogue constructors prepend speaker/emotion controls and join
            # catalogued lines. Keep ruby atomic while resolving those lines.
            parts = re.split(r"(<#[^<>]*>|\r\n|\n|\\n)", source)
            if len(parts) > 1:
                return "".join(t if i % 2 else self.translate(t, mode) for i, t in enumerate(parts))
            return source  # handled by render(), never nested
        # A whole plain sentence gets one complete translation, even when its
        # wording contains punctuation used as a composite UI separator.
        if "<" not in source and ">" not in source:
            whole = self.component(source, mode)
            if whole != source:
                return whole
        return "".join(
            t if i % 2 else self.component(t, mode) for i, t in enumerate(TOKEN.split(source))
        )

    def render(self, source, mode="annotation"):
        """Return text plus owned annotation metadata, including original ruby."""
        if mode == "bilingual":
            mode = "annotation"
        if self.same_language and mode == "annotation":
            mode = "primary"
        a = self.translate(source, "primary")
        b = self.translate(source, "secondary")
        if mode == "annotation" and (
            not needs_annotation(a, b)
            or (a == b == source and display_text(source) in self.ambiguous_display)
        ):
            return {"text": a, "layers": [], "kind": "plain"}
        known = self.raw_pair(source) is not None or self.raw_pair(display_text(source)) is not None
        if mode == "annotation" and known:
            prefix = re.match(r"^(?:<#[^<>]*>)*", a)[0]
            body = a[len(prefix) :]
            visible_b = visual_secondary(b)
            if (
                prefix
                and "<" not in body + visible_b
                and len(re.split(r"\r\n|\n|\\n", body)) == len(re.split(r"\r\n|\n|\\n", visible_b))
            ):
                value = ruby(body, visible_b)
                if value is not None:
                    text = prefix + value
                    return {
                        "text": text,
                        "layers": [],
                        "kind": "ruby" if text != source else "plain",
                    }
        left = re.split(r"\r\n|\n|\\n", a)
        right = re.split(r"\r\n|\n|\\n", b)
        different_lines = len(left) != len(right) or any(
            bool(x.strip()) != bool(y.strip()) for x, y in zip(left, right)
        )
        if mode == "annotation" and (
            (known and (any(c in a + b for c in "<>") or different_lines))
            or (a != b and ("<R>" in a + b or different_lines))
        ):
            # Original tags remain byte-for-byte in the primary text. A
            # separate lane avoids nested ruby and preserves native notation.
            if visual_secondary(b).strip():
                return annotation_plan(a, b)
        text = self.translate(source, mode)
        return {
            "text": text,
            "layers": [],
            "kind": "ruby"
            if mode == "annotation" and text != source and "<R>" in text
            else "plain",
        }

    def dictionary(self, mode):
        if self.same_language and mode == "annotation":
            mode = "primary"
        result = {s: t for s in self.pairs if (t := self.translate(s, mode)) != s}
        for scope, tr in self.scoped.items():
            result.update(
                {
                    "\x02" + scope + "\x00" + s: t
                    for s in tr.pairs
                    if (t := tr.translate(s, mode)) != s
                }
            )
        for key, source, (a, b) in self.keyed:
            one = MenuTranslator(
                [{"texts": {"source": source, "primary": a, "secondary": b}}],
                "primary",
                "secondary",
                "source",
            )
            text = one.translate(source, mode)
            if text != source:
                result["\x01" + key + "\x00" + source] = text
        return result

    def runtime_model(self):
        """Serialize bounded matching rules once; resolve new text in-game."""
        keyed = {}
        for key, source, (a, b) in self.keyed:
            one = MenuTranslator(
                [{"texts": {"source": source, "primary": a, "secondary": b}}],
                "primary",
                "secondary",
                "source",
                True,
            )
            keyed[key] = {"source": source, "model": one.runtime_model()}
        return {
            "pairs": self.pairs,
            "plain_pairs": self.plain_pairs,
            "numeric": [(pattern.pattern, pair) for pattern, pair in self.numeric],
            "raw_numeric": [(pattern.pattern, pair) for pattern, pair in self.raw_numeric],
            "detail_numeric": [(pattern.pattern, pair) for pattern, pair in self.detail_numeric],
            "same_language": self.same_language,
            "ambiguous_display": sorted(self.ambiguous_display),
            "keyed": keyed,
            "detail_sources": sorted(self.detail_sources),
            "details": self.details.runtime_model() if self.details else None,
            "scoped": {k: v.runtime_model() for k, v in self.scoped.items()},
        }
