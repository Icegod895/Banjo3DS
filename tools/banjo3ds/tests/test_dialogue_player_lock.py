"""Native rest adaptation: real input mapping, one-shot policy and live collision path."""
import ctypes as C
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
import test_player_input as inputs
import test_camera_runtime as runtime
from tools.banjo3ds import dialogue_import as imp
from tools.banjo3ds.tests.test_actor_draw import preprocess
from tools.banjo3ds.tests.test_dialogue_preview import FLAGS


def library(owner):
    tmp=tempfile.TemporaryDirectory();owner.addClassCleanup(tmp.cleanup);p=Path(tmp.name)
    (p/'generated_dialogue.h').write_bytes(imp.generate_header(imp.import_resources(
        ROOT/'assets/dialog'/f'{rid:04X}.dialog' for rid in imp.RESOURCE_IDS)))
    (p/'test.c').write_text(r'''
#include <string.h>
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE 1
#include "bottles_dialogue_preview.h"
enum { BOTTLES_WAITING, BOTTLES_EMERGING, BOTTLES_IDLE, BOTTLES_EXITING, BOTTLES_HIDDEN_DONE };
#include "bottles_dialogue_player_lock.h"
static DplLock lock;
static PlayerInputState input;
static PlayerInputFrame frame;
void reset(void) { lock=(DplLock){0};input=(PlayerInputState){0};frame=(PlayerInputFrame){0}; }
int begin(int accepted,int actor,unsigned selector) { return dplBegin(&lock,accepted,actor,selector); }
void release(void) { dplRelease(&lock); }
void abort_start(void) { dplAbortStart(&lock); }
void observe(int status,int actor) { dplObserve(&lock,(DsStatus)status,actor); }
int state(void) { return lock.state; }
void sample(unsigned physical,int x,int y) {
 frame=playerInputUpdate(&input,physical,x,y);
 dplFilter(&lock,&frame);
}
unsigned held(void) { return frame.held; }
unsigned pressed(void) { return frame.pressed; }
unsigned manual(void) { return frame.manual; }
unsigned history(void) { return input.held; }
int jump(void) { return frame.jump_pressed; }
int suppressed(void) { return frame.suppress_movement; }
void rest(BanjoHorizontal *h) { dplRest(h); }
''')
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
        '-I'+str(p),'-I'+str(ROOT/'platform/3ds/source'),'-I'+str(ROOT/'tools/banjo3ds/horizontal'),
        '-I/opt/devkitpro/libctru/include',str(p/'test.c'),str(ROOT/'platform/3ds/source/player_input.c'),
        '-o',str(p/'test.so')],check=True)
    lib=C.CDLL(str(p/'test.so'));lib.rest.argtypes=[C.c_void_p]
    return lib

class DialoguePlayerLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.lib=library(cls)
    def setUp(self): self.lib.reset()
    def lock(self): self.assertEqual(self.lib.begin(1,0,2),1)
    def test_no_boot_proximity_or_rejected_press_lock(self):
        self.lib.observe(0,0)
        for _ in range(5): self.assertEqual(self.lib.begin(0,0,2),0)
        self.assertEqual(self.lib.state(),0)
    def test_only_accepted_initial_selector_two(self):
        for actor,sel in [(0,8),(1,2),(2,2),(3,2),(4,2),(-1,2),(99,2)]:
            self.assertEqual(self.lib.begin(1,actor,sel),0)
        self.lock();self.assertEqual(self.lib.begin(1,0,2),0)
    def test_all_buttons_and_camera_chords_suppressed(self):
        self.lock()
        for key in [inputs.A,inputs.B,inputs.L,inputs.X,inputs.R|inputs.B,inputs.R|inputs.X,
                    inputs.UP,inputs.DOWN,inputs.LEFT,inputs.RIGHT,inputs.A|inputs.L|inputs.B]:
            self.lib.sample(key,60,60)
            self.assertEqual((self.lib.held(),self.lib.pressed(),self.lib.manual(),self.lib.jump()),(0,0,0,0))
            self.assertEqual(self.lib.suppressed(),1)
    def test_physical_history_continues(self):
        self.lock();self.lib.sample(inputs.A,0,0)
        self.assertEqual(self.lib.history(),inputs.NA)
        self.lib.sample(0,0,0);self.assertEqual(self.lib.history(),0)
    def test_a_held_across_unlock_requires_release(self):
        self.lock();self.lib.sample(inputs.A,0,0);self.lib.release()
        for _ in range(5):
            self.lib.sample(inputs.A,0,0);self.assertEqual(self.lib.jump(),0);self.assertEqual(self.lib.held(),0)
        self.lib.sample(0,0,0);self.lib.sample(inputs.A,0,0)
        self.assertEqual(self.lib.jump(),1)
    def test_downstream_held_edges_quarantined(self):
        for physical in (inputs.B,inputs.L,inputs.UP,inputs.X,inputs.R|inputs.B):
            self.lib.reset();self.lock();self.lib.sample(physical,0,0);self.lib.release()
            for _ in range(3):
                self.lib.sample(physical,0,0);self.assertEqual(self.lib.held(),0)
            self.lib.sample(0,0,0);self.lib.sample(physical,0,0)
            self.assertNotEqual(self.lib.held(),0)
    def test_cstick_held_across_unlock_no_fresh_camera_entry(self):
        self.lock();self.lib.sample(0,0,60);self.lib.release()
        self.lib.sample(0,0,60);self.assertEqual(self.lib.held(),0)
        self.lib.sample(0,0,0);self.lib.sample(0,0,60)
        self.assertEqual(self.lib.held(),inputs.CU)
    def test_r_b_modifier_release_does_not_create_b(self):
        self.lock();self.lib.sample(inputs.R|inputs.B,0,0);self.lib.release()
        self.lib.sample(inputs.B,0,0);self.assertEqual(self.lib.held(),0)
        self.lib.sample(0,0,0);self.lib.sample(inputs.B,0,0)
        self.assertEqual(self.lib.pressed(),inputs.NB)
    def test_suppressed_press_and_release_not_buffered(self):
        self.lock();self.lib.sample(inputs.A|inputs.B,0,0);self.lib.sample(0,0,0)
        self.lib.release();self.lib.sample(0,0,0)
        self.assertEqual((self.lib.jump(),self.lib.pressed()),(0,0))
    def test_completed_and_exit_retry_retain_lock(self):
        self.lock()
        for _ in range(5): self.lib.observe(2,2);self.assertEqual(self.lib.state(),1)
        self.lib.release();self.assertEqual(self.lib.state(),2)
    def test_select_emergence_or_rejected_select_do_not_release(self):
        self.lock()
        for actor in (1,2): self.lib.observe(1,actor);self.assertEqual(self.lib.state(),1)
    def test_accepted_exit_releases_once_and_never_relocks(self):
        self.lock();self.lib.release();self.lib.release()
        self.assertEqual(self.lib.state(),2);self.assertEqual(self.lib.begin(1,0,2),0)
    def test_failure_and_invalid_state_release_without_actor_mutation(self):
        for dialogue,actor in [(0,2),(3,2),(4,2),(99,2),(-1,2),(1,99),(1,-1),(1,0),(2,3),(2,4)]:
            self.lib.reset();self.lock();self.lib.observe(dialogue,actor)
            self.assertEqual(self.lib.state(),2);self.assertEqual(self.lib.begin(1,0,2),0)
    def test_emergence_prepare_failure_allows_fresh_retry(self):
        self.lock();self.lib.abort_start();self.assertEqual(self.lib.state(),0);self.lock()
    def test_normal_input_without_lock_unchanged(self):
        self.lib.sample(inputs.A,0,0);self.assertEqual(self.lib.jump(),1)
        self.lib.sample(inputs.R|inputs.B,0,0);self.assertEqual(self.lib.manual(),inputs.CD)
    def test_default_off_and_all_dependencies(self):
        s=(ROOT/'platform/3ds/source/main.c').read_text()
        flags=dict(FLAGS,BOTTLES_DIALOGUE_PREVIEW=1,BOTTLES_DIALOGUE_SEQUENCE=1,BOTTLES_DIALOGUE_AUTO_EXIT=1)
        off=preprocess(s,**flags);self.assertEqual(off.returncode,0,off.stderr);self.assertNotIn('dplFilter',off.stdout)
        on=preprocess(s,**flags,BOTTLES_DIALOGUE_PLAYER_LOCK=1)
        self.assertEqual(on.returncode,0,on.stderr);self.assertIn('dplFilter',on.stdout)
        for dep in ('BOTTLES_B_INTERACTION','BOTTLES_DIALOGUE_PREVIEW','BOTTLES_DIALOGUE_SEQUENCE','BOTTLES_DIALOGUE_AUTO_EXIT'):
            f=dict(flags,BOTTLES_DIALOGUE_PLAYER_LOCK=1);f[dep]=0
            self.assertNotEqual(preprocess(s,**f).returncode,0)
    def test_actual_boundaries_and_preserved_select(self):
        s=(ROOT/'platform/3ds/source/main.c').read_text();loop=s[s.index('while (aptMainLoop())'):]
        tokens=['hidScanInput();','playerInputUpdate(','bottlesBPrepareInput(','dplFilter(',
                'cameraRuntimeManualInput(','cameraRuntimeFirstPersonInput(','playerCrouchFrame(',
                'cameraRuntimeMove(','bottlesExitPrepare(dt, exitStart)','C3D_FrameBegin(']
        offsets=[loop.index(t) for t in tokens];self.assertEqual(offsets,sorted(offsets))
        self.assertIn('if (exitReady) dplRelease(&dialoguePlayerLock);',loop)
        self.assertIn('hillOpenManualPressed && hillOpenInRange()',loop)
        self.assertIn('bottlesEmergenceState == BOTTLES_IDLE &&',loop)
        self.assertIn('if (dialoguePlayerLock.state == DPL_LOCKED) pad.dx = pad.dy = 0;',loop)
        self.assertIn('if (!dialoguePreviewValid) dplRelease',loop)
        header=(ROOT/'platform/3ds/source/bottles_dialogue_player_lock.h').read_text()
        for forbidden in ('actor.x','actor.y','actor.z','verticalVelocity','grounded =','C3D_','GSPGPU_', 'dsTick(', 'actor_pose_'):
            self.assertNotIn(forbidden,header)

