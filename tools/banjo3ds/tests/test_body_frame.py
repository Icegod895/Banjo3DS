"""E.2A actual PlayerMotionStep seam, original loop, same-frame floor history.
The host-only callback is not linked into the 3DS viewer. Prescribed candidates
are explicitly isolated post-physics probes, not a claim about possible speed.
"""
import ctypes as C
import functools
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import body_frame_reference as original
import body_corpus as corpus
import bridge_reference
import bridge_corpus
import contact_corpus
import ground_reference
import floor_state_reference
from ground_corpus import State,Frame
from test_floor_state import State as Floor
from test_floor_bridge import Bridge as Clock
from test_jump_runtime import Player
from test_body import Scratch
from test_bridge_state import State as World,View
from test_camera import Math
from world_query_reference import original as asset
from segment_reference import ROOT,FLAGS
F=C.c_float
HERE=Path(__file__).parent

class Observation(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('floors','spheres','moving','lines')]+[
        ('parity',C.c_uint32*5),('candidate',(F*3)*5),('before',(C.c_uint8*120)*5),('after',(C.c_uint8*120)*5)]
class Context(C.Structure):
    _fields_=[(n,C.c_void_p) for n in ('clock','history','phase','opa','xlu','math','scratch')]

@functools.lru_cache(None)
def production(opt):
    tmp=tempfile.TemporaryDirectory(prefix='body-frame-runtime-');p=Path(tmp.name)/'frame.so'
    sources=['platform/3ds/source/'+s for s in ('player_runtime.c','movement.c')]
    sources.append('tools/banjo3ds/camera_first_person/first_person.c')
    sources+=['tools/banjo3ds/'+s for s in (
      'body/body.c','body/frame.c','ground/ground.c','world_query/segment.c','world_query/floor_state.c',
      'world_query/floor_bridge.c','bridge_state/bridge.c','bridge_state/query_segment.c',
      'bridge_state/query_floor_state.c','bridge_state/query_contact.c','camera/camera.c',
      'pose/pose.c','gait/gait.c','gait/gait_motion.c','horizontal/horizontal.c','jump/jump.c','jump/jump_animation.c')]
    includes=['platform/3ds/source','tools/banjo3ds/pose','tools/banjo3ds/gait','tools/banjo3ds/jump',
              'tools/banjo3ds/camera','tools/banjo3ds/world_query']
    subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
       *['-I'+str(ROOT/n) for n in includes],*[str(ROOT/n) for n in sources],str(HERE/'body_frame_harness.c'),
       *['-Wl,--wrap=bridge_'+n for n in ('floor_update','sphere','moving','segment')],'-lm','-o',str(p)],check=True)
    lib=C.CDLL(str(p));lib._tmp=tmp
    lib.frame_host_size.restype=C.c_size_t
    lib.frame_host_init.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint32,F,F]
    lib.frame_host_update.argtypes=[C.c_void_p,F,F,F,F,C.c_int,C.c_void_p,C.c_bool,C.c_bool,C.c_uint32]
    lib.frame_host_snapshot.argtypes=[C.c_void_p]*10
    lib.frame_host_player.argtypes=[C.c_void_p];lib.frame_host_player.restype=C.POINTER(Player)
    lib.frame_host_pending.argtypes=[C.c_void_p,C.c_uint32];lib.frame_host_camera_lease.argtypes=[C.c_void_p]
    lib.frame_host_reinit.argtypes=[C.c_void_p];lib.frame_host_stuck.argtypes=[C.c_void_p,C.c_uint32]
    return lib

def setup_reference(opt,pos,bits,published=True):
    lib=original.library(opt)
    for role,id in enumerate(('14CF','14D0')):lib.ref_load(role,(ROOT/f'assets/model/{id}.model.bin').read_bytes())
    br=bridge_reference.library(opt);contact_corpus.load(br,'real');bridge_corpus.configure(br,'raw')
    br.bridge_ref_actor(bits)
    if published:br.bridge_ref_mesh(F(1/60))
    publish_reference(lib,br)
    lib.floor_ref_init();lib.body_ref_init(0,0)
    for i in range(6):lib.floor_ref_step((F*3)(*pos),56,0x400000,i&1)
    return lib,br

