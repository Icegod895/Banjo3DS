"""Run the viewer's portable animation/VBO update path on the host."""
import ctypes as C
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT, idle_reference
from walk_pose_reference import reference
from test_walk_pose import Pose, packed
from tools.banjo3ds.pose_binding import export_pose_packet
from tools.banjo3ds.export_3ds_model import export_scene

F=C.c_float
class State(C.Structure):
    _fields_=[('pose',Pose),('phase',F),('walking',C.c_bool)]
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
                        str(ROOT/'tools/banjo3ds/pose/pose.c'),
                        str(ROOT/'platform/3ds/source/walk_animation.c'),
                        str(ROOT/'platform/3ds/source/movement.c'),'-lm','-o',str(library)],check=True)
        cls.lib=C.CDLL(str(library))
        cls.lib.walkAnimationUpdate.argtypes=[C.POINTER(State),C.c_char_p,C.c_size_t,C.c_bool,F,F,
                                              C.c_void_p,C.c_void_p,C.c_size_t,C.c_size_t,C.c_size_t,C.c_size_t]
        cls.lib.walkAnimationUpdate.restype=C.c_bool
        cls.lib.walkAnimationDuration.argtypes=[F];cls.lib.walkAnimationDuration.restype=F
        cls.lib.movementUpdate.argtypes=[C.POINTER(Actor),F,F,F,F,C.c_bool,C.c_void_p,C.c_void_p,C.c_size_t]
        cls.lib.movementUpdate.restype=C.c_bool
        cls.packet=export_pose_packet(ROOT/'assets/model/034D.model.bin',ROOT/'assets/anim/0003.anim.bin')
        _,_,_,pose=idle_reference()
        cls.idle=(Vertex*TOTAL)()
        for i,v in enumerate(cls.idle):
            v.x=i;v.y=-i;v.z=17;v.u=i*.125;v.v=-i*.25;v.rgba[:]=(17,33,65,129)
        for corner,index in enumerate(i for t in pose.triangles for i in t):
            v=cls.idle[FIRST+corner];v.x,v.y,v.z=pose.loads[index]['xyz']

    def update(self,state,vertices,accepted=True,speed=150,dt=0):
        return self.lib.walkAnimationUpdate(C.byref(state),self.packet,len(self.packet),accepted,speed,dt,
                                            vertices,self.idle,TOTAL,FIRST,COUNT,C.sizeof(Vertex))

    def test_runtime_phases_and_only_actor_xyz_mutates(self):
        original=bytes(self.idle);stride=C.sizeof(Vertex)
        for phase in (0.,.25,.5,.75):
            with self.subTest(phase=phase):
                vertices=(Vertex*TOTAL).from_buffer_copy(original);state=State();state.phase=phase
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

    def test_idle_restores_exact_golden_and_rejected_floor_stops_phase(self):
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));state=State()
        self.assertTrue(self.update(state,vertices,dt=.05))
        self.assertGreater(state.phase,0)
        actor=Actor(0,1800,0,0)
        accepted=self.lib.movementUpdate(C.byref(actor),156,0,0,.05,False,None,None,0)
        self.assertFalse(accepted)
        self.assertTrue(self.update(state,vertices,accepted=accepted,dt=.05))
        self.assertEqual(state.phase,0);self.assertFalse(state.walking)
        self.assertEqual(bytes(vertices),bytes(self.idle))
        self.assertFalse(self.update(state,vertices,accepted=False,dt=.05))
        self.assertEqual(state.phase,0)
        stream=packed(((v.x,v.y,v.z) for v in vertices[FIRST:FIRST+COUNT]),3)
        self.assertEqual(hashlib.sha256(stream).hexdigest(),
                         '7536cd507d67f2de4e3ab1bec2beb707fd902b361995b8c6ce5d208e16e2cc6c')

    def test_duration_phase_wrap_and_immediate_stop(self):
        for speed,duration in ((0,1.5),(30,1.5),(80,1.3),(115,.95),(150,.6),(225,.3)):
            self.assertAlmostEqual(self.lib.walkAnimationDuration(speed),duration,places=6)
        vertices=(Vertex*TOTAL).from_buffer_copy(bytes(self.idle));state=State();state.phase=.99
        self.update(state,vertices,dt=.03)
        self.assertAlmostEqual(state.phase,.04,places=6)
        self.update(state,vertices,accepted=False,dt=.03)
        self.assertEqual(state.phase,0);self.assertEqual(bytes(vertices),bytes(self.idle))

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
        self.assertEqual(data,self.packet);self.assertEqual(len(data),12082)
        for name,n in [('OPA_DRAW',436),('ACTOR_DRAW',28),('XLU_DRAW',46),('GEO_NODE',36)]:
            self.assertIn(f'#define BANJO_{name}_COUNT {n}\n',animated)
        self.assertIn('#define BANJO_ACTOR_FIRST_VERTEX 9408\n',suffix)
        self.assertIn('#define BANJO_ACTOR_VERTEX_COUNT 2085\n',suffix)
        # Complete old header equality includes the four SORT nodes verbatim.

if __name__=='__main__':unittest.main()
