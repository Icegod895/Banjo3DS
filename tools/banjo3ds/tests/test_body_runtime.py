"""E.2B real cameraRuntimeMove -> playerGroundStep -> body frame, original oracle."""
import ctypes as C
import math
import unittest
import json
from pathlib import Path
import test_camera_runtime as runtime
import test_body_frame as frame
import body_corpus as corpus
import floor_state_reference as floor_ref
from ground_corpus import State,Frame
from test_floor_state import State as Floor
from test_horizontal import State as Horizontal
from test_movement import Actor
F=C.c_float
class Capture(C.Structure):
    _fields_=[('before',State),('after',State),('input',Frame),('output',Frame),
        ('floor_before',Floor),('floor_after',Floor),('history_before',corpus.History),('history_after',corpus.History),
        ('trace',corpus.Trace),('queries',frame.Observation),
        *[(n,C.c_uint32) for n in ('frame','parity','ordinal_before','ordinal_after','world_changed')],
        ('applied',(C.c_int32*3)*5),('result',C.c_int)]

class BodyRuntimeTests(unittest.TestCase):
    body_observer=True
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move
    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:
            lib.body_runtime_capture.argtypes=[C.POINTER(Capture)];lib.body_runtime_capture_size.restype=C.c_size_t
            assert lib.body_runtime_capture_size()==C.sizeof(Capture)
            lib.banjo_horizontal_init.argtypes=[C.POINTER(Horizontal),F]
            lib.bridge_actor_tick.argtypes=[C.c_void_p,C.c_uint32];lib.bridge_mesh_tick.argtypes=[C.c_void_p,F]

    def seed(self,lib,opt,pos,vy=-1,grounded=True,bits=0x9db1,heading=0,speed=0):
        s,p=self.start(lib,pos,heading);lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
        lib.bridge_actor_tick(C.byref(s.world_bridge),bits);lib.bridge_mesh_tick(C.byref(s.world_bridge),F(1/60))
        ref,br=frame.setup_reference(opt,pos,bits)
        C.memmove(C.byref(s.bridge.floor),floor_ref.snapshot(ref),120)
        p.motion.vy=vy;p.motion.grounded=grounded
        s.player_ground.phase=State((F*3)(*pos),vy,s.bridge.floor.height,grounded,0)
        lib.banjo_horizontal_init(C.byref(p.horizontal),heading);p.horizontalInitialized=True
        p.horizontal.velocity[:]=(F(speed*math.sin(math.radians(heading))).value,F(speed*math.cos(math.radians(heading))).value)
        p.locomotion.gait=4 if speed else 0
        return s,p,ref

    def compare(self,lib,s,p,ref,*,raw=0,heading=0,dt=1/60,jump=False,orbit=False):
        prior=State.from_buffer_copy(s.player_ground.phase)
        prior.position[:]=(p.motion.actor.x,p.motion.actor.y,p.motion.actor.z);prior.vy=p.motion.vy;prior.grounded=p.motion.grounded
        if prior.grounded:prior.falling=0
        before_clock=s.bridge.frame
        status=self.move(lib,s,p,0,raw,-heading,dt=dt,jump=jump,orbit=orbit)
        self.assertNotIn(status,(-1,-3))
        c=Capture();lib.body_runtime_capture(C.byref(c));self.assertEqual(c.result,1)
        self.assertEqual((s.calls,s.bridge.frame,c.ordinal_before,c.ordinal_after),(1,before_clock+1,0,c.trace.iterations))
        self.assertEqual(c.frame,before_clock);self.assertEqual(c.parity,before_clock&1)
        self.assertEqual(bytes(c.floor_before),floor_ref.snapshot(ref))
        self.assertEqual(c.world_changed,0)
        # Original E.1 state/candidate for normal motion, independent of the body
        # oracle. Explicit jumps retain the previously proved air candidate path.
        if not (jump or s.player_ground.jump_flight or p.events&2):
            gref=frame.ground_reference.library('-O0')
            expected_entry=gref.ground_ref_state(C.byref(prior))
            expected=Frame();gref.ground_ref_candidate.argtypes=[C.c_void_p,C.c_void_p,F,C.c_void_p]
            gref.ground_ref_candidate(C.byref(prior),(F*2)(*p.horizontal.velocity),dt,C.byref(expected))
            self.assertEqual(s.player_ground.fall_request,expected_entry)
            self.assertEqual(bytes(c.input),bytes(expected))
        ref.frame_ref_reset();out=(F*3)(*c.input.candidate);v=F(c.before.vy)
        ground=C.c_uint(c.before.grounded);stuck=C.c_uint(c.history_before.stuck);trace=corpus.Trace()
        self.assertEqual(ref.body_ref_step(c.input.previous,out,C.byref(v),c.parity,C.byref(ground),C.byref(stuck),C.byref(trace)),1)
        observed=frame.Observation();ref.frame_ref_observation(C.byref(observed))
        self.assertEqual(bytes(c.trace),bytes(trace));self.assertEqual(bytes(c.queries),bytes(observed))
        self.assertEqual(bytes(s.bridge.floor),floor_ref.snapshot(ref));self.assertEqual(bytes(c.floor_after),bytes(s.bridge.floor))
        self.assertEqual(list(c.after.position),list(out));self.assertEqual((c.after.vy,c.after.grounded),(v.value,ground.value))
        self.assertEqual((p.motion.actor.x,p.motion.actor.y,p.motion.actor.z),tuple(out))
        self.assertEqual((p.motion.vy,p.motion.grounded),(v.value,bool(ground.value)))
        self.assertEqual(bytes(s.body),bytes(c.history_after));self.assertEqual(s.body.stuck,stuck.value)
        self.assertEqual(list(s.body.normal),list(trace.normal));self.assertEqual(bytes(s.player_ground.phase),bytes(c.after))
        for i in range(c.queries.floors):
            self.assertEqual(c.queries.parity[i],c.parity)
            if i:self.assertEqual(bytes(c.queries.before[i]),bytes(c.queries.after[i-1]))
        return c

    def test_known_wall_and_steep_through_actual_runtime_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref=self.seed(lib,opt,(-37.666668,1784,-3751),heading=180,speed=500)
            c=self.compare(lib,s,p,ref,raw=156,heading=180,dt=.05)
            self.assertEqual(p.motion.actor.z,-3754.125);self.assertEqual(c.trace.iteration[0].record,497)
            self.assertEqual((c.trace.iterations,c.trace.hits),(2,1));self.assertEqual(p.horizontal.velocity[1],-500)
            for unique,record in ((91,1701),(93,404),(108,260)):
                case=next(x for x in corpus.cases() if x[0]==f'steep-{unique}')
                s,p,ref=self.seed(lib,opt,case[1],vy=-600,grounded=False)
                c=self.compare(lib,s,p,ref,dt=.05)
                self.assertEqual(c.trace.iteration[0].record,record)
                self.assertEqual((c.trace.iterations,c.trace.hits),(2,1));self.assertFalse(p.motion.grounded)

    def test_five_iteration_fallback_live_clock(self):
        case=next(x for x in corpus.cases() if x[0]=='corner-0-259-0-25')
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref=self.seed(lib,opt,case[1],vy=135,grounded=False,heading=180,speed=500)
            c=self.compare(lib,s,p,ref,raw=156,heading=180,dt=.05)
            self.assertEqual((c.trace.iterations,c.trace.exhausted,s.bridge.ordinal),(5,1,5))
            self.assertEqual(list(c.after.position),list(c.trace.fallback))
            self.assertEqual(bytes(s.bridge.floor),bytes(c.trace.iteration[4].floor))

    def test_normal_trajectories_ledge_slopes_bridge_O0_O2(self):
        from ground_corpus import schedules
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for name in ('flat_walk','plateau_ledge','slope_down','slope_up','bridge_tutorial','bridge_full','floor_reacquisition'):
                pos,vy,g,rows,bits=schedules()[name];hx,hz,dt=rows[0]
                heading=math.degrees(math.atan2(hx,hz)) if hx or hz else 0
                s,p,ref=self.seed(lib,opt,pos,vy,g,bits,heading,math.hypot(hx,hz))
                for i in range(len(rows)):
                    c=self.compare(lib,s,p,ref,raw=156 if hx or hz else 0,heading=heading,dt=dt)
                    if name=='plateau_ledge' and i<3:
                        self.assertEqual(s.player_ground.fall_request,int(i==1))
                if name=='bridge_full':self.assertTrue(p.motion.grounded)
                if name=='bridge_tutorial':self.assertFalse(p.motion.grounded)

    def test_jump_and_airborne_wall_landing_Y_orbit_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for speed,orbit in ((0,False),(500,False),(500,True)):
                s,p,ref=self.seed(lib,opt,(0,1800,0),speed=speed)
                self.compare(lib,s,p,ref,raw=156 if speed else 0,jump=True)
                self.assertTrue(p.events&1);self.assertEqual(p.motion.vy,687.5)
                if speed:self.assertEqual(p.metrics.physics_speed,500)
                for i in range(180):
                    c=self.compare(lib,s,p,ref,raw=156 if speed else 0,orbit=orbit)
                    if p.motion.grounded:break
                else:self.fail('did not land within three seconds')
                self.assertEqual(p.motion.vy,-1)
            s,p,ref=self.seed(lib,opt,(-37.666668,1820,-3751),vy=0,grounded=False,heading=180,speed=500)
            s.player_ground.jump_flight=True
            for i in range(20):
                c=self.compare(lib,s,p,ref,raw=156,heading=180)
                if p.motion.grounded:break
            self.assertTrue(p.motion.grounded)

    def test_long_line_exact_3D_boundary(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for delta in (65.999755859375,66,66.000244140625):
                s,p,ref=self.seed(lib,opt,(0,2000,0),vy=135-delta/.05,grounded=False)
                c=self.compare(lib,s,p,ref,dt=.05)
                actual=F(c.input.candidate[1]-c.input.previous[1]).value
                self.assertEqual(abs(actual),delta)
                self.assertEqual(bool(c.trace.iteration[0].paths&64),delta>66)
