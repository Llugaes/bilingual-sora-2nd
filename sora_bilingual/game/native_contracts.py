"""Resolve the resident native adapter's local PE contracts.

The resolver deliberately knows nothing about executable versions, hashes or
section layouts.  A reviewed contract supplies function bodies, the narrowly
approved operand masks, and only the globals that injected code dereferences.
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections import defaultdict


_IMAGE_DIRECTORY_ENTRY_IMPORT = 1
_IMAGE_DIRECTORY_ENTRY_EXCEPTION = 3
_IMAGE_SCN_MEM_EXECUTE = 0x20000000
_IMAGE_SCN_MEM_READ = 0x40000000
_IMAGE_SCN_MEM_WRITE = 0x80000000


def _error(message: str, *, details=None):
    # Keep the production exception authoritative and avoid an import cycle
    # while native_contract_data is generated or absent during isolated tests.
    from sora_bilingual.game.exe_compatibility import ExecutableCompatibilityError

    return ExecutableCompatibilityError(message, details=details)


def _as_contract(contract):
    if contract is None:
        from sora_bilingual.game.native_contract_data import CONTRACT

        contract = CONTRACT
    if not isinstance(contract, dict) or contract.get("schema") != 1:
        raise _error("原生合同格式不受支持")
    if not isinstance(contract.get("functions"), dict) or not contract["functions"]:
        raise _error("原生合同缺少函数定义")
    if not isinstance(contract.get("global_specs"), dict):
        raise _error("原生合同缺少全局对象定义")
    return contract


def _section_for_rva(pe, rva: int, size: int, *, executable: bool = False):
    if not isinstance(rva, int) or not isinstance(size, int) or rva < 0 or size < 0:
        raise _error("原生合同地址范围无效")
    end = rva + size
    for section in pe.sections:
        start = section.VirtualAddress
        virtual_size = section.Misc_VirtualSize or section.SizeOfRawData
        if rva < start or end > start + virtual_size:
            continue
        offset = rva - start
        raw_end = offset + size
        raw_start = section.PointerToRawData + offset
        if raw_start < 0:
            raise _error(f"原生合同地址 0x{rva:X} 未完整映射到文件字节")
        characteristics = section.Characteristics
        if not characteristics & _IMAGE_SCN_MEM_READ:
            raise _error(f"原生合同地址 0x{rva:X} 不在可读映像区间")
        if executable and not characteristics & _IMAGE_SCN_MEM_EXECUTE:
            raise _error(f"原生函数地址 0x{rva:X} 不在可执行映像区间")
        if raw_end <= section.SizeOfRawData and raw_start + size <= len(pe.__data__):
            return section, bytes(pe.__data__[raw_start : raw_start + size])
        if executable:
            raise _error(f"原生函数地址 0x{rva:X} 未完整映射到文件字节")
        # A virtual section can legitimately end in loader-supplied zeroed
        # BSS.  It is still a complete readable image interval for a global.
        available = max(0, min(size, section.SizeOfRawData - offset, len(pe.__data__) - raw_start))
        return section, bytes(pe.__data__[raw_start : raw_start + available]) + bytes(
            size - available
        )
    raise _error(f"原生合同地址 0x{rva:X} 不在映像区间")


def _read(pe, rva: int, size: int, *, executable: bool = False) -> bytes:
    return _section_for_rva(pe, rva, size, executable=executable)[1]


def _masked_hash(data: bytes, masks) -> str:
    normalized = bytearray(data)
    previous_end = 0
    for mask in masks:
        if not isinstance(mask, (list, tuple)) or len(mask) != 2:
            raise _error("原生合同掩码格式无效")
        offset, width = mask
        if not isinstance(offset, int) or not isinstance(width, int) or width <= 0:
            raise _error("原生合同掩码范围无效")
        end = offset + width
        if offset < previous_end or end > len(normalized):
            raise _error("原生合同掩码越界或重叠")
        normalized[offset:end] = bytes(width)
        previous_end = end
    return hashlib.sha256(normalized).hexdigest()


def _variant_matches(pe, start: int, variant: dict) -> bool:
    size = variant.get("size")
    expected = variant.get("sha256")
    masks = variant.get("masks", [])
    if not isinstance(size, int) or size <= 0 or not isinstance(expected, str):
        raise _error("原生合同函数变体格式无效")
    return _masked_hash(_read(pe, start, size, executable=True), masks) == expected


def _exception_entries(pe):
    directories = pe.OPTIONAL_HEADER.DATA_DIRECTORY
    if len(directories) <= _IMAGE_DIRECTORY_ENTRY_EXCEPTION:
        raise _error("游戏 EXE 缺少异常目录，无法定位原生函数")
    directory = directories[_IMAGE_DIRECTORY_ENTRY_EXCEPTION]
    if not directory.VirtualAddress or not directory.Size or directory.Size % 12:
        raise _error("游戏 EXE 异常目录无效，无法定位原生函数")
    raw = _read(pe, directory.VirtualAddress, directory.Size)
    entries = []
    for offset in range(0, len(raw), 12):
        start, end, unwind = struct.unpack_from("<III", raw, offset)
        if not start or end <= start:
            continue
        try:
            _read(pe, start, end - start, executable=True)
        except ValueError:
            # Exception metadata describes every native function.  A damaged
            # entry unrelated to this adapter is not a dependency contract.
            continue
        entries.append((start, end, unwind))
    return entries


def _exception_spans(pe):
    return [(start, end) for start, end, _ in _exception_entries(pe)]


def _chain_root(pe, entry):
    start, _end, unwind = entry
    header = _read(pe, unwind, 4)
    flags = header[0] >> 3
    if not flags & 4:  # UNW_FLAG_CHAININFO
        return start
    codes = header[2]
    chain_offset = unwind + 4 + codes * 2
    chain_offset = (chain_offset + 3) & ~3
    root, _root_end, _root_unwind = struct.unpack("<III", _read(pe, chain_offset, 12))
    if not root:
        raise _error("原生函数 CHAININFO 缺少根函数")
    return root


def _ultimate_chain_root(pe, entry, entries):
    by_start = {
        start: candidate
        for start, _end, _unwind in entries
        for candidate in [(start, _end, _unwind)]
    }
    current = entry
    seen = set()
    while True:
        start = current[0]
        if start in seen:
            raise _error("原生函数 CHAININFO 循环")
        seen.add(start)
        root = _chain_root(pe, current)
        if root == start:
            return root
        current = by_start.get(root)
        if current is None:
            raise _error("原生函数 CHAININFO 根函数不在异常目录")


def _chain_index(pe, entries):
    """Resolve CHAININFO roots once; unrelated malformed entries stay irrelevant."""
    by_start = {start: (start, end, unwind) for start, end, unwind in entries}
    roots = {}

    def resolve(start, active=()):
        if start in roots:
            return roots[start]
        if start in active:
            return None
        entry = by_start[start]
        try:
            immediate = _chain_root(pe, entry)
        except ValueError:
            roots[start] = None
            return None
        if immediate == start:
            roots[start] = start
            return start
        if immediate not in by_start:
            roots[start] = None
            return None
        roots[start] = resolve(immediate, active + (start,))
        return roots[start]

    groups = defaultdict(list)
    for start, entry in by_start.items():
        root = resolve(start)
        if root is not None:
            groups[root].append(entry)
    return roots, groups


def _reference_target(pe, start: int, link: dict) -> int:
    displacement = link.get("displacement")
    if not isinstance(displacement, (list, tuple)) or len(displacement) != 2:
        raise _error("原生合同链接位移格式无效")
    offset, width = displacement
    encoding = link.get("encoding", "relative")
    next_offset = link.get("next")
    if width not in (1, 2, 4) or not isinstance(offset, int):
        raise _error("原生合同链接位移范围无效")
    raw = _read(pe, start + offset, width, executable=True)
    if encoding == "rva32":
        if width != 4:
            raise _error("原生合同 rva32 链接必须是 4 字节")
        return int.from_bytes(raw, "little", signed=False)
    if encoding != "relative" or not isinstance(next_offset, int):
        raise _error("原生合同链接编码无效")
    value = int.from_bytes(raw, "little", signed=True)
    return start + next_offset + value


def _candidate_links_match(pe, candidate, candidates) -> bool:
    start, variant = candidate
    for link in variant.get("links", []):
        target_name = link.get("function")
        addend = link.get("addend", 0)
        if not isinstance(target_name, str) or not isinstance(addend, int):
            raise _error("原生合同函数链接格式无效")
        target = _reference_target(pe, start, link)
        if not any(target == other_start + addend for other_start, _ in candidates[target_name]):
            return False
    return True


def _template_links_match(pe, start: int, template: dict, candidates) -> bool:
    for link in template.get("links", []):
        target_name = link.get("function")
        addend = link.get("addend", 0)
        if not isinstance(target_name, str) or not isinstance(addend, int):
            raise _error("原生合同嵌套链接格式无效")
        target = _reference_target(pe, start, link)
        if not any(target == other_start + addend for other_start, _ in candidates[target_name]):
            return False
    return True


def _equal_target(pe, start: int, template: dict, side: dict) -> int:
    """Read one side of an audited address pair.

    A side normally lives in the template itself.  ``continuation`` names one
    of the template's own, already verified continuations instead, so a helper
    can be required to use the very table its reviewed callee reads.
    """
    name = side.get("continuation")
    if name is None:
        return _reference_target(pe, start, side)
    refs = [
        ref
        for ref in template.get("continuations", [])
        if isinstance(ref, dict) and ref.get("name") == name
    ]
    if len(refs) != 1:
        raise _error("原生合同等价目标引用的 continuation 不唯一")
    return _reference_target(pe, _reference_target(pe, start, refs[0]), side)


def _equal_target_rows(template: dict):
    for row in template.get("equal_targets", []):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("left"), dict)
            or not isinstance(row.get("right"), dict)
        ):
            raise _error("原生合同等价目标格式无效")
        yield row


def _equal_targets_match(pe, start: int, template: dict) -> bool:
    return all(
        _equal_target(pe, start, template, row["left"])
        == _equal_target(pe, start, template, row["right"])
        for row in _equal_target_rows(template)
    )


def _import_at(pe, slot: int):
    """Name the import bound to one IAT slot from the import directory itself."""
    directories = pe.OPTIONAL_HEADER.DATA_DIRECTORY
    if len(directories) <= _IMAGE_DIRECTORY_ENTRY_IMPORT:
        return None
    directory = directories[_IMAGE_DIRECTORY_ENTRY_IMPORT]
    if not directory.VirtualAddress:
        return None
    bindings = []
    terminated = False
    try:
        for offset in range(0, max(0, directory.Size - 19), 20):
            lookup, _stamp, _forwarder, library, thunks = struct.unpack(
                "<5I", _read(pe, directory.VirtualAddress + offset, 20)
            )
            if not (lookup or _stamp or _forwarder or library or thunks):
                terminated = True
                break
            index, remainder = divmod(slot - thunks, 8)
            if not thunks or index < 0 or remainder or index >= 0x10000:
                continue
            # The slot belongs to this DLL only inside its null-terminated
            # thunk list.  The lookup table still names it once the loader
            # has bound the address table.
            names = lookup or thunks
            entry = 0
            for position in range(index + 1):
                entry = struct.unpack("<Q", _read(pe, names + position * 8, 8))[0]
                if not entry:
                    break
            if not entry:
                continue
            if entry >> 32:
                return None  # Imported by ordinal: there is no name to review.
            _read(pe, slot, 8)
            bindings.append(
                (
                    _read_c_string(pe, library, label="导入库名").lower(),
                    _read_c_string(pe, entry + 2, label="导入符号名"),
                )
            )
    except ValueError:
        return None
    if not terminated or len(bindings) != 1:
        return None
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        parsed = [
            (descriptor.dll.lower(), imported.name)
            for descriptor in pe.DIRECTORY_ENTRY_IMPORT
            for imported in descriptor.imports
            if imported.address - _image_base(pe) == slot
        ]
        expected = tuple(value.encode("ascii") for value in bindings[0])
        if parsed != [expected]:
            return None
    return bindings[0]


def _import_rows(template: dict):
    for row in template.get("imports", []):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("dll"), str)
            or not isinstance(row.get("name", row.get("symbol")), str)
            or ("name" in row and "symbol" in row and row["name"] != row["symbol"])
        ):
            raise _error("原生合同导入引用格式无效")
        yield {**row, "name": row.get("name", row.get("symbol"))}


def _import_matches(pe, start: int, row: dict) -> bool:
    return _import_at(pe, _reference_target(pe, start, row)) == (row["dll"].lower(), row["name"])


def _imports_match(pe, start: int, template: dict) -> bool:
    return all(_import_matches(pe, start, row) for row in _import_rows(template))


def _data_rows(template: dict):
    for row in template.get("data_refs", []):
        if (
            not isinstance(row, dict)
            or type(row.get("size")) is not int
            or not 0 < row["size"] <= 65536
            or type(row.get("alignment", 1)) is not int
            or row.get("alignment", 1) <= 0
            or not isinstance(row.get("sha256"), str)
            or len(row["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in row["sha256"])
        ):
            raise _error("原生合同数据引用格式无效")
        yield {**row, "alignment": row.get("alignment", 1)}


def _data_matches(pe, start: int, row: dict) -> bool:
    target = _reference_target(pe, start, row)
    if target % row["alignment"]:
        return False
    try:
        section, _ = _section_for_rva(pe, target, row["size"])
        if section.Characteristics & _IMAGE_SCN_MEM_WRITE:
            return False
        data = _read(pe, target, row["size"])
    except ValueError:
        return False
    return hashlib.sha256(data).hexdigest() == row["sha256"]


def _indirect_dependency_failure(pe, start: int, template: dict):
    """Use the same data/import checks for leaf diagnostics and matching."""
    for index, row in enumerate(_data_rows(template)):
        if not _data_matches(pe, start, row):
            return (
                f"data_refs[{index}]",
                "Reviewed data bounds, permissions, alignment or digest differ",
            )
    for index, row in enumerate(_import_rows(template)):
        if not _import_matches(pe, start, row):
            return f"imports[{index}]", "Reviewed IAT binding differs"
    return None


def _nested_templates_match(
    pe, start: int, template: dict, candidates, entries, chain_index
) -> bool:
    if not _template_links_match(pe, start, template, candidates):
        return False
    if not _imports_match(pe, start, template):
        return False
    if not all(_data_matches(pe, start, row) for row in _data_rows(template)):
        return False
    for ref in template.get("continuations", []):
        if not isinstance(ref, dict) or not isinstance(ref.get("template"), dict):
            raise _error("原生合同 continuation 格式无效")
        target = _reference_target(pe, start, ref)
        if not _template_matches(pe, target, ref["template"], candidates, entries, chain_index):
            return False
    # After the continuations: a pair may read inside one of their bodies.
    if not _equal_targets_match(pe, start, template):
        return False
    return _chained_templates_match(pe, start, template, candidates, entries, chain_index)


def _template_matches(pe, start: int, template: dict, candidates, entries, chain_index) -> bool:
    if "points" in template:
        raise _error("原生合同嵌套模板不能定义 point")
    try:
        if not _variant_matches(pe, start, template):
            return False
    except ValueError:
        return False
    return _nested_templates_match(pe, start, template, candidates, entries, chain_index)


def _chained_fragments(pe, start: int, template: dict, entries, chain_index):
    """Return each reviewed chained fragment at its audited relative RVA."""
    templates = template.get("chained", [])
    if not templates:
        return []
    if not isinstance(templates, list) or any(not isinstance(row, dict) for row in templates):
        raise _error("原生合同 chained 模板格式无效")
    own = [
        entry for entry in entries if entry[0] == start and entry[1] - entry[0] == template["size"]
    ]
    if len(own) != 1:
        return None
    roots, groups = chain_index
    root = roots.get(start)
    fragments = {entry[0]: entry for entry in groups.get(root, []) if entry[0] != start}
    if len(fragments) != len(templates):
        return None
    result = []
    for chained in templates:
        offset = chained.get("offset")
        if not isinstance(offset, int) or offset == 0:
            raise _error("原生合同 chained 片段缺少相对偏移")
        entry = fragments.get(start + offset)
        if entry is None:
            return None
        result.append((entry, chained))
    return result


def _chained_templates_match(
    pe, start: int, template: dict, candidates, entries, chain_index
) -> bool:
    fragments = _chained_fragments(pe, start, template, entries, chain_index)
    if fragments is None:
        return False
    return all(
        _template_matches(pe, entry[0], chained, candidates, entries, chain_index)
        for entry, chained in fragments
    )


def _candidate_nested_contract_matches(pe, candidate, candidates, entries, chain_index) -> bool:
    start, variant = candidate
    return _nested_templates_match(pe, start, variant, candidates, entries, chain_index)


def _failure(function: str, path: str, reason: str) -> dict[str, str]:
    return {"function": function, "path": path, "reason": reason}


def _template_failure(
    pe, start: int, template: dict, candidates, entries, chain_index, function: str, path: str
):
    """Explain the first local checked dependency that makes a template unusable.

    Candidate propagation can empty innocent callers after their callee fails.
    This walks only the already-reviewed local template graph so compatibility
    reports retain the first body/continuation/chained evidence instead.
    """
    try:
        if not _variant_matches(pe, start, template):
            return _failure(function, path, "规范化函数体摘要不匹配")
    except ValueError:
        return _failure(function, path, "函数体未完整映射到可执行映像")

    for index, ref in enumerate(template.get("continuations", [])):
        if not isinstance(ref, dict) or not isinstance(ref.get("template"), dict):
            raise _error("原生合同 continuation 格式无效")
        target = _reference_target(pe, start, ref)
        name = ref.get("name", index)
        nested = _template_failure(
            pe,
            target,
            ref["template"],
            candidates,
            entries,
            chain_index,
            function,
            f"{path}.continuation[{name}]",
        )
        if nested is not None:
            return nested

    fragments = _chained_fragments(pe, start, template, entries, chain_index)
    if fragments is None:
        if template.get("chained"):
            return _failure(function, f"{path}.chained", "CHAININFO 片段数量或相对位置不匹配")
    else:
        for index, (entry, chained) in enumerate(fragments):
            nested = _template_failure(
                pe,
                entry[0],
                chained,
                candidates,
                entries,
                chain_index,
                function,
                f"{path}.chained[{index}]",
            )
            if nested is not None:
                return nested

    for index, row in enumerate(_equal_target_rows(template)):
        if _equal_target(pe, start, template, row["left"]) != _equal_target(
            pe, start, template, row["right"]
        ):
            return _failure(function, f"{path}.equal_targets[{index}]", "已审计目标地址不相等")

    for index, row in enumerate(_import_rows(template)):
        if not _import_matches(pe, start, row):
            return _failure(
                function,
                f"{path}.imports[{index}]",
                f"导入表槽位不是 {row['dll']}!{row['name']}",
            )

    for index, row in enumerate(_data_rows(template)):
        if not _data_matches(pe, start, row):
            return _failure(
                function, f"{path}.data_refs[{index}]", "已审计数据的范围、对齐或内容摘要不匹配"
            )

    for index, link in enumerate(template.get("links", [])):
        target_name = link.get("function")
        addend = link.get("addend", 0)
        if not isinstance(target_name, str) or not isinstance(addend, int):
            raise _error("原生合同嵌套链接格式无效")
        target = _reference_target(pe, start, link)
        if not any(target == other_start + addend for other_start, _ in candidates[target_name]):
            return _failure(
                function, f"{path}.links[{index}]", f"到 {target_name} 的已审计目标不匹配"
            )
    return None


def _candidate_link_failure(pe, candidate, candidates, function: str):
    start, variant = candidate
    for index, link in enumerate(variant.get("links", [])):
        target_name = link.get("function")
        addend = link.get("addend", 0)
        if not isinstance(target_name, str) or not isinstance(addend, int):
            raise _error("原生合同函数链接格式无效")
        target = _reference_target(pe, start, link)
        if not any(target == other_start + addend for other_start, _ in candidates[target_name]):
            return _failure(function, f"links[{index}]", f"到 {target_name} 的已审计目标不匹配")
    return None


def _derive_leaf_candidates(pe, functions, candidates, local_failures):
    """Recover no-pdata leaves only from a contract link in an already found caller."""
    changed = False
    for caller_name, caller_candidates in candidates.items():
        for caller_start, variant in caller_candidates:
            for link in variant.get("links", []):
                leaf_name = link.get("function")
                if leaf_name not in functions or not functions[leaf_name].get("leaf"):
                    continue
                addend = link.get("addend", 0)
                if not isinstance(addend, int):
                    raise _error("原生合同叶函数链接格式无效")
                leaf_start = _reference_target(pe, caller_start, link) - addend
                for leaf_variant in functions[leaf_name].get("variants", []):
                    try:
                        matches = _variant_matches(pe, leaf_start, leaf_variant)
                        # Immutable data/IAT failures cannot become valid as
                        # other function candidates are discovered. Reject them
                        # before insertion, otherwise the fixed point repeatedly
                        # reintroduces a leaf eliminated later in the same pass.
                        if matches:
                            failure = _indirect_dependency_failure(pe, leaf_start, leaf_variant)
                            if failure is not None:
                                detail = _failure(leaf_name, "body." + failure[0], failure[1])
                                if detail not in local_failures:
                                    local_failures.append(detail)
                                matches = False
                    except ValueError:
                        # An unselected/false caller candidate can name an
                        # address outside the image.  Ignore it and let its
                        # required link eliminate that caller below.
                        matches = False
                    if matches:
                        candidate = (leaf_start, leaf_variant)
                        if candidate not in candidates[leaf_name]:
                            candidates[leaf_name].append(candidate)
                            changed = True
    return changed


def _apply_reverse_link_constraints(pe, candidates):
    """Intersect every viable caller link's concrete target for each callee."""
    changed = False
    inbound = defaultdict(lambda: defaultdict(set))
    for caller_name, rows in candidates.items():
        for start, variant in rows:
            for link in variant.get("links", []):
                addend = link.get("addend", 0)
                if not isinstance(addend, int):
                    raise _error("原生合同函数链接格式无效")
                target_name = link["function"]
                slot = (
                    caller_name,
                    tuple(link["displacement"]),
                    link["next"],
                    addend,
                )
                inbound[target_name][slot].add(_reference_target(pe, start, link) - addend)
    for target_name, slots in inbound.items():
        allowed_sets = list(slots.values())
        allowed = set.intersection(*allowed_sets) if allowed_sets else set()
        rows = candidates[target_name]
        filtered = [row for row in rows if row[0] in allowed]
        if len(filtered) != len(rows):
            candidates[target_name] = filtered
            changed = True
    return changed


