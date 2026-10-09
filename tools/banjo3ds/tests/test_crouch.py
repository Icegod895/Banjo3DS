"""Host crouch reference. Production is compared with extracted original C at -O0 and -O2."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

import crouch_reference as ref
from horizontal_reference import FLAGS, ROOT

Z, A, B = 1, 8, 9
C_LEFT, C_DOWN, C_UP, C_RIGHT = 10, 11, 12, 13
DT = 1.0 / 30.0
PROD = ROOT / 'tools/banjo3ds/crouch/crouch.c'


def make(**kw):
    inp = ref.Input()
    inp.dt = kw.pop('dt', DT)
    inp.transformation = kw.pop('transformation', 1)
    for button in range(14):
        inp.release_count[button] = 2
    for button in kw.pop('held', ()):
        inp.button_count[button] = 2
        inp.release_count[button] = 0
    for button in kw.pop('pressed', ()):
        inp.button_count[button] = 1
        inp.release_count[button] = 0
    buttons = kw.pop('buttons', None)
    if buttons is not None:
        for button, count in enumerate(buttons):
            inp.button_count[button] = count
    releases = kw.pop('releases', None)
    if releases is not None:
        for button, count in enumerate(releases):
            inp.release_count[button] = count
    for name, value in kw.items():
        setattr(inp, name, value)
    return inp


class CrouchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='crouch-tests-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs, cls.oracles = [], []
        for opt in ('-O0', '-O2'):
            path = Path(cls.tmp.name) / (opt + '.so')
            result = subprocess.run(
                ['cc', *FLAGS, opt, '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                 str(PROD), '-lm', '-o', str(path)],
                capture_output=True, text=True)
            if result.returncode or result.stderr:
                raise RuntimeError(result.stderr)
            lib = C.CDLL(str(path))
            ref.bind(lib, 'banjo_crouch_')
            cls.libs.append(lib)
            cls.oracles.append(ref.library(opt))

    def view(self, lib, oracle):
        out = ref.View()
        (lib.ref_view if oracle else lib.banjo_crouch_view)(C.byref(out))
        return bytes(out)

    def call(self, lib, oracle, name, *args):
        prefix = 'ref_' if oracle else 'banjo_crouch_'
        return getattr(lib, prefix + name)(*args)

    def reset(self, lib, oracle, yaw=0.0, ideal=0.0):
        self.call(lib, oracle, 'reset', yaw, ideal)

    def select(self, lib, oracle, inp):
        return self.call(lib, oracle, 'select', C.byref(inp))

    def enter(self, lib, oracle, inp):
        self.call(lib, oracle, 'enter', C.byref(inp))

    def step(self, lib, oracle, inp):
        self.call(lib, oracle, 'step', C.byref(inp))

    def snapshot(self, lib, oracle):
        view = ref.View()
        self.call(lib, oracle, 'view', C.byref(view))
        return view

    def assert_same(self, label, prod, original):
        if prod == original:
            return
        left, right = ref.View.from_buffer_copy(prod), ref.View.from_buffer_copy(original)
        for name in ref.VIEW_FIELDS:
            if getattr(left, name) != getattr(right, name):
                self.fail('%s field %s production=%r oracle=%r' % (label, name, getattr(left, name), getattr(right, name)))
        self.fail(label + ' bytes differ without a named field mismatch')

    def both(self, fn):
        for opt, lib, oracle in zip(('-O0', '-O2'), self.libs, self.oracles):
            fn(opt, lib, oracle)

    def test_layout_and_source_order(self):
        self.assertEqual(self.libs[0].banjo_crouch_input_size(), C.sizeof(ref.Input))
        self.assertEqual(self.libs[0].banjo_crouch_view_size(), C.sizeof(ref.View))
        self.assertEqual(self.oracles[0].ref_input_size(), C.sizeof(ref.Input))
        self.assertEqual(self.oracles[0].ref_view_size(), C.sizeof(ref.View))
        init = ref.original_function('src/core2/bs/crouch.c', 'bscrouch_init')
        update = ref.original_function('src/core2/bs/crouch.c', 'bscrouch_update')
        choose = ref.original_function('src/core2/bs/crouch.c', 'func_802ADCD4')
        for text in ('0.5357f', '0.7f', '0.2f', '350.0f', '14.0f', '8.0f', '140.0f', 'BA_PHYSICS_LOCKED_ROTATION'):
            self.assertIn(text, init)
        self.assertLess(update.index('batimer_decrement(0)'), update.index('ml_map_f'))
        self.assertLess(update.index('player_shouldFall'), update.index('func_802ADCD4'))
        self.assertLess(update.index('func_802ADCD4'), update.index('batimer_isNonzero'))
        self.assertLess(update.index('batimer_isNonzero'), update.index('player_inWater'))
        self.assertIn('0.9999f', ref.original_function('src/core2/bs/crouch.c', 'func_802AD728'))
        self.assertNotIn('playback_direction', ref.original_function('src/core2/bs/crouch.c', 'func_802AD728'))
        self.assertLess(choose.index('bainput_should_wonderwing'), choose.index('bainput_should_trot'))
        self.assertLess(choose.index('bainput_should_trot'), choose.index('bainput_should_flap_flip'))
        self.assertLess(choose.index('bainput_should_flap_flip'), choose.index('bainput_should_beak_barge'))
        self.assertLess(choose.index('BS_6_CLAW'), choose.index('bs_getTypeOfJump'))
        walk = ref.original_function('src/core2/bs/walk.c', 'bswalk_update')
        fast = ref.original_function('src/core2/bs/walk.c', 'bswalk_fast_update')
        stand = ref.original_function('src/core2/bs/stand.c', 'bsstand_update')
        self.assertLess(walk.index('BS_C_SKID'), walk.index('bainput_should_look_first_person_camera'))
        self.assertLess(walk.index('player_shouldFall'), walk.index('bakey_held(BUTTON_Z)'))
        self.assertLess(fast.rindex('bainput_should_look_first_person_camera'), fast.index('player_isOnDangerousGround'))
        self.assertLess(stand.index('func_802B488C'), stand.rindex('player_shouldFall'))
        self.assertIn('return 6;', ref.original_function('src/core2/code_14420.c', 'func_8029BAF0'))
        table = (ROOT / 'src/core2/code_14420.c').read_text()
        self.assertIn('{BS_98_WALK_DRONE,            ASSET_3_ANIM_BSWALK,            0.43f}', table)
        attack = ref.original_function('src/core2/bs/walk.c', 'func_802B6F20')
        self.assertLess(attack.index('bsWalkWalkFastWalkVelocityThreshold <'), attack.index('can_roll'))
        self.assertIn('bsWalkWalkFastWalkVelocityThreshold = 225.0f', (ROOT / 'src/core2/bs/walk.c').read_text())
        self.assertIn('bsWalkSkidVelocity = 125.0f', (ROOT / 'src/core2/bs/walk.c').read_text())
        bridge = (ROOT / 'tools/banjo3ds/bridge_state/bridge.h').read_text()
        self.assertIn('0x9db1', bridge.lower())

    def test_selection_priorities_match_original(self):
        def check(opt, lib, oracle):
            cases = []
            for context, zone, provisional in (
                    (1, 0, 0), (1, 3, 99), (0x1F, 1, 0x1F), (2, 2, 2), (3, 3, 3), (4, 4, 4), (0x7A, 1, 0)):
                cases.append(dict(context=context, zone=zone, provisional=provisional))
                cases.append(dict(context=context, zone=zone, provisional=provisional, held=(Z,)))
                cases.append(dict(context=context, zone=zone, provisional=provisional, held=(Z,), pressed=(B,), can_claw=1))
                cases.append(dict(context=context, zone=zone, provisional=provisional, held=(Z,), pressed=(A,), can_flap_flip=1))
                cases.append(dict(context=context, zone=zone, provisional=provisional, pressed=(A,)))
                cases.append(dict(context=context, zone=zone, provisional=provisional, fp_look=1, held=(Z,)))
                cases.append(dict(context=context, zone=zone, provisional=provisional, should_fall=1, held=(Z,)))
                cases.append(dict(context=context, zone=zone, provisional=provisional, slide=1))
                cases.append(dict(context=context, zone=zone, provisional=provisional, in_water=1, held=(Z,)))
            for speed, roll, claw in ((225.0, 1, 1), (225.0, 0, 1), (225.01, 1, 1), (225.01, 0, 1), (500.0, 0, 0)):
                cases.append(dict(context=3, provisional=3, held=(Z,), pressed=(B,), target_speed=speed, can_roll=roll, can_claw=claw))
                cases.append(dict(context=1, zone=0, pressed=(B,), target_speed=speed, can_roll=roll, can_claw=claw))
            for flag in ('spring', 'flight', 'turbo', 'transform', 'notedoor', 'wading', 'timeout_flag', 'jiggy', 'boggy'):
                cases.append(dict(context=3, provisional=3, held=(Z,), **{flag: 1}))
            cases.append(dict(context=3, provisional=3, held=(Z,), notedoor=1, transformation=6))
            cases.append(dict(context=3, provisional=3, held=(Z,), boggy=1, transformation=4, turbo=1))
            cases.append(dict(context=4, provisional=0, fp_look=1))
            cases.append(dict(context=4, provisional=0x98, fp_look=1, held=(Z,)))
            cases.append(dict(context=3, provisional=3, skid=1, horizontal_velocity=125.0))
            cases.append(dict(context=3, provisional=3, skid=1, horizontal_velocity=125.01, fp_look=1))
            cases.append(dict(context=3, provisional=3, skid=1, horizontal_velocity=125.01, held=(Z,)))
            cases.append(dict(context=0x7A, zone=0, dangerous_ground=1, held=(Z,)))
            cases.append(dict(context=0x7A, zone=3, dangerous_ground=0))
            cases.append(dict(context=0x7A, zone=3, dangerous_ground=1))
            cases.append(dict(context=99, provisional=42, held=(Z,)))
            for row in cases:
                inp = make(**row)
                self.assertEqual(self.select(lib, False, inp), self.select(oracle, True, inp), (opt, row))
        self.both(check)
        lib = self.libs[0]
        self.reset(lib, False)
        self.assertEqual(self.select(lib, False, make(context=1, held=(Z,))), 7)
        self.assertEqual(self.select(lib, False, make(context=1, zone=3)), 3)
        self.assertEqual(self.select(lib, False, make(context=1, held=(Z,), pressed=(B,), can_claw=1)), 6)
        self.assertEqual(self.select(lib, False, make(context=1, held=(Z,), fp_look=1)), 0x98)
        self.assertEqual(self.select(lib, False, make(context=1, held=(Z,), should_fall=1)), 0x2F)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), should_fall=1)), 7)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), fp_look=1)), 7)
        self.assertEqual(self.select(lib, False, make(context=4, provisional=0, fp_look=1)), 0)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(B,), target_speed=225.0, can_roll=1, can_claw=1)), 6)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(B,), target_speed=225.01, can_roll=1, can_claw=1)), 0x31)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(B,), target_speed=500.0, can_roll=0, can_claw=1)), 7)
        self.assertEqual(self.select(lib, False, make(context=1, pressed=(B,), target_speed=500.0, can_roll=1, can_claw=1)), 6)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(A,), can_flap_flip=1)), 0x12)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, pressed=(A,), spring=1)), 5)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, pressed=(A,), flight=1)), 0x23)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(A,), flight=1, can_flap_flip=1)), 0x12)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(A,), flight=1, can_flap_flip=0)), 0x23)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), turbo=1)), 0x14)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), transform=1)), 0x98)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), notedoor=1, transformation=6)), 0x46)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), notedoor=1)), 0x34)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), wading=1)), 0x25)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), timeout_flag=1)), 0x53)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), jiggy=1)), 0x44)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), boggy=1, transformation=4)), 0x80)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), boggy=1, turbo=1)), 0x53)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, skid=1, horizontal_velocity=125.0)), 3)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, skid=1, horizontal_velocity=125.01)), 0xC)
        self.assertEqual(self.select(lib, False, make(context=0x1F, provisional=0x1F, held=(Z,))), 7)
        self.assertEqual(self.select(lib, False, make(context=2, provisional=2, held=(Z,))), 7)
        self.assertEqual(self.select(lib, False, make(context=4, provisional=4, held=(Z,))), 7)
        self.assertEqual(self.select(lib, False, make(context=0x7A, provisional=99, dangerous_ground=1, zone=2)), 0)
        self.assertEqual(self.select(lib, False, make(context=0x7A, zone=0, dangerous_ground=1, held=(Z,))), 7)

    def test_histories_are_identical_at_O0_and_O2(self):
        # Independent full runs so O0 and O2 do not share state.
        runs = []
        for opt, lib, oracle in zip(('-O0', '-O2'), self.libs, self.oracles):
            frames = []
            self.reset(lib, False, 10.0, 10.0)
            self.reset(oracle, True, 10.0, 10.0)
            enter = make(held=(Z,), velocity_x=300.0, velocity_z=40.0, prev_anim=0x6F, stick_distance=1, stick_angle=40)
            self.enter(lib, False, enter)
            self.enter(oracle, True, enter)
            frames.append(self.view(lib, False))
            self.assert_same((opt, 'enter'), frames[-1], self.view(oracle, True))
            for i in range(48):
                inp = make(held=(Z,), stick_distance=1 if i < 30 else 0, stick_angle=40 if i < 30 else 0)
                self.step(lib, False, inp)
                self.step(oracle, True, inp)
                frames.append(self.view(lib, False))
                self.assert_same((opt, i), frames[-1], self.view(oracle, True))
            runs.append(frames)
        self.assertEqual(runs[0], runs[1])
        oracle_frames = []
        for oracle in self.oracles:
            self.reset(oracle, True, 10.0, 10.0)
            enter = make(held=(Z,), velocity_x=300.0, velocity_z=40.0, prev_anim=0x6F, stick_distance=1, stick_angle=40)
            self.enter(oracle, True, enter)
            got = [self.view(oracle, True)]
            for i in range(48):
                self.step(oracle, True, make(held=(Z,), stick_distance=1 if i < 30 else 0, stick_angle=40 if i < 30 else 0))
                got.append(self.view(oracle, True))
            oracle_frames.append(got)
        self.assertEqual(oracle_frames[0], oracle_frames[1])

    def test_coast_latch_phases_and_heading(self):
        lib, oracle = self.libs[0], self.oracles[0]
        def pair(yaw, ideal, enter, steps):
            self.reset(lib, False, yaw, ideal)
            self.reset(oracle, True, yaw, ideal)
            before = self.view(lib, False)
            self.select(lib, False, make(context=1, held=(Z,), target_speed=999))
            self.assertEqual(before, self.view(lib, False))
            self.enter(lib, False, enter)
            self.enter(oracle, True, enter)
            views = [(self.snapshot(lib, False), self.snapshot(oracle, True))]
            self.assert_same('enter', self.view(lib, False), self.view(oracle, True))
            for i, inp in enumerate(steps):
                self.step(lib, False, inp)
                self.step(oracle, True, inp)
                self.assert_same(('step', i), self.view(lib, False), self.view(oracle, True))
                views.append((self.snapshot(lib, False), self.snapshot(oracle, True)))
            return views

        held = make(held=(Z,), velocity_x=300, velocity_z=0, dt=DT)
        # 0.7s coast at 1/30s: full speed while the timer stays above 0.3s,
        # then a linear decay, then phase 1 on the frame the mapped speed hits 0.
        views = pair(0, 0, held, [make(held=(Z,), dt=DT) for _ in range(21)])
        self.assertGreater(views[0][0].sfx_count, 0)
        self.assertEqual(views[0][0].puff_count, 0)
        self.assertGreater(views[1][0].puff_count, 0)
        self.assertEqual(views[0][0].phase, 0)
        self.assertEqual(views[0][0].anim_index, 1)
        self.assertEqual(views[0][0].physics_type, 3)
        self.assertEqual(views[0][0].yaw_mode, 7)
        self.assertEqual(views[0][0].yaw_state, 3)
        self.assertEqual(views[0][0].yaw_limit, 350.0)
        self.assertEqual(views[0][0].yaw_percent, 14.0)
        for i in range(1, 12):
            self.assertEqual(views[i][0].phase, 0)
            self.assertEqual(views[i][0].target_speed, 300.0)
        self.assertEqual(views[12][0].phase, 0)
        self.assertLess(views[12][0].target_speed, 300.0)
        self.assertGreater(views[12][0].target_speed, 0.0)
        self.assertEqual(views[20][0].phase, 0)
        self.assertGreater(views[20][0].target_speed, 0.0)
        self.assertEqual(views[21][0].phase, 1)
        self.assertEqual(views[21][0].target_speed, 0.0)
        self.assertEqual(views[21][0].anim_index, 1)

        slow = pair(0, 0, make(held=(Z,), velocity_x=150, dt=DT), [make(held=(Z,), dt=DT)])
        self.assertEqual(slow[0][0].sfx_count, 1)
        self.assertEqual(slow[1][0].sfx_count, 1)
        self.assertEqual(slow[1][0].puff_count, 0)
        edge = pair(0, 0, make(held=(Z,), velocity_x=140, dt=DT), [make(held=(Z,), dt=DT)])
        self.assertEqual(edge[0][0].sfx_count, 0)
        faster = pair(0, 0, make(held=(Z,), velocity_x=160, dt=DT), [make(held=(Z,), dt=DT)])
        self.assertEqual(faster[0][0].sfx_count, 1)
        self.assertEqual(faster[1][0].sfx_count, 1)
        over = pair(0, 0, make(held=(Z,), velocity_x=221, dt=DT), [make(held=(Z,), dt=DT)])
        self.assertEqual(over[1][0].puff_count, 1)

        fresh = pair(0, 0, make(held=(Z,), prev_anim=0, dt=DT), [])
        blended = pair(0, 0, make(held=(Z,), prev_anim=0x6F, dt=DT), [])
        self.assertEqual(fresh[0][0].anim_blend, 1)
        self.assertLess(blended[0][0].anim_blend, 1)
        self.assertGreater(blended[0][0].anim_blend, 0)

        for prev, start in ((9, C.c_float(0.5357).value), (10, C.c_float(0.5357).value), (0x1A, C.c_float(0.5357).value), (1, 0.0)):
            views = pair(0, 0, make(held=(Z,), prev_state=prev, dt=DT), [])
            self.assertEqual(views[0][0].anim_start, start)
            self.assertEqual(views[0][0].anim_ctrl_timer, start)

        dead = pair(0, 0, make(held=(Z,), stick_distance=1, stick_angle=8, dt=DT), [])
        inside = pair(0, 0, make(held=(Z,), stick_distance=1, stick_angle=7.9, dt=DT), [])
        quiet = pair(0, 0, make(held=(Z,), stick_distance=0, stick_angle=90, dt=DT), [])
        self.assertEqual(dead[0][0].ideal_yaw, 8)
        self.assertEqual(inside[0][0].ideal_yaw, 0)
        self.assertEqual(quiet[0][0].ideal_yaw, 0)

        aimed = pair(20, 20, make(held=(Z,), velocity_x=0, velocity_z=0, dt=DT), [])
        self.assertEqual(aimed[0][0].target_yaw_set, 0)
        self.assertEqual(aimed[0][0].target_yaw, 0)
        self.assertEqual(aimed[0][0].yaw, 20)
        # h < 0.01 is a double compare. 0.01f is just under that, so it does not set a heading.
        below = pair(0, 0, make(held=(Z,), velocity_x=0.009, dt=DT), [])
        above = pair(0, 0, make(held=(Z,), velocity_x=0.0100001, dt=DT), [])
        self.assertEqual(below[0][0].target_yaw_set, 0)
        self.assertEqual(above[0][0].target_yaw_set, 1)
        heading = {}
        for key, vx, vz, expect in (
                ('x', 1, 0, 90), ('z', 0, 1, 0), ('-z', 0, -1, 180),
                ('xz', 1, 1, 45), ('x-z', 1, -1, 135), ('-x-z', -1, -1, 225), ('-xz', -1, 1, 315)):
            views = pair(0, 0, make(held=(Z,), velocity_x=vx, velocity_z=vz, dt=DT), [make(held=(Z,), stick_distance=1, stick_angle=10, dt=DT)])
            heading[key] = views[0][0].target_yaw
            self.assertEqual(views[0][0].target_yaw_set, 1)
            self.assertAlmostEqual(views[0][0].target_yaw, expect, delta=0.2)
            self.assertEqual(views[1][0].target_yaw, views[0][0].target_yaw)
        self.assertNotEqual(heading['z'], heading['-z'])

        latched = pair(0, 0, make(held=(Z,), dt=DT), [make(dt=DT), make(dt=DT, pressed=(B,), can_claw=1)])
        self.assertEqual(latched[1][0].state, 7)
        self.assertEqual(latched[1][0].requested, 0)
        self.assertEqual(latched[2][0].state, 6)
        self.assertEqual(latched[2][0].active, 0)
        jumped = pair(0, 0, make(held=(Z,), dt=0.05), [make(dt=0.05, pressed=(A,), can_flap_flip=1)])
        self.assertEqual(jumped[1][0].state, 5)
        flight = pair(0, 0, make(held=(Z,), dt=1), [make(dt=1, pressed=(A,), flight=1)])
        self.assertEqual(flight[1][0].state, 0x23)
        water = pair(0, 0, make(held=(Z,), dt=0.01), [make(dt=0.01, in_water=1)])
        self.assertEqual(water[1][0].state, 0x2D)
        falling = pair(0, 0, make(held=(Z,), dt=DT), [make(held=(Z,), should_fall=1)])
        self.assertEqual(falling[1][0].state, 0x2F)
        released_fall = pair(0, 0, make(held=(Z,), dt=DT), [make(dt=DT, should_fall=1)])
        self.assertEqual(released_fall[1][0].state, 7)

        both_zero = [0] * 14
        quirk = pair(0, 0, make(held=(Z,)), [make(buttons=both_zero, releases=both_zero, can_wonderwing=1)])
        self.assertEqual(quirk[1][0].state, 7)
        wonder = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_RIGHT,), can_wonderwing=1)])
        self.assertEqual(wonder[1][0].state, 0x1A)
        self.assertEqual(wonder[1][0].item_use, 1)
        self.assertEqual(wonder[1][0].buzzer, 0)
        empty = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_RIGHT,), can_wonderwing=1, feather_empty=1)])
        self.assertEqual(empty[1][0].state, 7)
        self.assertEqual(empty[1][0].buzzer, 1)
        self.assertEqual(empty[1][0].item_use, 0)
        eggs = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_DOWN,), can_egg=1)])
        self.assertEqual(eggs[1][0].state, 0xA)
        self.assertEqual(eggs[1][0].item_use, 0)
        shot = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_UP,), can_egg=1, fp_look=1)])
        self.assertEqual(shot[1][0].state, 9)
        trot = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_LEFT,), can_trot=1)])
        self.assertEqual(trot[1][0].state, 0x14)
        no_trot = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(C_LEFT,))])
        self.assertEqual(no_trot[1][0].state, 7)
        barge = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(A, B, C_LEFT, C_RIGHT, C_UP, C_DOWN),
                                                    can_flap_flip=1, can_beak_barge=1, can_trot=1, can_wonderwing=1, can_egg=1)])
        self.assertEqual(barge[1][0].state, 0x13)
        flip = pair(0, 0, make(held=(Z,)), [make(held=(Z,), pressed=(A,), can_flap_flip=1)])
        self.assertEqual(flip[1][0].state, 0x12)

        idle = pair(180, 180, make(held=(Z,), stick_distance=1, stick_angle=0, dt=DT), [])
        self.assertGreater(abs(idle[0][0].ideal_yaw - idle[0][0].yaw), 20)
        exit_views = pair(0, 0, make(held=(Z,), stick_distance=1, stick_angle=180, dt=DT),
                          [make(held=(Z,), dt=DT) for _ in range(8)] + [make(dt=DT)])
        left = exit_views[-2][0]
        done = exit_views[-1][0]
        self.assertEqual(done.state, 1)
        self.assertEqual(done.anim_index, 0x6F)
        self.assertEqual(done.anim_duration, 5.5)
        self.assertEqual(done.physics_type, 2)
        self.assertEqual(done.yaw_mode, 1)
        self.assertEqual(done.yaw_state, 1)
        self.assertEqual(done.target_speed, 0)
        self.assertEqual(done.fidget, 1)
        self.assertGreater(abs(done.yaw - left.yaw), 11.67)

        quick = pair(0, 0, make(held=(Z,), dt=2), [make(held=(Z,), dt=2) for _ in range(3)])
        self.assertEqual(quick[1][0].phase, 1)
        self.assertEqual(quick[1][0].anim_index, 1)
        self.assertEqual(quick[2][0].phase, 2)
        self.assertEqual(quick[2][0].anim_index, 0x116)
        self.assertEqual(quick[3][0].phase, 1)
        self.assertEqual(quick[3][0].anim_index, 0x10C)
        self.assertEqual(quick[3][0].anim_start, C.c_float(0.9999).value)
        self.assertEqual(quick[3][0].playback, 3)
        self.assertEqual(quick[3][0].direction, 1)

    def test_bridge_mask_records_attacks_without_trot_or_eggs(self):
        mask = 0x9DB1
        self.assertEqual(mask & 1, 1)
        self.assertEqual(mask & (1 << 4), 1 << 4)
        self.assertEqual(mask & (1 << 8), 1 << 8)
        self.assertEqual(mask & (1 << 12), 1 << 12)
        self.assertEqual(mask & (1 << 6), 0)
        self.assertEqual(mask & (1 << 16), 0)
        self.assertEqual(mask & (1 << 18), 0)
        lib = self.libs[1]
        ability = dict(can_claw=1, can_roll=1, can_flap_flip=1, can_beak_barge=1)
        self.reset(lib, False)
        self.enter(lib, False, make(held=(Z,), **ability))
        self.step(lib, False, make(held=(Z,), pressed=(B,), **ability))
        self.assertEqual(self.snapshot(lib, False).state, 0x13)
        self.reset(lib, False)
        self.enter(lib, False, make(held=(Z,), **ability))
        self.step(lib, False, make(held=(Z,), pressed=(A,), **ability))
        self.assertEqual(self.snapshot(lib, False).state, 0x12)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(C_LEFT,), **ability)), 7)
        self.assertEqual(self.select(lib, False, make(context=3, provisional=3, held=(Z,), pressed=(C_UP,), **ability)), 7)


if __name__ == '__main__':
    unittest.main()
