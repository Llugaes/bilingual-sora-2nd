"""Background game discovery. Never launches games or replaces live hooks."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import frida

ROOT=Path(__file__).resolve().parent


class ConnectionPolicy:
    def __init__(self):self.attempted=set()
    def choose(self,games,backend_busy):
        if backend_busy or len(games)!=1:return None
        game=next(iter(games))
        if game in self.attempted:return None
        self.attempted.add(game);return game


class AutoConnector:
    def __init__(self,status_path):
        self.status_path=Path(status_path);self.policy=ConnectionPolicy();self.process=None
        self.message='自动连接已开启，等待游戏启动';self.error=None
        self.stop=threading.Event();self.wake=threading.Event()
        self.thread=threading.Thread(target=self._run,name='auto-connect',daemon=True);self.thread.start()

    def _run(self):
        from win32 import process_identity
        from tool_updates import ReleaseWatch
        releases=ReleaseWatch();device=None
        while not self.stop.is_set():
            try:
                if (ROOT/'generated/update-installing.json').exists():
                    self.message='正在安装更新，稍后自动连接';self.wake.wait(1);self.wake.clear();continue
                if device is None:device=frida.get_local_device()
                games=set()
                for p in device.enumerate_processes():
                    if p.name.lower()=='sora_2nd.exe':
                        try:games.add((p.pid,process_identity(p.pid)))
                        except OSError:pass
                try:status=json.loads(self.status_path.read_text('utf-8'))
                except (OSError,ValueError):status={}
                busy=bool(status.get('running') and 0<=time.time()-status.get('updated_at',0)<5)
                if self.process is not None:
                    if self.process.poll() is None:busy=True
                    else:
                        if self.process.returncode:
                            try:self.error=(ROOT/'generated/native-error.log').read_text('utf-8').strip().splitlines()[-1]
                            except (OSError,IndexError):self.error='连接未成功'
                        self.process=None
                changes=releases.poll()
                if not busy and changes & {'resident','catalog','logic'}:
                    # One attempt with the new release, never replace a live
                    # or initializing resident backend.
                    self.policy.attempted.difference_update(games)
                selected=self.policy.choose(games,busy)
                if not games:self.error=None;self.message='自动连接已开启，等待游戏启动'
                elif len(games)>1:self.message='检测到多个游戏进程，请保留一个'
                elif busy:self.error=None;self.message='自动连接正在运行'
                elif selected is not None:
                    self.error=None;self.message='已发现游戏，正在自动连接…'
                    executable=Path(sys.executable).with_name('pythonw.exe')
                    self.process=subprocess.Popen([str(executable),str(ROOT/'native_probe.py')],cwd=ROOT,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                elif self.error:self.message='连接失败：'+self.error
            except Exception as exc:
                device=None;self.message='自动检测暂不可用：'+str(exc)
            self.wake.wait(1);self.wake.clear()

    def close(self):
        self.stop.set();self.wake.set();self.thread.join(timeout=2)