class DialogueLockMovementTests(unittest.TestCase):
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move
    @classmethod
    def setUpClass(cls):
        runtime.CameraRuntimeTests.setUpClass.__func__(cls)
        cls.policy=library(cls)
    def test_real_collision_simulation_and_control_resume_O0_O2(self):
        for lib in self.libs:
            s,p=self.start(lib)
            for _ in range(8): self.assertEqual(self.move(lib,s,p),1)
            # Native allowlist permits moving gaits: seed genuine existing momentum.
            p.horizontalInitialized=True;p.horizontal.velocity[:]=(200,300)
            p.horizontal.speed=400;p.horizontal.target[:]=(200,300)
            p.horizontal.magnitude=1;p.locomotion.gait=3
            before=(p.motion.actor.x,p.motion.actor.y,p.motion.actor.z,p.motion.vy,p.motion.grounded)
            self.policy.rest(C.byref(p.horizontal))
            self.assertEqual(before,(p.motion.actor.x,p.motion.actor.y,p.motion.actor.z,p.motion.vy,p.motion.grounded))
            x,z=p.motion.actor.x,p.motion.actor.z;frame=s.bridge.frame
            self.policy.reset();self.policy.begin(1,0,2)
            for _ in range(90):
                self.policy.sample(inputs.A|inputs.B|inputs.L|inputs.R,60,60)
                lib.cameraRuntimeManualInput(C.byref(s),self.policy.manual(),35)
                lib.cameraRuntimeFirstPersonInput(C.byref(s),C.byref(p),0,0,0,1/60,1)
                self.assertEqual(self.move(lib,s,p,jump=bool(self.policy.jump()),orbit=bool(self.policy.suppressed())),1)
                self.assertEqual((p.motion.actor.x,p.motion.actor.z),(x,z))
                self.assertTrue(p.motion.grounded);self.assertEqual(s.calls,1)
            self.assertGreater(s.bridge.frame,frame)
            self.assertEqual(tuple(p.horizontal.velocity),(0,0))
            self.policy.release();self.policy.sample(0,0,0)
            self.assertEqual(self.move(lib,s,p),1)
            self.assertEqual((p.motion.actor.x,p.motion.actor.z),(x,z))
            for _ in range(20): self.assertEqual(self.move(lib,s,p,y=156),1)
            self.assertNotEqual((p.motion.actor.x,p.motion.actor.z),(x,z))
            self.policy.sample(inputs.A,0,0)
            self.assertEqual(self.move(lib,s,p,jump=bool(self.policy.jump())),1)
            self.assertFalse(p.motion.grounded)
