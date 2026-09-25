import struct
import unittest
from unittest.mock import patch
from runtime_identity import compile_script_identities, script_signature


class FakeArchive:
    entries = {'script_sc/scena/test.dat': (0, 512)}
    data = None
    def __init__(self, *args):pass
    def read(self, *args):return self.data
    def close(self):pass


class RuntimeIdentityTests(unittest.TestCase):
    def test_identical_script_bytes_with_conflicting_localizations_are_quarantined(self):
        _,entries=self.fixture()
        entries += [{'key':e['key'].replace('/test.dat/','/clone.dat/'),
                     'texts':{**e['texts'],'ja':'Different owner'}} for e in entries]
        with patch('runtime_identity.FpacArchive',FakeArchive),patch.object(FakeArchive,'entries',
            {'script_sc/scena/test.dat':(0,512),'script_sc/scena/clone.dat':(0,512)}):
            model=compile_script_identities('unused',entries,'zh-Hans','ja','zh-Hans')
        self.assertEqual(model['stats']['conflicting_function_identities'],1)
        self.assertTrue(all('Talk' not in script['functions'] for group in model['scripts'].values() for script in group))
        self.assertEqual(model['pointer_models'],{})

    def fixture(self, dynamic=False):
        data=bytearray(512);struct.pack_into('<4sIIIII',data,0,b'#scp',24,1,0,0,0)
        struct.pack_into('<II',data,40,2,64);struct.pack_into('<I',data,52,0xc0000000+220)
        data[220:225]=b'Talk\0'
        for i,offset in enumerate((256,280)):
            struct.pack_into('<IHHI',data,64+i*12,0xffffffff,3,4,88+i*40)
            for j,value in enumerate((0x40000005,0x40000000,0x40000001,0xc0000000+offset)):
                struct.pack_into('<II',data,88+i*40+j*8,0 if dynamic and j==2 else value,2 if dynamic and j==2 else 0)
            value='好。'.encode()+b'\0';data[offset:offset+len(value)]=value
        entries=[{'key':f'script/scena/test.dat/Talk/called/{i}/arg/3',
                  'texts':{'zh-Hans':'好。','ja':t}} for i,t in enumerate(('はい。','よし。'))]
        FakeArchive.data=bytes(data)
        return bytes(data),entries

    def test_source_equality_does_not_merge_distinct_script_offsets(self):
        data,entries=self.fixture()
        with patch('runtime_identity.FpacArchive',FakeArchive):
            result=compile_script_identities('unused',entries,'zh-Hans','ja','zh-Hans')
        fn=result['scripts'][script_signature(data)][0]['functions']['Talk']
        self.assertNotIn('好。',fn['model']['pairs'])
        self.assertEqual(fn['calls'][f'{0x40000001},{0xc0000000+256}']['model']['pairs']['好。'],('好。','はい。'))
        self.assertEqual(fn['calls'][f'{0x40000001},{0xc0000000+280}']['model']['pairs']['好。'],('好。','よし。'))

    def test_dynamic_arguments_only_wildcard_the_unresolved_value(self):
        data,entries=self.fixture(True)
        with patch('runtime_identity.FpacArchive',FakeArchive):
            result=compile_script_identities('unused',entries,'zh-Hans','ja','zh-Hans')
        fn=result['scripts'][script_signature(data)][0]['functions']['Talk']
        self.assertEqual(set(fn['calls']),{f'?,{0xc0000000+256}',f'?,{0xc0000000+280}'})
        self.assertEqual(result['stats']['dynamic_calls'],2)

    def test_empty_localized_source_is_not_a_pointer_translation(self):
        data,entries=self.fixture();data=bytearray(data)
        for i,offset in enumerate((256,280)):
            data[offset]=0;entries[i]['texts']['zh-Hans']=''
            entries[i]['texts']['en']='Empty source '+str(i)
        FakeArchive.data=bytes(data)
        with patch('runtime_identity.FpacArchive',FakeArchive):
            result=compile_script_identities('unused',entries,'en','ja','zh-Hans')
        self.assertNotIn('',result['pointers'])

    def test_script_identity_bounds(self):
        for data in (b'',b'#scp'+bytes(20),b'bad!'+bytes(100)):
            with self.assertRaises(ValueError):script_signature(data)
