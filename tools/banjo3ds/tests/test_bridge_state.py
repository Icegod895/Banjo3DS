"""Bridge lifecycle + sparse query geometry against original actor/mesh code."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
import bridge_reference as reference
import bridge_corpus as corpus
import contact_corpus as contact
import free_b_corpus as free
import test_camera as camera
import test_camera_contact as query_test
import test_free_b as free_test
from test_world_segment import Model,Hit

F=C.c_float
class Mesh(C.Structure):
    _fields_=[('offset',F),('elapsed',F),('applied',C.c_int16),('pending',C.c_uint8),('completed',C.c_uint8)]
class State(C.Structure):
    _fields_=[('mesh',Mesh*3),('initialized',C.c_uint8),('alive',C.c_uint8)]
class View(C.Structure):
    _fields_=[('base',Model),('state',C.POINTER(State))]

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='bridge-production-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[];base=reference.ROOT/'tools/banjo3ds'
        for opt in ('-O0','-O2'):
            path=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*reference.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *[str(base/p) for p in ('camera/camera.c','world_query/segment.c','camera_contact/contact.c',
                'bridge_state/bridge.c','bridge_state/query_segment.c','bridge_state/query_contact.c','bridge_state/query_free_b.c')],'-lm','-o',str(path)],check=True)
            lib=C.CDLL(str(path));mp=C.POINTER(Model);fp=C.POINTER(F);hp=C.POINTER(Hit);sp=C.POINTER(query_test.Scratch)
            lib.bridge_init.argtypes=[C.POINTER(State)]
            lib.bridge_actor_tick.argtypes=[C.POINTER(State),C.c_uint32]
            lib.bridge_mesh_tick.argtypes=[C.POINTER(State),F]
            lib.bridge_model_open.argtypes=[C.POINTER(View),C.c_void_p,C.c_size_t,C.POINTER(State)]
            lib.bridge_component.argtypes=[mp,C.c_uint,C.c_uint];lib.bridge_component.restype=C.c_int16
            for prefix in ('bridge','base'):
                segment=lib.bridge_segment if prefix=='bridge' else lib.bq_segment
                sphere=lib.bridge_sphere if prefix=='bridge' else lib.bc_sphere
                segment.argtypes=[mp,mp,fp,fp,C.c_uint32,hp]
                sphere.argtypes=[mp,mp,fp,F,C.c_uint32,hp]
                for name in ('moving','gated'):
                    getattr(lib,('bridge_' if prefix=='bridge' else 'bc_')+name).argtypes=[mp,mp,fp,fp,F,C.c_int,C.c_uint32,sp,hp]
            lib.bridge_camera_terrain.argtypes=[mp,mp,fp,fp]
            lib.banjo_camera_math_init.argtypes=[C.POINTER(camera.Math)]
            lib.banjo_camera_init.argtypes=[C.POINTER(camera.State),C.POINTER(camera.Math),C.POINTER(camera.Input),fp,fp]
            lib.bridge_free_b_update.argtypes=[C.POINTER(camera.State),C.POINTER(free_test.PostState),C.POINTER(camera.Math),C.POINTER(camera.Zoom),C.POINTER(camera.Trigger),C.c_size_t,C.POINTER(camera.Input),mp,mp,fp,sp,C.POINTER(free.Trace)]
            lib.bridge_free_b_update.restype=C.c_bool
            cls.libs.append(lib);cls.refs.append(reference.library(opt))
        data=camera.reader.read_spiral_camera(camera.ASSET);z=data['zoom']
        cls.zoom=camera.Zoom((F*3)(*z[:3]),(F*3)(*z[3:6]),(F*2)(*z[6:8]),(F*2)(*z[8:10]),*z[10:])
        cls.frozen=json.loads((Path(__file__).parent/'fixtures/bridge_state_golden.json').read_text())

    def initialize(self,lib,ref,mode='raw'):
        data=contact.load(ref,'real');corpus.configure(ref,mode)
        state=State();lib.bridge_init(C.byref(state))
        if corpus.MODES[mode] is not None:
            lib.bridge_actor_tick(C.byref(state),corpus.MODES[mode]);lib.bridge_mesh_tick(C.byref(state),F(1/60))
        buffers=[C.create_string_buffer(p) for _,p in data];views=[View(),View()]
        for view,b in zip(views,buffers):self.assertEqual(lib.bridge_model_open(C.byref(view),b,len(b)-1,C.byref(state)),1)
        return state,views,buffers

    def assert_state(self,lib,ref,s,views):
        floats=(F*6)();ints=(C.c_int32*9)();ref.bridge_ref_state(floats,ints)
        self.assertEqual(struct.pack('>6f',*[x for m in s.mesh for x in (m.offset,m.elapsed)]),struct.pack('>6f',*floats))
        self.assertEqual([x for m in s.mesh for x in (m.pending,m.completed)]+[s.initialized,s.alive],list(ints)[:8])
        for role,view in enumerate(views):
            for vertex in range(view.base.nv):
                xyz=(C.c_int16*3)();ref.bridge_ref_xyz(role,vertex,xyz)
                self.assertEqual([lib.bridge_component(C.byref(view.base),vertex,a) for a in range(3)],list(xyz),(role,vertex))

    def test_original_lifecycle_each_phase_progress_and_reload(self):
        for lib,ref in zip(self.libs,self.refs):
            for initial in (0,corpus.MODES['all_learned']):
                s,views,buffers=self.initialize(lib,ref);self.assert_state(lib,ref,s,views)
                for kind,value in [('actor',initial),('mesh',0),('mesh',0.000001),('mesh',1/60),('mesh',1/60),
                    ('actor',0),('mesh',1/60),('actor',corpus.MODES['all_learned']),('mesh',1/60),
                    ('actor',0),('mesh',1/60)]:
                    getattr(lib,'bridge_'+kind+'_tick')(C.byref(s),value)
                    getattr(ref,'bridge_ref_'+kind)(value)
                    self.assert_state(lib,ref,s,views)
                self.assertEqual(s.alive,0)
                # Actual reload/new map uses fresh immutable base and new actor,
                # not subtraction from previously transformed vertices.
                s,views,buffers=self.initialize(lib,ref,'before_all');self.assert_state(lib,ref,s,views)

    def test_every_required_ability_and_unrelated_bits(self):
        all_bits=corpus.MODES['all_learned'];self.assertEqual(all_bits,0x9db1)
        for lib,ref in zip(self.libs,self.refs):
            for mask in [all_bits,0xffffffff]+[all_bits&~(1<<i) for i in range(32)]:
                s,views,buffers=self.initialize(lib,ref)
                lib.bridge_actor_tick(C.byref(s),mask);ref.bridge_ref_actor(mask)
                lib.bridge_mesh_tick(C.byref(s),1/60);ref.bridge_ref_mesh(1/60)
                self.assert_state(lib,ref,s,views)
                self.assertEqual(bool(s.alive),(mask&all_bits)!=all_bits)

    def test_asset_membership_and_all_occurrences(self):
        self.assertEqual(reference.geometry_manifest(),self.frozen['manifest'])
        self.assertEqual(reference.membership(),{497:list(range(134,138)),498:list(range(150,166)),499:list(range(138,150))})
        self.assertEqual(len(self.frozen['manifest']['occurrences']),20)
        self.assertEqual(self.frozen['manifest']['unique_triangles'],10)
        self.assertEqual({r[0] for r in self.frozen['manifest']['occurrences']},{17,18})

    def test_original_setup_and_update_order_contract(self):
        self.assertEqual(reference.actor_setup(),self.frozen['setup'])
        self.assertEqual([a['position'] for a in self.frozen['setup']['actors']],[[-168,1800,145]])
        # Original normal update schedules actor transforms BEFORE the camera,
        # but applies those pending transforms AFTER that camera query/update.
        from segment_reference import function
        body=function('src/core2/gsworld.c','gsworld_update')
        names=('func_80330FF4();','func_8028E71C();','ncCamera_update();','func_8034C9D4();')
        places=[body.index(n) for n in names];self.assertEqual(places,sorted(places))
        self.assertIn('spawnQueue_func_802C39D4();',function('src/core2/code_A5BC0.c','func_80330FF4'))
        self.assertIn('func_803268B4();',function('src/core2/spawnqueue.c','spawnQueue_func_802C39D4'))
        self.assertIn('marker->actorUpdateFunc(actor);',function('src/core2/code_9E370.c','func_803268B4'))
        for lib,ref in zip(self.libs,self.refs):
            state,views,buffers=self.initialize(lib,ref)
            old=[lib.bridge_component(C.byref(views[1].base),v,1) for v in range(134,166)]
            lib.bridge_actor_tick(C.byref(state),0);ref.bridge_ref_actor(0)
            self.assertEqual([lib.bridge_component(C.byref(views[1].base),v,1) for v in range(134,166)],old)
            lib.bridge_mesh_tick(C.byref(state),1/60);ref.bridge_ref_mesh(1/60)
            after=[lib.bridge_component(C.byref(views[1].base),v,1) for v in range(134,166)]
            self.assertEqual(sum(a!=b for a,b in zip(old,after)),12)
            self.assert_state(lib,ref,state,views)
            for v,b in zip(views,buffers):
                self.assertEqual(v.base.vertices,C.addressof(b)+64)  # borrowed, no copy

    def query(self,lib,views,case,base=False):
        names=dict(bq_segment='bq_segment' if base else 'bridge_segment')
        for n in ('sphere','moving','gated'):names['bc_'+n]=('bc_' if base else 'bridge_')+n
        proxy=types.SimpleNamespace(**{k:getattr(lib,v) for k,v in names.items()})
        return query_test.CameraContactTests.query(self,proxy,[v.base for v in views],case)

    def test_all_queries_bit_exact_and_static_unrelated_geometry(self):
        for lib,ref in zip(self.libs,self.refs):
            for mode in corpus.MODES:
                s,views,buffers=self.initialize(lib,ref,mode);old=[bytes(b) for b in buffers];stream=[];unchanged=0;different=0
                for case in corpus.cases():
                    want=contact.query(ref,case);got=self.query(lib,views,case)
                    self.assertGreaterEqual(want[0],0,case)
                    self.assertEqual(contact.pack_query(got),contact.pack_query(want),(mode,case,got,want))
                    stream.append(contact.pack_query(got))
                    base=self.query(lib,views,case,True)
                    if contact.pack_query(got)==contact.pack_query(base):unchanged+=1
                    else:different+=1
                self.assertEqual(corpus.sha(b''.join(stream)),self.frozen['states'][mode]['queries_sha256'])
                self.assertGreater(unchanged,100)
                if mode!='raw':self.assertGreater(different,0)
                self.assertEqual([bytes(b) for b in buffers],old)
                self.assertEqual([hashlib.sha256(x[:-1]).hexdigest() for x in old],[
                    '59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953',
                    '500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f'])
                self.assert_state(lib,ref,s,views)

    def test_three_bridge_schedules_complete_contact_camera_state(self):
        for lib,ref in zip(self.libs,self.refs):
            for seed in corpus.seeds():
                for mode in corpus.MODES:
                    frames=corpus.run(ref,seed,mode)
                    bridge,views,buffers=self.initialize(lib,ref,mode)
                    s=camera.State();m=camera.Math();lib.banjo_camera_math_init(C.byref(m))
                    lib.banjo_camera_init(C.byref(s),C.byref(m),C.byref(camera.make_input(free.command(seed['player']))),
                        (F*3)(*seed['eye']),(F*3)(*seed['rotation']))
                    post=free_test.PostState();packed=[]
                    for frame,(cmd,want) in enumerate(frames,1):
                        under=F();self.assertGreaterEqual(lib.bridge_camera_terrain(*[C.byref(v.base) for v in views],s.position,C.byref(under)),0)
                        self.assertEqual(bytes(under),bytes(F(cmd['under'])))
                        s.preset=cmd['preset'];t=free.Trace()
                        self.assertTrue(lib.bridge_free_b_update(C.byref(s),C.byref(post),C.byref(m),C.byref(self.zoom),None,0,
                            C.byref(camera.make_input(cmd)),*[C.byref(v.base) for v in views],(F*3)(*cmd['target']),C.byref(query_test.Scratch()),C.byref(t)))
                        v=camera.values(s);got=free.packed(v[:22],v[22:],post.history,post.counter,t)
                        self.assertEqual(got,free.packed(*want),(seed['name'],mode,frame));packed.append(got)
                    self.assertEqual(corpus.sha(b''.join(packed)),self.frozen['schedules'][seed['name']][mode]['sha256'])

    def test_frozen_independent_goldens_O0_O2(self):
        for ref in self.refs:self.assertEqual(corpus.golden(ref),self.frozen)
