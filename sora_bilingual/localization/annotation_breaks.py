"""Unicode boundaries for repartitioning annotation payloads.

This guards existing paragraph segments, not native automatic line wrapping.
It applies Unicode punctuation, combining/glue, word and Hangul constraints
conservatively; native font measurement still owns actual visual wrapping.
"""

from bisect import bisect_right
import json
from pathlib import Path
import re

_RANGES = json.loads(Path(__file__).with_name("annotation_break_data.json").read_text("utf-8"))[
    "ranges"
]
_STARTS = [row[0] for row in _RANGES]
_NO_START = frozenset(("CL", "CP", "EX", "IN", "IS", "SY", "NS", "CM", "ZWJ", "WJ", "GL", "QU"))
_NO_END = frozenset(("OP", "WJ", "GL", "QU"))
_WORDS = frozenset(("AL", "HL", "NU"))


def break_class(character):
    row = _RANGES[bisect_right(_STARTS, ord(character)) - 1]
    value = row[2]
    return "AL" if value in ("AI", "SG", "XX", "SA") else "NS" if value == "CJ" else value


def annotation_break_allowed(left, right):
    left = re.sub("<[^<>]*>", "", left)
    right = re.sub("<[^<>]*>", "", right)
    space = False
    while left and left[-1].isspace() and break_class(left[-1]) in ("SP", "BA"):
        left, space = left[:-1], True
    while right and right[0].isspace() and break_class(right[0]) in ("SP", "BA"):
        right, space = right[1:], True
    if not left or not right:
        return True
    a, b = break_class(left[-1]), break_class(right[0])
    if b in _NO_START or a in _NO_END:
        return False
    # Whitespace provides a word boundary, while punctuation/glue above still
    # cannot be stranded across an independent annotation control.
    if a in _WORDS and b in _WORDS:
        return space
    if a == "JL" and b in ("JL", "JV", "H2", "H3"):
        return False
    if a in ("JV", "H2") and b in ("JV", "JT") or a in ("JT", "H3") and b == "JT":
        return False
    return not (a == "EB" and b == "EM" or a == b == "RI")
