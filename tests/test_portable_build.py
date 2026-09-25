import unittest
from tools.build_portable import canonical_records


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
