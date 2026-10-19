"""FIX5/FIX6 isolation, fixed geometry, and deferred GPU state regressions."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.actor_mesh import export_actor_header, load_actor, parse_packet

ROOT = Path(__file__).resolve().parents[3]
MAIN = ROOT / 'platform/3ds/source/main.c'


def preprocess(main, **flags):
    # Only preprocess the control flow: SDK types need not exist for -E.
    source = re.sub(r'^#include[^\n]*', '', main, flags=re.M)
    args = ['cc', '-E', '-P', '-x', 'c', '-', '-DBANJO_MATERIAL_COUNT=1',
            '-DBANJO_TEXTURE_COUNT=1', '-DBANJO_ACTOR_DRAW_COUNT=28']
    defaults = dict(ISOLATION=1, TEXTURE_UPLOAD=1, VERTEX_INIT=1, HILL_DRAW=1, STATIC_BOTTLES=0, IDLE_ANIMATION=0)
    defaults.update(flags)
    args += [f'-DBANJO3DS_ACTOR_{key}={value}' for key, value in defaults.items()]
    return subprocess.run(args, input=source, text=True, capture_output=True)


def function(source, name):
    start = source.index('static void ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ActorDrawTests(unittest.TestCase):
    def test_fix5_preprocessor_excludes_bottles_and_all_pose_calls(self):
        result = preprocess(MAIN.read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        active = result.stdout
        for token in ('sceneDrawPlacedActors(', 'actor_pose_', 'actor_bottles_phase',
                      'actorDiagStage(', 'actorDiagClear(', 'sceneDrawActorRange(ACTOR_BOTTLES_FIRST_DRAW'):
            self.assertNotIn(token, active)
        self.assertIn('sceneDrawClosedMolehill(&render_state);', active)
        self.assertIn('initActorVertexBuffer();', active)
        self.assertIn('uploadActorTextures();', active)
        self.assertIn('C3D_RenderTargetClear(target, C3D_CLEAR_ALL, 0x68B0D8FF, 0);', active)
        draw = function(active, 'sceneDrawClosedMolehill')
        self.assertEqual(draw.count('sceneDrawActorRange('), 1)
        self.assertIn('ACTOR_HILL_FIRST_DRAW, ACTOR_HILL_DRAW_COUNT', draw)
        self.assertNotIn('linearAlloc', draw)
        loop = active[active.index('while (aptMainLoop())'):]
        self.assertNotIn('actor_vbo', loop)
        self.assertNotIn('memcpy(actor_', loop)
        render = function(active, 'sceneRender')
        self.assertLess(render.index('sceneDrawClosedMolehill('),
                        render.index('if (BANJO_XLU_DRAW_COUNT > 0)'))

    def test_fix5_rejects_unsafe_macro_combinations(self):
        for flag in ('ISOLATION', 'TEXTURE_UPLOAD', 'VERTEX_INIT'):
            with self.subTest(flag=flag):
                result = preprocess(MAIN.read_text(), **{flag: 0})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FIX5 requires', result.stderr)

    def test_fix4_control_still_has_no_draw_or_pose(self):
        result = preprocess(MAIN.read_text(), HILL_DRAW=0)
        self.assertEqual(result.returncode, 0, result.stderr)
        for token in ('sceneDrawClosedMolehill(', 'sceneDrawActorRange(', 'actor_pose_'):
            self.assertNotIn(token, result.stdout)

    def test_closed_geometry_matches_original_vertices_and_draw_ranges(self):
        hill = load_actor(ROOT / 'assets/model/0388.model.bin', 'molehill', boneless=True)
        info = parse_packet(hill.packet)
        self.assertTrue(info.boneless)
        self.assertEqual(info.anim_bytes, 0)
        self.assertEqual(len(hill.corners), 168)
        for vertex, load in zip(hill.render.vertices, hill.loads):
            self.assertEqual((vertex.x, vertex.y, vertex.z), load[:3])
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        batches = build_draw_batches(hill.render.triangles)
        self.assertEqual([(d[0], d[1]) for d in batches], [(0, 24), (24, 48), (72, 48), (120, 48)])
        self.assertEqual([d[3] for d in batches], [1, 1, 1, 3])
        self.assertEqual(len(hill.render.textures), 2)

    def test_fix6_compiles_only_static_draws_without_actor_updates(self):
        result = preprocess(MAIN.read_text(), STATIC_BOTTLES=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        active = result.stdout
        for token in ('actor_pose_', 'actor_bottles_phase', 'actorDiagStage(',
                      'actorDiagClear(', 'sceneDrawPlacedActors('):
            self.assertNotIn(token, active)
        render = function(active, 'sceneRender')
        self.assertEqual(render.count('sceneDrawStaticBottles(&render_state);'), 1)
        self.assertLess(render.index('sceneDrawClosedMolehill('), render.index('sceneDrawStaticBottles('))
        self.assertLess(render.index('sceneDrawStaticBottles('), render.index('if (BANJO_XLU_DRAW_COUNT > 0)'))
        draw = function(active, 'sceneDrawStaticBottles')
        self.assertEqual(draw.count('sceneDrawActorRange('), 1)
        self.assertIn('ACTOR_BOTTLES_FIRST_DRAW, ACTOR_BOTTLES_DRAW_COUNT', draw)
        self.assertIn('Mtx_Translate(&world, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z, true)', draw)
        # The static actor has no update or interaction dispatch: these are its
        # complete call sites, all matrix/state/draw operations.
        calls = set(re.findall(r'\b(\w+)\s*\(', draw[draw.index('{'):]))
        self.assertEqual(calls, {'Mtx_Identity', 'Mtx_Translate', 'Mtx_Multiply',
            'C3D_FVUnifMtx4x4', 'C3D_GetBufInfo', 'BufInfo_Init', 'BufInfo_Add',
            'sizeof', 'sceneDrawActorRange', 'C3D_SetBufInfo'})
        loop = active[active.index('while (aptMainLoop())'):]
        self.assertNotIn('actor_vbo', loop)
        self.assertNotIn('memcpy(actor_', loop)
        self.assertIn('C3D_GetCmdBufUsage()', loop)
        self.assertIn('actor-isolation: FIX6 closed molehill and static Bottles', active)

    def test_fix6_requires_the_entire_fix5_configuration(self):
        for flag in ('ISOLATION', 'TEXTURE_UPLOAD', 'VERTEX_INIT', 'HILL_DRAW'):
            with self.subTest(flag=flag):
                result = preprocess(MAIN.read_text(), STATIC_BOTTLES=1, **{flag: 0})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('requires', result.stderr)

    def test_bottles_export_is_the_valid_idle_phase_zero_pose(self):
        from tools.banjo3ds.actor_mesh import reference_evaluate
        from tools.banjo3ds.export_3ds_model import build_draw_batches
        bottles = load_actor(ROOT / 'assets/model/0387.model.bin', 'bottles',
                             (ROOT / 'assets/anim/013B.anim.bin').read_bytes())
        xyz = reference_evaluate(bottles.packet, 0.0)[2]
        self.assertEqual(len(bottles.corners), 1851)
        self.assertEqual([(v.x, v.y, v.z) for v in bottles.render.vertices], xyz)
        batches = build_draw_batches(bottles.render.triangles)
        self.assertEqual(len(batches), 16)
        self.assertEqual(sum(d[1] for d in batches), 1851)
        for first, count, _material, mode, _combine, cull in batches:
            self.assertLessEqual(first + count, 1851)
            self.assertEqual(count % 3, 0)
            self.assertIn(mode, (1, 3))
            self.assertIn(cull, (0, 2))
        header = export_actor_header(ROOT / 'assets/model/0387.model.bin',
                                     ROOT / 'assets/model/0388.model.bin',
                                     ROOT / 'assets/anim/013B.anim.bin')
        vertices = header.split('actor_vertices[] = {', 1)[1].split('};', 1)[0]
        records = re.findall(r'\{([^}]+)\}', vertices)[168:]
        self.assertEqual(len(records), 1851)
        for record, corner in zip(records, bottles.corners):
            point = [float(v.strip().rstrip('f')) for v in record.split(',')[:3]]
            for value, expected in zip(point, xyz[corner]):
                self.assertAlmostEqual(value, expected, places=6)

    def test_fix6_restores_world_state_after_each_static_actor(self):
        self.check_gpu_buffer_restore(static_bottles=True)

    def test_gpu_buffer_restore_survives_draw_consuming_dirty_flag(self):
        self.check_gpu_buffer_restore(static_bottles=False)

    def check_gpu_buffer_restore(self, static_bottles):
        """Execute actual draw functions against Citro3D's deferred binding contract.

        The mutation check demonstrates that omitting SetBufInfo reproduces the
        stale actor VBO on the next world draw, even though CPU state says world.
        """
        main = preprocess(MAIN.read_text(), STATIC_BOTTLES=int(static_bottles)).stdout
        routines = '\n'.join(function(main, name) for name in
            ('sceneDrawRange', 'sceneDrawActorRange', 'sceneDrawClosedMolehill'))
        if static_bottles:
            routines += '\n' + function(main, 'sceneDrawStaticBottles')
        model = (ROOT / 'platform/3ds/source/generated_model.h').read_text()
        types = '\n'.join(re.search(r'typedef struct \{[^}]*\} ' + name + ';', model).group()
                          for name in ('Banjo3DSVertex', 'Banjo3DSCombine', 'Banjo3DSMaterial', 'Banjo3DSDraw'))
        header = export_actor_header(ROOT / 'assets/model/0387.model.bin',
                                     ROOT / 'assets/model/0388.model.bin',
                                     ROOT / 'assets/anim/013B.anim.bin')
        data = '\n'.join(re.findall(r'^#define ACTOR_.*', header, re.M))
        for name in ('actor_draws', 'actor_materials'):
            data += '\n' + re.search(r'static const [^\n]* ' + name + r'\[\] = \{.*?\n\};', header, re.S).group()
        prelude = r'''
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#define GPU_TRIANGLES 0
#define GPU_VERTEX_SHADER 0
#define RENDERER_CULL_SKIP -1
#define GPU_CULLMODE int
#define C3D_Both 0
#define GPU_PRIMARY_COLOR 0
#define GPU_REPLACE 0
static const Banjo3DSDraw banjo_draws[] = {
    {12000, 48, 0, 1, 2, {1,3,5,3,1,7,4,7,0,15,4,7,0,7,5,7}},
    {12048, 6, -1, 1, 2, {0}},
};
static const Banjo3DSMaterial banjo_materials[] = {{0}};
static int textures[] = {100};
typedef int C3D_TexEnv;
static C3D_TexEnv env;
static int sampling;
static C3D_TexEnv *C3D_GetTexEnv(int index) { (void)index; return &env; }
static void resetTexEnvs(void) { sampling=0; }
static void C3D_TexEnvSrc(C3D_TexEnv *e, int a, int b, int c, int d) {
    (void)e; (void)a; (void)b; (void)c; (void)d; sampling=0;
}
static void C3D_TexEnvFunc(C3D_TexEnv *e, int a, int b) { (void)e; (void)a; (void)b; }
typedef struct { float m[4][4]; } C3D_Mtx;
typedef struct { const void *data; } C3D_BufInfo;
typedef struct { unsigned primitive_color, environment_color; } Banjo3DSRenderState;
static int failures, drawCount, skip, isWorldDraw, boundTexture;
static int actor_textures[ACTOR_TEXTURE_COUNT]={0,1,2,3,4};
static char actorMemory, worldMemory;
static void *actor_vbo = &actorMemory, *vbo_data = &worldMemory;
static int uLoc_modelView, viewWindingParity;
static C3D_Mtx modelView, uniform;
static C3D_BufInfo cpuBuffer;
static const void *gpuBuffer;
static bool dirty;
static void check(bool ok) { if (!ok) ++failures; }
static C3D_BufInfo *C3D_GetBufInfo(void) { dirty = true; return &cpuBuffer; }
static void BufInfo_Init(C3D_BufInfo *b) { b->data = NULL; }
static void BufInfo_Add(C3D_BufInfo *b, const void *data, size_t stride, int count, int perm) {
    check(stride == 24 && count == 3 && perm == 0x210); b->data = data;
}
static void C3D_SetBufInfo(C3D_BufInfo *b) { cpuBuffer = *b; dirty = true; }
static void Mtx_Identity(C3D_Mtx *m) {
    memset(m, 0, sizeof(*m)); for (int i=0; i<4; ++i) m->m[i][i]=1;
}
static void Mtx_Translate(C3D_Mtx *m, float x, float y, float z, bool right) {
    check(right); m->m[0][3]=x; m->m[1][3]=y; m->m[2][3]=z;
}
static void Mtx_Multiply(C3D_Mtx *out, const C3D_Mtx *a, const C3D_Mtx *b) {
    memset(out,0,sizeof(*out));
    for(int i=0;i<4;i++) for(int j=0;j<4;j++) for(int k=0;k<4;k++) out->m[i][j]+=a->m[i][k]*b->m[k][j];
}
static void C3D_FVUnifMtx4x4(int shader, int loc, const C3D_Mtx *m) {
    check(shader==0 && loc==uLoc_modelView); uniform=*m;
}
static int rendererCullMode(int mode, int parity) { check((mode==0 || mode==2) && parity==0); return skip && !isWorldDraw ? -1 : mode; }
static void C3D_CullFace(int mode) { check(mode==0 || mode==2); }
static void applyCombine(const Banjo3DSCombine *combine, const Banjo3DSRenderState *state) {
    check(combine != NULL && state != NULL); sampling=combine->a0!=6;
}
static void C3D_TexBind(int unit, int *tex) { check(unit==0); boundTexture=*tex; }
static void C3D_DrawArrays(int primitive, unsigned first, unsigned count) {
    if(dirty) { gpuBuffer=cpuBuffer.data; dirty=false; }
    check(primitive==0);
    if(isWorldDraw) {
        check(gpuBuffer==vbo_data);
        check(memcmp(&uniform,&modelView,sizeof uniform)==0);
        check(first==12000 ? (sampling && boundTexture==100) : !sampling);
    } else {
        check(gpuBuffer==actor_vbo);
        unsigned i=0;
        while(i<ACTOR_DRAW_COUNT && actor_draws[i].first_vertex!=first) ++i;
        check(i<ACTOR_DRAW_COUNT);
        if(i<ACTOR_DRAW_COUNT) {
            const Banjo3DSDraw *draw=&actor_draws[i];
            check(count==draw->vertex_count && first+count<=ACTOR_VERTEX_COUNT && count%3==0);
            if(draw->material_index>=0)
                check(boundTexture==(int)actor_materials[draw->material_index].texture_slot);
            else
                check(!sampling);
        }
        check(uniform.m[0][3]==4507 && uniform.m[1][3]==-23 && uniform.m[2][3]==2787);
        ++drawCount;
    }
}
'''
        driver = r'''
int main(void) {
    Banjo3DSRenderState state={0};
    Mtx_Identity(&modelView); modelView.m[0][0]=2; modelView.m[0][3]=7; modelView.m[1][3]=11; modelView.m[2][3]=13;
    cpuBuffer.data=vbo_data; gpuBuffer=vbo_data;
    for(int frame=0; frame<3; ++frame) {
        skip=frame==2; isWorldDraw=0;
        sceneDrawClosedMolehill(&state);
        check(cpuBuffer.data==vbo_data);
        isWorldDraw=1; sceneDrawRange(0, 2, &state);
        STATIC_BOTTLES_DRAW
    }
    check(drawCount==8);
    return failures ? 1 : 0;
}
'''
        driver = driver.replace('STATIC_BOTTLES_DRAW', (
            'isWorldDraw=0; sceneDrawStaticBottles(&state); '
            'check(cpuBuffer.data==vbo_data); '
            'isWorldDraw=1; sceneDrawRange(0, 2, &state);') if static_bottles else '')
        driver = driver.replace('check(drawCount==8);',
                                f'check(drawCount=={40 if static_bottles else 8});')
        with tempfile.TemporaryDirectory(prefix='banjo-static-draw-') as tmp:
            for broken in (False, True):
                code = routines.replace('C3D_SetBufInfo(bufInfo);', '') if broken else routines
                # Keep the mock definition used under -Werror for the negative control.
                code += '\n' + driver.replace('cpuBuffer.data=vbo_data;', '(void)C3D_SetBufInfo; cpuBuffer.data=vbo_data;')
                source = Path(tmp) / 'draw.c'
                source.write_text(types + '\n' + data + '\n' + prelude + code)
                binary = Path(tmp) / 'draw'
                result = subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                                         '-O2', str(source), '-o', str(binary)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([str(binary)], capture_output=True)
                self.assertEqual(result.returncode, 1 if broken else 0)
