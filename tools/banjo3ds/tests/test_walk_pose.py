"""Independent original-C oracle versus standalone production C, no viewer changes."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from idle_animation_reference import F, ROOT, idle_reference
from walk_pose_reference import PHASES, WalkAnimation, golden, reference, reference_binding
from tools.banjo3ds.pose_binding import binding, export_pose_packet

class Pose(C.Structure):
    _fields_ = [('bones', (F*10)*109), ('matrices', ((F*4)*4)*60), ('xyz', (F*3)*723)]


def packed(rows, width):
    return b''.join(struct.pack('>'+str(width)+'f', *row) for row in rows)


class WalkPoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loads, cls.corners, cls.calls = binding(ROOT/'assets/model/034D.model.bin')
        cls.packet = export_pose_packet(ROOT/'assets/model/034D.model.bin', ROOT/'assets/anim/0003.anim.bin')
        cls.frozen = json.loads((Path(__file__).parent/'fixtures/walk_0003_golden.json').read_text())
        cls.temporary = tempfile.TemporaryDirectory(prefix='banjo-walk-c-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.libs = []
        for optimization in ('-O0', '-O2'):
            output = Path(cls.temporary.name)/(optimization+'.so')
            subprocess.run(['cc','-std=c99',optimization,'-Wall','-Wextra','-Werror',
                            '-shared','-fPIC','-ffp-contract=off','-fno-fast-math',
                            '-fexcess-precision=standard',str(ROOT/'tools/banjo3ds/pose/pose.c'),
                            '-lm','-o',str(output)],check=True,capture_output=True)
            lib = C.CDLL(str(output))
            lib.banjo_pose_evaluate.argtypes = [C.c_char_p,C.c_size_t,F,C.POINTER(Pose)]
            lib.banjo_pose_evaluate.restype = C.c_bool
            cls.libs.append(lib)

    def evaluate(self, phase, lib=None, packet=None):
        out = Pose()
        packet = self.packet if packet is None else packet
        self.assertTrue((lib or self.libs[0]).banjo_pose_evaluate(packet,len(packet),phase,C.byref(out)))
        return out

    def test_independent_frozen_goldens(self):
        self.assertEqual([g['phase'] for g in self.frozen['phases']], list(PHASES))
        self.assertEqual(hashlib.sha256((ROOT/'assets/anim/0003.anim.bin').read_bytes()).hexdigest(),self.frozen['asset_sha256'])
        for expected in self.frozen['phases']:
            with self.subTest(phase=expected['phase']):
                self.assertEqual(json.loads(json.dumps(golden(expected['phase']))),expected)

    def test_binding_matches_independent_matrix_tags(self):
        self.assertEqual((self.loads,self.corners,self.calls),reference_binding())
        self.assertEqual((len(self.loads),len(self.corners),len(self.calls)),(723,2085,49))
        self.assertEqual(set(self.corners),set(range(723)))
        self.assertTrue(all(0<=r<60 or r==65535 for x,y,z,r in self.loads))

    def test_binding_reproduces_existing_idle_golden(self):
        animation,bones,_,pose = idle_reference()
        matrices = animation.matrices(bones)
        xyz=[]
        for x,y,z,record in self.loads:
            matrix=matrices[record] if record!=65535 else tuple(tuple(float(i==j) for j in range(4)) for i in range(4))
            result=[]
            for c in range(3):
                row=[F(v).value for v in matrix[c]]
                if c==2:row[3]=F(row[3]-100.).value
                row=[int(F(v*65536.).value)/65536. for v in row]
                result.append(sum(v*w for v,w in zip(row,(x,y,z,1)))+(100. if c==2 else 0.))
            xyz.append(result)
        stream=packed((xyz[i] for i in self.corners),3)
        self.assertEqual(hashlib.sha256(stream).hexdigest(),'7536cd507d67f2de4e3ab1bec2beb707fd902b361995b8c6ce5d208e16e2cc6c')
        self.assertEqual(stream,packed((pose.loads[i]['xyz'] for tri in pose.triangles for i in tri),3))

    def assert_reference(self, phase):
        animation,bones,pose=reference(phase)
        self.assertEqual((len(pose.calls),len(pose.triangles),len(pose.loads)),(49,695,723))
        matrices=animation.matrices(bones)
        for lib in self.libs:
            out=self.evaluate(phase,lib)
            self.assertEqual(packed(out.bones,10),packed(bones,10))
            for i in range(60):
                self.assertEqual(packed(out.matrices[i],4),packed(zip(*matrices[i]),4))
            self.assertEqual(packed(out.xyz,3),packed((e['xyz'] for e in pose.loads),3))
            self.assertEqual(packed((out.xyz[i] for i in self.corners),3),
                             packed((pose.loads[i]['xyz'] for tri in pose.triangles for i in tri),3))

    def test_c_exact_all_golden_phases_debug_and_optimized(self):
        for phase in PHASES:
            with self.subTest(phase=phase):self.assert_reference(phase)

    def test_c_key_and_midpoint_phases(self):
        animation=WalkAnimation()
        frames=sorted({k&0x3fff for b,c,keys in animation.channels for k,v in keys})
        phases={F(f/120.).value for f in frames}
        phases.update(F((a+b)/240.).value for a,b in zip(frames,frames[1:]))
        for phase in sorted(phases):
            with self.subTest(phase=phase):self.assert_reference(phase)

    def test_end_and_original_loop_boundary(self):
        a,b=self.evaluate(0),self.evaluate(1)
        self.assertEqual(bytes(a),bytes(b))
        lib=WalkAnimation().library
        self.assertEqual(lib.loop_time(1.,0.,1.),0.)
        epsilon=2**-20
        self.assertEqual(lib.loop_time(1.,epsilon,1.),epsilon)
        self.assertEqual(lib.loop_time(1-epsilon,epsilon,1.),0.)
        self.assert_reference(lib.loop_time(1.,epsilon,1.))

    def test_0003_layout_and_interpolation_coverage(self):
        animation=WalkAnimation()
        self.assertEqual((animation.first,animation.last,len(animation.channels)),(0,120,47))
        self.assertEqual(sum(len(k) for b,c,k in animation.channels),234)
        intervals=[bool(a[0]&0x4000 or b[0]&0x8000)
                   for bone,ch,keys in animation.channels for a,b in zip(keys,keys[1:])]
        self.assertEqual((intervals.count(False),intervals.count(True)),(12,175))
        # Bone zero has no channels and retains reset identity at every phase.
        self.assertFalse(any(b==0 for b,c,k in animation.channels))
        for phase in PHASES:
            self.assertEqual(tuple(self.evaluate(phase).bones[0]),(0.,0.,0.,1.,1.,1.,1.,0.,0.,0.))

    def test_m42_complete_export_byte_identity(self):
        from tools.banjo3ds.export_3ds_model import export_scene
        output=export_scene(*(ROOT/f'assets/model/{a}.model.bin' for a in ('14CF','14D0','034D')),
                            ROOT/'assets/anim/006F.anim.bin')
        self.assertEqual(hashlib.sha256(output.encode()).hexdigest(),
                         '6d2e846ad060b9c9463c74d5474dfd35b9d1fb71b429b1504cc0f7ac059ba6a4')

    def test_packet_and_scratch_sizes(self):
        self.assertEqual(len(self.packet),32+4+60*16+723*8+2085*2+1132)
        self.assertEqual(C.sizeof(Pose),16876)
        self.assertEqual(self.packet[-1132:],(ROOT/'assets/anim/0003.anim.bin').read_bytes())
        self.assertEqual(struct.unpack_from('>2085H',self.packet,36+960+5784),tuple(self.corners))

    def test_invalid_packet_or_phase_rejected(self):
        cases=[self.packet[:-1],b'',b'FAIL'+self.packet[4:]]
        for offset,data in ((4,struct.pack('>I',2)),(36+960+6,b'\x00\x3c'),
                            (36+960+5784,b'\xff\xff'),(36+14,b'\x00\x00'),
                            (len(self.packet)-1132+10,b'\x7f\xff')):
            p=bytearray(self.packet);p[offset:offset+len(data)]=data;cases.append(bytes(p))
        for p in cases:
            self.assertFalse(self.libs[0].banjo_pose_evaluate(p,len(p),0,C.byref(Pose())))
        for phase in (-1.,1.01,float('nan'),float('inf')):
            self.assertFalse(self.libs[0].banjo_pose_evaluate(self.packet,len(self.packet),phase,C.byref(Pose())))

if __name__=='__main__':unittest.main()
