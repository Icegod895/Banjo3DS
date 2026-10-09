"""Native crouch integration: host machine, locked coast, v5 packet, input priority."""
import ctypes as C
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from crouch_reference import View
from idle_animation_reference import ROOT
from test_gait_production import Bones
from test_horizontal import State as Horizontal
from test_jump import floor
from test_jump_runtime import Player
from tools.banjo3ds.pose_binding import export_jump_packet, write_crouch_clips_header

F = C.c_float
DT = 1.0 / 30.0
Z, A, B = 32, 64, 128
C_LEFT, C_UP = 2, 16
MODEL_HASH = '4674427ddfadbbeb36afd49a337291d59fbce2751775a177381720ba36788a0c'
SOURCES = (
    'tools/banjo3ds/pose/pose.c',
    'tools/banjo3ds/gait/gait.c',
    'tools/banjo3ds/gait/gait_motion.c',
    'tools/banjo3ds/horizontal/horizontal.c',
    'tools/banjo3ds/ground/ground.c',
    'tools/banjo3ds/jump/jump.c',
    'tools/banjo3ds/jump/jump_animation.c',
    'tools/banjo3ds/camera_first_person/first_person.c',
    'tools/banjo3ds/crouch/crouch.c',
    'platform/3ds/source/movement.c',
    'platform/3ds/source/player_runtime.c',
    'platform/3ds/source/player_ground.c',
    'platform/3ds/source/player_crouch.c',
    'tools/banjo3ds/tests/crouch_runtime_drive.c',
)
INCLUDES = (
    'platform/3ds/source',
    'tools/banjo3ds',
    'tools/banjo3ds/pose',
    'tools/banjo3ds/gait',
    'tools/banjo3ds/jump',
    'tools/banjo3ds/horizontal',
    'tools/banjo3ds/ground',
    'tools/banjo3ds/body',
    'tools/banjo3ds/world_query',
    'tools/banjo3ds/camera_first_person',
)


def bind(lib):
    lib.playerCrouchInstall.argtypes = []
    lib.playerCrouchSetAbilities.argtypes = [C.c_uint32]
    lib.playerCrouchReset.argtypes = [F]
    lib.playerCrouchFrame.argtypes = [C.POINTER(Player), C.c_uint32, C.c_int]
    lib.playerCrouchActive.restype = C.c_bool
    lib.playerCrouchSlideSfx.restype = C.c_int
    lib.playerCrouchRequested.restype = C.c_int
    lib.playerCrouchState.restype = C.c_int
    lib.playerCrouchCopy.argtypes = [C.POINTER(View)]
    lib.playerCrouchActivate.argtypes = [C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t,
                                         C.c_char_p, C.c_size_t, C.c_char_p, C.c_size_t,
                                         C.c_char_p, C.c_size_t]
    lib.playerCrouchActivate.restype = C.c_size_t
    lib.playerGroundSetCrouchHook.argtypes = [C.c_void_p]
    lib.crouch_host_reset.argtypes = [C.POINTER(Player)]
    lib.crouch_host_set_floor.argtypes = [F]
    lib.crouch_host_step.argtypes = [C.POINTER(Player), F, F, F, C.c_int,
                                     C.c_void_p, C.c_void_p, C.c_size_t]
    lib.crouch_host_step.restype = C.c_uint
    lib.playerRuntimeAnimate.argtypes = [C.POINTER(Player), C.c_char_p, C.c_size_t, F]
    lib.playerRuntimeAnimate.restype = C.c_bool
    lib.banjo_pose_sample.argtypes = [C.c_char_p, C.c_size_t, C.c_int, F, C.POINTER(F * 10)]
    lib.banjo_pose_sample.restype = C.c_bool
    lib.banjo_pose_blend.argtypes = [C.POINTER(F * 10), C.POINTER(F * 10), C.POINTER(F * 10), F]
    lib.banjo_gait_update.argtypes = [C.c_void_p, C.c_char_p, C.c_size_t, C.c_bool, F, F]
    lib.banjo_gait_update.restype = C.c_bool


class CrouchRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='banjo-crouch-runtime-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs = []
        for opt in ('-O0', '-O2'):
            output = Path(cls.tmp.name) / (opt + '.so')
            result = subprocess.run(
                ['cc', '-std=c99', opt, '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                 '-ffp-contract=off', '-fno-fast-math', '-fexcess-precision=standard',
                 *['-I' + str(ROOT / p) for p in INCLUDES],
                 *[str(ROOT / p) for p in SOURCES], '-lm', '-o', str(output)],
                capture_output=True, text=True)
            if result.returncode or result.stderr:
                raise RuntimeError(result.stderr or result.stdout)
            lib = C.CDLL(str(output))
            bind(lib)
            lib.playerCrouchInstall()
            cls.libs.append(lib)
        anims = {name: ROOT / f'assets/anim/{name}.anim.bin' for name in
                 ('0003', '006F', '0002', '000C', '0008', '0001', '010C', '0116')}
        cls.v4 = export_jump_packet(
            ROOT / 'assets/model/034D.model.bin',
            *(anims[name] for name in ('0003', '006F', '0002', '000C', '0008')))
        cls.clips = [anims[name].read_bytes() for name in ('0001', '010C', '0116')]
        cls.floor_v, cls.floor_t = floor(y=1800)
        cls.v5_size, cls.v5 = cls.assemble(cls.libs[0])

    @classmethod
    def assemble(cls, lib, prefix=None, clips=None):
        prefix = cls.v4 if prefix is None else prefix
        clips = cls.clips if clips is None else clips
        out = C.create_string_buffer(36994)
        size = lib.playerCrouchActivate(
            out, len(out), prefix, len(prefix),
            clips[0], len(clips[0]), clips[1], len(clips[1]), clips[2], len(clips[2]))
        return size, out.raw

    def fresh(self, lib, gait=0, yaw=0.0):
        player = Player()
        player.motion.actor.y = 1800
        player.motion.actor.yaw = yaw
        player.motion.grounded = True
        player.locomotion.gait = gait
        player.horizontal.ideal = yaw
        player.horizontal.visible = yaw
        player.horizontal.heading = yaw
        lib.playerCrouchSetAbilities(0)
        lib.playerCrouchReset(yaw)
        lib.crouch_host_reset(C.byref(player))
        return player

    def step(self, lib, player, held, magnitude=0.0, stick=0.0, dt=DT, jump=0):
        lib.playerCrouchFrame(C.byref(player), held, 0)
        return lib.crouch_host_step(
            C.byref(player), magnitude, stick, dt, jump,
            self.floor_v, self.floor_t, len(self.floor_t))

    def view(self, lib):
        out = View()
        lib.playerCrouchCopy(C.byref(out))
        return out

    def test_packet_v5_preserves_v4_and_frozen_model_header(self):
        for lib in self.libs:
            size, packet = self.assemble(lib)
            self.assertEqual(size, 36994)
            self.assertEqual(packet[:4], b'B3P3')
            self.assertEqual(packet[4:8], b'\x00\x00\x00\x05')
            self.assertEqual(packet[8:28022], self.v4[8:])
            self.assertEqual(packet[28022:], b''.join(self.clips))
            self.assertEqual(lib.playerCrouchActivate(
                C.create_string_buffer(36993), 36993, self.v4, len(self.v4),
                self.clips[0], len(self.clips[0]), self.clips[1], len(self.clips[1]),
                self.clips[2], len(self.clips[2])), 0)
            short = self.clips[0][:-1]
            self.assertEqual(lib.playerCrouchActivate(
                C.create_string_buffer(36994), 36994, self.v4, len(self.v4),
                short, len(short), self.clips[1], len(self.clips[1]),
                self.clips[2], len(self.clips[2])), 0)
        text = write_crouch_clips_header(
            *(ROOT / f'assets/anim/{name}.anim.bin' for name in ('0001', '010C', '0116')))
        for name, blob in zip(('banjo_crouch_enter_clip', 'banjo_crouch_turn_clip', 'banjo_crouch_noinput_clip'), self.clips):
            self.assertIn('static const unsigned char %s[]' % name, text)
            self.assertEqual(text.count('0x'), sum(len(blob) for blob in self.clips))
        header = ROOT / 'platform/3ds/source/generated_model.h'
        self.assertEqual(hashlib.sha256(header.read_bytes()).hexdigest(), MODEL_HASH)
        make = (ROOT / 'platform/3ds/Makefile').read_text()
        self.assertIn('BANJO3DS_LEARNED_ABILITIES ?= 0x9DB1', make)
        self.assertIn('$(BANJO3DS_RUN_ANIMATION) $(BANJO3DS_JUMP_ANIMATION) --runtime-transitions', make)
        self.assertIn('assets/anim/0001.anim.bin', make)
        self.assertEqual(C.sizeof(Player), 42792)

    def test_v4_and_v5_samples_match_for_original_clips(self):
        size, packet = self.assemble(self.libs[0])
        self.assertEqual(size, 36994)
        for clip in range(5):
            for phase in (0.0, 0.5, 1.0):
                old, new = Bones(), Bones()
                self.assertTrue(self.libs[0].banjo_pose_sample(self.v4, len(self.v4), clip, phase, old))
                self.assertTrue(self.libs[0].banjo_pose_sample(packet, len(packet), clip, phase, new))
                self.assertEqual(bytes(old), bytes(new))
                self.assertFalse(self.libs[0].banjo_pose_sample(self.v4, len(self.v4), 5, phase, old))
                self.assertTrue(self.libs[0].banjo_pose_sample(packet, len(packet), 5, phase, new))
        for lib in self.libs:
            lib.playerCrouchReset(0)
            left, right = Player(), Player()
            for player, data in ((left, self.v4), (right, packet)):
                player.motion.grounded = True
                player.locomotion.gait = 3
                player.metrics.physics_speed = 180
                self.assertTrue(lib.playerRuntimeAnimate(C.byref(player), data, len(data), DT))
            self.assertEqual(bytes(left.gait.pose.bones), bytes(right.gait.pose.bones))
            self.assertEqual(left.gait.gait, right.gait.gait)

    def test_l_enters_from_idle_and_each_grounded_gait(self):
        for lib in self.libs:
            for gait in (0, 1, 2, 3, 4):
                player = self.fresh(lib, gait=gait)
                self.step(lib, player, Z)
                got = self.view(lib)
                self.assertTrue(lib.playerCrouchActive(), gait)
                self.assertEqual((got.state, got.requested, got.anim_index, got.playback), (7, 7, 1, 1))
                self.assertEqual((got.physics_type, got.yaw_mode, got.yaw_state), (3, 7, 3))
                self.assertEqual((got.yaw_limit, got.yaw_percent), (350.0, 14.0))
                self.assertEqual(got.timer0, F(0.7).value)
                self.assertEqual(got.timer1, F(0.2).value)

    def test_coast_timer_bounds_and_locked_heading(self):
        for lib in self.libs:
            player = self.fresh(lib)
            player.horizontal.velocity[0] = 300
            views = []
            coast = None
            for i in range(22):
                self.step(lib, player, Z, magnitude=1, stick=90)
                views.append(self.view(lib))
                if i == 0:
                    coast = (player.horizontal.candidate[0], player.horizontal.candidate[1])
                self.assertEqual(player.horizontal.heading, views[-1].target_yaw)
                self.assertEqual(player.horizontal.visible, views[-1].yaw)
                self.assertEqual(player.motion.actor.yaw, views[-1].yaw)
                self.assertEqual(player.horizontal.speed, views[-1].target_speed)
            self.assertAlmostEqual(views[0].target_yaw, 90, delta=0.2)
            self.assertGreater(views[0].sfx_count, 0)
            self.assertEqual(views[0].puff_count, 0)
            self.assertGreater(abs(views[0].yaw - views[0].target_yaw), 8)
            self.assertGreater(coast[0], abs(coast[1]))
            for i in range(1, 12):
                self.assertEqual(views[i].phase, 0)
                self.assertEqual(views[i].target_speed, 300.0)
            self.assertLess(views[12].target_speed, 300.0)
            self.assertGreater(views[12].target_speed, 0.0)
            self.assertEqual(views[21].phase, 1)
            self.assertEqual(views[21].target_speed, 0.0)
            self.assertEqual(views[21].anim_index, 1)
            self.assertGreater(views[21].yaw, views[0].yaw)

    def test_yaw_deadzone_and_bounded_slew(self):
        for lib in self.libs:
            inside = self.fresh(lib)
            self.step(lib, inside, Z, magnitude=1, stick=7.9)
            self.assertEqual(self.view(lib).ideal_yaw, 0)
            edge = self.fresh(lib)
            self.step(lib, edge, Z, magnitude=1, stick=8)
            self.assertEqual(self.view(lib).ideal_yaw, 8)
            quiet = self.fresh(lib)
            self.step(lib, quiet, Z, magnitude=0, stick=90)
            self.assertEqual(self.view(lib).ideal_yaw, 0)
            turned = self.fresh(lib)
            self.step(lib, turned, Z, magnitude=1, stick=90)
            got = self.view(lib)
            self.assertEqual(got.ideal_yaw, 90)
            self.assertGreater(got.yaw, 11.0)
            self.assertLess(got.yaw, 12.5)
            self.assertEqual(turned.motion.actor.yaw, got.yaw)
            self.assertNotEqual(turned.horizontal.heading, got.ideal_yaw)

    def test_animation_phases_and_blended_clip_sample(self):
        for lib in self.libs:
            player = self.fresh(lib)
            self.step(lib, player, Z, dt=DT)
            self.assertTrue(lib.playerRuntimeAnimate(C.byref(player), self.v5, len(self.v5), DT))
            got = self.view(lib)
            self.assertEqual(got.anim_index, 1)
            self.assertGreater(got.anim_blend, 0)
            self.assertLess(got.anim_blend, 1)
            idle, dest, mixed = Bones(), Bones(), Bones()
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), 1, 0, idle))
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), 5, got.anim_timer, dest))
            lib.banjo_pose_blend(mixed, idle, dest, got.anim_blend)
            self.assertEqual(bytes(player.gait.pose.bones), bytes(mixed))
            recorded = self.fresh(lib)
            phases = []
            self.step(lib, recorded, Z, dt=2)
            phases.append(self.view(lib))
            for _ in range(3):
                self.step(lib, recorded, Z, dt=2)
                phases.append(self.view(lib))
            self.assertEqual((phases[1].phase, phases[1].anim_index), (1, 1))
            self.assertEqual((phases[2].phase, phases[2].anim_index), (2, 0x116))
            self.assertEqual((phases[3].phase, phases[3].anim_index, phases[3].playback), (1, 0x10C, 3))
            self.assertEqual(phases[3].anim_start, F(0.9999).value)
            self.assertEqual(phases[2].anim_blend, 1)
            self.assertTrue(lib.playerRuntimeAnimate(C.byref(recorded), self.v5, len(self.v5), 2))
            direct = Bones()
            clip = {1: 5, 0x10C: 6, 0x116: 7}[phases[3].anim_index]
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), clip, phases[3].anim_timer, direct))
            self.assertEqual(bytes(recorded.gait.pose.bones), bytes(direct))

    def test_slide_sfx_latch_follows_sfx_count(self):
        for lib in self.libs:
            still = self.fresh(lib)
            for _ in range(5):
                self.step(lib, still, Z)
                self.assertTrue(lib.playerCrouchActive())
                self.assertEqual(self.view(lib).sfx_count, 0)
                self.assertEqual(lib.playerCrouchSlideSfx(), 0)

            for speed, pulses in ((140, 0), (150, 1), (160, 1)):
                player = self.fresh(lib)
                player.horizontal.velocity[0] = speed
                self.step(lib, player, Z)
                entered = self.view(lib)
                self.assertTrue(lib.playerCrouchActive())
                self.assertEqual(entered.sfx_count, pulses)
                self.assertEqual(lib.playerCrouchSlideSfx(), pulses)
                self.step(lib, player, Z)
                held = self.view(lib)
                self.assertTrue(lib.playerCrouchActive())
                self.assertEqual(held.sfx_count, pulses)
                self.assertEqual(lib.playerCrouchSlideSfx(), 0)

            coast = self.fresh(lib)
            coast.horizontal.velocity[0] = 300
            previous = 0
            quiet = None
            for i in range(22):
                self.step(lib, coast, Z)
                got = self.view(lib)
                latch = lib.playerCrouchSlideSfx()
                self.assertTrue(lib.playerCrouchActive())
                self.assertEqual(latch, 1 if got.sfx_count > previous else 0)
                if i == 0 or got.target_speed > 160:
                    self.assertEqual(latch, 1)
                if i > 0 and got.target_speed <= 160:
                    self.assertEqual(latch, 0)
                    quiet = got
                previous = got.sfx_count
            self.assertIsNotNone(quiet)
            self.assertEqual(quiet.state, 7)
            self.assertGreater(previous, 1)

            lib.playerCrouchFrame(C.byref(coast), Z, 0)
            self.assertEqual(lib.playerCrouchSlideSfx(), 0)
            self.step(lib, coast, 0, dt=0.05)
            self.assertEqual(lib.playerCrouchSlideSfx(), 0)
            self.assertFalse(lib.playerCrouchActive())
            coast.horizontal.velocity[0] = 300
            self.step(lib, coast, Z)
            self.assertEqual(lib.playerCrouchSlideSfx(), 1)
            self.assertGreater(self.view(lib).sfx_count, previous)
            self.assertTrue(lib.playerCrouchActive())

            falling = self.fresh(lib)
            falling.horizontal.velocity[0] = 300
            self.step(lib, falling, Z)
            lib.crouch_host_set_floor(1700)
            self.step(lib, falling, Z)
            self.assertEqual(self.view(lib).state, 0x2F)
            lib.playerCrouchFrame(C.byref(falling), Z, 0)
            self.assertEqual(lib.playerCrouchSlideSfx(), 0)

            again = self.fresh(lib)
            again.horizontal.velocity[0] = 300
            self.step(lib, again, Z)
            self.assertEqual(lib.playerCrouchSlideSfx(), 1)
            self.step(lib, again, Z)
            self.assertEqual(lib.playerCrouchSlideSfx(), 1)
            self.step(lib, again, A, jump=1)
            self.assertEqual(self.view(lib).state, 5)
            self.step(lib, again, 0)
            self.assertEqual(lib.playerCrouchSlideSfx(), 0)
            self.assertFalse(lib.playerCrouchActive())
            self.assertFalse(again.motion.grounded)

            blocked = self.fresh(lib)
            blocked.horizontal.velocity[0] = 300
            lib.playerCrouchFrame(C.byref(blocked), Z, 1)
            lib.crouch_host_step(
                C.byref(blocked), 0, 0, DT, 0, self.floor_v, self.floor_t, len(self.floor_t))
            self.assertEqual(lib.playerCrouchSlideSfx(), 0)
            self.assertFalse(lib.playerCrouchActive())

    def test_release_latch_exit_fall_and_jump(self):
        for lib in self.libs:
            player = self.fresh(lib)
            self.step(lib, player, Z, dt=0.05)
            self.assertEqual(self.view(lib).timer1, F(0.2).value)
            held_frames = 0
            done = None
            for _ in range(6):
                player.horizontal.speed = 500
                self.step(lib, player, 0, magnitude=1, stick=45, dt=0.05)
                got = self.view(lib)
                if got.state == 7:
                    held_frames += 1
                    self.assertGreater(got.timer1, 0)
                    continue
                done = got
                break
            self.assertGreaterEqual(held_frames, 3)
            self.assertEqual(done.state, 1)
            self.assertEqual(done.target_speed, 0)
            self.assertEqual(player.horizontal.speed, 0)
            self.assertEqual(player.locomotion.gait, 0)
            self.assertFalse(lib.playerCrouchActive())
            self.assertEqual(done.target_speed, 0)
            self.assertEqual(player.horizontal.speed, 0)
            self.assertEqual(player.locomotion.gait, 0)
            self.assertFalse(lib.playerCrouchActive())

            falling = self.fresh(lib)
            falling.horizontal.velocity[0] = 80
            self.step(lib, falling, Z)
            lib.crouch_host_set_floor(1700)
            self.step(lib, falling, Z, magnitude=1, stick=0)
            fell = self.view(lib)
            self.assertEqual((fell.state, fell.active), (0x2F, 0))
            self.assertAlmostEqual(fell.target_yaw, 90, delta=0.2)
            self.assertEqual(falling.horizontal.heading, 0)

            latched = self.fresh(lib)
            self.step(lib, latched, Z, dt=DT)
            lib.crouch_host_set_floor(1700)
            self.step(lib, latched, 0, magnitude=1, stick=90, dt=DT)
            self.assertEqual(self.view(lib).state, 7)
            self.assertEqual(latched.horizontal.heading, 90)

            released = self.fresh(lib)
            self.step(lib, released, Z, dt=0.05)
            events = self.step(lib, released, A, magnitude=1, stick=0, dt=0.05, jump=1)
            self.assertEqual(self.view(lib).state, 5)
            self.assertTrue(events & 1)
            self.assertGreater(released.motion.vy, 0)
            self.assertFalse(released.motion.grounded)

            ordinary = self.fresh(lib)
            events = self.step(lib, ordinary, A, jump=1)
            self.assertFalse(lib.playerCrouchActive())
            self.assertTrue(events & 1)
            self.assertGreater(ordinary.motion.vy, 0)
            self.assertFalse(ordinary.motion.grounded)

    def test_conflicting_inputs_and_deferred_attacks(self):
        for lib in self.libs:
            for gait in (0, 3):
                player = self.fresh(lib, gait=gait)
                events = self.step(lib, player, Z | A, jump=1)
                self.assertFalse(lib.playerCrouchActive(), gait)
                self.assertEqual(lib.playerCrouchRequested(), 5)
                self.assertTrue(events & 1)
            held = self.fresh(lib)
            self.step(lib, held, Z)
            events = self.step(lib, held, Z | A, jump=1)
            self.assertEqual(self.view(lib).state, 7)
            self.assertFalse(events & 1)
            self.assertTrue(held.motion.grounded)
            claw = self.fresh(lib)
            self.step(lib, claw, Z)
            self.step(lib, claw, Z | B)
            self.assertEqual(self.view(lib).state, 7)
            barge = self.fresh(lib)
            lib.playerCrouchSetAbilities(0x9DB1)
            self.step(lib, barge, Z)
            events = self.step(lib, barge, Z | B, jump=1)
            self.assertEqual((self.view(lib).state, self.view(lib).active), (0x13, 0))
            self.assertEqual(lib.playerCrouchRequested(), 0x13)
            self.assertFalse(events & 1)
            self.assertEqual(barge.horizontal.speed, 0)
            self.step(lib, barge, Z | B)
            self.assertFalse(lib.playerCrouchActive())
            self.assertEqual(lib.playerCrouchState(), 0x13)
            flap = self.fresh(lib)
            lib.playerCrouchSetAbilities(0x9DB1)
            self.step(lib, flap, Z)
            events = self.step(lib, flap, Z | A, jump=1)
            self.assertEqual(self.view(lib).state, 0x12)
            self.assertFalse(events & 1)
            trot = self.fresh(lib)
            lib.playerCrouchSetAbilities(0x9DB1)
            self.step(lib, trot, Z)
            self.step(lib, trot, Z | C_LEFT)
            self.assertEqual(self.view(lib).state, 7)
            blocked = self.fresh(lib)
            lib.playerCrouchFrame(C.byref(blocked), Z, 1)
            lib.crouch_host_step(C.byref(blocked), 0, 0, DT, 0, self.floor_v, self.floor_t, len(self.floor_t))
            self.assertFalse(lib.playerCrouchActive())
            lib.playerGroundSetCrouchHook(None)
            try:
                bypass = self.fresh(lib)
                self.step(lib, bypass, Z)
                self.assertFalse(lib.playerCrouchActive())
            finally:
                lib.playerCrouchInstall()

    def test_first_person_priority_and_manual_camera_source(self):
        main = (ROOT / 'platform/3ds/source/main.c').read_text()
        ground = (ROOT / 'platform/3ds/source/player_ground.c').read_text()
        crouch = (ROOT / 'platform/3ds/source/player_crouch.c').read_text()
        mask = main.index('playerCrouchActive()')
        fp = main.index('cameraRuntimeFirstPersonInput(')
        frame = main.index('playerCrouchFrame(')
        move = main.index('cameraRuntimeMove(')
        self.assertLess(mask, fp)
        self.assertLess(fp, frame)
        self.assertLess(frame, move)
        self.assertLess(main.index('fp_buttons &= ~(uint32_t)FP_CUP'), fp)
        self.assertIn('player.first_person.buttons |= FP_CUP', main)
        self.assertIn('cameraRuntimeManualInput(&rareCamera, BANJO_DEBUG_CAMERA ? 0 : controls.manual, 0x23)', main)
        self.assertEqual(main.count('cameraRuntimeManualInput('), 1)
        self.assertIn('playerCrouchSetAbilities(BANJO_LEARNED_ABILITIES)', main)
        self.assertIn('cameraRuntimeSetLearnedAbilities(&rareCamera, BANJO_LEARNED_ABILITIES)', main)
        self.assertIn('a->y+80.0f', (ROOT / 'platform/3ds/source/camera_runtime.c').read_text())
        self.assertEqual(ground.count('bp_frame_resolve('), 1)
        self.assertLess(ground.index('c->observe('), ground.index('bp_frame_resolve('))
        self.assertIn('BANJO_HORIZONTAL_LOCKED', ground)
        self.assertIn('in->can_trot = 0', crouch)
        self.assertIn('in->can_egg = 0', crouch)
        self.assertIn('in->can_wonderwing = 0', crouch)
        self.assertNotIn('#ifdef BANJO_LEARNED_ABILITIES', crouch)
        self.assertIn('if (!BANJO_DEBUG_CAMERA)\n            playerCrouchFrame(', main)

    def fadd(self, a, b):
        return F(F(a).value + F(b).value).value

    def fsub(self, a, b):
        return F(F(a).value - F(b).value).value

    def fmul(self, a, b):
        return F(F(a).value * F(b).value).value

    def fdiv(self, a, b):
        return F(F(a).value / F(b).value).value

    def idle_advance(self, phase, factor, dt=DT):
        dt = min(F(dt).value, F(0.05).value)
        phase = self.fadd(phase, self.fdiv(dt, 5.5))
        if phase >= 1.0:
            phase = self.fsub(phase, int(phase))
        factor = self.fadd(factor, self.fdiv(dt, 0.2))
        if factor > 1.0:
            factor = F(1.0).value
        return phase, factor

    def animate(self, lib, player, dt=DT):
        return lib.playerRuntimeAnimate(C.byref(player), self.v5, len(self.v5), dt)

    def assert_idle_pose(self, lib, player):
        dest, mixed = Bones(), Bones()
        self.assertTrue(lib.banjo_pose_sample(
            self.v5, len(self.v5), 1, player.gait.phase, dest))
        lib.banjo_pose_blend(mixed, player.gait.source, dest, player.gait.factor)
        self.assertEqual(bytes(player.gait.pose.bones), bytes(mixed))

    def hold_crouch(self, lib, player, frames=40):
        for _ in range(frames):
            self.step(lib, player, Z)
            self.assertTrue(lib.playerCrouchActive())
            self.assertTrue(self.animate(lib, player))
        return bytes(player.gait.pose.bones), player.gait.phase

    def test_crouch_to_idle_blends_from_the_final_pose(self):
        for lib in self.libs:
            player = self.fresh(lib)
            crouch_pose, crouch_phase = self.hold_crouch(lib, player)
            self.step(lib, player, 0)
            got = self.view(lib)
            self.assertEqual((got.state, got.active), (1, 0))
            self.assertFalse(lib.playerCrouchActive())
            self.assertEqual(bytes(player.gait.pose.bones), crouch_pose)
            self.assertTrue(self.animate(lib, player))
            phase, factor = self.idle_advance(0.0, 0.0)
            self.assertEqual(player.gait.gait, 0)
            self.assertEqual(player.gait.phase, phase)
            self.assertEqual(player.gait.factor, factor)
            self.assertNotEqual(player.gait.phase, crouch_phase)
            self.assertEqual(bytes(player.gait.source), crouch_pose)
            self.assert_idle_pose(lib, player)
            idle = Bones()
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), 1, phase, idle))
            self.assertNotEqual(bytes(player.gait.pose.bones), crouch_pose)
            self.assertNotEqual(bytes(player.gait.pose.bones), bytes(idle))
            source = bytes(player.gait.source)
            frames = 1
            while player.gait.factor < 1.0:
                self.step(lib, player, 0)
                self.assertEqual(self.view(lib).state, 1)
                self.assertFalse(lib.playerCrouchActive())
                self.assertTrue(self.animate(lib, player))
                frames += 1
                phase, factor = self.idle_advance(phase, factor)
                self.assertEqual(player.gait.phase, phase)
                self.assertEqual(player.gait.factor, factor)
                self.assertEqual(bytes(player.gait.source), source)
                self.assertNotEqual(player.gait.phase, self.idle_advance(0.0, 0.0)[0])
                self.assertLess(frames, 12)
            self.assertEqual(player.gait.factor, F(1.0).value)
            self.assertEqual(frames, 6)
            self.assertAlmostEqual(frames * DT, 0.2, delta=DT)
            continued = player.gait.phase
            self.step(lib, player, 0)
            self.assertTrue(self.animate(lib, player))
            phase, factor = self.idle_advance(continued, 1.0)
            self.assertEqual(player.gait.phase, phase)
            self.assertEqual(player.gait.factor, F(1.0).value)
            self.assertEqual(bytes(player.gait.source), source)
            self.assertGreater(player.gait.phase, continued)

    def test_rapid_crouch_tap_blends_from_the_intermediate_pose(self):
        for lib in self.libs:
            player = self.fresh(lib)
            self.step(lib, player, Z)
            self.assertTrue(self.animate(lib, player))
            last = None
            for _ in range(20):
                last = self.view(lib)
                self.step(lib, player, 0)
                if not lib.playerCrouchActive():
                    break
                self.assertTrue(self.animate(lib, player))
            else:
                self.fail('crouch tap did not return to idle')
            self.assertEqual(self.view(lib).state, 1)
            self.assertEqual(last.anim_index, 1)
            self.assertGreater(last.anim_timer, 0.0)
            self.assertLess(last.anim_timer, 1.0)
            crouch_pose = bytes(player.gait.pose.bones)
            settled = Bones()
            self.assertTrue(lib.banjo_pose_sample(self.v5, len(self.v5), 5, 1.0, settled))
            self.assertNotEqual(crouch_pose, bytes(settled))
            self.assertTrue(self.animate(lib, player))
            phase, factor = self.idle_advance(0.0, 0.0)
            self.assertEqual(bytes(player.gait.source), crouch_pose)
            self.assertEqual(player.gait.phase, phase)
            self.assertEqual(player.gait.factor, factor)
            self.assertNotEqual(player.gait.phase, last.anim_timer)
            self.step(lib, player, 0)
            self.assertTrue(self.animate(lib, player))
            phase, factor = self.idle_advance(phase, factor)
            self.assertEqual(player.gait.phase, phase)
            self.assertEqual(bytes(player.gait.source), crouch_pose)

    def test_stick_release_keeps_the_following_gait_blend(self):
        for lib in self.libs:
            player = self.fresh(lib)
            self.hold_crouch(lib, player)
            player.locomotion.gait = 3
            self.step(lib, player, 0, magnitude=0.6, stick=10)
            self.assertEqual(self.view(lib).state, 1)
            self.assertEqual(player.locomotion.gait, 0)
            self.assertTrue(self.animate(lib, player))
            phase, factor = self.idle_advance(0.0, 0.0)
            self.assertEqual(player.gait.gait, 0)
            self.assertEqual(player.gait.phase, phase)
            self.assertEqual(player.gait.factor, factor)
            mixed = bytes(player.gait.pose.bones)
            player.locomotion.gait = 3
            player.metrics.physics_speed = 180
            self.step(lib, player, 0, magnitude=0.6, stick=10)
            self.assertEqual(player.locomotion.gait, 3)
            self.assertFalse(lib.playerCrouchActive())
            self.assertTrue(self.animate(lib, player))
            duration = self.fadd(self.fmul(
                self.fdiv(self.fsub(180.0, 150.0), self.fsub(225.0, 150.0)),
                self.fsub(0.58, 0.92)), 0.92)
            self.assertEqual(player.gait.gait, 3)
            self.assertEqual(bytes(player.gait.source), mixed)
            self.assertEqual(player.gait.factor, self.fdiv(DT, 0.2))
            self.assertEqual(player.gait.phase, self.fdiv(DT, duration))
            self.assertNotEqual(player.gait.phase, self.idle_advance(phase, factor)[0])

    def test_jump_fall_and_first_person_skip_the_idle_handoff(self):
        for lib in self.libs:
            released = self.fresh(lib)
            self.step(lib, released, Z)
            self.assertTrue(self.animate(lib, released))
            crouch_pose = bytes(released.gait.pose.bones)
            crouch_phase = released.gait.phase
            crouch_factor = released.gait.factor
            source = bytes(released.gait.source)
            events = self.step(lib, released, A, magnitude=1, stick=0, dt=0.05, jump=1)
            self.assertEqual(self.view(lib).state, 5)
            self.assertFalse(lib.playerCrouchActive())
            self.assertTrue(events & 1)
            self.assertFalse(released.motion.grounded)
            self.assertTrue(self.animate(lib, released, 0.05))
            self.assertTrue(released.jumpActive)
            self.assertEqual(bytes(released.gait.pose.bones), crouch_pose)
            self.assertEqual(released.gait.phase, crouch_phase)
            self.assertEqual(released.gait.factor, crouch_factor)
            self.assertEqual(bytes(released.gait.source), source)
            self.assertNotEqual(released.gait.phase, self.idle_advance(0.0, 0.0, 0.05)[0])

            falling = self.fresh(lib)
            self.step(lib, falling, Z)
            self.assertTrue(self.animate(lib, falling))
            phase = falling.gait.phase
            factor = falling.gait.factor
            pose = bytes(falling.gait.pose.bones)
            source = bytes(falling.gait.source)
            lib.crouch_host_set_floor(1700)
            self.step(lib, falling, Z, magnitude=1, stick=0)
            fell = self.view(lib)
            self.assertEqual((fell.state, fell.active), (0x2F, 0))
            self.assertTrue(falling.motion.grounded)
            self.assertTrue(self.animate(lib, falling))
            expected_phase, expected_factor = self.idle_advance(phase, factor)
            self.assertEqual(falling.gait.phase, expected_phase)
            self.assertEqual(falling.gait.factor, expected_factor)
            self.assertEqual(bytes(falling.gait.source), source)
            self.assertNotEqual(bytes(falling.gait.source), pose)
            self.assertNotEqual(falling.gait.phase, self.idle_advance(0.0, 0.0)[0])

            looking = self.fresh(lib)
            looking.gait.initialized = True
            looking.gait.gait = 0
            looking.gait.factor = 1
            looking.gait.phase = F(0.37).value
            lib.playerCrouchFrame(C.byref(looking), Z, 1)
            lib.crouch_host_step(
                C.byref(looking), 0, 0, DT, 0, self.floor_v, self.floor_t, len(self.floor_t))
            self.assertFalse(lib.playerCrouchActive())
            self.assertTrue(self.animate(lib, looking))
            phase, factor = self.idle_advance(F(0.37).value, 1.0)
            self.assertEqual(looking.gait.phase, phase)
            self.assertEqual(looking.gait.factor, factor)
            self.assertNotEqual(looking.gait.phase, self.idle_advance(0.0, 0.0)[0])
            self.step(lib, looking, 0)
            self.assertTrue(self.animate(lib, looking))
            phase, factor = self.idle_advance(phase, factor)
            self.assertEqual(looking.gait.phase, phase)
            self.assertEqual(looking.gait.factor, F(1.0).value)


if __name__ == '__main__':
    unittest.main()