def publish_reference(lib,br):
    for ids in bridge_reference.membership().values():
        for vertex in ids:
            xyz=(C.c_int16*3)();br.bridge_ref_xyz(1,vertex,xyz);lib.body_ref_vertex(1,vertex,xyz)

class Harness:
    def __init__(self,opt,pos,vy,ground,bits=0x9db1,heading=0,speed=0,published=True):
        self.opt=opt;self.bits=bits;self.lib=production(opt);self.memory=C.create_string_buffer(self.lib.frame_host_size())
        self.ref,self.bridge_ref=setup_reference(opt,pos,bits,published)
        self.buffers=[C.create_string_buffer(asset(a,r)['packet']) for r,a in enumerate((0x14cf,0x14d0))]
        floor=Floor.from_buffer_copy(floor_state_reference.snapshot(self.ref))
        self.want=State((F*3)(*pos),vy,floor.height,ground,0);self.stuck=C.c_uint32(0)
        self.lib.frame_host_init(self.memory,self.buffers[0],len(self.buffers[0])-1,
            self.buffers[1],len(self.buffers[1])-1,C.byref(self.want),C.byref(floor),bits,heading,speed)
        if not published:self.lib.frame_host_pending(self.memory,bits)
        self.frame=0;self.rows=[]
        self.groundref=ground_reference.library(opt)
        self.groundref.ground_ref_candidate.argtypes=[C.c_void_p,C.c_void_p,F,C.c_void_p]

    def update(self,*,x=0,y=0,yaw=0,dt=1/60,mode=0,end=None,jump=False,orbit=False,check=True):
        r=self.lib.frame_host_update(self.memory,x,y,yaw,dt,mode,(F*3)(*end) if end else None,jump,orbit,self.bits)
        assert r==1,r
        phase=State();clock=Clock();history=corpus.History();trace=corpus.Trace();obs=Observation();prior=State();candidate=Frame()
        counts=(C.c_uint32*6)();applied=((C.c_uint32*3)*5)()
        self.lib.frame_host_snapshot(self.memory,*map(C.byref,(phase,clock,history,trace,obs,prior,candidate,counts,applied)))
        if dt==0:
            assert not any(counts) and obs.floors==0 and clock.ordinal==0
            self.frame+=1
            return phase,trace,obs,counts,clock
        # Original gameplay state update sees previous player and previous floor,
        # never one of the intermediate body's new floors or snapped candidates.
        if self.want.grounded:self.want.falling=0
        assert bytes(prior)==bytes(self.want),(self.frame,'prior phase')
        entry=0 if mode==2 else self.groundref.ground_ref_state(C.byref(self.want))
        assert counts[3]==entry,(self.frame,'FALL selection')
        p=self.lib.frame_host_player(self.memory).contents
        f=Frame()
        if mode==0:
            self.groundref.ground_ref_candidate(C.byref(self.want),(F*2)(*p.horizontal.velocity),dt,C.byref(f))
            assert bytes(f)==bytes(candidate),(self.frame,'original physics candidate')
        elif mode==1:
            f.previous[:]=self.want.position;f.candidate[:]=end;f.grounded=self.want.grounded
            f.requested[:]=[F(f.candidate[k]-f.previous[k]).value for k in range(3)]
            assert bytes(f)==bytes(candidate)
        else:
            # Isolate same supplied air-physics candidate. Another test compares
            # this boundary against the existing actual jump observer.
            f=Frame.from_buffer_copy(candidate);self.want.falling=0
            if jump and self.want.grounded and not orbit:self.want.vy=710;self.want.grounded=0
            self.want.vy=max(F(self.want.vy-F(1350*F(dt).value).value).value,-4000)
        self.ref.frame_ref_reset()
        v=F(self.want.vy);g=C.c_uint(self.want.grounded);out=(F*3)(*f.candidate);expected=corpus.Trace()
        assert self.ref.body_ref_step(f.previous,out,C.byref(v),self.frame&1,C.byref(g),C.byref(self.stuck),C.byref(expected))==1
        expected_observation=Observation();self.ref.frame_ref_observation(C.byref(expected_observation))
        self.want.position[:]=out;self.want.vy=v.value;self.want.grounded=g.value
        self.want.height=Floor.from_buffer_copy(floor_state_reference.snapshot(self.ref)).height
        if check:
            assert bytes(phase)==bytes(self.want),(self.frame,'phase')
            assert bytes(trace)==bytes(expected),(self.frame,'body')
            assert bytes(obs)==bytes(expected_observation),(self.frame,'observation',list((obs.floors,obs.spheres,obs.moving,obs.lines)),list((expected_observation.floors,expected_observation.spheres,expected_observation.moving,expected_observation.lines)))
            assert bytes(clock.floor)==floor_state_reference.snapshot(self.ref),(self.frame,'floor')
            assert list(history.normal)==list(trace.normal) and history.stuck==self.stuck.value
            assert list(counts)==[1,1,1,entry,0,0]
            assert (clock.frame,clock.ordinal,clock.active)==(self.frame+1,trace.iterations,0)
            assert obs.floors==trace.iterations and all(p==self.frame&1 for p in obs.parity[:obs.floors])
            assert [p.motion.actor.x,p.motion.actor.y,p.motion.actor.z]==list(phase.position)
            assert (p.motion.vy,p.motion.grounded)==(phase.vy,bool(phase.grounded))
            for i in range(obs.floors):
                assert bytes(obs.after[i])==bytes(trace.iteration[i].floor)
                if i:assert bytes(obs.before[i])==bytes(obs.after[i-1]),'floor history was reset/replayed'
        # Canonical stream: no pointers, little-endian scalar fields only.
        blob=bytes(phase)+bytes(clock)+bytes(history)+bytes(trace)+bytes(obs)+bytes(prior)+bytes(candidate)+bytes(counts)+bytes(applied)
        self.rows.append(dict(hash=hashlib.sha256(blob).hexdigest(),frame=self.frame,counts=list(counts),
            position=list(phase.position),vy=phase.vy,grounded=phase.grounded,falling=phase.falling,
            velocity=[p.horizontal.velocity[0],phase.vy,p.horizontal.velocity[1]],
            physics_candidate=list(candidate.candidate),requested_displacement=list(candidate.requested),
            accepted_horizontal=list(p.metrics.accepted),
            floor_calls=obs.floors,sphere_calls=obs.spheres,body_queries=obs.moving,line_queries=obs.lines,
            parity=list(obs.parity[:obs.floors]),bridge=[list(a) for a in applied[:obs.floors]],
            floor_heights=[Floor.from_buffer_copy(bytes(q.floor)).height for q in trace.iteration[:trace.iterations]],
            corrections=[list(q.final) for q in trace.iteration[:trace.iterations]],exhausted=trace.exhausted,stuck=history.stuck))
        # Original bridge publication is after player AND camera queries. The
        # harness has no camera callback; it observes the same immutable lease.
        self.bridge_ref.bridge_ref_mesh(F(dt));publish_reference(self.ref,self.bridge_ref)
        self.frame+=1
        return phase,trace,obs,counts,clock


