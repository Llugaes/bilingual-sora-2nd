"""Prove a complete finite item-count panel from its executable stack producers.

The seven sepith IDs are the actual resource domain. Each numeric operand must
come from the matching one-argument item-count helper, whose complete bytecode
forwards group 16 / command 2. No arbitrary call result is treated as a number.
"""

ITEM_IDS = tuple(range(310, 317))
HELPER_CODE = (
    ("slot", 2, 1),
    ("system-call", 16, 2, 1),
    ("pop", 1),
    ("byte", 9, 0),
    ("byte", 10, 0),
    ("pop", 1),
    ("return",),
)


def panel_parts(call):
    if (
        call.kind != 3
        or not 40 <= len(call.args) <= 80
        or call.args[:4] != (("int", 5), ("int", 8), ("int", 65535), ("int", 16))
        or call.args[4][0] != "string"
        or call.args[5] != ("int", 10)
    ):
        return None
    parts, slots, controls = [call.args[4][1], "\n"], [], []
    at = 6
    while at < len(call.args):
        kind, value = call.args[at]
        if kind == "string":
            parts.append(value)
        elif (kind, value) == ("int", 10):
            parts.append("\n")
            controls.append((10,))
        elif (kind, value) == ("int", 17) and at + 1 < len(call.args):
            if call.args[at + 1][0] != "int":
                return None
            ident = call.args[at + 1][1]
            parts.append(("item", ident))
            controls.append((17, ident))
            at += 1
        elif (kind, value) == ("int", 18) and at + 1 < len(call.args):
            if call.args[at + 1] != ("call", None) or len(slots) >= len(ITEM_IDS):
                return None
            parts.append(("count", ITEM_IDS[len(slots)]))
            slots.append(at + 1)
            controls.append((18,))
            at += 1
        else:
            return None
        at += 1
    expected = [op for ident in ITEM_IDS for op in ((17, ident), (18,), (10,))][:-1]
    if controls != expected:
        return None
    return tuple(parts), tuple(slots)


def panel_contract(script, function_name, called):
    from sora_bilingual.localization.control_dialogue import _program

    function = script.functions[function_name]
    if not 0 <= called < len(function.called):
        return None
    call = function.called[called]
    decoded = panel_parts(call)
    if decoded is None:
        return None
    parts, slots = decoded
    helpers = {}
    for ordinal, (slot, ident) in enumerate(zip(slots, ITEM_IDS, strict=True), called + 1):
        if ordinal >= len(function.called):
            return None
        child = function.called[ordinal]
        helper = script.functions.get(child.target)
        if (
            child.kind != 0
            or child.args != (("int", ident),)
            or helper is None
            or helper.arg_types != (1,)
            or helper.code_shape != HELPER_CODE
        ):
            return None
        helpers[slot] = child.target
    code = _program(function)
    if code is None:
        return None
    meaningful = [i for i, op in enumerate(code) if op[0] != "line"]
    sites = []
    for ordinal, pc in enumerate(meaningful):
        if code[pc] != ("system-call", 5, 8, len(call.args) - 2):
            continue
        cursor = ordinal - 1
        for slot, arg in enumerate(call.args[2:], 2):
            if cursor < 0:
                break
            if slot not in helpers:
                if code[meaningful[cursor]] != ("push", *arg):
                    break
                cursor -= 1
                continue
            expected = [
                ("byte", 9, 0),
                ("local-call", helpers[slot]),
                ("push", "int", ITEM_IDS[slots.index(slot)]),
            ]
            if cursor < 3 or any(
                code[meaningful[cursor - i]] != op for i, op in enumerate(expected)
            ):
                break
            prepare = code[meaningful[cursor - 3]]
            if prepare != ("prepare-local", meaningful[cursor]):
                break
            cursor -= 4
        else:
            start = meaningful[cursor + 1]
            if (
                ordinal + 1 < len(meaningful)
                and code[meaningful[ordinal + 1]] == ("pop", len(call.args) - 2)
                and not any(op[0] == "branch" and start < op[-1] <= pc for op in code)
            ):
                sites.append(pc)
    if len(sites) != 1:
        return None
    return {"parts": parts, "slots": slots, "code_index": sites[0]}
