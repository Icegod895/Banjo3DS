"""FIX1 proximity gate around the original one-shot hill runtime, at O0 and O2."""
import ctypes as C
import math

from tools.banjo3ds.tests import test_actor_hill_open as hill_tests
from tools.banjo3ds.tests.test_actor_draw import preprocess


class ActorHillProximityTests(hill_tests.ActorHillOpenTests):
    # Re-run all seven B2-P1 pose, scatter, wait, and clock tests with the gate
    # enabled and already latched, then exercise the waiting/entry state below.
    proximity = True

    def test_waits_at_starting_geometry_while_bottles_idles(self):
        for lib in self.libs:
            lib.arm()
            before=C.string_at(lib.bytes(),2019*24+64)
            for _ in range(700):
                lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0)
            self.assertEqual(lib.phase_get(),0)
            after=C.string_at(lib.bytes(),len(before))
            self.assertEqual(after[32:32+168*24],before[32:32+168*24])
            self.assertNotEqual(after[32+168*24:-32],before[32+168*24:-32])
            self.assertEqual(C.string_at(lib.world_bytes(),2019*24),b'\x5a'*(2019*24))

    def test_enters_once_full_duration_and_no_restart_after_reentry(self):
        for lib in self.libs:
            lib.arm()
            lib.position(2250+400.25,-34,2774)
            lib.frame(.05,1)
            self.assertEqual(lib.triggered(),0)
            lib.position(2250+400,-34,2774)
            lib.frame(.05,1)
            self.assertEqual(lib.triggered(),1)
            self.assertEqual(lib.phase_get(),0)
            for _ in range(89): lib.frame(.05,1)
            self.assertAlmostEqual(lib.phase_get(),4.45/4.5,places=6)
            lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            final=C.string_at(lib.bytes()+32,168*24)
            for xyz in ((2250,-34,2774),(0,1800,0),(2250,-34,2774)):
                lib.position(*xyz)
                for _ in range(100): lib.frame(.05,1)
                self.assertEqual(lib.triggered(),1)
                self.assertEqual(lib.phase_get(),1)
                self.assertEqual(C.string_at(lib.bytes()+32,168*24),final)

    def test_distance_is_three_dimensional_original_world_position(self):
        for lib in self.libs:
            for offset,inside in (((400,0,0),1),((-400,0,0),1),((0,400,0),1),
                                  ((0,0,-400),1),((300,0,300),0),((0,401,0),0),
                                  ((0,0,401),0),((math.nan,0,0),0),
                                  ((0,math.inf,0),0),((1e30,0,0),0)):
                lib.arm()
                lib.position(2250+offset[0],-34+offset[1],2774+offset[2])
                self.assertEqual(lib.prepare(.05),1)
                self.assertEqual(lib.triggered(),inside,offset)
                self.assertEqual(lib.phase_get(),0)
            # Actual render/runtime position is read after movement, with no
            # camera, local-space vertex, button, or selector dispatch input.
        loop=self.active[self.active.index('while (aptMainLoop())'):]
        self.assertLess(loop.index('cameraRuntimeMove('),loop.index('hillOpenPrepare(dt)'))
        check=self.active.split('static bool hillOpenInRange(void)',1)[1].split('static float hillOpenBones',1)[0]
        for axis in 'xyz': self.assertIn('player.motion.actor.'+axis,check)
        self.assertIn('#define ACTOR_HILL_PROXIMITY_RADIUS 400.0f',self.main)

    def test_leaving_radius_does_not_pause_or_reset(self):
        for lib in self.libs:
            lib.arm();lib.position(2250,-34,2774);lib.frame(.016,1)
            lib.position(0,1800,0)
            for _ in range(90): lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            self.assertEqual(lib.triggered(),1)

    def test_rejected_trigger_is_atomic_and_failed_wait_does_not_write(self):
        for lib in self.libs:
            for fault in (1,4):
                lib.arm();lib.position(2250,-34,2774);lib.fault_set(fault)
                before=C.string_at(lib.bytes(),2019*24+64)
                self.assertEqual(lib.prepare(.05),0)
                self.assertEqual(lib.triggered(),0)
                self.assertEqual(lib.phase_get(),0)
                self.assertEqual(lib.flush_count(),0)
                self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.arm();lib.position(2250,-34,2774)
            before=C.string_at(lib.bytes(),2019*24+64)
            lib.frame(.05,0)
            self.assertEqual(lib.triggered(),1)
            self.assertEqual(lib.phase_get(),0)
            self.assertEqual(lib.flush_count(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.frame(.05,1)
            self.assertGreater(lib.phase_get(),0)
            self.assertEqual(lib.flush_count(),2)

    def test_switch_off_has_original_ungated_clock_and_requires_animation(self):
        control=preprocess(self.main,STATIC_BOTTLES=1,IDLE_ANIMATION=1,
                           HILL_OPEN_ANIMATION=1,HILL_PROXIMITY_TRIGGER=0)
        self.assertEqual(control.returncode,0,control.stderr)
        for name in ('hillOpenTriggered','hillOpenInRange'):
            self.assertNotIn(name,control.stdout)
        self.assertIn('double seconds = hillOpenSeconds + (double)dt;',control.stdout)
        invalid=preprocess(self.main,STATIC_BOTTLES=1,IDLE_ANIMATION=1,
                           HILL_OPEN_ANIMATION=0,HILL_PROXIMITY_TRIGGER=1)
        self.assertNotEqual(invalid.returncode,0)
        self.assertIn('requires B2-P1',invalid.stderr)