def schedules(opt):
    result={}
    for name,pos,vy,g,bits,heading,speed,rows in (
      ('wall',(-37.666668,1784,-3751),-1,1,0x9db1,180,500,[(156,.05,False)]*8),
      ('flat',(0,1800,0),-1,1,0x9db1,0,100,[(54,1/60,False)]*20),
      ('ledge',(0,1800,391.666779),-1,1,0x9db1,0,500,[(156,1/60,False)]*60),
      ('slope-down',(-2094,133.333344,-383.666656),-1,1,0x9db1,135,500,[(156,.05,False)]*4),
      ('slope-up',(-2076.322266,99.449371,-401.34433),-1,1,0x9db1,315,500,[(156,.05,False)]*4),
      ('bridge-tutorial',(0,1576,-1770),-1,1,0,180,500,[(156,1/60,False)]*20),
      ('bridge-full',(0,1576,-1770),-1,1,0x9db1,180,500,[(156,1/60,False)]*20),
      ('orbit-ground',(0,1800,0),-1,1,0x9db1,0,500,[(156,1/60,True)]*8),
    ):
        h=Harness(opt,pos,vy,g,bits,heading,speed)
        for raw,dt,orbit in rows:h.update(y=raw,yaw=-heading,dt=dt,orbit=orbit)
        result[name]=h.rows
    for name,orbit,pos,heading,speed in (
        ('jump-rest',False,(0,1800,0),0,0),('jump-full',False,(0,1800,0),0,500),
        ('jump-orbit',True,(0,1800,0),0,500),('landing-wall',False,(-37.666668,1820,-3751),180,500)):
        h=Harness(opt,pos,0,name!='landing-wall',0x9db1,heading,speed)
        for i in range(70):
            phase,*_=h.update(y=156 if speed else 0,yaw=-heading,mode=2,jump=i==0 and name!='landing-wall',orbit=orbit and i>0)
            if i>0 and phase.grounded:break
        result[name]=h.rows
    return result

