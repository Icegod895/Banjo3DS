"""E.1B state/candidate preservation through E.2B actual body/floor dispatch.
No old fail-closed movement is substituted into the live runtime under test.
"""
import ctypes as C
import math
import unittest
import ground_corpus as corpus
import ground_reference as original
import floor_state_reference as floor_ref
import test_body_frame as body_frame
import body_corpus as body
from test_ground_falling import bind_reference,reference_world
import test_camera_runtime as runtime
from test_floor_state import State as Floor
from test_horizontal import State as Horizontal
from test_movement import Actor
F=C.c_float

class GroundRuntimeTests(unittest.TestCase):
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move
    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:
            lib.banjo_horizontal_init.argtypes=[C.POINTER(Horizontal),F]

    def seed(self,lib,opt,pos,vy=-1,grounded=True,bits=0x9db1,heading=0,speed=500,warm=True):
        s,p=self.start(lib,pos,heading);lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
        # Establish the SAME already-published lifecycle as the E.1 fixtures.
        # No production update is fabricated: these are explicit initial states.
        s.world_bridge.initialized=1;s.world_bridge.alive=bool(bits==0)
        for i,offset in enumerate((0,0,-5000) if bits==0 else (-5000,-5000,0)):
            s.world_bridge.mesh[i].applied=offset;s.world_bridge.mesh[i].offset=offset
            s.world_bridge.mesh[i].elapsed=F(.00001).value;s.world_bridge.mesh[i].completed=1
        ref,_=body_frame.setup_reference(opt,pos,bits)
        ref.floor_ref_init();ref.body_ref_init(0,0)
        if warm:
            for frame in range(6):ref.floor_ref_step((F*3)(*pos),56,0x400000,frame&1)
        snapshot=floor_ref.snapshot(ref);C.memmove(C.byref(s.bridge.floor),snapshot,len(snapshot))
        p.motion.vy=vy;p.motion.grounded=grounded
        phase=s.player_ground.phase;phase.position[:]=pos;phase.vy=vy;phase.grounded=grounded
        phase.height=s.bridge.floor.height if warm else pos[1];phase.falling=0
        s.player_ground.jump_flight=False
        lib.banjo_horizontal_init(C.byref(p.horizontal),heading);p.horizontalInitialized=True
        p.horizontal.velocity[:]=(speed*math.sin(math.radians(heading)),speed*math.cos(math.radians(heading)))
        p.locomotion.gait=4
        return s,p,ref,corpus.State.from_buffer_copy(phase)

    def compare_step(self,lib,s,p,ref,want,frame,heading=0,dt=1/60,raw=156,orbit=False):
        # Normal gameplay exits FALL after seeing previous-frame landing.
        if want.grounded:want.falling=0
        gref=original.library("-O0");bind_reference(gref)
        entry=gref.ground_ref_state(C.byref(want))
        previous_stuck=s.body.stuck
        status=self.move(lib,s,p,0,raw,-heading,dt=dt,orbit=orbit)
        self.assertNotIn(status,(-1,-3))
        f=corpus.Frame();gref.ground_ref_candidate(C.byref(want),(F*2)(*p.horizontal.velocity),dt,C.byref(f))
        self.assertEqual(list(s.pre),list(f.candidate))
        # E.1 remains the oracle for the once-per-frame state/physics phase.
        # Contact now uses the original E.2 loop, including repeated floor calls.
        out=(F*3)(*f.candidate);vy=F(want.vy);ground=C.c_uint(want.grounded)
        stuck=C.c_uint(previous_stuck);trace=body.Trace();ref.frame_ref_reset()
        self.assertEqual(ref.body_ref_step(f.previous,out,C.byref(vy),frame&1,C.byref(ground),C.byref(stuck),C.byref(trace)),1)
        want.position[:]=out;want.vy=vy.value;want.grounded=ground.value
        want.height=Floor.from_buffer_copy(floor_ref.snapshot(ref)).height
        self.assertEqual(s.body.stuck,stuck.value)
        self.assertEqual([p.motion.actor.x,p.motion.actor.y,p.motion.actor.z],list(want.position))
        self.assertEqual((p.motion.vy,p.motion.grounded),(want.vy,bool(want.grounded)))
        self.assertEqual(bytes(s.bridge.floor),floor_ref.snapshot(ref))
        self.assertEqual(s.player_ground.fall_request,entry)
        self.assertEqual((s.calls,s.bridge.ordinal,s.bridge.frame),(1,trace.iterations,frame+1))
        return entry

    @unittest.skip("superseded by test_body_runtime's E.2B cadence oracle")
    def test_real_schedules_integrated_original_floor_phase_O0_O2(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for name in ('plateau_ledge','flat_walk','slope_down','slope_up','floor_reacquisition','bridge_tutorial','bridge_full'):
                pos,vy,ground,rows,bits=corpus.schedules()[name]
                hx,hz,dt=rows[0];heading=math.degrees(math.atan2(hx,hz)) if hx or hz else 0
                speed=math.hypot(hx,hz);raw=156 if speed else 0
                s,p,ref,want=self.seed(lib,opt,pos,vy,ground,bits,heading,speed)
                for frame in range(len(rows)):
                    self.compare_step(lib,s,p,ref,want,frame,heading,dt,raw)
                if name=='bridge_full':self.assertTrue(p.motion.grounded);self.assertGreaterEqual(p.motion.actor.y,1576)
                if name=='bridge_tutorial':self.assertFalse(p.motion.grounded);self.assertLess(p.motion.actor.y,1576)

    def test_exact_ledge_and_delayed_fall(self):
        expected=[(1799.2332763671875,400.0001220703125,0),
                  (1797.716552734375,408.3334655761719,1),
                  (1795.4498291015625,416.66680908203125,0)]
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref,want=self.seed(lib,opt,(0,1800,391.666779))
            for i,(y,z,event) in enumerate(expected):
                self.assertEqual(self.compare_step(lib,s,p,ref,want,i),event)
                self.assertEqual((p.motion.actor.y,p.motion.actor.z),(y,z));self.assertFalse(p.motion.grounded)
            self.assertEqual(p.events&1,0)

    @unittest.skip("superseded by test_body_runtime's E.2B cadence oracle")
    def test_fresh_init_flat_contact_uses_actual_original_query(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref,want=self.seed(lib,opt,(0,1800,0),vy=0,speed=0,warm=False)
            for i in range(8):self.compare_step(lib,s,p,ref,want,i,raw=0)
            self.assertTrue(p.motion.grounded);self.assertEqual(p.motion.vy,-1)

    @unittest.skip("superseded by test_body_runtime's airborne body corpus")
    def test_jump_keeps_impulse_body_landing_and_return_to_normal_gravity(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref,want=self.seed(lib,opt,(0,1800,0),speed=0)
            self.move(lib,s,p,jump=True)
            self.assertTrue(p.events&1);self.assertEqual(p.motion.vy,687.5);self.assertTrue(s.player_ground.jump_flight)
            for i in range(150):
                self.move(lib,s,p)
                if p.events&2:break
            else:self.fail('jump never landed')
            self.assertEqual(p.motion.vy,-1);self.assertFalse(s.player_ground.jump_flight)
            self.move(lib,s,p);self.assertEqual(p.motion.vy,-1);self.assertTrue(p.motion.grounded)

    def test_boundary_and_orbit_do_not_cancel_gravity(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for gap in corpus.neighbors(60):
                s,p,ref,want=self.seed(lib,opt,(0,1800+gap,0),grounded=False,speed=0)
                # Threshold compares original float32 subtraction, not the
                # requested Python decimal before position rounding.
                want.height=1800;s.player_ground.phase.height=1800
                self.compare_step(lib,s,p,ref,want,0,raw=156,orbit=True)
                self.assertEqual(p.metrics.magnitude,0);self.assertLess(p.motion.vy,0)

    @unittest.skip("superseded by test_body_runtime's E.2B wall/steep corpus")
    def test_known_E1_only_limitations_receive_original_body_correction(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            for name in ('steep_no_body_LIMITATION','wall_no_body_LIMITATION'):
                pos,vy,ground,rows,bits=corpus.schedules()[name];hx,hz,dt=rows[0]
                heading=math.degrees(math.atan2(hx,hz)) if hx or hz else 0
                s,p,ref,want=self.seed(lib,opt,pos,vy,ground,bits,heading,math.hypot(hx,hz))
                self.compare_step(lib,s,p,ref,want,0,heading,dt,156 if hz else 0)
                if name.startswith('steep'):self.assertLess(p.motion.actor.y,2014.666667);self.assertFalse(p.motion.grounded)
                else:self.assertEqual(p.motion.actor.z,-3754.125)

    @unittest.skip("superseded by test_body_runtime's bridge-state corpus")
    def test_bridge_tutorial_actual_entry_and_no_grounded_follow_fallback(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref,want=self.seed(lib,opt,(0,1576,-1770),bits=0,heading=180)
            lost=False
            for frame in range(15):
                self.compare_step(lib,s,p,ref,want,frame,heading=180)
                if not p.motion.grounded:lost=True
            self.assertTrue(lost);self.assertLess(p.motion.actor.z,-1800)
            s,p,ref,want=self.seed(lib,opt,(0,1576,-1770),bits=0x9db1,heading=180)
            for frame in range(15):self.compare_step(lib,s,p,ref,want,frame,heading=180)
            self.assertTrue(p.motion.grounded)
        from pathlib import Path
        from segment_reference import ROOT
        code=(ROOT/'platform/3ds/source/player_ground.c').read_text()
        self.assertNotIn('movementFollowFloor',code)
        runtime_code=(ROOT/'platform/3ds/source/camera_runtime.c').read_text()
        self.assertIn('playerGroundStep,&ground',runtime_code)
        self.assertNotIn('playerRuntimeMoveOverlay(',runtime_code)

    def test_diagnostic_recovery_phase_and_floor_lifecycle(self):
        for opt,lib in zip(('-O0','-O2'),self.libs):
            s,p,ref,want=self.seed(lib,opt,(0,1800,0),speed=0)
            self.move(lib,s,p)
            p.motion.actor=Actor(9000,-1100,9000,0);p.motion.grounded=False;p.motion.vy=-1000
            self.move(lib,s,p)
            self.assertTrue(p.events&4);self.assertTrue(p.motion.grounded)
            self.assertEqual(s.bridge.ordinal,2)
            self.assertEqual(s.player_ground.phase.height,s.bridge.floor.height)
            self.assertEqual(list(s.player_ground.phase.position),[p.motion.actor.x,p.motion.actor.y,p.motion.actor.z])
            self.assertEqual(s.player_ground.phase.vy,0)
            self.move(lib,s,p)
            self.assertTrue(p.motion.grounded);self.assertEqual(s.player_ground.fall_request,0)
