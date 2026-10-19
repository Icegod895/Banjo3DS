"""Bounded DF4 subset; diagnostic automatic timing, no input/actor ownership."""
import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds import dialogue_import as imp
from tools.banjo3ds.tests.test_actor_draw import preprocess, function
from tools.banjo3ds.tests.test_dialogue_preview import FLAGS

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT/'platform/3ds/source/main.c'


class DialogueSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        p = Path(cls.tmp.name)
        resources = imp.import_resources(ROOT/'assets/dialog'/f'{rid:04X}.dialog' for rid in imp.RESOURCE_IDS)
        cls.df4 = next(r for r in resources if r.resource_id == 0xDF4)
        cls.expected = [cls.df4.streams[s][i] for s,i in [(1,0),(0,1),(1,2),(0,3),(1,4),(0,5)]]
        (p/'generated_dialogue.h').write_bytes(imp.generate_header(resources))
        source = r'''
#include <string.h>
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE 1
#include "bottles_dialogue_preview.h"
static DsSequence seq;
static DpPreview observer;
void reset(void) { seq = (DsSequence){0}; observer = (DpPreview){0}; }
int start(void) { return dsBeginGenerated(&seq); }
int next(void) { return dsNext(&seq); }
int tick(double dt) { return dsTick(&seq, dt); }
int cancel(void) { return dsCancel(&seq); }
int status(void) { return seq.status; }
int visits(void) { return seq.visits; }
int index_at(int s) { return seq.index[s]; }
int closed_at(int s) { return seq.closed[s]; }
int speaker(void) { return seq.speech.speaker; }
int length(void) { return seq.speech.length; }
int lines(void) { return seq.layout.count; }
const unsigned char *payload(void) { return seq.speech.bytes; }
const char *label(void) { return dsSpeakerLabel(seq.speech.speaker); }
double duration(void) { return dsDuration(seq.speech.length); }
double elapsed(void) { return seq.elapsed; }
int line_offset(int i) { return seq.layout.offset[i]; }
int line_length(int i) { return seq.layout.length[i]; }
int frame(int emerging, int idle, int exiting, float phase, double dt) {
 int activation = dpObserve(&observer, emerging, idle, exiting, phase);
 if (exiting) return dsCancel(&seq);
 if (activation && observer.active) return dsBeginGenerated(&seq);
 return dsTick(&seq, dt);
}
int invalid_state(int which) {
 dsBeginGenerated(&seq);
 switch(which) {
 case 0: seq.stream=2; break;
 case 1: seq.index[0]=8; break;
 case 2: seq.visits=33; break;
 case 3: seq.closed[0]=true; break;
 }
 return dsNext(&seq);
}
int bad_resource(int which) {
 BanjoDialogueResource r = banjo_dialogue_resources[1];
 BanjoDialogueRecord bottom[7], top[6]; unsigned char text[320];
 memcpy(bottom,r.streams[0].records,sizeof bottom); memcpy(top,r.streams[1].records,sizeof top);
 memcpy(text,r.text,sizeof text); r.text=text; r.streams[0].records=bottom; r.streams[1].records=top;
 size_t cap[2]={7,6};
 switch(which) {
 case 0: bottom[1].opcode=7; break;
 case 1: r.streams[1].identity=2; break;
 case 2: bottom[1].text_offset=321; break;
 case 3: bottom[1].text_length=65535; break;
 case 4: bottom[1].speaker=0; break;
 case 5: bottom[1].portrait=12; break;
 case 6: bottom[0].text_length=1; break;
 case 7: r.streams[0].count=8; break;
 case 8: r.text_length=321; break;
 case 9: text[bottom[5].text_offset]=27; break;
 case 10: bottom[6].opcode=6; break;
 case 11: r.resource_id=0xDF5; break;
 case 12: r.streams[0].records=NULL; break;
 case 13: cap[0]=0; break;
 case 14: top[1].opcode=4; break;
 }
 return dsBegin(&seq,&r,sizeof text,cap);
}
int wrap_bytes(const unsigned char *bytes, size_t count, unsigned char *out, size_t capacity) {
 DsLayout layout;
 if (!dsWrap(bytes,count,&layout) || capacity < count) return -1;
 size_t n=0;
 for(unsigned i=0;i<layout.count;i++) {
  if(layout.length[i]>36 || layout.offset[i]!=n) return -2;
  memcpy(out+n,bytes+layout.offset[i],layout.length[i]); n+=layout.length[i];
 }
 return n==count ? layout.count : -3;
}
int clear_area(unsigned short *pixels, size_t count) { return dsClearTextArea(pixels,count); }
'''
        (p/'test.c').write_text(source)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',
                        '-I'+str(p),'-I'+str(ROOT/'platform/3ds/source'),str(p/'test.c'),'-o',str(p/'test.so')],
                        check=True,capture_output=True)
        cls.lib=C.CDLL(str(p/'test.so'))
        cls.lib.tick.argtypes=[C.c_double]
        cls.lib.duration.restype=cls.lib.elapsed.restype=C.c_double
        cls.lib.payload.restype=C.POINTER(C.c_ubyte)
        cls.lib.label.restype=C.c_char_p
        cls.lib.frame.argtypes=[C.c_int,C.c_int,C.c_int,C.c_float,C.c_double]
        cls.lib.wrap_bytes.argtypes=[C.c_char_p,C.c_size_t,C.POINTER(C.c_ubyte),C.c_size_t]
        cls.lib.clear_area.argtypes=[C.POINTER(C.c_uint16),C.c_size_t]

    def setUp(self):
        self.lib.reset()

    def test_six_speeches_exact_order_bytes_labels_and_closure(self):
        self.assertEqual(self.lib.start(),1)
        labels=[b'BANJO',b'BOTTLES',b'KAZOOIE',b'BOTTLES',b'KAZOOIE',b'BOTTLES']
        for i,rec in enumerate(self.expected):
            with self.subTest(speech=i+1):
                self.assertEqual(self.lib.status(),1)
                self.assertEqual(self.lib.speaker(),rec.speaker)
                self.assertEqual(self.lib.label(),labels[i])
                self.assertEqual(C.string_at(self.lib.payload(),self.lib.length()),rec.payload)
                pieces=[]
                for line in range(self.lib.lines()):
                    off,n=self.lib.line_offset(line),self.lib.line_length(line)
                    self.assertLessEqual(n,36)
                    pieces.append(rec.payload[off:off+n])
                self.assertEqual(b''.join(pieces),rec.payload)
                self.assertLessEqual(self.lib.lines(),8)
            self.assertEqual(self.lib.next(),1)
        self.assertEqual(self.lib.status(),2)
        self.assertEqual(self.lib.visits(),13)
        self.assertEqual([self.lib.index_at(i) for i in range(2)],[7,6])
        self.assertEqual([self.lib.closed_at(i) for i in range(2)],[1,1])
        self.assertEqual(self.lib.length(),0)

    def test_completed_terminal_no_extra_speech_or_completion(self):
        self.lib.start()
        for _ in range(6): self.lib.next()
        for _ in range(3):
            self.assertEqual(self.lib.next(),0)
            self.assertEqual(self.lib.tick(10),0)
            self.assertEqual(self.lib.start(),0)
            self.assertEqual(self.lib.cancel(),0)
            self.assertEqual(self.lib.status(),2)

    def test_automatic_progress_without_buttons(self):
        self.lib.start()
        changes=0
        for _ in range(1500): changes+=self.lib.tick(0.025)
        self.assertEqual(changes,6)
        self.assertEqual(self.lib.status(),2)

    def test_timing_seconds_not_idle_direction_or_frame_count(self):
        for dt in (1/60,1/30,0.1):
            self.lib.reset();self.lib.start();seconds=0
            while self.lib.visits()==2:
                self.lib.tick(dt);seconds+=dt
                self.assertLess(seconds,4)
            self.assertGreaterEqual(seconds,3.14-1e-8)
            self.assertLessEqual(seconds,3.14+dt+1e-8)

    def test_diagnostic_duration_constants(self):
        self.lib.start()
        for rec in self.expected:
            self.assertAlmostEqual(self.lib.duration(),max(3,min(9,2+0.06*len(rec.payload))))
            self.lib.next()

    def test_hitch_does_not_skip_entries(self):
        self.lib.start()
        self.assertEqual(self.lib.tick(100),0)
        self.assertAlmostEqual(self.lib.elapsed(),0.25)
        self.assertEqual(self.lib.visits(),2)

    def test_invalid_delta_does_not_advance(self):
        self.lib.start()
        for dt in (float('nan'),float('inf'),-1): self.assertEqual(self.lib.tick(dt),0)
        self.assertEqual(self.lib.elapsed(),0)

    def test_select_cancellation_during_every_speech_is_terminal(self):
        for entry in range(6):
            self.lib.reset();self.lib.start()
            for _ in range(entry): self.lib.next()
            self.assertEqual(self.lib.cancel(),1)
            self.assertEqual(self.lib.status(),3)
            self.assertEqual(self.lib.length(),0)
            self.assertEqual(self.lib.cancel(),0)
            self.assertEqual(self.lib.start(),0)
            self.assertEqual(self.lib.tick(1),0)

    def test_no_premature_start_and_one_shot_observer(self):
        for args in [(0,0,0,0),(0,1,0,1),(1,0,0,0),(1,0,0,0.349)]:
            self.assertEqual(self.lib.frame(*args,0.1),0)
        self.assertEqual(self.lib.status(),0)
        self.assertEqual(self.lib.frame(1,0,0,0.35,0.1),1)
        self.assertEqual(self.lib.elapsed(),0)
        self.assertEqual(self.lib.frame(1,0,0,0.35,0.1),0)
        self.assertAlmostEqual(self.lib.elapsed(),0.1)
        self.assertEqual(self.lib.frame(0,0,1,1,0.1),1)
        self.assertEqual(self.lib.frame(1,0,0,0.35,0.1),0)
        self.assertEqual(self.lib.status(),3)

    def test_cancel_before_activation(self):
        self.assertEqual(self.lib.cancel(),0)
        self.assertEqual(self.lib.frame(1,0,0,0.4,0.1),0)
        self.assertEqual(self.lib.status(),3)

    def test_malformed_data_fails_terminal_without_partial_speech(self):
        for case in range(15):
            with self.subTest(case=case):
                self.lib.reset();self.lib.bad_resource(case)
                self.assertEqual(self.lib.status(),4)
                self.assertEqual(self.lib.length(),0)
                self.assertEqual(self.lib.next(),0)

    def test_corrupt_cursor_and_visit_budget_fail_closed(self):
        for case in range(4):
            self.lib.reset();self.lib.invalid_state(case)
            self.assertEqual(self.lib.status(),4)
            self.assertEqual(self.lib.length(),0)

    def test_wrapping_bytes_bounds_and_no_truncation(self):
        for text in [r.payload for r in self.expected]+[b'x'*254,b'a b '*50,b'X'*36+b' Y']:
            out=(C.c_ubyte*260)(*([0xA5]*260))
            lines=self.lib.wrap_bytes(text,len(text),out,254)
            self.assertGreater(lines,0)
            self.assertLessEqual(lines,8)
            self.assertEqual(bytes(out[:len(text)]),text)
            self.assertEqual(bytes(out[len(text):]),b'\xA5'*(260-len(text)))
        for text in (b'x'*255,b'X\nY',b'X\0Y',b'X\xffY',b''):
            out=(C.c_ubyte*260)(*([0xA5]*260))
            self.assertEqual(self.lib.wrap_bytes(text,len(text),out,254),-1)
            self.assertEqual(bytes(out),b'\xA5'*260)

    def test_partial_framebuffer_clear_bounds(self):
        size=320*240
        pixels=(C.c_uint16*(size+2))(*([0xA55A]*(size+2)))
        ptr=C.cast(C.byref(pixels,2),C.POINTER(C.c_uint16))
        self.assertEqual(self.lib.clear_area(ptr,size-1),0)
        self.assertTrue(all(x==0xA55A for x in pixels))
        self.assertEqual(self.lib.clear_area(ptr,size),1)
        self.assertEqual(pixels[0],0xA55A);self.assertEqual(pixels[-1],0xA55A)
        for x in range(320):
            self.assertTrue(all(pixels[1+x*240+y]==0xA55A for y in range(144)))
            self.assertTrue(all(pixels[1+x*240+y]==0 for y in range(144,240)))

    def test_feature_gates_no_new_input_or_actor_mutation(self):
        text=MAIN.read_text()
        off=preprocess(text,**FLAGS,BOTTLES_DIALOGUE_PREVIEW=1)
        self.assertEqual(off.returncode,0,off.stderr)
        self.assertNotIn('dialogueSequence',off.stdout)
        on=preprocess(text,**FLAGS,BOTTLES_DIALOGUE_PREVIEW=1,BOTTLES_DIALOGUE_SEQUENCE=1)
        self.assertEqual(on.returncode,0,on.stderr)
        self.assertIn('dsTick(&dialogueSequence, dt)',on.stdout)
        missing=preprocess(text,**FLAGS,BOTTLES_DIALOGUE_SEQUENCE=1)
        self.assertNotEqual(missing.returncode,0)
        observer=text[text.index('bool activation = dpObserve'):text.index('/* CPU pose evaluation')]
        for forbidden in ('KEY_A','KEY_B','held','controls','playerInput','bottlesExitPrepare'):
            self.assertNotIn(forbidden,observer)
        self.assertNotRegex(observer,r'bottlesEmergence(?:State|Phase)\s*=(?!=)')
        body=function(text,'dialoguePreviewPresent')
        for forbidden in ('C3D_', 'gfxSwap', 'gfxFlush', 'consoleClear(', r'\n'):
            self.assertNotIn(forbidden,body)
        self.assertIn('if (textChanged) dialoguePreviewPresent();',observer)
        self.assertIn('BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE ?= 0',(ROOT/'platform/3ds/Makefile').read_text())


if __name__=='__main__': unittest.main()