@functools.lru_cache(None)
def goldens(opt):
    cases={}
    for name,pos,end,vy,g,bits in corpus.cases():
        h=Harness(opt,pos,vy,g,bits);h.update(mode=1,end=end);cases[name]=h.rows[0]
    return dict(format='E2A v1 little-endian float32/u32; complete observed state hash',
                cases=cases,schedules=schedules(opt))

class BodyFrameTests(unittest.TestCase):
    def test_frozen_composition_certificate_O0_O2(self):
        frozen=json.loads((HERE/'fixtures/body_frame_golden.json').read_text())
        for opt in ('-O0','-O2'):self.assertEqual(goldens(opt),frozen)

    def test_intermediate_ground_does_not_finalize_vy_or_request_fall(self):
        case=next(c for c in corpus.cases() if c[0]=='corner-0-1050-0-25')
        for opt in ('-O0','-O2'):
            _,pos,end,vy,g,bits=case;h=Harness(opt,pos,vy,g,bits)
            phase,trace,obs,counts,clock=h.update(mode=1,end=end)
            self.assertEqual([q.grounded for q in trace.iteration[:trace.iterations]],[1,1,0,0,0])
            self.assertEqual(phase.vy,-500)
            self.assertEqual(counts[0],1)
            self.assertEqual(clock.ordinal,5)


    def test_real_postphysics_cases_same_floor_history_parity_O0_O2(self):
        for case in corpus.cases():
            name,pos,end,vy,g,bits=case;baseline=None
            for opt in ('-O0','-O2'):
                h=Harness(opt,pos,vy,g,bits);h.update(mode=1,end=end)
                if baseline is None:baseline=h.rows
                self.assertEqual(h.rows,baseline,name)

    def test_actual_player_dispatch_schedules_O0_O2(self):
        self.assertEqual(schedules('-O0'),schedules('-O2'))

    def test_first_floor_differs_after_correction_and_no_premature_fall(self):
        case=next(c for c in corpus.cases() if c[0]=='steep-91')
        for opt in ('-O0','-O2'):
            _,pos,end,vy,g,bits=case;h=Harness(opt,pos,vy,g,bits)
            phase,trace,obs,counts,clock=h.update(mode=1,end=end)
            self.assertEqual(list(counts[:4]),[1,1,1,0])
            self.assertEqual(trace.iterations,2)
            self.assertNotEqual(bytes(obs.after[0]),bytes(obs.after[1]))
            self.assertEqual(h.rows[0]['floor_heights'],[2014.6666259765625,1983.773193359375])
            self.assertEqual(phase.vy,vy)

    def test_five_iterations_one_frame_and_retained_last_query_on_fallback(self):
        case=next(c for c in corpus.cases() if c[0]=='corner-0-259-0-25')
        for opt in ('-O0','-O2'):
            _,pos,end,vy,g,bits=case;h=Harness(opt,pos,vy,g,bits)
            phase,trace,obs,counts,clock=h.update(mode=1,end=end)
            self.assertEqual((trace.iterations,trace.exhausted,clock.frame,clock.ordinal),(5,1,1,5))
            self.assertEqual(list(obs.parity),[0]*5)
            self.assertEqual(list(phase.position),list(trace.fallback))
            self.assertEqual(bytes(clock.floor),bytes(obs.after[4]))
            self.assertNotEqual(list(clock.floor.candidate),list(phase.position))
            h.update(mode=1,end=end)
            self.assertTrue(all(x==1 for x in h.rows[-1]['parity']))

    def test_pending_mesh_publication_never_mid_loop_and_reinit(self):
        for opt in ('-O0','-O2'):
            for bits in (0,0x9db1):
                h=Harness(opt,(0,1576,-1800),-136,1,bits,published=False)
                h.update(mode=1,end=(0,1569.2,-1825))
                self.assertTrue(all(a==[0,0,0] for a in h.rows[-1]['bridge']))
                h.update(mode=1,end=(0,1569.2,-1825))
                expected=[0,0,2**32-5000] if not bits else [2**32-5000,2**32-5000,0]
                self.assertTrue(all(a==expected for a in h.rows[-1]['bridge']))
                h.lib.frame_host_reinit(h.memory);h.ref.floor_ref_reinit()
                h.update(mode=1,end=(0,1569.2,-1825))
                self.assertEqual(h.rows[-1]['frame'],2)

    def test_scratch_camera_lease_does_not_destroy_persistent_player_state(self):
        for opt in ('-O0','-O2'):
            h=Harness(opt,(-37.666668,1784,-3751),-1,1,heading=180,speed=500)
            for _ in range(6):
                h.update(y=156,yaw=-180,dt=.05)
                h.lib.frame_host_camera_lease(h.memory)

    def test_body_acceptance_does_not_overwrite_horizontal_physics(self):
        for opt in ('-O0','-O2'):
            h=Harness(opt,(-37.666668,1784,-3751),-1,1,heading=180,speed=500)
            h.update(y=156,yaw=-180,dt=.05)
            p=h.lib.frame_host_player(h.memory).contents
            self.assertAlmostEqual(p.metrics.physics_speed,500,places=4)
            self.assertLess(p.metrics.accepted_speed,70)
            self.assertEqual(p.horizontal.velocity[1],-500)
            self.assertEqual(p.motion.actor.z,-3754.125)

    def test_zero_dt_clock_only_and_same_frame_second_body_is_rejected(self):
        h=Harness('-O2',(0,1800,0),-1,1)
        _,_,_,_,clock=h.update(dt=0)
        self.assertEqual(clock.frame,1)
        h.update()
        # Dedicated isolated API guards: a closed/wrong/used frame must not run.
        lib=production('-O2');lib.bp_frame_resolve.argtypes=[C.POINTER(Context),C.POINTER(Frame),C.c_uint32]
        from test_body import ProductionWorld
        w=ProductionWorld('-O2',(0,1800,0),1,0x9db1)
        clock=Clock();clock.initialized=1;clock.floor=w.floor
        f=Frame();f.previous[:]=(0,1800,0);f.candidate[:]=(0,1799,0);f.requested[:]=(0,-1,0);f.grounded=1
        c=Context(*[C.addressof(v) for v in (clock,w.hist,w.state,*w.views,w.math,w.scratch)])
        for active,ordinal,identity in ((0,0,0),(1,1,0),(1,0,99)):
            clock.active=active;clock.ordinal=ordinal
            before=bytes(clock),bytes(w.state),bytes(w.hist)
            self.assertEqual(lib.bp_frame_resolve(C.byref(c),C.byref(f),identity),-1)
            self.assertEqual((bytes(clock),bytes(w.state),bytes(w.hist)),before)
        # Valid views distinguish a real duplicate-dispatch rejection from an
        # unrelated invalid-provider error.
        clock.active=1;clock.ordinal=0
        self.assertEqual(lib.bp_frame_resolve(C.byref(c),C.byref(f),0),1)
        before=bytes(clock),bytes(w.state),bytes(w.hist)
        self.assertEqual(lib.bp_frame_resolve(C.byref(c),C.byref(f),0),-1)
        self.assertEqual((bytes(clock),bytes(w.state),bytes(w.hist)),before)
        # A failed body invocation cannot publish a partial floor or ordinal.
        clock.ordinal=0;f.candidate[:]=(1e9,0,0)
        before=bytes(clock),bytes(w.state),bytes(w.hist)
        self.assertEqual(lib.bp_frame_resolve(C.byref(c),C.byref(f),0),-1)
        self.assertEqual((bytes(clock),bytes(w.state),bytes(w.hist)),before)

    def test_air_candidate_exactly_matches_current_jump_presweep_observer(self):
        from tools.banjo3ds.floor_collision import scene_collision
        from test_jump import arrays
        vertices,triangles=arrays(*scene_collision([ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0')]))
        for opt in ('-O0','-O2'):
            for speed,orbit in ((0,False),(500,False),(500,True)):
                h=Harness(opt,(0,1800,0),-1,1,heading=0,speed=speed)
                h.lib.frame_host_probe_geometry.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_size_t]
                h.lib.frame_host_air_probe.argtypes=[C.c_void_p]
                h.lib.frame_host_probe_geometry(h.memory,vertices,triangles,len(triangles))
                for i in range(20):
                    h.update(mode=2,y=156 if speed else 0,jump=i==0,orbit=orbit and i>0)
                    self.assertEqual(h.lib.frame_host_air_probe(h.memory),1,(opt,speed,orbit,i))

    def test_live_runtime_uses_proven_boundary_and_sequential_publication(self):
        camera=(ROOT/'platform/3ds/source/camera_runtime.c').read_text()
        main=(ROOT/'platform/3ds/source/main.c').read_text()
        ground=(ROOT/'platform/3ds/source/player_ground.c').read_text()
        self.assertIn('bp_frame_resolve',ground)
        self.assertNotIn('bp_resolve(',ground)
        self.assertIn('playerGroundStep,&ground',camera)
        move=camera[camera.index('int cameraRuntimeMove(CameraRuntime'):camera.index('int cameraRuntimeUpdateView')]
        self.assertLess(move.index('bridge_actor_tick'),move.index('cameraRuntimeMoveQueries'))
        self.assertLess(move.index('cameraRuntimeMoveQueries'),move.index('bridge_mesh_tick'))
        query=camera[camera.index('static int cameraRuntimeMoveQueries'):camera.index('void cameraRuntimeSetLearnedAbilities')]
        self.assertLess(query.index('playerRuntimeMoveStepped'),query.index('bq_bridge_end'))
        self.assertLess(query.index('bq_bridge_end'),query.index('cameraRuntimeUpdateView'))
        self.assertLess(main.index('cameraRuntimeMove('),main.index('bridge_render_y('))
        make=(ROOT/'platform/3ds/Makefile').read_text()
        self.assertIn('banjo3ds/body',make)
        motion=(ROOT/'platform/3ds/source/player_ground.c').read_text()
        self.assertEqual(motion.count('bp_frame_resolve('),1)
        self.assertNotIn('banjo_jump_step_overlay(',motion)
        self.assertNotIn('bg_query_resolve(',motion)
        self.assertLess(motion.index('c->observe('),motion.index('bp_frame_resolve('))
