"""Prove finite popup-control variables from a bounded SCP stack region.

The common builder appends string arguments, including K controls. A variable
is never erased: only a local whose every reaching definition is a literal K
control becomes a finite complete-output variant. Calls, expressions, visible
replacement strings, unknown writes and branches entering the region reject.
"""

from dataclasses import replace
import re

from sora_bilingual.localization.resources import assembled_dialogue

_UNKNOWN = ("unknown", None)
_K_CONTROL = re.compile(r"(?:<K[0-9]*>)?")


def _program(function):
    strings = iter(function.code_strings)
    code = [(*op, next(strings)) if op == ("push", "string") else op for op in function.code_shape]
    if sum(op[0] in ("local-call", "external-call", "system-call") for op in code) != len(
        function.called
    ):
        return None
    return code


def _local_values(function, code, stop, call_end, rejection):
    def reject(reason, pc=None):
        rejection.update(reason=reason, **({"code_index": pc} if pc is not None else {}))
        return None

    starts = [i for i in range(max(0, stop - 2048), stop) if code[i] == ("push", "special", 0)]
    if not starts:
        return reject("control_definition_outside_bounded_region")
    start = starts[-1]
    helper_types = dict(function.local_arg_types)
    if any(
        op[0] == "branch" and start < op[-1] <= call_end
        for i, op in enumerate(code)
        if not start <= i < stop
    ):
        return reject("external_entry_into_control_region")
    # Prove only paths that can reach this exact argument producer. A prior
    # popup's branch can leave the region without reading this local; its
    # unrelated helper arguments are not evidence about this dialogue. Do
    # not relax unknown operations on paths that actually reach the read.
    predecessors = {}
    for pc in range(start + 1, stop):
        op = code[pc]
        successors = () if op[0] == "return" else (pc + 1,)
        if op[0] == "branch":
            successors = (op[-1],) if op[1] == 11 else (pc + 1, op[-1])
        for target in successors:
            if start < target <= stop:
                predecessors.setdefault(target, []).append(pc)
    reaches, todo = {stop}, [stop]
    while todo:
        for pc in predecessors.get(todo.pop(), ()):
            if pc not in reaches:
                reaches.add(pc)
                todo.append(pc)
    pending, seen, values = [(start + 1, (_UNKNOWN,))], set(), {}
    while pending:
        pc, stack = pending.pop()
        if pc not in reaches:
            continue
        if (pc, stack) in seen:
            continue
        seen.add((pc, stack))
        if len(seen) > 4096 or len(stack) > 32 or not start < pc <= stop:
            return reject("control_proof_budget_or_stack_bound", pc)
        if pc == stop:
            if len(stack) != 1 or stack[0][0] != "string" or not _K_CONTROL.fullmatch(stack[0][1]):
                return reject("nonliteral_or_visible_dynamic_value", pc)
            values.setdefault(stack[0][1], set()).add(stack[0][2])
            continue
        op, next_pc = code[pc], pc + 1
        stack = list(stack)
        if op[0] == "line":
            pass
        elif op[0] == "push" and op[1] in ("int", "string", "special"):
            stack.append((*op[1:], pc) if op[1] == "string" else tuple(op[1:]))
        elif op[:2] == ("slot", 5):
            if len(stack) < 2:
                return reject("invalid_local_write_stack", pc)
            value = stack.pop()
            target = len(stack) - op[2]
            if target != 0:
                return reject("write_to_unowned_local", pc)
            stack[target] = value
        elif op[:2] == ("slot", 2):
            # Values are copied, never caller-local addresses. The same read
            # appears in preceding dialogue argument producers in this region.
            if not 1 <= op[2] <= len(stack):
                return reject("invalid_local_read_stack", pc)
            stack.append(stack[-op[2]])
        elif op[0] == "system-call":
            # The native handler consumes copied arguments; SCP's following
            # pop owns their stack cleanup. No address-producing slot is
            # admitted by this proof, so a handler cannot mutate this local.
            if len(stack) <= op[3]:
                return reject("system_call_argument_stack_not_proven", pc)
        elif op[0] == "pop":
            if not 0 < op[1] < len(stack):
                return reject("stack_cleanup_removes_control_local", pc)
            del stack[-op[1] :]
        elif op[0] == "prepare-local":
            # SCP prepares return frame, pushes declared arguments in reverse,
            # then the callee removes its own frame. Accept only literal outer
            # arguments; no local address or value is forwarded to the helper.
            end = pc + 1
            while end < stop and code[end][0] == "push":
                end += 1
            arguments = tuple(tuple(item[1:]) for item in reversed(code[pc + 1 : end]))
            if (
                end >= stop
                or code[end][0] != "local-call"
                or op[-1] != end + 1
                or not any(
                    call.kind == 0
                    and call.target == code[end][1]
                    and (
                        call.args == arguments
                        or (
                            (declared := helper_types.get(call.target)) is not None
                            and len(arguments) == len(declared)
                            and len(call.args) < len(arguments)
                            and arguments[: len(call.args)] == call.args
                            and all(kind & 8 for kind in declared[len(call.args) :])
                        )
                    )
                    for call in function.called
                )
            ):
                return reject("helper_literal_arguments_not_proven", pc)
            next_pc = end + 1
        elif op == ("byte", 9, 0):
            stack.append(_UNKNOWN)
        elif op == ("op", 32):
            if len(stack) < 2:
                return reject("unary_condition_stack_not_proven", pc)
            stack[-1] = _UNKNOWN
        elif op == ("op", 29):
            # Two flag results feed the VM's binary condition; retain both
            # branch outcomes rather than guessing either game's flag value.
            if len(stack) < 3:
                return reject("binary_condition_stack_not_proven", pc)
            stack[-2:] = [_UNKNOWN]
        elif op[0] == "branch" and op[1] in (11, 14, 15):
            if op[-1] <= pc:
                return reject("backward_control_path_not_proven", pc)
            if op[1] != 11:
                if len(stack) < 2:
                    return reject("branch_condition_stack_not_proven", pc)
                stack.pop()
                pending.append((next_pc, tuple(stack)))
            if op[-1] > stop:
                # This path does not reach the read. The external-entry check
                # above rejects any later edge re-entering the proof region.
                continue
            next_pc = op[-1]
        else:
            return reject("unsupported_reaching_operation", pc)
        pending.append((next_pc, tuple(stack)))
    return (
        {value: sorted(indices) for value, indices in sorted(values.items())}
        if values
        else reject("no_reaching_control_definition")
    )


