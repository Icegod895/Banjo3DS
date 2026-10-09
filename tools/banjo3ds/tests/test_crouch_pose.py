"""B3P3 v5 crouch clips. Production sampling versus the original-C channel oracle."""
import ctypes as C
import hashlib
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from crouch_pose_reference import CLIPS, CrouchAnimation, reference
from idle_animation_reference import F, ROOT
from test_walk_pose import Pose
from tools.banjo3ds.pose_binding import export_crouch_packet, export_gait_packet, export_jump_packet, export_pose_packet, export_transition_packet

NAMES = ('0001', '010C', '0116')
INDEX = {'0003': 0, '006F': 1, '0002': 2, '000C': 3, '0008': 4, '0001': 5, '010C': 6, '0116': 7}
PHASES = (0., 2 ** -20, .25, .5, .75, 1 - 2 ** -20, 1 - 2 ** -24, 1.)
V4_SIZE = 28022
V5_SIZE = 36994


def packed(rows, width):
    return b''.join(struct.pack('<' + str(width) + 'f', *row) for row in rows)


def asset(name):
    return (ROOT / f'assets/anim/{name}.anim.bin').read_bytes()


def paths():
    model = ROOT / 'assets/model/034D.model.bin'
    anim = [ROOT / f'assets/anim/{name}.anim.bin' for name in ('0003', '006F', '0002', '000C', '0008', *NAMES)]
    return (model, *anim)


class CrouchPoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='banjo-crouch-pose-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs = []
        for opt in ('-O0', '-O2'):
            out = Path(cls.tmp.name) / (opt + '.so')
            result = subprocess.run(
                ['cc', '-std=c99', opt, '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                 '-ffp-contract=off', '-fno-fast-math', '-fexcess-precision=standard',
                 str(ROOT / 'tools/banjo3ds/pose/pose.c'), '-lm', '-o', str(out)],
                capture_output=True, text=True)
            if result.returncode or result.stderr:
                raise RuntimeError(result.stderr)
            lib = C.CDLL(str(out))
            lib.banjo_pose_sample.argtypes = [C.c_char_p, C.c_size_t, C.c_int, F, C.POINTER(F * 10)]
            lib.banjo_pose_sample.restype = C.c_bool
            lib.banjo_pose_apply.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(Pose)]
            lib.banjo_pose_apply.restype = C.c_bool
            lib.banjo_pose_evaluate.argtypes = [C.c_char_p, C.c_size_t, F, C.POINTER(Pose)]
            lib.banjo_pose_evaluate.restype = C.c_bool
            cls.libs.append(lib)
        model, walk, idle, creep, run, jump, enter, turn, noinput = paths()
        cls.v1 = export_pose_packet(model, walk)
        cls.v2 = export_transition_packet(model, walk, idle)
        cls.v3 = export_gait_packet(model, walk, idle, creep, run)
        cls.v4 = export_jump_packet(model, walk, idle, creep, run, jump)
        cls.v5 = export_crouch_packet(model, walk, idle, creep, run, jump, enter, turn, noinput)
        cls.animations = {name: CrouchAnimation(name) for name in NAMES}

    def sample(self, lib, packet, clip, phase):
        pose = Pose()
        ok = lib.banjo_pose_sample(packet, len(packet), clip, phase, pose.bones)
        return ok, pose

    def test_asset_metadata_matches_the_evaluator_subset(self):
        model = (ROOT / 'assets/model/034D.model.bin').read_bytes()
        offset = struct.unpack_from('>I', model, 24)[0]
        factor, count = struct.unpack_from('>fh', model, offset)
        self.assertEqual((factor, count), (10., 60))
        skeleton = {struct.unpack_from('>3fhh', model, offset + 8 + 16 * i)[3] for i in range(count)}
        expected = {
            '0001': (2176, 28, 58, 484, 26, 400, (0, 1, 2, 3, 4, 5, 7, 8)),
            '010C': (2576, 48, 53, 589, 414, 122, (0, 1, 2, 6, 7, 8)),
            '0116': (4220, 95, 57, 996, 820, 119, (0, 1, 2, 7, 8)),
        }
        for name, (size, last, channels, keys, linear, spline, chan_ids) in expected.items():
            animation = self.animations[name]
            data = asset(name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), CLIPS[name][0])
            self.assertEqual(len(data), size)
            self.assertEqual((animation.first, animation.last, len(animation.channels)), (0, last, channels))
            self.assertEqual(sum(len(item) for _, _, item in animation.channels), keys)
            spans = [bool(a[0] & 0x4000 or b[0] & 0x8000)
                     for _, _, rows in animation.channels for a, b in zip(rows, rows[1:])]
            self.assertEqual((spans.count(False), spans.count(True)), (linear, spline))
            seen = set()
            for bone, channel, rows in animation.channels:
                self.assertIn(bone, skeleton)
                self.assertLess(bone, 109)
                self.assertLessEqual(channel, 8)
                self.assertNotIn((bone, channel), seen)
                seen.add((bone, channel))
                frames = [word & 0x3fff for word, _ in rows]
                self.assertEqual(frames, sorted(set(frames)))
                self.assertLessEqual(frames[-1], last)
            self.assertEqual(tuple(sorted({channel for _, channel, _ in animation.channels})), chan_ids)
            self.assertNotIn(0, {bone for bone, _, _ in animation.channels})

    def test_v5_appends_without_moving_v4_bytes(self):
        self.assertEqual(len(self.v4), V4_SIZE)
        self.assertEqual(len(self.v5), V5_SIZE)
        self.assertEqual(self.v5[:4], b'B3P3')
        self.assertEqual(struct.unpack_from('>I', self.v5, 4)[0], 5)
        self.assertEqual(self.v5[8:V4_SIZE], self.v4[8:])
        self.assertEqual(struct.unpack_from('>5I', self.v5, 8), (60, 723, 2085, 1132, 12316))
        self.assertEqual(struct.unpack_from('>HH', self.v5, 28), (888, 948))
        blobs = [asset(name) for name in NAMES]
        self.assertEqual(self.v5[V4_SIZE:], b''.join(blobs))
        offset = V4_SIZE
        for name, blob in zip(NAMES, blobs):
            self.assertEqual(self.v5[offset:offset + len(blob)], blob)
            offset += len(blob)
        self.assertEqual(offset, V5_SIZE)
        with self.assertRaises(ValueError):
            model, walk, idle, creep, run, jump, enter, turn, noinput = paths()
            export_crouch_packet(model, walk, idle, creep, run, jump, walk, turn, noinput)

    def test_legacy_packets_and_walk_evaluation_stay_unchanged(self):
        packets = (self.v1, self.v2, self.v3, self.v4, self.v5)
        self.assertEqual(tuple(map(len, packets)), (12082, 24398, 26234, V4_SIZE, V5_SIZE))
        required = (1, 2, 3, 3, 4, 5, 5, 5)
        for lib in self.libs:
            for packet in packets:
                version = struct.unpack_from('>I', packet, 4)[0]
                for clip, need in enumerate(required):
                    ok, _ = self.sample(lib, packet, clip, 0)
                    self.assertEqual(ok, version >= need, (version, clip))
            for phase in (0., .5, 1.):
                walk = []
                for packet in (self.v4, self.v5):
                    pose = Pose()
                    self.assertTrue(lib.banjo_pose_evaluate(packet, len(packet), phase, C.byref(pose)))
                    walk.append(bytes(pose))
                self.assertEqual(walk[0], walk[1])
                for clip in range(5):
                    left, right = Pose(), Pose()
                    self.assertTrue(lib.banjo_pose_sample(self.v4, len(self.v4), clip, phase, left.bones))
                    self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), clip, phase, right.bones))
                    self.assertTrue(lib.banjo_pose_apply(self.v4, len(self.v4), C.byref(left)))
                    self.assertTrue(lib.banjo_pose_apply(self.v5, len(self.v5), C.byref(right)))
                    self.assertEqual(bytes(left), bytes(right))
            grown = self.v4 + asset('0001')
            pose = Pose()
            self.assertFalse(lib.banjo_pose_evaluate(grown, len(grown), 0, C.byref(pose)))
            self.assertFalse(lib.banjo_pose_sample(self.v5[:-1], len(self.v5) - 1, 5, 0, pose.bones))
            for phase in (-1., 1.01, float('nan'), float('inf')):
                self.assertFalse(lib.banjo_pose_sample(self.v5, len(self.v5), 5, phase, pose.bones))
            self.assertFalse(lib.banjo_pose_sample(self.v5, len(self.v5), 8, 0, pose.bones))

    def phases_for(self, name):
        animation = self.animations[name]
        phases = {F(phase).value for phase in PHASES}
        frames = sorted({word & 0x3fff for _, _, rows in animation.channels for word, _ in rows})
        phases.update(F(frame / animation.last).value for frame in frames)
        linear = spline = None
        for _, _, rows in animation.channels:
            for left, right in zip(rows, rows[1:]):
                midpoint = F(((left[0] & 0x3fff) + (right[0] & 0x3fff)) / (2 * animation.last)).value
                if left[0] & 0x4000 or right[0] & 0x8000:
                    spline = spline if spline is not None else midpoint
                else:
                    linear = linear if linear is not None else midpoint
        self.assertIsNotNone(linear)
        self.assertIsNotNone(spline)
        phases.update((linear, spline))
        return sorted(phases)

    def test_samples_match_original_channels_at_O0_and_O2(self):
        endpoints = []
        at = {0.: {}, .5: {}}
        for name in NAMES:
            animation = self.animations[name]
            seen = []
            for phase in self.phases_for(name):
                bones, _ = animation.transforms(phase)
                expected = packed(bones, 10)
                got = []
                for lib in self.libs:
                    ok, pose = self.sample(lib, self.v5, INDEX[name], phase)
                    self.assertTrue(ok)
                    self.assertEqual(packed(pose.bones, 10), expected)
                    self.assertEqual(tuple(pose.bones[0]), (0., 0., 0., 1., 1., 1., 1., 0., 0., 0.))
                    got.append(bytes(pose.bones))
                self.assertEqual(got[0], got[1])
                seen.append(got[0])
                if phase in at:
                    at[phase][name] = got[0]
            # Phase 1 stays on the last frame. A closed clip can still match
            # phase 0; an interior sample has to leave that pose.
            self.assertTrue(any(item != seen[0] for item in seen[1:-1]))
            endpoints.append(seen[0] == seen[-1])
        # 0001 and 0116 stay open at phase 1. 010C's keyed endpoint matches phase 0.
        self.assertEqual(endpoints, [False, True, False])
        # 010C and 0116 key every channel that one clip has and the other
        # lacks to 0 on frame 0, so both start on the same crouched pose.
        # 0001 begins standing. Phase 0.5 selects three different poses.
        self.assertEqual(at[0.]['010C'], at[0.]['0116'])
        self.assertNotEqual(at[0.]['0001'], at[0.]['010C'])
        self.assertEqual(len(set(at[.5].values())), 3)

    def test_geometry_matches_independent_binding_at_boundaries(self):
        for name in NAMES:
            for phase in (0., .5, 1.):
                animation, bones, pose = reference(name, phase)
                matrices = animation.matrices(bones)
                self.assertEqual((len(pose.calls), len(pose.triangles), len(pose.loads)), (49, 695, 723))
                for lib in self.libs:
                    out = Pose()
                    self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), INDEX[name], phase, out.bones))
                    self.assertTrue(lib.banjo_pose_apply(self.v5, len(self.v5), C.byref(out)))
                    self.assertEqual(packed(out.bones, 10), packed(bones, 10))
                    for i in range(60):
                        self.assertEqual(packed(out.matrices[i], 4), packed(zip(*matrices[i]), 4))
                    self.assertEqual(packed(out.xyz, 3), packed((entry['xyz'] for entry in pose.loads), 3))

    def test_crouch_bytes_do_not_change_an_earlier_clip(self):
        tampered = bytearray(self.v5)
        tampered[V4_SIZE + 2] ^= 0x01
        tampered = bytes(tampered)
        for lib in self.libs:
            clean, dirty = Pose(), Pose()
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), 0, .5, clean.bones))
            self.assertTrue(lib.banjo_pose_sample(tampered, len(tampered), 0, .5, dirty.bones))
            self.assertEqual(bytes(clean.bones), bytes(dirty.bones))
            pose = Pose()
            self.assertFalse(lib.banjo_pose_sample(tampered, len(tampered), 5, 0, pose.bones))
            self.assertTrue(lib.banjo_pose_sample(tampered, len(tampered), 6, 0, pose.bones))
