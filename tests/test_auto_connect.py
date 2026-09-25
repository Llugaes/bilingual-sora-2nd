import unittest
import tempfile,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from auto_connect import ConnectionPolicy


class AutoConnectTests(unittest.TestCase):
    def test_detector_launches_backend_after_late_game_start_and_never_terminates_it(self):
        from auto_connect import AutoConnector
        games=[];launched=[];exit_code=[None]
        def launch(*args,**kwargs):
            launched.append(args)
            return SimpleNamespace(poll=lambda:exit_code[0],returncode=0)
        with tempfile.TemporaryDirectory() as tmp,\
             patch('auto_connect.frida.get_local_device',return_value=SimpleNamespace(enumerate_processes=lambda:list(games))),\
             patch('win32.process_identity',side_effect=lambda pid:pid*10),\
             patch('auto_connect.subprocess.Popen',side_effect=launch):
            auto=AutoConnector(Path(tmp)/'status.json')
            def tick_until(predicate):
                end=time.monotonic()+2
                while not predicate() and time.monotonic()<end:auto.wake.set();time.sleep(.01)
                self.assertTrue(predicate())
            try:
                time.sleep(.02);self.assertEqual(launched,[])
                games.append(SimpleNamespace(pid=42,name='sora_2nd.exe'));tick_until(lambda:len(launched)==1)
                auto.wake.set();time.sleep(.02);self.assertEqual(len(launched),1)
                games[:]=[SimpleNamespace(pid=43,name='sora_2nd.exe')];exit_code[0]=0
                tick_until(lambda:len(launched)==2)
            finally:auto.close()

    def test_wait_connect_once_and_reconnect_after_game_restart(self):
        p=ConnectionPolicy();self.assertIsNone(p.choose(set(),False))
        self.assertEqual(p.choose({(42,1)},False),(42,1))
        self.assertIsNone(p.choose({(42,1)},False))
        self.assertIsNone(p.choose(set(),False))
        self.assertEqual(p.choose({(42,2)},False),(42,2))

    def test_live_backend_and_multiple_games_prevent_duplicate_injection(self):
        p=ConnectionPolicy()
        self.assertIsNone(p.choose({(42,1)},True))
        self.assertIsNone(p.choose({(42,1),(43,1)},False))
        self.assertEqual(p.choose({(42,1)},False),(42,1))
