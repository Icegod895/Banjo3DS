"""Category-4 Spiral Mountain rail against the canonical 071D volumes and knots."""
import ctypes as C
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import contact_corpus as contact
import test_camera as camera
from test_camera_contact import Scratch
from test_camera_manual import Rail, State, Trace
from test_camera_zones import production_data
from test_world_segment import Model
from tools.banjo3ds.camera_rail.setup import read_rail
from tools.banjo3ds.export_camera_data import export_camera_data

F = C.c_float
ROOT = camera.ROOT
SETUP = ROOT / 'assets/lvl_setup/071D.lvl_setup.bin'
PRESET = {1: (550.0, 175.0), 2: (850.0, 375.0), 3: (1100.0, 675.0)}
LEAD_FAR = 180.0
LEAD_CLOSE = 45000.0 / 330.0
ENABLED = 0x23


class Volume(C.Structure):
    _fields_ = [('center', C.c_int32 * 3), ('radius', C.c_int32), ('actor', C.c_int32),
                ('marker_bit', C.c_int32), ('spline_actor', C.c_int32),
                ('cube', C.c_int32 * 3), ('prop', C.c_int32)]


class Spline(C.Structure):
    _fields_ = [('knots', C.POINTER(F)), ('count', C.c_int32), ('actor', C.c_int32),
                ('scale', C.c_int32), ('origin', F * 3)]


class RailData(C.Structure):
    _fields_ = [('volumes', C.POINTER(Volume)), ('splines', C.POINTER(Spline)),
                ('volume_count', C.c_int32), ('spline_count', C.c_int32),
                ('cube_min', C.c_int32 * 3), ('cube_width', C.c_int32 * 3),
                ('stride', C.c_int32 * 2)]


def build_rail(spec):
    holders = []
    splines = []
    for sp in spec['splines']:
        flat = [c for knot in sp['knots'] for c in knot]
        buf = (F * len(flat))(*flat)
        holders.append(buf)
        splines.append(Spline(buf, len(sp['knots']), sp['actor'], sp['scale'], (F * 3)(*sp['origin'])))
    spline_arr = (Spline * len(splines))(*splines)
    volumes = (Volume * len(spec['volumes']))(*[
        Volume((C.c_int32 * 3)(*v['center']), v['radius'], v['actor'], v['marker_bit'],
               v['spline_actor'], (C.c_int32 * 3)(*v['cube']), v['prop'])
        for v in spec['volumes']])
    data = RailData(volumes, spline_arr, len(spec['volumes']), len(spec['splines']),
                    (C.c_int32 * 3)(*spec['minimum']), (C.c_int32 * 3)(*spec['width']),
                    (C.c_int32 * 2)(*spec['stride']))
    return data, holders, volumes, spline_arr


class CameraRailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='camera-rail-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.spec = read_rail(SETUP)
        cls.rail, cls._knots, cls._volumes, cls._splines = build_rail(cls.spec)
        cls.data, cls.keep, cls.raw = production_data()
        cls.world = contact.world('real')
        base = ROOT / 'tools/banjo3ds'
        sources = ('camera_manual/manual.c', 'camera_manual/contact.c', 'camera/camera.c',
                   'camera_contact/contact.c', 'camera_contact/free_b.c', 'camera_zones/zones.c',
                   'camera_rail/rail.c', 'world_query/segment.c')
        cls.libs = []
        for opt in ('-O0', '-O2'):
            so = Path(cls.tmp.name) / (opt + '.so')
            subprocess.run(['cc', *camera.FLAGS, opt, '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                            *[str(base / p) for p in sources], '-lm', '-o', str(so)], check=True)
            lib = C.CDLL(str(so))
            fp = C.POINTER(F)
            lib.bm_init.argtypes = [C.POINTER(State), C.POINTER(camera.Math), C.POINTER(camera.Input), fp, fp]
            lib.bm_update.argtypes = [C.POINTER(State), C.POINTER(camera.Math), C.POINTER(type(cls.data)),
                                      C.POINTER(camera.Input), C.c_uint, C.c_uint, C.POINTER(Model),
                                      C.POINTER(Model), fp, C.POINTER(Scratch), C.POINTER(Trace)]
            lib.bm_update.restype = C.c_bool
            lib.banjo_camera_math_init.argtypes = [C.POINTER(camera.Math)]
            lib.bq_open.argtypes = [C.POINTER(Model), C.c_void_p, C.c_size_t]
            lib.bq_open.restype = C.c_int
            lib.br_bind.argtypes = [C.POINTER(RailData)]
            for name in ('br_volume_size', 'br_spline_size', 'br_data_size', 'br_runtime_size', 'bm_state_size'):
                getattr(lib, name).restype = C.c_size_t
            lib.br_bind(C.byref(cls.rail))
            cls.libs.append(lib)

    def setUp(self):
        for lib in self.libs:
            lib.br_bind(C.byref(self.rail))

    def open_models(self, lib):
        models = [Model(), Model()]
        buffers = []
        for model, (_, packet) in zip(models, self.world):
            buf = C.create_string_buffer(packet)
            buffers.append(buf)
            self.assertEqual(lib.bq_open(C.byref(model), buf, len(packet)), 1)
        return models, buffers

    def fresh(self, lib, math, player, eye, rotation, lead, preset):
        state = State()
        lib.bm_init(C.byref(state), C.byref(math), C.byref(camera.make_input(self.command(player))),
                    (F * 3)(*eye), (F * 3)(*rotation))
        state.camera.preset = preset
        state.camera.position[:] = eye
        state.camera.rotation[:] = rotation
        state.camera.lead[:] = lead
        state.viewport_position[:] = eye
        state.viewport_rotation[:] = rotation
        return state

    def command(self, player, yaw=180.0, floor=None, dt=1 / 60, buttons=0):
        if floor is None:
            floor = player[1]
        return dict(player=list(player), floor=floor, yaw=yaw, under=floor, dt=dt, vi=1, stable=True, buttons=buttons)

    def step(self, lib, math, models, scratch, state, player, buttons=0, yaw=180.0, floor=None, dt=1 / 60):
        cmd = self.command(player, yaw, floor, dt, buttons)
        target = (F * 3)(player[0], player[1] + 80.0, player[2])
        trace = Trace()
        self.assertTrue(lib.bm_update(
            C.byref(state), C.byref(math), C.byref(self.data), C.byref(camera.make_input(cmd)),
            buttons, ENABLED, C.byref(models[0]), C.byref(models[1]), target, C.byref(scratch), C.byref(trace)))
        return trace

    def behind(self, lib, math, player, preset, lead_length, yaw=180.0):
        radius, height = PRESET[preset]
        lead = [0.0, 0.0, -lead_length]
        eye = [player[0], player[1] + height, player[2] + lead[2] + radius]
        return self.fresh(lib, math, player, eye, [0.0, yaw, 0.0], lead, preset), eye

    def test_layout_and_exported_knots(self):
        lib = self.libs[0]
        self.assertEqual(lib.br_volume_size(), C.sizeof(Volume))
        self.assertEqual(lib.br_spline_size(), C.sizeof(Spline))
        self.assertEqual(lib.br_data_size(), C.sizeof(RailData))
        self.assertEqual(lib.br_runtime_size(), C.sizeof(Rail))
        self.assertEqual(lib.bm_state_size(), C.sizeof(State))
        self.assertEqual([sp['actor'] for sp in self.spec['splines']], [49, 0xCC])
        self.assertEqual(len(self.spec['volumes']), 15)
        text = export_camera_data(ROOT / 'assets/model/14CF.model.bin',
                                   ROOT / 'assets/model/14D0.model.bin', SETUP)
        self.assertIn('{0,1999,-2614}', text)
        self.assertIn(float(1892).hex() + 'f', text)
        self.assertIn(float(-3779).hex() + 'f', text)
        self.assertIn('door sample (0, 1892, -3779)', text)
        for name in ('camera_rail/rail.c', 'camera_manual/manual.c'):
            source = (ROOT / 'tools/banjo3ds' / name).read_text()
            self.assertNotIn('-2210', source)
            self.assertNotIn('-3779', source)

    def test_outer_middle_dead_band_and_yaws(self):
        for lib in self.libs:
            math = camera.Math()
            lib.banjo_camera_math_init(C.byref(math))
            models, buffers = self.open_models(lib)
            scratch = Scratch()
            outer = [0.0, 1612.98, -2210.0]
            outside = [0.0, 1612.98, -2209.0]
            for preset, expect in ((2, 847.7), (3, 1112.5)):
                state, eye = self.behind(lib, math, outside, preset, LEAD_FAR)
                self.step(lib, math, models, scratch, state, outside)
                self.assertEqual(state.camera.mode, 2, preset)
                self.assertEqual(state.camera.state, 0xB, preset)
                self.assertEqual(state.rail.actor, 0, preset)
                state, eye = self.behind(lib, math, outer, preset, LEAD_FAR)
                self.step(lib, math, models, scratch, state, outer)
                self.assertEqual(state.camera.mode, 0xA,
                                 (preset, state.rail.engage_predicate, state.rail.engage_distance,
                                  state.rail.actor, state.rail.param, state.camera.state))
                self.assertEqual(state.camera.state, 0x12, preset)
                self.assertEqual(state.rail.actor, 0xCC, preset)
                self.assertEqual(state.rail.allow_zero, 1)
                self.assertEqual(state.rail.allow_one, 0)
                self.assertEqual(state.rail.engage_predicate, 1, state.rail.engage_distance)
                self.assertGreater(state.rail.engage_distance, 550.0)
                self.assertAlmostEqual(state.rail.engage_distance, expect, delta=1.0, msg=preset)
                self.assertNotEqual(bytes(state.camera.position), struct.pack('=3f', *eye))
            for yaw, lead_z, eye_at in (
                    (90.0, -145.0, [850.0, 1612.98 + 375.0, -2210.0]),
                    (0.0, -110.0, [0.0, 1612.98 + 375.0, -2210.0 - 850.0])):
                state = self.fresh(lib, math, outer, eye_at, [0.0, yaw, 0.0], [0.0, 0.0, lead_z], 2)
                self.step(lib, math, models, scratch, state, outer, yaw=180.0)
                self.assertEqual(state.camera.mode, 0xA, (yaw, state.rail.engage_distance, state.rail.engage_predicate))
                self.assertEqual(state.camera.state, 0x12, yaw)
            deck_y = 1784.0
            measured = {}
            for z in (-2210.0, -2500.0, -2800.0, -2811.0, -2812.0, -2813.0, -2814.0,
                      -3035.0, -3058.0, -3057.0, -3070.0):
                player = [0.0, deck_y, z]
                state, _eye = self.behind(lib, math, player, 1, LEAD_CLOSE)
                self.step(lib, math, models, scratch, state, player)
                measured[z] = (state.rail.engage_distance, state.rail.engage_predicate,
                               state.camera.mode, state.camera.state, state.rail.param)
            for z in (-2210.0, -2500.0, -2800.0, -2811.0, -2814.0, -3035.0):
                dist, pred, mode, dynamic, param = measured[z]
                self.assertEqual(pred, 2, (z, dist, param))
                self.assertEqual((mode, dynamic), (2, 0xB), (z, dist))
                self.assertGreater(dist, 500.0, (z, dist))
                self.assertLessEqual(dist, 550.0, (z, dist))
            # One-triangle graze snaps the parameter to the end. Neighbors above stay in the band.
            for z in (-2812.0, -2813.0):
                dist, pred, mode, dynamic, param = measured[z]
                self.assertEqual(pred, 1, (z, dist, param))
                self.assertEqual((mode, dynamic), (0xA, 0x12), z)
                self.assertGreater(param, 0.99, (z, param))
            # A3 crossed 550 between Z=-3058 (549.98) and Z=-3057 (550.04).
            # Host libm is about 0.08 higher, so Z=-3058 already returns 1.
            for z in (-3058.0, -3057.0, -3070.0):
                dist, pred, mode, dynamic, param = measured[z]
                self.assertEqual(pred, 1, (z, dist, param))
                self.assertEqual((mode, dynamic), (0xA, 0x12), (z, dist))
                self.assertGreater(dist, 550.0, (z, dist))
                self.assertLess(dist, 551.0, (z, dist, param))
            del buffers

    def test_gap_persistence_release_and_warp(self):
        for lib in self.libs:
            math = camera.Math()
            lib.banjo_camera_math_init(C.byref(math))
            models, buffers = self.open_models(lib)
            scratch = Scratch()
            outer = [0.0, 1612.98, -2210.0]
            state, _eye = self.behind(lib, math, outer, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, state, outer)
            gap = [0.0, 1784.0, -3330.0]
            self.step(lib, math, models, scratch, state, gap)
            self.assertEqual(state.camera.mode, 0xA)
            self.assertEqual(state.camera.state, 0x12)
            self.assertEqual(state.rail.actor, 0xCC)
            fresh, _eye = self.behind(lib, math, gap, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, fresh, gap)
            self.assertEqual(fresh.camera.mode, 2)
            self.assertEqual(fresh.camera.state, 0xB)
            self.assertEqual(fresh.rail.actor, 0)
            state, _eye = self.behind(lib, math, outer, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, state, outer)
            clear = [0.0, 1800.0, -1800.0]
            self.step(lib, math, models, scratch, state, clear)
            self.assertEqual((state.camera.mode, state.camera.state, state.rail.actor), (2, 0x12, 0))
            self.step(lib, math, models, scratch, state, clear)
            self.assertEqual((state.camera.mode, state.camera.state), (2, 0xB))
            warp = [0.0, 1944.0, -3780.0]
            state, _eye = self.behind(lib, math, warp, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, state, warp)
            self.assertEqual(state.camera.mode, 2)
            self.assertEqual(state.camera.state, 0xB)
            state, _eye = self.behind(lib, math, outer, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, state, outer)
            # Past every exported volume and past the param-1 knot, so the
            # camera keeps a positive step until the scale-1 end stop.
            plateau = [0.0, 1800.0, 3000.0]
            ended = False
            for _ in range(180):
                self.step(lib, math, models, scratch, state, plateau)
                if state.rail.actor == 0:
                    self.assertEqual(state.camera.mode, 0xA)
                    self.assertEqual(state.camera.state, 0x12)
                    ended = True
                    break
                self.assertEqual(state.camera.mode, 0xA)
            self.assertTrue(ended, state.rail.param)
            self.step(lib, math, models, scratch, state, plateau)
            self.assertEqual((state.camera.mode, state.camera.state, state.rail.actor), (2, 0x12, 0))
            self.step(lib, math, models, scratch, state, plateau)
            self.assertEqual((state.camera.mode, state.camera.state), (2, 0xB))
            del buffers

    def test_input_suppression_and_free_camera(self):
        for lib in self.libs:
            math = camera.Math()
            lib.banjo_camera_math_init(C.byref(math))
            models, buffers = self.open_models(lib)
            scratch = Scratch()
            outer = [0.0, 1612.98, -2210.0]
            quiet, _eye = self.behind(lib, math, outer, 2, LEAD_FAR)
            held, _eye = self.behind(lib, math, outer, 2, LEAD_FAR)
            buttons = 1 | 2 | 4 | 8
            self.step(lib, math, models, scratch, quiet, outer, 0)
            self.step(lib, math, models, scratch, held, outer, buttons)
            self.assertEqual(bytes(quiet.camera.position), bytes(held.camera.position))
            self.assertEqual(bytes(quiet.camera.rotation), bytes(held.camera.rotation))
            self.assertEqual(held.camera.preset, 2)
            self.assertEqual(held.camera.mode, 0xA)
            self.assertEqual(held.camera.state, 0x12)
            outside = [0.0, 1612.98, -2209.0]
            state, _eye = self.behind(lib, math, outside, 2, LEAD_FAR)
            self.step(lib, math, models, scratch, state, outside, 1)
            self.assertEqual(state.camera.mode, 4)
            self.assertEqual(state.camera.state, 19)
            def run(player, bound):
                lib.br_bind(C.byref(self.rail) if bound else None)
                eye = [player[0], player[1] + 375.0, player[2] - 850.0]
                rotation = [340.0, 180.0, 0.0]
                state = self.fresh(lib, math, player, eye, rotation, [0.0, 0.0, 0.0], 2)
                rows = []
                for buttons in (0, 0, 0, 1, 1, 0, 0):
                    self.step(lib, math, models, scratch, state, player, buttons, yaw=180.0, floor=player[1])
                    rows.append((bytes(state.camera.position), bytes(state.camera.rotation), bytes(state.camera.lead),
                                 state.camera.mode, state.camera.state, state.camera.preset,
                                 struct.pack('=f', state.profile_radius), struct.pack('=f', state.profile_height)))
                return rows

            # One unit outside the outer volume: unzoned free B, including R.
            free = [0.0, 1800.0, -2209.0]
            unbound = run(free, False)
            self.assertEqual(unbound, run(free, True))
            self.assertEqual(unbound[0][3:6], (2, 0xB, 2))
            self.assertEqual(unbound[3][3], 4)
            # Node 32 zoom at the spawn marker stays on the category-9 path.
            spawn = [0.0, 1800.0, 0.0]
            self.assertEqual(run(spawn, False), run(spawn, True))
            lib.br_bind(C.byref(self.rail))
            del buffers
