"""One-shot completion handoff; original interpreter and paired actor path retained."""
import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.banjo3ds import dialogue_import as imp
from tools.banjo3ds.tests.test_actor_draw import preprocess
from tools.banjo3ds.tests.test_dialogue_preview import FLAGS

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT/'platform/3ds/source/main.c'

class DialogueAutoExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        p = Path(cls.tmp.name)
        (p/'generated_dialogue.h').write_bytes(imp.generate_header(imp.import_resources(
            ROOT/'assets/dialog'/f'{rid:04X}.dialog' for rid in imp.RESOURCE_IDS)))
        (p/'test.c').write_text(r'''
#include <string.h>
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE 1
#include "bottles_dialogue_preview.h"
enum { BOTTLES_WAITING, BOTTLES_EMERGING, BOTTLES_IDLE, BOTTLES_EXITING, BOTTLES_HIDDEN_DONE };
#include "bottles_dialogue_auto_exit.h"
static DaeBridge b;
static DsSequence d;
static int actor, starts;
void reset(void) { b=(DaeBridge){0}; d=(DsSequence){0}; actor=0; starts=0; }
void observe(int status,int state,unsigned selector) { daeObserve(&b,(DsStatus)status,state,selector); }
int request(int state,unsigned selector) { return daeRequest(&b,state,selector); }
void corrupt(void) { b.state=99; }
void start(void) { actor=BOTTLES_IDLE; dsBeginGenerated(&d); daeObserve(&b,d.status,actor,2); }
int frame(double dt,int manual,int prepare_ok) {
 int exitStart=actor==BOTTLES_IDLE && (manual || daeRequest(&b,actor,2));
 if(exitStart && prepare_ok) { actor=BOTTLES_EXITING; ++starts; b.state=DAE_DONE; }
 if(actor>=BOTTLES_EXITING) dsCancel(&d); else dsTick(&d,dt);
 daeObserve(&b,d.status,actor,2);
 return starts;
}
int status(void) { return d.status; }
int visits(void) { return d.visits; }
int final_speech(void) { return d.status==DS_ACTIVE && d.speech.bytes==d.resource->text+d.resource->streams[0].records[5].text_offset; }
int length(void) { return d.speech.length; }
double elapsed(void) { return d.elapsed; }
double duration(void) { return dsDuration(d.speech.length); }
int state(void) { return b.state; }
void fail(void) { dsFinish(&d,DS_FAILED); daeObserve(&b,d.status,actor,2); }
''')
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pedantic','-shared','-fPIC',
            '-I'+str(p),'-I'+str(ROOT/'platform/3ds/source'),str(p/'test.c'),'-o',str(p/'test.so')],check=True)
        cls.lib=C.CDLL(str(p/'test.so'))
        cls.lib.frame.argtypes=[C.c_double,C.c_int,C.c_int]
        cls.lib.elapsed.restype=cls.lib.duration.restype=C.c_double

    def setUp(self): self.lib.reset()
    def complete(self):
        self.lib.start()
        for _ in range(2000):
            self.assertEqual(self.lib.frame(.025,0,1),0)
            if self.lib.status()==2: return
        self.fail('No valid closure')

    def test_boot_and_waiting_do_not_arm(self):
        for _ in range(10):
            self.lib.observe(0,0,2)
            self.assertEqual(self.lib.request(0,2),0)
        self.assertEqual(self.lib.state(),0)
    def test_completed_without_active_interaction_rejected(self):
        self.lib.observe(2,2,2)
        self.assertEqual(self.lib.request(2,2),0)
    def test_all_speeches_finish_and_close_before_request(self):
        self.complete()
        self.assertEqual(self.lib.visits(),13)
        self.assertEqual(self.lib.length(),0)
        self.assertEqual(self.lib.request(2,2),1)
    def test_one_exit_on_next_safe_update(self):
        self.complete()
        for _ in range(20): self.assertEqual(self.lib.frame(.025,0,1),1)
        self.assertEqual(self.lib.status(),2)
    def test_rejected_preparation_retains_same_request(self):
        self.complete()
        for _ in range(4): self.assertEqual(self.lib.frame(.025,0,0),0)
        self.assertEqual(self.lib.state(),2)
        self.assertEqual(self.lib.frame(.025,0,1),1)
    def test_repeated_completed_observations_do_not_rearm(self):
        self.complete(); self.lib.frame(.025,0,1)
        for _ in range(10): self.lib.observe(2,2,2)
        self.assertEqual(self.lib.request(2,2),0)
    def test_canceled_and_failed_terminal(self):
        for terminal in (3,4):
            self.lib.reset(); self.lib.observe(1,2,2); self.lib.observe(terminal,2,2)
            self.lib.observe(2,2,2)
            self.assertEqual(self.lib.request(2,2),0)
    def test_select_cancels_active_sequence(self):
        self.lib.start()
        self.assertEqual(self.lib.frame(.025,1,1),1)
        self.assertEqual(self.lib.status(),3)
        for _ in range(2000): self.assertEqual(self.lib.frame(.025,0,1),1)
    def test_select_wins_on_final_duration_frame(self):
        self.lib.start()
        for _ in range(2000):
            if self.lib.final_speech() and self.lib.elapsed()+.025>=self.lib.duration(): break
            self.lib.frame(.025,0,1)
        else: self.fail('Final speech boundary not found')
        self.assertEqual(self.lib.frame(.025,1,1),1)
        self.assertEqual(self.lib.status(),3)
    def test_select_and_pending_completion_coalesce(self):
        self.complete()
        self.assertEqual(self.lib.frame(.025,1,1),1)
        self.assertEqual(self.lib.frame(.025,1,1),1)
        self.assertEqual(self.lib.status(),2)
    def test_emergence_pending_waits_for_idle(self):
        self.lib.observe(1,1,2); self.lib.observe(2,1,2)
        self.assertEqual(self.lib.request(1,2),0)
        self.assertEqual(self.lib.request(2,2),1)
    def test_unrelated_selector_and_invalid_actor_fail_closed(self):
        for actor,selector in ((2,8),(0,2),(3,2),(4,2),(-1,2),(99,2)):
            self.lib.reset(); self.lib.observe(1,2,2); self.lib.observe(2,2,2)
            self.assertEqual(self.lib.request(actor,selector),0)
            self.assertEqual(self.lib.request(2,2),0)
    def test_invalid_bridge_and_status_fail_closed(self):
        self.lib.corrupt(); self.assertEqual(self.lib.request(2,2),0)
        for status in (-1,99):
            self.lib.reset(); self.lib.observe(status,2,2)
            self.assertEqual(self.lib.request(2,2),0)
    def test_feature_defaults_and_dependencies(self):
        flags=dict(FLAGS,BOTTLES_DIALOGUE_PREVIEW=1,BOTTLES_DIALOGUE_SEQUENCE=1)
        off=preprocess(MAIN.read_text(),**flags)
        self.assertEqual(off.returncode,0,off.stderr); self.assertNotIn('daeRequest',off.stdout)
        on=preprocess(MAIN.read_text(),**flags,BOTTLES_DIALOGUE_AUTO_EXIT=1)
        self.assertEqual(on.returncode,0,on.stderr); self.assertIn('daeRequest',on.stdout)
        for dependency in ('BOTTLES_DIALOGUE_PREVIEW','BOTTLES_DIALOGUE_SEQUENCE','BOTTLES_EXIT'):
            bad=dict(flags, BOTTLES_DIALOGUE_AUTO_EXIT=1); bad[dependency]=0
            self.assertNotEqual(preprocess(MAIN.read_text(),**bad).returncode,0)
    def test_safe_existing_route_and_no_new_ownership(self):
        s=MAIN.read_text(); loop=s[s.index('while (aptMainLoop())'):]
        self.assertLess(loop.index('daeRequest('),loop.index('bottlesExitPrepare(dt, exitStart)'))
        self.assertLess(loop.index('bottlesExitPrepare(dt, exitStart)'),loop.index('C3D_FrameBegin('))
        self.assertLess(loop.index('bottlesExitPublish()'),loop.index('daeObserve('))
        self.assertIn('hillOpenManualPressed && hillOpenInRange()',loop)
        h=(ROOT/'platform/3ds/source/bottles_dialogue_auto_exit.h').read_text()
        for token in ('KEY_', 'C3D_', 'GSPGPU_', 'player', 'camera', 'actor_pose_'):
            self.assertNotIn(token,h.replace('input or player state','input state'))
