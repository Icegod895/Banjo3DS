"""Bounded scheduler vs original floor; live viewer is not linked to bridge."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import floor_bridge_reference as ref
import floor_state_reference as original_floor
from floor_state_corpus import canonical
from segment_reference import ROOT,FLAGS,load_real
import test_floor_state as floors
State=floors.State
from test_world_segment import Model
F=C.c_float
class Bridge(C.Structure):
    _fields_=[('floor',State),('frame',C.c_uint32),('ordinal',C.c_uint32),('seed',C.c_uint8),
              ('active',C.c_uint8),('initialized',C.c_uint8),('reserved',C.c_uint8)]

class FloorBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='floor-bridge-test-');cls.addClassCleanup(cls.tmp.cleanup);cls.libs=[]
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
              *[str(ROOT/'tools/banjo3ds/world_query'/f) for f in ('floor_bridge.c','floor_state.c','segment.c')],'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));bp=C.POINTER(Bridge);mp=C.POINTER(Model)
            for name,args in [('init',[bp,C.c_uint]),('begin',[bp]),('end',[bp]),('reinit',[bp]),('parity',[bp]),
                ('candidate',[bp,mp,mp,C.POINTER(F),C.c_uint32])]:getattr(lib,'bq_bridge_'+name).argtypes=args
            lib.bq_open.argtypes=[mp,C.c_void_p,C.c_size_t]
            lib.bq_camera_terrain.argtypes=[mp,mp,C.POINTER(F),C.POINTER(F)]
            cls.libs.append(lib)
    models=floors.FloorStateTests.models
    def evaluate(self,lib,models,rows,opt):
        oracle=original_floor.library(opt);load_real(oracle);oracle.floor_ref_init();s=Bridge()
        self.assertEqual(lib.bq_bridge_init(C.byref(s),0),1);stream=[];calls=0
        for frame,row in enumerate(rows):
            self.assertEqual(lib.bq_bridge_begin(C.byref(s)),1);self.assertEqual(s.frame,frame)
            self.assertEqual(lib.bq_bridge_parity(C.byref(s)),frame&1)
            ordinal=0
            for event,p in ref.schedule(row):
                if event=='reinit':
                    old=bytes(s.floor);oracle.floor_ref_reinit();self.assertEqual(lib.bq_bridge_reinit(C.byref(s)),1)
                    self.assertEqual(bytes(s.floor)[:93],old[:93]);self.assertEqual(s.ordinal,ordinal)
                else:
                    oracle.floor_ref_step((F*3)(*p),56,0x400000,frame&1)
                    self.assertEqual(lib.bq_bridge_candidate(C.byref(s),*[C.byref(m) for m in models],(F*3)(*p),ordinal),1)
                    ordinal+=1;calls+=1
                self.assertEqual(bytes(s.floor),original_floor.snapshot(oracle),(opt,frame,event))
                self.assertEqual(lib.bq_bridge_parity(C.byref(s)),frame&1)
            stream.append(canonical(original_floor.snapshot(oracle)))
            self.assertEqual(s.ordinal,ordinal);self.assertEqual(lib.bq_bridge_end(C.byref(s)),1)
            self.assertEqual(lib.bq_bridge_parity(C.byref(s)),(frame+1)&1)
        return dict(frames=len(rows),calls=calls,sha256=hashlib.sha256(b''.join(stream)).hexdigest())
    def test_all_runtime_candidate_schedules_original_bit_exact(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/floor_bridge_golden.json').read_text())
        result=[]
        for opt,lib in zip(('-O0','-O2'),self.libs):
            models,buffers=self.models(lib);out={}
            for name,rows in ref.trajectories(opt).items():out[name]=self.evaluate(lib,models,rows,opt)
            self.assertEqual(out,frozen['floor']);result.append(out)
        self.assertEqual(result[0],result[1])
    def test_existing_six_observed_trajectories_unchanged(self):
        import floor_camera_inputs as old
        for opt in ('-O0','-O2'):
            new=ref.trajectories(opt)
            for name,rows in old.traces(opt).items():
                for a,b in zip(rows,new[name]):
                    for k,v in a.items():self.assertEqual(v,b[k],(name,k))
    def test_multiple_callbacks_same_parity_and_empty_frame(self):
        # Special state4 makes timer parity observable, not merely metadata.
        scene=((0,0x100,False,1000),(300,0x20000,False,1000))
        from floor_state_corpus import load
        for opt,lib in zip(('-O0','-O2'),self.libs):
            models,buffers=self.models(lib,scene);oracle=original_floor.library(opt);load(oracle,scene)
            s=Bridge();lib.bq_bridge_init(C.byref(s),1);oracle.floor_ref_init()
            for frame,n in enumerate((3,0,2,4,1,2,1,2,0)):
                lib.bq_bridge_begin(C.byref(s))
                for ordinal in range(n):
                    oracle.floor_ref_step((F*3)(0,200,0),56,0x400000,(frame+1)&1)
                    self.assertEqual(lib.bq_bridge_candidate(C.byref(s),*[C.byref(m) for m in models],(F*3)(0,200,0),ordinal),1)
                    self.assertEqual(bytes(s.floor),original_floor.snapshot(oracle))
                    self.assertEqual(lib.bq_bridge_parity(C.byref(s)),(frame+1)&1)
                lib.bq_bridge_end(C.byref(s));self.assertEqual(s.frame,frame+1)
    def test_lifecycle_order_atomic_failure_and_wrap(self):
        lib=self.libs[1];models,buffers=self.models(lib);s=Bridge();self.assertEqual(C.sizeof(s),132)
        self.assertEqual(lib.bq_bridge_begin(C.byref(s)),-1);lib.bq_bridge_init(C.byref(s),0)
        def submit(n,p=(0,1800,0)):return lib.bq_bridge_candidate(C.byref(s),*[C.byref(m) for m in models],(F*3)(*p),n)
        self.assertEqual(submit(0),-1);lib.bq_bridge_begin(C.byref(s));self.assertEqual(lib.bq_bridge_begin(C.byref(s)),-1)
        self.assertEqual(submit(1),-1);self.assertEqual(submit(0),1);before=bytes(s)
        self.assertEqual(submit(0),-1);self.assertEqual(bytes(s),before)
        self.assertEqual(submit(1,(float('nan'),0,0)),-1);self.assertEqual(bytes(s),before)
        lib.bq_bridge_reinit(C.byref(s));self.assertEqual(s.floor.height,1800);self.assertEqual(s.floor.countdown,5)
        self.assertEqual(s.ordinal,1);self.assertEqual(submit(1),1);lib.bq_bridge_end(C.byref(s));before=bytes(s)
        self.assertEqual(lib.bq_bridge_end(C.byref(s)),-1);self.assertEqual(bytes(s),before)
        lib.bq_bridge_reinit(C.byref(s));self.assertEqual(s.frame,1)
        s.frame=0xffffffff;lib.bq_bridge_begin(C.byref(s));self.assertEqual(lib.bq_bridge_parity(C.byref(s)),1)
        lib.bq_bridge_end(C.byref(s));self.assertEqual(s.frame,0);self.assertEqual(lib.bq_bridge_parity(C.byref(s)),0)
        lib.bq_bridge_init(C.byref(s),1);self.assertEqual((s.frame,s.floor.height,s.floor.countdown),(0,-9000,5))
    def test_expected_runtime_events_and_no_fabricated_candidates(self):
        cases=ref.trajectories('-O2')
        for n,rows in cases.items():
            for row in rows:
                calls=sum(e=='candidate' for e,_ in ref.schedule(row))
                self.assertEqual(calls,(row['candidate'] is not None)+bool(row['events']&4),(n,row))
        self.assertEqual(sum(bool(r['events']&4) for r in cases['void_recovery']),1)
        self.assertTrue(any(r['candidate'] is not None and r['candidate'][::2]!=r['player'][::2] for r in cases['rejected_ground']))
        for name in ('orbit_ground','orbit_air'):
            self.assertTrue(any(r['camera'] and r['candidate'] is not None for r in cases[name]))
        self.assertTrue(any(r['events']&2 for r in cases['node_jump_landing']))
        self.assertTrue(any(r['candidate'] is None for r in cases['zero_dt']))
        self.assertGreater(max(r['physics_speed'] for r in cases['rejected_ground']),499.99)
        self.assertTrue(any(struct.unpack_from('=f',s,64)[0]==-9000 for s in ref.states(cases['free_walk'],'-O2')))
    def test_camera_acceptance_and_counterfactual_divergence_O0_O2(self):
        import floor_bridge_camera
        frozen=json.loads((Path(__file__).parent/'fixtures/floor_bridge_golden.json').read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            models,buffers=self.models(lib)
            result=floor_bridge_camera.compare(self,lib,models,opt)
            self.assertEqual(json.loads(json.dumps(result)),frozen['camera'])
