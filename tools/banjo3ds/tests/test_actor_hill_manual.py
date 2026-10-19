"""FIX2 explicit SELECT diagnostic, without gameplay-input interception."""
import ctypes as C
import math
import re

from tools.banjo3ds.tests import test_actor_hill_open as hill_tests
from tools.banjo3ds.tests.test_actor_draw import ROOT, preprocess

SELECT = 1 << 2
B = 1 << 1


class ActorHillManualTests(hill_tests.ActorHillOpenTests):
    manual = True

    def test_actual_spawn_distance_and_first_frame_are_outside(self):
        match=re.search(r'static PlayerRuntime player = .*?actor = \{([^}]+)',self.main)
        spawn=[float(v.strip().removesuffix('f')) for v in match[1].split(',')[:3]]
        header=(ROOT/'platform/3ds/build/generated_actors.h').read_text()
        hill=[float(re.search(r'#define ACTOR_PLACE_'+axis+r' ([^\n]+)',header)[1].strip('()f')) for axis in 'XYZ']
        self.assertEqual(spawn,[0,1800,0]);self.assertEqual(hill,[2250,-34,2774])
        squared=sum((a-b)**2 for a,b in zip(spawn,hill))
        self.assertEqual(squared,16121132)
        self.assertAlmostEqual(math.sqrt(squared),4015.112949843379)
        for lib in self.libs:
            lib.arm();lib.position(*spawn);lib.keys(SELECT);lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0);self.assertEqual(lib.phase_get(),0)

    def test_no_auto_playback_or_queued_press_and_B_does_not_trigger(self):
        for lib in self.libs:
            lib.arm();lib.keys(SELECT);lib.frame(.05,1)
            lib.position(2250,-34,2774)
            before=C.string_at(lib.bytes()+32,168*24)
            for _ in range(700):lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0);self.assertEqual(lib.phase_get(),0)
            self.assertEqual(C.string_at(lib.bytes()+32,168*24),before)
            lib.keys(B);lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0)
            lib.keys(0);lib.frame(.05,1)
            lib.keys(SELECT);lib.frame(.05,1)
            self.assertEqual(lib.triggered(),1);self.assertEqual(lib.phase_get(),0)

    def test_manual_phase_zero_full_duration_final_hold_and_idle_independence(self):
        for lib in self.libs:
            lib.arm();lib.position(2250,-34,2774)
            for _ in range(120):lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),0);self.assertNotEqual(lib.bottles_phase(),0)
            before=C.string_at(lib.bytes()+32,168*24)
            lib.keys(SELECT);lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),0)
            self.assertEqual(C.string_at(lib.bytes()+32,168*24),before)
            for _ in range(30):lib.frame(.05,1)
            self.assertNotEqual(C.string_at(lib.bytes()+32,168*24),before)
            lib.position(0,1800,0)
            for _ in range(59):lib.frame(.05,1)
            self.assertAlmostEqual(lib.phase_get(),4.45/4.5,places=6)
            lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            self.assertEqual(C.string_at(lib.bytes()+32,168*24),before)
            bottles=lib.bottles_phase()
            for _ in range(100):
                lib.position(2250,-34,2774);lib.keys(0);lib.frame(.05,1)
                lib.keys(SELECT);lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            self.assertEqual(C.string_at(lib.bytes()+32,168*24),before)
            self.assertNotEqual(lib.bottles_phase(),bottles)

    def test_radius_and_failed_prepare_do_not_latch(self):
        for lib in self.libs:
            for xyz,expected in (((2650,-34,2774),1),((2650.25,-34,2774),0),
                                  ((2250,367,2774),0),((math.nan,-34,2774),0)):
                lib.arm();lib.position(*xyz);lib.keys(SELECT);lib.frame(.05,1)
                self.assertEqual(lib.triggered(),expected)
                self.assertEqual(lib.phase_get(),0)
            lib.arm();lib.position(2250,-34,2774);lib.fault_set(1)
            before=C.string_at(lib.bytes(),2019*24+64)
            lib.keys(SELECT);lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0);self.assertEqual(lib.flush_count(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.fault_set(0);lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0)  # held key cannot replay rejected edge

    def test_manual_trigger_preserves_gpu_wait_and_catches_up(self):
        for lib in self.libs:
            lib.arm();lib.position(2250,-34,2774);lib.keys(SELECT)
            before=C.string_at(lib.bytes(),2019*24+64)
            lib.frame(.05,0)
            self.assertEqual(lib.triggered(),1);self.assertEqual(lib.phase_get(),0)
            self.assertEqual(lib.flush_count(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.frame(.05,1)
            self.assertGreater(lib.phase_get(),0);self.assertEqual(lib.flush_count(),2)

    def test_switches_and_readonly_physical_edge_input(self):
        flags=dict(STATIC_BOTTLES=1,IDLE_ANIMATION=1,HILL_OPEN_ANIMATION=1,HILL_MANUAL_TRIGGER=1)
        self.assertNotEqual(preprocess(self.main,**dict(flags,HILL_PROXIMITY_TRIGGER=1)).returncode,0)
        self.assertNotEqual(preprocess(self.main,**dict(flags,HILL_OPEN_ANIMATION=0)).returncode,0)
        fix1=preprocess(self.main,STATIC_BOTTLES=1,IDLE_ANIMATION=1,
                        HILL_OPEN_ANIMATION=1,HILL_PROXIMITY_TRIGGER=1,HILL_MANUAL_TRIGGER=0)
        self.assertEqual(fix1.returncode,0)
        self.assertNotIn('hillOpenManualPressed',fix1.stdout)
        self.assertIn('bool triggered = hillOpenTriggered || hillOpenInRange();',fix1.stdout)
        loop=self.active[self.active.index('while (aptMainLoop())'):]
        self.assertIn('u32 down = hidKeysDown();',loop)
        self.assertIn('hillOpenManualPressed = (down & KEY_SELECT) != 0;',loop)
        self.assertLess(loop.index('cameraRuntimeMove('),loop.index('hillOpenManualPressed ='))
        self.assertLess(loop.index('hillOpenManualPressed ='),loop.index('hillOpenPrepare(dt)'))
        self.assertNotIn('KEY_SELECT',(ROOT/'platform/3ds/source/player_input.c').read_text())
