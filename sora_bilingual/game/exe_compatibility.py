"""Accept known native images without requiring identical PE resources/metadata.

This is not an ABI scanner or a license check. Code, constants, initialized
globals, unwind data and relocations must still match a reviewed build.
"""

import hashlib
import json
from pathlib import Path
import struct

TARGET_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
BUILD_ID = "25386012"
# Hashes only, generated from TARGET_SHA256. No game code or assets are shipped.
# Keep this inside the module: existing stable update clients accept Python
# sources here but deliberately reject arbitrary data files in this directory.
KNOWN_IMAGE = {
    # This is the PE loader contract captured from TARGET_SHA256.  It does
    # not fingerprint the DOS stub, reserved DOS fields, or COFF symbol-table
    # metadata: Windows identifies the PE header through e_lfanew, and COFF
    # symbols are deprecated and should be zero for an image.  The fields
    # below determine the mapped image, entry point, or loader behavior.
    "layout": {
        "machine": 0x8664,
        "size_optional_header": 0xF0,
        "characteristics": 0x22,
        "optional": {
            "AddressOfEntryPoint": 0x7C9D8C,
            "ImageBase": 0x140000000,
            "SectionAlignment": 0x1000,
            "FileAlignment": 0x200,
            "SizeOfHeaders": 0x400,
            "Subsystem": 2,
            "DllCharacteristics": 0x8160,
            "LoaderFlags": 0,
            "NumberOfRvaAndSizes": 16,
        },
        # Resource, certificate, and debug directories are not native-hook
        # ABI.  A trusted fixed CodeView span below still protects all
        # neighbouring .rdata bytes.
        "directories": {
            0: [0xBEF9B0, 572],
            1: [0xBEFBEC, 280],
            3: [0xC62000, 326388],
            5: [0xCE5000, 44236],
            7: [0, 0],
            8: [0, 0],
            9: [0xB34A80, 40],
            10: [0xB34720, 320],
            11: [0, 0],
            12: [0x8BB000, 1960],
            13: [0, 0],
            14: [0, 0],
            15: [0, 0],
        },
        "sections": [
            {
                "name": ".text",
                "rva": 0x1000,
                "virtual_size": 0x8B900E,
                "characteristics": 0x60000020,
            },
            {
                "name": ".rdata",
                "rva": 0x8BB000,
                "virtual_size": 0x3366F0,
                "characteristics": 0x40000040,
            },
            {
                "name": ".data",
                "rva": 0xBF2000,
                "virtual_size": 0x6F2F4,
                "characteristics": 0xC0000040,
            },
            {
                "name": ".pdata",
                "rva": 0xC62000,
                "virtual_size": 0x4FAF4,
                "characteristics": 0x40000040,
            },
            {
                "name": ".reloc",
                "rva": 0xCE5000,
                "virtual_size": 0xACCC,
                "characteristics": 0x42000040,
            },
        ],
        "resource_section": {
            "name": ".rsrc",
            "rva": 0xCB2000,
            "virtual_size": 0x32DC8,
            "characteristics": 0x40000040,
        },
    },
    "debug_metadata": [[0xB6DEDC, 89]],  # trusted CodeView GUID/age/PDB path
    "sections": {
        ".text": "391bfb798c017892e9b97363d22ba80c00cc990283d8d1b3acece02d48c8910c",
        ".rdata": "a2d93c2e713aabfb5f160b449725f66859a7d86237aaf85c2b829eda16ebd54c",
        ".data": "35d2f4a6c74b6eea3e33363af672f32356e30b1761600cc8c7f09fc941f74c5e",
        ".pdata": "d5089978aa79e5b8fad4fb0dfe61735a6b19ed09eb62a5092950b8de9ce31b03",
        ".reloc": "61f3bee006e262a101a38aa4038bd1eaaeef2ba3f6321c8f190093d6b5efc7ca",
    },
}


class ExecutableCompatibilityError(ValueError):
    """The executable cannot satisfy this adapter's verified native contract."""

    def __init__(self, message, *, sha256=None, details=None):
        super().__init__(message)
        self.sha256 = sha256
        self.details = details or []


_LAYOUT_OPTIONAL_FIELDS = (
    "AddressOfEntryPoint",
    "ImageBase",
    "SectionAlignment",
    "FileAlignment",
    "SizeOfHeaders",
    "Subsystem",
    "DllCharacteristics",
    "LoaderFlags",
    "NumberOfRvaAndSizes",
)
_IGNORED_DIRECTORY_INDICES = {2, 4, 6}  # resource, certificate, debug
_MEM_EXECUTE = 0x20000000
_MEM_WRITE = 0x80000000
_CNT_CODE = 0x20


