"""Multisection #TBL reader using declared offsets and audited pointer fields.

The header word at +4 counts 80-byte section descriptors; it is not a version.
Only the field layouts below emit strings. Record identity excludes explicitly
listed pointers, retains all other bytes, and never uses a row's position.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

from resources import FpacArchive, FormatError, LANGUAGES


@dataclass(frozen=True)
class Schema:
    size: int
    fields: tuple
    pointers: tuple


def spec(size, fields, pointers=()):
    return Schema(size, tuple(fields), tuple(sorted(set(pointers) | {o for _, o in fields})))


SCHEMAS = {
    # Audited across all eight local tables. Non-display resource pointers
    # are masked for identity, but are not emitted as translatable fields.
    'ActiveVoiceTableData': spec(128, [('body',112)], [40]),
    'ChapterParam': spec(88, [('title',24),('heading',32),('ending',40)], [16,48,64,80]),
    'DLCTableData': spec(64, [('name',40),('description',48)], [56]),
    'EventGroupData': spec(16, [('title',8)]),
    'EventSubGroupData': spec(16, [('title',8)]),
    'LookPointTableData': spec(64, [('label',16)], [8,24]),
    'MapJumpAreaData': spec(56, [('name',8)], [16,40,48]),
    'ShopInfo': spec(72, [('name',8)], [24]),
    'FishInfo': spec(224, [('description',208)], [8]),
    'AttrData': spec(24, [('name',16)]),
    'SlotPomInfo': spec(32, [('name',8)]),
    'SlotMonsterInfo': spec(48, [('name',8)]),
    'PokerMessage': spec(32, [('body',8)], [24]),
    'PokerHelp': spec(16, [('body',8)]),
    'PokerRollRate': spec(128, [('short_name',8),('name',16),('description',24)]),
    'PokerRuleText': spec(24, [('body',8)]),
    'BlackJackMessage': spec(32, [('body',8)], [24]),
    'BlackJackHelp': spec(16, [('body',8)]),
    'BlackJackRollRate': spec(128, [('short_name',8),('name',16),('description',24)]),
    'BlackJackRuleText': spec(24, [('body',8)]),
    'RouletteMessage': spec(24, [('body',8)]),
    'RouletteBetRate': spec(40, [('name',8),('description',16)]),
    'RouletteBetExplain': spec(16, [('body',8)]),
    'RouletteRuleText': spec(24, [('body',8)]),
    'ConditionInfoTableData': spec(88, [('name',8)], [80]),
    'OverDriveEffect': spec(104, [('name',96),('common_effect',48),('accuracy',56),
        ('critical',64),('effect_1',72),('effect_2',80),('effect_3',88)]),
    'ItemTableData': spec(256, [('name',224),('description',232)], [8,24,32,216]),
    'ItemKindParam2': spec(16, [('title',8)]),
    'SkillParam': spec(176, [('name',152),('description',168)], [8,24,144,160]),
    'SkillPowerIcon': spec(16, [('label',8)]),
    'SupportAbilityParam': spec(64, [('name',48),('description',56)], [16,32,40]),
    'HelpTitle': spec(24, [('title',8)]),
    'HelpPage': spec(32, [('title',16),('subtitle',24)], [8]),
    'HelpIconList': spec(56, [('title',8),('description',24),('detail',40)], [48]),
    'HelpController': spec(16, [('label',8)]),
    'HelpOverlayIcon': spec(40, [('label',8)]),
    'RealTimeHelpTableData': spec(24, [('label',8)]),
    'TipsTableData': spec(56, [('title',40),('body',48)], [8,16,24]),
    'NoteMainCategory': spec(24, [('title',8),('page',16)]),
    'NoteMainPartnerInfo': spec(24, [('name',0)], [8]),
    'NoteMainAffiliation': spec(16, [('title',0)]),
    'NoteMainHistory': spec(8, [('body',0)]),
    'NoteBattleCategory': spec(24, [('title',8),('subtitle',16)]),
    'NoteCookCategory': spec(32, [('title',8),('heading',16),('subtitle',24)]),
    'NoteHelpCategory': spec(32, [('title',8),('subtitle',16),('heading',24)]),
    'NoteFishingCategory': spec(32, [('title',8),('heading',16),('subtitle',24)]),
    'NoteMonsRecordData': spec(48, [('body',40)], [0,16,32]),
    'NoteCookItem': spec(56, [('description',32)], [16,40]),
    'QuestRank': spec(24, [('rank',8)]),
    'QuestRankBefore': spec(16, [('rank',8)]),
    'QuestTitle': spec(104, [('title',8),('client',16),('comment',88)], [32,80]),
    'QuestText': spec(56, [('body',8),('detail',48)], [16,32]),
    'NaviText': spec(56, [('title',8),('detail',16)], [24,40]),
    'ATBonusParam': spec(40, [('label',32)], [8]),
    'TacticalBonus': spec(16, [('label',8)]),
    'ConditionHelpData': spec(40, [('format',8),('condition',16),('rate',24),('next_condition',32)]),
    'SkillEffectTypeHelpData': spec(24, [('label',8),('suffix',16)]),
    'SkillEffectHelpData': spec(88, [('name',8),('stat',32),('format',40),('turns',72),('value',80)], [16,48,56]),
    'AttrTypeHelpData': spec(24, [('label',8)]),
    'SkillTypeHelpData': spec(24, [('label',8),('suffix',16)]),
    'SkillRangeHelpData': spec(40, [('label',8),('short_label',24)], [32]),
    'ItemKindHelpData': spec(32, [('description',8),('label',24)]),
    'SkillItemStatusData': spec(48, [('format',8),('name',16),('value',24)], [40]),
    'SkillTextArrayData': spec(24, [('format',8)], [16]),
    'AchievementTableData': spec(96, [('title',72),('description',80),('counter',88)], [24,64]),
    'AchievementCategoryData': spec(16, [('title',8)]),
    'PlayRecordData': spec(40, [('title',16),('description',24),('condition',32)], [8]),
    'BooksTitle': spec(24, [('title',8)]),
    'BooksText': spec(24, [('body',8)], [16]),
    'BooksCategory': spec(24, [('title',8),('subtitle',16)]),
    'NameTableData': spec(104, [('name',8)], [16,24,32,48,64,80,88,96]),
    'PlaceTableData': spec(168, [('name',96),('subtitle',104)], [8,16,24,48,64,88,120]),
    'StatusParam': spec(424, [('name',408)], [0,8,24,32,40,48,56,64,152,416]),
    'ViewerMainList': spec(24, [('title',8)]),
    'ViewerSystemList': spec(16, [('title',8)]),
    'ViewerMapList': spec(16, [('title',8)]),
    'ViewerCharaSelectList': spec(24, [('title',8),('description',16)]),
    'ViewerCharaEquipList': spec(24, [('title',8)]),
    'ViewerShotList': spec(16, [('title',8)]),
    'ViewerMapData': spec(80, [('name',16)], [8,40,56]),
    'ViewerEnvList': spec(16, [('title',8)]),
    'ViewerBGMList': spec(24, [('title',8)]),
    'ViewerCharaList': spec(64, [('name',24)], [8,16,40,48]),
    'ViewerCostumeList': spec(32, [('name',8)], [24]),
    'ViewerAttachList': spec(32, [('name',8)]),
    'ViewerHairList': spec(24, [('name',8)]),
    'ViewerWeaponList': spec(24, [('name',8)]),
    'ViewerFaceList': spec(48, [('name',8)], [16,24,40]),
    'ViewerMouseList': spec(24, [('name',8)], [16]),
    'ViewerCheekList': spec(24, [('name',8)], [16]),
    'ViewerEyeLineList': spec(24, [('name',8)], [16]),
    'ViewerNeckDirList': spec(24, [('name',8)]),
    'ViewerMotionList': spec(40, [('name',8)], [16,24,32]),
}


def sections(data):
    if len(data)<88 or data[:4]!=b'#TBL':
        raise FormatError('missing #TBL descriptor header')
    count=struct.unpack_from('<I',data,4)[0]
    if not 1<=count<=1024 or 8+80*count>len(data):
        raise FormatError('invalid section descriptor count')
    result=[]
    for i in range(count):
        at=8+i*80
        try: kind=data[at:at+64].split(b'\0',1)[0].decode('ascii')
        except UnicodeDecodeError as exc: raise FormatError('non-ASCII section name') from exc
        start,size,rows=struct.unpack_from('<III',data,at+68)
        if not kind or size==0 or start<8+80*count or start+size*rows>len(data):
            raise FormatError('section data outside file')
        result.append((kind,start,size,rows))
    occupied=sorted((s,s+z*c) for _,s,z,c in result if c)
    if any(a[1]>b[0] for a,b in zip(occupied,occupied[1:])):
        raise FormatError('overlapping section records')
    return result


def schema_for(path,kind):
    if path=='table/t_quest_fc.tbl':
        if kind=='QuestText':return spec(32,[('body',8),('detail',24)])
        if kind=='NoteMainHistory':return spec(16,[('body',0)])
    return SCHEMAS[kind]


def record_identity(data, at, kind, schema, text_floor):
    row=bytearray(data[at:at+schema.size]);extra=b''
    if kind=='NaviText':
        # These pointers refer to uint16 quest-flag arrays, not text. Removing
        # them alone collapses every objective in a chapter into one identity.
        for pointer_at,count_at in ((24,32),(40,48)):
            pointer,count=struct.unpack_from('<Q',row,pointer_at)[0],struct.unpack_from('<Q',row,count_at)[0]
            if count>4096 or (count and not text_floor<=pointer<=len(data)-count*2):
                raise FormatError('navigation condition array outside pool')
            extra+=struct.pack('<Q',count)+data[pointer:pointer+count*2]
    for offset in schema.pointers:row[offset:offset+8]=b'\0'*8
    return 'sha256:'+hashlib.sha256(row+extra).hexdigest()


def read_section(data, section, schema, text_floor):
    kind,start,size,count=section
    if size!=schema.size: raise FormatError('section stride mismatch: '+kind)
    result={}
    for i in range(count):
        at=start+i*size
        row=bytearray(data[at:at+size]); fields={}
        for name,offset in schema.fields:
            pointer=struct.unpack_from('<Q',row,offset)[0]
            if not pointer: continue
            if not text_floor<=pointer<len(data): raise FormatError('text pointer outside string pool: '+kind)
            end=data.find(b'\0',pointer)
            if end<0: raise FormatError('unterminated string: '+kind)
            try: value=data[pointer:end].decode('utf-8')
            except UnicodeDecodeError as exc: raise FormatError('invalid UTF-8: '+kind) from exc
            if any(ord(c)<32 and c not in '\n\r\t' for c in value):
                raise FormatError('binary data in text field: '+kind)
            if value: fields[name]=value
        identity=record_identity(data,at,kind,schema,text_floor)
        result.setdefault(identity,[]).append(fields)
    return result


def build_menu_entries(game_dir):
    from tables import _TABLE_ARCHIVES, _logical_tables, _text_rows, _coalesce_duplicate_groups, _emit_aligned
    audit={'version':2,'languages':list(LANGUAGES),'counters':Counter(),'diagnostics':[],
           'recognized_tables':[],'unrecognized_tables':[],'unsupported_tables':[],
           'coverage':[],'ambiguous_duplicate_groups':[]}
    archives={}; entries=[]
    try:
        for language,filename in _TABLE_ARCHIVES.items():
            archive_path=Path(game_dir)/'pac/steam'/filename
            if archive_path.exists():archives[language]=FpacArchive(archive_path)
            else:audit['diagnostics'].append({'language':language,'reason':'missing table archive'})
        if not archives:raise FileNotFoundError('No table archives found')
        paths={l:_logical_tables(a) for l,a in archives.items()}
        for path in sorted(set().union(*(p.keys() for p in paths.values()))):
            files={l:a.read(paths[l][path]) for l,a in archives.items() if path in paths[l]}
            headers={}
            for l,data in files.items():
                try: headers[l]=sections(data)
                except FormatError as exc:
                    audit['diagnostics'].append({'path':path,'language':l,'reason':str(exc)})
            if not headers:
                audit['unsupported_tables'].append({'path':path,'reason':'invalid section descriptors'})
                continue
            section_types={}
            for rows in headers.values():
                for index,section in enumerate(rows):
                    occurrence=sum(s[0]==section[0] for s in rows[:index])
                    section_types.setdefault((section[0],occurrence),(index,section))
            for (kind,occurrence),(index,section) in section_types.items():
                kind=section[0]
                if kind!='TextTableData' and kind not in SCHEMAS:
                    audit['unrecognized_tables'].append({'path':path,'class':kind});continue
                # Duplicate section kinds (difficulty variants) are distinct sections.
                parsed={}
                for l,data in files.items():
                    matching=[s for s in headers.get(l,[]) if s[0]==kind]
                    if occurrence>=len(matching): continue
                    try:
                        if kind=='TextTableData': parsed[l]=_text_rows(data)
                        else:
                            floor=max(s+z*c for _,s,z,c in headers[l])
                            parsed[l]=read_section(data,matching[occurrence],schema_for(path,kind),floor)
                    except FormatError as exc:
                        audit['diagnostics'].append({'path':path,'class':kind,'language':l,'reason':str(exc)})
                if not parsed:
                    audit['unsupported_tables'].append({'path':path,'class':kind});continue
                key_path=path if index==0 else path+'/'+kind+(f'/{occurrence}' if occurrence else '')
                before=len(entries)
                if kind=='TextTableData': _emit_aligned(entries,parsed,path=key_path,field=None,audit=audit)
                else:
                    parsed=_coalesce_duplicate_groups(parsed,audit,path=key_path,kind=kind)
                    for field,_ in schema_for(path,kind).fields:
                        _emit_aligned(entries,parsed,path=key_path,field=field,audit=audit)
                audit['recognized_tables'].append({'path':path,'class':kind})
                audit['coverage'].append({'path':key_path,'class':kind,
                    'records_by_language':{l:len(r) for l,r in parsed.items()},'entries_emitted':len(entries)-before})
        audit['counters']=dict(audit['counters'])
        return entries,audit
    finally:
        for archive in archives.values(): archive.close()