def _ordered_dialogue_producers(function, code):
    """Exact leaf producer sequence, independent of nested non-display calls.

    Every talk producer's command, arity, literals, actor and value-copy reads
    must agree with metadata, in complete order, with native argument cleanup.
    This distinguishes duplicate descriptors by PC, not by their short text.
    A nested/expressive talk argument or any disagreeing producer rejects.
    """
    records = [
        (i, call)
        for i, call in enumerate(function.called)
        if call.kind == 3
        and call.args[:1] == (("int", 5),)
        and call.args[1] in (("int", 0), ("int", 6), ("int", 19))
    ]
    sites = [i for i, op in enumerate(code) if op[:2] == ("system-call", 5) and op[2] in (0, 6, 19)]
    if len(records) != len(sites):
        return {}
    positions = [i for i, op in enumerate(code) if op[0] != "line"]
    ordinal = {pc: i for i, pc in enumerate(positions)}
    result = {}
    for (called, call), pc in zip(records, sites):
        args = tuple(reversed(call.args[2:]))
        at = ordinal[pc]
        producers = positions[max(0, at - len(args)) : at]
        if (
            code[pc] != ("system-call", 5, call.args[1][1], len(args))
            or len(producers) != len(args)
            or any(
                code[p] != ("push", *arg)
                if arg[0] in ("int", "string")
                else arg[0] != "var" or code[p][:2] != ("slot", 2)
                for p, arg in zip(producers, args)
            )
            or at + 1 >= len(positions)
            or code[positions[at + 1]] != ("pop", len(args))
        ):
            return {}
        result[called] = pc
    return result


def control_dialogue_contract(function, called, program=None, *, rejection=None):
    rejection = {} if rejection is None else rejection

    def reject(reason):
        rejection["reason"] = reason
        return None

    call = function.called[called]
    dynamic = [i for i, (kind, _) in enumerate(call.args[3:], 3) if kind in ("var", "call", "expr")]
    if (
        call.kind != 3
        or len(call.args) < 4
        or call.args[:1] != (("int", 5),)
        or call.args[1] not in (("int", 0), ("int", 6), ("int", 19))
        or call.args[2][0] != "int"
        or len(dynamic) != 1
        or call.args[dynamic[0]][0] != "var"
    ):
        return reject("unsupported_dynamic_builder_layout")
    slot = dynamic[0]
    if (
        assembled_dialogue(
            replace(call, args=call.args[:slot] + (("string", ""),) + call.args[slot + 1 :])
        )
        is None
    ):
        return reject("unsupported_surrounding_builder_grammar")
    # A nested call's metadata precedes its child, whereas executable calls
    # run child first. Locate a unique complete argument producer instead of
    # treating those independent ordinals as a proven PC map.
    duplicate = sum(candidate == call for candidate in function.called) != 1
    code = program if program is not None else _program(function)
    if code is None:
        return reject("executable_call_count_mismatch")
    ordered = _ordered_dialogue_producers(function, code) if duplicate else {}
    if duplicate and called not in ordered:
        return reject("duplicate_call_without_ordered_producer_proof")
    candidates = []
    args = tuple(reversed(call.args[2:]))
    for call_end, op in enumerate(code):
        if op != ("system-call", 5, call.args[1][1], len(args)):
            continue
        positions = [i for i in range(call_end) if code[i][0] != "line"][-len(args) :]
        if len(positions) == len(args) and all(
            code[position]
            == (("slot", 2, index + 1) if argument[0] == "var" else ("push", *argument))
            for index, (position, argument) in enumerate(zip(positions, args))
        ):
            candidates.append((call_end, positions[0]))
    if duplicate:
        candidates = [candidate for candidate in candidates if candidate[0] == ordered[called]]
    if len(candidates) != 1:
        return reject("argument_producer_missing_or_ambiguous")
    call_end, stop = candidates[0]
    values = _local_values(function, code, stop, call_end, rejection)
    if values is None:
        return None
    return {
        "code_index": call_end,
        "control_slot": slot,
        "definitions": values,
        "producer_identity": "complete_ordered_dialogue_producers"
        if duplicate
        else "unique_complete_producer",
        "variants": {
            value: assembled_dialogue(
                replace(call, args=call.args[:slot] + (("string", value),) + call.args[slot + 1 :])
            )
            for value in values
        },
    }