def _section_name(section):
    try:
        return section.Name.rstrip(b"\0").decode("ascii")
    except UnicodeDecodeError as exc:
        raise ExecutableCompatibilityError("游戏 EXE 区段名称无法识别") from exc


def _semantic_layout(pe):
    """Return only PE fields that define this adapter's mapped-image ABI."""
    if len(pe.OPTIONAL_HEADER.DATA_DIRECTORY) < 16:
        raise ExecutableCompatibilityError("游戏 EXE 数据目录不完整")
    return {
        "machine": pe.FILE_HEADER.Machine,
        "size_optional_header": pe.FILE_HEADER.SizeOfOptionalHeader,
        "characteristics": pe.FILE_HEADER.Characteristics,
        "optional": {
            field: getattr(pe.OPTIONAL_HEADER, field) for field in _LAYOUT_OPTIONAL_FIELDS
        },
        "directories": {
            index: [directory.VirtualAddress, directory.Size]
            for index, directory in enumerate(pe.OPTIONAL_HEADER.DATA_DIRECTORY)
            if index not in _IGNORED_DIRECTORY_INDICES
        },
        "sections": [
            {
                "name": _section_name(section),
                "rva": section.VirtualAddress,
                "virtual_size": section.Misc_VirtualSize,
                "characteristics": section.Characteristics,
            }
            for section in pe.sections
            if _section_name(section) != ".rsrc"
        ],
        "resource_section": next(
            (
                {
                    "name": _section_name(section),
                    "rva": section.VirtualAddress,
                    "virtual_size": section.Misc_VirtualSize,
                    "characteristics": section.Characteristics,
                }
                for section in pe.sections
                if _section_name(section) == ".rsrc"
            ),
            None,
        ),
    }


def _mapped_bytes(pe, section):
    """Fingerprint mapped contents, including BSS, excluding file padding."""
    start, size = section.PointerToRawData, section.SizeOfRawData
    if start < pe.OPTIONAL_HEADER.SizeOfHeaders or start + size > len(pe.__data__):
        raise ExecutableCompatibilityError("游戏 EXE 区段数据不完整")
    virtual_size = section.Misc_VirtualSize or size
    data = pe.__data__[start : start + min(size, virtual_size)]
    return data + bytes(max(0, virtual_size - size))


def image_profile(pe):
    """Build hashes for a trusted developer baseline, never learn from users' EXEs."""
    debug_metadata = _trusted_debug_metadata(pe)
    return {
        "layout": _semantic_layout(pe),
        "debug_metadata": debug_metadata,
        "sections": {
            _section_name(section): hashlib.sha256(
                _normalized_section(pe, section, debug_metadata)
            ).hexdigest()
            for section in pe.sections
            if _section_name(section) != ".rsrc"
        },
    }


def _trusted_debug_metadata(pe):
    """Locate PDB identity/path bytes only while building the trusted profile.

    Runtime candidates cannot choose their own ignored spans. The containing
    directory, RSDS signature and all neighboring bytes remain fingerprinted.
    """
    if len(pe.OPTIONAL_HEADER.DATA_DIRECTORY) <= 6:
        return []
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[6]
    if not directory.Size:
        return []
    entries = pe.get_data(directory.VirtualAddress, directory.Size)
    if len(entries) != directory.Size or directory.Size % 28:
        raise ExecutableCompatibilityError("游戏 EXE 调试目录不完整")
    spans = []
    for offset in range(0, len(entries), 28):
        _, _, _, _, kind, size, rva, raw = struct.unpack_from("<IIHHIIII", entries, offset)
        if kind != 2 or size < 24 or pe.get_data(rva, 4) != b"RSDS":
            continue
        section = pe.get_section_by_rva(rva)
        if (
            section is None
            or rva + size > section.VirtualAddress + section.Misc_VirtualSize
            or pe.get_offset_from_rva(rva) != raw
            or len(pe.get_data(rva, size)) != size
        ):
            raise ExecutableCompatibilityError("游戏 EXE 调试记录越界")
        spans.append([rva + 4, size - 4])
    return spans


def _normalized_section(pe, section, debug_metadata):
    data = bytearray(_mapped_bytes(pe, section))
    for rva, size in debug_metadata:
        offset = rva - section.VirtualAddress
        if 0 <= offset < len(data):
            if size < 0 or offset + size > len(data):
                raise ExecutableCompatibilityError("已适配调试记录范围越界")
            data[offset : offset + size] = bytes(size)
    return data


def _load_profile():
    return KNOWN_IMAGE


def _format_layout_value(value):
    if isinstance(value, int):
        return f"0x{value:X}"
    return str(value)


