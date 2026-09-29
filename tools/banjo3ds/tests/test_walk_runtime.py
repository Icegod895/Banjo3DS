"""Run the viewer's portable animation/VBO update path on the host."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT, idle_reference
from walk_pose_reference import reference
from test_walk_pose import Pose, packed
from tools.banjo3ds.pose_binding import export_pose_packet, export_transition_packet, export_gait_packet
from tools.banjo3ds.export_3ds_model import export_scene

F=C.c_float
class State(C.Structure):
    _fields_=[('pose',Pose),('source',(F*10)*109),('phase',F),('factor',F),
              ('gait',C.c_uint8),('initialized',C.c_bool)]
class Vertex(C.Structure):
    _fields_=[('x',F),('y',F),('z',F),('u',F),('v',F),('rgba',C.c_ubyte*4)]
class Actor(C.Structure):
    _fields_=[('x',F),('y',F),('z',F),('yaw',F)]
FIRST,COUNT,TOTAL=9408,2085,12600

class WalkRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-walk-runtime-')
        cls.addClassCleanup(cls.tmp.cleanup)
        library=Path(cls.tmp.name)/'walk.so'
        subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                        '-I'+str(ROOT/'tools/banjo3ds/pose'),
                        '-I'+str(ROOT/'tools/banjo3ds/gait'),
                        str(ROOT/'tools/banjo3ds/gait/gait.c'),
                        str(ROOT/'tools/banjo3ds/pose/pose.c'),
                        str(ROOT/'platform/3ds/source/walk_animation.c'),
                        str(ROOT/'platform/3ds/source/movement.c'),'-lm','-o',str(library)],check=True)
        cls.lib=C.CDLL(str(library))
        cls.lib.walkAnimationUpdate.argtypes=[C.POINTER(State),C.c_char_p,C.c_size_t,C.c_bool,F,F,
                                              C.c_void_p,C.c_size_t,C.c_size_t,C.c_size_t,C.c_size_t]
        cls.lib.walkAnimationUpdate.restype=C.c_bool
        cls.lib.banjo_gait_duration.argtypes=[C.c_int,F];cls.lib.banjo_gait_duration.restype=F
        cls.lib.movementUpdate.argtypes=[C.POINTER(Actor),F,F,F,F,C.c_bool,C.c_void_p,C.c_void_p,C.c_size_t]
        cls.lib.movementUpdate.restype=C.c_bool
        cls.packet=export_gait_packet(ROOT/'assets/model/034D.model.bin',ROOT/'assets/anim/0003.anim.bin',
                                     ROOT/'assets/anim/006F.anim.bin',ROOT/'assets/anim/0002.anim.bin',
                                     ROOT/'assets/anim/000C.anim.bin')
        _,_,_,pose=idle_reference()
        cls.idle=(Vertex*TOTAL)()
        for i,v in enumerate(cls.idle):
            v.x=i;v.y=-i;v.z=17;v.u=i*.125;v.v=-i*.25;v.rgba[:]=(17,33,65,129)
        for corner,index in enumerate(i for t in pose.triangles for i in t):
            v=cls.idle[FIRST+corner];v.x,v.y,v.z=pose.loads[index]['xyz']

    def update(self,state,vertices,accepted=True,speed=75,dt=0):
        return self.lib.walkAnimationUpdate(C.byref(state),self.packet,len(self.packet),accepted,speed,dt,
                                            vertices,TOTAL,FIRST,COUNT,C.sizeof(Vertex))

    def test_runtime_phases_and_only_actor_xyz_mutates(self):
        original=bytes(self.idle);stride=C.sizeof(Vertex)
        for phase in (0.,.25,.5,.75):
            with self.subTest(phase=phase):
                vertices=(Vertex*TOTAL).from_buffer_copy(original);state=State();state.phase=phase
                state.initialized=True;state.gait=2;state.factor=1
                self.assertTrue(self.update(state,vertices))
                _,_,pose=reference(phase)
                actual=packed(((v.x,v.y,v.z) for v in vertices[FIRST:FIRST+COUNT]),3)
                expected=packed((pose.loads[i]['xyz'] for t in pose.triangles for i in t),3)
                self.assertEqual(actual,expected)
                result=bytes(vertices)
                self.assertEqual(result[:FIRST*stride],original[:FIRST*stride])
                self.assertEqual(result[(FIRST+COUNT)*stride:],original[(FIRST+COUNT)*stride:])
                for i in range(FIRST,FIRST+COUNT):
                    self.assertEqual(result[i*stride+12:(i+1)*stride],original[i*stride+12:(i+1)*stride])

    def test_runtime_idle_and_rejected_floor_selects_idle_destination(self):
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));state=State()
        self.assertTrue(self.update(state,vertices,accepted=False,dt=0))
        self.assertEqual(bytes(vertices),bytes(self.idle))
        self.assertTrue(self.update(state,vertices,dt=.05))
        self.assertGreater(state.phase,0)
        mixed=bytes(state.pose.bones)
        actor=Actor(0,1800,0,0)
        accepted=self.lib.movementUpdate(C.byref(actor),156,0,0,.05,False,None,None,0)
        self.assertFalse(accepted)
        self.assertTrue(self.update(state,vertices,accepted=accepted,dt=.05))
        self.assertEqual(state.gait,0)
        self.assertEqual(bytes(state.source),mixed)
        self.assertAlmostEqual(state.phase,.05/5.5,places=8)
        self.assertEqual(state.factor,.25)
        phase=state.phase
        self.assertTrue(self.update(state,vertices,accepted=False,dt=.05))
        self.assertGreater(state.phase,phase)
        self.assertEqual(bytes(state.source),mixed)

    def test_duration_phase_wrap_and_idle_loop(self):
        for speed,duration in ((0,1.3),(30,1.3),(52.5,.95),(75,.6),(150,.6)):
            self.assertAlmostEqual(self.lib.banjo_gait_duration(2,speed),duration,places=6)
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));state=State()
        state.initialized=True;state.gait=2;state.factor=1;state.phase=.99
        self.update(state,vertices,dt=.03)
        self.assertAlmostEqual(state.phase,.04,places=6)
        self.update(state,vertices,accepted=False,dt=.03)
        self.assertAlmostEqual(state.phase,.03/5.5,places=8)
        state.phase=.999
        self.update(state,vertices,accepted=False,dt=.05)
        self.assertLess(state.phase,.01)

    def test_controller_matches_all_transition_goldens_and_interruption(self):
        from transition_reference import IdleAnimation, WalkAnimation, digest
        golden=json.loads((Path(__file__).parent/'fixtures/transition_006f_0003_golden.json').read_text())['scenarios']
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle))
        original=bytes(vertices);stride=C.sizeof(Vertex)
        def check(state,row):
            self.assertEqual(state.phase,row['phase']);self.assertEqual(state.factor,row['factor'])
            self.assertEqual(digest(state.source,10),row['source_hash'])
            self.assertEqual(digest(state.pose.bones,10),row['bones'])
            self.assertEqual(digest(([v for r in m for v in r] for m in state.pose.matrices),16),row['matrices'])
            self.assertEqual(digest(state.pose.xyz,3),row['loads'])
            self.assertEqual(digest(((v.x,v.y,v.z) for v in vertices[FIRST:FIRST+COUNT]),3),row['corners'])
            result=bytes(vertices)
            self.assertEqual(result[:FIRST*stride],original[:FIRST*stride])
            self.assertEqual(result[(FIRST+COUNT)*stride:],original[(FIRST+COUNT)*stride:])
            for i in range(FIRST,FIRST+COUNT):
                self.assertEqual(result[i*stride+12:(i+1)*stride],original[i*stride+12:(i+1)*stride])
        for name,reference,phase,moving in [('idle_to_walk',IdleAnimation,.37,True),
                ('walk_to_idle',WalkAnimation,.625,False),('idle_tail_to_walk',IdleAnimation,.625,True)]:
            state=State();state.initialized=True;state.gait=2 if not moving else 0
            values=reference().transforms(phase)[0]
            for i,row in enumerate(values):state.pose.bones[i][:]=row
            for n,row in enumerate(golden[name]):
                self.assertTrue(self.update(state,vertices,accepted=moving,dt=0 if n==0 else .025))
                check(state,row)
        state=State();state.initialized=True
        for i,row in enumerate(IdleAnimation().transforms(.37)[0]):state.pose.bones[i][:]=row
        for _ in range(3):self.update(state,vertices,dt=.025)
        check(state,golden['interruption']['at'])
        for n,row in enumerate(golden['interruption']['return_to_idle']):
            self.assertTrue(self.update(state,vertices,accepted=False,dt=0 if n==0 else .025))
            check(state,row)

    def assert_only_actor_xyz(self,vertices):
        original=bytes(self.idle);result=bytes(vertices);stride=C.sizeof(Vertex)
        self.assertEqual(result[:FIRST*stride],original[:FIRST*stride])
        self.assertEqual(result[(FIRST+COUNT)*stride:],original[(FIRST+COUNT)*stride:])
        for i in range(FIRST,FIRST+COUNT):
            self.assertEqual(result[i*stride+12:(i+1)*stride],original[i*stride+12:(i+1)*stride])

    def test_runtime_gait_chain_both_directions_hysteresis_and_large_jumps(self):
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));s=State()
        # Includes equality, both sides of each hysteresis region and direct jumps.
        cases=[(0,0),(15,1),(32,1),(34,2),(76,2),(79,3),(114,3),(116,4),
               (110,4),(108,3),(73,3),(71,2),(28,2),(26,1),(0,0),
               (150,4),(15,1),(90,3),(0,0)]
        for speed,gait in cases:
            self.assertTrue(self.update(s,vertices,accepted=speed>0,speed=speed,dt=.025))
            self.assertEqual(s.gait,gait)
            self.assert_only_actor_xyz(vertices)

    def test_vbo_matches_all_m45_transition_goldens_including_interruption(self):
        from gait_reference import ClipReference, CLIPS
        from transition_reference import digest
        golden=json.loads((Path(__file__).parent/'fixtures/gait_golden.json').read_text())
        ids={'IDLE':0,'CREEP':1,'SLOW':2,'WALK':3,'FAST':4}
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle))
        def check(s,row):
            self.assertEqual((s.phase,s.factor),(row['phase'],row['factor']))
            self.assertEqual(digest(s.source,10),row['source_hash'])
            self.assertEqual(digest(s.pose.bones,10),row['bones'])
            self.assertEqual(digest(([v for r in m for v in r] for m in s.pose.matrices),16),row['matrices'])
            self.assertEqual(digest(s.pose.xyz,3),row['loads'])
            self.assertEqual(digest(((v.x,v.y,v.z) for v in vertices[FIRST:FIRST+COUNT]),3),row['corners'])
            self.assert_only_actor_xyz(vertices)
        for case in golden['transitions'].values():
            s=State();s.initialized=True;s.factor=1;s.phase=case['source_phase'];s.gait=ids[case['source_gait']]
            for i,row in enumerate(ClipReference(CLIPS[case['source_gait']]).transforms(s.phase)[0]):s.pose.bones[i][:]=row
            for n,row in enumerate(case['rows']):
                self.assertTrue(self.update(s,vertices,accepted=case['destination_gait']!='IDLE',speed=case['speed'],dt=0 if n==0 else .025))
                self.assertEqual(s.gait,ids[case['destination_gait']]);check(s,row)
        s=State();s.initialized=True;s.factor=1;s.phase=.37;s.gait=1
        for i,row in enumerate(ClipReference('0002').transforms(.37)[0]):s.pose.bones[i][:]=row
        for _ in range(3):self.update(s,vertices,speed=60,dt=.025)
        check(s,golden['interruption']['at'])
        for n,row in enumerate(golden['interruption']['rows']):
            self.update(s,vertices,speed=90,dt=0 if n==0 else .025);check(s,row)

    def test_runtime_walk_fast_changes_rate_without_restart(self):
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));s=State()
        self.update(s,vertices,speed=90,dt=.025)
        phase,factor,source,pose,buffer=s.phase,s.factor,bytes(s.source),bytes(s.pose),bytes(vertices)
        self.update(s,vertices,speed=150,dt=0)
        self.assertEqual(s.gait,4)
        self.assertEqual((s.phase,s.factor,bytes(s.source),bytes(s.pose),bytes(vertices)),
                         (phase,factor,source,pose,buffer))
        self.update(s,vertices,speed=150,dt=.025)
        self.assertEqual(s.phase,F(phase+F(F(.025).value/F(.44).value).value).value)
        phase,factor,source,pose,buffer=s.phase,s.factor,bytes(s.source),bytes(s.pose),bytes(vertices)
        self.update(s,vertices,speed=90,dt=0)
        self.assertEqual(s.gait,3)
        self.assertEqual((s.phase,s.factor,bytes(s.source),bytes(s.pose),bytes(vertices)),
                         (phase,factor,source,pose,buffer))

    def test_y_circle_pad_and_rejected_floor_never_select_locomotion(self):
        for camera_mode in (False,True):
            vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));s=State()
            self.update(s,vertices,speed=150,dt=.025)
            actor=Actor(0,1800,0,37);before=bytes(actor)
            # With Y held, movement exits before any floor access. Without Y,
            # empty collision rejects the candidate. Both preserve position/yaw.
            accepted=self.lib.movementUpdate(C.byref(actor),156,0,145,.025,camera_mode,None,None,0)
            self.assertFalse(accepted);self.assertEqual(bytes(actor),before)
            self.update(s,vertices,accepted=accepted,speed=0,dt=.025)
            self.assertEqual(s.gait,0);self.assertAlmostEqual(s.phase,.025/5.5,places=8)
            self.assert_only_actor_xyz(vertices)

    def test_export_only_appends_verified_packet_and_preserves_passes_sort(self):
        args=[ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0','034D')]
        base=export_scene(*args,ROOT/'assets/anim/006F.anim.bin')
        animated=export_scene(*args,ROOT/'assets/anim/006F.anim.bin',
                              walk_animation_path=ROOT/'assets/anim/0003.anim.bin')
        self.assertTrue(animated.startswith(base))
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(),
                         '6d2e846ad060b9c9463c74d5474dfd35b9d1fb71b429b1504cc0f7ac059ba6a4')
        suffix=animated[len(base):]
        data=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',suffix))
        self.assertEqual(data,export_pose_packet(args[2],ROOT/'assets/anim/0003.anim.bin'))
        self.assertEqual(len(data),12082)
        current=export_scene(*args,ROOT/'assets/anim/006F.anim.bin',
                            walk_animation_path=ROOT/'assets/anim/0003.anim.bin',runtime_transitions=True)
        self.assertTrue(current.startswith(base))
        packet=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',current[len(base):]))
        self.assertEqual(packet,export_transition_packet(args[2],ROOT/'assets/anim/0003.anim.bin',ROOT/'assets/anim/006F.anim.bin'))
        self.assertEqual(len(packet),24398)
        # The old full M4.4 viewer header stays byte-identical as an opt-in v2 export.
        self.assertEqual(hashlib.sha256(current.encode()).hexdigest(),
                         '5954065f9220c1d97c4fbe1083cd2da57e47cb01d5dbc8749312086aafc421e9')
        gaits=export_scene(*args,ROOT/'assets/anim/006F.anim.bin',
                          walk_animation_path=ROOT/'assets/anim/0003.anim.bin',runtime_transitions=True,
                          creep_animation_path=ROOT/'assets/anim/0002.anim.bin',
                          run_animation_path=ROOT/'assets/anim/000C.anim.bin')
        self.assertTrue(gaits.startswith(base))
        gait_packet=bytes(int(v,16) for v in re.findall(r'0x([0-9a-f]{2})',gaits[len(base):]))
        self.assertEqual(gait_packet,self.packet);self.assertEqual(len(gait_packet),26234)
        for name,n in [('VERTEX',12600),('TEXTURE',97),('MATERIAL',469),('DRAW',510),
                       ('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {n}\n',gaits)
        for name,n in [('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {n}\n',animated)
        self.assertIn('#define BANJO_ACTOR_FIRST_VERTEX 9408\n',suffix)
        self.assertIn('#define BANJO_ACTOR_VERTEX_COUNT 2085\n',suffix)
        # Complete old header equality includes the four SORT nodes verbatim.

if __name__=='__main__':unittest.main()
