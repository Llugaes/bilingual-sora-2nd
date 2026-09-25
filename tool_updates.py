"""Atomic, validated releases: running tools never reload half-written edits."""
import ast
import hashlib
import json
from pathlib import Path
from native_config import write_config

ROOT=Path(__file__).resolve().parent
RELEASE=ROOT/'generated/tool-release.json'
GROUPS={
    'ui':('native_overlay.py','native_settings.py','auto_connect.py','tool_updates.py','overlay_reloader.py','inputs.py','native_config.py','locales.py','win32.py','distribution.json','update_bootstrap.py','github_updates.py','update_installer.py','update_service.py','update_ui.py'),
    'logic':('runtime_text.js','runtime_identity.js'),
    'catalog':('resources.py','tables.py','menu_tables.py','catalog_build.py','menu_text.py','runtime_identity.py','native_catalog.py','cache_io.py','locales.py','model_worker.py'),
    'resident':('native_probe.py','native_runtime.py','native_agent.js','native_hash.js','native_transport.js','native_loading.py','inputs.py','native_config.py','win32.py'),
}


def release_data(root=ROOT):
    groups={k:hashlib.sha256(b''.join((root/name).read_bytes() for name in names)).hexdigest() for k,names in GROUPS.items()}
    return {'groups':groups,'version':hashlib.sha256(json.dumps(groups,sort_keys=True).encode()).hexdigest()[:16]}


def read_release(path=RELEASE):
    try:
        data=json.loads(Path(path).read_text('utf-8'))
        if isinstance(data,dict) and isinstance(data.get('groups'),dict) and set(data['groups'])==set(GROUPS):return data
    except (OSError,ValueError):pass
    return None


class ReleaseWatch:
    def __init__(self,path=RELEASE):self.path=path;self.current=read_release(path)
    def poll(self):
        value=read_release(self.path)
        if not value or value==self.current:return set()
        previous=self.current;self.current=value
        return {k for k in GROUPS if not previous or value['groups'][k]!=previous['groups'][k]}


if __name__=='__main__':
    import subprocess
    for name in set().union(*GROUPS.values()):
        path=ROOT/name
        if path.suffix=='.py':ast.parse(path.read_text('utf-8-sig'),filename=name)
        elif path.suffix=='.js':subprocess.run(['node','--check',str(path)],check=True)
    value=release_data();write_config(value,RELEASE);print(json.dumps(value,indent=2))
