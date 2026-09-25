"""Check the live native geometry captured by layout_probe.py."""
import json
from pathlib import Path

rows=[m['payload'] for m in json.loads(Path('generated/layout-probe.json').read_text(encoding='utf-8')) if m.get('type')=='send']
rubies=[r for r in rows if r.get('call')=='0x587229']
assert rubies,'No live ruby placement captured'
assert all(max(r['scale'])<=0.301 for r in rubies),'Secondary glyph size still exceeds 14.4/48'
description=[r for r in rubies if '要害' in r['text']]
assert description,'Two-line skill description not captured'
# Each root measurement/render pass contains three rubies: two on the effect
# line and one on the prose line. Check the final (drawing) pass's row pitch.
last=description[-3:]
pitch=max(r['xy'][1] for r in last)-min(r['xy'][1] for r in last)
assert pitch>=50,f'Second-line annotation is still too close: pitch={pitch}'
print('PASS: secondary size <=14.4, two-line ruby pitch',pitch)
