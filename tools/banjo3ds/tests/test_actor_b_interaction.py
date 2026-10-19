"""Authorized bounded diagnostic: not a test of complete Rare qualification."""
import ctypes as C
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.banjo3ds.tests import test_actor_emergence as actor_fixture
from tools.banjo3ds.tests import test_player_input as inputs
from tools.banjo3ds.tests.test_actor_draw import ROOT, MAIN, preprocess, function


class BottlesBInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        main=MAIN.read_text();cls.main=main
        helper=function(main.replace('static bool bottlesBPrepareInput','static void bottlesBPrepareInput'),'bottlesBPrepareInput').replace('static void bottlesBPrepareInput','static bool bottlesBPrepareInput')
        defines='\n'.join(re.findall(r'^#define ACTOR_PLACE_[XYZ] .*', (ROOT/'platform/3ds/build/generated_actors.h').read_text(),re.M))
        text='''#include <string.h>
#include <3ds/types.h>
#include <3ds/services/hid.h>
#include "player_runtime.h"
#include "player_crouch.h"
#include "camera_runtime.h"
#include "bottles_b_interaction.h"
#define BANJO_LEARNED_ABILITIES 0x9DB1
static PlayerRuntime player;
static CameraRuntime rareCamera;
static BottlesBInput bottlesBInput;
static int bottlesEmergenceState, requested, crouching, fpActive, fpBlocked, fpCamera;
enum { BOTTLES_WAITING=0 };
int playerCrouchRequested(void) { return requested; }
bool playerCrouchActive(void) { return crouching; }
bool playerRuntimeFirstPersonActive(const PlayerRuntime *p) { (void)p;return fpActive; }
bool playerRuntimeFirstPersonBlocks(const PlayerRuntime *p) { (void)p;return fpBlocked; }
bool cameraRuntimeFirstPersonActive(const CameraRuntime *p) { (void)p;return fpCamera; }
'''+defines+'\n'+helper+'''
static PlayerInputState mapping;
static PlayerInputFrame frame;
static uint32_t previous;
static int accepted;
void reset(void) {
    memset(&player,0,sizeof player); memset(&mapping,0,sizeof mapping);
    bottlesBInput=(BottlesBInput){0};previous=0;accepted=0;
    bottlesEmergenceState=requested=crouching=fpActive=fpBlocked=fpCamera=0;
    player.motion.actor.x=ACTOR_PLACE_X;player.motion.actor.y=ACTOR_PLACE_Y;player.motion.actor.z=ACTOR_PLACE_Z;
    player.motion.grounded=true;player.motion.verticalVelocity=-1;
}
void position(float x,float y,float z,float yaw) { player.motion.actor.x=x;player.motion.actor.y=y;player.motion.actor.z=z;player.motion.actor.yaw=yaw; }
void setting(int key,int value) {
    switch(key) {
    case 0:bottlesEmergenceState=value;break;
    case 1:player.motion.grounded=value!=0;break;
    case 2:player.jumpActive=value!=0;break;
    case 3:player.locomotion.gait=value;break;
    case 4:requested=value;break;
    case 5:crouching=value;break;
    case 6:fpActive=value;break;
    case 7:fpBlocked=value;break;
    case 8:fpCamera=value;break;
    }
}
void velocity(float v) { player.motion.verticalVelocity=v; }
void tick(uint32_t keys,int x,int y) {
    uint32_t down=keys&~previous;previous=keys;
    frame=playerInputUpdate(&mapping,keys,x,y);
    accepted=bottlesBPrepareInput(&frame,keys,down);
}
const PlayerInputFrame *output(void) { return &frame; }
int started(void) { return accepted; }
int reserved(void) { return bottlesBInput.reserved; }
int consumed(void) { return bottlesBInput.consumed; }
int eligible_ability(uint32_t abilities) {
    BottlesBContext c={.x=ACTOR_PLACE_X,.y=ACTOR_PLACE_Y,.z=ACTOR_PLACE_Z,
        .vertical_velocity=-1,.abilities=abilities,.waiting=true,.grounded=true};
    return bottlesBEligible(&c,ACTOR_PLACE_X,ACTOR_PLACE_Y,ACTOR_PLACE_Z);
}
int gameplay_attack(void) {
    CrouchInput in={0}; in.context=BANJO_CROUCH_IDLE;in.prev_state=BANJO_CROUCH_IDLE;
    in.zone=1;in.transformation=1;in.can_claw=1;in.can_roll=1;
    in.release_count[1]=1;
    in.button_count[9]=(frame.pressed & PI_N64_B)?1:((frame.held & PI_N64_B)?2:0);
    return banjo_crouch_select(&in);
}
'''
        cls.libs=[]
        includes=['-I/opt/devkitpro/libctru/include','-I'+str(ROOT/'platform/3ds/source')]
        includes += ['-I'+str(p) for p in (ROOT/'tools/banjo3ds').iterdir() if p.is_dir()]
        for opt in ('-O0','-O2'):
            source=Path(cls.tmp.name)/(opt+'.c');source.write_text(text);out=source.with_suffix('.so')
            subprocess.run(['cc',opt,'-shared','-fPIC','-Wall','-Wextra','-Werror',*includes,str(source),
                str(ROOT/'platform/3ds/source/player_input.c'),str(ROOT/'tools/banjo3ds/crouch/crouch.c'),'-lm','-o',str(out)],check=True,capture_output=True)
            lib=C.CDLL(str(out));lib.position.argtypes=[C.c_float]*4;lib.velocity.argtypes=[C.c_float]
            lib.output.restype=C.POINTER(inputs.Frame);cls.libs.append(lib)

    def setUp(self):
        for lib in self.libs:lib.reset()

    def test_strict_root_3d_radius_and_no_facing(self):
        for lib in self.libs:
            for xyz,want in [((249.99,0,0),1),((250,0,0),0),((0,250,0),0),((0,0,-250),0),((149,199,0),1),((150,200,0),0),((200,200,0),0),((float('nan'),0,0),0)]:
                for yaw in (0,90,180,270):
                    lib.reset();lib.position(2250+xyz[0],-34+xyz[1],2774+xyz[2],yaw);lib.tick(0,0,0)
                    self.assertEqual(lib.reserved(),want)

    def test_ability_stability_and_explicit_locomotion_allowlist(self):
        for lib in self.libs:
            self.assertTrue(lib.eligible_ability(0x9db1));self.assertFalse(lib.eligible_ability(0x9db9))
            for vy,want in ((-1,1),(-.001,1),(0,0),(1,0),(float('nan'),0),(float('-inf'),0)):
                lib.reset();lib.velocity(vy);lib.tick(0,0,0);self.assertEqual(lib.reserved(),want)
            for key,bad in ((0,1),(0,2),(0,3),(0,4),(1,0),(2,1),(3,5),(3,255),(4,7),(4,5),(4,0x2f),(4,0xd),(5,1),(6,1),(7,1),(8,1)):
                lib.reset();lib.setting(key,bad);lib.tick(0,0,0);self.assertFalse(lib.reserved(),(key,bad))
            for gait in range(5):
                for request in (0,1,2,3,4,31):
                    lib.reset();lib.setting(3,gait);lib.setting(4,request);lib.tick(0,0,0);self.assertTrue(lib.reserved())

    def test_previous_reservation_fresh_press_and_gameplay_consumption(self):
        for lib in self.libs:
            lib.tick(inputs.B,0,0) # first eligible frame has no previous reservation
            self.assertFalse(lib.started());self.assertTrue(lib.output().contents.pressed & inputs.NB)
            self.assertEqual(lib.gameplay_attack(),6) # actual crouch selector: claw
            for _ in range(5):lib.tick(inputs.B,0,0);self.assertFalse(lib.started())
            lib.tick(0,0,0);lib.tick(inputs.B,0,0)
            self.assertTrue(lib.started());self.assertTrue(lib.consumed());self.assertFalse(lib.reserved())
            self.assertEqual(lib.output().contents.held & inputs.NB,0)
            self.assertNotEqual(lib.gameplay_attack(),6)

    def test_consumed_through_state_changes_release_no_synthetic_edges(self):
        for lib in self.libs:
            lib.tick(0,0,0);lib.tick(inputs.B,0,0);self.assertTrue(lib.started())
            for state in (1,2,3,4,0):
                lib.setting(0,state)
                for _ in range(5):
                    lib.tick(inputs.B,0,0);f=lib.output().contents
                    self.assertFalse(lib.started());self.assertEqual((f.held|f.pressed|f.released)&inputs.NB,0)
            lib.tick(0,0,0);self.assertFalse(lib.consumed());self.assertFalse(lib.output().contents.released&inputs.NB)
            lib.setting(0,2);lib.tick(inputs.B,0,0)
            self.assertFalse(lib.started());self.assertEqual(lib.output().contents.pressed&inputs.NB,inputs.NB)
            self.assertEqual(lib.gameplay_attack(),6)

    def test_ineligible_b_preserved_and_reservation_cleared(self):
        for lib in self.libs:
            for state in (1,2,3,4):
                lib.reset();lib.tick(0,0,0);lib.setting(0,state);lib.tick(inputs.B,0,0)
                self.assertFalse(lib.started());self.assertFalse(lib.reserved());self.assertEqual(lib.gameplay_attack(),6)
            lib.reset();lib.tick(0,0,0);lib.position(3000,-34,2774,0);lib.tick(inputs.B,0,0)
            self.assertFalse(lib.started());self.assertFalse(lib.reserved());self.assertEqual(lib.gameplay_attack(),6)
            lib.position(2250,-34,2774,0);lib.tick(inputs.B,0,0);self.assertFalse(lib.started())

    def test_chords_and_simultaneous_conflicts_preserved(self):
        for lib in self.libs:
            for key in (inputs.A,inputs.L,inputs.R,inputs.X,inputs.Y,inputs.UP,inputs.DOWN,inputs.LEFT,inputs.RIGHT,inputs.SELECT):
                lib.reset();lib.tick(0,0,0);lib.tick(inputs.B|key,0,0)
                self.assertFalse(lib.started());self.assertFalse(lib.reserved())
                if key==inputs.R:self.assertEqual(lib.output().contents.held,inputs.CD)
                else:self.assertTrue(lib.output().contents.held&inputs.NB)
            lib.reset();lib.tick(0,0,0);lib.tick(inputs.B,40,0);self.assertFalse(lib.started())
            lib.reset();lib.tick(0,0,0);lib.tick(inputs.R|inputs.B,0,0);lib.tick(inputs.B,0,0)
            self.assertFalse(lib.started());self.assertFalse(lib.output().contents.held&inputs.NB)
            lib.tick(0,0,0);lib.tick(inputs.B,0,0);self.assertTrue(lib.started())
            lib.tick(inputs.R|inputs.B,0,0);self.assertEqual(lib.output().contents.held,inputs.CD)
            lib.tick(inputs.B,0,0);self.assertFalse(lib.output().contents.held&inputs.NB)

    def test_actual_main_order_and_off_preprocessing(self):
        flags=dict(STATIC_BOTTLES=1,IDLE_ANIMATION=1,HILL_OPEN_ANIMATION=1,HILL_MANUAL_TRIGGER=1,BOTTLES_EMERGENCE=1,BOTTLES_EXIT=1)
        active=preprocess(self.main,**flags,BOTTLES_B_INTERACTION=1).stdout
        loop=active[active.index('while (aptMainLoop())'):]
        self.assertLess(loop.index('playerInputUpdate'),loop.index('bottlesBPrepareInput'))
        for consumer in ('cameraRuntimeFirstPersonInput','playerCrouchFrame','cameraRuntimeMove('):
            self.assertLess(loop.index('bottlesBPrepareInput'),loop.index(consumer))
        off=preprocess(self.main,**flags).stdout
        self.assertNotIn('bottlesB',off)
        for name in ('hillOpenPublish','bottlesEmergencePrepare','bottlesEmergencePublish','bottlesExitPrepare','bottlesExitPublish','sceneDrawStaticBottles','sceneDrawClosedMolehill'):
            self.assertEqual(function(active.replace('static bool ','static void '),name),function(off.replace('static bool ','static void '),name))
        self.assertNotEqual(preprocess(self.main,**dict(flags,BOTTLES_EXIT=0),BOTTLES_B_INTERACTION=1).returncode,0)


