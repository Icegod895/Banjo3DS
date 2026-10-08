"""M4.10B: original grouped selector + full original camera/contact vs production."""
import ctypes as C
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zones_reference as ref
import zones_corpus as corpus
import free_b_corpus as free
import contact_corpus as contact
import test_camera as camera
from test_free_b import PostState
from test_camera_contact import Scratch
from test_world_segment import Model
sys.path.insert(0,str(ref.ROOT/'tools/banjo3ds'))
from camera_zones.setup import read_zones
F=C.c_float
I=C.c_int
class Group(C.Structure):_fields_=[('first',I),('count',I),('node',I)]
class Node(C.Structure):_fields_=[('type',I),('profile',I),('zoom',camera.Zoom)]
class Data(C.Structure):_fields_=[('triggers',C.POINTER(camera.Trigger)),('groups',C.POINTER(Group)),('nodes',C.POINTER(Node)),('count',C.c_size_t),('node_count',C.c_size_t)]
class Selection(C.Structure):_fields_=[('group',I),('local',I),('profile',I),('last_zoom',I),('enabled',C.c_uint8*80)]

def production_data():
    data=read_zones(camera.ASSET);ts=[];gs=[]
    for group in data['groups']:
        gs.append(Group(len(ts),len(group),group[0]['node']))
        ts.extend(camera.Trigger((I*3)(*t['position']),t['radius'],t['node'],t['mask']) for t in group)
    nodes=(Node*43)()
    for i,n in data['nodes'].items():
        nodes[i].type=n['type'];f=n['fields']
        if n['type']==4:nodes[i].profile=f[1]
        elif n['type']==3:nodes[i].zoom=camera.Zoom((F*3)(*f[1]),(F*3)(*f[4]),(F*2)(*f[2]),(F*2)(*f[3]),*f[6],f[5])
    triggers=(camera.Trigger*len(ts))(*ts);groups=(Group*len(gs))(*gs)
    return Data(triggers,groups,nodes,len(gs),43),(triggers,groups,nodes),data

class CameraZonesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='zones-test-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[];base=ref.ROOT/'tools/banjo3ds'
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*camera.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *[str(base/p) for p in ('camera/camera.c','camera_contact/contact.c','camera_contact/free_b.c','world_query/segment.c','camera_zones/zones.c')],'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));fp=C.POINTER(F)
            lib.bz_init.argtypes=[C.POINTER(Selection)]
            lib.bz_select.argtypes=[C.POINTER(Selection),C.POINTER(Data),fp];lib.bz_select.restype=I
            lib.bz_enable.argtypes=[C.POINTER(Selection),I,C.c_bool];lib.bz_enable.restype=C.c_bool
            lib.banjo_camera_math_init.argtypes=[C.POINTER(camera.Math)]
            lib.banjo_camera_init.argtypes=[C.POINTER(camera.State),C.POINTER(camera.Math),C.POINTER(camera.Input),fp,fp]
            lib.bq_open.argtypes=[C.POINTER(Model),C.c_void_p,C.c_size_t]
            lib.bz_update.argtypes=[C.POINTER(Selection),C.POINTER(camera.State),C.POINTER(PostState),C.POINTER(camera.Math),
                C.POINTER(Data),C.POINTER(camera.Input),C.c_bool,C.POINTER(Model),C.POINTER(Model),fp,C.POINTER(Scratch),C.POINTER(free.Trace)]
            lib.bz_update.restype=C.c_bool
            cls.libs.append(lib);cls.refs.append(ref.library(opt))
        cls.data,cls.keep,cls.raw=production_data()

    def test_original_group_build_and_node_payloads(self):
        records,nodes,enemy=ref.asset();self.assertEqual(len(records),150);self.assertEqual(len({r[5] for r in records}),26)
        self.assertEqual(len(self.raw['groups']),27);self.assertEqual(enemy,self.raw['enemy_count'])
        for original in self.refs:
            ref.configure(original);buf=(I*2000)();n=original.zone_groups(buf);want=[]
            for g in self.raw['groups']:
                want.extend((g[0]['node'],len(g)))
                for t in g:want.extend((*t['position'],t['radius'],t['mask']))
            self.assertEqual(want,list(buf[:n]))
        for n,(kind,fields) in nodes.items():
            self.assertEqual(self.raw['nodes'][n]['type'],kind)
            for tag,v in fields.items():self.assertEqual(self.raw['nodes'][n]['fields'][tag],v if len(v)>1 else v[0])
            if kind==3:self.assertEqual(fields[5][0]&1,0)
        self.assertEqual([t['offset'] for t in self.raw['groups'][17]],[0x11ba,0xc96,0x11fd,0x11e9])

    def test_membership_boundaries_cache_enablebits_and_truncation(self):
        for lib,original in zip(self.libs,self.refs):
            ref.configure(original);s=Selection();lib.bz_init(C.byref(s))
            for name in ('D_8037C010','D_8037C014'):I.in_dll(original,name).value=-1
            points=[]
            for g in self.raw['groups']:
                for t in g:
                    x,y,z=t['position'];r=t['radius']
                    points.extend((x+dx,y+dy,z) for dx in (0,r-.01,r,r+.01,-r-.01,-r,-r+.01) for dy in (-150.01,-150,149.99,150))
            points+=[(-820,400,-75),(-737,445,-316),(-640,400,-531),(-737,445,-316)]
            for i,p in enumerate(points):
                if i%47==0:
                    node=(i//47)%43;enabled=(i//47)%2
                    lib.bz_enable(C.byref(s),node,enabled);original.zone_enable(node,enabled)
                v=(F*3)(*p);got=lib.bz_select(C.byref(s),C.byref(self.data),v);want=original.zone_select(v)
                self.assertEqual((got,s.group,s.local),(want,I.in_dll(original,'D_8037C010').value,I.in_dll(original,'D_8037C014').value),(i,p))

    def test_full_camera_contact_schedules_bit_exact(self):
        for lib,original in zip(self.libs,self.refs):
            for scenario in corpus.schedules():
                p,eye,rotation=corpus.initialize(original,scenario)
                state=camera.State();math=camera.Math();sel=Selection();lib.bz_init(C.byref(sel));lib.banjo_camera_math_init(C.byref(math))
                initial=camera.make_input(scenario['commands'][0]);lib.banjo_camera_init(C.byref(state),C.byref(math),C.byref(initial),(F*3)(*eye),(F*3)(*rotation))
                post=PostState(scenario['counter'],scenario['history']);scratch=Scratch()
                buffers=[C.create_string_buffer(p) for _,p in contact.world('real')];models=[Model(),Model()]
                for m,b in zip(models,buffers):self.assertEqual(lib.bq_open(C.byref(m),b,len(b)-1),1)
                for i,command in enumerate(scenario['commands']):
                    want,result=corpus.snapshot(original,command);t=free.Trace();state.preset=command['preset']
                    self.assertTrue(lib.bz_update(C.byref(sel),C.byref(state),C.byref(post),C.byref(math),C.byref(self.data),
                        C.byref(camera.make_input(command)),False,*[C.byref(m) for m in models],(F*3)(*command['target']),C.byref(scratch),C.byref(t)))
                    v=camera.values(state)
                    got=free.packed(v[:22],v[22:],post.history,post.counter,t)+struct.pack('>4i',sel.group,sel.local,sel.profile,sel.last_zoom)
                    self.assertEqual(got,want,(scenario['name'],i,v,result[:4],corpus.select_state(original)))
                    if state.state==17:self.assertEqual(t.contact.changed,0)

    def test_frozen_original_goldens_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_zones_golden.json').read_text())
        for opt in ('-O0','-O2'):self.assertEqual(corpus.golden(opt),frozen)

    def test_required_transition_and_history_observations(self):
        for original in self.refs:
            for scenario in corpus.schedules()[:6]:
                corpus.initialize(original,scenario);frames=[]
                for c in scenario['commands']:
                    _,result=corpus.snapshot(original,c);frames.append(result)
                name=scenario['name']
                if name=='spawn-jump-landing':
                    self.assertTrue(all(r[1][2]==32 for r in frames[:60]))
                    self.assertEqual(frames[60][1][:3],[2,17,-1])
                    self.assertEqual(frames[61][1][:3],[2,11,-1])
                    self.assertEqual(frames[90][1][:3],[9,17,32])
                if name=='opa-wall-node11':
                    self.assertTrue(all(r[1][:3]==[9,17,11] for r in frames))
                    g,l,_,_=corpus.select_state(original)
                    self.assertEqual(self.raw['groups'][g][l]['offset'],0x1542)
                if name=='zoom-replacement-exit-history':
                    self.assertEqual(frames[19][1][:3],[9,17,32])
                    self.assertEqual(frames[20][1][:3],[9,17,11])
                    self.assertTrue(all(r[2:4]==(-1.,3) for r in frames[:41]))
                    self.assertEqual(frames[40][1][:3],[2,17,-1])
                    self.assertEqual(frames[41][1][:3],[2,11,-1])
                    self.assertNotEqual(frames[20][0][12:18],[0]*6)
                if name=='profile1-entry-exit':self.assertEqual(frames[0][1][:3],[2,11,38])
                if name=='overlap-retain-22':self.assertTrue(all(r[1][2]==22 for r in frames[:15]))
                if name=='overlap-retain-21':self.assertTrue(all(r[1][2]==21 for r in frames[:15]))

    def test_force_refresh_and_new_selection_instance_are_separate_from_camera_history(self):
        for lib,original in zip(self.libs,self.refs):
            scenario=corpus.schedules()[0];p,eye,rotation=corpus.initialize(original,scenario)
            s=camera.State();m=camera.Math();sel=Selection();lib.bz_init(C.byref(sel));lib.banjo_camera_math_init(C.byref(m))
            lib.banjo_camera_init(C.byref(s),C.byref(m),C.byref(camera.make_input(scenario['commands'][0])),(F*3)(*eye),(F*3)(*rotation))
            post=PostState(3,-1);original.composition_seed(F(-1),3)
            buffers=[C.create_string_buffer(p) for _,p in contact.world('real')];models=[Model(),Model()]
            for model,b in zip(models,buffers):lib.bq_open(C.byref(model),b,len(b)-1)
            for i,(p,stable,force) in enumerate((([0,1800,0],True,False),([1875,-9,-3262],False,False),
                                               ([1875,-9,-3262],False,True))):
                command=free.command(p,stable=stable,target=[p[0],p[1]+80,p[2]]);C.c_uint8.in_dll(original,'D_8037C02C').value=force
                want,result=corpus.snapshot(original,command);t=free.Trace()
                self.assertTrue(lib.bz_update(C.byref(sel),C.byref(s),C.byref(post),C.byref(m),C.byref(self.data),
                    C.byref(camera.make_input(command)),force,*[C.byref(v) for v in models],(F*3)(*command['target']),C.byref(Scratch()),C.byref(t)))
                v=camera.values(s)
                self.assertEqual(free.packed(v[:22],v[22:],post.history,post.counter,t)+struct.pack('>4i',sel.group,sel.local,sel.profile,sel.last_zoom),want)
                self.assertEqual(s.node,11 if force else 32)
            before=(bytes(s),bytes(post));lib.bz_init(C.byref(sel))
            self.assertEqual(before,(bytes(s),bytes(post)))
            self.assertEqual((sel.group,sel.local,sel.profile,sel.last_zoom),(-1,-1,0,-1))