def _semantic_body(pe, start: int, template: dict):
    # Both pinned and relocated operands are permitted only after their full
    # template and dependency checks. Compare the same reviewed addresses in
    # one normal form, rather than treating a pinned IAT operand as new code.
    masks = {tuple(mask) for mask in template.get("masks", [])}
    for row in (
        *template.get("links", []),
        *template.get("globals", []),
        *template.get("continuations", []),
        *_data_rows(template),
        *_import_rows(template),
    ):
        masks.add(tuple(row["displacement"]))
    normalized = sorted(masks)
    return (
        template["size"],
        _masked_hash(_read(pe, start, template["size"], executable=True), normalized),
        tuple(normalized),
    )


def _variant_semantics(pe, start: int, variant: dict):
    points = tuple(
        sorted((name, start + offset) for name, offset in variant.get("points", {}).items())
    )
    globals_ = tuple(
        sorted(
            (row["name"], _reference_target(pe, start, row)) for row in variant.get("globals", [])
        )
    )
    links = tuple(
        sorted(
            (row["function"], row.get("addend", 0), _reference_target(pe, start, row))
            for row in variant.get("links", [])
        )
    )
    continuations = tuple(
        (
            _reference_target(pe, start, ref),
            *_semantic_body(pe, _reference_target(pe, start, ref), ref["template"]),
            _variant_semantics(pe, _reference_target(pe, start, ref), ref["template"]),
        )
        for ref in variant.get("continuations", [])
    )
    chained = tuple(
        (
            row.get("offset"),
            *_semantic_body(pe, start + row["offset"], row),
            _variant_semantics(pe, start + row["offset"], row),
        )
        for row in variant.get("chained", [])
    )
    data_refs = tuple(
        (_reference_target(pe, start, row), row["size"], row["alignment"], row["sha256"])
        for row in _data_rows(variant)
    )
    imports = tuple(
        (_reference_target(pe, start, row), row["dll"].lower(), row["name"])
        for row in _import_rows(variant)
    )
    equal_targets = tuple(
        (
            _equal_target(pe, start, variant, row["left"]),
            _equal_target(pe, start, variant, row["right"]),
        )
        for row in _equal_target_rows(variant)
    )
    return points, globals_, links, continuations, chained, data_refs, imports, equal_targets


