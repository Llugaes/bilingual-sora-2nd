"""Resolve complete menu strings and their explicit formatted components.

No fuzzy translation or character-substring replacement: a component must be
an entire indexed string or an unambiguous numeric printf instance. Native
icons, colours and separators are copied literally around translated runs.
"""

import re
from sora_bilingual.config.locales import DEFAULT_PRIMARY
from sora_bilingual.localization.annotation_breaks import annotation_break_allowed
from sora_bilingual.localization.save_summary import save_display_constructors

TOKEN = re.compile(r"(<[^<>]*>|\r\n|\n|\\n)")
STYLE = re.compile(r"</?[Cc][0-9a-fA-F]*>|<s\d+>")
FORMAT = re.compile(r"%(?:\d+\$)?[-+0 #]*(?:\d+)?(?:\.\d+)?[diusg]")
FORMAT_TOKEN = re.compile(r"%%|" + FORMAT.pattern)
SEPARATORS = re.compile(r"(\r\n|\n|\\n|[【】「」：:／/\[\]()]| - |[ \u3000]{2,})")
COMPONENT_LINKS = re.compile(r"([·・･])")
LINE_BREAK = re.compile(r"\r\n|\n|\\n")

# Recorded syntax/contract failures are hard by default. Only lack of role
# association permits an ordinary independently admitted resource fallback.
# Keep the complete enumeration aligned with RuntimeText.effectRefusalPolicy.
EFFECT_REFUSAL_POLICY = {
    "missing_native_join_contract": "unproved",
    "unassociated_effect_unit": "unproved",
    "partial_effect_members": "unproved",
    "hard_line_or_native_ruby": "hard",
    "invalid_separator_style": "hard",
    "member_budget": "hard",
    "empty_effect_member": "hard",
    "partition_budget": "hard",
    "different_partition_targets": "hard",
    "invalid_effect_parameter": "hard",
    "unproven_effect_parameter": "hard",
    "unproven_standalone_constructor": "hard",
    "unproven_direction_parameter": "hard",
    "conflicting_effect_member": "hard",
    "unsupported_effect_controls": "hard",
    "item_help_header_missing_record_body": "hard",
}


def _format_remainder(value):
    """Remove supported printf fields and escaped literal percent signs."""
    return FORMAT_TOKEN.sub("", value)


def _menu_record_identity(entry, language):
    """Source-locale physical menu text slot; alignment hashes are not IDs."""
    code = re.fullmatch(
        r"(script/.+\.dat/[^/]+)/code/\d+(?:/alignment/[^/]+)?", entry.get("key", "")
    )
    if code and entry.get("display_role") == "script_menu":
        called = entry.get("menu_called_ids", {}).get(language)
        if isinstance(called, int) and called >= 0:
            return code[1], called, 1
    match = re.fullmatch(
        r"(script/.+\.dat/[^/]+)/called/(\d+)/arg/(\d+)(?:/alignment/[^/]+)?", entry.get("key", "")
    )
    if not match:
        return None
    called = entry.get("called_ids", {}).get(language, int(match[2]))
    return match[1], called, int(match[3])


def _format_fields(value):
    return [match for match in FORMAT_TOKEN.finditer(value) if match.group() != "%%"]


def _render_format(template, values):
    return FORMAT_TOKEN.sub(lambda match: "%" if match.group() == "%%" else next(values), template)


def _format_pattern(source, matches, *, parameter_guard=False):
    chunks, at = [], 0
    for match in matches:
        chunks.extend(
            (
                re.escape(source[at : match.start()].replace("%%", "%")),
                r"([^<>\r\n]{0,512}?)"
                if parameter_guard and match.group()[-1] in "diu"
                else r"([^<>\r\n]{1,512}?)"
                if match.group()[-1] == "s"
                else r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
                if match.group()[-1] == "g"
                else r"([+-]?\d+)",
            )
        )
        at = match.end()
    chunks.append(re.escape(source[at:].replace("%%", "%")))
    return re.compile("".join(chunks))


def _detail_join_rule(entries, primary, secondary, source_language):
    """Keep FORMAT8 as constructor metadata, never a punctuation dictionary pair."""
    candidates = set()
    for entry in entries:
        if (
            not entry.get("detail_join_only")
            or entry.get("key") != "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"
        ):
            continue
        texts = entry.get("texts", {})
        values = tuple(
            texts.get(language, "") for language in (source_language, primary, secondary)
        )
        if all(value.strip() for value in values) and all(
            not any(char.isalnum() or char in "<>%\r\n" for char in value) for value in values
        ):
            candidates.add(values)
    return next(iter(candidates)) if len(candidates) == 1 else None


def _detail_join_parameter(entry, text):
    """Literal parameter labels are not FORMAT8's effect name/stat role.

    The native constructor reads name/stat for an effect-list member; turns,
    value and format label another argument. Typed complete constructors and
    numeric templates keep their own checked contracts below.
    """
    key = entry.get("key", "")
    return (
        key.startswith("table/t_itemhelp.tbl/SkillEffectHelpData/")
        and key.rsplit("/", 1)[-1] in {"turns", "value", "format"}
        and not _format_fields(text)
    )


def _detail_join_members(entries, primary, secondary, source_language):
    """Effect fields, proven typed constructors and native extra-effect labels."""
    flags = {"DEBUFF_CANCEL", "DELAY_SHORT", "HITTING", "STUN_L", "STUN_LL"}
    candidates, parameters = {}, set()
    for entry in entries:
        if not (
            entry.get("key", "").startswith("table/t_itemhelp.tbl/SkillEffectHelpData/")
            or entry.get("item_help_contract")
            or entry.get("key", "").removeprefix("table/t_text.tbl/TXT_ITEM_HELP_") in flags
        ):
            continue
        text = entry.get("texts", {}).get(source_language)
        if not text or not any(char.isalnum() for char in text):
            continue
        pair = complete_pair(entry["texts"], primary, secondary)
        kinds = [match.group()[-1] for match in _format_fields(text)]
        if pair and any(
            [match.group()[-1] for match in _format_fields(value)] != kinds for value in pair
        ):
            pair = None
        # A raw printf escape without a numeric slot has no compiled runtime
        # formatter here. Do not introduce its doubled percent into a list.
        if any("%%" in value and not _format_fields(value) for value in (text, *(pair or ()))):
            pair = None
        if _detail_join_parameter(entry, text):
            parameters.add(plain(text))
            continue
        candidates.setdefault(plain(text), set()).add(tuple(map(plain, pair)) if pair else None)
    for source in parameters:
        # A parameter alone cannot authorize a list, nor re-enter through a
        # wider template. It cannot veto a different, proven name/stat role.
        candidates.setdefault(source, {None})
    return candidates


def _detail_context_rules(entries, primary, secondary, source_language):
    """Compile raw-resource-authorized spans keyed by an exact description."""
    candidates = {}
    for entry in entries:
        if not entry.get("detail_context_only"):
            continue
        descriptions = entry.get("detail_context_descriptions", {})
        description = descriptions.get(source_language)
        source = entry.get("texts", {}).get(source_language)
        pair = complete_pair(entry.get("texts", {}), primary, secondary)
        if not description or not source or not pair:
            continue
        for anchor in (description, "<C0>" + description):
            candidates.setdefault(anchor, {}).setdefault(source, set()).add(pair)
    return {
        description: {
            source: next(iter(pairs)) for source, pairs in values.items() if len(pairs) == 1
        }
        for description, values in candidates.items()
    }


def _ruby_ranges(source):
    """Return every original ruby range, or fail closed on an unbalanced tag."""
    if "<R" not in source and "</R" not in source:
        return []
    ranges, at = [], 0
    while at < len(source):
        opening = source.find("<R>", at)
        closing = source.find("</R", at)
        if closing >= 0 and (opening < 0 or closing < opening):
            return None
        if source.find("<R", at) != opening:
            return None
        if opening < 0:
            return None if "<R" in source[at:] else ranges
        close_start = source.find("</R", opening + 3)
        if close_start < 0:
            return None
        nested = source.find("<R", opening + 3)
        if 0 <= nested < close_start:
            return None
        close_end = source.find(">", close_start + 3)
        if close_end < 0 or "<" in source[close_start + 3 : close_end]:
            return None
        ranges.append((opening, close_end + 1))
        at = close_end + 1
    return ranges


def _overlaps(span, ranges):
    return any(span[0] < end and start < span[1] for start, end in ranges)


def _find_all(source, value):
    at = source.find(value)
    while at >= 0:
        yield at
        at = source.find(value, at + len(value))


def _detail_inline_icon_rules(entries, primary, secondary, source_language):
    """Compile bounded, coloured detail spans that retain a native icon token."""
    result = []
    for entry in entries:
        if not entry.get("detail_inline_icon"):
            continue
        texts = entry.get("texts", {})
        pair = complete_pair(texts, primary, secondary)
        source = texts.get(source_language)
        icons = entry.get("item_help_contract", {}).get("inline_icons", ())
        fields = _format_fields(source) if isinstance(source, str) else []
        if (
            not pair
            or not source
            or len(fields) != 1
            or fields[0].group() != "%d"
            or not icons
            or any(
                icon not in source or icon not in pair[0] or icon not in pair[1] for icon in icons
            )
        ):
            continue
        chunks, at = [], 0
        for field in fields:
            chunks.extend((re.escape(source[at : field.start()]), r"([+-]?\d+)"))
            at = field.end()
        chunks.append(re.escape(source[at:]))
        result.append((re.compile("".join(chunks)), pair))
    return result


def _proven_panel_icon_slots(entry, count, languages):
    """A finite item stream can exceed the ordinary four numeric arguments.

    This budget bounds regex/output work, not generic printf admission. Every
    extra argument must be an opcode-17 icon, with the same proven item stream
    and physical call across locales; quantities/dynamic values cannot borrow it.
    """
    producer = entry["dynamic_producer"]
    origin = entry.get("producer_origin", {})
    signature = origin.get("signature", {})
    ids = origin.get("item_ids", ())
    return (
        1 <= count <= 32
        and producer.get("family") == origin.get("family") == "static_item_panel"
        and signature.get("kind") == 3
        and signature.get("command") == 8
        and signature.get("path", "").endswith(".dat")
        and bool(signature.get("function"))
        and len(ids) == count
        and all(type(i) is int and i > 0 for i in ids)
        and producer.get("slots") == [{"kind": "icon", "opcode": 17}] * count
        and all(type(entry.get("called_ids", {}).get(lang)) is int for lang in languages)
        and all(entry["texts"][lang].count("<I%d>") == count for lang in languages)
        and all(producer["numbers"][lang] == ["ascii"] * count for lang in languages)
    )


def _producer_numeric_rules(entries, primary, secondary, source_language, rejections=None):
    """Compile only integer slots whose display width was proven at the producer."""
    result = []
    for entry in entries:
        producer = entry.get("dynamic_producer")
        if not producer:
            continue
        texts, numbers = entry["texts"], producer.get("numbers", {})
        languages = (source_language, primary, secondary)

        def reject(reason):
            if rejections is not None:
                rejections.append(
                    {
                        "key": entry.get("key", ""),
                        "reason": reason,
                        "called_ids": entry.get("called_ids", {}),
                    }
                )

        if any(not texts.get(lang) or not numbers.get(lang) for lang in languages):
            reject("missing_producer_locale_or_slots")
            continue
        styles = [numbers[lang] for lang in languages]
        count = len(styles[0])
        if any(len(s) != count for s in styles):
            reject("different_integer_slot_counts")
            continue
        if not 1 <= count <= 4 and not _proven_panel_icon_slots(entry, count, languages):
            reject("unproved_integer_slot_contract")
            continue
        if any(style not in ("ascii", "fullwidth") for group in styles for style in group):
            reject("unproved_integer_width")
            continue
        if any(
            texts[lang].count("%d") != count
            or "%" in texts[lang].replace("%d", "").replace("%%", "")
            for lang in languages
        ):
            reject("unsupported_printf_slot")
            continue
        chunks = texts[source_language].split("%d")
        pattern = re.escape(chunks[0].replace("%%", "%"))
        for style, suffix in zip(styles[0], chunks[1:]):
            digits = (
                r"(-?(?:0|[1-9][0-9]{0,9}))"
                if style == "ascii"
                else r"(-?(?:０|[１-９][０-９]{0,9}))"
            )
            pattern += digits + re.escape(suffix.replace("%%", "%"))
        result.append((re.compile(pattern), (texts[primary], texts[secondary]), styles[1:]))
    return result


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
        while units and not annotation_break_allowed("".join(line), "".join(u[0] for u in units)):
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


def _owned_secondary_lines(lines):
    """Keep aligned hard rows intact, closing/reopening each lane's styles."""
    result, colours, bold, size = [], [], False, ""
    for line in lines:
        units = _secondary_units(line)
        if units is None:
            return None
        prefix = "".join(colours) + ("<B>" if bold else "") + size
        for value, _, tag in units:
            if not tag:
                continue
            if re.fullmatch(r"<[Cc][0-9a-fA-F]*>", value):
                colours.append(value)
            elif value in ("</C>", "</c>") and colours:
                colours.pop()
            elif value in ("<B>", "</B>"):
                bold = value == "<B>"
            elif re.fullmatch(r"<[sS]\d+>", value):
                size = value
        result.append(prefix + line + ("</B>" if bold else "") + "</C>" * len(colours))
    return result


def annotation_plan(primary, secondary, *, preserve_lines=False):
    """An independent native annotation lane, with the primary bytes intact.

    The empty ruby is only an anchor. The native adapter supplies its payload
    separately and suppresses its cursor/line compensation. It must NOT be
    rendered by a bare game parser without that adapter.
    """
    lines = re.split(r"(\r\n|\n|\\n)", primary)
    visible = visual_secondary(secondary)
    right = re.split(r"\r\n|\n|\\n", visible)
    left_count = (len(lines) + 1) // 2
    needs_reflow = (
        left_count != len(right)
        or not preserve_lines
        and any(bool(a.strip()) != bool(b.strip()) for a, b in zip(lines[::2], right))
    )
    owned = _owned_secondary_lines(right) if not needs_reflow else None
    if owned is not None:
        right = owned
    elif needs_reflow or ("<" in visible and left_count > 1):
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
    elif left_count == 1:
        right[0] += close_colours(right[0])
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


_ASCII_WIDTH_FOLD = {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}


