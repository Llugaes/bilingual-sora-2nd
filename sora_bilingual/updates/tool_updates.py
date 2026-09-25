"""Atomic, validated releases: running tools never reload half-written edits."""

import ast
import hashlib
import json
from pathlib import Path
from sora_bilingual.config.native_config import write_config

from sora_bilingual.paths import ROOT

RELEASE = ROOT / "generated/tool-release.json"
GROUPS = {
    "ui": (
        "sora_bilingual/__init__.py",
        "sora_bilingual/__main__.py",
        "sora_bilingual/app/__init__.py",
        "sora_bilingual/config/__init__.py",
        "sora_bilingual/platform/__init__.py",
        "sora_bilingual/updates/__init__.py",
        "sora_bilingual/app/native_overlay.py",
        "sora_bilingual/app/presentation.py",
        "sora_bilingual/app/i18n.py",
        "sora_bilingual/app/ui_widgets.py",
        "sora_bilingual/paths.py",
        "launch.py",
        "sora_bilingual/app/native_settings.py",
        "sora_bilingual/app/auto_connect.py",
        "sora_bilingual/updates/tool_updates.py",
        "sora_bilingual/app/overlay_reloader.py",
        "sora_bilingual/platform/inputs.py",
        "sora_bilingual/config/native_config.py",
        "sora_bilingual/config/locales.py",
        "sora_bilingual/platform/win32.py",
        "distribution.json",
        "sora_bilingual/bootstrap.py",
        "sora_bilingual/updates/github_updates.py",
        "sora_bilingual/updates/update_installer.py",
        "sora_bilingual/updates/update_service.py",
        "sora_bilingual/app/update_ui.py",
        "sora_bilingual/platform/shortcuts.py",
    ),
    "logic": (
        "sora_bilingual/game/scripts/runtime_text.js",
        "sora_bilingual/game/scripts/runtime_identity.js",
    ),
    "catalog": (
        "sora_bilingual/localization/__init__.py",
        "sora_bilingual/config/__init__.py",
        "sora_bilingual/localization/resources.py",
        "sora_bilingual/localization/tables.py",
        "sora_bilingual/localization/menu_tables.py",
        "sora_bilingual/localization/catalog_build.py",
        "sora_bilingual/localization/menu_text.py",
        "sora_bilingual/localization/runtime_identity.py",
        "sora_bilingual/localization/native_catalog.py",
        "sora_bilingual/localization/cache_io.py",
        "sora_bilingual/config/locales.py",
        "sora_bilingual/localization/model_worker.py",
    ),
    "resident": (
        "sora_bilingual/game/hooks.py",
        "sora_bilingual/game/__init__.py",
        "sora_bilingual/config/__init__.py",
        "sora_bilingual/config/locales.py",
        "sora_bilingual/platform/__init__.py",
        "sora_bilingual/updates/__init__.py",
        "sora_bilingual/paths.py",
        "sora_bilingual/game/native_probe.py",
        "sora_bilingual/game/native_runtime.py",
        "sora_bilingual/game/scripts/native_agent.js",
        "sora_bilingual/game/scripts/native_hash.js",
        "sora_bilingual/game/scripts/native_transport.js",
        "sora_bilingual/game/native_loading.py",
        "sora_bilingual/platform/inputs.py",
        "sora_bilingual/config/native_config.py",
        "sora_bilingual/platform/win32.py",
    ),
}


def release_data(root=ROOT):
    groups = {
        k: hashlib.sha256(b"".join((root / name).read_bytes() for name in names)).hexdigest()
        for k, names in GROUPS.items()
    }
    return {
        "groups": groups,
        "version": hashlib.sha256(json.dumps(groups, sort_keys=True).encode()).hexdigest()[:16],
    }


def read_release(path=RELEASE):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
        if (
            isinstance(data, dict)
            and isinstance(data.get("groups"), dict)
            and set(data["groups"]) == set(GROUPS)
        ):
            return data
    except OSError, ValueError:
        pass
    return None


class ReleaseWatch:
    def __init__(self, path=RELEASE):
        self.path = path
        self.current = read_release(path)

    def poll(self):
        value = read_release(self.path)
        if not value or value == self.current:
            return set()
        previous = self.current
        self.current = value
        return {k for k in GROUPS if not previous or value["groups"][k] != previous["groups"][k]}


if __name__ == "__main__":
    import subprocess

    for name in set().union(*GROUPS.values()):
        path = ROOT / name
        if path.suffix == ".py":
            ast.parse(path.read_text("utf-8-sig"), filename=name)
        elif path.suffix == ".js":
            subprocess.run(["node", "--check", str(path)], check=True)
    value = release_data()
    write_config(value, RELEASE)
    print(json.dumps(value, indent=2))
