"""Bounded proof for a nested character action's retained VM return value.

Group 1 / command 47 preserves register 0. The talk builder ignores special
zero and its command callback emits nothing for integer 0/1. These values
must come from a proved reaching helper return; unknown calls never become
empty strings. The source executable contract is checked independently.
"""

from dataclasses import replace

_NON_DISPLAY = frozenset((0, 0x40000000, 0x40000001))
_FLAG = (
    ("slot", 2, 1),
    ("system-call", 0, 0, 1),
    ("pop", 1),
    ("byte", 9, 0),
    ("byte", 10, 0),
    ("pop", 1),
    ("return",),
)


def helper_return_values(functions):
    """Read exact helper epilogues, including helpers with no called metadata."""
    result = {}
    for name, function in functions.items():
        code = function.code_shape
        if code == _FLAG and len(function.arg_types) == 1:
            result[name] = (0x40000000, 0x40000001)
            continue
        exits = [i for i, op in enumerate(code) if op == ("return",)]
        if not exits:
            continue
        valid = True
        for end in exits:
            at = end - 1
            while at >= 0 and code[at][0] in ("pop", "line"):
                at -= 1
            if at < 1 or code[at] != ("byte", 10, 0) or code[at - 1] != ("push", "special", 0):
                valid = False
                break
            if any(op[0] == "branch" and at - 1 < op[-1] <= end for op in code):
                valid = False
                break
        if valid:
            result[name] = (0,)
    return result


def _reaching_return_values(function, code, stop):
    predecessors = [[] for _ in range(len(code) + 1)]
    for at, op in enumerate(code):
        successors = [] if op[0] == "return" else [at + 1]
        if op[0] == "branch":
            successors = [op[-1]] + ([] if op[1] == 11 else successors)
        for successor in successors:
            if not 0 <= successor <= len(code):
                return None
            predecessors[successor].append(at)
    helpers = dict(function.local_return_values)
    pending, seen, values = list(predecessors[stop]), set(), set()
    while pending:
        at = pending.pop()
        if at in seen:
            continue
        seen.add(at)
        if len(seen) > 2048:
            return None
        op = code[at]
        if op[0] == "branch" and op[1] not in (11, 14, 15):
            return None
        if op[0] == "local-call":
            domain = helpers.get(op[1])
            if not domain or not set(domain) <= _NON_DISPLAY:
                return None
            values.update(domain)
            continue
        if op == ("byte", 10, 0):
            if at < 1 or code[at - 1] != ("push", "special", 0):
                return None
            if predecessors[at] != [at - 1]:
                return None
            values.add(0)
            continue
        if op[0] in ("external-call", "system-call", "return"):
            return None
        if op[0] == "byte" and (op[1] not in (9, 10) or not 0 <= op[2] < 16):
            return None
        if op[0] not in (
            "push",
            "pop",
            "slot",
            "byte",
            "global",
            "op",
            "line",
            "branch",
            "prepare-local",
        ):
            return None
        if not predecessors[at]:
            return None
        # An unbounded loop can carry an unobserved register value.
        if any(parent >= at for parent in predecessors[at]):
            return None
        pending.extend(predecessors[at])
    return sorted(values) if values else None


def nested_action_contract(function, called, code):
    """Match complete parent/child argument producers before proving the value."""
    from sora_bilingual.localization.resources import assembled_dialogue

    call = function.called[called]
    dynamic = [i for i, (kind, _) in enumerate(call.args[3:], 3) if kind in ("call", "var", "expr")]
    if (
        call.kind != 3
        or call.args[:2] != (("int", 5), ("int", 0))
        or len(dynamic) != 1
        or call.args[dynamic[0]][0] != "call"
        or called + 1 >= len(function.called)
    ):
        return None
    child = function.called[called + 1]
    if (
        child.kind != 3
        or child.args[:2] != (("int", 1), ("int", 47))
        or len(child.args) != 5
        or tuple(kind for kind, _ in child.args[2:]) != ("int", "int", "string")
    ):
        return None
    slot = dynamic[0]
    source = assembled_dialogue(
        replace(call, args=call.args[:slot] + (("string", ""),) + call.args[slot + 1 :])
    )
    if source is None or code is None:
        return None
    meaningful = [i for i, op in enumerate(code) if op[0] != "line"]
    sites = []
    for ordinal, pc in enumerate(meaningful):
        if code[pc] != ("system-call", 5, 0, len(call.args) - 2):
            continue
        cursor, nested = ordinal - 1, None
        for arg in call.args[2:]:
            if cursor < 0:
                break
            if arg[0] != "call":
                if code[meaningful[cursor]] != ("push", *arg):
                    break
                cursor -= 1
            else:
                expected = [("byte", 9, 0), ("pop", 3), ("system-call", 1, 47, 3)]
                expected.extend(("push", *value) for value in child.args[2:])
                if cursor + 1 < len(expected) or any(
                    code[meaningful[cursor - i]] != op for i, op in enumerate(expected)
                ):
                    break
                nested = meaningful[cursor - 2]
                cursor -= len(expected)
        else:
            start = meaningful[cursor + 1]
            if (
                nested is not None
                and ordinal + 1 < len(meaningful)
                and code[meaningful[ordinal + 1]] == ("pop", len(call.args) - 2)
                and not any(op[0] == "branch" and start < op[-1] <= pc for op in code)
            ):
                values = _reaching_return_values(function, code, nested)
                if values is not None:
                    sites.append((pc, values))
    if len(sites) != 1:
        return None
    pc, values = sites[0]
    return {
        "code_index": pc,
        "control_slot": slot,
        "producer_identity": "nested_action_retained_finite_return",
        "definitions": {"": []},
        "raw_values": {"": values},
        "variants": {"": source},
    }
