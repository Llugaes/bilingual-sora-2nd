"""Build an isolated DEV ZIP from clean commits and verified accepted runtime bytes."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import zipfile

from sora_bilingual.paths import ROOT, build_label
from tools.build_release import build

BASELINE = "d7d98f057470dab766333f4fbe719749e24b2f38"
HOTFIX = "541dbbd9fbfa2cb9364992d831403e69b59d7168"
INTEGRATED = "974364ddc209e56d762e63a03d359e2b6f89fb21"
DISPLAY = "1.0.0-dev5-r26"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compiled_cache(receipt_path, game, *, cache_root=None):
    """Private local candidate seed: current compiler/resources, no user state."""
    from sora_bilingual.localization.native_catalog import fingerprint, model_path
    from sora_bilingual.localization.model_wire import wire_ready
    from sora_bilingual.localization.cache_io import read_model
    from sora_bilingual.localization.language_cache import LanguageFacts, _digest
    from sora_bilingual.config.locales import LOCALES

    receipt_path = Path(receipt_path).resolve()
    if not receipt_path.is_relative_to((ROOT / "generated").resolve()):
        raise ValueError("compiled receipt must belong to this candidate clone")
    receipt = json.loads(receipt_path.read_text("utf-8"))
    rendered = json.loads(
        (
            receipt_path.parent / (receipt_path.name.replace("-receipt.json", "-frida.json"))
        ).read_text("utf-8")
    )
    if rendered["wire_sha256"] != receipt["wire_sha256"] or rendered["runtime_text_sha256"] != sha(
        (ROOT / "sora_bilingual/game/scripts/runtime_text.js").read_bytes()
    ):
        raise ValueError("compiled wire does not match the verified production renderer")
    stamp = fingerprint(Path(game))
    if json.loads(json.dumps(stamp)) != receipt["signature"]:
        raise ValueError("compiled model does not match current compiler/resources")
    model = Path(receipt["model_path"]).resolve()
    wire = Path(receipt["wire_path"]).resolve()
    directory = model.parent
    allowed_cache = (
        Path(cache_root).resolve() if cache_root is not None else (ROOT / "generated").resolve()
    )
    directory_allowed = (
        directory == allowed_cache
        if cache_root is not None
        else directory.is_relative_to(allowed_cache)
    )
    if not directory_allowed or wire.parent != directory:
        raise ValueError("compiled cache path escapes this clone")
    signature = json.dumps(stamp, sort_keys=True)
    if model != model_path(signature, receipt["config"], directory).resolve():
        raise ValueError("compiled model filename does not match production identity")
    if not wire_ready(model) or sha(wire.read_bytes()) != receipt["wire_sha256"]:
        raise ValueError("compiled wire is not current/verified")
    if read_model(model) is None:
        raise ValueError("compiled source model is invalid")
    catalog_signature = directory / "catalog-signature.json"
    if catalog_signature.read_text("utf-8") != json.dumps(
        {"resources": stamp["resources"], "code": stamp["catalog_code"]}, sort_keys=True
    ):
        raise ValueError("raw catalogue identity mismatch")
    files = {
        f"generated/{p.name}": p
        for p in (
            directory / "catalog.json",
            catalog_signature,
            model,
            wire,
            wire.with_name(wire.name + ".stamp.json"),
        )
    }
    facts = LanguageFacts(directory)
    rejected_rules = 0
    for path in sorted(facts.output.glob("*/*/*.json")):
        record = json.loads(path.read_text("utf-8"))
        identity = record.get("identity")
        if not isinstance(identity, list) or len(identity) != 4:
            raise ValueError("invalid language fact identity")
        locale, kind, rules, resource = identity
        if rules != facts.codes.get(kind):
            rejected_rules += 1
            continue
        if (
            locale not in LOCALES
            or path.parent.name != kind
            or path.parent.parent.name != locale
            or path.stem != _digest(identity)
            or record.get("digest") != _digest(record["value"])
        ):
            raise ValueError("language fact provenance/checksum mismatch")
        files["generated/" + path.relative_to(directory).as_posix()] = path
    for path in files.values():
        if not path.resolve().is_relative_to(directory) or not path.is_file():
            raise ValueError("cache file escapes current compilation directory")
    return files, {
        "schema": 1,
        "private_candidate_only": True,
        "config": receipt["config"],
        "signature": stamp,
        "wire_sha256": receipt["wire_sha256"],
        "model_name": model.name,
        "wire_name": wire.name,
        "renderer_sha256": rendered["runtime_text_sha256"],
        "files": {name: sha(path.read_bytes()) for name, path in files.items()},
        "compatible_language_facts": len(files) - 5,
        "obsolete_fact_rules_excluded": rejected_rules,
        "copied_user_state": False,
        "copied_font_receipts_or_agent_tokens": False,
        "fresh_zip_extraction": "model/raw/facts remain reusable when code/resources/config match; wire stamp may require one serialization after extraction changes model mtime",
    }


def candidate(accepted, output, *, compiled_receipt=None, game=None):
    accepted, output = Path(accepted).resolve(), Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT.resolve()):
        raise ValueError("candidate output must be a new directory inside this clone")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("commit the source before packaging")
    cache_files, cache_manifest = (
        compiled_cache(compiled_receipt, game) if compiled_receipt else ({}, None)
    )
    dev = json.loads((accepted / "dev-manifest.json").read_text("utf-8"))
    if dev.get("source_head") != BASELINE or dev.get("display_version") != "1.0.0-dev5-r14":
        raise ValueError("accepted runtime provenance differs")
    installed_path = accepted / "installed-manifest.json"
    # The accepted DEV unpacks the full managed-file receipt as dev-manifest;
    # it intentionally omits a stable installed receipt to retain DEV identity.
    receipt = json.loads(installed_path.read_text("utf-8")) if installed_path.is_file() else dev
    runtime_id = receipt["runtime_id"]
    extra = {}
    for name, digest in receipt["files"].items():
        if name == "BilingualSora2nd.exe" or name.startswith("runtime/"):
            path = (accepted / name).resolve()
            if not path.is_relative_to(accepted):
                raise ValueError("runtime path escapes accepted package")
            data = path.read_bytes()
            if sha(data) != digest:
                raise ValueError("accepted runtime checksum mismatch: " + name)
            extra[name] = data
    if "BilingualSora2nd.exe" not in extra or f"runtime/{runtime_id}/python.exe" not in extra:
        raise ValueError("accepted launcher/runtime incomplete")
    runtime_sha = sha(
        json.dumps({n: sha(v) for n, v in sorted(extra.items())}, sort_keys=True).encode()
    )
    if (
        runtime_id != "bac6e42e94e62356"
        or len(extra) != 552
        or runtime_sha != "abf98b97e7ae210ea8f930cb7727caca4e7aaa0cfb8987e9b3b227d1e09d2f55"
    ):
        raise ValueError("runtime differs from independently verified r14/r18 exact inventory")
    distribution = json.loads((ROOT / "distribution.json").read_text("utf-8"))
    staging = output / "build-components"
    package, _ = build(
        distribution["version"],
        distribution["repository"],
        staging,
        extra=extra,
        runtime_id=runtime_id,
    )
    with zipfile.ZipFile(package) as archive:
        installed = json.loads(archive.read("installed-manifest.json"))
    manifest = {
        **installed,
        "display_version": DISPLAY,
        "target_version": "1.0.0",
        "source_head": source,
        "source_dirty": False,
        "accepted_baseline": BASELINE,
        "hotfix_source": HOTFIX,
        "hotfix_target": INTEGRATED,
        "validation": "offline; live user acceptance pending",
        "unresolved": [
            "045 CRC/callee/IAT contracts and existing 1.0 safe variants pass offline PE gates; actual MOD runtime resources and GPU remain unverified",
            "r26 bounded record-owned item-help copies and complete native Tools type/range headers pass offline resource/production regressions; user-confirmed r25 description/wrapping behavior is preserved; r26 live acceptance remains pending",
            "The user reported r25 observed descriptions and line breaks correct at 12:20 UTC on 2026-10-07, with Tools type/range remaining; this is observed user coverage, not every offline row; geometry is frozen for this follow-up",
            "All 5511 inherited raw-input three-mode plans remain unchanged; 94 inherited raw-input gaps, including 48 name surface inputs, Move and DEF role evidence, retain their status; r26 live acceptance remains pending",
            "Independent exact candidate audit is required before any DEV deployment; this package is not deployed",
        ],
    }
    # Sidecars deliberately remain outside the stable install manifest. A DEV
    # candidate is extracted directly; it is never a stable update asset.
    with zipfile.ZipFile(package, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dev-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("generated/development-version.txt", distribution["version"] + "\n")
        archive.writestr(
            "candidate-case-status.md",
            (ROOT / "docs/verification/dev5-r26-case-regression.md").read_bytes(),
        )
        archive.writestr(
            "dev5-r26-remaining-names.md",
            (ROOT / "docs/verification/dev5-r26-remaining-names.md").read_bytes(),
        )
        archive.writestr(
            "candidate-tips-evidence.md",
            (ROOT / "docs/verification/dev5-r19-tips-owner-proposal.md").read_bytes(),
        )
        if cache_manifest:
            cache_manifest["source_head"] = source
            archive.writestr(
                "candidate-cache.json", json.dumps(cache_manifest, ensure_ascii=False, indent=2)
            )
            for name, path in cache_files.items():
                archive.write(path, name)
    packages = output / "packages"
    packages.mkdir()
    final = packages / f"bilingual-sora-2nd-{DISPLAY}-windows-x64.zip"
    package.rename(final)
    destination = output / "DEV"
    destination.mkdir()
    with zipfile.ZipFile(final) as archive:
        for name in archive.namelist():
            if not (destination / name).resolve().is_relative_to(destination):
                raise ValueError("candidate ZIP path escapes output")
        archive.extractall(destination)
    # Local handoff keeps exact source model mtime so its existing wire stamp
    # remains valid. No model or wire payload is changed. Ordinary ZIP tools
    # may choose another mtime; that portable limitation is disclosed above.
    for name, path in cache_files.items():
        shutil.copy2(path, destination / name)
    checked = 0
    for name, digest in installed["files"].items():
        if sha((destination / name).read_bytes()) != digest:
            raise ValueError("candidate checksum mismatch: " + name)
        checked += 1
    # Exercise the packaged dependency closure in its own embedded interpreter,
    # without a GUI, game resources or attachment. A correct receipt alone
    # cannot detect a module omitted from the explicit release allowlist.
    subprocess.run(
        [
            str(destination / f"runtime/{runtime_id}/python.exe"),
            "-B",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from sora_bilingual.game.native_contract_data import CONTRACT; "
            "from sora_bilingual.localization.menu_text import MenuTranslator; "
            "from sora_bilingual.localization.save_summary import save_display_constructors; "
            "assert CONTRACT['functions'] and CONTRACT['global_specs']",
            str(destination),
        ],
        cwd=destination,
        check=True,
    )
    assert build_label(destination) == "DEV " + DISPLAY
    generated = {"generated/development-version.txt"} | set(cache_files)
    assert {
        p.relative_to(destination).as_posix()
        for p in (destination / "generated").rglob("*")
        if p.is_file()
    } == generated
    if cache_manifest:
        from sora_bilingual.localization.model_wire import wire_ready

        assert wire_ready(destination / "generated" / cache_manifest["model_name"])
        for name, digest in cache_manifest["files"].items():
            assert sha((destination / name).read_bytes()) == digest, name
    result = {
        "source_head": source,
        "source_dirty": False,
        "baseline": BASELINE,
        "hotfix_source": HOTFIX,
        "hotfix_target": INTEGRATED,
        "root": str(destination),
        "entry": str(destination / "BilingualSora2nd.exe"),
        "package": str(final),
        "package_sha256": sha(final.read_bytes()),
        "package_bytes": final.stat().st_size,
        "build_label": build_label(destination),
        "managed_files_verified": checked,
        "reused_runtime_files": len(extra),
        "runtime_id": runtime_id,
        "reused_runtime_sha256": runtime_sha,
        "runtime_matches_accepted": True,
        "copied_user_state": False,
        "limitations": manifest["unresolved"],
        "compiled_cache": cache_manifest,
        "local_wire_stamp_ready": bool(cache_manifest),
    }
    (packages / "candidate-package.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
    )
    # Remove only the exact disposable files created above, never an older dist.
    for name in staging.iterdir():
        if not name.is_file():
            raise ValueError("unexpected staging directory")
        name.unlink()
    staging.rmdir()
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--accepted", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--compiled-receipt", type=Path)
    p.add_argument("--game", type=Path)
    a = p.parse_args()
    if bool(a.compiled_receipt) != bool(a.game):
        p.error("--compiled-receipt and --game must be supplied together")
    result = candidate(a.accepted, a.output, compiled_receipt=a.compiled_receipt, game=a.game)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "compiled_cache"}, ensure_ascii=False, indent=2
        )
    )