class BottlesBActorTests(unittest.TestCase):
    b_enabled=True
    exit_enabled=True
    proximity=False
    manual=True
    setUpClass=classmethod(actor_fixture.ActorEmergenceTests.setUpClass.__func__)
    tearDownClass=classmethod(actor_fixture.ActorEmergenceTests.tearDownClass.__func__)
    setUp=actor_fixture.ActorEmergenceTests.setUp

    def test_b_event_routes_existing_cycle_select_only_exits(self):
        for lib in self.libs:
            lib.keys(4);lib.frame(.05,1)
            self.assertEqual((lib.state(),lib.visible(),lib.triggered()),(0,0,0))
            lib.release_select();lib.b_event(1)
            # Event was accepted before movement; later actor position must
            # not silently cancel or requalify it using the SELECT radius.
            lib.position(3000,-34,2774);lib.frame(.05,1);lib.b_event(0)
            lib.position(2250,-34,2774)
            self.assertEqual((lib.state(),lib.visible()),(1,1))
            self.assertEqual(lib.phase_get(),0);self.assertAlmostEqual(lib.emerge_phase(),.0001,places=7)
            for _ in range(90):
                lib.release_select();lib.keys(4);lib.b_event(1);lib.frame(.05,1)
            self.assertEqual(lib.state(),1);self.assertEqual(lib.phase_get(),1)
            lib.release_select();lib.frame(.05,1);self.assertEqual(lib.state(),2)
            for _ in range(10):lib.frame(.05,1);self.assertEqual(lib.state(),2)
            lib.keys(4);lib.frame(.05,1);self.assertEqual(lib.state(),3)
            for _ in range(35):
                lib.release_select();lib.keys(4);lib.frame(.05,1)
            self.assertEqual((lib.state(),lib.visible()),(4,0))
            for _ in range(100):lib.frame(.05,1)
            self.assertEqual((lib.state(),lib.visible()),(4,0))
