"""FIX7: execute the actual isolated update routines with the original A3P1 clip."""
import ctypes as C
import math
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.actor_mesh import export_actor_header, load_actor, reference_evaluate
from tools.banjo3ds.tests.test_actor_draw import MAIN, ROOT, preprocess, function


class ActorIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.main = MAIN.read_text()
        cls.active = preprocess(cls.main, STATIC_BOTTLES=1, IDLE_ANIMATION=1).stdout
        block = cls.active.split('static float bottlesIdlePhase;', 1)[1].split('static void sceneDrawActorRange', 1)[0]
        # The final attribute belongs to the following renderer, not this block.
        block = 'static float bottlesIdlePhase;' + block
        header = export_actor_header(ROOT/'assets/model/0387.model.bin',
                                    ROOT/'assets/model/0388.model.bin', ROOT/'assets/anim/013B.anim.bin')
        data = '\n'.join(re.findall(r'^#define ACTOR_.*', header, re.M))
        for name in ('actor_vertices', 'actor_bottles_packet'):
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
    return ok;
}
bool __real_actor_pose_evaluate(const uint8_t *, size_t, float, float *, float *, float *);
bool __wrap_actor_pose_evaluate(const uint8_t *p, size_t n, float phase, float *b, float *m, float *xyz) {
    ++evaluations;
    bool ok=__real_actor_pose_evaluate(p,n,phase,b,m,xyz);
    if (fault == 1) xyz[0]=NAN;
    if (fault == 2) xyz[1]=INFINITY;
    if (fault == 3) xyz[2]=401.0f;
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
    bottlesIdlePhase=0; flushes=0; fault=0; evaluations=0;
}
void phase_set(float p) { bottlesIdlePhase=p; }
float phase_get(void) { return bottlesIdlePhase; }
int prepare(float dt) { return bottlesIdlePrepare(dt); }
int publish(void) { return bottlesIdlePublish(); }
void ownership(int mode) { actor_vbo=mode == 1 ? NULL : vbo_data; }
const void *bytes(void) { return owned.bytes; }
const void *world_bytes(void) { return world; }
const float *xyz(void) { return bottlesIdleXYZ; }
unsigned flush_count(void) { return flushes; }
int flush_valid(void) { return flush_address == owned.bytes+32+168*24 && flush_size == 1851*24; }
'''
        cls.libs = []
        for opt in ('-O0', '-O2'):
            source = Path(cls.temp.name)/f'idle{opt}.c'
            source.write_text(prelude+vertex+'\n'+data+'\n'+block+wrapper)
            out = source.with_suffix('.so')
            subprocess.run(['cc',opt,'-shared','-fPIC','-Wall','-Wextra','-Werror',
                '-ffp-contract=off','-fno-fast-math','-fexcess-precision=standard',
                '-I'+str(ROOT/'tools/banjo3ds/actor_pose'),str(source),
                str(ROOT/'tools/banjo3ds/actor_pose/actor_pose.c'),
                '-Wl,--wrap=actor_pose_info', '-Wl,--wrap=actor_pose_evaluate','-lm','-o',str(out)],check=True,capture_output=True)
            lib=C.CDLL(str(out))
            lib.prepare.argtypes=[C.c_float];lib.phase_set.argtypes=[C.c_float]
            lib.phase_get.restype=C.c_float
            lib.bytes.restype=C.c_void_p;lib.world_bytes.restype=C.c_void_p
            lib.xyz.restype=C.POINTER(C.c_float)
            cls.libs.append(lib)
        cls.bottles=load_actor(ROOT/'assets/model/0387.model.bin','bottles',
                              (ROOT/'assets/anim/013B.anim.bin').read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        for lib in self.libs: lib.reset()

    def test_original_loop_endpoints_and_near_wrap_are_continuous(self):
        start=reference_evaluate(self.bottles.packet,0)[2]
        end=reference_evaluate(self.bottles.packet,1)[2]
        self.assertEqual(start,end)
        near=reference_evaluate(self.bottles.packet,0.999999)[2]
        self.assertLess(max(abs(a-b) for p,q in zip(start,near) for a,b in zip(p,q)),0.002)
        for lib in self.libs:
            lib.phase_set(C.c_float(1-0.05/7))
            self.assertEqual(lib.prepare(0.05),1)
            self.assertLess(lib.phase_get(),1e-6)
            self.assertEqual(lib.prepare(0),1)

    def test_deterministic_delta_time_and_seven_second_duration(self):
        phase=0.0
        for i in range(2000):
            dt=C.c_float((0,0.016,0.033,0.05)[i%4]).value
            step=C.c_float(dt/C.c_float(7).value).value
            phase=C.c_float(phase+step).value
            phase=C.c_float(phase-int(phase)).value
            for lib in self.libs:
                self.assertEqual(lib.prepare(dt),1)
                self.assertEqual(lib.phase_get(),phase)
        self.assertIn('ACTOR_BOTTLES_IDLE_DURATION 7.0f', export_actor_header(
            ROOT/'assets/model/0387.model.bin',ROOT/'assets/model/0388.model.bin',ROOT/'assets/anim/013B.anim.bin'))

    def test_dense_clip_output_is_finite_and_bounded(self):
        for lib in self.libs:
            for i in range(1001):
                lib.phase_set(i/1001)
                self.assertEqual(lib.prepare(0),1)
                self.assertTrue(all(math.isfinite(x) and -200<=x<=400 for x in lib.xyz()[:590*3]))

    def test_only_bottles_xyz_changes_with_canaries_and_world_untouched(self):
        for lib in self.libs:
            before=C.string_at(lib.bytes(),2019*24+64)
            world=C.string_at(lib.world_bytes(),2019*24)
            lib.phase_set(.4)
            self.assertEqual(lib.prepare(0),1)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before) # scratch only
            self.assertEqual(lib.publish(),1)
            after=C.string_at(lib.bytes(),len(before))
            first=32+168*24; end=32+2019*24
            self.assertEqual(before[:first],after[:first])
            self.assertEqual(before[end:],after[end:])
            self.assertNotEqual(before[first:end],after[first:end])
            for offset in range(first,end,24):
                self.assertEqual(before[offset+12:offset+24],after[offset+12:offset+24])
            self.assertEqual(C.string_at(lib.world_bytes(),len(world)),world)
            self.assertEqual(lib.flush_count(),1)
            self.assertEqual(lib.flush_valid(),1)

    def test_invalid_time_and_phase_leave_published_geometry_unchanged(self):
        for lib in self.libs:
            before=C.string_at(lib.bytes(),2019*24+64)
            for dt in (-1,.051,1e30,math.nan,math.inf):
                self.assertEqual(lib.prepare(dt),0)
                self.assertEqual(lib.phase_get(),0)
            for phase in (-1,1,math.nan,math.inf):
                lib.phase_set(phase)
                self.assertEqual(lib.prepare(.016),0)
            self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
            self.assertEqual(lib.flush_count(),0)

    def test_bad_pose_and_capacity_mismatch_reject_before_gpu_writes(self):
        for lib in self.libs:
            for fault in (1,2,3,4):
                lib.reset();lib.fault_set(fault)
                before=C.string_at(lib.bytes(),2019*24+64)
                self.assertEqual(lib.prepare(.016),0)
                self.assertEqual(lib.phase_get(),0)
                self.assertEqual(lib.eval_count(),0 if fault == 4 else 1)
                self.assertEqual(C.string_at(lib.bytes(),len(before)),before)
                self.assertEqual(lib.flush_count(),0)

    def test_null_or_world_alias_cannot_be_published(self):
        for lib in self.libs:
            for mode in (1,2):
                lib.reset();self.assertEqual(lib.prepare(.016),1)
                lib.ownership(mode)
                self.assertEqual(lib.publish(),0)
                self.assertEqual(lib.flush_count(),0)
                self.assertEqual(C.string_at(lib.world_bytes(),2019*24),b'\x5a'*(2019*24))

    def test_publication_requires_successful_gpu_wait_and_prepare(self):
        loop=self.active[self.active.index('while (aptMainLoop())'):]
        prepare=loop.index('bool bottlesIdleReady = bottlesIdlePrepare(dt);')
        wait=loop.index('if (!C3D_FrameBegin(C3D_FRAME_SYNCDRAW)) continue;')
        publish=loop.index('if (bottlesIdleReady) {\n            if (bottlesIdlePublish())')
        self.assertLess(prepare,wait);self.assertLess(wait,publish)
        self.assertLess(publish,loop.index('sceneRender();'))
        self.assertEqual(loop.count('bottlesIdlePublish()'),1)

    def test_fix6_switch_excludes_all_runtime_pose_updates(self):
        result=preprocess(self.main,STATIC_BOTTLES=1,IDLE_ANIMATION=0)
        self.assertEqual(result.returncode,0,result.stderr)
        for token in ('bottlesIdle','actor_pose_','actor_bottles_phase'):
            self.assertNotIn(token,result.stdout)
        for draw in ('sceneDrawStaticBottles','sceneDrawClosedMolehill','sceneDrawActorRange'):
            self.assertEqual(function(self.active,draw),function(result.stdout,draw))

    def test_fix7_requires_full_validated_rendering_configuration(self):
        for flag in ('ISOLATION','TEXTURE_UPLOAD','VERTEX_INIT','HILL_DRAW','STATIC_BOTTLES'):
            flags=dict(STATIC_BOTTLES=1,IDLE_ANIMATION=1);flags[flag]=0
            result=preprocess(self.main,**flags)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('requires',result.stderr)

    def test_no_molehill_pose_or_actor_behaviour_can_run(self):
        block=self.active.split('static float bottlesIdlePhase;',1)[1].split('static void sceneDrawActorRange',1)[0]
        calls=set(re.findall(r'\b(\w+)\s*\(',block))
        self.assertEqual(calls,{'__attribute__','_Static_assert','bottlesIdlePrepare',
            'bottlesIdlePublish','if','for','isfinite','sizeof','actor_pose_info',
            'actor_pose_advance','actor_pose_evaluate','actor_pose_scatter','GSPGPU_FlushDataCache'})
        for token in ('actor_molehill_packet','linearAlloc','malloc','actorDiagStage(',
                      'sceneDrawPlacedActors(','actor_pose_placement('):
            self.assertNotIn(token,block)
        for token in ('actorDiagStage(', 'sceneDrawPlacedActors(', 'actor_diag_stage', 'actor_bottles_phase'):
            self.assertNotIn(token,self.active)
