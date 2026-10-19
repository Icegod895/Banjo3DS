"""B2-P1: original hill clip, once clock, bounded publication and FIX7 isolation."""
import ctypes as C
import math
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.actor_mesh import export_exit_header, export_actor_header, export_bottles_emergence_header, export_hill_open_header, load_actor, parse_packet, reference_evaluate, ActorClip
from tools.banjo3ds.tests.test_actor_draw import MAIN, ROOT, preprocess, function


class ActorEmergenceTests(unittest.TestCase):
    b_enabled = False
    exit_enabled = False
    proximity = False
    manual = True
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.main = MAIN.read_text()
        cls.active = preprocess(cls.main, STATIC_BOTTLES=1, IDLE_ANIMATION=1, HILL_OPEN_ANIMATION=1,
                                HILL_PROXIMITY_TRIGGER=int(cls.proximity),
                                HILL_MANUAL_TRIGGER=int(cls.manual),BOTTLES_EMERGENCE=1, BOTTLES_EXIT=int(cls.exit_enabled), BOTTLES_B_INTERACTION=int(getattr(cls, "b_enabled", False))).stdout
        block = cls.active[cls.active.index('static double hillOpenSeconds;'):]
        block = block.split('static void sceneDrawActorRange', 1)[0]
        header = export_actor_header(ROOT/'assets/model/0387.model.bin',
                                    ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/013B.anim.bin')
        header += export_hill_open_header(ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/013D.anim.bin')
        header += export_bottles_emergence_header(ROOT/'assets/model/0387.model.bin',ROOT/'assets/anim/013A.anim.bin')
        if cls.exit_enabled:
            header += export_exit_header(ROOT/'assets/model/0387.model.bin', ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/0139.anim.bin', ROOT/'assets/anim/013C.anim.bin')
        data = '\n'.join(re.findall(r'^#define ACTOR_.*', header, re.M))
        for name in ('actor_vertices', 'actor_bottles_packet', 'actor_hill_open_packet', 'actor_bottles_emerge_packet') + (('actor_bottles_exit_packet', 'actor_hill_close_packet') if cls.exit_enabled else ()):
            data += '\n' + re.search(r'static const [^\n]* '+name+r'\[\] = \{.*?\n\};', header, re.S).group()
        model = (ROOT/'platform/3ds/source/generated_model.h').read_text()
        vertex = re.search(r'typedef struct \{[^}]*\} Banjo3DSVertex;', model).group()
        prelude = '''#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include "actor_pose.h"
typedef uint8_t u8;
typedef uint32_t u32;
static void *actor_vbo, *vbo_data;
static unsigned flushes;
static unsigned sound_requests;
static unsigned pull_requests, pop_requests;
static unsigned retreat_start_requests, retreat_stop_requests;
static bool retreat_playing, retreat_available = true;
static unsigned emergence_loop_start_requests, emergence_loop_stop_requests;
static bool emergence_loop_playing, emergence_loop_available = true;
void sfxProbe3dsBottlesEmergence(void) { ++sound_requests; }
void sfxProbe3dsBottlesPull(void) { ++pull_requests; }
void sfxProbe3dsBottlesPop(void) { ++pop_requests; }
bool sfxProbe3dsBottlesRetreatStart(void) {
    ++retreat_start_requests;
    if (!retreat_available) return false;
    retreat_playing = true;
    return true;
}
void sfxProbe3dsBottlesRetreatStop(void) {
    if (retreat_playing) ++retreat_stop_requests;
    retreat_playing = false;
}
bool sfxProbe3dsBottlesEmergenceLoopStart(void) {
    ++emergence_loop_start_requests;
    if (!emergence_loop_available) return false;
    emergence_loop_playing = true;
    return true;
}
void sfxProbe3dsBottlesEmergenceLoopStop(void) {
    if (emergence_loop_playing) ++emergence_loop_stop_requests;
    emergence_loop_playing = false;
}
static int fault, evaluations, bottle_only;
bool __real_actor_pose_info(const uint8_t *, size_t, ActorPoseInfo *);
bool __wrap_actor_pose_info(const uint8_t *p, size_t n, ActorPoseInfo *out) {
    bool ok=__real_actor_pose_info(p,n,out);
    if (ok && (!bottle_only || n != 1256) && fault == 4) ++out->load_count;
    if (ok && (!bottle_only || n != 1256) && fault == 5) ++out->matrix_count;
    if (ok && (!bottle_only || n != 1256) && fault == 6) ++out->corner_count;
    if (ok && (!bottle_only || n != 1256) && fault == 7) ++out->bone_slots;
    if (ok && (!bottle_only || n != 1256) && fault == 8) ++out->anim_bytes;
    if (ok && (!bottle_only || n != 1256) && fault == 9) ++out->anim_last;
    if (ok && (!bottle_only || n != 1256) && fault == 10) ++out->anim_channels;
    if (ok && (!bottle_only || n != 1256) && fault == 11) out->boneless=1;
    return ok;
}
bool __real_actor_pose_evaluate(const uint8_t *, size_t, float, float *, float *, float *);
bool __wrap_actor_pose_evaluate(const uint8_t *p, size_t n, float phase, float *b, float *m, float *xyz) {
    ++evaluations;
    bool ok=__real_actor_pose_evaluate(p,n,phase,b,m,xyz);
    if ((!bottle_only || n != 1256) && fault == 1) xyz[0]=NAN;
    if ((!bottle_only || n != 1256) && fault == 2) xyz[1]=INFINITY;
    if ((!bottle_only || n != 1256) && fault == 3) xyz[2]=401.0f;
    return ok;
}
void fault_set(int f) { fault=f; evaluations=0; }
void fault_bottles(int f) { fault_set(f); bottle_only=1; }
int eval_count(void) { return evaluations; }
static void *flush_address;
static size_t flush_size;
static void GSPGPU_FlushDataCache(void *p, size_t n) { ++flushes; flush_address=p; flush_size=n; }
'''
        if cls.exit_enabled:
            prelude += """
bool __real_actor_pose_evaluate_blend(const uint8_t *, size_t, float, const float *, size_t, float, float *, float *, float *);
bool __wrap_actor_pose_evaluate_blend(const uint8_t *p, size_t n, float phase, const float *src, size_t slots, float factor, float *b, float *m, float *xyz) {
    ++evaluations;
    bool ok=__real_actor_pose_evaluate_blend(p,n,phase,src,slots,factor,b,m,xyz);
    if (fault == 1) xyz[0]=NAN;
    if (fault == 2) xyz[1]=INFINITY;
    if (fault == 3) xyz[2]=401;
    return ok;
}
"""
        if cls.exit_enabled:
            prelude = prelude.replace('static int fault,', 'static size_t fault_packet_size;\nstatic int fault,')
            prelude = prelude.replace('if (ok &&', 'if (ok && (!fault_packet_size || n == fault_packet_size) &&')
            prelude = prelude.replace('if ((!bottle_only', 'if ((!fault_packet_size || n == fault_packet_size) && (!bottle_only')
            prelude = prelude.replace('if (fault ==', 'if ((!fault_packet_size || n == fault_packet_size) && fault ==')
        wrapper = '''
static union { double align; unsigned char bytes[sizeof actor_vertices + 64]; } owned;
static unsigned char world[sizeof actor_vertices];
void reset(void) {
    memset(owned.bytes, 0xA5, sizeof owned.bytes);
    memcpy(owned.bytes+32, actor_vertices, sizeof actor_vertices);
    memset(world, 0x5A, sizeof world);
    actor_vbo=owned.bytes+32; vbo_data=world;
    hillOpenSeconds=0; bottlesEmergenceIdlePhase=0;
    bottlesEmergenceState=BOTTLES_WAITING; bottlesEmergenceVisible=false;
    bottlesEmergencePhase=0; bottlesEmergenceBlend=0; bottlesEmergenceSfxPending=false;
    bottlesPullSfxPending=false; bottlesPopSfxPending=false;
    bottlesEmergenceLoopStarted=false;
    sound_requests=0; pull_requests=0; pop_requests=0;
    retreat_start_requests=0; retreat_stop_requests=0;
    retreat_playing=false; retreat_available=true;
    emergence_loop_start_requests=0; emergence_loop_stop_requests=0;
    emergence_loop_playing=false; emergence_loop_available=true;
    bottle_only=0; flushes=0; fault=0; evaluations=0;
}
void phase_set(float p) { hillOpenSeconds=(double)p*4.5; }
float phase_get(void) { return (float)(hillOpenSeconds/4.5); }
float bottles_phase(void) { return bottlesEmergenceIdlePhase; }
int prepare(float dt) { return hillOpenPrepare(dt); }
int publish(void) { return hillOpenPublish(); }
void ownership(int mode) { actor_vbo=mode == 1 ? NULL : vbo_data; }
const void *bytes(void) { return owned.bytes; }
const void *world_bytes(void) { return world; }
const float *xyz(void) { return hillOpenXYZ; }
unsigned flush_count(void) { return flushes; }
int flush_valid(void) { return flush_address == owned.bytes+32 && flush_size == 168*24; }

static bool C3D_FrameBegin(int mode) { return mode != 0; }
#define C3D_FRAME_SYNCDRAW wait_ok
void frame(float dt, int wait_ok) {
    for (int once=0; once<1; ++once) {
FRAME_BODY
    }
}
'''
        if cls.proximity or cls.manual:
            prelude += '#include "movement.h"\nstatic struct { struct { MovementActor actor; } motion; } player;\n'
            wrapper = wrapper.replace('hillOpenSeconds=0;',
                'hillOpenTriggered=false; player.motion.actor=(MovementActor){2250,-34,2774,0}; hillOpenSeconds=0;')
            wrapper += """
void position(float x, float y, float z) { player.motion.actor=(MovementActor){x,y,z,0}; }
void arm(void) { reset(); hillOpenTriggered=false; position(0,1800,0); }
int triggered(void) { return hillOpenTriggered; }
"""
        if cls.manual:
            prelude += '#define KEY_SELECT (1u << 2)\nstatic u32 testKeys, testPreviousKeys;\n'
            wrapper = wrapper.replace('hillOpenSeconds=0;',
                'hillOpenManualPressed=false; testKeys=0; testPreviousKeys=0; hillOpenSeconds=0;')
            wrapper = wrapper.replace('void frame(float dt, int wait_ok) {',
                'void frame(float dt, int wait_ok) {\n    u32 down=testKeys & ~testPreviousKeys; testPreviousKeys=testKeys;')
            wrapper += 'void keys(u32 held) { testKeys=held; }\n'
        wrapper += """
int state(void) { return bottlesEmergenceState; }
int visible(void) { return bottlesEmergenceVisible; }
unsigned sound_count(void) { return sound_requests; }
unsigned pull_count(void) { return pull_requests; }
unsigned pop_count(void) { return pop_requests; }
unsigned emergence_loop_start_count(void) { return emergence_loop_start_requests; }
unsigned emergence_loop_stop_count(void) { return emergence_loop_stop_requests; }
int emergence_loop_is_playing(void) { return emergence_loop_playing; }
void emergence_loop_available_set(int value) { emergence_loop_available=value!=0; }
float emerge_phase(void) { return bottlesEmergencePhase; }
float blend_factor(void) { return bottlesEmergenceBlend; }
const float *bottles_xyz(void) { return bottlesEmergenceXYZ; }
const float *bottles_bones(void) { return bottlesEmergenceBones; }
const float *source_bones(void) { return bottlesEmergenceSource; }
void emerge_phase_set(float p) { bottlesEmergencePhase=p; }
int bottles_prepare(float dt) { return bottlesEmergencePrepare(dt,false); }
void release_select(void) { testKeys=0; testPreviousKeys=0; }
"""
        if cls.exit_enabled:
            wrapper = wrapper.replace('bottlesEmergenceState=BOTTLES_WAITING;',
                'fault_packet_size=0; bottlesExitPhase=0; hillClosePhase=0; bottlesExitBlend=0; hillCloseBlend=0; bottlesExitFinalPublished=false; bottlesRetreatSfxStarted=false; bottlesEmergenceState=BOTTLES_WAITING;')
            wrapper += """
void fault_close(int f) { fault_set(f); fault_packet_size=1232; }
float exit_phase(void) { return bottlesExitPhase; }
float close_phase(void) { return hillClosePhase; }
float exit_blend(void) { return bottlesExitBlend; }
float close_blend(void) { return hillCloseBlend; }
void exit_phase_set(float f) { bottlesExitPhase=f; }
void close_phase_set(float f) { hillClosePhase=f; }
int exit_prepare(float dt, int start) { return bottlesExitPrepare(dt,start); }
const float *close_bones(void) { return hillCloseBones; }
const float *close_source(void) { return hillCloseSource; }
int final_published(void) { return bottlesExitFinalPublished; }
unsigned retreat_start_count(void) { return retreat_start_requests; }
unsigned retreat_stop_count(void) { return retreat_stop_requests; }
int retreat_is_playing(void) { return retreat_playing; }
void retreat_available_set(int value) { retreat_available=value!=0; }
"""
        if getattr(cls, "b_enabled", False):
            prelude += 'static bool bottlesBStart;\n'
            wrapper += 'void b_event(int b) { bottlesBStart=b!=0; }\n'
            wrapper = wrapper.replace('bottlesEmergenceState=BOTTLES_WAITING;', 'bottlesBStart=false; bottlesEmergenceState=BOTTLES_WAITING;')
        loop = cls.active[cls.active.index('hillOpenManualPressed = (down & KEY_SELECT) != 0;'):]
        loop = loop[:loop.index('u64 scatterStart')]
        wrapper = wrapper.replace('FRAME_BODY', loop)
        cls.libs = []
        for opt in ('-O0', '-O2'):
            source = Path(cls.temp.name)/f'idle{opt}.c'
            source.write_text(prelude+vertex+'\n'+data+'\n'+block+wrapper)
            out = source.with_suffix('.so')
            subprocess.run(['cc',opt,'-shared','-fPIC','-Wall','-Wextra','-Werror',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                '-DBANJO3DS_ACTOR_BOTTLES_EMERGENCE=1',
                '-I'+str(ROOT/'tools/banjo3ds/actor_pose'),
                '-I'+str(ROOT/'platform/3ds/source'),str(source),
                str(ROOT/'tools/banjo3ds/actor_pose/actor_pose.c'),
                *(['-Wl,--wrap=actor_pose_evaluate_blend'] if cls.exit_enabled else []),
                '-Wl,--wrap=actor_pose_info', '-Wl,--wrap=actor_pose_evaluate','-lm','-o',str(out)],check=True,capture_output=True)
            lib=C.CDLL(str(out))
            lib.prepare.argtypes=[C.c_float];lib.phase_set.argtypes=[C.c_float]
            lib.phase_get.restype=C.c_float
            lib.bottles_phase.restype=C.c_float
            lib.frame.argtypes=[C.c_float, C.c_int]
            lib.bytes.restype=C.c_void_p;lib.world_bytes.restype=C.c_void_p
            lib.xyz.restype=C.POINTER(C.c_float)
            if cls.proximity or cls.manual:
                lib.position.argtypes=[C.c_float,C.c_float,C.c_float]
            for name in ('emerge_phase','blend_factor'): getattr(lib,name).restype=C.c_float
            for name in ('bottles_xyz','bottles_bones','source_bones'): getattr(lib,name).restype=C.POINTER(C.c_float)
            lib.emerge_phase_set.argtypes=[C.c_float];lib.bottles_prepare.argtypes=[C.c_float]
            if cls.exit_enabled:
                for name in ('exit_phase','close_phase','exit_blend','close_blend'): getattr(lib,name).restype=C.c_float
                for name in ('close_bones','close_source'): getattr(lib,name).restype=C.POINTER(C.c_float)
                lib.exit_prepare.argtypes=[C.c_float,C.c_int]
                lib.exit_phase_set.argtypes=[C.c_float];lib.close_phase_set.argtypes=[C.c_float]
            cls.libs.append(lib)
        cls.hill=load_actor(ROOT/'assets/model/0388.model.bin','molehill',
                           (ROOT/'assets/anim/013D.anim.bin').read_bytes())

        cls.emerge=load_actor(ROOT/'assets/model/0387.model.bin','bottles', (ROOT/'assets/anim/013A.anim.bin').read_bytes())
        cls.idle=load_actor(ROOT/'assets/model/0387.model.bin','bottles',(ROOT/'assets/anim/013B.anim.bin').read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        for lib in self.libs: lib.reset()

    def activate(self, lib, wait=1):
        lib.position(2250,-34,2774);lib.keys(4);lib.frame(.05,wait)

    def test_original_asset_geometry_hierarchy_channels_and_bounds(self):
        import struct
        info=parse_packet(self.emerge.packet);idle=parse_packet(self.idle.packet)
        self.assertEqual((len(self.emerge.packet),info.matrix_count,info.bone_slots,info.load_count,
                          info.corner_count,info.anim_last,info.anim_channels,info.anim_bytes),
                         (19378,37,72,590,1851,248,52,10316))
        self.assertEqual((info.records,info.loads,info.corners,info.factor),
                         (idle.records,idle.loads,idle.corners,idle.factor))
        self.assertEqual(info.animation,(ROOT/'assets/anim/013A.anim.bin').read_bytes())
        self.assertEqual(struct.unpack_from('>hhhH',info.animation),(0,248,52,0))
        clip=ActorClip(info.animation,72)
        self.assertEqual({k for k in clip.channels if k[1]>=6},{(3,7),(3,8),(43,7),(43,8)})
        self.assertEqual(sum(k[1]<3 for k in clip.channels),47)
        self.assertIn('#define ACTOR_BOTTLES_EMERGE_DURATION 4.5f',export_bottles_emergence_header(
            ROOT/'assets/model/0387.model.bin',ROOT/'assets/anim/013A.anim.bin'))

    def test_dense_original_pose_rotation_and_translation_parity(self):
        info=parse_packet(self.emerge.packet);clip=ActorClip(info.animation,72)
        phases={0.,.0001,.9999,1.}
        phases.update(i/248 for i in range(249));phases.update((i+.37)/248 for i in range(248))
        for keys in clip.channels.values():
            for word,_ in keys:
                for offset in (-.001,0,.001):
                    frame=(word&0x3fff)+offset
                    if 0<=frame<=248: phases.add(frame/248)
        packet=(C.c_ubyte*len(self.emerge.packet)).from_buffer_copy(self.emerge.packet)
        for lib in self.libs:
            lib.actor_pose_evaluate.argtypes=[C.c_void_p,C.c_size_t,C.c_float,C.c_void_p,C.c_void_p,C.c_void_p]
            bones=(C.c_float*(72*10))();matrices=(C.c_float*(37*16))();xyz=(C.c_float*(590*3))()
            for phase in sorted(phases):
                phase=C.c_float(phase).value
                expected_bones,_,expected_xyz=reference_evaluate(self.emerge.packet,phase)
                self.assertTrue(lib.actor_pose_evaluate(packet,len(packet),phase,bones,matrices,xyz))
                self.assertLess(max(abs(a-b) for a,b in zip(bones,[x for row in expected_bones for x in row])),.00005)
                self.assertLess(max(abs(a-b) for a,b in zip(xyz,[x for row in expected_xyz for x in row])),.005)
                self.assertTrue(all(math.isfinite(x) and -200<=x<=400 for x in xyz))
        start=reference_evaluate(self.emerge.packet,0)[2];middle=reference_evaluate(self.emerge.packet,.5)[2]
        end=reference_evaluate(self.emerge.packet,1)[2]
        self.assertNotEqual(start,middle);self.assertNotEqual(middle,end)
        self.assertGreater(min(p[1] for p in end),min(p[1] for p in start)+100)
        # All authored rotational channels (including head motion) are covered
        # above; no guessed head bone label or hand-authored visual golden.
        self.assertNotEqual(clip.transforms(.15),clip.transforms(.3))

    def test_hidden_waiting_and_same_select_start_then_independent_clocks(self):
        for lib in self.libs:
            lib.arm()
            before=C.string_at(lib.bytes(),2019*24+64)
            for _ in range(700):lib.frame(.05,1)
            self.assertEqual((lib.state(),lib.visible(),lib.triggered()),(0,0,0))
            self.assertEqual(lib.emerge_phase(),0);self.assertEqual(lib.phase_get(),0)
            self.assertEqual(C.string_at(lib.bytes()+32+168*24,1851*24),before[32+168*24:-32])
            lib.keys(4);lib.frame(.05,1) # far SELECT is discarded
            lib.position(2250,-34,2774);lib.frame(.05,1)
            self.assertEqual(lib.state(),0)
            lib.release_select();lib.keys(4);lib.frame(.05,1)
            self.assertEqual((lib.state(),lib.visible(),lib.triggered()),(1,1,1))
            self.assertEqual(lib.phase_get(),0);self.assertEqual(lib.emerge_phase(),C.c_float(.0001).value)
            hill=lib.phase_get()
            self.assertEqual(lib.bottles_prepare(.05),1) # no hill controller access
            self.assertEqual(lib.phase_get(),hill);self.assertGreater(lib.emerge_phase(),.0001)
            bottles=lib.emerge_phase()
            self.assertEqual(lib.prepare(.05),1)
            self.assertEqual(lib.emerge_phase(),bottles)

    def test_once_completion_original_threshold_and_idle_speed(self):
        for lib in self.libs:
            lib.arm();self.activate(lib)
            for _ in range(90):lib.frame(.05,1)
            self.assertEqual(lib.state(),1)
            self.assertEqual(lib.emerge_phase(),C.c_float(.9999989867210388).value)
            self.assertEqual(lib.phase_get(),1)
            self.assertEqual(list(lib.xyz()[:219]),[float(x) for load in parse_packet(self.hill.packet).loads for x in load[:3]])
            end=list(lib.bottles_bones()[:720])
            lib.frame(.05,1)
            self.assertEqual(lib.state(),2)
            self.assertAlmostEqual(lib.bottles_phase(),.0001+.05/7,places=7)
            self.assertEqual(lib.blend_factor(),.25)
            self.assertEqual(list(lib.source_bones()[:720]),end)
            for _ in range(3):lib.frame(.05,1)
            self.assertEqual(lib.blend_factor(),1)
            for _ in range(200):
                lib.release_select();lib.keys(4);lib.frame(.05,1)
            self.assertEqual(lib.state(),2);self.assertEqual(lib.phase_get(),1)
            self.assertEqual(lib.visible(),1)
            lib.reset();self.activate(lib);lib.emerge_phase_set(.9999)
            lib.bottles_prepare(0);self.assertEqual(lib.state(),1)
            lib.bottles_prepare(.001);self.assertEqual(lib.state(),1)
            lib.bottles_prepare(0);self.assertEqual(lib.state(),2)

    def test_original_c6_crossing_once_after_published_emergence(self):
        for lib in self.libs:
            lib.arm()
            for _ in range(3): lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),0)
            self.activate(lib)
            self.assertEqual(lib.sound_count(),0)
            # Normal 4.5 s clip: .14 is crossed after more than twelve 50 ms frames.
            for _ in range(12): lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),0)
            lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),1)
            for _ in range(100): lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),1)

            # A prepared but unpublished crossing queues no audio until publication.
            lib.arm(); self.activate(lib)
            lib.emerge_phase_set(.139)
            lib.frame(.05,0)
            self.assertEqual(lib.sound_count(),0)
            lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),1)
            lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),1)

            # Failed pose evaluation at the crossing does not request audio.
            lib.arm(); self.activate(lib)
            lib.emerge_phase_set(.139)
            lib.fault_bottles(1)
            lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),0)
            lib.fault_bottles(0)
            lib.frame(.05,1)
            self.assertEqual(lib.sound_count(),1)

    def test_original_3f9_emergence_window_and_publication(self):
        for lib in self.libs:
            lib.arm()
            self.assertEqual(lib.emergence_loop_start_count(), 0)
            self.activate(lib, wait=0)
            self.assertEqual(lib.emergence_loop_start_count(), 0)
            lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_start_count(), 1)
            self.assertEqual(lib.emergence_loop_is_playing(), 1)
            for _ in range(11): lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_start_count(), 1)
            self.assertEqual(lib.emergence_loop_stop_count(), 0)
            self.assertEqual(lib.sound_count(), 0)
            lib.frame(.05, 1)
            self.assertEqual(lib.sound_count(), 1)
            self.assertEqual(lib.emergence_loop_is_playing(), 1)
            for _ in range(3): lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_stop_count(), 1)
            self.assertEqual(lib.emergence_loop_is_playing(), 0)
            for _ in range(80): lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_start_count(), 1)
            self.assertEqual(lib.emergence_loop_stop_count(), 1)

            lib.arm(); lib.emergence_loop_available_set(0); self.activate(lib)
            lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_is_playing(), 0)
            self.assertGreater(lib.emergence_loop_start_count(), 0)
            lib.emergence_loop_available_set(1)
            lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_is_playing(), 1)

            lib.arm(); self.activate(lib, wait=0)
            lib.fault_bottles(1)
            lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_start_count(), 0)
            lib.fault_bottles(0)
            lib.frame(.05, 1)
            self.assertEqual(lib.emergence_loop_start_count(), 1)

    def test_original_2c_and_c5_crossings_after_publication(self):
        for lib in self.libs:
            lib.arm(); self.activate(lib)
            for _ in range(90): lib.frame(.05,1)
            self.assertEqual((lib.sound_count(),lib.pull_count(),lib.pop_count()),(1,1,1))
            for _ in range(10): lib.frame(.05,1)
            self.assertEqual((lib.sound_count(),lib.pull_count(),lib.pop_count()),(1,1,1))

            # A rejected frame must not publish its prepared threshold crossing.
            lib.arm(); self.activate(lib)
            lib.emerge_phase_set(.399)
            lib.frame(.05,0)
            self.assertEqual(lib.pull_count(),0)
            lib.frame(.05,1)
            self.assertEqual(lib.pull_count(),1)
            lib.frame(.05,1)
            self.assertEqual(lib.pull_count(),1)

            lib.arm(); self.activate(lib)
            lib.emerge_phase_set(.749)
            lib.fault_bottles(1)
            lib.frame(.05,1)
            self.assertEqual(lib.pop_count(),0)
            lib.fault_bottles(0)
            lib.frame(.05,1)
            self.assertEqual(lib.pop_count(),1)

    def test_blend_matches_original_C_oracle(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools/banjo3ds/tests'))
        from transition_reference import blend_pose
        identity=(0.,0.,0.,1.,1.,1.,1.,0.,0.,0.)
        for lib in self.libs:
            lib.arm();self.activate(lib)
            for _ in range(90):lib.frame(.05,1)
            source=[tuple(lib.bottles_bones()[i*10:i*10+10]) for i in range(72)]
            for _ in range(8):
                lib.frame(.025,1)
                target=reference_evaluate(self.idle.packet,lib.bottles_phase())[0]
                expected,_=blend_pose(source+[identity]*37,target+[identity]*37,lib.blend_factor())
                self.assertLess(max(abs(a-b) for a,b in zip(lib.bottles_bones()[:720],[x for row in expected[:72] for x in row])),.00005)

    def test_pair_rejection_wait_visibility_and_corner_canaries(self):
        import struct
        info=parse_packet(self.emerge.packet)
        for lib in self.libs:
            lib.arm();before=C.string_at(lib.bytes(),2019*24+64)
            self.activate(lib,wait=0)
            self.assertEqual(lib.visible(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.frame(.05,1)
            self.assertEqual(lib.visible(),1)
            after=C.string_at(lib.bytes(),len(before))
            self.assertEqual(before[:32],after[:32]);self.assertEqual(before[-32:],after[-32:])
            for i,load in enumerate(info.corners):
                offset=32+(168+i)*24
                self.assertEqual(struct.unpack_from('3f',after,offset),tuple(lib.bottles_xyz()[load*3:load*3+3]))
            for offset in range(32,32+2019*24,24):
                self.assertEqual(before[offset+12:offset+24],after[offset+12:offset+24])
            self.assertEqual(C.string_at(lib.world_bytes(),2019*24),b'\x5a'*(2019*24))
            for fault in (1,2,3,4,5,6,7,8,9,10,11):
                lib.arm();lib.fault_bottles(fault);self.activate(lib)
                self.assertEqual((lib.state(),lib.visible(),lib.triggered()),(0,0,0))
                self.assertEqual(lib.phase_get(),0)
                self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
                self.assertEqual(lib.flush_count(),0)
            lib.arm();self.activate(lib);lib.fault_bottles(1)
            before=C.string_at(lib.bytes(),2019*24+64);old=lib.emerge_phase()
            lib.frame(.05,1)
            self.assertEqual(lib.emerge_phase(),old);self.assertEqual(lib.phase_get(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)

    def test_visibility_gate_renderers_compatibility_and_configuration(self):
        flags=dict(STATIC_BOTTLES=1,IDLE_ANIMATION=1,HILL_OPEN_ANIMATION=1,HILL_MANUAL_TRIGGER=1,BOTTLES_EMERGENCE=1)
        for flag in ('ISOLATION','TEXTURE_UPLOAD','VERTEX_INIT','HILL_DRAW','STATIC_BOTTLES','IDLE_ANIMATION','HILL_OPEN_ANIMATION','HILL_MANUAL_TRIGGER'):
            self.assertNotEqual(preprocess(self.main,**dict(flags,**{flag:0})).returncode,0)
        self.assertNotEqual(preprocess(self.main,**dict(flags,HILL_PROXIMITY_TRIGGER=1)).returncode,0)
        control=preprocess(self.main,**dict(flags,BOTTLES_EMERGENCE=0)).stdout
        for token in ('bottlesEmergence','actor_bottles_emerge_packet'):self.assertNotIn(token,control)
        facing = '    Mtx_RotateY(&world, C3D_AngleFromDegrees(bottlesFacingYaw), true);\n'
        self.assertEqual(function(self.active,'sceneDrawStaticBottles').replace(facing, ''),
                         function(control,'sceneDrawStaticBottles'))
        self.assertEqual(function(self.active,'sceneDrawStaticBottles').count(facing), 1)
        for name in ('sceneDrawClosedMolehill','sceneDrawActorRange'):
            self.assertEqual(function(self.active,name),function(control,name))
        render=function(self.active,'sceneRender')
        self.assertIn('if (bottlesEmergenceVisible)\n    sceneDrawStaticBottles',render)
        self.assertNotIn('bottlesIdlePrepare',self.active)
        loop=self.active[self.active.index('while (aptMainLoop())'):]
        self.assertLess(loop.index('bottlesEmergencePrepare'),loop.index('C3D_FrameBegin'))
        self.assertLess(loop.index('C3D_FrameBegin'),loop.index('bottlesEmergencePublish'))
        self.assertNotIn('KEY_B',loop[loop.index('hillOpenManualPressed ='):loop.index('u64 scatterStart')])

    def test_blend_api_rejects_bad_source_capacity_and_factor(self):
        packet=(C.c_ubyte*len(self.idle.packet)).from_buffer_copy(self.idle.packet)
        initial=reference_evaluate(self.emerge.packet,.9999989867210388)[0]
        source=(C.c_float*720)(*[x for row in initial for x in row])
        for lib in self.libs:
            fn=lib.actor_pose_evaluate_blend
            fn.argtypes=[C.c_void_p,C.c_size_t,C.c_float,C.c_void_p,C.c_size_t,C.c_float,C.c_void_p,C.c_void_p,C.c_void_p]
            bones=(C.c_float*720)();matrices=(C.c_float*(37*16))();xyz=(C.c_float*(590*3))()
            for slots,factor in ((71,.5),(73,.5),(72,-.1),(72,1.1),(72,math.nan)):
                self.assertFalse(fn(packet,len(packet),.01,source,slots,factor,bones,matrices,xyz))
            self.assertTrue(fn(packet,len(packet),.01,source,72,0,bones,matrices,xyz))
            self.assertEqual(list(bones),list(source))
            source[0]=math.nan
            self.assertFalse(fn(packet,len(packet),.01,source,72,.5,bones,matrices,xyz))
            source[0]=initial[0][0]
