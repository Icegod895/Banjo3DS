"""A3P1 Bottles and molehill pose: original assets, no Banjo packet changes."""
import ctypes as C
import hashlib
import math
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.actor_mesh import (
    export_actor_header, load_actor, parse_packet, reference_evaluate, skeleton_bytes,
)
from tools.banjo3ds.export_3ds_model import (
    build_draw_batches, encode_3ds_rgba8_pixels, find_texture_for_load,
    n64_texture_coordinate_to_uv,
)
from tools.banjo3ds.n64_displaylist_decoder import BKModel
from tools.banjo3ds.pose_binding import export_pose_packet
from tools.banjo3ds.static_idle import f32

def active_source(source, isolation, texture_upload=0, vertex_init=0, hill_draw=0):
    """Keep lines compiled for one isolation, upload, and vertex-init triple.

    Other conditions stay on their taken branch. An unknown #if is taken, so a
    call hidden only by an unrelated flag still counts as present. An #elif
    or #else is kept only when no earlier branch of that chain was taken.
    """

    def known_condition(expression):
        expression = ' '.join(expression.split())
        flags = {
            'BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER': False,
            'BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER': False,
            'BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER || BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER': False,
            'BANJO3DS_ACTOR_HILL_OPEN_ANIMATION': False,
            'BANJO3DS_ACTOR_BOTTLES_B_INTERACTION': False,
            '!BANJO3DS_ACTOR_BOTTLES_B_INTERACTION': True,
            'BANJO3DS_ACTOR_BOTTLES_EXIT': False,
            'BANJO3DS_ACTOR_BOTTLES_EMERGENCE': False,
            '!BANJO3DS_ACTOR_BOTTLES_EMERGENCE': True,
            'BANJO3DS_ACTOR_IDLE_ANIMATION': False,
            'BANJO3DS_ACTOR_STATIC_BOTTLES': False,
            'BANJO3DS_ACTOR_HILL_DRAW': hill_draw != 0,
            'BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_HILL_DRAW':
                isolation == 0 or hill_draw != 0,
            'BANJO3DS_ACTOR_ISOLATION': isolation != 0,
            'BANJO3DS_ACTOR_ISOLATION == 0': isolation == 0,
            'BANJO3DS_ACTOR_ISOLATION == 1': isolation == 1,
            'BANJO3DS_ACTOR_TEXTURE_UPLOAD': texture_upload != 0,
            'BANJO3DS_ACTOR_TEXTURE_UPLOAD == 0': texture_upload == 0,
            'BANJO3DS_ACTOR_TEXTURE_UPLOAD == 1': texture_upload == 1,
            'BANJO3DS_ACTOR_VERTEX_INIT': vertex_init != 0,
            'BANJO3DS_ACTOR_VERTEX_INIT == 0': vertex_init == 0,
            'BANJO3DS_ACTOR_VERTEX_INIT == 1': vertex_init == 1,
            'BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_TEXTURE_UPLOAD':
                isolation == 0 or texture_upload != 0,
            'BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_VERTEX_INIT':
                isolation == 0 or vertex_init != 0,
        }
        return flags.get(expression)

    known_macros = (
        'BANJO3DS_ACTOR_BOTTLES_B_INTERACTION',
        'BANJO3DS_ACTOR_BOTTLES_EXIT',
        'BANJO3DS_ACTOR_BOTTLES_EMERGENCE',
        'BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER',
        'BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER',
        'BANJO3DS_ACTOR_HILL_OPEN_ANIMATION',
        'BANJO3DS_ACTOR_IDLE_ANIMATION',
        'BANJO3DS_ACTOR_STATIC_BOTTLES',
        'BANJO3DS_ACTOR_HILL_DRAW',
        'BANJO3DS_ACTOR_ISOLATION',
        'BANJO3DS_ACTOR_TEXTURE_UPLOAD',
        'BANJO3DS_ACTOR_VERTEX_INIT',
    )
    stack = []
    kept = []
    for line in source.splitlines(True):
        stripped = line.strip()
        parent = all(frame['parent'] and frame['cond'] for frame in stack)
        if stripped.startswith(('#if ', '#ifdef ', '#ifndef ')):
            kind, expression = stripped.split(None, 1)
            if kind == '#ifndef' and expression in known_macros:
                condition = False
            elif kind == '#ifdef' and expression in known_macros:
                condition = True
            elif kind == '#if':
                condition = known_condition(expression)
                if condition is None:
                    condition = True
            else:
                condition = True
            stack.append({
                'parent': parent,
                'cond': condition,
                'else': False,
                'matched': condition,
            })
            continue
        if stripped.startswith('#elif '):
            frame = stack[-1]
            known = known_condition(stripped[len('#elif '):])
            if frame['else'] or frame['matched'] or known is None:
                frame['cond'] = False
            else:
                frame['cond'] = bool(known)
                frame['matched'] = frame['cond']
            continue
        if stripped.startswith('#else'):
            frame = stack[-1]
            frame['else'] = True
            frame['cond'] = not frame['matched']
            continue
        if stripped.startswith('#endif'):
            stack.pop()
            continue
        if parent:
            kept.append(line)
    if stack:
        raise RuntimeError('unbalanced preprocessor condition in main.c')
    return ''.join(kept)