def _select_variant(pe, name: str, start: int, rows):
    variants = [variant for candidate_start, variant in rows if candidate_start == start]
    semantics = {_variant_semantics(pe, start, variant) for variant in variants}
    if len(semantics) != 1:
        raise _error(f"原生合同函数 {name} 的同址变体语义不一致")
    return variants[0]


def _validate_function_spec(name: str, spec: dict):
    if not isinstance(spec, dict) or not isinstance(spec.get("leaf"), bool):
        raise _error(f"原生合同函数 {name} 格式无效")
    variants = spec.get("variants")
    if not isinstance(variants, list) or not variants:
        raise _error(f"原生合同函数 {name} 缺少变体")
    for variant in variants:
        if not isinstance(variant, dict):
            raise _error(f"原生合同函数 {name} 变体格式无效")
        size = variant.get("size")
        if not isinstance(size, int) or size <= 0 or not isinstance(variant.get("sha256"), str):
            raise _error(f"原生合同函数 {name} 变体缺少大小或摘要")
        _masked_hash(bytes(size), variant.get("masks", []))
        if not isinstance(variant.get("points", {}), dict):
            raise _error(f"原生合同函数 {name} point 格式无效")
        if not isinstance(variant.get("links", []), list) or not isinstance(
            variant.get("globals", []), list
        ):
            raise _error(f"原生合同函数 {name} 链接格式无效")
        for link in variant.get("links", []):
            if not isinstance(link, dict) or not isinstance(link.get("function"), str):
                raise _error(f"原生合同函数 {name} 链接缺少目标")


