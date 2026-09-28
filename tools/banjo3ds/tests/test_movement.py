"""Execute the exact portable C movement code used by the 3DS target."""
import ctypes as C
import hashlib
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.banjo3ds.floor_collision import read_collision, scene_collision
from tools.banjo3ds.export_3ds_model import export_scene

ROOT = Path(__file__).resolve().parents[3]
F = C.c_float
class Vertex(C.Structure):
    _fields_ = [('x',C.c_int16),('y',C.c_int16),('z',C.c_int16)]
class Triangle(C.Structure):
    _fields_ = [('a',C.c_uint16),('b',C.c_uint16),('c',C.c_uint16),
                ('surface',C.c_int16),('flags',C.c_uint32)]
class Actor(C.Structure):
    _fields_ = [('x',F),('y',F),('z',F),('yaw',F)]

class TestMovement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        library = Path(cls.tmp.name)/'movement.so'
        subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        str(ROOT/'platform/3ds/source/movement.c'),'-lm','-o',str(library)],check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.movementNormalize.argtypes = [F,F,C.POINTER(F)]
        cls.lib.movementDirection.argtypes = [F,F,F,C.POINTER(F)]
        cls.lib.movementDelta.argtypes = [C.c_uint64,C.c_uint64]
        cls.lib.movementDelta.restype = F
        cls.lib.movementFloor.argtypes = [C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t,F,F,F,C.POINTER(F)]
        cls.lib.movementFloor.restype = C.c_bool
        cls.lib.movementUpdate.argtypes = [C.POINTER(Actor),F,F,F,F,C.c_bool,C.POINTER(Vertex),C.POINTER(Triangle),C.c_size_t]
        cls.lib.movementUpdate.restype = C.c_bool
        cls.lib.movementActorMatrix.argtypes = [C.POINTER(Actor),C.POINTER(F)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def normalize(self,x,y):
        out=(F*2)(); self.lib.movementNormalize(x,y,out); return tuple(out)

    def direction(self,x,y,yaw):
        out=(F*2)(); self.lib.movementDirection(x,y,yaw,out); return tuple(out)

    def assertVector(self, actual, expected):
        for a,b in zip(actual,expected): self.assertAlmostEqual(a,b,places=5)

    def test_radial_deadzone_exact_zero_and_response(self):
        for x,y in [(0,0),(20,0),(-20,0),(0,20),(12,16),(14,14),(-12,-16)]:
            self.assertEqual(self.normalize(x,y),(0,0))
        self.assertGreater(self.normalize(15,15)[0],0) # Radial, not square.
        self.assertVector(self.normalize(88,0),(.5,0))
        for x,y in [(156,0),(-156,0),(0,156),(0,-156),(156,156),(-156,-156),(32767,32767)]:
            length=math.hypot(x,y)
            self.assertVector(self.normalize(x,y),(x/length,y/length))

    def test_camera_yaw_cardinals(self):
        for yaw,forward,right in [(0,(0,1),(1,0)),(90,(-1,0),(0,1)),
                                  (180,(0,-1),(-1,0)),(-90,(1,0),(0,-1))]:
            self.assertVector(self.direction(0,1,yaw),forward)
            self.assertVector(self.direction(1,0,yaw),right)

    def test_actor_matrix_translation_is_not_rotated(self):
        for yaw,forward in [(0,(0,0,1)),(90,(1,0,0)),(180,(0,0,-1)),(-90,(-1,0,0))]:
            a=Actor(10,20,30,yaw); rows=(F*16)()
            self.lib.movementActorMatrix(C.byref(a),rows)
            def apply(p): return [sum(rows[4*i+j]*p[j] for j in range(4)) for i in range(4)]
            self.assertVector(apply((0,0,0,1)),(10,20,30,1))
            self.assertVector(apply((0,0,1,1)),(10+forward[0],20,30+forward[2],1))
            # Noncommuting view: Ry(90) * T(-focus), focus=(1,2,3).
            view=((0,0,1,-3),(0,1,0,-2),(-1,0,0,1),(0,0,0,1))
            product=[[sum(view[i][k]*rows[4*k+j] for k in range(4)) for j in range(4)] for i in range(4)]
            self.assertVector([r[3] for r in product],(27,18,-9,1))

    def arrays(self, vertices, triangles):
        return (Vertex*len(vertices))(*(Vertex(*v) for v in vertices)), (Triangle*len(triangles))(*(Triangle(*t) for t in triangles))

    def ground(self,height=1800,flags=0):
        return self.arrays([(-100,height,-100),(-100,height,100),(100,height,-100),
                            (100,height,100)],[(0,1,2,0,flags),(2,1,3,0,flags)])

    def update(self,a,vertices,triangles,x=156,y=0,yaw=0,dt=.05,camera=False):
        return self.lib.movementUpdate(C.byref(a),x,y,yaw,dt,camera,vertices,triangles,len(triangles))

    def test_grounded_motion_stop_camera_mode_and_yaw(self):
        vertices,triangles=self.ground()
        for x,y,yaw in [(156,0,90),(-156,0,-90),(0,156,0),(0,-156,180)]:
            a=Actor(0,1800,0,0)
            self.assertTrue(self.update(a,vertices,triangles,x,y))
            self.assertAlmostEqual(a.yaw,yaw,places=4)
            self.assertAlmostEqual(math.hypot(a.x,a.z),7.5,places=5)
            before=bytes(a)
            self.assertFalse(self.update(a,vertices,triangles,12,16))
            self.assertEqual(bytes(a),before)
            self.assertFalse(self.update(a,vertices,triangles,camera=True))
            self.assertEqual(bytes(a),before)

    def test_missing_far_steep_and_filtered_floor_fail_closed(self):
        cases=[self.arrays([],[]),self.ground(1831),self.ground(1769),self.ground(flags=0x400000),
               self.ground(flags=0x20000),self.arrays([(-100,1000,-100),(-100,1000,100),
               (100,2600,-100)],[(0,1,2,0,0)])]
        for vertices,triangles in cases:
            a=Actor(0,1800,0,37); before=bytes(a)
            self.assertFalse(self.update(a,vertices,triangles))
            self.assertEqual(bytes(a),before)

    def test_floor_window_boundaries_winding_and_flags(self):
        for h in [1770,1830]:
            v,t=self.ground(h); a=Actor(0,1800,0,0)
            self.assertTrue(self.update(a,v,t)); self.assertEqual(a.y,h)
        v,t=self.ground(); t[0].a,t[0].b=t[0].b,t[0].a; t[1].a,t[1].b=t[1].b,t[1].a
        a=Actor(0,1800,0,0)
        self.assertFalse(self.update(a,v,t))
        for triangle in t: triangle.flags=0x10000
        self.assertTrue(self.update(a,v,t))
        v,t=self.ground(flags=0x80000700)
        self.assertTrue(self.update(a,v,t)) # Actual plateau flags are not a reject mask.

    def test_dt_and_rate_independence_on_flat_floor(self):
        self.assertEqual(self.lib.movementDelta(999,1000),0)
        self.assertAlmostEqual(self.lib.movementDelta(2000,1000),.05)
        v,t=self.ground()
        a=Actor(0,1800,0,0); b=Actor(0,1800,0,0)
        self.update(a,v,t,dt=.05)
        for _ in range(5): self.update(b,v,t,dt=.01)
        self.assertVector((a.x,a.y,a.z),(b.x,b.y,b.z))

    def test_real_collision_plateau_and_nearby_movement(self):
        paths=[ROOT/f'assets/model/{name}.model.bin' for name in ('14CF','14D0')]
        for path,expected in zip(paths,[2945,200]):
            _,records=read_collision(path)
            self.assertEqual(len(records),expected)
            self.assertEqual(len(records),len(set(records)))
        vertices,triangles=self.arrays(*scene_collision(paths))
        height=F(-1)
        self.assertTrue(self.lib.movementFloor(vertices,triangles,len(triangles),0,0,1800,C.byref(height)))
        self.assertEqual(height.value,1800)
        a=Actor(0,1800,0,0)
        self.assertTrue(self.update(a,vertices,triangles))
        self.assertVector((a.x,a.y,a.z),(7.5,1800,0))

    def test_viewer_local_golden_and_unchanged_map_render_sections(self):
        opa,xlu,banjo=[ROOT/f'assets/model/{n}.model.bin' for n in ('14CF','14D0','034D')]
        anim=ROOT/'assets/anim/006F.anim.bin'
        old=export_scene(opa,xlu,banjo,anim,runtime_actor=False)
        new=export_scene(opa,xlu,banjo,anim)
        render,collision=new.split('\n/* Static map collision;',1)
        def split(text):
            prefix,rest=text.split('banjo_vertices[] = {\n',1)
            v,suffix=rest.split('};',1)
            return prefix,v.splitlines(),suffix
        op,ov,os=split(old); np,nv,ns=split(render)
        self.assertEqual((op,os),(np,ns))
        self.assertEqual(ov[:9408],nv[:9408]); self.assertEqual(ov[11493:],nv[11493:])
        xyz=[tuple(float(x.strip().removesuffix('f')) for x in row.strip(' {},').split(',')[:3]) for row in nv[9408:11493]]
        self.assertEqual(hashlib.sha256(b''.join(struct.pack('>3f',*p) for p in xyz)).hexdigest(),
                         '7536cd507d67f2de4e3ab1bec2beb707fd902b361995b8c6ce5d208e16e2cc6c')
        for a,b in zip(ov[9408:11493],nv[9408:11493]): self.assertEqual(a.split(',')[3:],b.split(',')[3:])

    def test_collision_export_preserves_source_indices_winding_and_flags(self):
        paths=[ROOT/f'assets/model/{n}.model.bin' for n in ('14CF','14D0')]
        vertices,triangles=scene_collision(paths)
        base=0
        for path in paths:
            source,records=read_collision(path)
            for original,exported in zip(records,triangles[base:]):
                self.assertEqual([source[i] for i in original[:3]],
                                 [vertices[i] for i in exported[:3]])
                self.assertEqual(original[3:],exported[3:])
            base+=len(records)
        self.assertEqual(base,len(triangles))

    def test_sloped_floor_and_highest_valid_layer(self):
        v,t=self.arrays([(-100,1790,-100),(-100,1790,100),(100,1810,-100),
                         (100,1810,100)],[(0,1,2,0,0),(2,1,3,0,0)])
        a=Actor(0,1800,0,0)
        self.assertTrue(self.update(a,v,t))
        self.assertAlmostEqual(a.y,1800.75,places=4)
        # Overlapping levels: choose nearest downward hit inside the window,
        # independent of record order; do not snap to a distant upper layer.
        vertices=[]; triangles=[]
        for height in [1805,1795,1900]:
            offset=len(vertices)
            vertices.extend([(-100,height,-100),(-100,height,100),(100,height,0)])
            triangles.append((offset,offset+1,offset+2,0,0))
        for records in (triangles,list(reversed(triangles))):
            v,t=self.arrays(vertices,records); a=Actor(0,1800,0,0)
            self.assertTrue(self.update(a,v,t)); self.assertEqual(a.y,1805)
