"""Compact, atomic cache publication with a private temporary file per writer."""
import json
from pathlib import Path
import tempfile
from native_config import replace_file


def publish_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,suffix='.tmp',delete=False) as out:
        temporary=Path(out.name)
        try:json.dump(value,out,ensure_ascii=False,separators=(',',':'))
        except Exception:
            out.close();temporary.unlink(missing_ok=True);raise
    try:replace_file(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def read_model(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(value,dict):return None
        if any(not isinstance(value.get(k),dict) for k in ('pairs','plain_pairs','keyed','scoped','script_identities','table_identities')):
            return None
        if any(not isinstance(value.get(k),list) for k in ('numeric','raw_numeric','detail_sources')):return None
        for key in ('pairs','plain_pairs'):
            if any(not isinstance(s,str) or not isinstance(pair,list) or len(pair)!=2 or
                   any(not isinstance(t,str) or not t.strip() for t in pair) for s,pair in value[key].items()):return None
        return value
    except (OSError,ValueError):return None
