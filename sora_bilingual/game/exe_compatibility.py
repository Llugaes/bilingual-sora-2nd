"""Accept known native images without requiring identical PE resources/metadata.

This is not an ABI scanner or a license check. Code, constants, initialized
globals, unwind data and relocations must still match a reviewed build.
"""

import hashlib
import json
from pathlib import Path

TARGET_SHA256 = "d8b2911d1576216bdc22d070550e4f531e105de7ed2981885849669f4acf8aaf"
BUILD_ID = "25386012"
# Hashes only, generated from TARGET_SHA256. No game code or assets are shipped.
# Keep this inside the module: existing stable update clients accept Python
# sources here but deliberately reject arbitrary data files in this directory.
KNOWN_IMAGE = {
    "header": "18d70e5abfb13554f801b5170279bf475b6fb06ebea231bc9a55c604a263664e",
    "sections": {
        ".text": "391bfb798c017892e9b97363d22ba80c00cc990283d8d1b3acece02d48c8910c",
        ".rdata": "dbce29cd2d041541d14aa4ade511f4a9af7669f0a69d2dee79a138a8f0cf9bfb",
        ".data": "35d2f4a6c74b6eea3e33363af672f32356e30b1761600cc8c7f09fc941f74c5e",
        ".pdata": "d5089978aa79e5b8fad4fb0dfe61735a6b19ed09eb62a5092950b8de9ce31b03",
        ".reloc": "61f3bee006e262a101a38aa4038bd1eaaeef2ba3f6321c8f190093d6b5efc7ca",
    },
}


class ExecutableCompatibilityError(ValueError):
    """The executable cannot satisfy this adapter's verified native contract."""


def _header_fingerprint(pe):
    """Keep every header field except explicitly allowed non-ABI changes."""
    size = pe.OPTIONAL_HEADER.SizeOfHeaders
    if size > len(pe.__data__) or len(pe.OPTIONAL_HEADER.DATA_DIRECTORY) < 5:
        raise ExecutableCompatibilityError("游戏 EXE 文件头不完整")
    header = bytearray(pe.__data__[:size])
    ignored = [
        (pe.FILE_HEADER.get_field_absolute_offset("TimeDateStamp"), 4),
        (pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum"), 4),
        (pe.OPTIONAL_HEADER.DATA_DIRECTORY[2].get_file_offset(), 8),  # resource directory
        (pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].get_file_offset(), 8),  # certificate file offset
    ]
    # Repacking a resource can move the raw sections without moving any RVA.
    ignored.extend((s.get_field_absolute_offset("PointerToRawData"), 4) for s in pe.sections)
    for offset, length in ignored:
        if offset < 0 or offset + length > size:
            raise ExecutableCompatibilityError("游戏 EXE 文件头越界")
        header[offset : offset + length] = bytes(length)
    return hashlib.sha256(header).hexdigest()


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
    return {
        "header": _header_fingerprint(pe),
        "sections": {
            s.Name.rstrip(b"\0").decode("ascii"): hashlib.sha256(_mapped_bytes(pe, s)).hexdigest()
            for s in pe.sections
            if s.Name.rstrip(b"\0") != b".rsrc"
        },
    }


def _load_profile():
    return KNOWN_IMAGE


def verify_image(pe, digest):
    if pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20B:
        raise ExecutableCompatibilityError("需要 64 位 PE32+ sora_2nd.exe")
    if digest == TARGET_SHA256:
        return "exact"
    profile = _load_profile()
    if _header_fingerprint(pe) != profile["header"]:
        raise ExecutableCompatibilityError(
            "游戏 EXE 的地址布局与已适配版本不同（PE layout）；尚不能安全连接，请提供兼容诊断。"
        )
    raw_ranges = []
    resources = None
    for section in pe.sections:
        name = section.Name.rstrip(b"\0").decode("ascii")
        data = _mapped_bytes(pe, section)
        start, size = section.PointerToRawData, section.SizeOfRawData
        if start % pe.OPTIONAL_HEADER.FileAlignment or any(
            start < end and begin < start + size for begin, end in raw_ranges
        ):
            raise ExecutableCompatibilityError("游戏 EXE 区段重叠或未对齐")
        raw_ranges.append((start, start + size))
        if name == ".rsrc":
            resources = section
            continue
        if hashlib.sha256(data).hexdigest() != profile["sections"].get(name):
            raise ExecutableCompatibilityError(
                f"游戏 EXE 核心内容不兼容（{name}）；游戏版本或补丁修改了已适配的代码／数据。"
                "尚不能安全连接，请提供兼容诊断。"
            )
    resource = pe.OPTIONAL_HEADER.DATA_DIRECTORY[2]
    if resource.Size or resource.VirtualAddress:
        if resources is None or not (
            resources.VirtualAddress <= resource.VirtualAddress
            and resource.VirtualAddress + resource.Size
            <= resources.VirtualAddress + resources.Misc_VirtualSize
        ):
            raise ExecutableCompatibilityError("游戏 EXE 资源目录越界")
    certificate = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4]
    if certificate.Size or certificate.VirtualAddress:
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
        result["sha256"] = hashlib.sha256(args.exe.read_bytes()).hexdigest()
        report = verify_target(args.exe)
        result.update(
            compatible=True, compatibility=report["compatibility"], hooks=len(report["hooks"])
        )
    except (OSError, ValueError) as exc:
        result.update(compatible=False, error=str(exc))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0 if result["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
