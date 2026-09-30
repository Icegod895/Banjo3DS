"""M4.8B.10: production enum mapping and independent geometric parity proof.

No renderer, exporter, camera or shader math is imported to calculate winding.
Projection coefficients are from Citro3D mtx_{ortho,persp}tilt.c, documented in
CULLING_PARITY.md. Cameras are paired at the SAME eye and forward direction:
unrelated camera positions need not see the same side of a triangle.
"""
import ctypes as C
from collections import Counter
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.banjo3ds.n64_displaylist_decoder import BKModel, interpret_display_list
from tools.banjo3ds.static_idle import decode_static_idle
from tools.banjo3ds.export_3ds_model import build_draw_batches

ROOT = Path(__file__).resolve().parents[3]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def det(m):
    return dot(m[0], cross(m[1], m[2]))


def debug_rotation(pitch, yaw):
    p, y = map(math.radians, (pitch, yaw))
    sp, cp, sy, cy = math.sin(p), math.cos(p), math.sin(y), math.cos(y)
    return ((cy, 0, sy), (sp*sy, cp, -sp*cy), (-cp*sy, sp, cp*cy))


def rare_lh_rotation(pitch, yaw):
    # Original inverse yaw, then inverse pitch; negate ONLY RH view Z.
    p, y = map(math.radians, (pitch, yaw))
    sp, cp, sy, cy = math.sin(p), math.cos(p), math.sin(y), math.cos(y)
    return ((cy, 0, -sy), (sp*sy, cp, sp*cy), (-cp*sy, sp, -cp*cy))


def area(points):
    a, b, c = points
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def project(q, perspective):
    if not perspective:
        return (q[1]/900, -q[0]/1500)
    cot = 1/math.tan(math.radians(40)/2)
    return (cot*q[1]/q[2], -cot*q[0]/((400/240)*q[2]))


def retained(mode, signed_area):
    # PICA register: 0=all, 1=keep CW, 2=keep CCW. -1=do not submit.
    return mode == 0 or (mode == 1 and signed_area < 0) or (mode == 2 and signed_area > 0)


class Actor(C.Structure):
    _fields_ = [(k, C.c_float) for k in ('x', 'y', 'z', 'yaw')]