def _layout_differences(pe, profile):
    """Describe mapped-image differences without accepting a candidate profile."""
    actual = _semantic_layout(pe)
    expected = profile["layout"]
    differences = []
    for field in ("machine", "size_optional_header", "characteristics"):
        if actual[field] != expected[field]:
            differences.append(
                f"COFF.{field}={_format_layout_value(actual[field])}"
                f"（应为 {_format_layout_value(expected[field])}）"
            )
    for field, expected_value in expected["optional"].items():
        actual_value = actual["optional"].get(field)
        if actual_value != expected_value:
            differences.append(
                f"OptionalHeader.{field}={_format_layout_value(actual_value)}"
                f"（应为 {_format_layout_value(expected_value)}）"
            )
    for index, expected_value in expected["directories"].items():
        index = int(index)
        actual_value = actual["directories"].get(index)
        if actual_value != expected_value:
            differences.append(f"DataDirectory[{index}]={actual_value}（应为 {expected_value}）")

    expected_sections = {section["name"]: section for section in expected["sections"]}
    actual_sections = {}
    for section in pe.sections:
        name = _section_name(section)
        if name in actual_sections:
            differences.append(f"区段 {name} 重复")
        actual_sections[name] = section
    for name, expected_section in expected_sections.items():
        section = actual_sections.get(name)
        if section is None:
            differences.append(f"缺少核心区段 {name}")
            continue
        for field, actual_value in (
            ("rva", section.VirtualAddress),
            ("virtual_size", section.Misc_VirtualSize),
            ("characteristics", section.Characteristics),
        ):
            if actual_value != expected_section[field]:
                differences.append(
                    f"区段 {name}.{field}={_format_layout_value(actual_value)}"
                    f"（应为 {_format_layout_value(expected_section[field])}）"
                )
    expected_resource = expected["resource_section"]
    if expected_resource is None:
        raise ExecutableCompatibilityError("已适配映像缺少资源区段合同")
    actual_resource = actual_sections.get(expected_resource["name"])
    if actual_resource is None:
        differences.append(f"缺少资源区段 {expected_resource['name']}")
    else:
        for field, actual_value in (
            ("rva", actual_resource.VirtualAddress),
            ("virtual_size", actual_resource.Misc_VirtualSize),
            ("characteristics", actual_resource.Characteristics),
        ):
            if actual_value != expected_resource[field]:
                differences.append(
                    f"资源区段 {expected_resource['name']}.{field}="
                    f"{_format_layout_value(actual_value)}"
                    f"（应为 {_format_layout_value(expected_resource[field])}）"
                )
    resource = _resource_section(pe)
    resource_directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[2]
    if not resource_directory.VirtualAddress or not resource_directory.Size:
        differences.append("资源目录缺失")
    elif resource is None:
        differences.append("资源目录未落在有效区段内")
    elif _section_name(resource) in expected_sections:
        differences.append(f"资源目录指向核心区段 {_section_name(resource)}")
    for section in pe.sections:
        name = _section_name(section)
        if name in expected_sections:
            continue
        if name == expected_resource["name"]:
            continue
        if resource is None or section.VirtualAddress != resource.VirtualAddress:
            differences.append(f"新增非资源区段 {name}")
        elif section.Characteristics & (_MEM_EXECUTE | _MEM_WRITE | _CNT_CODE):
            differences.append(f"新增资源区段 {name} 具有可执行或可写权限")
        elif not _is_trailing_section(pe, section):
            differences.append(f"新增资源区段 {name} 不在映像尾部")
    return differences


def _resource_section(pe):
    resource = pe.OPTIONAL_HEADER.DATA_DIRECTORY[2]
    if not (resource.VirtualAddress or resource.Size):
        return None
    for section in pe.sections:
        begin = section.VirtualAddress
        end = begin + max(section.Misc_VirtualSize, section.SizeOfRawData)
        if begin <= resource.VirtualAddress and resource.VirtualAddress + resource.Size <= end:
            return section
    return None


def _is_trailing_section(pe, candidate):
    candidate_end = candidate.VirtualAddress + max(
        candidate.Misc_VirtualSize, candidate.SizeOfRawData
    )
    return (
        all(
            section is candidate
            or section.VirtualAddress + max(section.Misc_VirtualSize, section.SizeOfRawData)
            <= candidate.VirtualAddress
            for section in pe.sections
        )
        and candidate_end <= pe.OPTIONAL_HEADER.SizeOfImage
    )


