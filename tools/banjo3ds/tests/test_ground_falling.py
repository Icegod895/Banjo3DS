"""Isolated original ground/falling phase: no player/viewer integration."""
import ctypes as C
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import ground_reference as ref
import ground_corpus as corpus
import floor_state_reference as floor_ref
import bridge_reference
import bridge_corpus
import contact_corpus
from test_floor_state import State as Floor
from test_bridge_state import State as Bridge, View
from test_world_segment import Model
from world_query_reference import original
from segment_reference import ROOT,FLAGS
F=corpus.F;State=corpus.State;Frame=corpus.Frame;FP=C.POINTER(F)
FIXTURE=Path(__file__).parent/'fixtures/ground_falling_golden.json'


def bind_reference(lib):
    lib.ground_ref_state.argtypes=[C.POINTER(State)]
    lib.ground_ref_candidate.argtypes=[C.POINTER(State),FP,F,C.POINTER(Frame)]
    lib.ground_ref_resolve.argtypes=[C.POINTER(State),C.POINTER(Frame),C.c_int,F,FP,C.c_uint]
    lib.ground_ref_fall_config.argtypes=[FP,C.POINTER(C.c_int)]


def reference_world(lib,opt,bits):
    for role,id in enumerate(('14CF','14D0')):lib.ref_load(role,(ROOT/f'assets/model/{id}.model.bin').read_bytes())
    # Original actor + original mesh callbacks, not production offsets.
    b=bridge_reference.library(opt);contact_corpus.load(b,'real');bridge_corpus.configure(b,'raw')
    b.bridge_ref_actor(bits);b.bridge_ref_mesh(F(1/60))
    for ids in bridge_reference.membership().values():
        for vertex in ids:
            p=(C.c_int16*3)();b.bridge_ref_xyz(1,vertex,p);lib.ground_ref_vertex(1,vertex,p)
    lib.floor_ref_init()


def original_run(opt,spec):
    lib=ref.library(opt);bind_reference(lib);pos,vy,grounded,rows,bits=spec
    reference_world(lib,opt,bits)
    for i in range(6):lib.floor_ref_step((F*3)(*pos),56,0x400000,i&1)
    fstate=Floor.from_buffer_copy(floor_ref.snapshot(lib));s=State((F*3)(*pos),vy,fstate.height,grounded,0)
    out=[]
    for i,(hx,hz,dt) in enumerate(rows):
        entry=lib.ground_ref_state(C.byref(s));f=Frame()
        lib.ground_ref_candidate(C.byref(s),(F*2)(hx,hz),dt,C.byref(f))
        lib.ground_ref_resolve(C.byref(s),C.byref(f),1,0,(F*3)(),i&1)
        out.append((bytes(s),bytes(f),floor_ref.snapshot(lib),entry))
    return out


def summary(rows):
    blobs=[corpus.packed(State.from_buffer_copy(s),Frame.from_buffer_copy(f),floor) for s,f,floor,_ in rows]
    checkpoints={}
    for i in sorted(set([0,1,2,len(rows)-1]+[j for j,r in enumerate(rows) if r[3]])):
        if i>=len(rows):continue
        s=State.from_buffer_copy(rows[i][0]);f=Frame.from_buffer_copy(rows[i][1])
        checkpoints[str(i)]=dict(position=list(s.position),vy=s.vy,floor=s.height,
           grounded=s.grounded,falling=s.falling,entry=rows[i][3],normal=list(f.normal),requested=list(f.requested))
    return dict(count=len(rows),sha256=corpus.digest(blobs),checkpoints=checkpoints)


def boundary_reference(opt):
    lib=ref.library(opt);bind_reference(lib);lib.floor_ref_init();out=[]
    for ny,gap,grounded,dy in corpus.boundaries():
        s=State((F*3)(7,gap-dy,9),-10,0,grounded,0)
        f=Frame((F*3)(*s.position),(F*3)(8,gap,10),(F*3)(1,dy,1),(F*3)(),grounded)
        lib.ground_ref_resolve(C.byref(s),C.byref(f),0,0,(F*3)(0,ny,0),0)
        out.append((bytes(s),bytes(f)))
    return out


def golden(opt):
    return dict(schedules={name:summary(original_run(opt,spec)) for name,spec in corpus.schedules().items()},
        boundary_count=len(corpus.boundaries()),boundary_sha256=corpus.digest([s+f for s,f in boundary_reference(opt)]))


class GroundFallingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='ground-production-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];base=ROOT/'tools/banjo3ds'
        for opt in ('-O0','-O2'):
            p=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                *[str(base/f) for f in ('ground/ground.c','world_query/segment.c','bridge_state/bridge.c',
                                      'bridge_state/query_segment.c','bridge_state/query_floor_state.c')],'-lm','-o',str(p)],check=True)
            lib=C.CDLL(str(p));cls.libs.append(lib)
            lib.bg_state_update.argtypes=[C.POINTER(State)]
            lib.bg_candidate.argtypes=[C.POINTER(State),FP,F,C.POINTER(Frame)]
            lib.bg_resolve.argtypes=[C.POINTER(State),C.POINTER(Frame),F,FP]
            lib.bg_query_resolve.argtypes=[C.POINTER(State),C.POINTER(Frame),C.POINTER(Floor),C.POINTER(Model),C.POINTER(Model),C.c_uint,C.c_void_p]
            lib.bridge_init.argtypes=[C.POINTER(Bridge)];lib.bridge_actor_tick.argtypes=[C.POINTER(Bridge),C.c_uint32]
            lib.bridge_mesh_tick.argtypes=[C.POINTER(Bridge),F]
            lib.bridge_model_open.argtypes=[C.POINTER(View),C.c_void_p,C.c_size_t,C.POINTER(Bridge)]
            lib.bridge_floor_init.argtypes=[C.POINTER(Floor)]
            lib.bridge_floor_update.argtypes=[C.POINTER(Floor),C.POINTER(Model),C.POINTER(Model),FP,F,C.c_uint32,C.c_uint]

    def run_production(self,lib,spec):
        pos,vy,grounded,rows,bits=spec;b=Bridge();lib.bridge_init(C.byref(b));lib.bridge_actor_tick(C.byref(b),bits)
        lib.bridge_mesh_tick(C.byref(b),F(1/60))
        buffers=[C.create_string_buffer(original(a,r)['packet']) for r,a in enumerate((0x14cf,0x14d0))]
        views=[View(),View()]
        for v,buf in zip(views,buffers):self.assertEqual(lib.bridge_model_open(C.byref(v),buf,len(buf)-1,C.byref(b)),1)
        models=[C.byref(v.base) for v in views];floor=Floor();lib.bridge_floor_init(C.byref(floor))
        for i in range(6):self.assertEqual(lib.bridge_floor_update(C.byref(floor),*models,(F*3)(*pos),56,0x400000,i&1),1)
        s=State((F*3)(*pos),vy,floor.height,grounded,0);out=[]
        for i,(hx,hz,dt) in enumerate(rows):
            entry=lib.bg_state_update(C.byref(s));f=Frame();lib.bg_candidate(C.byref(s),(F*2)(hx,hz),dt,C.byref(f))
            self.assertEqual(lib.bg_query_resolve(C.byref(s),C.byref(f),C.byref(floor),*models,i&1,C.cast(lib.bridge_floor_update,C.c_void_p)),1,(pos,i,list(f.candidate),floor.mode,floor.height))
            # The floor-only phase never changes horizontal endpoint.
            self.assertEqual(list(s.position)[::2],list(f.candidate)[::2])
            out.append((bytes(s),bytes(f),bytes(floor),entry))
        return out

    def test_all_real_schedules_full_state_and_independent_goldens_O0_O2(self):
        frozen=json.loads(FIXTURE.read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            self.assertEqual(golden(opt),frozen)
            for name,spec in corpus.schedules().items():
                want=original_run(opt,spec);got=self.run_production(lib,spec)
                for i,(a,b) in enumerate(zip(got,want)):self.assertEqual(a,b,(opt,name,i))

    def test_snap_normal_boundaries_and_previous_contact_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            wanted=boundary_reference(opt)
            for row,(ws,wf) in zip(corpus.boundaries(),wanted):
                ny,gap,grounded,dy=row;s=State((F*3)(7,gap-dy,9),-10,0,grounded,0)
                f=Frame((F*3)(*s.position),(F*3)(8,gap,10),(F*3)(1,dy,1),(F*3)(),grounded)
                lib.bg_resolve(C.byref(s),C.byref(f),0,(F*3)(0,ny,0))
                self.assertEqual((bytes(s),bytes(f)),(ws,wf),(opt,row))
                self.assertEqual((s.position[0],s.position[2]),(8,10))
                self.assertEqual(s.vy,-1 if s.grounded else -10)
        # Crucial unsuffixed .9: float32(.9) is BELOW original double .9.
        self.assertLess(F(.9).value,.9)

    def test_state_update_before_physics_60_boundary_and_no_jump_impulse(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            oracle=ref.library(opt);bind_reference(oracle)
            for separation in corpus.neighbors(60):
                for vy in (-4000,-1,0,100):
                    a=State((F*3)(0,separation,0),vy,0,0,0);b=State.from_buffer_copy(a)
                    config=(F*5)();calls=C.c_int();oracle.ground_ref_fall_config(config,C.byref(calls));prior=calls.value
                    want=oracle.ground_ref_state(C.byref(b));got=lib.bg_state_update(C.byref(a))
                    self.assertEqual(got,want);self.assertEqual(bytes(a),bytes(b));self.assertEqual(a.vy,vy)
                    self.assertEqual(got,int(separation>60))
                    oracle.ground_ref_fall_config(config,C.byref(calls));self.assertEqual(calls.value,prior)
                    if got:self.assertEqual(list(config),[1,176,F(.3).value,F(.38).value,6])
            rows=self.run_production(lib,corpus.schedules()['plateau_ledge'])
            self.assertEqual([r[3] for r in rows[:3]],[0,1,0])
            self.assertFalse(State.from_buffer_copy(rows[0][0]).grounded)
            self.assertGreater(State.from_buffer_copy(rows[0][0]).position[2],400)

    def test_limitations_are_visible_and_old_fail_closed_contract_untouched(self):
        lib=self.libs[1]
        steep=self.run_production(lib,corpus.schedules()['steep_no_body_LIMITATION'])
        s=State.from_buffer_copy(steep[0][0]);self.assertFalse(s.grounded);self.assertLess(s.position[1],2014.666667)
        wall=self.run_production(lib,corpus.schedules()['wall_no_body_LIMITATION'])
        self.assertEqual(State.from_buffer_copy(wall[0][0]).position[2],-3776)
        # E.1B calls this phase without bringing historical floor-follow into it.
        self.assertNotIn('movementFollowFloor',(ROOT/'tools/banjo3ds/ground/ground.c').read_text())

    def test_candidate_rounding_terminal_velocity_and_no_new_dt_policy(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            oracle=ref.library(opt);bind_reference(oracle)
            for dt in (0,1/60,.05):
                for vy in (-3999,-4000,0):
                    a=State((F*3)(1e7,1800,3),vy,1800,1,0);b=State.from_buffer_copy(a);fa=Frame();fb=Frame();h=(F*2)(.0001,500)
                    lib.bg_candidate(C.byref(a),h,dt,C.byref(fa));oracle.ground_ref_candidate(C.byref(b),h,dt,C.byref(fb))
                    self.assertEqual((bytes(a),bytes(fa)),(bytes(b),bytes(fb)))
                    self.assertGreaterEqual(a.vy,-4000)

    def test_explicit_snap_rules_and_contact_velocity(self):
        for lib in self.libs:
            for normal,limit in ((.8,30.),(1.,5.),(F(.9).value,30.)):
                for gap in corpus.neighbors(limit):
                    s=State((F*3)(0,gap+1,0),-46,0,1,0)
                    f=Frame((F*3)(*s.position),(F*3)(0,gap,0),(F*3)(0,-1,0),(F*3)(),1)
                    lib.bg_resolve(C.byref(s),C.byref(f),0,(F*3)(0,normal,0))
                    self.assertEqual(s.grounded,int(gap<limit))
            for ny in corpus.neighbors(.432):
                s=State((F*3)(0,1,0),-46,0,1,0)
                f=Frame((F*3)(*s.position),(F*3)(0,-1,0),(F*3)(0,-2,0),(F*3)(),1)
                lib.bg_resolve(C.byref(s),C.byref(f),0,(F*3)(0,ny,0))
                self.assertEqual(s.grounded,int(ny>=.432))
            # Contact itself does not invent vy=-1 when velocity is nonnegative.
            s=State((F*3)(0,-1,0),10,0,0,0);f=Frame();f.candidate[:]=(0,-1,0)
            lib.bg_resolve(C.byref(s),C.byref(f),0,(F*3)(0,1,0))
            self.assertEqual((s.grounded,s.vy),(1,10))

    def test_landing_and_published_bridge_configurations(self):
        for lib in self.libs:
            land=self.run_production(lib,corpus.schedules()['floor_reacquisition'])
            self.assertTrue(any(State.from_buffer_copy(r[0]).grounded for r in land))
            last=State.from_buffer_copy(land[-1][0]);self.assertEqual((last.position[1],last.vy),(1800,-1))
            full=self.run_production(lib,corpus.schedules()['bridge_full'])
            tutorial=self.run_production(lib,corpus.schedules()['bridge_tutorial'])
            self.assertTrue(all(State.from_buffer_copy(r[0]).grounded for r in full))
            self.assertTrue(all(not State.from_buffer_copy(r[0]).grounded for r in tutorial))
            self.assertEqual(State.from_buffer_copy(full[-1][0]).position[1],1576)
            self.assertLess(State.from_buffer_copy(tutorial[-1][0]).position[1],1576)

    def test_floor_provider_failure_is_not_a_floor_miss(self):
        Query=C.CFUNCTYPE(C.c_int,C.POINTER(Floor),C.POINTER(Model),C.POINTER(Model),FP,F,C.c_uint32,C.c_uint)
        @Query
        def failure(floor,opa,xlu,p,upper,mask,parity):return -1
        for lib in self.libs:
            s=State((F*3)(0,1800,0),-1,1800,1,0);f=Frame();floor=Floor()
            lib.bg_candidate(C.byref(s),(F*2)(0,500),F(1/60),C.byref(f))
            before=bytes(s),bytes(f),bytes(floor)
            self.assertEqual(lib.bg_query_resolve(C.byref(s),C.byref(f),C.byref(floor),None,None,0,C.cast(failure,C.c_void_p)),-1)
            self.assertEqual((bytes(s),bytes(f),bytes(floor)),before)