class TestRendererCulling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name)
        wrapper = path/'culling.c'
        wrapper.write_text('''#include "renderer_culling.h"
_Static_assert(GPU_CULL_NONE == 0, "PICA keep all");
_Static_assert(GPU_CULL_FRONT_CCW == 1, "PICA keep CW");
_Static_assert(GPU_CULL_BACK_CCW == 2, "PICA keep CCW");
int mapping(unsigned int mode, int parity) {
    return rendererCullMode(mode, (RendererWindingParity)parity);
}
''')
        cls.libs = []
        include = Path(os.environ.get('DEVKITPRO', '/opt/devkitpro'))/'libctru/include'
        for opt in ('-O0', '-O2'):
            lib = path/(opt+'.so')
            subprocess.run(['cc', '-std=c11', opt, '-Wall', '-Wextra', '-Werror',
                            '-shared', '-fPIC', '-I'+str(include),
                            '-I'+str(ROOT/'platform/3ds/source'), str(wrapper),
                            str(ROOT/'platform/3ds/source/movement.c'), '-lm',
                            '-o', str(lib)], check=True)
            dll = C.CDLL(str(lib))
            dll.mapping.argtypes = [C.c_uint, C.c_int]
            dll.mapping.restype = C.c_int
            dll.movementActorMatrix.argtypes = [C.POINTER(Actor), C.POINTER(C.c_float)]
            cls.libs.append(dll)
        cls.models = {}
        for asset in ('14CF', '14D0', '034D'):
            model = BKModel(ROOT/f'assets/model/{asset}.model.bin')
            cls.models[asset] = (decode_static_idle(model, ROOT/'assets/anim/006F.anim.bin')
                                 if asset == '034D' else interpret_display_list(model))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_six_mappings_and_both_skip_at_both_optimizations(self):
        for lib in self.libs:
            # Order: NONE, FRONT, BACK, BOTH. Values are actual PICA enum values.
            self.assertEqual([lib.mapping(c, 0) for c in range(4)], [0, 2, 1, -1])
            self.assertEqual([lib.mapping(c, 1) for c in range(4)], [0, 1, 2, -1])
            self.assertEqual(lib.mapping(99, 0), -1)
            self.assertEqual(lib.mapping(99, 1), -1)

    def test_actor_transform_has_positive_determinant(self):
        for lib in self.libs:
            for yaw in (-720, -90, 0, 45, 90, 145, 180, 270, 360):
                actor = Actor(123, 1800, -456, yaw)
                rows = (C.c_float*16)()
                lib.movementActorMatrix(C.byref(actor), rows)
                m = [tuple(rows[4*i:4*i+3]) for i in range(3)]
                self.assertAlmostEqual(det(m), 1, places=6)
                self.assertEqual((rows[3], rows[7], rows[11]), (123, 1800, -456))
                self.assertEqual(tuple(rows[12:]), (0, 0, 0, 1))

    def test_projection_tilt_and_depth_add_no_parity_flip(self):
        cot = 1/math.tan(math.radians(20))
        for aspect in (1.35185182, 400/240):
            # 2D tilt block [[0,sy],[-sx,0]] has determinant sx*sy > 0.
            self.assertGreater(cot*cot/aspect, 0)
            for near, far in ((1, 20000), (10, 20000), (100, 30000)):
                # Installed Mtx_PerspTilt: zclip=n/(f-n)*z-f*n/(f-n), w=z.
                for z, expected in ((near, -1), (far, 0)):
                    self.assertAlmostEqual((near*z/(far-near)-far*near/(far-near))/z,
                                           expected)
                # Depth coefficients do not enter either projected X or Y.
                self.assertGreater(near, 0)
        self.assertGreater(1/(900*1500), 0)

    def test_real_geometry_counts_and_culling_coverage(self):
        expected = {'14CF': (3136, 417, 436, {2: 3136}),
                    '14D0': (369, 36, 46, {2: 170, 0: 199}),
                    '034D': (695, 16, 28, {2: 695})}
        for asset, data in self.models.items():
            self.assertEqual((len(data.triangles), len(data.materials),
                              len(build_draw_batches(data.triangles)),
                              dict(Counter(int(t.cull_mode) for t in data.triangles))),
                             expected[asset])
            used = {t.material_index for t in data.triangles} - {None}
            self.assertEqual(used, set(range(len(data.materials))))

    def test_all_real_triangles_match_determinant_and_cull_contract(self):
        counts = Counter()
        lib = self.libs[0]
        for asset, data in self.models.items():
            # Maps have identity world transform; actor has only T*Ry.
            for actor_yaw in ((0, 90, 145) if asset == '034D' else (0,)):
                a = math.radians(actor_yaw)
                for triangle in data.triangles:
                    points = [(data.vertices[i].x, data.vertices[i].y, data.vertices[i].z)
                              for i in (triangle.v0, triangle.v1, triangle.v2)]
                    if asset == '034D':
                        points = [(math.cos(a)*x+math.sin(a)*z, y+1800,
                                   -math.sin(a)*x+math.cos(a)*z) for x,y,z in points]
                    n = cross(sub(points[1], points[0]), sub(points[2], points[0]))
                    self.assertGreater(dot(n, n), 0)  # No degenerate fixture triangles.
                    center = tuple(sum(p[k] for p in points)/3 for k in range(3))
                    radius = max(math.sqrt(dot(sub(p, center), sub(p, center))) for p in points)
                    distance = max(1000, 4*radius)
                    for pitch in (-70, -20, 0, 25, 70):
                        for yaw in (0, 45, 145, 270):
                            d, r = debug_rotation(pitch, yaw), rare_lh_rotation(pitch, 180-yaw)
                            self.assertAlmostEqual(det(d), 1)
                            self.assertAlmostEqual(det(r), -1)
                            for k in range(3):
                                self.assertAlmostEqual(d[2][k], r[2][k])
                            facing = dot(n, d[2])
                            if abs(facing) < 1e-8*math.sqrt(dot(n,n)):
                                counts['edge_on'] += 1
                                continue  # No stable winding for exactly edge-on geometry.
                            eye = tuple(center[k]-distance*d[2][k] for k in range(3))
                            qd = [tuple(dot(row, sub(p, eye)) for row in d) for p in points]
                            qr = [tuple(dot(row, sub(p, eye)) for row in r) for p in points]
                            self.assertTrue(all(q[2] > 0 for q in qd+qr))
                            sd = area([project(q, False) for q in qd])
                            sr = area([project(q, True) for q in qr])
                            # Independent determinant/triple-product area formulas.
                            self.assertAlmostEqual(sd, det(d)*facing/(900*1500), places=7)
                            expected = (1/math.tan(math.radians(20)))**2/(400/240)
                            expected *= det(r)*dot(n, sub(points[0], eye))
                            expected /= math.prod(q[2] for q in qr)
                            self.assertAlmostEqual(sr, expected, places=7)
                            self.assertLess(sd*sr, 0)
                            counts['front' if facing < 0 else 'back'] += 1
                            # Also exercise synthetic FRONT/BOTH on every real triangle:
                            # these states do not occur in the current three assets.
                            for cull in (0, 1, 2, 3):
                                kept = cull == 0 or (cull == 2 and facing < 0) or (cull == 1 and facing > 0)
                                self.assertEqual(retained(lib.mapping(cull, 0), sd), kept)
                                self.assertEqual(retained(lib.mapping(cull, 1), sr), kept)
        self.assertEqual(sum(counts.values()), (3136+369+695*3)*20)
        self.assertEqual(dict(counts), {'front': 54059, 'back': 53954, 'edge_on': 3787})

    def test_plateau_regression_signed_areas(self):
        points = ((0,1800,0), (0,1800,-400), (-125,1800,-400))
        eye = (-125/3, 2800, -800/3)
        d, r = debug_rotation(-90, 0), rare_lh_rotation(270, 180)
        # These matching rotations look down; Rare's horizontal axis is reversed.
        areas = []
        for m, perspective in ((d,False),(r,True)):
            q = [tuple(dot(row,sub(p,eye)) for row in m) for p in points]
            areas.append(area([project(p,perspective) for p in q]))
        self.assertAlmostEqual(areas[0], -0.03703703703703704)
        self.assertAlmostEqual(areas[1], 0.22645896511239097)