def _resolve_functions(pe, functions):
    for name, spec in functions.items():
        _validate_function_spec(name, spec)
    for spec in functions.values():
        for variant in spec["variants"]:
            for link in variant.get("links", []):
                if link["function"] not in functions:
                    raise _error(f"原生合同链接引用未知函数 {link['function']}")

    entries = _exception_entries(pe)
    chain_index = _chain_index(pe, entries)
    spans_by_size = defaultdict(list)
    for start, end, _unwind in entries:
        spans_by_size[end - start].append(start)
    candidates = {name: [] for name in functions}
    body_failures = []
    local_failures = []
    link_failures = []
    locally_valid = set()
    hash_cache = {}
    for name, spec in functions.items():
        if spec["leaf"]:
            continue
        for variant in spec["variants"]:
            key = (variant["size"], tuple(tuple(mask) for mask in variant.get("masks", [])))
            for start in spans_by_size[variant["size"]]:
                cache_key = (start, key)
                actual = hash_cache.get(cache_key)
                if actual is None:
                    actual = _masked_hash(
                        _read(pe, start, variant["size"], executable=True), variant.get("masks", [])
                    )
                    hash_cache[cache_key] = actual
                if actual == variant["sha256"]:
                    candidates[name].append((start, variant))
        if not candidates[name]:
            body_failures.append(_failure(name, "body", "没有匹配已审计 PDATA 函数体"))

    while True:
        changed = _derive_leaf_candidates(pe, functions, candidates, local_failures)
        changed = _apply_reverse_link_constraints(pe, candidates) or changed
        for name, rows in candidates.items():
            filtered = []
            for row in rows:
                nested_matches = _candidate_nested_contract_matches(
                    pe, row, candidates, entries, chain_index
                )
                links_match = _candidate_links_match(pe, row, candidates)
                if nested_matches:
                    locally_valid.add(name)
                if nested_matches and links_match:
                    filtered.append(row)
                    continue
                if not nested_matches:
                    detail = _template_failure(
                        pe, row[0], row[1], candidates, entries, chain_index, name, "body"
                    )
                    if detail is not None and detail not in local_failures:
                        local_failures.append(detail)
                if not links_match:
                    detail = _candidate_link_failure(pe, row, candidates, name)
                    if detail is not None and detail not in link_failures:
                        link_failures.append(detail)
            if len(filtered) != len(rows):
                candidates[name] = filtered
                changed = True
        if not changed:
            break

    resolved = {}
    variants = {}
    unresolved = []
    for name, rows in candidates.items():
        starts = {start for start, _ in rows}
        if not starts:
            unresolved.append(name)
            continue
        if len(starts) != 1:
            raise _error(f"原生合同函数 {name} 有 {len(starts)} 个匹配，拒绝连接")
        start = starts.pop()
        resolved[name] = start
        variants[name] = _select_variant(pe, name, start, rows)
    if unresolved:
        local = [row for row in local_failures if row["function"] in unresolved]
        # A function with one complete reviewed variant was only lost through
        # a failed callee; its other variants' mismatches are not the cause.
        local = [row for row in local if row["function"] not in locally_valid] or local
        detail = None
        if local:
            # Of several reviewed variants, report the one matched furthest.
            detail = max(
                (row for row in local if row["function"] == local[0]["function"]),
                key=lambda row: row["path"].count("."),
            )
        if detail is None:
            detail = next((row for row in body_failures if row["function"] in unresolved), None)
        if detail is None:
            detail = next((row for row in link_failures if row["function"] in unresolved), None)
        if detail is not None:
            detail = dict(
                detail, affected_callers=[name for name in unresolved if name != detail["function"]]
            )
            raise _error(
                f"原生合同函数 {detail['function']} 的 {detail['path']} 验证失败：{detail['reason']}",
                details=[detail],
            )
        raise _error(f"原生合同函数 {unresolved[0]} 没有唯一匹配")
    # The final unique assignments must still satisfy every explicitly needed link.
    final_candidates = {name: [(resolved[name], variants[name])] for name in functions}
    for name, row in final_candidates.items():
        if not _candidate_links_match(pe, row[0], final_candidates):
            raise _error(f"原生合同函数 {name} 的链接与已定位目标不一致")
    return resolved, variants


