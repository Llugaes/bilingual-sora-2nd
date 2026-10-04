"""Validate only the native contracts used by the bilingual renderer.

Whole-file SHA-256 remains diagnostic identity, never an allowlist. Unrelated
code, assets, metadata, section contents and version labels are not compared.
"""

import json
from pathlib import Path

BUILD_ID = "native-contract-v1"


class ExecutableCompatibilityError(ValueError):
    """One required native dependency could not be located unambiguously."""

    def __init__(self, message, *, sha256=None, details=None):
        super().__init__(message)
        self.sha256 = sha256
        self.details = details or []


def verify_image(pe, digest=None):
    """Return independently located native dependencies from this PE snapshot."""
    if pe.FILE_HEADER.Machine != 0x8664 or pe.OPTIONAL_HEADER.Magic != 0x20B:
        raise ExecutableCompatibilityError("需要 64 位 PE32+ sora_2nd.exe")
    from sora_bilingual.game.native_contracts import resolve_native_contracts

    return resolve_native_contracts(pe)


def main():
    """Read-only diagnosis; never starts, attaches to, or alters a game."""
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
            native_points=len(report["native"]),
            contract_id=report["native_contract_id"],
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
