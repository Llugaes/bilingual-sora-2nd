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
SEPARATORS = re.compile(
    r"(\r\n|\n|\\n|[【】「」：:／/]| - |[ \u3000]{2,}|^[ \u3000]*[·・][ \u3000]*)"
)


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
    right = re.split(r"\r\n|\n|\\n", visual_secondary(secondary))
    left_count = (len(lines) + 1) // 2
    if left_count != len(right) or any(
        bool(a.strip()) != bool(b.strip()) for a, b in zip(lines[::2], right)
    ):
        # There is no semantic line alignment in the localisation keys.
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


class MenuTranslator:
    def __init__(
        self, entries, primary, secondary, source_language=DEFAULT_PRIMARY, _details_only=False
    ):
        entries = list(entries)
        if not _details_only:
            entries += overdrive_descriptions(entries)
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
            ]
            self.detail_sources = {
                e["texts"][source_language]
                for e in detail_entries
                if e.get("key", "").endswith("/description") and source_language in e["texts"]
            }
            if detail_entries:
                self.details = MenuTranslator(
                    detail_entries, primary, secondary, source_language, True
                )
        self.keyed = []
        candidates = {}
        display_candidates = {}
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
        for source, pairs in display_candidates.items():
            if len(pairs) == 1 and candidates[source] - {None} == pairs:
                candidates[source] = pairs
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
        for source, pair, is_raw in [(s, p, False) for s, p in normalized.items()] + [
            (s, p, True) for s, p in self.pairs.items() if "<" in s
        ]:
            matches = list(FORMAT.finditer(source))
            if (
                not matches
                or len(matches) > 4
                or any("%" in FORMAT.sub("", t) for t in (source, *pair))
            ):
                continue
            # Number arguments retain order unless explicit positional slots are
            # available; reject mismatched placeholder contracts.
            if any(len(FORMAT.findall(t)) != len(matches) for t in pair):
                continue
            if any("$" in m.group() for t in (source, *pair) for m in FORMAT.finditer(t)):
                continue
            kinds = [m.group()[-1] for m in matches]
            if any([m.group()[-1] for m in FORMAT.finditer(t)] != kinds for t in pair):
                continue
            if "s" in kinds and len(FORMAT.sub("", source).strip()) < 2:
                continue
            chunks = []
            at = 0
            for m in matches:
                chunks.extend(
                    (
                        re.escape(source[at : m.start()]),
                        r"([^<>\r\n]{1,512}?)" if m.group()[-1] == "s" else r"([+-]?\d+)",
                    )
                )
                at = m.end()
            chunks.append(re.escape(source[at:]))
            (self.raw_numeric if is_raw else self.numeric).append(
                (re.compile("".join(chunks)), pair)
            )

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
                rendered.append(FORMAT.sub(lambda _: next(values), target))
            matches.add(tuple(rendered))
        return next(iter(matches)) if len(matches) == 1 else None

    def pair(self, source):
        if source in self.plain_pairs:
            return self.plain_pairs[source]
        matches = set()
        for pattern, pair in self.numeric:
            m = pattern.fullmatch(source)
            if m:
                rendered = []
                for side, target in enumerate(pair):
                    # Name arguments are translated only by an exact known pair;
                    # unknown player-defined values are preserved verbatim.
                    values = iter(self.plain_pairs.get(v, (v, v))[side] for v in m.groups())
                    rendered.append(FORMAT.sub(lambda _: next(values), target))
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
        pair = self.raw_pair(source)
        if pair and mode in ("primary", "secondary"):
            return pair[0 if mode == "primary" else 1]
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
        if mode == "annotation" and not needs_annotation(a, b):
            return {"text": a, "layers": [], "kind": "plain"}
        known = self.raw_pair(source) is not None
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
            "same_language": self.same_language,
            "keyed": keyed,
            "detail_sources": sorted(self.detail_sources),
            "details": self.details.runtime_model() if self.details else None,
            "scoped": {k: v.runtime_model() for k, v in self.scoped.items()},
        }
