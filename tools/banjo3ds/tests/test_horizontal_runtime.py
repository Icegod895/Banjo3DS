"""M4.7C actual viewer path, both optimization levels; no graphics dependency."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import struct
import unittest

import test_jump_runtime as runtime
from test_jump import floor, arrays, Motion
from test_movement import Actor
from test_walk_runtime import Vertex, TOTAL, FIRST, COUNT
from test_horizontal import State, Metrics, packed, neighbor
from horizontal_reference import Reference, trace, f
import floor_step_reference as floors

F=C.c_float

class HorizontalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime.JumpRuntimeTests.setUpClass.__func__(cls)
        cls.checkpoints=json.loads((Path(__file__).parent/'fixtures/horizontal_golden.json').read_text())['cases']
        for lib in cls.libs:
            lib.banjo_horizontal_init.argtypes=[C.POINTER(State),F]
            lib.banjo_horizontal_intent.argtypes=[C.POINTER(State),F,F]
            lib.banjo_horizontal_takeoff.argtypes=[C.POINTER(State)]
            lib.banjo_gait_motion_select.argtypes=[C.POINTER(runtime.GaitMotion),C.POINTER(Metrics),F]
            lib.banjo_gait_motion_select.restype=C.c_int
            lib.banjo_gait_motion_duration.argtypes=[C.c_int,F]
            lib.banjo_gait_motion_duration.restype=F
        cls.flat=floor(0,x0=-5000,x1=5000,z0=-5000,z1=5000)

    def player(self,y=0,yaw=0):
        return runtime.Player(motion=Motion(actor=Actor(0,y,0,yaw),grounded=True))

    def move(self,lib,p,m=1,yaw=0,dt=1/60,jump=False,camera=False,mesh=None):
        # Cardinal Circle Pad; normalized magnitude exactly equals m for these cases.
        v,t=self.flat if mesh is None else mesh
        raw=0 if m==0 else 20+136*m
        lib.playerRuntimeMove(C.byref(p),0,raw,-yaw,dt,jump,camera,v,t,len(t))

    def steady(self,lib,y=0,yaw=0):
        p=self.player(y,yaw)
        lib.banjo_horizontal_init(C.byref(p.horizontal),yaw)
        lib.banjo_horizontal_intent(C.byref(p.horizontal),1,yaw)
        lib.banjo_horizontal_takeoff(C.byref(p.horizontal))
        p.horizontalInitialized=True;p.locomotion.gait=4
        return p

    def compare(self,p,row):
        h=p.horizontal
        # Position subtraction rounds accepted displacement independently. Compare
        # target/physics/candidate/yaw bit-exact, not rounded acceptedSpeed.
        actual=[h.magnitude,h.desired,h.speed,*h.target,*h.velocity,*h.candidate]
        self.assertEqual(packed(actual),packed(row[:9]))
        self.assertEqual(packed([h.ideal,h.visible,h.heading]),packed(row[11:14]))
        self.assertEqual(p.metrics.physics_speed,row[14])

    def test_full_acceleration_coasting_and_fraction_traces_bit_exact(self):
        for lib in self.libs:
            for name in ('start_stop','constant_25','constant_50','constant_75','constant_100'):
                p=self.player()
                for frame,(command,row) in enumerate(trace(name),1):
                    self.move(lib,p,command['m'])
                    self.compare(p,row)
                    self.assertEqual((p.motion.actor.x,p.motion.actor.z),tuple(row[16:18]))
                    checkpoint=self.checkpoints[name]['checkpoints'].get(str(frame))
                    if checkpoint:self.compare(p,checkpoint)
                    if name=='start_stop' and frame==121:
                        self.assertEqual(p.metrics.magnitude,0)
                        self.assertGreater(p.metrics.physics_speed,400)
                        self.assertGreater(p.metrics.accepted_speed,0)
                if name=='constant_100':self.assertAlmostEqual(p.metrics.physics_speed,500,delta=.001)

    def test_ground_90_delay_and_180_without_skid(self):
        for lib in self.libs:
            for yaw in (90,180):
                p=self.steady(lib);ref=Reference();ref.velocity=[0,500]
                for frame in range(60):
                    self.move(lib,p,yaw=yaw)
                    ref.intent(1,p.horizontal.desired);ref.step(0,f(1/60))
                    self.compare(p,ref.snapshot(f(1/60)))
                    if frame==0:
                        self.assertEqual(p.horizontal.heading,0)
                        self.assertEqual(p.horizontal.ideal,yaw)
                        self.assertNotEqual(p.motion.actor.yaw,yaw)
                    if yaw==90:
                        self.compare(p,list(trace('ground_90'))[frame][1])
                self.assertEqual(p.locomotion.gait,4)  # no skid controller

    def test_takeoff_air_release_and_steering_match_original_reference(self):
        for lib in self.libs:
            for name in ('jump_rest_neutral','jump_rest_full','jump_steady_full',
                         'jump_neutral_before','jump_release_after','air_90','air_180'):
                p=self.steady(lib) if name not in ('jump_rest_neutral','jump_rest_full') else self.player()
                for frame,(command,row) in enumerate(trace(name)):
                    self.move(lib,p,command['m'],command['yaw'],jump=frame==0)
                    self.compare(p,row)
                    self.assertFalse(p.motion.grounded)
                    if frame==0:
                        self.assertTrue(p.events&1)
                        self.assertEqual(p.metrics.physics_speed,500 if command['m'] else 0)
                    if frame==1 and name=='jump_release_after':
                        self.assertEqual(p.metrics.magnitude,0)
                        self.assertGreater(p.metrics.physics_speed,480)
                    if name in ('air_90','air_180'):
                        self.assertEqual(p.motion.actor.yaw,0)

    def test_Y_orbit_removes_intent_not_momentum_or_gravity(self):
        for lib in self.libs:
            for jump in (False,True):
                p=self.steady(lib)
                if jump:self.move(lib,p,jump=True)
                x,z=p.motion.actor.x,p.motion.actor.z;vy=p.motion.vy
                self.move(lib,p,camera=True,yaw=90)
                self.assertEqual(p.metrics.magnitude,0)
                self.assertEqual(p.metrics.target_speed,0)
                self.assertGreater(p.metrics.physics_speed,0)
                self.assertLess(p.metrics.physics_speed,500)
                self.assertGreater(math.hypot(p.motion.actor.x-x,p.motion.actor.z-z),0)
                if jump:self.assertLess(p.motion.vy,vy)
                else:self.assertEqual(p.motion.actor.y,0)

    def test_floor_rejection_preserves_velocity_candidate_and_position(self):
        for lib in self.libs:
            p=self.steady(lib)
            # Start is supported, but the first candidate segment has no floor.
            self.move(lib,p,dt=.05,mesh=floor(0,z0=-1,z1=1))
            self.assertEqual((p.motion.actor.x,p.motion.actor.y,p.motion.actor.z),(0,0,0))
            self.assertEqual(p.metrics.physics_speed,500)
            self.assertEqual(tuple(p.horizontal.candidate),(0,25))
            self.assertEqual(tuple(p.horizontal.accepted),(0,0))
            self.assertEqual(p.metrics.accepted_speed,0)
            self.assertFalse(p.accepted);self.assertEqual(p.metrics.magnitude,1)
            self.assertEqual(p.locomotion.gait,4)

    def test_record_1196_via_actual_runtime_500_times_005(self):
        vertices,triangles=floors.read_14cf()
        self.assertEqual(triangles[1196],floors.RECORD_1196)
        mesh=arrays(vertices,triangles)
        for lib in self.libs:
            for speed,dt in ((150,.05),(500,1/60),(500,.05)):
                p=self.steady(lib,yaw=135)
                p.motion.actor=Actor(*floors.START_1196,135)
                m=.5 if speed==150 else 1
                lib.banjo_horizontal_intent(C.byref(p.horizontal),m,135)
                lib.banjo_horizontal_takeoff(C.byref(p.horizontal))
                p.locomotion.gait=2 if speed==150 else 4
                self.move(lib,p,m=m,yaw=135,dt=dt,mesh=mesh)
                self.assertTrue(p.accepted);self.assertTrue(p.motion.grounded)
                expected,_=floors.follow(vertices,triangles,floors.START_1196,(p.motion.actor.x,p.motion.actor.z))
                self.assertAlmostEqual(p.motion.actor.y,expected,delta=.001)
                if speed==500 and dt==.05:
                    self.assertAlmostEqual(p.motion.actor.y,floors.EXPECTED_END_Y,delta=.001)
                    self.assertAlmostEqual(math.hypot(*p.horizontal.candidate),25,delta=.00001)
                    self.assertGreater(floors.START_1196[1]-p.motion.actor.y,30)

    def test_gait_input_zones_velocity_exits_timer_and_durations(self):
        for lib in self.libs:
            def select(gait,m,speed,timer=0,accepted=0):
                s=runtime.GaitMotion(timer,gait);metrics=Metrics(m,0,speed,accepted,(F*2)(0,0))
                result=lib.banjo_gait_motion_select(C.byref(s),C.byref(metrics),f(1/60))
                return result,s.timer
            for m,gait in ((.12,0),(.2,1),(.5,2),(.75,3),(1,4)):
                self.assertEqual(select(0,m,500)[0],gait)
                if m<1:self.assertEqual(select(0,neighbor(m,1),0)[0],gait+1)
            for gait,limit in ((1,1),(2,3),(4,18)):
                self.assertEqual(select(gait,0,limit)[0],0)
                self.assertEqual(select(gait,0,neighbor(limit,1))[0],gait)
            self.assertEqual(select(3,0,150,timer=.3)[0],3)
            self.assertEqual(select(3,0,150)[0],2)
            self.assertEqual(select(3,0,neighbor(150,1))[0],3)
            self.assertEqual(select(4,.75,225,timer=.3)[0],4)
            self.assertEqual(select(4,.75,225)[0],3)
            self.assertEqual(select(4,.5,150,timer=.3)[0],2)
            self.assertEqual(select(4,.5,neighbor(150,1))[0],4)
            for accepted in (0,50,500):self.assertEqual(select(4,0,300,accepted=accepted)[0],4)
            for gait,lo,hi,dlo,dhi in ((1,30,80,1.8,1.2),(2,80,150,1.3,.6),
                                      (3,150,225,.92,.58),(4,225,500,.54,.44)):
                for speed in (0,lo,hi,500):
                    expected=f(f(f(f(speed-lo)/f(hi-lo))*f(f(dhi)-f(dlo)))+f(dlo))
                    expected=min(f(1.5),max(f(.3),expected))
                    self.assertEqual(lib.banjo_gait_motion_duration(gait,speed),expected)

    def test_walk_fast_phase_and_interrupted_blend_on_new_metrics(self):
        for lib in self.libs:
            p=self.player()
            for m in (.75,1,.75,.5,.2,1,0):
                oldclip=p.gait.gait;oldphase=p.gait.phase;oldfactor=p.gait.factor
                mixed=bytes(p.gait.pose.bones)
                self.move(lib,p,m=m)
                self.assertTrue(lib.playerRuntimeAnimate(C.byref(p),self.packet,len(self.packet),f(1/60)))
                new=p.gait.gait
                if oldclip in (3,4) and new in (3,4):
                    self.assertGreater(p.gait.phase,oldphase)
                    self.assertGreaterEqual(p.gait.factor,oldfactor)
                elif oldclip and new!=oldclip:
                    self.assertEqual(bytes(p.gait.source),mixed)
                    self.assertLess(p.gait.factor,1)

    def test_ground_animation_only_actor_XYZ_and_dt_cap(self):
        for lib in self.libs:
            a=self.steady(lib);b=self.steady(lib)
            self.move(lib,a,dt=.5);self.move(lib,b,dt=.05)
            self.assertEqual(bytes(a),bytes(b))
            position=bytes(a.motion.actor);h=bytes(a.horizontal)
            self.move(lib,a,dt=0)
            self.assertEqual(bytes(a.motion.actor),position);self.assertEqual(bytes(a.horizontal),h)
            vertices=(Vertex*TOTAL)();C.memset(vertices,0x55,C.sizeof(vertices));original=bytes(vertices)
            p=self.player();stride=C.sizeof(Vertex)
            for m in (1,0,.25,.5,.75):
                self.move(lib,p,m=m)
                self.assertTrue(lib.playerRuntimeAnimate(C.byref(p),self.packet,len(self.packet),.025))
                self.assertTrue(lib.playerRuntimeWriteVertices(C.byref(p),self.packet,vertices,TOTAL,FIRST,COUNT,stride))
                result=bytes(vertices)
                self.assertEqual(result[:FIRST*stride],original[:FIRST*stride])
                self.assertEqual(result[(FIRST+COUNT)*stride:],original[(FIRST+COUNT)*stride:])
                for i in range(FIRST,FIRST+COUNT):self.assertEqual(result[i*stride+12:(i+1)*stride],original[i*stride+12:(i+1)*stride])