ROOT = Path(__file__).resolve().parents[3]
BOTTLES = ROOT / 'assets/model/0387.model.bin'
HILL = ROOT / 'assets/model/0388.model.bin'
IDLE = ROOT / 'assets/anim/013B.anim.bin'
PHASES = (0.0, 0.25, 0.5, 0.75, 1.0)
TEXTURE_SHA256 = {
    (0, 64, 64, 0): '311e2fd98c0077e11003dd6ed7543c88da11522f7869d28ee6b9ba06ca7a45ee',
    (1, 32, 32, 0): '5a422fb882e18f5588befeceea7ca0cd930b8d350c2c4617d42d2ba7be23ca62',
    (1, 16, 16, 1): '3bb6f8a588a35924f1877bc0c2981590b60e2bd5b948344a7b4077611d64b143',
    (1, 8, 8, 2): '1ccb0ae1782f8a1783ee822c30fda5fceb15a01c4d1c7c1b93d6f31459b3f8e6',
    (1, 16, 16, 0): '34f677b14663c2a76762b618883024ca93c7a8971a1e13d1ed4c09bf36998ed5',
    (3, 16, 16, 0): 'daf1ae916363dcb99d807d4c9f33108d6a5f886afb09d61d091b08d4336e0851',
    (5, 16, 16, 0): '7e2c29c84529188f2e5420495ec1c1dca17a3e69d172dc762df030b353395b23',
}


class Info(C.Structure):
    _fields_ = [
        ('matrix_count', C.c_uint32), ('load_count', C.c_uint32),
        ('corner_count', C.c_uint32), ('bone_slots', C.c_uint32),
        ('anim_bytes', C.c_uint32), ('anim_last', C.c_uint16),
        ('anim_channels', C.c_uint16), ('factor', C.c_float),
        ('boneless', C.c_uint32),
    ]


class BanjoPose(C.Structure):
    _fields_ = [
        ('bones', (C.c_float * 10) * 109),
        ('matrices', ((C.c_float * 4) * 4) * 60),
        ('xyz', (C.c_float * 3) * 723),
    ]


def packed(values):
    values = [float(value) for value in values]
    return struct.pack('>' + 'f' * len(values), *values)


def advance_reference(phase, dt, duration):
    if not all(math.isfinite(value) for value in (phase, dt, duration)) or not duration > 0:
        return phase
    tmp = f32(f32(phase) + f32(f32(dt) / f32(duration)))
    tmp = f32(tmp - float(int(tmp)))
    return f32(tmp + 1.0) if tmp < 0 else tmp


class ActorPoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idle = IDLE.read_bytes()
        cls.hill = load_actor(HILL, 'molehill', boneless=True)
        cls.bottles = load_actor(BOTTLES, 'bottles', cls.idle)
        cls.header = export_actor_header(BOTTLES, HILL, IDLE)
        cls.temporary = tempfile.TemporaryDirectory(prefix='banjo-actor-pose-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.libs = []
        flags = ['-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                 '-ffp-contract=off', '-fno-fast-math', '-fexcess-precision=standard']
        for optimization in ('-O0', '-O2'):
            output = Path(cls.temporary.name) / (optimization + '.so')
            subprocess.run(['cc', *flags, optimization,
                            str(ROOT / 'tools/banjo3ds/actor_pose/actor_pose.c'),
                            '-lm', '-o', str(output)], check=True, capture_output=True)
            lib = C.CDLL(str(output))
            lib.actor_pose_info.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(Info)]
            lib.actor_pose_info.restype = C.c_bool
            lib.actor_pose_evaluate.argtypes = [
                C.c_char_p, C.c_size_t, C.c_float, C.POINTER(C.c_float),
                C.POINTER(C.c_float), C.POINTER(C.c_float)]
            lib.actor_pose_evaluate.restype = C.c_bool
            lib.actor_pose_advance.argtypes = [C.c_float, C.c_float, C.c_float]
            lib.actor_pose_advance.restype = C.c_float
            lib.actor_pose_placement.argtypes = [
                C.POINTER(C.c_float), C.c_float, C.c_float, C.c_float, C.c_float, C.c_float]
            cls.libs.append(lib)
        banjo = Path(cls.temporary.name) / 'banjo.so'
        subprocess.run(['cc', *flags, '-O2', str(ROOT / 'tools/banjo3ds/pose/pose.c'),
                        '-lm', '-o', str(banjo)], check=True, capture_output=True)
        cls.banjo = C.CDLL(str(banjo))
        cls.banjo.banjo_pose_evaluate.argtypes = [C.c_char_p, C.c_size_t, C.c_float, C.POINTER(BanjoPose)]
        cls.banjo.banjo_pose_evaluate.restype = C.c_bool

    def info(self, packet, lib=None):
        out = Info()
        ok = (lib or self.libs[0]).actor_pose_info(packet, len(packet), C.byref(out))
        return ok, out

    def evaluate(self, packet, phase, lib):
        view = parse_packet(packet)
        bones = (C.c_float * (view.bone_slots * 10))()
        matrices = (C.c_float * (view.matrix_count * 16))()
        xyz = (C.c_float * (view.load_count * 3))()
        ok = lib.actor_pose_evaluate(packet, len(packet), phase, bones, matrices, xyz)
        return ok, bones, matrices, xyz

    def assert_matches(self, packet, phase, lib):
        transforms, matrices, xyz = reference_evaluate(packet, phase)
        ok, bones, c_matrices, c_xyz = self.evaluate(packet, phase, lib)
        self.assertTrue(ok)
        self.assertEqual(packed(bones), packed(value for row in transforms for value in row))
        self.assertEqual(packed(c_matrices), packed(value for matrix in matrices for row in matrix for value in row))
        self.assertEqual(packed(c_xyz), packed(value for row in xyz for value in row))
        self.assertTrue(all(math.isfinite(value) for row in xyz for value in row))
        if phase == 0.0 and lib is self.libs[0]:
            view = parse_packet(packet)
            scattered = (C.c_byte * (view.corner_count * 12))()
            lib.actor_pose_scatter.argtypes = [
                C.c_char_p, C.c_size_t, C.POINTER(C.c_float), C.c_void_p,
                C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t]
            lib.actor_pose_scatter.restype = C.c_bool
            self.assertTrue(lib.actor_pose_scatter(
                packet, len(packet), c_xyz, scattered, view.corner_count, 0, view.corner_count, 12))
            flat = b''.join(struct.pack('<3f', c_xyz[index * 3], c_xyz[index * 3 + 1], c_xyz[index * 3 + 2])
                             for index in view.corners)
            self.assertEqual(bytes(scattered), flat)

    def test_original_asset_census(self):
        bottles, hill = self.bottles, self.hill
        self.assertEqual((len(bottles.render.triangles), len(bottles.loads), len(bottles.corners), len(bottles.calls)),
                         (617, 590, 1851, 54))
        self.assertEqual((len(hill.render.triangles), len(hill.loads), len(hill.corners), len(hill.calls)),
                         (56, 73, 168, 7))
        self.assertEqual(bottles.selector_log, [(1, 1, True), (3, 0, False), (4, 0, False)])
        self.assertEqual(hill.selector_log, [])
        self.assertEqual(sum(triangle.material_index is None for triangle in bottles.render.triangles), 14)
        self.assertTrue(all(triangle.combine is not None for triangle in bottles.render.triangles))
        self.assertEqual({(load.texture_index, load.texture_type, load.width, load.height,
                           load.palette_offset, load.texel_offset, load.texture_level, load.texture_on)
                          for load in bottles.render.texture_loads},
                         {(1, 'CI4', 16, 16, 0, 32, 0, 1),
                          (3, 'CI4', 16, 16, 0, 32, 0, 1),
                          (5, 'CI4', 16, 16, 0, 32, 0, 1)})
        self.assertEqual([(load.texture_index, load.texture_type, load.width, load.height,
                           load.palette_offset, load.texel_offset, load.texture_level, load.texture_on)
                          for load in hill.render.texture_loads],
                         [(0, 'CI4', 64, 64, 0, 32, 0, 1),
                          (0, 'CI4', 64, 64, 0, 32, 0, 1),
                          (0, 'CI4', 64, 64, 0, 32, 0, 1),
                          (1, 'RGBA16', 32, 32, None, 0, 2, 1)])
        self.assertEqual(bottles.geo_type, 0)
        self.assertEqual(hill.geo_type, 2)
        self.assertEqual((bottles.linear_filter, hill.linear_filter), (0, 1))
        file_textures = {
            'bottles': [(BKModel(BOTTLES).read_texture(index)['type_name'],
                         BKModel(BOTTLES).read_texture(index)['width'],
                         BKModel(BOTTLES).read_texture(index)['height'])
                        for index in range(BKModel(BOTTLES).texture_count)],
            'hill': [(BKModel(HILL).read_texture(index)['type_name'],
                      BKModel(HILL).read_texture(index)['width'],
                      BKModel(HILL).read_texture(index)['height'])
                     for index in range(BKModel(HILL).texture_count)],
        }
        self.assertEqual(file_textures['bottles'], [('CI4', 16, 16)] * 8 + [('CI4', 64, 32)])
        self.assertEqual(file_textures['hill'], [('CI4', 64, 64), ('RGBA16', 32, 32)])

    def test_texture_encoding_is_stable(self):
        seen = []
        for mesh in (self.hill, self.bottles):
            for texture in mesh.render.textures:
                digest = hashlib.sha256(encode_3ds_rgba8_pixels(
                    texture.width, texture.height, texture.pixels)).hexdigest()
                seen.append((texture.texture_index, texture.width, texture.height, 0))
                self.assertEqual(digest, TEXTURE_SHA256[seen[-1]])
                for level, pixels in enumerate(texture.mipmaps or [], start=1):
                    digest = hashlib.sha256(encode_3ds_rgba8_pixels(
                        texture.width >> level, texture.height >> level, pixels)).hexdigest()
                    key = (texture.texture_index, texture.width >> level, texture.height >> level, level)
                    seen.append(key)
                    self.assertEqual(digest, TEXTURE_SHA256[key])
        self.assertEqual(seen, list(TEXTURE_SHA256))

    def test_packets_preserve_skeleton_and_clip(self):
        for mesh, model_path, animation in (
            (self.hill, HILL, b''),
            (self.bottles, BOTTLES, self.idle),
        ):
            factor, count, records = skeleton_bytes(model_path.read_bytes())
            view = parse_packet(mesh.packet)
            self.assertEqual(view.records, records)
            self.assertEqual(view.matrix_count, count)
            self.assertEqual(mesh.packet[32:36], factor)
            self.assertEqual(view.animation, animation)
        hill, bottles = parse_packet(self.hill.packet), parse_packet(self.bottles.packet)
        self.assertEqual((len(self.hill.packet), hill.matrix_count, hill.bone_slots, hill.boneless),
                         (1000, 2, 70, True))
        self.assertEqual((len(self.bottles.packet), bottles.matrix_count, bottles.load_count,
                          bottles.bone_slots, bottles.anim_last, bottles.anim_channels, bottles.factor),
                         (11258, 37, 590, 72, 267, 42, 9.0))
        self.assertEqual(struct.unpack_from('>hhhH', self.idle), (0, 267, 42, 0))

    def test_c_matches_reference_at_both_optimizations(self):
        for phase in PHASES:
            for lib in self.libs:
                with self.subTest(phase=phase, optimized=lib is self.libs[1]):
                    self.assert_matches(self.bottles.packet, phase, lib)
                    self.assert_matches(self.hill.packet, phase, lib)

    def test_idle_moves_and_closed_hill_stays_raw(self):
        _, _, start = reference_evaluate(self.bottles.packet, 0.0)
        _, _, middle = reference_evaluate(self.bottles.packet, 0.5)
        raw = [(x, y, z) for x, y, z, _ in parse_packet(self.bottles.packet).loads]
        self.assertNotEqual(start, middle)
        self.assertNotEqual(start, raw)
        _, matrices, xyz = reference_evaluate(self.hill.packet, 0.0)
        identity = tuple(tuple(1.0 if row == column else 0.0 for column in range(4)) for row in range(4))
        self.assertEqual(matrices, [identity, identity])
        self.assertEqual(xyz, [(x, y, z) for x, y, z, _ in parse_packet(self.hill.packet).loads])

    def test_packets_reject_each_other_and_bad_phase(self):
        walk = export_pose_packet(ROOT / 'assets/model/034D.model.bin', ROOT / 'assets/anim/0003.anim.bin')
        self.assertFalse(self.info(walk)[0])
        pose = BanjoPose()
        self.assertFalse(self.banjo.banjo_pose_evaluate(self.bottles.packet, len(self.bottles.packet), 0, C.byref(pose)))
        self.assertFalse(self.evaluate(self.bottles.packet, float('nan'), self.libs[0])[0])
        self.assertFalse(self.evaluate(self.bottles.packet, 1.01, self.libs[0])[0])
        self.assertFalse(self.info(self.bottles.packet[:-1])[0])
        broken = bytearray(self.hill.packet)
        broken[:4] = b'B3P3'
        self.assertFalse(self.info(bytes(broken))[0])

    def test_placement_and_idle_clock(self):
        rows = (C.c_float * 16)()
        self.libs[0].actor_pose_placement(rows, 2250, -34, 2774, 0, 1)
        expected = [1, 0, 0, 2250, 0, 1, 0, -34, 0, 0, 1, 2774, 0, 0, 0, 1]
        self.assertEqual(packed(rows), packed(expected))
        self.assertEqual(struct.pack('<f', rows[8]), struct.pack('<f', 0.0))
        libm = C.CDLL('libm.so.6')
        libm.cosf.argtypes = libm.sinf.argtypes = [C.c_float]
        libm.cosf.restype = libm.sinf.restype = C.c_float
        product = f32(f32(90.0) * f32(0.017453292519943295))
        cosine = f32(libm.cosf(C.c_float(product)) * f32(2.0))
        sine = f32(libm.sinf(C.c_float(product)) * f32(2.0))
        self.libs[1].actor_pose_placement(rows, 1, 2, 3, 90, 2)
        self.assertEqual(packed(rows), packed([
            cosine, 0, sine, 1, 0, 2, 0, 2, -sine, 0, cosine, 3, 0, 0, 0, 1]))
        advance = self.libs[0].actor_pose_advance
        self.assertEqual(advance(0, 7, 7), 0)
        self.assertEqual(advance(0.5, 3.5, 7), 0)
        self.assertEqual(advance(0.2, -0.7, 7), advance_reference(0.2, -0.7, 7))
        self.assertEqual(advance(0.25, 0.05, 7), advance_reference(0.25, 0.05, 7))
        self.assertEqual(advance(0.25, 0.05, 0), 0.25)
        self.assertTrue(math.isnan(advance(float('nan'), 0.05, 7)))

    def test_generated_header_contract(self):
        header = self.header
        for line in (
            '#define ACTOR_PLACE_X 2250.0f',
            '#define ACTOR_PLACE_Y (-34.0f)',
            '#define ACTOR_PLACE_Z 2774.0f',
            '#define ACTOR_PLACE_YAW 0.0f',
            '#define ACTOR_PLACE_SCALE 1.0f',
            '#define ACTOR_BOTTLES_IDLE_DURATION 7.0f',
            '#define ACTOR_HILL_FIRST_VERTEX 0',
            '#define ACTOR_HILL_VERTEX_COUNT 168',
            '#define ACTOR_BOTTLES_FIRST_VERTEX 168',
            '#define ACTOR_BOTTLES_VERTEX_COUNT 1851',
            '#define ACTOR_HILL_FIRST_DRAW 0',
            '#define ACTOR_HILL_PACKET_SIZE 1000',
            '#define ACTOR_BOTTLES_PACKET_SIZE 11258',
            '#define ACTOR_HILL_MATRIX_COUNT 2',
            '#define ACTOR_HILL_BONE_SLOTS 70',
            '#define ACTOR_BOTTLES_MATRIX_COUNT 37',
            '#define ACTOR_BOTTLES_LOAD_COUNT 590',
            '#define ACTOR_BOTTLES_BONE_SLOTS 72',
            '#define ACTOR_BOTTLES_ANIM_LAST 267',
            '#define ACTOR_BOTTLES_ANIM_CHANNELS 42',
        ):
            self.assertIn(line + '\n', header)
        hill_draws = int(re.search(r'#define ACTOR_HILL_DRAW_COUNT (\d+)', header).group(1))
        bottles_draws = int(re.search(r'#define ACTOR_BOTTLES_DRAW_COUNT (\d+)', header).group(1))
        self.assertGreater(hill_draws, 0)
        self.assertGreater(bottles_draws, 0)
        self.assertIn(f'#define ACTOR_BOTTLES_FIRST_DRAW {hill_draws}\n', header)
        self.assertLess(header.index('actor_molehill_packet'), header.index('actor_bottles_packet'))
        self.assertIn(', '.join(f'0x{byte:02x}' for byte in self.hill.packet[:16]), header)
        self.assertIn(', '.join(f'0x{byte:02x}' for byte in self.bottles.packet[:16]), header)
        descriptors = re.findall(
            r'\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),',
            header.split('actor_texture_info[] = {', 1)[1].split('};', 1)[0])
        self.assertEqual(descriptors, [
            ('64', '64', '0', '1'), ('32', '32', '2', '1'),
            ('16', '16', '0', '0'), ('16', '16', '0', '0'), ('16', '16', '0', '0')])
        self.assertIn('{ 0, ', header.split('actor_draws[] = {', 1)[1])
        with self.assertRaises(ValueError):
            export_actor_header(BOTTLES, HILL, HILL)

    def test_runtime_keeps_player_bridge_camera_and_audio(self):
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        makefile = (ROOT / 'platform/3ds/Makefile').read_text()
        self.assertIn('movementActorMatrix(&player.motion.actor, rows)', main)
        self.assertIn('cameraRuntimeSetLearnedAbilities(&rareCamera, BANJO_LEARNED_ABILITIES)', main)
        self.assertIn('playerCrouchSetAbilities(BANJO_LEARNED_ABILITIES)', main)
        self.assertIn('{0.0f, 1800.0f, 0.0f, 0.0f}', main)
        self.assertLess(main.index('sfxProbe3dsFrame(playerCrouchSlideSfx());'),
                        main.index('footstep3dsSubmit(foot_plays, foot_play_count);'))
        self.assertIn('actor_pose_placement(rows, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z,\n'
                      '        ACTOR_PLACE_YAW, ACTOR_PLACE_SCALE);', main)
        self.assertLess(main.index('sceneDrawActorRange(ACTOR_HILL_FIRST_DRAW'),
                        main.index('sceneDrawActorRange(ACTOR_BOTTLES_FIRST_DRAW'))
        render = main[main.index('static void sceneRender(void)'):]
        self.assertLess(render.index('movementActorMatrix(&player.motion.actor, rows)'),
                        render.index('sceneDrawPlacedActors('))
        self.assertLess(render.index('sceneDrawPlacedActors('),
                        render.index('if (BANJO_XLU_DRAW_COUNT > 0)'))
        self.assertIn('ndspChnReset(1);', (ROOT / 'platform/3ds/source/footstep_3ds.c').read_text())
        self.assertIn('ndspChnReset(2);', (ROOT / 'platform/3ds/source/footstep_3ds.c').read_text())
        self.assertIn('ndspChnReset(0);', (ROOT / 'platform/3ds/source/sfx_probe_3ds.c').read_text())
        self.assertIn('#define BRIDGE_REQUIRED_ABILITIES UINT32_C(0x9db1)',
                      (ROOT / 'tools/banjo3ds/bridge_state/bridge.h').read_text())
        self.assertIn('BANJO3DS_DEBUG_CAMERA ?= 0', makefile)
        self.assertIn('BANJO3DS_LEARNED_ABILITIES ?= 0x9DB1', makefile)
        geo = main.index('static void sceneDrawGeo(')
        self.assertIn('sceneDrawRange(node->first_draw, node->draw_count, render_state);',
                      main[geo:main.index('\n#endif', geo)])

    def test_every_idle_frame_stays_bounded(self):
        """A posed coordinate outside the character is the huge-polygon failure mode."""
        last = parse_packet(self.bottles.packet).anim_last
        corners = parse_packet(self.bottles.packet).corners
        self.assertEqual(last, 267)
        for frame in range(last + 1):
            xyz = reference_evaluate(self.bottles.packet, frame / last)[2]
            for point in xyz:
                self.assertTrue(all(math.isfinite(value) for value in point))
                self.assertTrue(all(-200.0 <= value <= 400.0 for value in point))
            for index in range(0, len(corners), 3):
                tri = [xyz[corners[index + corner]] for corner in range(3)]
                for start, end in ((0, 1), (1, 2), (2, 0)):
                    self.assertLess(math.dist(tri[start], tri[end]), 100.0)
        hill = reference_evaluate(self.hill.packet, 0.0)[2]
        for point in hill:
            self.assertTrue(all(math.isfinite(value) and -200.0 <= value <= 200.0 for value in point))

    def test_actor_draws_bind_a_texture_or_skip_sampling(self):
        """Untextured draws must use the combiner that does not sample TEXTURE0."""
        shaded = (6, 3, 5, 3, 7, 7, 7, 4, 0, 15, 4, 7, 0, 7, 5, 7)
        handled = {
            shaded,
            (1, 3, 5, 3, 1, 7, 4, 7, 0, 15, 4, 7, 0, 7, 5, 7),
            (2, 1, 13, 1, 1, 7, 4, 7, 0, 15, 4, 7, 0, 7, 5, 7),
            (15, 15, 31, 1, 1, 7, 4, 7, 15, 15, 31, 0, 0, 7, 5, 7),
        }
        untextured = 0
        for mesh, base in ((self.hill, 0), (self.bottles, len(self.hill.corners))):
            total = len(self.hill.corners) + len(self.bottles.corners)
            for first, count, material, _mode, combine, _cull in build_draw_batches(mesh.render.triangles):
                self.assertEqual(count % 3, 0)
                self.assertGreaterEqual(base + first, 0)
                self.assertLessEqual(base + first + count, total)
                self.assertIn(combine, handled)
                if material < 0:
                    untextured += count // 3
                    self.assertEqual(combine, shaded)
        self.assertEqual(untextured, 14)

    def test_actor_texture_levels_match_upload_sizes(self):
        for mesh in (self.hill, self.bottles):
            for texture in mesh.render.textures:
                encoded = encode_3ds_rgba8_pixels(texture.width, texture.height, texture.pixels)
                self.assertEqual(len(encoded), texture.width * texture.height * 4)
                for level, pixels in enumerate(texture.mipmaps or [], start=1):
                    width, height = texture.width >> level, texture.height >> level
                    mip = encode_3ds_rgba8_pixels(width, height, pixels)
                    self.assertEqual(len(mip), width * height * 4)
                    self.assertGreaterEqual(width, 8)
                    self.assertGreaterEqual(height, 8)

    def test_exported_uvs_stay_in_a_repeat_range(self):
        for mesh in (self.hill, self.bottles):
            for triangle in mesh.render.triangles:
                if triangle.material_index is None:
                    continue
                material = mesh.render.materials[triangle.material_index]
                load = mesh.render.texture_loads[material.texture_load_index]
                texture = find_texture_for_load(mesh.render, load)
                for index in (triangle.v0, triangle.v1, triangle.v2):
                    vertex = mesh.render.vertices[index]
                    u = n64_texture_coordinate_to_uv(vertex.s, load.scale_s, texture.width)
                    v = 1.0 - n64_texture_coordinate_to_uv(vertex.t, load.scale_t, texture.height)
                    self.assertTrue(math.isfinite(u) and math.isfinite(v))
                    self.assertLess(abs(u), 8.0)
                    self.assertLess(abs(v), 8.0)

    def test_stage_clock_cannot_draw_before_four_seconds(self):
        """The previous image's first actor draw waits for 4.0s of osGetTime."""
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        body = main[main.index('static int actorDiagStage'):main.index('static u32 actorDiagClear')]
        self.assertLess(body.index('if (seconds < 4.0f)\n        return 0;'),
                        body.index('if (seconds < 8.0f)\n        return 1;'))
        self.assertLess(body.index('if (seconds < 8.0f)\n        return 1;'),
                        body.index('if (seconds < 12.0f)\n        return 2;'))
        self.assertLess(main.index('actor_diag_start_ms = osGetTime();'),
                        main.index('while (aptMainLoop())'))
        self.assertLess(main.index('while (aptMainLoop())'),
                        main.index('actor_diag_stage = actorDiagStage((float)(now - actor_diag_start_ms) / 1000.0f);'))
        self.assertLess(main.index('if (actor_diag_stage <= 0)'),
                        main.index('actor_pose_placement(rows, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z,\n'
                                   '        ACTOR_PLACE_YAW, ACTOR_PLACE_SCALE);'))

    def test_isolation_build_disables_actor_runtime(self):
        """FIX2 control: isolation 1, texture upload 0, and vertex init 0 run no actor code."""
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        makefile = (ROOT / 'platform/3ds/Makefile').read_text()
        disabled = active_source(main, isolation=1, texture_upload=0, vertex_init=0)
        enabled = active_source(main, isolation=0, texture_upload=0, vertex_init=0)
        forbidden = (
            'uploadActorTextures(',
            'initActorVertexBuffer(',
            'linearAlloc(sizeof(actor_vertices))',
            'sceneDrawPlacedActors(',
            'sceneDrawActorRange(',
            'actor_pose_evaluate(',
            'actor_pose_scatter(',
            'actor_pose_advance(',
            'actor_pose_placement(',
            'actorDiagClear(',
            'C3D_TexDelete(&actor_textures',
            'linearFree(actor_vbo)',
            'C3D_TexBind(0, &actor_textures',
            'actor_diag_start_ms',
        )
        for call in forbidden:
            self.assertNotIn(call, disabled, call)
            self.assertIn(call, enabled, call)
        self.assertIn('C3D_RenderTargetClear(target, C3D_CLEAR_ALL, CLEAR_COLOR, 0);', disabled)
        self.assertNotIn('actorDiagClear', disabled)
        self.assertIn('actor-isolation: runtime disabled', disabled)
        self.assertNotIn('actor-isolation: texture upload only', disabled)
        self.assertNotIn('actor-isolation: vertex buffer init', disabled)
        self.assertIn('actor_vertices', disabled)
        self.assertIn('movementActorMatrix(&player.motion.actor, rows)', disabled)
        self.assertIn('bridge_render_y(', disabled)
        self.assertIn('sfxProbe3dsFrame(playerCrouchSlideSfx());', disabled)
        self.assertIn('footstep3dsSubmit(foot_plays, foot_play_count);', disabled)
        self.assertIn('BANJO3DS_ACTOR_ISOLATION ?= 1', makefile)
        self.assertIn('-DBANJO3DS_ACTOR_ISOLATION=$(BANJO3DS_ACTOR_ISOLATION)', makefile)
        self.assertIn(
            'actor-isolation: ALL actor runtime disabled '
            '(BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=0)', makefile)
        self.assertIn("grep -q ' actor_isolation_banner$$'", makefile)
        for symbol in ('uploadActorTextures', 'sceneDrawPlacedActors', 'actor_pose_evaluate',
                       'actor_pose_scatter', 'actor_pose_advance', 'actor_pose_placement'):
            self.assertIn(symbol, makefile)

    def test_texture_upload_cannot_draw_or_animate(self):
        """FIX3 control: texture upload with vertex init off cannot allocate or draw."""
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        makefile = (ROOT / 'platform/3ds/Makefile').read_text()
        uploaded = active_source(main, isolation=1, texture_upload=1, vertex_init=0)
        self.assertIn('uploadActorTextures();', uploaded)
        self.assertIn('C3D_TexDelete(&actor_textures', uploaded)
        self.assertIn('actor-isolation: texture upload only', uploaded)
        self.assertNotIn('actor-isolation: runtime disabled', uploaded)
        self.assertNotIn('actor-isolation: vertex buffer init', uploaded)
        self.assertNotIn('initActorVertexBuffer(', uploaded)
        self.assertIn('C3D_RenderTargetClear(target, C3D_CLEAR_ALL, CLEAR_COLOR, 0);', uploaded)
        for call in (
            'linearAlloc(sizeof(actor_vertices))',
            'sceneDrawPlacedActors(',
            'sceneDrawActorRange(',
            'actor_pose_evaluate(',
            'actor_pose_scatter(',
            'actor_pose_advance(',
            'actor_pose_placement(',
            'actorDiagClear(',
            'linearFree(actor_vbo)',
            'C3D_TexBind(0, &actor_textures',
            'actor_vbo',
            'actor_diag_start_ms',
        ):
            self.assertNotIn(call, uploaded, call)
        self.assertIn('movementActorMatrix(&player.motion.actor, rows)', uploaded)
        self.assertIn('bridge_render_y(', uploaded)
        self.assertIn('sfxProbe3dsFrame(playerCrouchSlideSfx());', uploaded)
        self.assertIn('footstep3dsSubmit(foot_plays, foot_play_count);', uploaded)
        self.assertIn('BANJO3DS_ACTOR_TEXTURE_UPLOAD ?= 1', makefile)
        self.assertIn('-DBANJO3DS_ACTOR_TEXTURE_UPLOAD=$(BANJO3DS_ACTOR_TEXTURE_UPLOAD)', makefile)
        self.assertIn(
            'actor-isolation: texture upload only '
            '(BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=1)', makefile)
        self.assertIn("grep -q ' uploadActorTextures$$'", makefile)
        self.assertIn("grep -E ' (actor_vbo|initActorVertexBuffer)$$'", makefile)

    def test_vertex_init_allocates_without_drawing(self):
        """FIX4 copies the actor vertices once and leaves draws, binding, and poses out."""
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        makefile = (ROOT / 'platform/3ds/Makefile').read_text()
        diagnostic = active_source(main, isolation=1, texture_upload=1, vertex_init=1)
        self.assertIn('uploadActorTextures();', diagnostic)
        self.assertIn('initActorVertexBuffer();', diagnostic)
        self.assertIn('C3D_TexDelete(&actor_textures', diagnostic)
        self.assertIn('linearFree(actor_vbo)', diagnostic)
        self.assertIn('actor-isolation: vertex buffer init', diagnostic)
        self.assertNotIn('actor-isolation: texture upload only', diagnostic)
        self.assertNotIn('actor-isolation: runtime disabled', diagnostic)
        self.assertIn('C3D_RenderTargetClear(target, C3D_CLEAR_ALL, CLEAR_COLOR, 0);', diagnostic)
        for call in (
            'sceneDrawPlacedActors(',
            'sceneDrawActorRange(',
            'actor_pose_evaluate(',
            'actor_pose_scatter(',
            'actor_pose_advance(',
            'actor_pose_placement(',
            'actorDiagClear(',
            'C3D_TexBind(0, &actor_textures',
            'BufInfo_Add(bufInfo, actor_vbo',
            'C3D_SetBufInfo',
            'actor_diag_start_ms',
            'actor_bottles_phase',
        ):
            self.assertNotIn(call, diagnostic, call)
        scene_init = diagnostic[diagnostic.index('static void sceneInit'):diagnostic.index('typedef struct')]
        loop = diagnostic[diagnostic.index('while (aptMainLoop())'):diagnostic.index('footstep3dsExit();')]
        self.assertIn('initActorVertexBuffer();', scene_init)
        self.assertIn('uploadActorTextures();', scene_init)
        self.assertNotIn('actor_vbo', scene_init)
        self.assertNotIn('actor_vbo', loop)
        self.assertNotIn('initActorVertexBuffer', loop)
        self.assertNotIn('memcpy(actor_vbo', loop)
        self.assertNotIn('actor_pose_', loop)
        self.assertEqual(diagnostic.count('BufInfo_Add('), 1)
        self.assertIn('BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);', diagnostic)
        self.assertIn('movementActorMatrix(&player.motion.actor, rows)', diagnostic)
        self.assertIn('bridge_render_y(', diagnostic)
        self.assertIn('sfxProbe3dsFrame(playerCrouchSlideSfx());', diagnostic)
        self.assertIn('footstep3dsSubmit(foot_plays, foot_play_count);', diagnostic)
        self.assertIn('BANJO3DS_ACTOR_VERTEX_INIT ?= 1', makefile)
        self.assertIn('-DBANJO3DS_ACTOR_VERTEX_INIT=$(BANJO3DS_ACTOR_VERTEX_INIT)', makefile)
        self.assertIn(
            'actor-isolation: vertex buffer init '
            '(BANJO3DS_ACTOR_ISOLATION=1 BANJO3DS_ACTOR_TEXTURE_UPLOAD=1 '
            'BANJO3DS_ACTOR_VERTEX_INIT=1)', makefile)
        self.assertIn("grep -q ' actor_vbo$$'", makefile)
        self.assertIn("grep -q ' initActorVertexBuffer$$'", makefile)
        self.assertIn(
            'actor-isolation: vertex buffer init linked, draw and pose symbols absent',
            makefile)
        for symbol in ('sceneDrawPlacedActors', 'sceneDrawActorRange', 'actorDiagStage',
                       'actorDiagClear', 'actor_pose_evaluate', 'actor_pose_scatter',
                       'actor_pose_advance', 'actor_pose_placement'):
            self.assertIn(symbol, makefile)

    def test_vertex_init_buffer_cannot_overlap_world(self):
        """The actor copy is a separate allocation of exactly the exported vertex array."""
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        diagnostic = active_source(main, isolation=1, texture_upload=1, vertex_init=1)
        stride = 24
        hill = len(self.hill.corners)
        bottles = len(self.bottles.corners)
        count = hill + bottles
        payload = count * stride
        world = 12600 * stride
        self.assertEqual((hill, bottles, count, payload), (168, 1851, 2019, 48456))
        self.assertEqual(payload % 128, 72)
        self.assertNotEqual(payload, world)
        self.assertIn(
            '_Static_assert(sizeof(Banjo3DSVertex) == 24, "vertex stride stays 24 bytes");',
            main)
        self.assertIn(
            'sizeof(actor_vertices) == (size_t)ACTOR_VERTEX_COUNT * sizeof(Banjo3DSVertex)',
            main)
        self.assertIn(
            'sizeof(banjo_vertices) == (size_t)BANJO_VERTEX_COUNT * sizeof(Banjo3DSVertex)',
            main)
        self.assertEqual(diagnostic.count('linearAlloc(sizeof(actor_vertices))'), 1)
        self.assertEqual(diagnostic.count('memcpy(actor_vbo, actor_vertices, sizeof(actor_vertices))'), 1)
        self.assertEqual(diagnostic.count('linearAlloc(sizeof(banjo_vertices))'), 1)
        self.assertEqual(diagnostic.count('memcpy(vbo_data, banjo_vertices, sizeof(banjo_vertices))'), 1)
        self.assertNotIn('memcpy(vbo_data, actor_vertices', diagnostic)
        self.assertNotIn('memcpy(actor_vbo, banjo_vertices', diagnostic)
        copied = diagnostic[diagnostic.index('static void initActorVertexBuffer'):
                            diagnostic.index('static void uploadActorTextures')]
        self.assertIn('actor_vbo = linearAlloc(sizeof(actor_vertices));', copied)
        self.assertIn('memcpy(actor_vbo, actor_vertices, sizeof(actor_vertices));', copied)
        exit_body = diagnostic[diagnostic.index('static void sceneExit'):diagnostic.index('int main')]
        self.assertEqual(exit_body.count('linearFree(actor_vbo)'), 1)
        self.assertEqual(exit_body.count('linearFree(vbo_data)'), 1)
        loop = diagnostic[diagnostic.index('while (aptMainLoop())'):diagnostic.index('footstep3dsExit();')]
        self.assertIn(
            'playerRuntimeWriteVertices(&player, banjo_runtime_pose,\n'
            '            vbo_data, BANJO_VERTEX_COUNT,', loop)
        self.assertIn('bridge_render_y(&rareCamera.xlu, vbo_data,', loop)
        self.assertNotIn('actor_vbo', loop)

    def test_actor_texture_allocations_match_citro3d(self):
        """Uploaded RGBA8 levels use citro3d's size, order, and 128-byte alignment."""
        def level_bytes(width, height):
            return 32 * width * height // 8

        def total_bytes(width, height, max_level):
            size = level_bytes(width, height)
            return (size - (size >> (2 * (max_level + 1)))) * 4 // 3

        seen = []
        total = 0
        for mesh in (self.hill, self.bottles):
            for texture in mesh.render.textures:
                levels = len(texture.mipmaps or [])
                for value in (texture.width, texture.height):
                    self.assertGreaterEqual(value, 8)
                    self.assertLessEqual(value, 1024)
                    self.assertEqual(value & (value - 1), 0)
                legal_levels = min(texture.width, texture.height).bit_length() - 4
                self.assertLessEqual(levels, legal_levels)
                size = level_bytes(texture.width, texture.height)
                encoded = encode_3ds_rgba8_pixels(
                    texture.width, texture.height, texture.pixels)
                self.assertEqual(len(encoded), size)
                consumed = size
                for level, pixels in enumerate(texture.mipmaps or [], start=1):
                    width, height = texture.width >> level, texture.height >> level
                    mip_size = size >> (2 * level)
                    mip = encode_3ds_rgba8_pixels(width, height, pixels)
                    self.assertEqual(len(mip), mip_size)
                    consumed += mip_size
                    self.assertGreaterEqual(width, 8)
                    self.assertGreaterEqual(height, 8)
                allocated = total_bytes(texture.width, texture.height, levels)
                self.assertEqual(consumed, allocated)
                self.assertEqual(allocated % 128, 0)
                total += allocated
                seen.append((texture.width, texture.height, levels))
        self.assertEqual(seen, [
            (64, 64, 0), (32, 32, 2), (16, 16, 0), (16, 16, 0), (16, 16, 0)])
        self.assertEqual(total, 24832)
