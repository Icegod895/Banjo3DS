"""Passive preview: original data, bounded selection and read-only actor observation."""
import ctypes
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.tests.test_actor_draw import preprocess, function
from tools.banjo3ds import dialogue_import

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / 'platform/3ds/source/main.c'
FLAGS = dict(BOTTLES_B_INTERACTION=1, BOTTLES_EXIT=1, BOTTLES_EMERGENCE=1,
             HILL_OPEN_ANIMATION=1, HILL_MANUAL_TRIGGER=1, STATIC_BOTTLES=1, IDLE_ANIMATION=1)


class DialoguePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        p = Path(cls.tmp.name)
        assets = ROOT / 'assets/dialog'
        resources = dialogue_import.import_resources(assets / f'{rid:04X}.dialog'
                                                     for rid in dialogue_import.RESOURCE_IDS)
        (p/'generated_dialogue.h').write_bytes(dialogue_import.generate_header(resources))
        source = r'''
#include <string.h>
#include "bottles_dialogue_preview.h"
static DpPreview preview;
int observe(int emerging, int idle, int exiting, float phase) {
 return dpObserve(&preview, emerging, idle, exiting, phase);
}
void reset(void) { memset(&preview, 0, sizeof preview); }
int active(void) { return preview.active; }
int fired(void) { return preview.fired; }
int selected(unsigned char *out, size_t capacity) {
 DpSpeech speech;
 if (!dpSelectGenerated(&speech) || speech.speaker || capacity < speech.length) return -1;
 memcpy(out, speech.bytes, speech.length);
 return speech.length;
}
int malformed(int which) {
 BanjoDialogueResource r = *dpLookup(banjo_dialogue_resources, 3);
 BanjoDialogueRecord bottom[7], top[6];
 uint8_t text[320];
 memcpy(bottom, r.streams[0].records, sizeof bottom);
 memcpy(top, r.streams[1].records, sizeof top);
 memcpy(text, r.text, sizeof text);
 r.streams[0].records = bottom; r.streams[1].records = top; r.text = text;
 size_t cap[2] = {7,6}; DpSpeech out = {0};
 switch(which) {
 case 0: r.streams[0].count = 8; break;
 case 1: r.streams[1].identity = 0; break;
 case 2: r.text_length = 321; break;
 case 3: top[0].text_offset = 65535; break;
 case 4: top[0].text_length = 65535; break;
 case 5: bottom[0].opcode = 7; break;
 case 6: bottom[0].text_length = 1; break;
 case 7: top[0].speaker = 3; break;
 case 8: top[0].portrait = 15; break;
 case 9: top[5].opcode = 6; break;
 case 10: top[0].text_length = 37; break;
 case 11: text[top[0].text_offset] = 27; break;
 case 12: text[top[0].text_offset] = 0; break;
 case 13: r.streams[1].records = NULL; break;
 case 14: r.text = NULL; break;
 case 15: r.resource_id = 0xDF5; break;
 case 16: top[0].opcode = 4; top[0].text_length = 0; break;
 case 17: r.streams[0].count = 0; break;
 case 18: cap[1] = 0; break;
 default: return -1;
 }
 return dpFirstSpeech(&r, sizeof text, cap, &out);
}
int lookup_checks(void) {
 BanjoDialogueResource duplicate[2] = {banjo_dialogue_resources[1], banjo_dialogue_resources[1]};
 return !dpLookup(NULL, 3) && !dpLookup(banjo_dialogue_resources, 0) &&
 !dpLookup(banjo_dialogue_resources, 4) && !dpLookup(duplicate, 2) &&
 dpLookup(banjo_dialogue_resources, 3)->resource_id == 0xDF4;
}
int initial_stream(void) {
 /* If bottom starts with speech, Rare starts top. No bottom-first shortcut. */
 static const uint8_t text[] = {'T','O','P','B','O','T'};
 static const BanjoDialogueRecord bottom[] = {{3,3,0x83,3,15},{6,0,4,255,255}};
 static const BanjoDialogueRecord top[] = {{0,3,0x80,0,12},{6,0,4,255,255}};
 const BanjoDialogueResource r = {text,0xDF4,6,{{bottom,0,2},{top,1,2}}};
 const size_t cap[2] = {2,2}; DpSpeech speech;
 return dpFirstSpeech(&r, sizeof text, cap, &speech) && speech.bytes == text && speech.length == 3;
}
'''
        (p/'test.c').write_text(source)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pedantic','-fPIC','-shared',
                        '-I'+str(p), '-I'+str(ROOT/'platform/3ds/source'),str(p/'test.c'),
                        '-o',str(p/'test.so')],check=True,capture_output=True)
        cls.lib = ctypes.CDLL(str(p/'test.so'))
        cls.lib.observe.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_float]
        cls.lib.selected.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]

    def setUp(self):
        self.lib.reset()

    def test_lookup(self):
        self.assertEqual(self.lib.lookup_checks(), 1)

    def test_original_first_speech_bytes_and_speaker(self):
        expected = dialogue_import.parse_resource(0xDF4, (ROOT/'assets/dialog/0DF4.dialog').read_bytes()).streams[1][0].payload
        target = (ctypes.c_ubyte * 40)(*([0xA5]*40))
        length = self.lib.selected(target, 36)
        self.assertEqual(length, len(expected))
        self.assertEqual(bytes(target[:length]), expected)
        self.assertEqual(bytes(target[length:]), b'\xA5'*(40-length))

    def test_explicit_length_no_overwrite(self):
        target = (ctypes.c_ubyte * 4)(1,2,3,4)
        self.assertEqual(self.lib.selected(target, 3), -1)
        self.assertEqual(bytes(target), bytes([1,2,3,4]))

    def test_initial_stream_rule(self):
        self.assertEqual(self.lib.initial_stream(), 1)

    def test_malformed_records(self):
        for case in range(19):
            with self.subTest(case=case):
                self.assertEqual(self.lib.malformed(case), 0)

    def test_before_interaction_and_unrelated_idle(self):
        for args in [(0,0,0,0),(0,0,0,1),(0,1,0,1)]:
            self.assertEqual(self.lib.observe(*args), 0)
        self.assertEqual(self.lib.active(), 0)

    def test_threshold_and_one_shot(self):
        for phase in (0,0.1,0.349):
            self.assertEqual(self.lib.observe(1,0,0,phase),0)
        self.assertEqual(self.lib.observe(1,0,0,0.35),1)
        for phase in (0.35,0.4,0.9,0.1,0.4):
            self.assertEqual(self.lib.observe(1,0,0,phase),0)
        self.assertEqual(self.lib.active(),1)
        self.assertEqual(self.lib.fired(),1)

    def test_delayed_successful_frame_observation(self):
        self.assertEqual(self.lib.observe(1,0,0,0.4),1)

    def test_idle_keeps_preview(self):
        self.lib.observe(1,0,0,0.4)
        self.assertEqual(self.lib.observe(0,1,0,0.9999),0)
        self.assertEqual(self.lib.active(),1)

    def test_exit_dismisses_terminal_no_restart(self):
        self.lib.observe(1,0,0,0.4)
        self.assertEqual(self.lib.observe(0,0,1,0.9999),1)
        self.assertEqual(self.lib.active(),0)
        self.assertEqual(self.lib.observe(1,0,0,0.4),0)
        self.assertEqual(self.lib.active(),0)

    def test_exit_before_preview_prevents_display(self):
        self.lib.observe(1,0,0,0.1)
        self.lib.observe(0,0,1,0.1)
        self.assertEqual(self.lib.observe(1,0,0,0.4),0)

    def test_invalid_phase_ignored(self):
        for phase in (float('nan'),float('inf'),-0.1,1.1):
            self.assertEqual(self.lib.observe(1,0,0,phase),0)
        self.assertEqual(self.lib.fired(),0)

    def test_switch_default_and_enabled(self):
        text = MAIN.read_text()
        disabled = preprocess(text, **FLAGS)
        self.assertEqual(disabled.returncode,0,disabled.stderr)
        for name in ('dialoguePreview','consoleInit','dpObserve','fwrite'):
            self.assertNotIn(name, disabled.stdout)
        enabled = preprocess(text, **FLAGS, BOTTLES_DIALOGUE_PREVIEW=1)
        self.assertEqual(enabled.returncode,0,enabled.stderr)
        self.assertIn('dpObserve',enabled.stdout)
        self.assertIn('consoleInit(GFX_BOTTOM',enabled.stdout)
        missing = preprocess(text,BOTTLES_DIALOGUE_PREVIEW=1)
        self.assertNotEqual(missing.returncode,0)

    def test_console_and_observer_order_and_no_input_writes(self):
        text = MAIN.read_text()
        self.assertLess(text.index('consoleInit(GFX_BOTTOM'),text.index('C3D_Init('))
        wait = text.index('if (!C3D_FrameBegin(C3D_FRAME_SYNCDRAW)) continue;')
        observe = text.index('dpObserve(&dialoguePreview')
        self.assertLess(wait,observe)
        self.assertLess(text.index('if (bottlesEmergencePublish())'),observe)
        self.assertLess(observe,text.index('C3D_FrameDrawOn(target);'))
        body = function(text,'dialoguePreviewPresent')
        for forbidden in ('C3D_', 'gfxSwap', 'gfxFlush', 'consoleClear(', 'strcpy', 'sprintf'):
            self.assertNotIn(forbidden, body)
        self.assertNotIn(r'\n',body)  # libctru newline flushes both screens
        self.assertIn('dialoguePreviewSpeech.length',body)
        self.assertIn('320u * 240u * sizeof(u16)',body)
        observer = text[observe:text.index('#endif',observe)]
        for forbidden in ('KEY_', 'controls', 'phase +='):
            self.assertNotIn(forbidden,observer)
        self.assertNotRegex(observer, r"(?:State|Phase)\s*=(?!=)")

    def test_explicit_conditional_build_dependency(self):
        make = (ROOT/'platform/3ds/Makefile').read_text()
        self.assertIn('BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW ?= 0',make)
        self.assertIn('all: $(BANJO3DS_GENERATED_DIALOGUE)',make)
        rule = make[make.index('$(BANJO3DS_GENERATED_DIALOGUE):'):]
        for name in ('0DF4.dialog','0DF5.dialog','0D38.dialog','dialogue_import.py','--output $@'):
            self.assertIn(name,rule.split('endif')[0])


if __name__ == '__main__':
    unittest.main()