def control_dialogue_variants(function, called, program=None):
    contract = control_dialogue_contract(function, called, program)
    return contract["variants"] if contract is not None else None


def control_dialogue_calls(function, rejections=None):
    candidates = [
        i
        for i, call in enumerate(function.called)
        if call.kind == 3
        and call.args[:1] == (("int", 5),)
        and any(kind == "var" for kind, _ in call.args[3:])
    ]
    if not candidates:
        return {}
    program = _program(function)
    rejections = {} if rejections is None else rejections
    return {
        i: control_dialogue_contract(function, i, program, rejection=rejections.setdefault(i, {}))
        for i in candidates
    }


def align_control_dialogue_calls(path, name, functions, audit):
    import hashlib
    from sora_bilingual.localization.resources import (
        _aligned_call_map,
        _dynamic_dialogue_layout,
        _speaker_ids,
    )

    rejected = {language: {} for language in functions}
    decoded = {
        language: control_dialogue_calls(function, rejected[language])
        for language, function in functions.items()
    }
    for language, contracts in decoded.items():
        for called, contract in contracts.items():
            audit.setdefault("diagnostics", []).append(
                {
                    "path": path,
                    "function": name,
                    "called": called,
                    "language": language,
                    "reason": "finite_control_dialogue"
                    if contract
                    else "unproven_control_dialogue",
                    "status": "proven" if contract else "rejected",
                    **({"rejection": rejected[language][called]} if not contract else {}),
                    **(
                        {
                            "code_index": contract["code_index"],
                            "control_slot": contract["control_slot"],
                            "values": list(contract["variants"]),
                        }
                        if contract
                        else {}
                    ),
                }
            )
    # Only proved finite values become static alignment shadows. Original
    # functions/operands/IDs remain the source for every emitted record.
    shadows = {
        l: replace(
            f,
            called=tuple(
                replace(
                    call,
                    args=call.args[: c["control_slot"]]
                    + (("string", min(c["variants"])),)
                    + call.args[c["control_slot"] + 1 :],
                )
                if (c := decoded[l].get(i))
                else call
                for i, call in enumerate(f.called)
            ),
        )
        for l, f in functions.items()
    }
    reference_language = min(functions)
    reference = functions[reference_language]
    mappings = {l: _aligned_call_map(shadows[reference_language], shadows[l]) for l in functions}
    entries = []
    for called, reference_contract in decoded[reference_language].items():
        if reference_contract is None:
            continue
        peers = {
            l: mapped
            for l in sorted(functions)
            if (mapped := mappings[l].get(called)) is not None
            and decoded[l].get(mapped) is not None
            and shadows[l].called[mapped].dialogue_shape()
            == shadows[reference_language].called[called].dialogue_shape()
            and _dynamic_dialogue_layout(functions[l].called[mapped])
            == _dynamic_dialogue_layout(reference.called[called])
        }
        for value in reference_contract["variants"]:
            ids = {l: i for l, i in peers.items() if value in decoded[l][i]["variants"]}
            if len(ids) < 2:
                continue
            variant = hashlib.sha256(value.encode()).hexdigest()[:16]
            entries.append(
                {
                    "key": f"{path}/{name}/called/{called}/control_variant:{variant}/assembled_dialogue",
                    "texts": {l: decoded[l][i]["variants"][value] for l, i in ids.items()},
                    "display_role": "dialogue",
                    "called_ids": ids,
                    "speaker_ids": _speaker_ids(functions, ids),
                    "control_dialogue": {
                        "value": value,
                        "slot": reference_contract["control_slot"],
                    },
                }
            )
        if len(peers) >= 2:
            # A display callback may have consumed the proved popup control.
            # This alias contains all remaining literal text; it is never
            # obtained by erasing an unproved variable or arbitrary K tag.
            texts = {}
            for l, i in peers.items():
                call, slot = functions[l].called[i], decoded[l][i]["control_slot"]
                text = assembled_dialogue(
                    replace(call, args=call.args[:slot] + (("string", ""),) + call.args[slot + 1 :])
                )
                texts[l] = re.sub(r"^(?:<#[^<>]*>)+", "", text)
            entries.append(
                {
                    "key": f"{path}/{name}/called/{called}/control_dialogue_display",
                    "texts": texts,
                    "display_role": "dialogue",
                    "called_ids": peers,
                    "speaker_ids": _speaker_ids(functions, peers),
                }
            )
    return entries
