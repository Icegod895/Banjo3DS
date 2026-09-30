"""Host-C production vs ORIGINAL source reference, independent of the viewer."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

from horizontal_reference import ROOT, F, FP, FLAGS, CASES, FIELDS, Reference, f, golden, library, norm, trace

class State(C.Structure):
    _fields_=[('magnitude',F),('desired',F),('speed',F),('target',F*2),('velocity',F*2),
              ('candidate',F*2),('accepted',F*2),('ideal',F),('visible',F),('heading',F)]
class Metrics(C.Structure):
    _fields_=[('magnitude',F),('target_speed',F),('physics_speed',F),('accepted_speed',F),('accepted',F*2)]

def packed(values):return struct.pack('>'+str(len(values))+'f',*values)
def neighbor(x,offset):
    bits=struct.unpack('>I',struct.pack('>f',x))[0]
    return struct.unpack('>f',struct.pack('>I',bits+offset))[0]

class HorizontalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-horizontal-test-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                str(ROOT/'tools/banjo3ds/horizontal/horizontal.c'),'-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out))
            for name,args,result in (
                ('n64_axis',[C.c_int,C.c_bool],F),('magnitude',[F,F],F),('target',[F],F),
                ('yaw',[F,F,F],F),('should_skid',[F,F,F],C.c_bool),('skid_target',[F,F],F),
                ('init',[C.POINTER(State),F],None),('intent',[C.POINTER(State),F,F],C.c_bool),
                ('takeoff',[C.POINTER(State)],None),('step',[C.POINTER(State),C.c_int,F],C.c_bool),
                ('accept',[C.POINTER(State),F,F],None),('metrics',[C.POINTER(State),F],Metrics)):
                fn=getattr(lib,'banjo_horizontal_'+name);fn.argtypes=args;fn.restype=result
            cls.libs.append(lib)
        cls.fixture=json.loads((Path(__file__).parent/'fixtures/horizontal_golden.json').read_text())

    def state(self,lib,yaw=0):
        s=State();lib.banjo_horizontal_init(C.byref(s),yaw);return s
    def intent(self,lib,s,m=1,yaw=0):
        self.assertTrue(lib.banjo_horizontal_intent(C.byref(s),m,yaw))
    def step(self,lib,s,mode=0,dt=1/60):
        self.assertTrue(lib.banjo_horizontal_step(C.byref(s),mode,dt))

    def test_reference_goldens_frozen_sources_and_O0_O2(self):
        for opt in ('-O0','-O2'):
            self.assertEqual(golden(opt),self.fixture)

    def test_production_traces_bit_exact_O0_O2(self):
        for lib in self.libs:
            for name in CASES:
                with self.subTest(case=name,library=lib._name):
                    s=self.state(lib);position=[0.,0.];path=0.;stream=[];dt=f(1/60)
                    if name.startswith('ground_') or name in ('jump_steady_full','jump_neutral_before','jump_release_after','air_90','air_180'):
                        s.velocity[1]=500
                    for frame,(command,expected) in enumerate(trace(name),1):
                        self.intent(lib,s,command['m'],command['yaw'])
                        if command['takeoff']:lib.banjo_horizontal_takeoff(C.byref(s))
                        if command.get('idle_entry'):s.speed=0
                        if command.get('skid_enter'):
                            self.assertTrue(lib.banjo_horizontal_should_skid(s.ideal,s.visible,norm(*s.velocity)))
                        if 'skid_phase' in command:
                            s.speed=lib.banjo_horizontal_skid_target(command['skid_phase'],command['skid_start'])
                        if command.get('skid_exit'):s.visible=f((s.visible-180)%360)
                        self.step(lib,s,command['mode'],dt)
                        lib.banjo_horizontal_accept(C.byref(s),*s.candidate)
                        metrics=lib.banjo_horizontal_metrics(C.byref(s),dt)
                        position=[f(p+d) for p,d in zip(position,s.accepted)]
                        path=f(path+norm(*s.accepted))
                        row=list(struct.unpack('=14f',bytes(s)))+[metrics.physics_speed,metrics.accepted_speed,*position,path]
                        self.assertEqual(packed(row),packed(expected),(name,frame,[(k,a,b) for k,a,b in zip(FIELDS,row,expected) if packed([a])!=packed([b])]))
                        stream.append(packed(row))
                    self.assertEqual(hashlib.sha256(b''.join(stream)).hexdigest(),self.fixture['cases'][name]['sha256'])

    def test_n64_axis_exhaustive_signed_byte_and_magnitude(self):
        ref=library()
        for lib in self.libs:
            for raw in range(-128,128):
                for y in (False,True):
                    self.assertEqual(lib.banjo_horizontal_n64_axis(raw,y),ref.ref_axis(raw,61 if y else 59))
            for x,y in ((0,0),(7,-7),(59,0),(0,61),(59,61),(14,0),(-23,31)):
                a=lib.banjo_horizontal_n64_axis(x,False);b=lib.banjo_horizontal_n64_axis(y,True)
                self.assertEqual(lib.banjo_horizontal_magnitude(a,b),ref.ref_magnitude(a,b))
            self.assertEqual(lib.banjo_horizontal_target(lib.banjo_horizontal_n64_axis(13,False)),0)
            self.assertGreater(lib.banjo_horizontal_target(lib.banjo_horizontal_n64_axis(14,False)),30)
            self.assertEqual(lib.banjo_horizontal_n64_axis(7,False),0)
            self.assertEqual(lib.banjo_horizontal_magnitude(1,1),1)

    def test_target_boundaries_equality_and_adjacent_float32(self):
        ref=library()
        for lib in self.libs:
            for boundary,speed in ((.12,0),(.2,80),(.5,150),(.75,225),(1,500)):
                self.assertEqual(lib.banjo_horizontal_target(boundary),speed)
                for m in (neighbor(boundary,-1),f(boundary),neighbor(boundary,1)):
                    self.assertEqual(lib.banjo_horizontal_target(m),ref.ref_target(m))
            self.assertGreater(lib.banjo_horizontal_target(neighbor(.12,1)),30)
            for m in (0,.01,.125,.25,.375,.6,.9):
                self.assertEqual(lib.banjo_horizontal_target(m),ref.ref_target(m))

    def test_float_response_operation_order_and_pre_snap_displacement(self):
        rng=random.Random(47);ref=library()
        cases=[(500,0,.00009,0,0),(0,0,.00009,-.00009,1/60)]
        cases += [(rng.uniform(0,500),rng.uniform(0,359),rng.uniform(-500,500),rng.uniform(-500,500),rng.choice((1/60,1/30,.05))) for _ in range(100)]
        for lib in self.libs:
            for speed,yaw,vx,vz,dt in cases:
                for mode,c in ((0,.29),(1,.07)):
                    s=self.state(lib,yaw);s.speed=speed;s.velocity[:]=[vx,vz]
                    out=(F*6)();ref.ref_response(s.speed,s.heading,*s.velocity,dt,c,out)
                    self.step(lib,s,mode,dt)
                    self.assertEqual(packed([*s.target,*s.velocity,*s.candidate]),packed(list(out)))
            s=self.state(lib);s.velocity[0]=.00009
            self.step(lib,s)
            self.assertEqual(s.velocity[0],0)
            self.assertGreater(s.candidate[0],0) # original displacement copied before snap

    def test_takeoff_overwrites_instead_of_adding_momentum(self):
        for lib in self.libs:
            for initial,m,yaw in ((0,0,0),(0,1,0),(500,1,0),(500,0,0),(500,1,90),(500,1,180)):
                s=self.state(lib);s.velocity[1]=initial;self.intent(lib,s,m,yaw)
                lib.banjo_horizontal_takeoff(C.byref(s))
                out=(F*2)();library().ref_vector(library().ref_target(m),yaw,out)
                self.assertEqual(packed(s.velocity),packed(out))
            s=self.state(lib);self.intent(lib,s);lib.banjo_horizontal_takeoff(C.byref(s))
            self.intent(lib,s,0);self.step(lib,s,1)
            self.assertGreater(s.velocity[1],0);self.assertLess(s.velocity[1],500)
            self.assertEqual(s.speed,0)

    def test_ground_heading_lags_input_one_update_not_visible_yaw(self):
        for lib in self.libs:
            s=self.state(lib);s.velocity[1]=500
            self.intent(lib,s,1,90);self.step(lib,s)
            self.assertEqual((s.heading,s.ideal),(0,90))
            self.assertEqual(s.target[0],0);self.assertEqual(s.velocity[1],500)
            self.assertGreater(s.visible,0);self.assertLess(s.visible,90)
            self.intent(lib,s,1,90);self.step(lib,s)
            self.assertEqual(s.heading,90)
            self.assertGreater(s.velocity[0],0);self.assertGreater(s.velocity[1],0)
            self.assertNotEqual(s.heading,s.visible)

    def test_air_heading_changes_without_visible_facing_change(self):
        for lib in self.libs:
            for yaw in (90,180):
                s=self.state(lib);self.intent(lib,s);lib.banjo_horizontal_takeoff(C.byref(s))
                self.intent(lib,s,1,yaw);self.step(lib,s,1)
                self.assertEqual((s.heading,s.ideal,s.visible),(yaw,0,0))
                self.assertLess(s.velocity[1],500)
            self.intent(lib,s,0,270);self.step(lib,s,1)
            self.assertEqual(s.heading,180) # neutral retains last movement heading

    def test_visible_yaw_wrap_minimum_step_cap_and_no_overshoot(self):
        ref=library()
        for lib in self.libs:
            for visible,ideal in ((0,180),(180,0),(359,1),(1,359),(0,.01),(10,10),(0,90)):
                for dt in (0,1/60,1/30,.05):
                    self.assertEqual(lib.banjo_horizontal_yaw(visible,ideal,dt),ref.ref_yaw(visible,ideal,dt))
            self.assertAlmostEqual(lib.banjo_horizontal_yaw(0,180,1/60),700*f(1/60),places=5)
            self.assertEqual(lib.banjo_horizontal_yaw(0,.01,1/60),f(.01))

    def test_skid_strict_boundaries_wrap_and_target_ramp(self):
        for lib in self.libs:
            for angle in (134,135,neighbor(135,1),180,225,359):
                for speed in (124,125,neighbor(125,1),500):
                    self.assertEqual(lib.banjo_horizontal_should_skid(angle,0,speed),bool(library().ref_skid(angle,0,speed)))
            self.assertFalse(lib.banjo_horizontal_should_skid(180,0,125))
            self.assertFalse(lib.banjo_horizontal_should_skid(135,0,500))
            self.assertTrue(lib.banjo_horizontal_should_skid(180,0,500))
            for phase in (0,neighbor(.18,-1),.18,neighbor(.18,1),.5,.75,1,1.1):
                for speed in (0,126,500):
                    self.assertEqual(lib.banjo_horizontal_skid_target(phase,speed),library().ref_skid_target(phase,speed))
            self.assertEqual(lib.banjo_horizontal_skid_target(.18,500),500)
            self.assertEqual(lib.banjo_horizontal_skid_target(1,500),0)

    def test_intent_target_actual_and_accepted_are_independent(self):
        for lib in self.libs:
            s=self.state(lib);s.velocity[1]=500;self.intent(lib,s,0)
            self.step(lib,s)
            self.assertEqual((s.magnitude,s.speed),(0,0))
            self.assertGreater(s.velocity[1],0);self.assertGreater(s.candidate[1],0)
            velocity=bytes(s.velocity)
            # Collision refuses or clips the candidate, without inventing a velocity reset.
            for dx,dz in ((0,0),(0,1),(1,2)):
                lib.banjo_horizontal_accept(C.byref(s),dx,dz)
                m=lib.banjo_horizontal_metrics(C.byref(s),f(1/60))
                self.assertEqual((m.magnitude,m.target_speed),(0,0))
                self.assertGreater(m.physics_speed,0)
                self.assertEqual(m.accepted_speed,f(norm(dx,dz)/f(1/60)))
                self.assertEqual(list(m.accepted),[dx,dz]);self.assertEqual(bytes(s.velocity),velocity)
            self.step(lib,s);self.assertEqual(list(s.accepted),[0,0])
            self.assertEqual(lib.banjo_horizontal_metrics(C.byref(s),0).accepted_speed,0)

    def test_invalid_dt_intent_mode_leave_state_unchanged(self):
        for lib in self.libs:
            s=self.state(lib);self.intent(lib,s);before=bytes(s)
            for dt in (-1,float('nan'),float('inf'),.051):
                self.assertFalse(lib.banjo_horizontal_step(C.byref(s),0,dt));self.assertEqual(bytes(s),before)
            for m,yaw in ((-1,0),(1.1,0),(float('nan'),0),(1,float('inf'))):
                self.assertFalse(lib.banjo_horizontal_intent(C.byref(s),m,yaw));self.assertEqual(bytes(s),before)
            self.assertFalse(lib.banjo_horizontal_step(C.byref(s),3,.01));self.assertEqual(bytes(s),before)

    def test_M47A_quantitative_checkpoints_not_animation_inferred(self):
        rows=self.fixture['cases']
        # M4.7A was binary64/host trig; close numerical agreement, not a bit golden.
        for case,frame,speed,distance in (('start_stop','120',500,942.529),('start_stop','180',.041,991.663),
              ('jump_release_after','60',61.106,210.016),('ground_90','60',499.952,470.680),
              ('ground_180_skid','60',498.708,401.757)):
            self.assertAlmostEqual(rows[case]['checkpoints'][frame][14],speed,delta=.02)
            self.assertAlmostEqual(rows[case]['checkpoints'][frame][18],distance,delta=.02)
        self.assertEqual(C.sizeof(State),56);self.assertEqual(C.sizeof(Metrics),24)

if __name__=='__main__':unittest.main()
