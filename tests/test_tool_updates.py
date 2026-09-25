import json
from pathlib import Path
import tempfile
import unittest
from tool_updates import ReleaseWatch,GROUPS


class ReleaseTests(unittest.TestCase):
    def test_partial_or_unchanged_release_does_not_trigger_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'release.json';watch=ReleaseWatch(path)
            path.write_text('{');self.assertEqual(watch.poll(),set())
            first={'version':'1','groups':{k:'a' for k in GROUPS}}
            path.write_text(json.dumps(first));self.assertEqual(watch.poll(),set(GROUPS))
            self.assertEqual(watch.poll(),set())
            first['groups']['logic']='b';path.write_text(json.dumps(first))
            self.assertEqual(watch.poll(),{'logic'})
