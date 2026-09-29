"""Production C versus independent M4.4B frozen four-stream goldens."""
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from idle_animation_reference import ROOT
from transition_reference import IdleAnimation, WalkAnimation, raw_blend, pack
from test_walk_pose import Pose
from tools.banjo3ds.pose_binding import export_transition_packet

F=C.c_float
Bones=(F*10)*109
IDENTITY=(0.,0.,0.,1.,1.,1.,1.,0.,0.,0.)

def bones(values):
    return Bones(*( (F*10)(*v) for v in values))

def digest(values,width):
    return hashlib.sha256(pack(values,width)).hexdigest()

class ProductionTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='banjo-production-transition-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[]
        for optimization in ('-O0','-O2'):
            path=Path(cls.tmp.name)/(optimization+'.so')
            subprocess.run(['cc','-std=c99',optimization,'-Wall','-Wextra','-Werror',
                '-shared','-fPIC','-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                str(ROOT/'tools/banjo3ds/pose/pose.c'),'-lm','-o',str(path)],check=True)
            lib=C.CDLL(str(path))
            lib.banjo_pose_sample.argtypes=[C.c_char_p,C.c_size_t,C.c_int,F,C.POINTER(F*10)]
            lib.banjo_pose_sample.restype=C.c_bool
            lib.banjo_pose_apply.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(Pose)]
            lib.banjo_pose_apply.restype=C.c_bool
            lib.banjo_pose_blend.argtypes=[C.POINTER(F*10)]*3+[F]
            cls.libs.append(lib)
        cls.packet=export_transition_packet(ROOT/'assets/model/034D.model.bin',
                     ROOT/'assets/anim/0003.anim.bin',ROOT/'assets/anim/006F.anim.bin')
        import struct
        cls.corners=struct.unpack_from('>2085H',cls.packet,36+960+5784)
        cls.golden=json.loads((Path(__file__).parent/'fixtures/transition_006f_0003_golden.json').read_text())['scenarios']

    def sample(self,lib,clip,phase):
        out=Bones()
        self.assertTrue(lib.banjo_pose_sample(self.packet,len(self.packet),clip,phase,out))
        return out

    def check_row(self,lib,source,clip,row):
        pose=Pose();destination=self.sample(lib,clip,row['phase'])
        self.assertEqual(digest(destination,10),row['destination_hash'])
        self.assertEqual(digest(source,10),row['source_hash'])
        lib.banjo_pose_blend(pose.bones,source,destination,row['factor'])
        self.assertTrue(lib.banjo_pose_apply(self.packet,len(self.packet),C.byref(pose)))
        self.assertEqual(digest(pose.bones,10),row['bones'])
        self.assertEqual(digest(([v for r in m for v in r] for m in pose.matrices),16),row['matrices'])
        self.assertEqual(digest(pose.xyz,3),row['loads'])
        self.assertEqual(digest((pose.xyz[i] for i in self.corners),3),row['corners'])
        return Bones.from_buffer_copy(pose.bones)

    def test_all_four_streams_all_37_snapshots_at_O0_and_O2(self):
        for lib in self.libs:
            for name,clip,phase,target in [('idle_to_walk',1,.37,0),('walk_to_idle',0,.625,1),
                                           ('idle_tail_to_walk',1,.625,0)]:
                source=self.sample(lib,clip,phase)
                for row in self.golden[name]:
                    with self.subTest(case=name,phase=row['phase'],factor=row['factor']):
                        self.check_row(lib,source,target,row)
            source=self.sample(lib,1,.37)
            mixed=self.check_row(lib,source,0,self.golden['interruption']['at'])
            for row in self.golden['interruption']['return_to_idle']:
                self.check_row(lib,mixed,1,row)

    def test_clips_against_independent_evaluation_including_loop_end(self):
        for lib in self.libs:
            for clip,reference in ((0,WalkAnimation()),(1,IdleAnimation())):
                for phase in (0,.25,.5,.625,.75,.999,1):
                    out=self.sample(lib,clip,phase)
                    self.assertEqual(pack(out,10),pack(reference.transforms(phase)[0],10))

    def test_exact_endpoints_aliasing_and_original_quaternion_edges(self):
        q=(F(.0001).value,0.,0.,F(1.000001).value)
        cases=[IDENTITY, q+IDENTITY[4:], tuple(-v for v in q)+IDENTITY[4:],
               (1.,0.,0.,0.)+IDENTITY[4:],
               (F(math.sin(.5)).value,0.,0.,F(math.cos(.5)).value)+IDENTITY[4:],
               (0.,0.,0.,1.,3.,5.,7.,10.,20.,30.)]
        for lib in self.libs:
            source=bones([IDENTITY]*109)
            for value in cases:
                destination=bones([value]*109)
                expected=raw_blend(source,destination,.5)[0]
                out=Bones()
                lib.banjo_pose_blend(out,source,destination,.5)
                self.assertEqual(pack(out,10),pack(expected,10))
                lib.banjo_pose_blend(destination,source,destination,.5)
                self.assertEqual(bytes(destination),bytes(out))
            source=self.sample(lib,1,.37);destination=self.sample(lib,0,F(1/3).value)
            for factor,expected in ((-1,source),(0,source),(1,destination),(2,destination)):
                out=Bones();lib.banjo_pose_blend(out,source,destination,factor)
                self.assertEqual(bytes(out),bytes(expected))

    def test_packet_validation(self):
        self.assertEqual(len(self.packet),24398)
        for lib in self.libs:
            for data,clip,phase in ((self.packet[:-1],1,0),(self.packet,2,0),
                                    (self.packet,1,float('nan'))):
                self.assertFalse(lib.banjo_pose_sample(data,len(data),clip,phase,Bones()))

if __name__=='__main__':unittest.main()