def _fold_ascii_width(text):
    """Compare ASCII/fullwidth glyphs without rewriting the chosen resource.

    Do not use NFKC: it also folds kana, ligatures and numeral symbols. This
    comparison only resolves competing translations differing in ASCII width.
    """
    return text.translate(_ASCII_WIDTH_FOLD)


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
        # A native ruby reading is visible content even when its Latin base
        # is identical in both languages.
        value = re.sub(r"</R([^<>]*)>", lambda match: "\x00" + match[1], value)
        value = re.sub(r"<[^<>]*>", "", value)
        return re.sub(r"[\uff01-\uff5e]", lambda m: chr(ord(m[0]) - 0xFEE0), value).strip()

    left, right = visible(a), visible(b)
    if not left or not right:
        return False
    if left != right:
        return True
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", left))


def overdrive_descriptions(entries, source_language=DEFAULT_PRIMARY):
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
            source = texts.get(source_language, "")
            if source.rstrip() != source:
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
    # The native builder appends FORMAT8 before effect names and Sure Hit.
    # It owns locale punctuation; only anchored details may interpret it.
    result += [
        {**e, "detail_join_only": True}
        for e in entries
        if e.get("key") == "table/t_text.tbl/TXT_ITEM_HELP_FORMAT8"
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


MAP_NAME_FORMATTERS = (
    "table/t_text.tbl/TXT_MAPJUMP_CONFIRM_MAPJUMP",
    "table/t_text.tbl/TXT_HUD_ADD_MAPJUMP_SPOT",
)


def map_jump_confirmations(entries):
    """Expand complete map prompts/notifications with destination-owned names.

    A location name also occurs in quest clients and unrelated script literals.
    Those entries cannot select the wording of this complete menu prompt.
    Keep one result per destination identity, including incomplete targets, so
    genuinely different destinations with the same source remain ambiguous.
    """
    result = []
    for key in MAP_NAME_FORMATTERS:
        templates = [entry["texts"] for entry in entries if entry.get("key") == key]
        if len(templates) != 1:
            continue
        template = templates[0]
        for entry in entries:
            name_key = entry.get("key", "")
            if not (
                name_key.startswith("table/t_mapjump.tbl/MapJumpSpotData/")
                and name_key.endswith("/name")
            ):
                continue
            texts = {}
            for language, name in entry.get("texts", {}).items():
                form = template.get(language)
                if (
                    name
                    and "%" not in name
                    and form
                    and form.count("%s") == 1
                    and "%" not in form.replace("%s", "")
                ):
                    texts[language] = form.replace("%s", name)
            if texts:
                suffix = (
                    "mapjump_confirmation"
                    if key == MAP_NAME_FORMATTERS[0]
                    else "mapjump_registration"
                )
                result.append(
                    {"key": name_key + "/" + suffix, "texts": texts, "resource_formatter_key": key}
                )
    return result


def skill_help_header_contract(entries, primary, secondary, source_language):
    """The native SkillTextArray prefix + opaque icon + range + FORMAT6.

    This is a complete constructor grant, not a global fragment dictionary.
    Only actual range fields and the already-audited size compositions enter
    the argument domain. Identical text with different role targets is denied.
    """
    named = {e.get("key"): e.get("texts", {}) for e in entries}
    opening = named.get("table/t_text.tbl/TXT_ITEM_HELP_FORMAT5", {})
    closing = named.get("table/t_text.tbl/TXT_ITEM_HELP_FORMAT6", {})
    languages = (source_language, primary, secondary)
    if any(not opening.get(l) or not closing.get(l) for l in languages):
        return {}
    formats, ranges = {}, {}
    for entry in entries:
        key, texts = entry.get("key", ""), entry.get("texts", {})
        source = texts.get(source_language, "")
        if not key.startswith("table/t_itemhelp.tbl/SkillTextArrayData/") or not key.endswith(
            "/format"
        ):
            continue
        if (
            not source.startswith(opening[source_language])
            or source.count("%s") > 1
            or "%" in source.replace("%s", "")
        ):
            continue
        pair = complete_pair(texts, primary, secondary)
        if pair is not None and any(
            not texts[l].startswith(opening[l])
            or texts[l].count("%s") != source.count("%s")
            or "%" in texts[l].replace("%s", "")
            for l in languages
        ):
            pair = None
        formats.setdefault(source, []).append((pair, key))
    for entry in [*entries, *item_help_components(entries)]:
        key, texts = entry.get("key", ""), entry.get("texts", {})
        source = texts.get(source_language, "")
        if (
            key.startswith("table/t_itemhelp.tbl/SkillRangeHelpData/")
            and (key.endswith(("/label", "/short_label")) or "/label/composed/" in key)
            and source
            and "%" not in source
        ):
            ranges.setdefault(source, []).append((complete_pair(texts, primary, secondary), key))

    def admitted(values):
        return [
            {"source": source, "pair": rows[0][0], "ids": sorted({key for _, key in rows})}
            for source, rows in sorted(values.items())
            if len({pair for pair, _ in rows}) == 1 and rows[0][0] is not None
        ]

    compact = {}
    tails = [
        {
            text.split("%s")[1]
            for entry in entries
            if entry.get("key", "").startswith("table/t_itemhelp.tbl/SkillTextArrayData/")
            and entry.get("key", "").endswith("/format")
            and (text := entry.get("texts", {}).get(language, "")).startswith(opening[language])
            and text.count("%s") == 1
        }
        for language in languages
    ]
    if all(len(values) == 1 and next(iter(values)) for values in tails):
        for entry in entries:
            key, texts = entry.get("key", ""), entry.get("texts", {})
            if not key.startswith("table/t_itemhelp.tbl/SkillTextArrayData/") or not key.endswith(
                "/format"
            ):
                continue
            values = []
            for language, suffixes in zip(languages, tails):
                text, tail = texts.get(language, ""), next(iter(suffixes))
                if not text.startswith(opening[language]) or not text.endswith(tail):
                    break
                stem = text[: -len(tail)]
                if stem.endswith("%s"):
                    stem = stem[:-2]
                if "%" in stem:
                    break
                values.append(stem + closing[language])
            if len(values) == 3:
                compact.setdefault(values[0], []).append((tuple(values[1:]), key))
    return {
        "formats": admitted(formats),
        "compact_formats": admitted(compact),
        "ranges": admitted(ranges),
        "close": [closing[l] for l in languages],
    }


class MenuTranslator:
    def __init__(
        self,
        entries,
        primary,
        secondary,
        source_language=DEFAULT_PRIMARY,
        _details_only=False,
        *,
        item_help_headers=None,
    ):
        # Book bodies have locale-dependent pagination and a dedicated native
        # document resolver. They must never enter the page/string dictionary.
        entries = [entry for entry in entries if "book_pages" not in entry]
        history_entries = [entry for entry in entries if entry.get("bracer_history_frame")]
        self.bracer_history_frame = bool(
            _details_only and history_entries and len(history_entries) == len(entries)
        )
        if not _details_only:
            entries = [entry for entry in entries if not entry.get("bracer_history_frame")]
        notebook_candidates = {}
        for entry in entries:
            contract = entry.get("notebook_producer", {})
            if (
                contract.get("family") == "rod_bait_list"
                and contract.get("native_max_slots") == 16
                and len(contract.get("ordered_slots", [])) == 16
            ):
                source = entry.get("texts", {}).get(source_language)
                if source:
                    notebook_candidates.setdefault(source, set()).add(
                        complete_pair(entry["texts"], primary, secondary)
                    )
        # Exact physical constructor outputs cannot become substring tokens.
        # Existing records with the same full source still participate in the
        # conflict check, including an unavailable localized field.
        for entry in entries:
            if not entry.get("notebook_producer"):
                source = entry.get("texts", {}).get(source_language)
                if source in notebook_candidates:
                    notebook_candidates[source].add(
                        complete_pair(entry["texts"], primary, secondary)
                    )
        self.notebook_lists = {
            source: next(iter(pairs))
            for source, pairs in notebook_candidates.items()
            if len(pairs) == 1 and None not in pairs
        }
        entries = [entry for entry in entries if not entry.get("notebook_producer")]
        facility_candidates = {}
        for entry in entries:
            contract = entry.get("npc_facility_contract", {})
            if contract.get("callee") == "chr_set_shop_function" and contract.get("argument") == 2:
                source = entry["texts"].get(source_language)
                if source:
                    facility_candidates.setdefault(source, set()).add(
                        complete_pair(entry["texts"], primary, secondary)
                    )
        self.npc_facilities = {
            source: next(iter(pairs))
            for source, pairs in facility_candidates.items()
            if len(pairs) == 1 and None not in pairs
        }
        # These complete constructor outputs do not promote their undecorated
        # names into ordinary/global pairs or map/place scopes.
        entries = [entry for entry in entries if not entry.get("npc_facility_contract")]
        self.item_help_headers = item_help_headers or {}
        self.skill_help_headers = (
            skill_help_header_contract(entries, primary, secondary, source_language)
            if not _details_only
            else {}
        )
        # These native constructors own the entire destination parameter.
        # Unknown or incomplete destinations cannot fall back to token-wise
        # actor/title/name translation inside the otherwise known prompt.
        self.resource_formatter_patterns = []
        if not _details_only:
            for entry in entries:
                if entry.get("key") in MAP_NAME_FORMATTERS:
                    source = entry.get("texts", {}).get(source_language, "")
                    for value in sorted({source, plain(source)}):
                        fields = _format_fields(value)
                        if len(fields) == 1 and fields[0].group() == "%s":
                            self.resource_formatter_patterns.append(_format_pattern(value, fields))
        self.condition_lists = []
        for entry in entries:
            contract = entry.get("condition_list_contract")
            if not contract or contract.get("id") != 98 or contract.get("parameter_types") != [10]:
                continue
            languages = (source_language, primary, secondary)
            if any(l not in contract.get("templates", {}) for l in languages):
                continue
            candidates = {}
            for names in contract["names"]:
                source, pair = names.get(source_language), complete_pair(names, primary, secondary)
                if source:
                    candidates.setdefault(source, set()).add(pair)
            self.condition_lists.append(
                {
                    "id": 98,
                    "templates": [contract["templates"][l] for l in languages],
                    "links": [contract["links"][l] for l in languages],
                    "percent": [contract["percent"][l] for l in languages],
                    "names": {
                        s: next(iter(pairs))
                        for s, pairs in candidates.items()
                        if len(pairs) == 1 and None not in pairs
                    },
                }
            )
        # Resource-proven printf output replaces only its own raw template.
        # A template with zero arguments is still a format: treating its %% as
        # display text makes both matching and reverse-language output wrong.
        # Keep all other records/roles and actual conflicting localized values.
        formatted_descriptions = {}
        for entry in entries:
            contract = entry.get("printf_description_contract", {})
            raw = contract.get("raw_texts", {})
            if (
                contract.get("formatter") == "item_description_printf"
                and contract.get("key") == entry.get("key")
                and contract.get("slots") == 0
                and re.fullmatch(r"table/t_item\.tbl/sha256:[^/]+/description", entry["key"])
                and raw
                and all("%" not in text.replace("%%", "") for text in raw.values())
                and entry["texts"] == {l: t.replace("%%", "%") for l, t in raw.items()}
            ):
                formatted_descriptions.setdefault(entry["key"], []).append(raw)
        entries = [
            entry
            for entry in entries
            if entry.get("printf_description_contract")
            or not any(
                all(entry["texts"].get(l) == text for l, text in raw.items())
                for raw in formatted_descriptions.get(entry.get("key"), ())
            )
        ]
        self.detail_join = (
            _detail_join_rule(entries, primary, secondary, source_language)
            if _details_only
            else None
        )
        join_candidates = (
            _detail_join_members(entries, primary, secondary, source_language)
            if self.detail_join
            else {}
        )
        join_members = {
            source: next(iter(pairs))
            for source, pairs in join_candidates.items()
            if len(pairs) == 1 and None not in pairs
        }
        entries = [entry for entry in entries if not entry.get("detail_join_only")]
        # A resource-identified menu header authorizes the same detail scope
        # as a full description. Its arguments remain opaque native data.
        self.detail_headers = sorted(
            {
                tuple(template.split("%s"))
                for entry in entries
                if not _details_only
                and (template := entry.get("detail_header_templates", {}).get(source_language))
                and template.count("%s") == 1
            }
        )
        # Literal native category prefixes already have a complete resource
        # identity. Keep the whole prefix (including its hint and punctuation)
        # out of the effect-list parser; short category words grant no scope.
        self.detail_header_literals = {
            entry["texts"][source_language]
            for entry in entries
            if not _details_only
            and entry.get("key", "").startswith("table/t_itemhelp.tbl/ItemKindHelpData/")
            and entry.get("key", "").endswith("/description")
            and source_language in entry["texts"]
            and entry["texts"][source_language]
            and "%" not in entry["texts"][source_language]
        }
        self.detail_inline_icons = (
            _detail_inline_icon_rules(entries, primary, secondary, source_language)
            if _details_only
            else []
        )
        if _details_only:
            self.detail_contexts = _detail_context_rules(
                entries, primary, secondary, source_language
            )
            # These rows authorize only an exact span under an exact
            # description.  They must not also become ordinary detail pairs.
            entries = [entry for entry in entries if not entry.get("detail_context_only")]
        else:
            self.detail_contexts = {}
        self.producer_numeric_rejections = []
        self.producer_numeric = _producer_numeric_rules(
            entries, primary, secondary, source_language, self.producer_numeric_rejections
        )
        entries = [entry for entry in entries if not entry.get("dynamic_producer")]
        detail_aliases = []
        if not _details_only:
            generated_details = [e for e in entries if e.get("detail_only")]
            entries = [e for e in entries if not e.get("detail_only")]
            detail_aliases = item_help_detail_entries(entries) + generated_details
            # Proven complete effect constructors can appear without a
            # description (including items whose description is empty). They
            # are ordinary global candidates, not privileged detail aliases.
            # Context-dependent spans and element-label fragments stay scoped.
            entries += [
                {**e, "detail_authority": False}
                for e in generated_details
                if e.get("item_help_contract") and not e.get("detail_context_only")
            ]
            entries += overdrive_descriptions(entries, source_language)
            entries += map_jump_confirmations(entries)
            # These finite map-owned formatters must not fall back to a generic
            # %s rule that borrows actor/Tips/quest wording for an unknown name.
            # Missing/conflicting complete destinations stay untranslated.
            entries = [e for e in entries if e.get("key") not in MAP_NAME_FORMATTERS]
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
        if history_entries and not _details_only:
            self.scoped["bracer_history"] = MenuTranslator(
                history_entries, primary, secondary, source_language, True
            )
        self.save_confirmation_prefixes = []
        self.detail_sources = set()
        self.details = None
        self.frame_owner = None
        if not _details_only:
            # Saves embed display strings from the locale used when written.
            # Only the save-summary surface may read these cross-locale aliases;
            # normal menus must keep the current source language and conflicts.
            saved = []
            save_constructors = save_display_constructors(entries, source_language)
            localized_playtime = any(
                e.get("key", "").startswith("table/t_save_generated/playtime/")
                for e in save_constructors
            )
            for entry in [*entries, *save_constructors]:
                key = entry.get("key", "")
                if localized_playtime and key == "table/t_text.tbl/TXT_SAVE_DETAIL_PLAYTIME":
                    # The same-language raw caption remains in normal menus;
                    # only this ancestry-bound scope uses the display caption.
                    continue
                summary = (
                    key.startswith("table/t_chapter.tbl/")
                    and key.endswith(("/title", "/heading"))
                    or key.startswith(("table/t_place.tbl/", "table/t_name.tbl/"))
                    and key.endswith("/name")
                    or key.startswith("table/t_quest.tbl/NaviText/")
                    and key.endswith("/title")
                    or key.startswith("table/t_text.tbl/TXT_SAVE_DETAIL_")
                    or key == "table/t_text.tbl/TXT_TITLE_CONTINUE_CONFIRM"
                    or key.startswith("table/t_save_generated/")
                )
                if not summary:
                    continue
                values = sorted(
                    (
                        set(entry["texts"].values())
                        | set(entry.get("source_variants", {}).get(source_language, []))
                    )
                    - {""}
                )
                saved.append({**entry, "source_variants": {source_language: values}})
                if key == "table/t_text.tbl/TXT_TITLE_CONTINUE_CONFIRM":
                    self.save_confirmation_prefixes = [text + "\n" for text in values]
            if saved:
                self.scoped["save_summary"] = MenuTranslator(
                    saved, primary, secondary, source_language, True
                )
            # The verified second-chapter quest builder reads manager+0xd8,
            # whose QuestText section belongs to t_quest.tbl. FC's table is a
            # different manager slot and must not create global aliases here.
            quest_notes = [
                e
                for e in entries
                if e.get("key", "").startswith("table/t_quest.tbl/QuestText/")
                and e["key"].endswith("/body")
            ]
            if quest_notes:
                self.scoped["quest_notes"] = MenuTranslator(
                    quest_notes, primary, secondary, source_language, True
                )
            fc_quest_notes = [
                e
                for e in entries
                if e.get("key", "").startswith("table/t_quest_fc.tbl/QuestText/")
                and e["key"].endswith("/body")
            ]
            if fc_quest_notes:
                self.scoped["fc_quest_notes"] = MenuTranslator(
                    fc_quest_notes, primary, secondary, source_language, True
                )
            for scope, prefix in [
                ("support", "table/t_support_ability.tbl/"),
                ("overdrive", "table/t_condition_info.tbl/OverDriveEffect/"),
                ("item_name", "table/t_item.tbl/"),
                ("map_spot", "table/t_mapjump.tbl/"),
            ]:
                selected = [
                    e
                    for e in entries
                    if e.get("key", "").startswith(prefix)
                    and (scope not in ("item_name", "map_spot") or e["key"].endswith("/name"))
                ]
                if scope == "map_spot":
                    # The copied map labels include areas and individual spots.
                    # Keep the whole map-jump name family and its real conflicts;
                    # ViewerMapData remains outside this scope. Builders remove LF.
                    selected = [
                        {
                            **e,
                            "texts": {
                                language: text.replace("\n", "")
                                for language, text in e["texts"].items()
                            },
                        }
                        for e in selected
                    ]
                if selected:
                    self.scoped[scope] = MenuTranslator(
                        selected, primary, secondary, source_language, True
                    )
            # note_help layout 59 shares its list between Help and Tips. Its
            # copied titles must retain conflicts across both complete families.
            # The Tips detail pane (layout 89) has a distinct title ancestor.
            for scope in ("note_help_title", "tips_title"):
                titles = [
                    e
                    for e in entries
                    if (
                        e.get("key", "").startswith("table/t_tips.tbl/")
                        or scope == "note_help_title"
                        and e.get("key", "").startswith("table/t_help.tbl/")
                        and len(e["key"].split("/")) == 4
                    )
                    and e["key"].endswith("/title")
                ]
                if titles:
                    self.scoped[scope] = MenuTranslator(
                        titles, primary, secondary, source_language, True
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
                if e.get("item_help_scope") != "status"
                and e.get("key", "").startswith(
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
            # Known literal descriptions may lose trailing ASCII layout
            # padding when copied by a detail builder. Admit that complete
            # resource spelling locally; duplicate translations still enter
            # the ordinary conflict set. No word/prefix/%s alias is created.
            copied_descriptions = []
            for e in detail_entries:
                if (
                    e.get("key", "").endswith("/description")
                    and source_language in e.get("texts", {})
                    and e["texts"][source_language].endswith((" ", "\t"))
                    and "%" not in e["texts"][source_language]
                ):
                    # The copied source spelling is also the display target
                    # when primary follows the game. Retaining the original
                    # source padding in that alias creates a false conflict
                    # with an otherwise identical unpadded physical record.
                    # Keep the original record and every other locale intact.
                    copied_descriptions.append(
                        {
                            **e,
                            "key": e["key"].removesuffix("/description") + "/copied/description",
                            "texts": {
                                **e["texts"],
                                source_language: e["texts"][source_language].rstrip(" \t"),
                            },
                            "source_variants": {},
                        }
                    )
            detail_entries += copied_descriptions
            descriptions = {
                value
                for e in detail_entries
                if e.get("key", "").endswith("/description") and source_language in e["texts"]
                for value in [
                    e["texts"][source_language],
                    *e.get("source_variants", {}).get(source_language, []),
                ]
            }
            # UI style wrappers are peeled at the verified boundary. They are
            # not resource descriptions or effect-record context identities.
            self.detail_sources = descriptions
            if detail_entries:
                self.details = MenuTranslator(
                    detail_entries, primary, secondary, source_language, True
                )
                self.details.frame_owner = self
        self.keyed = []
        candidates = {}
        incomplete_candidates = {}
        incomplete_records = set()
        display_candidates = {}
        complete_display_sources = {}
        incomplete_voice_sources = set()
        detail_authority = {}
        join_label_candidates = {}
        menu_proofs = {}
        for entry in entries:
            if entry.get("display_role") != "script_menu":
                continue
            identity = _menu_record_identity(entry, source_language)
            pair = complete_pair(entry["texts"], primary, secondary)
            source = entry["texts"].get(source_language)
            if identity is not None and pair and source:
                menu_proofs.setdefault(source, {}).setdefault(identity, set()).add(pair)
        menu_claims = {source: [] for source in menu_proofs}
        for entry in entries:
            texts = entry["texts"]
            pair = complete_pair(texts, primary, secondary)
            voice_record = (
                # The aligned producer replaces the physical class prefix
                # with group/sequence/record identity. Classify the resource
                # family and whole body field, not its pre-alignment spelling.
                entry.get("key", "").startswith("table/t_active_voice.tbl/")
                and entry.get("key", "").endswith("/body")
                and "/segments:" not in entry.get("key", "")
            )
            display_record = (
                entry.get("display_role") in ("dialogue", "speaker", "popup_line") or voice_record
            )
            whole_display = (
                display_record
                or entry.get("display_role") == "script_menu"
                or entry.get("resource_formatter_key") in MAP_NAME_FORMATTERS
            )
            whole_resource_name = entry.get("key", "").startswith(
                ("table/t_item.tbl/", "table/t_skill.tbl/")
            ) and entry.get("key", "").endswith("/name")
            fragment = "/code/" in entry.get("key", "") and "/alignment/" in entry.get("key", "")
            prefix = "table/t_text.tbl/"
            if pair and source_language in texts and entry.get("key", "").startswith(prefix):
                self.keyed.append((entry["key"][len(prefix) :], texts[source_language], pair))
            sources = {texts[source_language]} if source_language in texts else set()
            if (source := texts.get(source_language)) in menu_claims:
                menu_claims[source].append(
                    (
                        _menu_record_identity(entry, source_language),
                        pair,
                        tuple(texts.get(locale) for locale in (primary, secondary)),
                    )
                )
            if entry.get("source_variants"):
                # Resource-proven presentation variants share the identified
                # stat's target pair. Do not create competing target spellings
                # when another locale has an unchanged source label.
                sources.update(entry.get("source_variants", {}).get(source_language, ()))
            # These become serialized rule arrays and indexes. Python's hash
            # seed must not change a cold model's bytes or rule traversal.
            for value in sorted(sources):
                if whole_resource_name and value.strip():
                    # Quarantine the complete physical spelling, not a new
                    # stripped alias of a distinct styled name.
                    complete_display_sources.setdefault(value, set()).add(entry.get("key", ""))
                for source in sorted({value, plain(value)}):
                    if source.strip():
                        if whole_display:
                            complete_display_sources.setdefault(source, set()).add(
                                entry.get("key", "")
                            )
                            if voice_record and pair is None:
                                incomplete_voice_sources.add(source)
                        candidates.setdefault(source, set()).add(pair)
                        if not _detail_join_parameter(entry, value):
                            join_label_candidates.setdefault(source, set()).add(
                                tuple(map(plain, pair)) if pair else None
                            )
                        if pair is None:
                            if not fragment:
                                incomplete_records.add(source)
                            incomplete_candidates.setdefault(source, set()).add(
                                tuple(texts.get(locale) for locale in (primary, secondary))
                            )
                        if entry.get("detail_authority") and pair:
                            detail_authority.setdefault(source, set()).add(pair)
                        if display_record and pair:
                            display_candidates.setdefault(source, set()).add(pair)
                # Native dialogue controls may be consumed before SetText.
                # Keep a separate complete display variant, not a substring match.
                visible = display_text(value)
                if visible != value and visible.strip():
                    if whole_display:
                        complete_display_sources.setdefault(visible, set()).add(
                            entry.get("key", "")
                        )
                        if voice_record and pair is None:
                            incomplete_voice_sources.add(visible)
                    candidates.setdefault(visible, set()).add(
                        tuple(display_text(t) for t in pair) if pair else None
                    )
                    if pair is None:
                        if not fragment:
                            incomplete_records.add(visible)
                        incomplete_candidates.setdefault(visible, set()).add(
                            tuple(
                                display_text(texts[locale]) if texts.get(locale) else None
                                for locale in (primary, secondary)
                            )
                        )
                    if display_record and pair:
                        display_candidates.setdefault(visible, set()).add(
                            tuple(display_text(t) for t in pair)
                        )
        # A partial bytecode alignment is not an independent display record.
        # It must not blacklist an otherwise unique complete UI pair. Missing
        # fields of actual table/call records remain identity-local misses.
        for source, fragments in incomplete_candidates.items():
            complete = candidates[source] - {None}
            if source in incomplete_records or len(complete) != 1:
                continue
            pair = next(iter(complete))
            if all(
                not value or not value.strip() or plain(value) == plain(pair[i])
                for fragment in fragments
                for i, value in enumerate(fragment)
            ):
                candidates[source] = complete
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
        # A proved menu payload completes only aliases of that same physical
        # call/slot. An untranslated homonym at another event is still unknown;
        # an actual conflicting localized value still blocks global selection.
        for source, proofs in menu_proofs.items():
            pairs = {pair for values in proofs.values() for pair in values}
            if len(pairs) != 1:
                self.ambiguous_display.add(source)
                continue
            pair = next(iter(pairs))
            if all(
                complete == pair
                if complete is not None
                else identity in proofs
                and pair in proofs[identity]
                and all(value is None or value == pair[i] for i, value in enumerate(known))
                for identity, complete, known in menu_claims[source]
            ):
                candidates[source] = {pair}
                self.ambiguous_display.discard(source)
        # Name/status records are the display-name authority. Script voice
        # identifiers can reuse the same source while omitting a locale (or
        # retaining its Japanese identifier in the English slot). Only exact
        # complete names get this fallback. A different complete menu/resource
        # meaning is also a conflict; an NPC name must not override a skill or
        # equipment name merely because its table is called t_name.
        names = {}
        for entry in entries:
            key = entry.get("key", "")
            texts = entry["texts"]
            if (
                key.startswith(("table/t_name.tbl/", "table/t_status.tbl/"))
                and key.endswith("/name")
                and source_language in texts
                # Aliases may come from saves in another language. The
                # current-locale name is not authority over those candidates.
                and not entry.get("source_variants")
            ):
                pair = complete_pair(texts, primary, secondary)
                names.setdefault(texts[source_language], set()).add(pair)
        for source, pairs in names.items():
            complete_candidates = candidates.get(source, set()) - {None}
            if (
                len(pairs) == 1
                and None not in pairs
                and all(
                    tuple(_fold_ascii_width(t) for t in pair)
                    == tuple(_fold_ascii_width(t) for t in next(iter(pairs)))
                    for pair in complete_candidates
                )
            ):
                candidates[source] = pairs
                self.ambiguous_display.discard(source)
        # Resource-generated fragments are valid only in the already-anchored
        # detail model. Prefer their spacing over a colliding standalone stat
        # record when native colour tags split the original name template.
        for source, pairs in detail_authority.items():
            if len(pairs) == 1:
                candidates[source] = pairs
                self.ambiguous_display.discard(source)
        complete_description_sources = (
            {
                e["texts"][source_language]
                for e in entries
                if e.get("key", "").endswith("/description") and source_language in e["texts"]
            }
            if _details_only
            else set()
        )
        for source, pairs in candidates.items():
            if len(pairs) < 2 or None in pairs:
                continue
            if (
                source in complete_description_sources
                and len({tuple(_without_line_padding(t) for t in pair) for pair in pairs}) == 1
            ):
                # Copied complete descriptions can share one physical source
                # while differing only in target layout padding. Select an
                # existing complete resource pair, as for display records.
                # Different words and missing targets still remain conflicts.
                candidates[source] = {min(pairs, key=lambda pair: (sum(map(len, pair)), pair))}
                self.ambiguous_display.discard(source)
                continue
            if len({tuple(_fold_ascii_width(t) for t in pair) for pair in pairs}) == 1:
                # Select an existing complete pair; never manufacture a target
                # or collapse genuinely different words into one translation.
                candidates[source] = {min(pairs)}
                self.ambiguous_display.discard(source)
        self.pairs = {
            s: next(iter(p))
            for s, p in candidates.items()
            if len(p) == 1 and None not in p and display_text(s) not in self.ambiguous_display
        }
        # A known whole dialogue/menu body cannot become a generic wrapper or
        # unrelated per-line translation when its own pair is unavailable.
        # Exact pointer/VM/key models contain their own complete record and can
        # still authorize it. This quarantine never selects a competing pair.
        self.display_rejections = []
        for source, keys in sorted(complete_display_sources.items()):
            if source in self.pairs and source not in incomplete_voice_sources:
                continue
            if source in incomplete_voice_sources:
                # A complete peer at a different voice identity cannot fill
                # an actually missing localized body. Exact identity models
                # may still resolve their own known record.
                self.pairs.pop(source, None)
                candidates.setdefault(source, set()).add(None)
            self.ambiguous_display.add(source)
            self.display_rejections.append(
                {
                    "source": source,
                    "keys": sorted(keys),
                    "reason": "conflicting_complete_display_targets"
                    if len(candidates.get(source, set()) - {None}) > 1
                    else "missing_complete_display_pair",
                }
            )
        # Formatting-only differences do not make a translation ambiguous.
        normalized = {}
        for source, pairs in candidates.items():
            p = {None if v is None else (plain(v[0]), plain(v[1])) for v in pairs}
            if len(p) == 1 and None not in p and display_text(source) not in self.ambiguous_display:
                normalized[source] = next(iter(p))
        self.plain_pairs = normalized
        self.numeric = []
        self.raw_numeric = []
        self.detail_numeric = []
        self.detail_join_pairs = {
            source: pair
            for source, pair in join_members.items()
            if join_label_candidates.get(source) == {pair} and not _format_fields(source)
        }
        self.detail_join_literals = set(self.detail_join_pairs)
        self.detail_join_numeric = []
        admitted_join_templates = set(self.detail_join_literals)
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
            rule = (_format_pattern(source, matches), pair)
            (self.raw_numeric if is_raw else self.numeric).append(rule)
            if not is_raw and source in detail_authority and "s" not in kinds:
                self.detail_numeric.append(rule)
            if not is_raw and join_members.get(source) == pair and "s" not in kinds:
                self.detail_join_numeric.append(rule[0])
                admitted_join_templates.add(source)
        self.detail_join_blocked_literals = set()
        self.detail_join_blocked_numeric = []
        for source in sorted(join_candidates.keys() - admitted_join_templates):
            matches = _format_fields(source)
            if not matches:
                self.detail_join_blocked_literals.update((source, source.replace("%%", "%")))
            elif (
                len(matches) <= 16
                and all(match.group()[-1] != "s" for match in matches)
                and "%" not in _format_remainder(source)
            ):
                self.detail_join_blocked_numeric.append(_format_pattern(source, matches))
        # Resource identity and constructor role travel with each rendered
        # effect. A full native constructor remains atomic even if it contains
        # FORMAT8. Raw parameter labels never enter this role contract.
        # A homograph in an unrelated item/skill field is not a competing
        # effect-role translation. Role-local collisions still reject.
        effect_entries = [
            e
            for e in entries
            if e.get("item_help_contract")
            or re.fullmatch(
                r"table/t_itemhelp\.tbl/SkillEffectHelpData/[^/]+/(?:name|stat)", e.get("key", "")
            )
            or e.get("key", "").removeprefix("table/t_text.tbl/TXT_ITEM_HELP_")
            in {"DEBUFF_CANCEL", "DELAY_SHORT", "HITTING", "STUN_L", "STUN_LL"}
        ]
        effect_candidates = (
            _detail_join_members(effect_entries, primary, secondary, source_language)
            if self.detail_join
            else {}
        )
        # An explicit resource-authoritative generated row can veto a
        # competing role target. It cannot itself grant an untyped role or
        # turn a prefix/parameter fragment into an effect identity.
        effect_vetoes = [
            e
            for e in entries
            if e.get("detail_authority")
            and not e.get("item_help_contract")
            and e.get("key", "").startswith("table/t_itemhelp.tbl/generated/")
        ]
        for entry in effect_vetoes:
            source = plain(entry.get("texts", {}).get(source_language, ""))
            if source in effect_candidates:
                pair = complete_pair(entry.get("texts", {}), primary, secondary)
                effect_candidates[source].add(tuple(map(plain, pair)) if pair else None)
        effect_members = {
            source: next(iter(pairs))
            for source, pairs in effect_candidates.items()
            if len(pairs) == 1 and None not in pairs
        }
        unit_sources = {source for source in effect_members if not _format_fields(source)}
        for entry in effect_entries:
            source = plain(entry.get("texts", {}).get(source_language, ""))
            fields = _format_fields(source)
            if (
                entry.get("item_help_contract")
                and source in effect_members
                and 0 < len(fields) <= 4
                and all(field.group()[-1] in "diug" for field in fields)
                and all(
                    [field.group()[-1] for field in _format_fields(t)]
                    == [field.group()[-1] for field in fields]
                    and "%" not in _format_remainder(t)
                    and all("$" not in field.group() for field in _format_fields(t))
                    for t in (source, *effect_members[source])
                )
            ):
                unit_sources.add(source)
        unit_ids, atomic_sources, constructor_ids, member_sequences = {}, set(), set(), set()
        for entry in effect_entries:
            text = entry.get("texts", {}).get(source_language, "")
            source = plain(text)
            pair = complete_pair(entry.get("texts", {}), primary, secondary)
            if (
                source in unit_sources
                and pair
                and tuple(map(plain, pair)) == effect_members.get(source)
                and not _detail_join_parameter(entry, text)
            ):
                unit_ids.setdefault(source, set()).add(entry.get("key", ""))
                if entry.get("item_help_contract", {}).get("record_ids") or re.fullmatch(
                    r"table/t_itemhelp\.tbl/SkillEffectHelpData/[^/]+/name", entry.get("key", "")
                ):
                    constructor_ids.add(entry["key"])
                if entry.get("item_help_contract", {}).get("family") in {
                    "percent_recovery_header",
                    "revive_recovery",
                    "before_ko_recovery",
                }:
                    atomic_sources.add(source)
                if (
                    entry.get("item_help_contract", {}).get("family")
                    == "native_mixed_effect_sequence"
                ):
                    member_sequences.add(source)
        self.detail_effect_units = [
            {
                "source": source,
                "pair": effect_members[source],
                "ids": sorted(ids),
                "pattern": _format_pattern(source, _format_fields(source)).pattern,
                **(
                    {"parameter_kinds": [f.group()[-1] for f in _format_fields(source)]}
                    if _format_fields(source)
                    else {}
                ),
                **({"atomic": True} if source in atomic_sources else {}),
                **({"member_sequence": True} if source in member_sequences else {}),
            }
            for source, ids in sorted(unit_ids.items())
        ]
        self._effect_rules = [(row, re.compile(row["pattern"])) for row in self.detail_effect_units]
        self.detail_effect_constructor_ids = constructor_ids
        self._effect_parameter_guards = [
            (
                row,
                _format_pattern(row["source"], _format_fields(row["source"]), parameter_guard=True),
            )
            for row in self.detail_effect_units
            if any(kind in "diu" for kind in row.get("parameter_kinds", []))
        ]
        # Direction slots have a finite machine-code domain. Derive guards
        # from complete proved constructors; no display-word aliases enter.
        direction_guards, direction_frames = set(), set()
        for entry in effect_entries:
            contract = entry.get("item_help_contract", {})
            if contract.get("family") not in {
                "direction_single_up",
                "direction_native_group",
                "self_direction_constructor",
            }:
                continue
            raw_source = entry.get("texts", {}).get(source_language, "")
            source = re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", plain(raw_source))
            arrows = contract.get("inline_icons") or re.findall(r"[↑↓]+", source)
            if len(arrows) != 1 or source.count(arrows[0]) != 1:
                continue
            pattern = _format_pattern(source, _format_fields(source), parameter_guard=True).pattern
            direction_guards.add(
                pattern.replace(re.escape(arrows[0]), r"(<I[0-9]{1,5}>|[^<>\r\n]{0,64})", 1)
            )
            direction_frames.update(re.findall(r"<[Cc][0-9a-fA-F]+>", raw_source))
        self.detail_effect_direction_guards = sorted(direction_guards)
        self._effect_direction_guards = [
            re.compile(pattern) for pattern in self.detail_effect_direction_guards
        ]
        self.detail_effect_direction_frames = sorted(direction_frames)
        self.effect_unit_failures = {}
        self.detail_effect_blocked_literals = set()
        self.detail_effect_blocked_numeric = []
        self.detail_effect_rejections = []
        for source in sorted(effect_candidates.keys() - unit_ids.keys()):
            fields = _format_fields(source)
            if not fields:
                self.detail_effect_blocked_literals.update((source, source.replace("%%", "%")))
            elif (
                len(fields) <= 16
                and all(field.group()[-1] != "s" for field in fields)
                and "%" not in _format_remainder(source)
            ):
                self.detail_effect_blocked_numeric.append(_format_pattern(source, fields))
            self.detail_effect_rejections.append(
                {
                    "source": source,
                    "ids": sorted(
                        {
                            e.get("key", "")
                            for e in [*effect_entries, *effect_vetoes]
                            if plain(e.get("texts", {}).get(source_language, "")) == source
                        }
                    ),
                    "reason": "missing_or_ambiguous_effect_role"
                    if source not in effect_members
                    else "unproven_parameter_contract",
                }
            )

    def _effect_unit(self, source, _coalesced=False):
        if not _coalesced:
            # Adjacent native runs in the same color are one presentation
            # span. Coalesce only identical close/open colors: never strip
            # size commands, readings, icons or different-color boundaries.
            joined = re.sub(r"(<([Cc][0-9a-fA-F]+)>[^<>]*)</[Cc]><\2>", r"\1", source)
            while joined != source:
                unit = self._effect_unit(joined, True)
                if unit:
                    return {**unit, "source": source}
                if self._effect_rejected(joined):
                    self.effect_unit_failures[source] = self.effect_unit_failures[joined]
                    return None
                further = re.sub(r"(<([Cc][0-9a-fA-F]+)>[^<>]*)</[Cc]><\2>", r"\1", joined)
                if further == joined:
                    break
                joined = further
        stripped = re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", source)
        if stripped != source and self.frame_owner is not None:
            frame = self.frame_owner.raw_pair(source)
            role = self._effect_unit(stripped, True)
            if self.effect_unit_failures.get(stripped) == "unproven_direction_parameter":
                self.effect_unit_failures[source] = "unproven_direction_parameter"
                return None
            if (
                frame
                and role
                and set(role.get("semantic_ids", ())) & self.detail_effect_constructor_ids
                and tuple(re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", t) for t in frame)
                == role["pair"]
            ):
                return {**role, "source": source, "pair": frame}
        if stripped != source and re.search(r"<I\d+>", source):
            # A proven native constructor owns the exact icon sequence. Apply
            # edge styles inside each icon-delimited field, never match an
            # arbitrary stripped word or move an internal colour boundary.
            role = self._effect_unit(stripped, True)
            if role and set(role.get("semantic_ids", ())) & self.detail_effect_constructor_ids:
                parts = re.split(r"(<I\d+>)", source)
                pair = []
                for target in role["pair"]:
                    target_parts = re.split(r"(<I\d+>)", target)
                    if len(target_parts) != len(parts) or target_parts[1::2] != parts[1::2]:
                        break
                    decorated = []
                    for index, (part, translated) in enumerate(zip(parts, target_parts)):
                        if index % 2 or "<" not in part:
                            decorated.append(translated)
                            continue
                        edge_style = re.fullmatch(
                            r"((?:</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)+)([^<>]*?)"
                            r"((?:</?[Cc][0-9a-fA-F]*>)*)(\s*(?:- )?)",
                            part,
                        )
                        if not edge_style:
                            break
                        opening, _core, closing, padding = edge_style.groups()
                        if padding and not translated.endswith(padding):
                            break
                        inner = translated[: -len(padding)] if padding else translated
                        decorated.append(opening + inner + closing + padding)
                    else:
                        pair.append("".join(decorated))
                        continue
                    break
                if len(pair) == 2:
                    return {**role, "source": source, "pair": tuple(pair)}
        condition = self.condition_list_unit(source)
        if condition is not None:
            return condition
        # Peel presentation at the edges only; internal controls, native ruby
        # and dynamic substitutions are not normalized into a matching label.
        edge = re.fullmatch(
            r"((?:</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)*)(.*?)((?:</[Cc]>)*)(\s*)",
            source,
        )
        if not edge:
            return None
        prefix, core, suffix, trailing = edge.groups()
        leading = core[: len(core) - len(core.lstrip())]
        # Resource-owned whitespace belongs to its locale's literal field.
        # Exact full-field matching precedes optional external presentation
        # padding; never trim a native field and manufacture a target suffix.
        for candidate, padding_left, padding_right in (
            (core + trailing, "", ""),
            (core, "", trailing),
            (core[len(leading) :] + trailing, leading, ""),
            (core[len(leading) :], leading, trailing),
        ):
            if candidate in self.detail_effect_blocked_literals or any(
                pattern.fullmatch(candidate) for pattern in self.detail_effect_blocked_numeric
            ):
                self.effect_unit_failures[source] = "conflicting_effect_member"
                return None
            matches = []
            for row, pattern in self._effect_rules:
                if match := pattern.fullmatch(candidate):
                    values = match.groups()
                    kinds = row.get("parameter_kinds", [])
                    if kinds and (
                        len(kinds) != len(values)
                        or any(
                            not re.fullmatch(r"[+-]?[0-9]+", value)
                            or not (
                                0 <= int(value) <= 4294967295
                                if kind == "u"
                                else -2147483648 <= int(value) <= 2147483647
                            )
                            for kind, value in zip(kinds, values)
                            if kind in "diu"
                        )
                    ):
                        self.effect_unit_failures[source] = "invalid_effect_parameter"
                        return None
                    pair = tuple(_render_format(t, iter(values)) for t in row["pair"])
                    matches.append(
                        (
                            pair,
                            row["ids"],
                            values,
                            row.get("atomic", False),
                            row.get("member_sequence", False),
                        )
                    )
            if not matches:
                continue
            if len({pair for pair, *_ in matches}) != 1:
                self.effect_unit_failures[source] = "conflicting_effect_member"
                return None
            return {
                "source": source,
                "pair": tuple(
                    prefix + padding_left + text + suffix + padding_right for text in matches[0][0]
                ),
                "semantic_ids": sorted({key for _, ids, *_ in matches for key in ids}),
                "parameters": list(matches[0][2]),
                **({"atomic": True} if any(m[3] for m in matches) else {}),
                **({"member_sequence": True} if any(m[4] for m in matches) else {}),
            }
        for candidate in dict.fromkeys(
            (core + trailing, core, core[len(leading) :] + trailing, core[len(leading) :])
        ):
            for pattern in self._effect_direction_guards:
                match = pattern.fullmatch(candidate)
                if not match or any(
                    (self.detail_join and self.detail_join[0] in value)
                    or COMPONENT_LINKS.search(value)
                    or re.search(r"[/\[\]()|]| - ", value)
                    for value in match.groups()
                ):
                    continue
                # A signed numeric stat suffix is another native syntax,
                # not a direction strength. Leave its existing bounded
                # stat/equipment parser in charge; do not grant a new role.
                if any(re.fullmatch(r"[+-][0-9]+", value) for value in match.groups()) and all(
                    re.fullmatch(r"[+-]?[0-9]+", value) for value in match.groups()
                ):
                    continue
                self.effect_unit_failures[source] = "unproven_direction_parameter"
                return None
        # Recognize a complete admitted constructor whose integer slots failed
        # syntax, before any legacy string formatter can reinterpret them.
        # Captures cannot absorb native joins or equipment fences: an unknown
        # complete neighbour remains independent of a valid numeric member.
        for candidate in dict.fromkeys(
            (core + trailing, core, core[len(leading) :] + trailing, core[len(leading) :])
        ):
            for row, pattern in self._effect_parameter_guards:
                match = pattern.fullmatch(candidate)
                if not match:
                    continue
                values = match.groups()
                if any(
                    (self.detail_join and self.detail_join[0] in value)
                    or COMPONENT_LINKS.search(value)
                    or re.search(r"[/\[\]()|]| - ", value)
                    for value in values
                ):
                    continue
                if any(
                    kind in "diu" and not re.fullmatch(r"[+-]?[0-9]+", value)
                    for kind, value in zip(row["parameter_kinds"], values)
                ):
                    self.effect_unit_failures[source] = "unproven_effect_parameter"
                    return None
        return None

    def effect_line_units(self, source, allow_opaque=False, description=""):
        ranges = _ruby_ranges(source)
        if ranges is None:
            self.effect_unit_failures[source] = "hard_line_or_native_ruby"
            return None
        if not ranges:
            # Equipment syntax fences whole effects with brackets/dashes.
            # Try the complete constructor first, then retain these literal
            # decorations around the same bounded role parser. Only a known
            # description/skill header may authorize this outer grammar.
            if allow_opaque and ("[" in source or " - " in source):
                whole = self._effect_unit(source)
                if whole:
                    return [whole]
                if self._effect_rejected(source):
                    return None
                original = self.effect_units(source, True, description)
                if original is None and self._effect_rejected(source):
                    return None
                units = []
                for index, part in enumerate(re.split(r"(\[|\]| - )", source)):
                    if not part:
                        continue
                    if index % 2:
                        units.append({"source": part, "pair": (part, part), "opaque": True})
                    else:
                        child = self.effect_units(part, True, description)
                        if child is None:
                            self.effect_unit_failures[source] = self.effect_unit_failures.get(part)
                            return None
                        units.extend(child)
                # Preserve the established anchor/style placement when the
                # existing parser already reconstructs the same complete
                # targets. The outer grammar supplies newly missing roles.
                if original is not None and all(
                    "".join(u["pair"][side] for u in original)
                    == "".join(u["pair"][side] for u in units)
                    for side in (0, 1)
                ):
                    return original
                return units
            return self.effect_units(source, allow_opaque, description)
        units, at = [], 0
        for start, end in [*ranges, (len(source), len(source))]:
            part = source[at:start]
            if part:
                if (
                    self.detail_join
                    and re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", part) == self.detail_join[0]
                ):
                    units.append(
                        {
                            "source": part,
                            "pair": tuple(
                                part.replace(self.detail_join[0], t, 1)
                                for t in self.detail_join[1:]
                            ),
                            "separator": True,
                        }
                    )
                else:
                    outside = self.effect_units(part, allow_opaque, description)
                    if outside is None:
                        self.effect_unit_failures[source] = self.effect_unit_failures.get(part)
                        return None
                    units.extend(outside)
            if end > start:
                value = source[start:end]
                units.append(
                    {"source": value, "pair": (value, value), "opaque": True, "native_ruby": True}
                )
            at = end
        self.effect_unit_failures.pop(source, None)
        return units

    def effect_units(
        self, source, allow_opaque=False, description="", native_join=None, owned_units=None
    ):
        """Complete, scoped effect list; rejection cannot authorize fragments."""

        def refuse(reason):
            if len(self.effect_unit_failures) >= 20000:
                self.effect_unit_failures.clear()
            self.effect_unit_failures[source] = reason
            return None

        join = native_join or self.detail_join
        if not join:
            return refuse("missing_native_join_contract")
        if LINE_BREAK.search(source) or "<R" in source:
            return refuse("hard_line_or_native_ruby")
        # A complete native constructor owns any FORMAT8 inside its name.
        # Reject a veto of that whole constructor before considering lists,
        # but do not let a rejected internal partition veto a wider role.
        self.effect_unit_failures.pop(source, None)
        resolve = lambda value: (
            owned_units[value] if owned_units and value in owned_units else self._effect_unit(value)
        )
        whole = resolve(source)
        if (
            whole
            and not whole.get("member_sequence")
            and (whole.get("atomic") or join[0] not in source)
        ):
            return [whole]
        # Independent mixed groups supplement the existing member partition.
        # The dynamic program prefers its identical, already successful
        # segmented targets; the full constructor still covers a refused
        # internal homograph without borrowing that homograph as a role.
        if self.effect_unit_failures.get(source) in {
            "conflicting_effect_member",
            "unproven_direction_parameter",
        }:
            return None
        separator, *targets = join
        parts, links, at = [], [], 0
        # Native FORMAT8 can have its own complete color wrapper. Its controls
        # belong to the separator, not either adjacent effect's argument.
        expression = r"(?:<[Cc][0-9a-fA-F]+>)*" + re.escape(separator) + r"(?:</[Cc]>)*"
        for match in re.finditer(expression, source):
            decorated = match[0]
            openings = re.findall(r"<[Cc][0-9a-fA-F]+>", decorated)
            closings = re.findall(r"</[Cc]>", decorated)
            if len(openings) > 16 or len(closings) > 16:
                return refuse("invalid_separator_style")
            parts.append(source[at : match.start()])
            links.append(
                {
                    "source": decorated,
                    "pair": tuple(decorated.replace(separator, t, 1) for t in targets),
                    "separator": True,
                }
            )
            at = match.end()
        parts.append(source[at:])
        if len(parts) > 32:
            return refuse("member_budget")
        leading, trailing = parts[0] == "", parts[-1] == ""
        leading_link = links.pop(0) if leading and links else None
        trailing_link = links.pop() if trailing and links else None
        if leading:
            parts.pop(0)
        if trailing and parts:
            parts.pop()
        if not parts or any(not part for part in parts):
            return refuse("empty_effect_member")
        states = [None] * (len(parts) + 1)
        states[-1] = {("", ""): ([], 0, 0)}
        for start in range(len(parts) - 1, -1, -1):
            alternatives = {}
            for end in range(start + 1, len(parts) + 1):
                member = "".join(
                    part + (links[start + i]["source"] if start + i < end - 1 else "")
                    for i, part in enumerate(parts[start:end])
                )
                unit = resolve(member)
                if not unit:
                    failure = self.effect_unit_failures.get(member)
                    if failure in {
                        "invalid_effect_parameter",
                        "unproven_effect_parameter",
                        "unproven_direction_parameter",
                        "conflicting_effect_member",
                    }:
                        continue
                    pair = self.detail_contexts.get(description, {}).get(member)
                    if pair is None:
                        continue
                    unit = {"source": member, "pair": pair, "contextual": True}
                for suffix_pair, (suffix_units, suffix_count, suffix_atomic) in states[end].items():
                    link = links[end - 1] if suffix_units else None
                    pair = tuple(
                        value + (link["pair"][side] + suffix_pair[side] if suffix_units else "")
                        for side, value in enumerate(unit["pair"])
                    )
                    count = 1 + suffix_count
                    atomic = suffix_atomic + (len(member) if unit.get("atomic") else 0)
                    if pair not in alternatives or (atomic, count) > (
                        alternatives[pair][2],
                        alternatives[pair][1],
                    ):
                        alternatives[pair] = (
                            [unit] + ([link] + suffix_units if suffix_units else []),
                            count,
                            atomic,
                        )
                    if len(alternatives) > 128:
                        return refuse("partition_budget")
            if allow_opaque and not alternatives:
                failure = self.effect_unit_failures.get(parts[start])
                if failure in {
                    "invalid_effect_parameter",
                    "unproven_effect_parameter",
                    "unproven_direction_parameter",
                    "conflicting_effect_member",
                }:
                    states[start] = alternatives
                    continue
                member = parts[start]
                if re.search(
                    r"[<>]", re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>|<I\d{1,5}>", "", member)
                ):
                    return refuse("unsupported_effect_controls")
                # Preserve complete admitted roles fenced by native styles;
                # parameters stay verbatim, without global-word fallback or
                # removing internal controls to invent a constructor.
                fragments = []
                for index, part in enumerate(re.split(r"(</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)", member)):
                    known = None if index % 2 else self._effect_unit(part)
                    failure = self.effect_unit_failures.get(part)
                    if failure in {
                        "invalid_effect_parameter",
                        "unproven_effect_parameter",
                        "unproven_direction_parameter",
                        "conflicting_effect_member",
                    }:
                        fragments = None
                        break
                    fragments.append(
                        known or {"source": part, "pair": (part, part), "opaque": True}
                    )
                if fragments is None:
                    # A wider admitted constructor may still cover this
                    # partition. If none does, preserve the fragment veto on
                    # the whole member so legacy fallback cannot translate it.
                    self.effect_unit_failures[member] = failure
                    states[start] = alternatives
                    continue
                admitted = [part for part in fragments if part.get("semantic_ids")]
                member_pair = tuple(
                    "".join(part["pair"][side] for part in fragments) for side in (0, 1)
                )
                for suffix_units, count, atomic in states[start + 1].values():
                    link = links[start] if suffix_units else None
                    pair = tuple(
                        member_pair[side]
                        + (
                            link["pair"][side] + "".join(u["pair"][side] for u in suffix_units)
                            if suffix_units
                            else ""
                        )
                        for side in (0, 1)
                    )
                    alternatives[pair] = (
                        fragments + ([link] + suffix_units if suffix_units else []),
                        count + len(admitted),
                        atomic,
                    )
            states[start] = alternatives
        if not states[0]:
            partial = any(self._effect_unit(part) for part in parts)
            rejected = next(
                (
                    self.effect_unit_failures[part]
                    for part in parts
                    if self.effect_unit_failures.get(part)
                    in {
                        "invalid_effect_parameter",
                        "unproven_effect_parameter",
                        "unproven_direction_parameter",
                        "conflicting_effect_member",
                    }
                ),
                None,
            )
            return refuse(
                rejected or ("partial_effect_members" if partial else "unassociated_effect_unit")
            )
        atomic = max(value[2] for value in states[0].values())
        complete = [value for value in states[0].values() if value[2] == atomic]
        if len(complete) != 1:
            return refuse("different_partition_targets")
        units, _, _ = complete[0]
        if leading:
            units.insert(0, leading_link)
        if trailing:
            units.append(trailing_link)
        self.effect_unit_failures.pop(source, None)
        return units

    def _effect_rejected(self, source):
        reason = self.effect_unit_failures.get(source)
        return reason is not None and EFFECT_REFUSAL_POLICY.get(reason, "hard") == "hard"

    def item_help_header(self, source):
        if not self.details or not self.item_help_headers.get("rows"):
            return None
        edge = re.match(r"(?:</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)*", source)[0]
        separator = LINE_BREAK.search(source)
        line = source[len(edge) : separator.start() if separator else len(source)]
        boundary = self._detail_body_boundary(source)
        if not separator or (boundary and boundary[0] == separator.start()):
            tail = re.search(r"(?:</[Cc]>)*$", line)[0]
            framed = line[: len(line) - len(tail)] if tail else line
            compact = []
            for row in [
                *self.item_help_headers.get("compact_rows", []),
                *self.item_help_headers.get("attack_rows", []),
            ]:
                close = row.get("close")
                if not framed.startswith(row["prefix"]) or (
                    close and not framed.endswith(close[0])
                ):
                    continue
                inner = framed[
                    len(row["prefix"]) : len(framed) - len(close[0]) if close else len(framed)
                ]
                for join in ([" - "] * 3, [" "] * 3):
                    units = self.details.effect_units(inner, False, "", join)
                    if not units or any(
                        unit.get("opaque") and unit["source"].strip() for unit in units
                    ):
                        continue
                    opaque = lambda text: {"source": text, "pair": (text, text), "opaque": True}
                    compact.append(
                        {
                            "parts": [
                                opaque(edge),
                                *row["parts"],
                                *units,
                                *(
                                    [{"source": close[0], "pair": close[1:], "opaque": True}]
                                    if close
                                    else []
                                ),
                                opaque(tail),
                            ],
                            "end": boundary[0] if separator else len(source),
                            "effect_units": units,
                            "effect_join": join,
                        }
                    )
            if compact and len({tuple(tuple(p["pair"]) for p in m["parts"]) for m in compact}) == 1:
                selected = compact[0]
                if boundary and not self.details.raw_pair(boundary[2]):

                    def signature(units, join):
                        if not units:
                            return None
                        entities = [unit for unit in units if unit["source"] != join[0]]
                        if not entities or any(
                            unit.get("opaque") or not unit.get("semantic_ids") for unit in entities
                        ):
                            return None
                        return tuple(
                            (
                                re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", unit["source"]),
                                tuple(sorted(unit["semantic_ids"])),
                                tuple(unit.get("parameters", [])),
                            )
                            for unit in entities
                        )

                    expected = signature(selected["effect_units"], selected["effect_join"])
                    bodies = []
                    for record in self.item_help_headers["rows"]:
                        if (
                            expected is None
                            or record["body"] != boundary[2]
                            or not line.startswith(record["frame_prefix"])
                            or not record.get("body_pair")
                        ):
                            continue
                        if any(
                            signature(
                                self.details.effect_units(
                                    effect,
                                    False,
                                    boundary[2],
                                    join,
                                    record.get("owned_effect_units"),
                                ),
                                join,
                            )
                            == expected
                            for effect in record.get("body_effect_sources", [])
                            for join in ([" - "] * 3, [" "] * 3)
                        ):
                            bodies.append(record)
                    if bodies and len({tuple(record["body_pair"]) for record in bodies}) == 1:
                        selected["body_pair"] = bodies[0]["body_pair"]
                        selected["body_key"] = bodies[0]["body_key"]
                return selected
        rows = [
            row for row in self.item_help_headers["rows"] if line.startswith(row["frame_prefix"])
        ]
        if not rows:
            if boundary and any(
                line.find(row.get("frame_prefix") or row["prefix"]) > 0
                for row in [
                    *self.item_help_headers.get("compact_rows", []),
                    *self.item_help_headers.get("attack_rows", []),
                    *self.item_help_headers["rows"],
                ]
            ):
                original = source[: boundary[0]]
                return {
                    "parts": [{"source": original, "pair": (original, original), "opaque": True}],
                    "end": boundary[0],
                }
            return None
        if not boundary or not separator or boundary[0] != separator.start():
            if source in self.pairs:
                return None
            self.effect_unit_failures[source] = "item_help_header_missing_record_body"
            return None
        original = source[: boundary[0]]
        tail = re.search(r"(?:</[Cc]>)*$", line)[0]
        line = line[: len(line) - len(tail)] if tail else line
        matches = []
        for row in rows:
            if (
                boundary[2] != row["body"]
                or not line.startswith(row["prefix"])
                or not line.endswith(row["close"][0])
            ):
                continue
            inner = line[len(row["prefix"]) : len(line) - len(row["close"][0])]
            units = self.details.effect_units(
                inner, False, boundary[2], owned_units=row.get("owned_effect_units")
            )
            if not units or any(unit.get("opaque") and unit["source"].strip() for unit in units):
                if native_join := self.item_help_headers.get("native_effect_join"):
                    units = self.details.effect_units(
                        inner, False, boundary[2], native_join, row.get("owned_effect_units")
                    )
            # Rejected effects retain their whole header; the independently
            # identified physical body keeps its existing translation plan.
            if not units:
                continue
            if any(unit.get("opaque") and unit["source"].strip() for unit in units):
                continue

            def opaque(value):
                return {"source": value, "pair": (value, value), "opaque": True}

            parts = [
                opaque(edge),
                *row["parts"],
                *units,
                {"source": row["close"][0], "pair": row["close"][1:], "opaque": True},
                opaque(tail),
            ]
            matches.append(
                {
                    "parts": parts,
                    "end": boundary[0],
                    **(
                        {"body_pair": row["body_pair"], "body_key": row["body_key"]}
                        if inner in row.get("body_effect_sources", [])
                        else {}
                    ),
                }
            )
        owned = [m for m in matches if m.get("body_pair")]
        selected = owned or matches
        if (
            not selected
            or len(
                {
                    (tuple(tuple(p["pair"]) for p in m["parts"]), tuple(m.get("body_pair", ())))
                    for m in selected
                }
            )
            != 1
        ):
            return {
                "parts": [{"source": original, "pair": (original, original), "opaque": True}],
                "end": boundary[0],
            }
        return selected[0]

    def skill_header(self, source):
        if item_header := self.item_help_header(source):
            return item_header
        if self._effect_rejected(source):
            return None
        contract = self.skill_help_headers
        if not contract.get("formats") or not contract.get("close", [None])[0]:
            return None
        edge = re.match(r"(?:</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)*", source)[0]
        source_body, matches = source[len(edge) :], []
        for row in contract.get("compact_formats", []):
            if not source_body.startswith(row["source"]):
                continue
            end = len(edge) + len(row["source"])
            if source[end:] and not re.match(r"[ \t\r\n]", source[end:]):
                continue
            spacing = re.match(r"[ \t]*", source[end:])[0]
            matches.append(
                {
                    "parts": [
                        {"source": edge, "pair": (edge, edge), "opaque": True},
                        {
                            "source": row["source"],
                            "pair": tuple(row["pair"]),
                            "semantic_ids": row["ids"],
                            "parameters": [],
                        },
                        {"source": spacing, "pair": (spacing, spacing), "opaque": True},
                    ],
                    "end": end + len(spacing),
                }
            )
        for row in contract["formats"]:
            chunks = row["source"].split("%s")
            expression = re.escape(chunks[0])
            if len(chunks) == 2:
                expression += r"((?:<I[0-9]{1,5}>)?)" + re.escape(chunks[1])
            elif len(chunks) != 1:
                continue
            match = re.match(expression, source_body)
            if not match:
                continue
            remaining = source_body[match.end() :]
            close = remaining.find(contract["close"][0])
            if close < 0:
                continue
            style = re.fullmatch(
                r"((?:<I[0-9]{1,5}>|</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)*)([^<>]*?)((?:</[Cc]>)*)([ \t]*)",
                remaining[:close],
            )
            if not style:
                continue
            ranges = [r for r in contract["ranges"] if r["source"] == style[2]]
            if not ranges or len({tuple(r["pair"]) for r in ranges}) != 1:
                continue
            targets = [t.split("%s") for t in row["pair"]]
            if any(len(t) != len(chunks) for t in targets):
                continue

            def opaque(value):
                return {"source": value, "pair": (value, value), "opaque": True}

            parts = [opaque(edge)]
            for index, chunk in enumerate(chunks):
                parts.append(
                    {
                        "source": chunk,
                        "pair": tuple(t[index] for t in targets),
                        "semantic_ids": row["ids"],
                        "parameters": [],
                    }
                )
                if index == 0 and len(chunks) == 2:
                    parts.append(opaque(match[1]))
            parts.extend(
                (
                    opaque(style[1]),
                    {
                        "source": style[2],
                        "pair": tuple(ranges[0]["pair"]),
                        "semantic_ids": sorted({key for r in ranges for key in r["ids"]}),
                        "parameters": [],
                    },
                    opaque(style[3] + style[4]),
                    {
                        "source": contract["close"][0],
                        "pair": tuple(contract["close"][1:]),
                        "opaque": True,
                    },
                )
            )
            end = len(edge) + match.end() + close + len(contract["close"][0])
            spacing = re.match(r"[ \t]*", source[end:])[0]
            parts.append(opaque(spacing))
            matches.append({"parts": parts, "end": end + len(spacing)})
        if not matches or len({tuple(p["pair"] for p in m["parts"]) for m in matches}) != 1:
            return None
        return matches[0]

    def whole_conflict(self, source):
        stripped = re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", source)
        return any(
            value in self.ambiguous_display
            for value in (source, display_text(source), stripped, display_text(stripped))
        )

    def _whole_effect_pair(self, value):
        """Whole global admission, without free-form string/list assembly."""
        if self.whole_conflict(value):
            return None
        if value in self.plain_pairs:
            return self.plain_pairs[value]
        candidates = {
            tuple(_render_format(t, iter(match.groups())) for t in pair)
            for pattern, pair in self.numeric
            if all(field.group()[-1] != "s" for t in pair for field in _format_fields(t))
            and (match := pattern.fullmatch(value))
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    def effect_detail_plan(self, source, mode="annotation"):
        if not self.details:
            return None
        ranges = _ruby_ranges(source)
        if ranges is None:
            return None  # malformed/nested R never grants detail roles
        if self.whole_conflict(source):
            return None
        self.effect_unit_failures.pop(source, None)
        boundary = self._detail_body_boundary(source)
        header = self.skill_header(source)
        if self._effect_rejected(source):
            return None
        if ranges and not boundary and self.raw_pair(source) is None:
            self.effect_unit_failures[source] = "hard_line_or_native_ruby"
            return None
        if ranges and not boundary and not header:
            return None
        if not header and (
            self._detail_header(source) is not None or re.match(r"^(?:<[^<>]*>)*【", source)
        ):
            return None
        if not self.details or (
            not header
            and not boundary
            and not LINE_BREAK.search(source)
            and (not self.details.detail_join or self.details.detail_join[0] not in source)
        ):
            return None
        strip_styles = lambda value: re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", value)
        header_only = header is not None and header["end"] == len(source)
        lines = LINE_BREAK.split(source)
        empty_body = (
            not header and not boundary and len(lines) == 2 and bool(lines[0]) and not lines[1]
        )
        whole, normalized = (
            (self.pairs.get(source) if header_only else self.raw_pair(source)),
            False,
        )
        if whole is None and not header_only:
            value = strip_styles(source)
            whole = self._whole_effect_pair(value)
            normalized = whole is not None
        if not header and not boundary and not whole and not empty_body:
            return None
        text, layers, has_units, unproved, semantic_count = "", [], False, False, 0
        hard_failure = None
        whole_veto = False
        reconstructed = ["", ""]

        def emit(part):
            nonlocal text
            a, b = part["pair"]
            plan = (
                annotation_plan(a, b)
                if mode == "annotation" and not part.get("opaque") and needs_annotation(a, b)
                else {"text": b if mode == "secondary" else a, "layers": []}
            )
            offset = len(text.encode("utf-8"))
            layers.extend(
                dict(
                    layer,
                    offset=layer["offset"] + offset,
                    **(
                        {"semantic_ids": part["semantic_ids"], "parameters": part["parameters"]}
                        if part.get("semantic_ids")
                        else {}
                    ),
                )
                for layer in plan["layers"]
            )
            text += plan["text"]

        if header:
            for part in header["parts"]:
                for side in (0, 1):
                    reconstructed[side] += part["pair"][side]
                emit(part)
        prefix = source[header["end"] if header else 0 : boundary[0] if boundary else len(source)]
        for index, line in enumerate(re.split(r"(\r\n|\n|\\n)", prefix)):
            if index % 2:
                text += line
                for side in (0, 1):
                    reconstructed[side] += line
                continue
            if (header or empty_body) and not line:
                continue
            candidate = strip_styles(line).strip(" \t")
            if candidate in self.details.detail_effect_blocked_literals or any(
                pattern.fullmatch(candidate)
                for pattern in self.details.detail_effect_blocked_numeric
            ):
                whole_veto = True
            units = self.details.effect_line_units(
                line, bool(header or boundary), boundary[2] if boundary else ""
            )
            # An exact admitted native frame may place styles inside a complete
            # field (for example SELF followed by a coloured direction field).
            # Its full global pair, not stripped controls alone, authorizes the
            # frame. Keep the existing role/parameter identity on that field.
            frame = self.raw_pair(line)
            stripped_line = strip_styles(line)
            role = self.details._effect_unit(stripped_line)
            if empty_body and role and role.get("member_sequence"):
                # Without a resource body, internal labels cannot borrow
                # standalone authority. This complete raw slot constructor
                # itself owns the empty-body field and its parameters.
                complete = self.details._effect_unit(line)
                if complete:
                    units = [complete]
            if (
                self.details.effect_unit_failures.get(stripped_line)
                == "unproven_direction_parameter"
            ):
                # Refuse this complete header, then inspect later lines for
                # a whole-constructor veto before preserving the independent
                # admitted body. This matches the final JS callback path.
                hard_failure = "unproven_direction_parameter"
                continue
            if (
                empty_body
                and not frame
                and any(token in line for token in self.details.detail_effect_direction_frames)
                and not any(
                    set(unit.get("semantic_ids", ())) & self.details.detail_effect_constructor_ids
                    for unit in units or ()
                )
            ):
                self.effect_unit_failures[source] = "unproven_standalone_constructor"
                return None
            if (
                (units is None or any(unit.get("opaque") for unit in units))
                and frame
                and role
                and set(role.get("semantic_ids", ())) & self.details.detail_effect_constructor_ids
                and tuple(map(strip_styles, frame)) == tuple(map(strip_styles, role["pair"]))
            ):
                units = [{**role, "source": line, "pair": frame}]
            if units is None:
                if (
                    empty_body
                    and self.details.effect_unit_failures.get(line) == "partial_effect_members"
                ):
                    self.effect_unit_failures[source] = "unproven_standalone_constructor"
                    return None
                if self.details._effect_rejected(line):
                    hard_failure = self.details.effect_unit_failures.get(line)
                if header or not boundary:
                    unproved = True
                    continue
                description = boundary[2]
                text += self.details.translate(line, "annotation", detail_context=description)
                for side, target in enumerate(("primary", "secondary")):
                    reconstructed[side] += self.details.translate(
                        line, target, detail_context=description
                    )
                continue
            if (
                not header
                and boundary
                and (ranges or not re.search(r"\[|\]| - ", line))
                and any(
                    unit.get("opaque")
                    and not unit.get("native_ruby")
                    and strip_styles(unit["source"]).strip()
                    for unit in units
                )
                and any(unit.get("semantic_ids") for unit in units)
            ):
                # A complete resource body does not grant effect identity to
                # an unknown neighbour or native reading in its header.
                unproved = True
                continue
            if empty_body:
                if not any(
                    set(unit.get("semantic_ids", ())) & self.details.detail_effect_constructor_ids
                    for unit in units
                ):
                    return None
                for unit in units:
                    if unit.get("separator"):
                        continue
                    member = strip_styles(unit["source"]).strip(" \t")
                    pair = self._whole_effect_pair(member)
                    if (
                        not set(unit.get("semantic_ids", ()))
                        & self.details.detail_effect_constructor_ids
                        or pair is None
                        or tuple(strip_styles(t).strip(" \t") for t in unit["pair"])
                        != tuple(t.strip(" \t") for t in pair)
                    ):
                        self.effect_unit_failures[source] = "unproven_standalone_constructor"
                        return None
            for unit in units:
                for side in (0, 1):
                    reconstructed[side] += unit["pair"][side]
            owned = _owned_secondary_lines([unit["pair"][1] for unit in units])
            for unit_index, unit in enumerate(units):
                a, b = unit["pair"]
                if unit.get("separator"):
                    text += b if mode == "secondary" else a
                    continue
                if owned is not None:
                    b = owned[unit_index]
                if unit.get("semantic_ids") or unit.get("contextual"):
                    has_units = True
                    semantic_count += 1
                if unit.get("native_ruby") and boundary:
                    has_units = True
                emit({**unit, "pair": (a, b if mode == "annotation" else unit["pair"][1])})
        if hard_failure:
            self.effect_unit_failures[source] = hard_failure
        if (hard_failure or unproved) and boundary and not whole and not whole_veto:
            # Preserve the rejected header exactly. Its separately admitted
            # complete description retains translation and its own line plan.
            end, description = boundary[1], boundary[2]
            wrapper = source[end : len(source) - len(description)]
            body = self.details.render(description, mode)
            prefix = source[:end] + wrapper
            offset = len(prefix.encode("utf-8"))
            return {
                "text": prefix + body["text"],
                "layers": [
                    dict(layer, offset=layer["offset"] + offset) for layer in body["layers"]
                ],
                "kind": body["kind"],
            }
        if hard_failure:
            return None
        if (
            (not has_units and not header)
            or unproved
            or (not header and not boundary and not empty_body and semantic_count < 2)
        ):
            return None
        if boundary:
            start, end, description = boundary
            wrapper = source[end : len(source) - len(description)]
            body_source, separator = wrapper + description, source[start:end]
            body_pair = header.get("body_pair") if header else None
            body = (
                (
                    annotation_plan(*body_pair)
                    if mode == "annotation" and needs_annotation(*body_pair)
                    else {"text": body_pair[mode == "secondary"], "layers": [], "kind": "plain"}
                )
                if body_pair
                else self.details.render(description, mode)
            )
            body = {
                **body,
                "text": wrapper + body["text"],
                "layers": [
                    dict(layer, offset=layer["offset"] + len(wrapper.encode("utf-8")))
                    for layer in body["layers"]
                ],
            }
            # Native layered rows collect empty-anchor lanes; an inline-ruby
            # body would miss that ownership, scale and newline-gap protocol.
            if mode == "annotation" and (layers or ranges) and body["kind"] == "ruby":
                body = annotation_plan(
                    wrapper
                    + (
                        body_pair[0]
                        if body_pair
                        else self.details.translate(description, "primary")
                    ),
                    wrapper
                    + (
                        body_pair[1]
                        if body_pair
                        else self.details.translate(description, "secondary")
                    ),
                )
            text += separator
            offset = len(text.encode("utf-8"))
            layers.extend(dict(layer, offset=layer["offset"] + offset) for layer in body["layers"])
            text += body["text"]
            for side, target in enumerate(("primary", "secondary")):
                reconstructed[side] += (
                    separator
                    + wrapper
                    + (
                        body_pair[side]
                        if body_pair
                        else self.details.translate(description, target)
                    )
                )
        if whole and any(
            target != (strip_styles(reconstructed[side]) if normalized else reconstructed[side])
            for side, target in enumerate(whole)
        ):
            return None
        return {
            "text": text,
            "layers": layers,
            "kind": "layered" if layers else "ruby" if "<R>" in text else "plain",
        }

    def _detail_join_pair(self, source):
        if not self.detail_join:
            return None
        if self._effect_rules and self.detail_join[0] in source:
            self.effect_units(source)
            if self._effect_rejected(source):
                return None
        separator, *targets = self.detail_join
        short = separator.rstrip()
        partial_tail = bool(
            short
            and short != separator
            and source.endswith(short)
            and not source.endswith(separator)
        )
        expanded = source + separator[len(short) :] if partial_tail else source
        parts = expanded.split(separator)
        if len(parts) < 2 or not any(parts) or any(not part for part in parts[1:-1]):
            return None
        pairs = [("", "")] if not parts[0] else []
        start, stop = int(not parts[0]), len(parts) - int(not parts[-1])
        while start < stop:
            # A proven constructor may itself contain FORMAT8 (e.g. revive +
            # recovery). Preserve the complete resource pair before splitting
            # it into shorter labels with potentially different official words.
            for end in range(stop, start, -1):
                member = separator.join(parts[start:end])
                if member in self.detail_join_blocked_literals or any(
                    pattern.fullmatch(member) for pattern in self.detail_join_blocked_numeric
                ):
                    return None
                if (
                    member in self.ambiguous_display and member not in self.detail_join_pairs
                ) or not (
                    member in self.detail_join_literals
                    or any(pattern.fullmatch(member) for pattern in self.detail_join_numeric)
                ):
                    continue
                pair = self.detail_join_pairs.get(member) or self.pair(member)
                if pair:
                    pairs.append(pair)
                    start = end
                    break
            else:
                return None
        if not parts[-1]:
            pairs.append(("", ""))
        result = []
        for side, target in enumerate(targets):
            value = target.join(pair[side] for pair in pairs)
            if partial_tail and target != target.rstrip():
                value = value[: -len(target)] + target.rstrip()
            result.append(value)
        return tuple(result)

    def _component_parts(self, source, allow_detail_join=True):
        parts = SEPARATORS.split(source)
        if self.detail_join and allow_detail_join:
            separator = self.detail_join[0]
            at = 1
            while at < len(parts) - 1:
                if parts[at] != separator:
                    at += 2
                    continue
                end = at
                while end + 2 < len(parts) and parts[end + 2] == separator:
                    end += 2
                combined = "".join(parts[at - 1 : end + 2])
                if self._detail_join_pair(combined):
                    parts[at - 1 : end + 2] = [combined]
                else:
                    at = end + 2
        return COMPONENT_LINKS.split(source) if len(parts) == 1 else parts

    def has_detail_context(self, source, description):
        values = self.detail_contexts.get(description, {})
        ranges = _ruby_ranges(source)
        return ranges is not None and any(
            any(not _overlaps((at, at + len(span)), ranges) for at in _find_all(source, span))
            for span in values
        )

    def _replace_detail_context(self, source, mode, description):
        values = self.detail_contexts.get(description, {})
        ranges = _ruby_ranges(source)
        if not values or ranges is None:
            return source
        selected = []
        for span, pair in values.items():
            target = pair[0 if mode != "secondary" else 1]
            for at in _find_all(source, span):
                match = (at, at + len(span))
                if not _overlaps(match, ranges):
                    selected.append((match, target))
        selected.sort()
        if any(left[0][1] > right[0][0] for left, right in zip(selected, selected[1:])):
            return source
        for (start, end), value in reversed(selected):
            source = source[:start] + value + source[end:]
        return source

    def has_detail_inline_icon(self, source):
        ranges = _ruby_ranges(source)
        if ranges is None:
            return False
        return any(
            not _overlaps(match.span(), ranges)
            for pattern, _pair in self.detail_inline_icons
            for match in pattern.finditer(source)
        )

    def _replace_detail_inline_icons(self, source, mode):
        """Replace only unambiguous complete icon-bearing spans in an anchored detail."""
        ranges = _ruby_ranges(source)
        if ranges is None:
            return source
        matches = {}
        for pattern, pair in self.detail_inline_icons:
            for match in pattern.finditer(source):
                target = pair[0 if mode != "secondary" else 1]
                rendered = _render_format(target, iter(match.groups()))
                matches.setdefault(match.span(), set()).add(rendered)
        conflicting = [span for span, values in matches.items() if len(values) != 1]
        selected = [
            (span, next(iter(values)))
            for span, values in matches.items()
            if len(values) == 1 and not _overlaps(span, conflicting) and not _overlaps(span, ranges)
        ]
        selected.sort()
        if any(left[0][1] > right[0][0] for left, right in zip(selected, selected[1:])):
            return source
        for (start, end), value in reversed(selected):
            source = source[:start] + value + source[end:]
        return source

    def _anchored_details(self, source):
        if not self.details:
            return None
        # A full description supplies a more specific effect-record context
        # than the header alone; preserve it when both anchors are present.
        boundary = self._detail_body_boundary(source)
        if boundary:
            return self.details, boundary[2]
        return (
            (self.details, "")
            if self._detail_header(source) is not None or self.skill_header(source)
            else None
        )

    def _detail_body_boundary(self, source):
        if not self.details:
            return None
        for separator in LINE_BREAK.finditer(source):
            suffix = source[separator.end() :]
            for _ in range(16):
                if suffix in self.detail_sources:
                    return separator.start(), separator.end(), suffix
                control = re.match(r"</?[Cc][0-9a-fA-F]*>|</?B>|<[sS]\d+>", suffix)
                if not control:
                    break
                suffix = suffix[control.end() :]
        return None

    def _detail_header(self, source):
        original = LINE_BREAK.split(source)[0]
        if original in self.detail_header_literals:
            return original
        header = re.sub(r"(?:</[Cc]>|</B>)+$", "", original)
        for _ in range(16):
            if any(
                header.startswith(prefix)
                and header.endswith(suffix)
                and len(header) >= len(prefix) + len(suffix)
                for prefix, suffix in self.detail_headers
            ):
                return original
            control = re.match(r"</?[Cc][0-9a-fA-F]*>|</?B>|<[sS]\d+>", header)
            if not control:
                break
            header = header[control.end() :]
        return None

    def literal_argument(self, source, side):
        """Resolve a string slot without re-entering numeric/printf matching."""
        # A printf string slot has no independent resource identity. Separators
        # must not inherit the translation of a punctuation-only script line.
        if not any(char.isalnum() for char in source):
            return source
        if source in self.ambiguous_display:
            return source
        if source in self.pairs:
            return self.pairs[source][side]
        if source in self.plain_pairs:
            return self.plain_pairs[source][side]
        parts = SEPARATORS.split(source)
        if len(parts) == 1:
            parts = COMPONENT_LINKS.split(source)
        if len(parts) == 1:
            return source
        return "".join(
            self.literal_argument(part, side) if i % 2 == 0 else part
            for i, part in enumerate(parts)
        )

    def condition_list_pair(self, source):
        unit = self.condition_list_unit(source)
        return None if unit is None else unit["pair"]

    def condition_list_unit(self, source):
        edge = re.fullmatch(
            r"((?:</?[Cc][0-9a-fA-F]*>|<[sS]\d+>)*)(.*?)((?:</[Cc]>)*)((?:\s)*)", source
        )
        if not edge:
            return None
        prefix, core, suffix, trailing = edge.groups()
        if source in self.ambiguous_display or core in self.ambiguous_display:
            return None
        # Prefer a complete typed constructor to this generic string slot.
        if any(row.get("ids") and pattern.fullmatch(core) for row, pattern in self._effect_rules):
            return None
        found = {}
        for row in self.condition_lists:
            chunks = row["templates"][0].split("%s")
            if len(chunks) != 2 or not core.startswith(chunks[0]) or not core.endswith(chunks[1]):
                continue
            argument = core[len(chunks[0]) : len(core) - len(chunks[1])]
            percent = row["percent"][0].split("%d")
            if len(percent) != 2 or not row["links"][0]:
                continue
            match = re.fullmatch(
                r"(.*)([ \t\u3000])"
                + re.escape(percent[0])
                + r"([0-9]{1,3})"
                + re.escape(percent[1].replace("%%", "%")),
                argument,
            )
            if not match or int(match[3]) > 100:
                continue
            members = match[1].split(row["links"][0])
            if (
                len(members) > 32
                or len(set(members)) != len(members)
                or any(m not in row["names"] for m in members)
            ):
                continue
            pair = tuple(
                prefix
                + row["templates"][side + 1].replace(
                    "%s",
                    row["links"][side + 1].join(row["names"][m][side] for m in members)
                    + match[2]
                    + row["percent"][side + 1].replace("%d", match[3]).replace("%%", "%"),
                )
                + suffix
                + trailing
                for side in (0, 1)
            )
            found[pair] = {
                "source": source,
                "pair": pair,
                "semantic_ids": [f"table/t_itemhelp.tbl/generated/condition_list/{row['id']}"],
                "parameters": [*members, match[3]],
            }
        return next(iter(found.values())) if len(found) == 1 else None

    def raw_pair(self, source):
        condition = self.condition_list_pair(source)
        if condition:
            return condition
        if source in self.pairs:
            return self.pairs[source]
        # Layout-owned size controls are not part of a resource's identity.
        # Peel only this leading wrapper, and only for a complete admitted
        # literal: token-wise matching would split coloured prompt arguments.
        size = re.match(r"^(?:<[sS]\d+>)+", source)
        if size and (pair := self.pairs.get(source[size.end() :])):
            return tuple(size[0] + target for target in pair)
        producer = self.producer_pair(source)
        if producer:
            return producer
        if "<" not in source:
            return None
        matches = set()
        for pattern, pair in self.raw_numeric:
            m = pattern.fullmatch(source)
            if not m:
                continue
            rendered = []
            for side, target in enumerate(pair):
                values = (
                    self.literal_argument(v, side) if field.group().endswith("s") else v
                    for field, v in zip(_format_fields(target), m.groups())
                )
                rendered.append(_render_format(target, values))
            matches.add(tuple(rendered))
        return next(iter(matches)) if len(matches) == 1 else None

    def pair(self, source):
        producer = self.producer_pair(source)
        if producer:
            return producer
        if source in self.plain_pairs:
            return self.plain_pairs[source]
        # A list of known labels is stronger evidence than a free-form %s
        # template consuming the previous labels as part of its argument.
        parts = COMPONENT_LINKS.split(source)
        pairs = [
            (self.pairs.get(part) or self.plain_pairs.get(part))
            if any(char.isalnum() for char in part)
            else None
            for part in parts[::2]
        ]
        if len(parts) > 1 and all(pairs):
            return tuple(
                "".join(pairs[i // 2][side] if i % 2 == 0 else part for i, part in enumerate(parts))
                for side in (0, 1)
            )
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
        literal_matches = set()
        for pattern, pair in self.numeric:
            m = pattern.fullmatch(source)
            if m:
                rendered = []
                for side, target in enumerate(pair):
                    # Name arguments are translated only by an exact known pair;
                    # unknown player-defined values are preserved verbatim.
                    values = (
                        self.literal_argument(v, side) if field.group().endswith("s") else v
                        for field, v in zip(_format_fields(target), m.groups())
                    )
                    rendered.append(_render_format(target, values))
                # A numeric-only template identifies the complete wording.
                # A free-form string constructor may consume that wording too,
                # but cannot veto it by arbitrarily dividing adjacent %s slots.
                selected = (
                    matches
                    if any(m.group()[-1] == "s" for m in _format_fields(pair[0]))
                    else literal_matches
                )
                selected.add(tuple(rendered))
        selected = literal_matches or matches
        return next(iter(selected)) if len(selected) == 1 else None

    def producer_pair(self, source, rules=None):
        matches = set()
        narrow = str.maketrans("０１２３４５６７８９", "0123456789")
        wide = str.maketrans("0123456789", "０１２３４５６７８９")
        for pattern, pair, styles in self.producer_numeric if rules is None else rules:
            match = pattern.fullmatch(source)
            if not match:
                continue
            values = [value.translate(narrow) for value in match.groups()]
            if any(not -2147483648 <= int(value) <= 2147483647 for value in values):
                continue
            matches.add(
                tuple(
                    _render_format(
                        target,
                        iter(
                            value.translate(wide) if style == "fullwidth" else value
                            for value, style in zip(values, widths)
                        ),
                    )
                    for target, widths in zip(pair, styles)
                )
            )
        return next(iter(matches)) if len(matches) == 1 else None

    def component(self, source, mode, allow_detail_join=True):
        # Whole dialogue/keyed lookup happens before decomposition. Once a
        # rich-text run is split, punctuation alone is only a separator.
        if not any(char.isalnum() for char in source):
            return source
        # A numeric run between native controls is presentation data, not a
        # translatable label. In particular, keep icon multipliers verbatim.
        if re.search(r"[0-9０-９]", source) and re.fullmatch(
            r"[\s×+−\-0-9０-９.,，．%％]+", source
        ):
            return source
        # Complete literals keep priority. A validated effect list is stronger
        # than a free-form %s template consuming previous effects as an argument.
        pair = (
            self.plain_pairs.get(source) or self._detail_join_pair(source) or self.pair(source)
            if self.detail_join and allow_detail_join
            else self.pair(source)
        )
        if pair:
            a, b = pair
            if mode == "primary":
                return a
            if mode == "secondary":
                return b
            value = ruby(a, b)
            if value is not None:
                return value
        if allow_detail_join and self._effect_rejected(source):
            return source
        # Whitespace and punctuation delimit complete indexed components.
        # Middle dots also join inline lists, not just leading bullets. Split
        # any number of members; complete resource pairs above still win.
        stripped = source.strip()
        if stripped != source and stripped:
            inner = self.component(stripped, mode, allow_detail_join)
            if inner != stripped:
                start = source.index(stripped)
                return source[:start] + inner + source[start + len(stripped) :]
        parts = self._component_parts(source, allow_detail_join)
        if len(parts) > 1:
            return "".join(
                self.component(p, mode, allow_detail_join) if i % 2 == 0 else p
                for i, p in enumerate(parts)
            )
        return source

    def _detail_join_icon_runs(self, source, include_rejected=False):
        if not (
            self.detail_join
            and "<I" in source
            and "<R>" not in source
            and self.detail_join[0] in source
            and not self.raw_pair(source)
        ):
            return None
        runs = re.split(r"(" + STYLE.pattern + r"|<S\d+>|\r\n|\n|\\n)", source)
        joined = {
            index
            for index, run in enumerate(runs)
            if index % 2 == 0 and "<I" in run and self._detail_join_pair(run)
        }
        return (runs, joined) if joined or include_rejected else None

    def translate(self, source, mode="annotation", detail_context=None):
        if self.bracer_history_frame:
            return self.render(source, mode)["text"]
        if _ruby_ranges(source) is None:
            return source
        if mode == "bilingual":
            mode = "annotation"
        if self.same_language and mode == "annotation":
            mode = "primary"
        if source not in self.ambiguous_display and (
            facility := self.npc_facilities.get(source) or self.notebook_lists.get(source)
        ):
            return (
                facility[0 if mode == "primary" else 1]
                if mode in ("primary", "secondary")
                else (ruby(*facility) or facility[0])
            )
        if self.whole_conflict(source):
            return source
        if self.details:
            if effects := self.effect_detail_plan(source, mode):
                return effects["text"]
        if self.effect_unit_failures.get(source, "").startswith("item_help_header_"):
            return source
        if self._effect_rejected(source) and self.raw_pair(source) is None:
            return source
        if self.raw_pair(source) is None:
            typed = self.details or self
            typed._effect_unit(source)
            stripped = re.sub(r"</?[Cc][0-9a-fA-F]*>|<[sS]\d+>", "", source)
            typed._effect_unit(stripped)
            if typed.effect_unit_failures.get(stripped) == "unproven_direction_parameter":
                return source
            if typed.effect_unit_failures.get(source) in {
                "invalid_effect_parameter",
                "unproven_effect_parameter",
                "unproven_direction_parameter",
            }:
                return source
        if (
            mode in ("primary", "secondary")
            and (detail_context is None or not self.detail_join)
            and source not in self.ambiguous_display
            and display_text(source) not in self.ambiguous_display
            and (complete := self.raw_pair(source))
        ):
            return complete[0 if mode == "primary" else 1]
        if not self.raw_pair(source) and any(
            pattern.fullmatch(value)
            for pattern in self.resource_formatter_patterns
            for value in (source, plain(source))
        ):
            return source
        # The game's item/skill description constructor appends the complete
        # database description after an effect header. That exact suffix is an
        # anchor for resolving header terms within the item/skill tables, where
        # a word like 强化 means 強化 rather than the shop command 強化する.
        if anchored := self._anchored_details(source):
            details, context = anchored
            boundary = self._detail_body_boundary(source)
            if boundary and self.raw_pair(source) is None:
                start, end, description = boundary
                # The description is an exact resource, possibly wrapped in
                # UI style commands. Resolve it whole; its line breaks cannot
                # authorize borrowing from the independently built effects.
                wrapper = source[end : len(source) - len(description)]
                return (
                    details.translate(source[:start], mode, detail_context=context)
                    + source[start:end]
                    + wrapper
                    + details.translate(description, mode)
                )
            return details.translate(source, mode, detail_context=context)
        if detail_context is not None and self.detail_join:
            lines = re.split(r"(\r\n|\n|\\n)", source)
            resolved = []
            for index, line in enumerate(lines):
                units = (
                    self.effect_line_units(line, description=detail_context)
                    if index % 2 == 0
                    else None
                )
                if units:
                    resolved.append(
                        "".join(
                            unit["pair"][0 if mode == "primary" else 1]
                            if mode in ("primary", "secondary")
                            else unit["pair"][0]
                            if unit.get("separator") or unit.get("opaque")
                            else (ruby(*unit["pair"]) or unit["pair"][0])
                            for unit in units
                        )
                    )
                else:
                    if (
                        index % 2 == 0
                        and self._effect_rejected(line)
                        and self.raw_pair(line) is None
                    ):
                        resolved.append(line)
                        continue
                    fallback = (
                        self._replace_detail_context(line, mode, detail_context)
                        if detail_context
                        else line
                    )
                    resolved.append(line if index % 2 else self.translate(fallback, mode))
            return "".join(resolved)
        if detail_context:
            source = self._replace_detail_context(source, mode, detail_context)
        if self.detail_inline_icons:
            source = self._replace_detail_inline_icons(source, mode)
        if joined_runs := self._detail_join_icon_runs(source, include_rejected=True):
            # An inline icon is data inside a proven effect member, not a
            # boundary between that member and the neighboring effects.
            runs, joined = joined_runs
            translated = []
            for index, run in enumerate(runs):
                if index % 2:
                    translated.append(run)
                elif index in joined:
                    translated.append(self.component(run, mode))
                else:
                    translated.append(
                        "".join(
                            part if offset % 2 else self.component(part, mode, "<I" not in run)
                            for offset, part in enumerate(TOKEN.split(run))
                        )
                    )
            return "".join(translated)
        # Only admitted complete literals reach this path. Mutable emotion
        # headers cannot rescue an ambiguous body; those are removed at model
        # compilation so native provenance capture sees the same eligibility.
        exact = self.pairs.get(source)
        if exact and mode in ("primary", "secondary"):
            return exact[0 if mode == "primary" else 1]
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
        if _ruby_ranges(source) is None:
            return {"text": source, "layers": [], "kind": "plain"}
        if mode == "bilingual":
            mode = "annotation"
        if self.same_language and mode == "annotation":
            mode = "primary"
        if self.bracer_history_frame:
            pair = self.raw_pair(source)
            if pair is None:
                return {"text": source, "layers": [], "kind": "plain"}
            if mode == "annotation" and needs_annotation(*pair):
                return annotation_plan(*pair, preserve_lines=True)
            return {"text": pair[mode == "secondary"], "layers": [], "kind": "plain"}
        if source not in self.ambiguous_display and (
            facility := self.npc_facilities.get(source) or self.notebook_lists.get(source)
        ):
            if mode == "annotation" and needs_annotation(*facility):
                return annotation_plan(*facility)
            return {
                "text": facility[0 if mode != "secondary" else 1],
                "layers": [],
                "kind": "plain",
            }
        if self.whole_conflict(source):
            return {"text": source, "layers": [], "kind": "plain"}
        if effects := self.effect_detail_plan(source, mode):
            return effects
        if self.effect_unit_failures.get(source, "").startswith("item_help_header_"):
            return {"text": source, "layers": [], "kind": "plain"}
        header = self._detail_header(source) if self.details else None
        if mode == "annotation" and header is not None:
            # The two header labels own their annotations; opaque arguments
            # must not enter the body's rich-text annotation/reflow lane.
            head = (
                self.details.render(header, mode) if header in self.detail_header_literals else None
            )
            text = head["text"] if head else self.details.translate(header, mode)
            head_layers = head["layers"] if head else []
            rest = source[len(header) :]
            separator = LINE_BREAK.match(rest)
            if separator:
                text += separator[0]
                body = self.render(rest[separator.end() :], mode)
                if head_layers and body["kind"] == "ruby":
                    # A layered header and its body share the native owned-lane
                    # protocol. Inline body ruby would have no owned body lane.
                    body_source = rest[separator.end() :]
                    body = annotation_plan(
                        self.translate(body_source, "primary"),
                        self.translate(body_source, "secondary"),
                    )
                offset = len(text.encode("utf8"))
                return {
                    "text": text + body["text"],
                    "layers": head_layers
                    + [dict(layer, offset=layer["offset"] + offset) for layer in body["layers"]],
                    "kind": "layered"
                    if head_layers or body["layers"]
                    else "ruby"
                    if "<R>" in text + body["text"]
                    else "plain",
                }
            return {
                "text": text,
                "layers": head_layers,
                "kind": "layered" if head_layers else "ruby" if "<R>" in text else "plain",
            }
        a = self.translate(source, "primary")
        b = self.translate(source, "secondary")
        if mode == "annotation" and (
            not needs_annotation(a, b)
            or (a == b == source and display_text(source) in self.ambiguous_display)
        ):
            return {"text": a, "layers": [], "kind": "plain"}
        boundary = self._detail_body_boundary(source) if mode == "annotation" else None
        if (
            boundary
            and self.raw_pair(source) is None
            and len(LINE_BREAK.split(a)) != len(LINE_BREAK.split(b))
        ):
            start, end, description = boundary
            wrapper = source[end : len(source) - len(description)]
            body_a, body_b = (
                wrapper + self.details.translate(description, side)
                for side in ("primary", "secondary")
            )
            separator = source[start:end]
            if a.endswith(separator + body_a) and b.endswith(separator + body_b):
                header_a, header_b = a[: -len(separator + body_a)], b[: -len(separator + body_b)]
                plans = [
                    annotation_plan(x, y)
                    if needs_annotation(x, y)
                    else {"text": x, "layers": [], "kind": "plain"}
                    for x, y in ((header_a, header_b), (body_a, body_b))
                ]
                header_plan, body_plan = plans
                prefix = header_plan["text"] + separator
                offset = len(prefix.encode("utf-8"))
                layers = header_plan["layers"] + [
                    dict(layer, offset=layer["offset"] + offset) for layer in body_plan["layers"]
                ]
                return {
                    "text": prefix + body_plan["text"],
                    "layers": layers,
                    "kind": "layered" if layers else "plain",
                }
        anchored = self._anchored_details(source)
        known = (
            self.raw_pair(source) is not None
            or self.raw_pair(display_text(source)) is not None
            or bool(anchored and anchored[0].has_detail_inline_icon(source))
            or bool(anchored and anchored[0].has_detail_context(source, anchored[1]))
            or bool(anchored and anchored[0]._detail_join_icon_runs(source))
        )
        if mode == "annotation" and known:
            prefix = re.match(r"^(?:<#[^<>]*>)*", a)[0]
            body = a[len(prefix) :]
            visible_b = visual_secondary(b)
            if "<" not in body + visible_b and len(re.split(r"\r\n|\n|\\n", body)) == len(
                re.split(r"\r\n|\n|\\n", visible_b)
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
            **({"bracer_history_frame": True} if self.bracer_history_frame else {}),
            "plain_pairs": self.plain_pairs,
            "numeric": [(pattern.pattern, pair) for pattern, pair in self.numeric],
            "raw_numeric": [(pattern.pattern, pair) for pattern, pair in self.raw_numeric],
            "producer_numeric": [
                (pattern.pattern, pair, styles) for pattern, pair, styles in self.producer_numeric
            ],
            "producer_numeric_rejections": self.producer_numeric_rejections,
            "detail_numeric": [(pattern.pattern, pair) for pattern, pair in self.detail_numeric],
            "detail_inline_icons": [
                (pattern.pattern, pair) for pattern, pair in self.detail_inline_icons
            ],
            "detail_contexts": self.detail_contexts,
            "condition_lists": self.condition_lists,
            "skill_help_headers": self.skill_help_headers,
            **({"item_help_headers": self.item_help_headers} if self.item_help_headers else {}),
            "npc_facilities": self.npc_facilities,
            "notebook_lists": self.notebook_lists,
            "detail_join": self.detail_join,
            "detail_join_literals": sorted(self.detail_join_literals),
            "detail_join_pairs": self.detail_join_pairs,
            "detail_effect_units": self.detail_effect_units,
            "detail_effect_constructor_ids": sorted(self.detail_effect_constructor_ids),
            "detail_effect_direction_guards": self.detail_effect_direction_guards,
            "detail_effect_direction_frames": self.detail_effect_direction_frames,
            "detail_effect_blocked_literals": sorted(self.detail_effect_blocked_literals),
            "detail_effect_blocked_numeric": [
                p.pattern for p in self.detail_effect_blocked_numeric
            ],
            "detail_effect_rejections": self.detail_effect_rejections,
            "detail_join_numeric": [pattern.pattern for pattern in self.detail_join_numeric],
            "detail_join_blocked_literals": sorted(self.detail_join_blocked_literals),
            "detail_join_blocked_numeric": [
                pattern.pattern for pattern in self.detail_join_blocked_numeric
            ],
            "same_language": self.same_language,
            "ambiguous_display": sorted(self.ambiguous_display),
            "display_rejections": self.display_rejections,
            "resource_formatter_patterns": [p.pattern for p in self.resource_formatter_patterns],
            "keyed": keyed,
            "detail_sources": sorted(self.detail_sources),
            "detail_headers": self.detail_headers,
            "detail_header_literals": sorted(self.detail_header_literals),
            "details": self.details.runtime_model() if self.details else None,
            "scoped": {k: v.runtime_model() for k, v in self.scoped.items()},
            "save_confirmation_prefixes": self.save_confirmation_prefixes,
        }
