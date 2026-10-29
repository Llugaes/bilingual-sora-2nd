"""Keep NPC dialogue attached to its executable dispatch case, not its ordinal.

The accepted switch reads one argument into register zero and compares it to
unique integer selectors. Every case has a closed region and a common exit.
Nested call operands, indirect entries and fallthrough cases are refused.
"""


def dispatch_regions(function):
    code = function.code_shape
    # Most functions are not NPC dispatchers. Avoid copying their full program.
    prefix = (op for op in code if op[0] != "line")
    if next(prefix, None) != ("slot", 2, 1) or next(prefix, None) != ("byte", 10, 0):
        return None
    positions = [i for i, op in enumerate(code) if op[0] != "line"]
    if len(positions) < 8:
        return None
    ops = [code[i] for i in positions]
    at, selectors = 2, {}
    while at + 3 < len(ops):
        a, b, c, d = ops[at : at + 4]
        if (
            a != ("byte", 9, 0)
            or b[:2] != ("push", "int")
            or c != ("op", 21)
            or d[:2] != ("branch", 14)
        ):
            break
        if b[2] in selectors:
            return None
        selectors[b[2]] = d[2]
        at += 4
    if len(selectors) < 2 or at >= len(ops) or ops[at][:2] != ("branch", 11):
        return None
    end = ops[at][2]
    starts = sorted(selectors.values())
    if (
        len(set(starts)) != len(starts)
        or starts[0] != positions[at] + 1
        or not starts[-1] < end < len(code)
    ):
        return None
    if any(any(kind in ("call", "expr") for kind, _ in call.args) for call in function.called):
        return None
    # This family has no nested metadata: physical calls must match every
    # called record in order before assigning a record to any branch.
    calls = [
        (i, op)
        for i, op in enumerate(code)
        if op[0] in ("local-call", "external-call", "system-call")
    ]
    if len(calls) != len(function.called):
        return None
    for (_, op), call in zip(calls, function.called, strict=True):
        if op[0] == "local-call":
            if call.kind != 0 or call.target != op[1]:
                return None
        elif op[0] == "system-call":
            if call.kind != 3 or call.args[:2] != (("int", op[1]), ("int", op[2])):
                return None
        else:
            return None
    result = {}
    branches = [(i, op[-1]) for i, op in enumerate(code) if op[0] == "branch"]
    for selector, begin in selectors.items():
        limit = min((p for p in starts if p > begin), default=end)
        body = [op for op in code[begin:limit] if op[0] != "line"]
        if not body or body[-1] != ("branch", 11, end):
            return None
        for i, target in branches:
            if begin <= i < limit and target != end and not begin <= target < limit:
                return None
            if not begin <= i < limit and begin < target < limit:
                return None
        result[selector] = tuple(n for n, (i, _) in enumerate(calls) if begin <= i < limit)
    return result


def dispatch_signature(function):
    regions = function.branch_regions
    if regions is None:
        return None
    return tuple(sorted(regions.items()))


def aligned_dispatch_calls(reference, candidate):
    """None means outside this contract; an empty map is a proved mismatch."""
    from types import SimpleNamespace
    from sora_bilingual.localization.resources import _sequential_call_map

    left, right = reference.branch_regions, candidate.branch_regions
    if left is None and right is None:
        return None
    if left is None or right is None:
        return {}
    mapped = {}
    for selector, a in left.items():
        b = right.get(selector)
        if b is None:
            continue
        x = SimpleNamespace(
            flags=reference.flags,
            arg_types=reference.arg_types,
            called=tuple(reference.called[i] for i in a),
        )
        y = SimpleNamespace(
            flags=candidate.flags,
            arg_types=candidate.arg_types,
            called=tuple(candidate.called[i] for i in b),
        )
        mapped.update((a[i], b[j]) for i, j in _sequential_call_map(x, y).items())
    return mapped
