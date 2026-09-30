"""Host-only C jump, swept landing and pose controller; viewer unchanged."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT
from test_walk_pose import Pose
from test_movement import Vertex, Triangle, Actor
from jump_reference import JumpTransition, animation, f
from transition_reference import pack
from tools.banjo3ds.pose_binding import export_gait_packet, export_jump_packet
from tools.banjo3ds.floor_collision import scene_collision

F=C.c_float
Bones=(F*10)*109
CLIPS={'0003':0,'006F':1,'0002':2,'000C':3,'0008':4}
class Motion(C.Structure):
    _fields_=[('actor',Actor),('vy',F),('safe',F*3),('grounded',C.c_bool),('has_safe',C.c_bool)]
class Animation(C.Structure):
    _fields_=[('pose',Pose),('source',Bones),('phase',F),('factor',F),('duration',F),('transition',F),('clip',C.c_uint8),('segment',C.c_uint8)]
def digest(rows,width):return hashlib.sha256(pack(rows,width)).hexdigest()
def arrays(vertices,triangles):
    return (Vertex*len(vertices))(*(Vertex(*v) for v in vertices)),(Triangle*len(triangles))(*(Triangle(*t) for t in triangles))
def floor(y=1800,flags=0,reverse=False,x0=-100,x1=100,z0=-100,z1=100):
    tris=[(0,1,2),(2,1,3)]
    if reverse:tris=[tuple(reversed(t)) for t in tris]
    return arrays([(x0,y,z0),(x0,y,z1),(x1,y,z0),(x1,y,z1)],[(*t,0,flags) for t in tris])
def combine(*meshes):
    v,t=[],[]
    for vv,tt in meshes:
        base=len(v);v.extend((a.x,a.y,a.z) for a in vv)
        t.extend((a.a+base,a.b+base,a.c+base,a.surface,a.flags) for a in tt)
    return arrays(v,t)

class JumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-jump-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for opt in ('-O0','-O2'):
            out=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc','-std=c99',opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                *['-I'+str(ROOT/p) for p in ('platform/3ds/source','tools/banjo3ds/pose','tools/banjo3ds/gait')],
                *[str(ROOT/p) for p in ('platform/3ds/source/movement.c','tools/banjo3ds/pose/pose.c',
                  'tools/banjo3ds/gait/gait.c','tools/banjo3ds/horizontal/horizontal.c','tools/banjo3ds/jump/jump.c','tools/banjo3ds/jump/jump_animation.c')],
                '-lm','-o',str(out)],check=True)
            lib=C.CDLL(str(out));fp=C.POINTER(F)
            lib.banjo_jump_sweep.argtypes=[C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t,fp,fp,fp,C.POINTER(C.c_size_t)]
            lib.banjo_jump_sweep.restype=C.c_bool
            lib.banjo_jump_step.argtypes=[C.POINTER(Motion),F,F,F,F,C.c_bool,C.c_bool,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
            lib.banjo_jump_step.restype=C.c_uint
            lib.banjo_pose_sample.argtypes=[C.c_char_p,C.c_size_t,C.c_int,F,C.POINTER(F*10)];lib.banjo_pose_sample.restype=C.c_bool
            lib.banjo_pose_apply.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(Pose)];lib.banjo_pose_apply.restype=C.c_bool
            lib.banjo_jump_animation_begin.argtypes=[C.POINTER(Animation),C.POINTER(F*10),C.c_int,F];lib.banjo_jump_animation_begin.restype=C.c_bool
            lib.banjo_jump_animation_step.argtypes=[C.POINTER(Animation),C.c_char_p,C.c_size_t,F];lib.banjo_jump_animation_step.restype=C.c_bool
            lib.banjo_jump_animation_land.argtypes=[C.POINTER(Animation),C.c_bool,F]
            cls.libs.append(lib)
        paths=[ROOT/'assets/model/034D.model.bin']+[ROOT/f'assets/anim/{c}.anim.bin' for c in ('0003','006F','0002','000C','0008')]
        cls.packet=export_jump_packet(*paths);cls.legacy=export_gait_packet(*paths[:-1])
        cls.corners=struct.unpack_from('>2085H',cls.packet,36+960+5784)
        cls.golden=json.loads((Path(__file__).parent/'fixtures/jump_golden.json').read_text())
        cls.real=arrays(*scene_collision([ROOT/f'assets/model/{m}.model.bin' for m in ('14CF','14D0')]))

    def step(self,lib,s,mesh,dt=.05,jump=False,x=0,y=0,yaw=0,camera=False,allowed=True):
        v,t=mesh
        return lib.banjo_jump_step(C.byref(s),x,y,yaw,dt,jump,camera,allowed,v,t,len(t))
    def sweep(self,lib,mesh,start,end):
        v,t=mesh;out=(F*3)(999,999,999);idx=C.c_size_t(999)
        found=lib.banjo_jump_sweep(v,t,len(t),(F*3)(*start),(F*3)(*end),out,C.byref(idx))
        return found,tuple(out),idx.value
    def check_pose(self,pose,row):
        self.assertEqual(digest(pose.bones,10),row['bones'])
        self.assertEqual(digest(([v for r in m for v in r] for m in pose.matrices),16),row['matrices'])
        self.assertEqual(digest(pose.xyz,3),row['loads'])
        self.assertEqual(digest((pose.xyz[i] for i in self.corners),3),row['corners'])
    def check_animation(self,s,row):
        for field in ('phase','factor','duration','segment'):self.assertEqual(getattr(s,field),row[field])
        self.assertEqual(digest(s.source,10),row['source_hash']);self.check_pose(s.pose,row)
    def tick(self,lib,s,dt=0):
        self.assertTrue(lib.banjo_jump_animation_step(C.byref(s),self.packet,len(self.packet),dt))
    def begin(self,lib,source,clip,duration):
        s=Animation();bones=Bones(*( (F*10)(*b) for b in source))
        self.assertTrue(lib.banjo_jump_animation_begin(C.byref(s),bones,CLIPS[clip],duration))
        return s

    def test_jump_pose_goldens_all_four_levels_O0_O2(self):
        for lib in self.libs:
            for row in self.golden['poses']:
                with self.subTest(phase=row['phase']):
                    p=Pose();self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),4,row['phase'],p.bones))
                    self.assertTrue(lib.banjo_pose_apply(self.packet,len(self.packet),C.byref(p)));self.check_pose(p,row)

    def test_transition_goldens_and_frozen_interruption_O0_O2(self):
        for lib in self.libs:
            for case in self.golden['transitions'].values():
                s=self.begin(lib,animation(case['source']).transforms(case['source_phase'])[0],case['destination'],case['duration'])
                for i,row in enumerate(case['rows']):self.tick(lib,s,0 if i==0 else .025);self.check_animation(s,row)
            s=self.begin(lib,animation('006F').transforms(.37)[0],'0008',1.9)
            for _ in range(3):self.tick(lib,s,.025)
            self.check_animation(s,self.golden['interruption']['at']);mixed=bytes(s.pose.bones)
            self.assertTrue(lib.banjo_jump_animation_begin(C.byref(s),s.pose.bones,0,.6))
            for i,row in enumerate(self.golden['interruption']['rows']):
                self.tick(lib,s,0 if i==0 else .025);self.check_animation(s,row);self.assertEqual(bytes(s.source),mixed)

    def test_subranges_strict_boundary_hold_and_no_wrap(self):
        source=animation('006F').transforms(.37)[0]
        for lib in self.libs:
            s=self.begin(lib,source,'0008',1.9);ref=JumpTransition(source,'0008')
            for _ in range(100):
                self.tick(lib,s,.05);ref.advance(.05)
                self.assertEqual((s.phase,s.segment,s.duration),(ref.phase,ref.segment,ref.duration))
            self.assertEqual((s.phase,s.segment),(f(.6667),2));held=bytes(s.pose)
            self.tick(lib,s,10);self.assertEqual(bytes(s.pose),held)
            for segment,end,duration in ((0,.5042,1.9),(1,.6667,4)):
                s.segment=segment;s.phase=end;s.duration=duration
                self.tick(lib,s,0);self.assertEqual(s.segment,segment)
                self.tick(lib,s,2**-20);self.assertEqual(s.segment,segment+1);self.assertEqual(s.phase,f(end))

    def test_actual_landing_returns_existing_gait_and_freezes_actual_jump(self):
        for lib in self.libs:
            for accepted,speed,clip,duration in ((False,150,1,5.5),(True,150,3,.44),(True,60,0,None),(True,15,2,None)):
                s=self.begin(lib,animation('006F').transforms(.37)[0],'0008',1.9)
                self.tick(lib,s,.05);mixed=bytes(s.pose.bones)
                lib.banjo_jump_animation_land(C.byref(s),accepted,speed)
                self.assertEqual((s.phase,s.factor,s.clip),(0,0,clip));self.assertEqual(bytes(s.source),mixed)
                if duration is not None:self.assertEqual(s.duration,f(duration))
                self.tick(lib,s,0);self.assertEqual(bytes(s.pose.bones),mixed)
                for _ in range(4):self.tick(lib,s,.05)
                target=Bones();self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),clip,s.phase,target))
                self.assertEqual(bytes(s.pose.bones),bytes(target))

    def test_packet_binding_legacy_output_and_state_sizes(self):
        self.assertEqual(len(self.packet),28022);self.assertEqual(len(self.legacy),26234)
        self.assertEqual(self.packet[:4],self.legacy[:4]);self.assertEqual(self.packet[8:26234],self.legacy[8:])
        self.assertEqual(self.packet[26234:],(ROOT/'assets/anim/0008.anim.bin').read_bytes())
        self.assertEqual(set(self.corners),set(range(723)))
        self.assertEqual(C.sizeof(Motion),36);self.assertEqual(C.sizeof(Animation),21256)
        for lib in self.libs:
            self.assertFalse(lib.banjo_pose_sample(self.legacy,len(self.legacy),4,.3,Bones()))
            for clip in range(4):
                for phase in (0,.25,.5,.75,1):
                    a,b=Bones(),Bones()
                    self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),clip,phase,a))
                    self.assertTrue(lib.banjo_pose_sample(self.legacy,len(self.legacy),clip,phase,b));self.assertEqual(bytes(a),bytes(b))

    def test_plateau_takeoff_apex_and_landing(self):
        results=[]
        for lib in self.libs:
            s=Motion(actor=Actor(0,1800,0,0),grounded=True)
            event=self.step(lib,s,self.real,jump=True)
            self.assertTrue(event&1);self.assertFalse(s.grounded)
            self.assertEqual((s.vy,s.actor.y),(642.5,1832.125));self.assertEqual(tuple(s.safe),(0,1800,0))
            rising=falling=False;highest=1800;states=[]
            for _ in range(100):
                event=self.step(lib,s,self.real,dt=.01);states.append(bytes(s))
                rising |= s.vy>0;falling |= s.vy<0;highest=max(highest,s.actor.y)
                if event&2:break
            self.assertTrue(rising and falling);self.assertGreater(highest,1970)
            self.assertTrue(s.grounded);self.assertEqual((s.actor.y,s.vy),(1800,0));results.append(states)
        self.assertEqual(*results)

    def test_reconfirm_floor_not_merely_grounded_flag_or_nearby_floor(self):
        for lib in self.libs:
            for mesh,y in ((arrays([],[]),1800),(floor(flags=0x20000),1800),(floor(),1810)):
                s=Motion(actor=Actor(0,y,0,0),grounded=True)
                event=self.step(lib,s,mesh,jump=True)
                self.assertFalse(event&1);self.assertFalse(s.grounded);self.assertLess(s.vy,0)
            s=Motion(actor=Actor(0,1800,0,0),grounded=True)
            self.assertTrue(self.step(lib,s,floor(),dt=0,jump=True)&1)
            self.assertEqual((s.actor.y,s.vy,s.grounded),(1800,710,False))
            self.step(lib,s,floor());self.assertGreater(s.actor.y,1800);self.assertFalse(s.grounded)

    def test_large_downward_step_and_dt_cap(self):
        for lib in self.libs:
            states=[]
            for dt in (.05,1):
                s=Motion(actor=Actor(0,1900,0,0),vy=-3000,grounded=False)
                self.assertTrue(self.step(lib,s,floor(),dt=dt)&2)
                self.assertEqual((s.actor.y,s.vy,s.grounded),(1800,0,True));states.append(bytes(s))
            self.assertEqual(*states)
            s=Motion(actor=Actor(0,2000,0,0),vy=-3999)
            self.step(lib,s,arrays([],[]));self.assertEqual((s.vy,s.actor.y),(-4000,1800))

    def test_full_segment_narrow_platform_and_horizontal_crossing(self):
        mesh=floor(0,x0=-1,x1=1,z0=-10,z1=10)
        for lib in self.libs:
            self.assertEqual(self.sweep(lib,mesh,(-20,10,0),(20,-10,0))[:2],(True,(0,0,0)))
            self.assertFalse(self.sweep(lib,mesh,(-20,10,20),(20,-10,20))[0])
            s=Motion(actor=Actor(-3,2,0,0),vy=-32.5)
            self.assertTrue(self.step(lib,s,mesh,x=156)&2)
            self.assertTrue(-1<=s.actor.x<=1);self.assertEqual(s.actor.y,0)

    def test_stacked_floors_earliest_actual_crossing_not_endpoint_height(self):
        mesh=combine(floor(0),floor(10),floor(20))
        for lib in self.libs:
            found,p,index=self.sweep(lib,mesh,(0,30,0),(0,-30,0))
            self.assertTrue(found);self.assertEqual(p,(0,20,0));self.assertEqual(index,4)
            # A higher floor at the endpoint is not intersected at its plane time.
            mesh2=combine(floor(0),floor(10,x0=18,x1=22))
            self.assertEqual(self.sweep(lib,mesh2,(-20,20,0),(20,-20,0))[1],(0,0,0))

    def test_edges_vertices_ties_and_takeoff_direction(self):
        for lib in self.libs:
            mesh=floor(0)
            for x,z,index in ((0,0,0),(-100,-100,0),(100,100,1),(0,-100,0)):
                for _ in range(3):self.assertEqual(self.sweep(lib,mesh,(x,10,z),(x,-10,z)),(True,(x,0,z),index))
            self.assertFalse(self.sweep(lib,mesh,(0,0,0),(0,10,0))[0])
            self.assertFalse(self.sweep(lib,mesh,(0,-10,0),(0,10,0))[0])
            self.assertFalse(self.sweep(lib,mesh,(0,1,0),(10,1,0))[0])
            self.assertTrue(self.sweep(lib,mesh,(0,0,0),(0,-10,0))[0])

    def test_flags_steep_degenerate_and_two_sided(self):
        steep=arrays([(0,0,0),(0,100,1),(10,0,0)],[(0,1,2,0,0)])
        for lib in self.libs:
            for flag in (0x20000,0x40000,0x80000,0x100000,0x400000):
                self.assertFalse(self.sweep(lib,floor(0,flag),(0,10,0),(0,-10,0))[0])
            self.assertFalse(self.sweep(lib,steep,(1,100,0),(1,-10,0))[0])
            self.assertFalse(self.sweep(lib,floor(0,reverse=True),(0,10,0),(0,-10,0))[0])
            self.assertTrue(self.sweep(lib,floor(0,0x10000,True),(0,10,0),(0,-10,0))[0])
            self.assertFalse(self.sweep(lib,floor(0,x0=0,x1=0),(0,10,0),(0,-10,0))[0])

    def test_no_floor_air_control_camera_and_horizontal_rejection(self):
        for lib in self.libs:
            for camera,allowed in ((True,True),(False,False),(False,True)):
                s=Motion(actor=Actor(0,1900,0,0),vy=-100)
                self.step(lib,s,arrays([],[]),x=156,camera=camera,allowed=allowed)
                self.assertFalse(s.grounded);self.assertEqual(s.vy,-167.5);self.assertLess(s.actor.y,1900)
                self.assertEqual(s.actor.x,7.5 if not camera and allowed else 0)
                s.actor.y=1801
                self.assertTrue(self.step(lib,s,floor(),x=156,camera=camera,allowed=allowed)&2)
                self.assertTrue(s.grounded)

    def test_grounded_path_keeps_fail_closed_and_camera_direction(self):
        for lib in self.libs:
            s=Motion(actor=Actor(0,1800,0,0),grounded=True)
            self.step(lib,s,floor(x0=-1,x1=1),x=156)
            self.assertEqual((s.actor.x,s.actor.y,s.actor.z),(0,1800,0))
            s.grounded=False;s.vy=710
            self.step(lib,s,arrays([],[]),y=156,yaw=90)
            self.assertAlmostEqual(s.actor.x,-7.5,places=5);self.assertAlmostEqual(s.actor.z,0,places=5)
            self.assertAlmostEqual(s.actor.yaw,-90,places=5)

    def test_diagnostic_void_policy_only_restores_revalidated_safe_position(self):
        for lib in self.libs:
            s=Motion(actor=Actor(0,1800,0,0),grounded=True)
            self.step(lib,s,floor(),dt=0);self.assertTrue(s.has_safe)
            s.grounded=False;s.actor.y=-1004;s.vy=0
            self.assertFalse(self.step(lib,s,floor(),dt=0)&4) # strict boundary
            s.actor.y=-1005
            bad=Motion.from_buffer_copy(s)
            self.assertFalse(self.step(lib,bad,arrays([],[]),dt=0)&4);self.assertFalse(bad.grounded)
            self.assertTrue(self.step(lib,s,floor(),dt=0)&4)
            self.assertEqual((s.actor.x,s.actor.y,s.actor.z,s.vy,s.grounded),(0,1800,0,0,True))

    def test_physics_events_drive_jump_then_idle_without_viewer(self):
        for lib in self.libs:
            motion=Motion(actor=Actor(0,1800,0,0),grounded=True)
            event=self.step(lib,motion,self.real,jump=True)
            self.assertTrue(event&1)
            pose=self.begin(lib,animation('006F').transforms(.37)[0],'0008',1.9)
            self.tick(lib,pose,.05)
            for _ in range(100):
                event=self.step(lib,motion,self.real,dt=.025)
                if event&2:
                    actual=bytes(pose.pose.bones)
                    lib.banjo_jump_animation_land(C.byref(pose),False,0)
                    self.tick(lib,pose,0)
                    self.assertEqual(bytes(pose.source),actual)
                    self.assertEqual(bytes(pose.pose.bones),actual)
                    self.assertEqual(pose.clip,1)
                    break
                self.tick(lib,pose,.025)
            else:self.fail('No plateau landing')
            for _ in range(8):self.tick(lib,pose,.025)
            self.assertEqual(pose.factor,1)

    def test_terminal_and_recovery_without_safe_floor_remain_airborne(self):
        for lib in self.libs:
            s=Motion(actor=Actor(0,-1100,0,0),vy=-3999)
            event=self.step(lib,s,arrays([],[]))
            self.assertEqual(s.vy,-4000);self.assertFalse(event&4)
            self.assertFalse(s.grounded);self.assertFalse(s.has_safe)

    def test_invalid_timestep_does_not_mutate_state(self):
        for lib in self.libs:
            s=Motion(actor=Actor(0,1800,0,0),grounded=True);before=bytes(s)
            for dt in (-1,float('nan')):
                self.assertEqual(self.step(lib,s,floor(),dt=dt,jump=True),0);self.assertEqual(bytes(s),before)
