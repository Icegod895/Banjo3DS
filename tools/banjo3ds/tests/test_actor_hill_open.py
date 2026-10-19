"""B2-P1: original hill clip, once clock, bounded publication and FIX7 isolation."""
import ctypes as C
import math
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.actor_mesh import export_actor_header, export_hill_open_header, load_actor, parse_packet, reference_evaluate, ActorClip
from tools.banjo3ds.tests.test_actor_draw import MAIN, ROOT, preprocess, function


class ActorHillOpenTests(unittest.TestCase):
    proximity = False
    manual = False
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.main = MAIN.read_text()
        cls.active = preprocess(cls.main, STATIC_BOTTLES=1, IDLE_ANIMATION=1, HILL_OPEN_ANIMATION=1,
                                HILL_PROXIMITY_TRIGGER=int(cls.proximity),
                                HILL_MANUAL_TRIGGER=int(cls.manual)).stdout
        block = cls.active[cls.active.index('static double hillOpenSeconds;'):]
        block = block.split('static void sceneDrawActorRange', 1)[0]
        header = export_actor_header(ROOT/'assets/model/0387.model.bin',
                                    ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/013B.anim.bin')
        header += export_hill_open_header(ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/013D.anim.bin')
        data = '\n'.join(re.findall(r'^#define ACTOR_.*', header, re.M))
        for name in ('actor_vertices', 'actor_bottles_packet', 'actor_hill_open_packet'):
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
static int fault, evaluations;
bool __real_actor_pose_info(const uint8_t *, size_t, ActorPoseInfo *);
bool __wrap_actor_pose_info(const uint8_t *p, size_t n, ActorPoseInfo *out) {
    bool ok=__real_actor_pose_info(p,n,out);
    if (ok && fault == 4) ++out->load_count;
    if (ok && fault == 5) ++out->matrix_count;
    if (ok && fault == 6) ++out->corner_count;
    if (ok && fault == 7) ++out->bone_slots;
    if (ok && fault == 8) ++out->anim_bytes;
    if (ok && fault == 9) ++out->anim_last;
    if (ok && fault == 10) ++out->anim_channels;
    if (ok && fault == 11) out->boneless=1;
    return ok;
}
bool __real_actor_pose_evaluate(const uint8_t *, size_t, float, float *, float *, float *);
bool __wrap_actor_pose_evaluate(const uint8_t *p, size_t n, float phase, float *b, float *m, float *xyz) {
    ++evaluations;
    bool ok=__real_actor_pose_evaluate(p,n,phase,b,m,xyz);
    if (fault == 1) xyz[0]=NAN;
    if (fault == 2) xyz[1]=INFINITY;
    if (fault == 3) xyz[2]=201.0f;
    return ok;
}
void fault_set(int f) { fault=f; evaluations=0; }
int eval_count(void) { return evaluations; }
static void *flush_address;
static size_t flush_size;
static void GSPGPU_FlushDataCache(void *p, size_t n) { ++flushes; flush_address=p; flush_size=n; }
'''
        wrapper = '''
static union { double align; unsigned char bytes[sizeof actor_vertices + 64]; } owned;
static unsigned char world[sizeof actor_vertices];
void reset(void) {
    memset(owned.bytes, 0xA5, sizeof owned.bytes);
    memcpy(owned.bytes+32, actor_vertices, sizeof actor_vertices);
    memset(world, 0x5A, sizeof world);
    actor_vbo=owned.bytes+32; vbo_data=world;
    hillOpenSeconds=0; bottlesIdlePhase=0; flushes=0; fault=0; evaluations=0;
}
void phase_set(float p) { hillOpenSeconds=(double)p*4.5; }
float phase_get(void) { return (float)(hillOpenSeconds/4.5); }
float bottles_phase(void) { return bottlesIdlePhase; }
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
                'hillOpenTriggered=true; player.motion.actor=(MovementActor){2250,-34,2774,0}; hillOpenSeconds=0;')
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
        loop = cls.active[cls.active.index('bool bottlesIdleReady = bottlesIdlePrepare(dt);'):]
        loop = loop[:loop.index('u64 scatterStart')]
        wrapper = wrapper.replace('FRAME_BODY', loop)
        cls.libs = []
        for opt in ('-O0', '-O2'):
            source = Path(cls.temp.name)/f'idle{opt}.c'
            source.write_text(prelude+vertex+'\n'+data+'\n'+block+wrapper)
            out = source.with_suffix('.so')
            subprocess.run(['cc',opt,'-shared','-fPIC','-Wall','-Wextra','-Werror',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                '-I'+str(ROOT/'tools/banjo3ds/actor_pose'),
                '-I'+str(ROOT/'platform/3ds/source'),str(source),
                str(ROOT/'tools/banjo3ds/actor_pose/actor_pose.c'),
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
            cls.libs.append(lib)
        cls.hill=load_actor(ROOT/'assets/model/0388.model.bin','molehill',
                           (ROOT/'assets/anim/013D.anim.bin').read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        for lib in self.libs: lib.reset()

    def test_original_packet_and_baseline_export(self):
        info=parse_packet(self.hill.packet)
        closed=load_actor(ROOT/'assets/model/0388.model.bin','molehill',boneless=True)
        base=parse_packet(closed.packet)
        self.assertEqual((len(self.hill.packet),info.matrix_count,info.bone_slots,
                          info.load_count,info.corner_count,info.anim_last,info.anim_channels),
                         (1256,2,70,73,168,248,6))
        self.assertEqual((info.records,info.loads,info.corners,info.factor),
                         (base.records,base.loads,base.corners,base.factor))
        self.assertEqual(info.animation,(ROOT/'assets/anim/013D.anim.bin').read_bytes())
        original=[tuple(load[:3]) for load in base.loads]
        for phase in (0,1):
            self.assertEqual(reference_evaluate(self.hill.packet,phase)[2],original)
        self.assertNotEqual(reference_evaluate(self.hill.packet,.2)[2],original)
        generated=export_actor_header(ROOT/'assets/model/0387.model.bin',
                    ROOT/'assets/model/0388.model.bin',ROOT/'assets/anim/013B.anim.bin')
        self.assertEqual(generated,(ROOT/'platform/3ds/build/generated_actors.h').read_text())

    def test_dense_original_reference_parity_and_closed_endpoints(self):
        info=parse_packet(self.hill.packet)
        clip=ActorClip(info.animation,info.bone_slots)
        phases={0.,1.,.0001,.999999}
        phases.update(i/248 for i in range(249))
        phases.update((i+.37)/248 for i in range(248))
        for keys in clip.channels.values():
            for word,_ in keys:
                frame=word & 0x3fff
                for delta in (-.0001,0,.0001):
                    if 0<=frame+delta<=248: phases.add((frame+delta)/248)
        for phase in sorted(phases):
            phase=C.c_float(phase).value
            expected=[x for point in reference_evaluate(self.hill.packet,phase)[2] for x in point]
            for lib in self.libs:
                lib.phase_set(phase)
                self.assertEqual(lib.prepare(0),1)
                actual=lib.xyz()[:73*3]
                self.assertTrue(all(math.isfinite(x) and -200<=x<=200 for x in actual))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),.003)
                if phase in (0,1):
                    self.assertEqual(actual,[float(x) for load in info.loads for x in load[:3]])

    def test_once_duration_and_hold_with_independent_bottles_clock(self):
        for lib in self.libs:
            self.assertEqual(lib.prepare(0),1)
            self.assertEqual(lib.phase_get(),0)
            for i in range(89): lib.frame(.05,1)
            self.assertAlmostEqual(lib.phase_get(),89*.05/4.5,places=6)
            lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            final=list(lib.xyz()[:219])
            bottles=lib.bottles_phase()
            for i in range(200): lib.frame(.05,1)
            self.assertEqual(lib.phase_get(),1)
            self.assertEqual(list(lib.xyz()[:219]),final)
            self.assertNotEqual(lib.bottles_phase(),bottles)

    def test_hill_scatter_canaries_all_corners_uv_and_world(self):
        import struct
        info=parse_packet(self.hill.packet)
        for lib in self.libs:
            before=C.string_at(lib.bytes(),2019*24+64)
            world=C.string_at(lib.world_bytes(),2019*24)
            lib.phase_set(.2)
            self.assertEqual(lib.prepare(0),1)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            self.assertEqual(lib.publish(),1)
            after=C.string_at(lib.bytes(),len(before))
            self.assertEqual(before[:32],after[:32])
            self.assertEqual(before[32+168*24:],after[32+168*24:])
            self.assertNotEqual(before,after)
            for i,load in enumerate(info.corners):
                offset=32+i*24
                self.assertEqual(struct.unpack_from('3f',after,offset),tuple(lib.xyz()[load*3:load*3+3]))
                self.assertEqual(before[offset+12:offset+24],after[offset+12:offset+24])
            self.assertEqual(C.string_at(lib.world_bytes(),len(world)),world)
            self.assertEqual(lib.flush_valid(),1)
            self.assertEqual(lib.flush_count(),1)

    def test_failed_wait_and_prepare_prohibit_publication(self):
        for lib in self.libs:
            before=C.string_at(lib.bytes(),2019*24+64)
            lib.frame(.05,0)
            self.assertEqual(lib.flush_count(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            lib.frame(.05,1)
            self.assertEqual(lib.flush_count(),2)
            after=C.string_at(lib.bytes(),len(before))
            self.assertNotEqual(before[32:32+168*24],after[32:32+168*24])
            self.assertNotEqual(before[32+168*24:-32],after[32+168*24:-32])
            lib.reset();lib.fault_set(1);lib.frame(.05,1)
            self.assertEqual(lib.flush_count(),0)
            self.assertEqual(lib.phase_get(),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)

    def test_bad_metadata_pose_and_time_leave_clock_and_gpu_unchanged(self):
        for lib in self.libs:
            for fault in range(1,12):
                lib.reset();lib.fault_set(fault)
                before=C.string_at(lib.bytes(),2019*24+64)
                self.assertEqual(lib.prepare(.016),0)
                self.assertEqual(lib.phase_get(),0)
                self.assertEqual(lib.eval_count(),0 if fault>=4 else 1)
                self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
                self.assertEqual(lib.flush_count(),0)
            lib.reset()
            for dt in (-1,.051,1e30,math.nan,math.inf):
                self.assertEqual(lib.prepare(dt),0)
                self.assertEqual(lib.phase_get(),0)
            for phase in (-1,1.001,math.nan,math.inf):
                lib.phase_set(phase);self.assertEqual(lib.prepare(0),0)
            for mode in (1,2):
                lib.reset();self.assertEqual(lib.prepare(.016),1);lib.ownership(mode)
                self.assertEqual(lib.publish(),0);self.assertEqual(lib.flush_count(),0)

    def test_switch_requirements_control_isolation_and_unchanged_renderers(self):
        flags=dict(STATIC_BOTTLES=1,IDLE_ANIMATION=1,HILL_OPEN_ANIMATION=1)
        for flag in ('ISOLATION','TEXTURE_UPLOAD','VERTEX_INIT','HILL_DRAW','STATIC_BOTTLES','IDLE_ANIMATION'):
            result=preprocess(self.main,**dict(flags,**{flag:0}))
            self.assertNotEqual(result.returncode,0)
            self.assertIn('B2-P1 requires',result.stderr)
        control=preprocess(self.main,STATIC_BOTTLES=1,IDLE_ANIMATION=1).stdout
        for token in ('hillOpen','actor_hill_open_packet'):
            self.assertNotIn(token,control)
        for draw in ('sceneDrawStaticBottles','sceneDrawClosedMolehill','sceneDrawActorRange','sceneRender'):
            self.assertEqual(function(self.active,draw),function(control,draw))
        loop=self.active[self.active.index('while (aptMainLoop())'):]
        self.assertLess(loop.index('hillOpenPrepare(dt)'),loop.index('C3D_FrameBegin'))
        self.assertLess(loop.index('C3D_FrameBegin'),loop.index('hillOpenPublish()'))
        self.assertLess(loop.index('hillOpenPublish()'),loop.index('sceneRender();'))
        block=self.active[self.active.index('static double hillOpenSeconds;'):self.active.index('static float bottlesIdlePhase;')]
        for token in ('actor_pose_advance','bottlesIdle','linearAlloc','malloc','actor_pose_placement','013C','013A','0139'):
            self.assertNotIn(token,block)