def _image_base(pe) -> int:
    value = getattr(pe.OPTIONAL_HEADER, "ImageBase", None)
    if not isinstance(value, int):
        raise _error("游戏 EXE 缺少映像基址")
    return value


def _rva_from_va_or_rva(pe, value: int) -> int:
    image_base = _image_base(pe)
    image_size = getattr(pe.OPTIONAL_HEADER, "SizeOfImage", 0)
    if image_base <= value < image_base + image_size:
        return value - image_base
    return value


def _read_c_string(pe, rva: int, *, limit: int = 1024, label: str = "原生 RTTI 类型名") -> str:
    value = bytearray()
    for index in range(limit):
        byte = _read(pe, rva + index, 1)[0]
        if byte == 0:
            try:
                return value.decode("ascii")
            except UnicodeDecodeError as exc:
                raise _error(f"{label}不是 ASCII") from exc
        value.append(byte)
    raise _error(f"{label}没有终止符")


def _validate_rtti(pe, rva: int, expected: str):
    if rva < 8:
        raise _error("原生 vtable 缺少 CompleteObjectLocator")
    locator_value = struct.unpack("<Q", _read(pe, rva - 8, 8))[0]
    locator = _rva_from_va_or_rva(pe, locator_value)
    # x64 MSVC CompleteObjectLocator: signature, offset, cdOffset,
    # pTypeDescriptor, pClassDescriptor, pSelf (all last fields are RVAs).
    raw = _read(pe, locator, 24)
    type_descriptor = struct.unpack_from("<I", raw, 12)[0]
    if not type_descriptor:
        raise _error("原生 vtable 缺少 TypeDescriptor")
    actual = _read_c_string(pe, type_descriptor + 16)
    if actual != expected:
        raise _error(f"原生 vtable RTTI 不匹配：需要 {expected}，得到 {actual}")


