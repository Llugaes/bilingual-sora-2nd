"""Background stable-release checks; no network or archive work on Qt's thread."""
import json
from pathlib import Path
import threading
import time
from github_updates import GitHubClient,version_tuple
from update_installer import install,UpdateBusy,write_json

INTERVAL=6*3600
POLICIES={'automatic','notify','off'}


class UpdateService:
    def __init__(self,root,*,client=None,clock=time.time):
        self.root=Path(root);self.clock=clock
        self.distribution=json.loads((self.root/'distribution.json').read_text('utf-8'))
        self.directory=self.root/'generated/updates';self.preferences=self.directory/'preferences.json'
        self.policy=self._read(self.preferences).get('policy','automatic')
        if self.policy not in POLICIES:self.policy='automatic'
        self.client=client or GitHubClient(self.distribution['repository'])
        self.message='等待检查更新';self.available=None;self.pending=None;self.progress=None
        self.last_check=0;self.next_check=0;self._thread=None;self._lock=threading.Lock()

    @staticmethod
    def _read(path):
        try:
            data=json.loads(path.read_text('utf-8'))
            return data if isinstance(data,dict) else {}
        except (OSError,ValueError):return {}

    @property
    def busy(self):return bool(self._thread and self._thread.is_alive())

    def set_policy(self,value):
        if value not in POLICIES:raise ValueError('未知更新策略')
        self.policy=value;write_json(self.preferences,{'policy':value});self.next_check=0

    def tick(self,manual=False):
        if self.busy or (not manual and (self.policy=='off' or self.clock()<self.next_check)):return
        self._thread=threading.Thread(target=self._run,args=(manual,),name='release-update',daemon=True)
        self._thread.start()

    def _run(self,manual):
        # A process may terminate during network work; installer transactions
        # recover at next bootstrap. Native hooks never belong to this worker.
        with self._lock:
            try:self._check(manual)
            except Exception as exc:
                self.message='更新未完成：'+str(exc);self.next_check=self.clock()+900
                write_json(self.directory/'last-error.json',{'time':self.clock(),'error':str(exc)})
            finally:self.progress=None

    def _check(self,manual=False):
        if self.pending and self.policy=='automatic':
            meta,path=self.pending
            try:
                installed=install(self.root,path,meta)
                self.message=f'已安装 {installed}，界面正在刷新';self.pending=None;self.next_check=float('inf')
            except UpdateBusy as exc:self.message=str(exc);self.next_check=self.clock()+10
            return
        self.message='正在检查 GitHub 稳定版…'
        release,cache=self.client.latest(self._read(self.directory/'release-cache.json'))
        write_json(self.directory/'release-cache.json',cache)
        self.last_check=self.clock();self.next_check=self.clock()+INTERVAL
        if not release or version_tuple(release['tag_name'])<=version_tuple(self.distribution['version']):
            self.message='当前已是最新稳定版' if release else '仓库尚未发布稳定版';return
        self.available=release['tag_name']
        if self.policy!='automatic':self.message=f'发现 {self.available}；选择自动安装后生效';return
        if not (self.root/'installed-manifest.json').is_file():
            self.message=f'发现 {self.available}；开发目录不会被覆盖，请使用发行包';return
        meta,asset=self.client.metadata(release);path=self.directory/meta['asset']
        self.message=f'正在下载 {self.available}…'
        self.client.download(asset,meta,path,lambda ratio:setattr(self,'progress',ratio))
        self.pending=(meta,path)
        # Respect a policy change made while downloading.
        if self.policy=='automatic':self._check()
