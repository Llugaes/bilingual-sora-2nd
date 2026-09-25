"""Change only the local experiment policy, never call into the game directly."""
import argparse
import json
from pathlib import Path
from native_config import read_config,write_config

parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['observe','replay','secondary','bilingual','annotation','language-toggle','language-hold','off','stop'])
parser.add_argument('--captured-description',action='store_true')
parser.add_argument('--item-name',action='store_true')
parser.add_argument('--all-item-names',action='store_true')
parser.add_argument('--all-menu-text',action='store_true')
parser.add_argument('--all-text',action='store_true')
parser.add_argument('--annotation-scale',type=float,default=0.9)
args=parser.parse_args()
root=Path(__file__).resolve().parent/'generated'
path=root/'native-control.json'
config=read_config(path)
if args.item_name:
    config['scope']='selected'
    config['sources']=['回复药']
if args.all_item_names:
    config['scope']='selected'
    table=json.loads((root/'table-next.json').read_text(encoding='utf-8'))
    config['sources']=sorted({text for entry in table['entries']
        if entry['key'].startswith('table/t_item.tbl/') and entry['key'].endswith('/name')
        for text in entry['texts'].values()})
if args.all_menu_text:
    config['scope']='menu'
    config['sources']=[]
if args.all_text:
    config['scope']='all';config['sources']=[]
if args.captured_description:
    rows=[json.loads(line).get('payload',{}) for line in (root/'probe-ui.jsonl').read_text(encoding='utf-8').splitlines()]
    matches=[r['text'] for r in rows if r.get('kind')=='setter' and r.get('caller')=='0x137e08']
    if not matches:
        raise SystemExit('No captured item description')
    config['sources']=[matches[-1]]
config.update(enabled=args.action in ('secondary','bilingual','annotation','language-toggle','language-hold'),replay=args.action=='replay',
              stop=args.action=='stop',mode=args.action if args.action in ('secondary','annotation') else 'bilingual')
config['interaction']=args.action.replace('-','_') if args.action in ('annotation','language-toggle','language-hold') else None
config['annotation_scale']=args.annotation_scale
write_config(config,path)
print(args.action,'scope:',config.get('scope','selected'),'selected source strings:',len(config.get('sources',[])))