def _template_globals(pe, start: int, template: dict, entries, candidates, chain_index):
    for row in template.get("globals", []):
        yield row["name"], _reference_target(pe, start, row)
    for ref in template.get("continuations", []):
        yield from _template_globals(
            pe, _reference_target(pe, start, ref), ref["template"], entries, candidates, chain_index
        )
    for entry, chained in _chained_fragments(pe, start, template, entries, chain_index) or []:
        if not _template_matches(pe, entry[0], chained, candidates, entries, chain_index):
            raise _error("已验证的 chained 片段在全局恢复时不一致")
        yield from _template_globals(pe, entry[0], chained, entries, candidates, chain_index)


def _resolve_globals(pe, variants, functions, specs, entries, chain_index):
    found = defaultdict(set)
    candidates = {name: [(functions[name], variants[name])] for name in functions}
    for key, variant in variants.items():
        for name, rva in _template_globals(
            pe, functions[key], variant, entries, candidates, chain_index
        ):
            if name not in specs:
                raise _error(f"原生合同引用未知全局对象 {name}")
            found[name].add(rva)
    resolved = {}
    for name, spec in specs.items():
        values = found.get(name, set())
        if len(values) != 1:
            raise _error(f"原生全局对象 {name} 未得到唯一 RIP 地址")
        rva = values.pop()
        alignment = spec.get("alignment")
        writable = spec.get("writable")
        if not isinstance(alignment, int) or alignment <= 0 or not isinstance(writable, bool):
            raise _error(f"原生全局对象 {name} 合同格式无效")
        if rva % alignment:
            raise _error(f"原生全局对象 {name} 地址未按 {alignment} 字节对齐")
        section, _ = _section_for_rva(pe, rva, 8)
        if writable and not section.Characteristics & _IMAGE_SCN_MEM_WRITE:
            raise _error(f"原生全局对象 {name} 不在所需可写映像区间")
        rtti = spec.get("rtti")
        if rtti is not None:
            if not isinstance(rtti, str) or not rtti:
                raise _error(f"原生全局对象 {name} RTTI 合同格式无效")
            _validate_rtti(pe, rva, rtti)
        resolved[name] = rva
    return resolved


def resolve_native_contracts(pe, contract=None) -> dict[str, object]:
    """Resolve only the native code/data consumed by the resident adapter.

    ``contract`` exists for tests and generated profiles.  Passing ``None``
    lazily imports the generated production contract.
    """
    contract = _as_contract(contract)
    functions, variants = _resolve_functions(pe, contract["functions"])
    entries = _exception_entries(pe)
    globals_ = _resolve_globals(
        pe, variants, functions, contract["global_specs"], entries, _chain_index(pe, entries)
    )
    points = {}
    for key, variant in variants.items():
        for name, offset in variant.get("points", {}).items():
            if not isinstance(name, str) or not isinstance(offset, int) or offset < 0:
                raise _error(f"原生合同函数 {key} 的 point 定义无效")
            rva = functions[key] + offset
            _read(pe, rva, 16, executable=True)
            if name in points and points[name] != rva:
                raise _error(f"原生 point {name} 被多个函数定义")
            points[name] = rva
    contract_id = contract.get("metadata", {}).get("contract_id", "native-contract-v1")
    if not isinstance(contract_id, str) or not contract_id:
        raise _error("原生合同标识无效")
    return {
        "points": points,
        "globals": globals_,
        "functions": functions,
        "contract_id": contract_id,
    }
