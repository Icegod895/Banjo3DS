"""Per-candidate persistent floor state vs compiled original, full snapshots."""
import ctypes as C
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import floor_state_reference as ref
import floor_state_corpus as corpus
from segment_reference import ROOT, FLAGS
from segment_corpus import synthetic
from world_query_reference import original
from test_world_segment import Model
F=C.c_float
class Triangle(C.Structure):_fields_=[('v',C.c_int16*3),('surface',C.c_int16),('flags',C.c_uint32)]
class State(C.Structure):
    _fields_=[('model',C.c_uint32),('floor_tri',Triangle),('special_tri',Triangle),
       ('candidate',F*3),('previous',F*3),('normal',F*3),('height',F),('special',F),('upper',F),
       ('flags',C.c_uint32),('surface',C.c_int16),('pad52',C.c_int16),('mask',C.c_uint32),
       *[(n,C.c_uint8) for n in ('valid','special_valid','old_valid','old_special_valid','grace','countdown','mode','pad5f')],
       ('floor_ref',C.c_int32*3),('special_ref',C.c_int32*3)]

class FloorStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='floor-tests-');cls.addClassCleanup(cls.tmp.cleanup);cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *[str(ROOT/'tools/banjo3ds/world_query'/f) for f in ('segment.c','floor_state.c')],'-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out));lib.bq_open.argtypes=[C.POINTER(Model),C.c_void_p,C.c_size_t]
            lib.bq_floor_init.argtypes=[C.POINTER(State)];lib.bq_floor_reinit.argtypes=[C.POINTER(State)]
            lib.bq_floor_update.argtypes=[C.POINTER(State),C.POINTER(Model),C.POINTER(Model),C.POINTER(F),F,C.c_uint32,C.c_uint]
            lib.bq_camera_terrain.argtypes=[C.POINTER(Model),C.POINTER(Model),C.POINTER(F),C.POINTER(F)]
            cls.libs.append(lib)
    def models(self,lib,scene=None):
        data=[original(a,r)['packet'] for r,a in enumerate((0x14cf,0x14d0))] if scene is None else [synthetic(r,*s)[1] for r,s in enumerate(scene)]
        buffers=[C.create_string_buffer(b) for b in data];models=[Model(),Model()]
        for m,b in zip(models,buffers):self.assertEqual(lib.bq_open(C.byref(m),b,len(b)-1),1)
        return models,buffers
    def test_original_full_state_goldens_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/floor_state_golden.json').read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            oracle=ref.library(opt);self.assertEqual(corpus.golden(oracle),frozen)
            for name,(scene,rows) in corpus.cases().items():
                states,_=corpus.run(oracle,scene,rows);models,buffers=self.models(lib,scene)
                s=State();lib.bq_floor_init(C.byref(s));oracle.floor_ref_init();self.assertEqual(bytes(s),ref.snapshot(oracle))
                for i,((p,parity,reinit),want) in enumerate(zip(rows,states)):
                    if reinit:lib.bq_floor_reinit(C.byref(s))
                    self.assertEqual(lib.bq_floor_update(C.byref(s),*[C.byref(m) for m in models],(F*3)(*p),56,0x400000,parity),1,(name,i))
                    self.assertEqual(bytes(s),want,(opt,name,i,[(j,a,b) for j,(a,b) in enumerate(zip(bytes(s),want)) if a!=b]))
    def test_layout_cadence_no_hit_reinit_and_atomic_error(self):
        self.assertEqual(C.sizeof(State),120);self.assertEqual(State.height.offset,0x40)
        lib=self.libs[1];models,buffers=self.models(lib);s=State();lib.bq_floor_init(C.byref(s))
        for i in range(5):
            self.assertEqual(lib.bq_floor_update(C.byref(s),*[C.byref(m) for m in models],(F*3)(0,1800,0),56,0x400000,0),1)
            self.assertEqual(s.countdown,4-i);self.assertEqual(s.height,1800)
        before=bytes(s);lib.bq_floor_reinit(C.byref(s));self.assertEqual(bytes(s)[:93],before[:93]);self.assertEqual((s.countdown,s.mode),(5,1))
        before=bytes(s);self.assertEqual(lib.bq_floor_update(C.byref(s),*[C.byref(m) for m in models],(F*3)(float('nan'),0,0),56,0x400000,0),-1);self.assertEqual(bytes(s),before)
        lib.bq_floor_update(C.byref(s),*[C.byref(m) for m in models],(F*3)(9000,1800,9000),56,0x400000,0)
        self.assertEqual((s.height,s.valid,s.model),(-9000,1,0))
    def test_query_ranges_split_overlap_and_state4_parity(self):
        oracle=ref.library('-O2');cases=corpus.cases()
        _,qs=corpus.run(oracle,*cases['split_far_floor'])
        self.assertIn([-100.,7000.], [q[3:5] for q in qs[0]])
        ranges=[q[3:5] for q in qs[-1]];self.assertIn([56.,-444.],ranges);self.assertIn([-443.,-1300.],ranges)
        states,qs=corpus.run(oracle,*cases['state4_parity_grace'])
        self.assertEqual({s[94] for s in states[:14]},{4})
        self.assertEqual([q[3:5] for q in qs[6]],[[170.,30.]])
        self.assertEqual([q[3:5] for q in qs[7]],[[60.,-390.]])
        self.assertEqual(states[14][92],0) # missed special gets exactly one grace
    def test_reference_state3_retains_previous_height_before_classifier(self):
        s,q=corpus.run(ref.library('-O2'),*corpus.cases()['retained_state3_height'])
        import struct
        self.assertEqual(struct.unpack_from('=f',s[8],64)[0],0)
        self.assertEqual(s[8][88],0);self.assertEqual(s[8][94],2)

    def test_camera_world_inputs_on_observed_runtime_candidates(self):
        import floor_camera_inputs
        results=[]
        for opt,lib in zip(('-O0','-O2'),self.libs):
            models,buffers=self.models(lib)
            results.append(floor_camera_inputs.compare(self,lib,models,opt))
        self.assertEqual(results[0],results[1])
        frozen=json.loads((Path(__file__).parent/'fixtures/floor_camera_inputs_golden.json').read_text())
        self.assertEqual(json.loads(json.dumps(results[0])),frozen)
