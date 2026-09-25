import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.build_portable import canonical_records, runtime_payload, QT_MODULES


class RuntimeRecordTests(unittest.TestCase):
    def test_removed_launchers_do_not_change_runtime_identity(self):
        name = "Lib/site-packages/library-1.0.dist-info/RECORD"
        a = {
            "Lib/site-packages/library.py": b"code",
            name: b"../../bin/tool.exe,sha256=machineA,123\nlibrary.py,sha256=same,4\nlibrary-1.0.dist-info/RECORD,,\n",
        }
        b = {**a, name: a[name].replace(b"machineA", b"machineB")}
        canonical_records(a)
        canonical_records(b)
        self.assertEqual(a, b)
        self.assertNotIn(b"bin/tool.exe", a[name])
        self.assertIn(b"library.py,sha256=same,4", a[name])


class RuntimePayloadTests(unittest.TestCase):
    def test_dependencies_dynamic_plugins_and_licenses_survive_pruning(self):
        qt = "Lib/site-packages/PySide6/"
        files = {
            qt + "QtWidgets.pyd": b"widgets",
            qt + "Qt6Widgets.dll": b"widget-dll",
            qt + "Qt6Core.dll": b"core",
            qt + "Qt6Svg.dll": b"svg",
            qt + "plugins/imageformats/qsvg.dll": b"plugin",
            qt + "plugins/platforms/qwindows.dll": b"platform",
            qt + "QtQuick.pyd": b"unused",
            qt + "Qt6Quick.dll": b"unused",
            qt + "qml/QtQuick/plugin.dll": b"unused",
            qt + "designer.exe": b"unused",
            qt + "include/header.h": b"unused",
            "Lib/site-packages/pygame/docs/generated/LGPL.txt": b"license",
            "Lib/site-packages/pygame/docs/generated/index.html": b"unused",
            "Lib/site-packages/pygame/examples/data/large.png": b"unused",
            "Lib/site-packages/pyside6_essentials.dist-info/licenses/license.txt": b"license",
        }

        def binary(*, data, **kwargs):
            imports = {b"widgets": [b"Qt6Widgets.dll"], b"widget-dll": [b"Qt6Core.dll"]}
            delayed = {b"plugin": [b"Qt6Svg.dll"]}
            from unittest.mock import MagicMock

            pe = MagicMock()
            pe.__enter__.return_value = SimpleNamespace(
                parse_data_directories=lambda **kwargs: None,
                DIRECTORY_ENTRY_IMPORT=[SimpleNamespace(dll=n) for n in imports.get(data, [])],
                DIRECTORY_ENTRY_DELAY_IMPORT=[
                    SimpleNamespace(dll=n) for n in delayed.get(data, [])
                ],
            )
            return pe

        with patch("pefile.PE", side_effect=binary):
            selected = runtime_payload(files)
        self.assertEqual(selected, {n: d for n, d in files.items() if d != b"unused"})

    def test_every_application_qt_import_is_bundled(self):
        root = Path(__file__).resolve().parents[1] / "sora_bilingual"
        for source in root.rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text("utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith("PySide6."):
                        self.assertIn(node.module.split(".")[1], QT_MODULES, source)
                    elif node.module == "PySide6":
                        for imported in node.names:
                            self.assertIn(imported.name, QT_MODULES, source)
                elif isinstance(node, ast.Import):
                    for imported in node.names:
                        if imported.name.startswith("PySide6."):
                            self.assertIn(imported.name.split(".")[1], QT_MODULES, source)