def _validate_mapped_sections(pe):
    alignment = pe.OPTIONAL_HEADER.SectionAlignment
    file_alignment = pe.OPTIONAL_HEADER.FileAlignment
    if (
        not alignment
        or alignment & (alignment - 1)
        or not file_alignment
        or file_alignment & (file_alignment - 1)
        or not 0x200 <= file_alignment <= 0x10000
        or pe.FILE_HEADER.NumberOfSections > 96
    ):
        raise ExecutableCompatibilityError(
            "游戏 EXE 加载布局无效（SectionAlignment 或 FileAlignment）；未扫描签名或安装 hook。",
            details=[
                f"OptionalHeader.SectionAlignment=0x{alignment:X}",
                f"OptionalHeader.FileAlignment=0x{file_alignment:X}",
            ],
        )
    raw_ranges = []
    virtual_ranges = []
    for section in pe.sections:
        start, size = section.PointerToRawData, section.SizeOfRawData
        if start % file_alignment or any(
            start < end and begin < start + size for begin, end in raw_ranges
        ):
            raise ExecutableCompatibilityError("游戏 EXE 区段重叠或未对齐")
        raw_ranges.append((start, start + size))
        begin = section.VirtualAddress
        end = begin + max(section.Misc_VirtualSize, section.SizeOfRawData)
        if (
            begin % alignment
            or end > pe.OPTIONAL_HEADER.SizeOfImage
            or any(
                begin < existing_end and existing_begin < end
                for existing_begin, existing_end in virtual_ranges
            )
        ):
            raise ExecutableCompatibilityError("游戏 EXE 虚拟区段重叠或越界")
        virtual_ranges.append((begin, end))
    expected_image_size = max(
        ((end + alignment - 1) // alignment) * alignment for _, end in virtual_ranges
    )
    if pe.OPTIONAL_HEADER.SizeOfImage != expected_image_size:
        raise ExecutableCompatibilityError("游戏 EXE SizeOfImage 与区段映射不一致")


def _layout_error(differences):
    category = differences[0].split("=", 1)[0]
    return ExecutableCompatibilityError(
        f"游戏 EXE 加载布局不兼容（{category} 等 {len(differences)} 项）；未扫描签名或安装 hook。",
        details=differences,
    )


def verify_image(pe, digest):
    if pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20B:
        raise ExecutableCompatibilityError("需要 64 位 PE32+ sora_2nd.exe")
    if digest == TARGET_SHA256:
        return "exact"
    profile = _load_profile()
    _validate_mapped_sections(pe)
    differences = _layout_differences(pe, profile)
    if differences:
        raise _layout_error(differences)
    resource_section = _resource_section(pe)
    for section in pe.sections:
        name = _section_name(section)
        data = _normalized_section(pe, section, profile.get("debug_metadata", []))
        is_baseline_resource = name == ".rsrc"
        is_new_resource = (
            name not in profile["sections"]
            and resource_section is not None
            and section.VirtualAddress == resource_section.VirtualAddress
        )
        if is_baseline_resource or is_new_resource:
            continue
        if hashlib.sha256(data).hexdigest() != profile["sections"].get(name):
            raise ExecutableCompatibilityError(
                f"游戏 EXE 核心内容不兼容（{name}）；游戏版本或补丁修改了已适配的代码／数据。"
                "尚不能安全连接，请提供兼容诊断。"
            )
    resource = pe.OPTIONAL_HEADER.DATA_DIRECTORY[2]
    if resource.Size or resource.VirtualAddress:
        if resource_section is None or not (
            resource_section.VirtualAddress <= resource.VirtualAddress
            and resource.VirtualAddress + resource.Size
            <= resource_section.VirtualAddress + resource_section.Misc_VirtualSize
        ):
            raise ExecutableCompatibilityError("游戏 EXE 资源目录越界")
    certificate = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]
    if certificate.Size or certificate.VirtualAddress:
        raw_ranges = [
            (section.PointerToRawData, section.PointerToRawData + section.SizeOfRawData)
            for section in pe.sections
        ]
        if not (
            certificate.VirtualAddress >= max(end for _, end in raw_ranges)
            and certificate.VirtualAddress + certificate.Size <= len(pe.__data__)
        ):
            raise ExecutableCompatibilityError("游戏 EXE 证书目录越界")
    return "compatible_image"


def main():
    """Read-only support report: no game launch, attach or game-file changes."""
    import argparse
    from sora_bilingual.game.hooks import verify_target

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {"file": args.exe.name, "adapter_build": BUILD_ID}
    try:
        report = verify_target(args.exe)
        result.update(
            sha256=report["sha256"],
            compatible=True,
            compatibility=report["compatibility"],
            hooks=len(report["hooks"]),
        )
    except (OSError, ValueError) as exc:
        result.update(compatible=False, error=str(exc))
        if getattr(exc, "sha256", None):
            result["sha256"] = exc.sha256
        if getattr(exc, "details", None):
            result["details"] = exc.details
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
