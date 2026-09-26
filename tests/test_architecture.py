"""Dependency rules checked without importing GUI or attaching to a process."""

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Dependencies flow from application orchestration towards data/platform modules.
ALLOWED = {
    "localization": {"localization", "config"},
    "platform": set(),
    "config": {"config", "platform"},
    "fonts": {"fonts", "localization", "game", "config"},
    "game": {"game", "localization", "platform", "config", "updates"},
    "updates": {"updates", "config"},
    "app": {"app", "game", "localization", "platform", "config", "updates", "fonts"},
    "legacy": {"legacy", "platform"},
}


class ArchitectureTests(unittest.TestCase):
    def test_hot_reload_sources_do_not_install_native_instrumentation(self):
        from sora_bilingual.updates.tool_updates import GROUPS

        for name in GROUPS["logic"]:
            self.assertNotRegex(
                (ROOT / name).read_text("utf-8"),
                r"\b(?:Interceptor|NativeFunction|NativeCallback|Memory|Process|Stalker|CModule)\b",
                name,
            )

    def test_resident_and_ui_files_have_reload_owners(self):
        from sora_bilingual.updates.tool_updates import GROUPS

        covered = set().union(*GROUPS.values())
        active = {
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "sora_bilingual").rglob("*")
            if p.suffix in {".py", ".js"} and not {"legacy", "fonts"} & set(p.parts)
        }
        self.assertTrue(active <= covered, sorted(active - covered))

    def test_module_dependencies(self):
        violations = []
        for file in (ROOT / "sora_bilingual").rglob("*.py"):
            if file.parent.name == "sora_bilingual":
                continue
            layer = file.relative_to(ROOT / "sora_bilingual").parts[0]
            for node in ast.walk(ast.parse(file.read_text("utf-8-sig"))):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                elif isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                for module in modules:
                    if layer in {"localization", "updates", "config", "game", "fonts"}:
                        self.assertFalse(module.startswith("PySide6"), f"{layer} imports Qt")
                    if layer == "localization":
                        self.assertNotIn(module.split(".")[0], {"frida", "urllib", "requests"})
                    if module.startswith("tools"):
                        violations.append(f"{file.name}: runtime imports developer tools")
                    elif module.startswith("sora_bilingual."):
                        dependency = module.split(".")[1]
                        if dependency != "paths" and dependency not in ALLOWED[layer]:
                            violations.append(f"{layer} -> {dependency} in {file.name}")
        self.assertEqual(violations, [])

    def test_release_contains_runtime_and_excludes_local_state(self):
        from tools.build_release import FILES

        self.assertEqual(len(FILES), len(set(FILES)))
        for name in FILES:
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertNotIn(
                Path(name).parts[0], {"generated", "tests", "tools", ".venv", ".local"}
            )
        runtime = {
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "sora_bilingual").rglob("*")
            if p.suffix in {".py", ".js"} and "legacy" not in p.parts
        }
        self.assertTrue(runtime <= set(FILES), sorted(runtime - set(FILES)))
