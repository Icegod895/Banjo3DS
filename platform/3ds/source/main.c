#include <3ds.h>
#include <citro3d.h>
#include <string.h>
#include <math.h>

#include "vshader_shbin.h"
#include "movement.h"
#include "walk_animation.h"
#include "generated_model.h"

#define CLEAR_COLOR 0x68B0D8FF

#define DISPLAY_TRANSFER_FLAGS \
    (GX_TRANSFER_FLIP_VERT(0) | GX_TRANSFER_OUT_TILED(0) | \
     GX_TRANSFER_RAW_COPY(0) | GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGBA8) | \
     GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8) | \
     GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO))

static DVLB_s *vshader_dvlb;
static shaderProgram_s program;
static int uLoc_projection, uLoc_modelView;
static C3D_Mtx projection, modelView;
static void *vbo_data;
static WalkAnimation walkAnimation;
/* Debugger-visible CPU measurements: evaluator + corner XYZ propagation,
 * excluding GPU wait/cache flush. No console work in the measured interval. */
volatile float banjoPoseLastUs, banjoPoseMaxUs;
volatile u32 banjoPoseUpdateCount;

#if BANJO_TEXTURE_COUNT > 0
static C3D_Tex textures[BANJO_TEXTURE_COUNT];
#endif

#if BANJO_TEXTURE_COUNT > 0
static GPU_TEXTURE_WRAP_PARAM textureWrapTo3DS(int wrap)
{
    switch (wrap) {
        case BANJO_TEXTURE_WRAP_WRAP:
            return GPU_REPEAT;
        case BANJO_TEXTURE_WRAP_MIRROR:
            return GPU_MIRRORED_REPEAT;
        case BANJO_TEXTURE_WRAP_CLAMP:
            return GPU_CLAMP_TO_EDGE;
        case BANJO_TEXTURE_WRAP_MIRROR_CLAMP:
        default:
            return GPU_CLAMP_TO_EDGE;
    }
}
#endif

static struct {
    float yawDegrees, pitchDegrees, zoom;
    float eyeDistance;
    float focusX, focusY, focusZ;
} camera;

static MovementActor actor = {0.0f, 1800.0f, 0.0f, 0.0f};

static float cameraClamp(float value, float minimum, float maximum)
{
    return value < minimum ? minimum : value > maximum ? maximum : value;
}

static float cameraPadAxis(s16 value)
{
    const float deadzone = 15.0f;
    float axis = value;
    if (axis > deadzone)
        return cameraClamp((axis - deadzone) / (156.0f - deadzone), 0.0f, 1.0f);
    if (axis < -deadzone)
        return cameraClamp((axis + deadzone) / (156.0f - deadzone), -1.0f, 0.0f);
    return 0.0f;
}

static void cameraReset(void)
{
    camera.yawDegrees = 145.0f;
    camera.pitchDegrees = -20.0f;
    camera.zoom = 1.0f;
    camera.eyeDistance = 20000.0f;
    camera.focusX = 102.5f;
    camera.focusY = 189.5f;
    camera.focusZ = 511.5f;
}

static void cameraUpdateMatrices(void)
{
    Mtx_OrthoTilt(&projection,
        -1500.0f / camera.zoom, 1500.0f / camera.zoom,
        -900.0f / camera.zoom, 900.0f / camera.zoom,
        -11000.0f, 11000.0f, true);
    Mtx_Identity(&modelView);
    Mtx_RotateX(&modelView, C3D_AngleFromDegrees(camera.pitchDegrees), true);
    Mtx_RotateY(&modelView, C3D_AngleFromDegrees(camera.yawDegrees), true);
    Mtx_Translate(&modelView, -camera.focusX, -camera.focusY, -camera.focusZ, true);
}

static void cameraUpdate(u32 down, u32 held, const circlePosition *pad, float dt)
{
    if (down & KEY_X) {
        cameraReset();
        cameraUpdateMatrices();
        return;
    }

    camera.yawDegrees += ((held & KEY_Y) ? cameraPadAxis(pad->dx) : 0.0f) * 90.0f * dt;
    if (camera.yawDegrees > 180.0f) camera.yawDegrees -= 360.0f;
    if (camera.yawDegrees < -180.0f) camera.yawDegrees += 360.0f;
    camera.pitchDegrees = cameraClamp(
        camera.pitchDegrees + ((held & KEY_Y) ? cameraPadAxis(pad->dy) : 0.0f) * 90.0f * dt, -85.0f, 85.0f);
    int zoomDirection = ((held & KEY_R) != 0) - ((held & KEY_L) != 0);
    camera.zoom = cameraClamp(camera.zoom * expf(zoomDirection * dt), 0.1f, 20.0f);

    float panX = (((held & KEY_DRIGHT) != 0) - ((held & KEY_DLEFT) != 0))
        * 600.0f * dt / camera.zoom;
    float panY = (((held & KEY_DUP) != 0) - ((held & KEY_DDOWN) != 0))
        * 600.0f * dt / camera.zoom;
    C3D_Mtx rotation;
    Mtx_Identity(&rotation);
    Mtx_RotateX(&rotation, C3D_AngleFromDegrees(camera.pitchDegrees), true);
    Mtx_RotateY(&rotation, C3D_AngleFromDegrees(camera.yawDegrees), true);
    // Transform view-plane movement back to model space using transpose(R).
    camera.focusX += rotation.r[0].x * panX + rotation.r[1].x * panY;
    camera.focusY += rotation.r[0].y * panX + rotation.r[1].y * panY;
    camera.focusZ += rotation.r[0].z * panX + rotation.r[1].z * panY;
    cameraUpdateMatrices();
}

static void sceneInit(void)
{
    vshader_dvlb = DVLB_ParseFile((u32 *)vshader_shbin, vshader_shbin_size);
    shaderProgramInit(&program);
    shaderProgramSetVsh(&program, &vshader_dvlb->DVLE[0]);
    C3D_BindProgram(&program);

    uLoc_projection =
        shaderInstanceGetUniformLocation(program.vertexShader, "projection");
    uLoc_modelView =
        shaderInstanceGetUniformLocation(program.vertexShader, "modelView");

    C3D_AttrInfo *attrInfo = C3D_GetAttrInfo();
    AttrInfo_Init(attrInfo);
    AttrInfo_AddLoader(attrInfo, 0, GPU_FLOAT, 3);
    AttrInfo_AddLoader(attrInfo, 1, GPU_FLOAT, 2);
    AttrInfo_AddLoader(attrInfo, 2, GPU_UNSIGNED_BYTE, 4);

    cameraReset();
    cameraUpdateMatrices();

    vbo_data = linearAlloc(sizeof(banjo_vertices));
    memcpy(vbo_data, banjo_vertices, sizeof(banjo_vertices));

    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);
#if BANJO_TEXTURE_COUNT > 0
    for (unsigned int i = 0; i < BANJO_TEXTURE_COUNT; i++) {
        C3D_TexInitWithParams(
            &textures[i],
            NULL,
            (C3D_TexInitParams){
                banjo_textures[i].width,
                banjo_textures[i].height,
                banjo_textures[i].mipmap_count,
                GPU_RGBA8,
                GPU_TEX_2D,
                false
            }
        );
        C3D_TexLoadImage(
            &textures[i],
            banjo_textures[i].data,
            GPU_TEXFACE_2D,
            0
        );

        for (
            unsigned int level = 1;
            level <= banjo_textures[i].mipmap_count;
            level++
        ) {
            C3D_TexLoadImage(
                &textures[i],
                banjo_textures[i].mipmaps[level - 1],
                GPU_TEXFACE_2D,
                level
            );
        }
        if (banjo_textures[i].mipmap_count > 0) {
            C3D_TexSetFilter(&textures[i], GPU_LINEAR, GPU_LINEAR);
        } else {
            C3D_TexSetFilter(&textures[i], GPU_NEAREST, GPU_NEAREST);
        }
        C3D_TexSetFilterMipmap(&textures[i], GPU_LINEAR);
        C3D_TexSetWrap(
            &textures[i],
            textureWrapTo3DS(BANJO_TEXTURE_WRAP_S),
            textureWrapTo3DS(BANJO_TEXTURE_WRAP_T)
        );
    }
#endif

    C3D_TexEnv *env = C3D_GetTexEnv(0);
    C3D_TexEnvInit(env);
    C3D_TexEnvSrc(
        env,
        C3D_Both,
        GPU_TEXTURE0,
        GPU_PRIMARY_COLOR,
        GPU_PRIMARY_COLOR
    );
    C3D_TexEnvFunc(env, C3D_Both, GPU_MODULATE);
}

typedef struct {
    u32 primitive_color;
    u32 environment_color;
} Banjo3DSRenderState;

static void resetTexEnvs(void)
{
    for (int i = 0; i < 6; i++) {
        C3D_TexEnvInit(C3D_GetTexEnv(i));
    }
}

static void applyCombine(
    const Banjo3DSCombine *combine,
    const Banjo3DSRenderState *state
)
{
    resetTexEnvs();
    C3D_TexEnv *env = C3D_GetTexEnv(0);
    C3D_TexEnvSrc(
        env,
        C3D_Both,
        GPU_TEXTURE0,
        GPU_PRIMARY_COLOR,
        GPU_PRIMARY_COLOR
    );
    C3D_TexEnvFunc(env, C3D_Both, GPU_MODULATE);
    if (
        combine->a0 == 1 &&
        combine->b0 == 3 &&
        combine->c0 == 5 &&
        combine->d0 == 3 &&
        combine->Aa0 == 1 &&
        combine->Ab0 == 7 &&
        combine->Ac0 == 4 &&
        combine->Ad0 == 7 &&
        combine->a1 == 0 &&
        combine->b1 == 15 &&
        combine->c1 == 4 &&
        combine->d1 == 7 &&
        combine->Aa1 == 0 &&
        combine->Ab1 == 7 &&
        combine->Ac1 == 5 &&
        combine->Ad1 == 7
    ) {
        C3D_TexEnvColor(env, state->environment_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_CONSTANT,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_CONSTANT,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvFunc(env, C3D_Both, GPU_REPLACE);

        env = C3D_GetTexEnv(1);
        C3D_TexEnvInit(env);
        C3D_TexEnvColor(env, state->primitive_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_TEXTURE0,
            GPU_CONSTANT,
            GPU_PREVIOUS
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_INTERPOLATE);
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_REPLACE);

        env = C3D_GetTexEnv(2);
        C3D_TexEnvInit(env);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_TEXTURE0,
            GPU_TEXTURE0
        );
        C3D_TexEnvFunc(env, C3D_Both, GPU_MODULATE);

        env = C3D_GetTexEnv(3);
        C3D_TexEnvInit(env);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_REPLACE);
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_MODULATE);
        return;
    }
    if (
        combine->a0 == 6 &&
        combine->b0 == 3 &&
        combine->c0 == 5 &&
        combine->d0 == 3 &&
        combine->Aa0 == 7 &&
        combine->Ab0 == 7 &&
        combine->Ac0 == 7 &&
        combine->Ad0 == 4 &&
        combine->a1 == 0 &&
        combine->b1 == 15 &&
        combine->c1 == 4 &&
        combine->d1 == 7 &&
        combine->Aa1 == 0 &&
        combine->Ab1 == 7 &&
        combine->Ac1 == 5 &&
        combine->Ad1 == 7
    ) {
        C3D_TexEnvColor(env, state->primitive_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_CONSTANT,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR
        );
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_REPLACE);
        C3D_TexEnvOpRgb(
            env,
            GPU_TEVOP_RGB_ONE_MINUS_SRC_COLOR,
            GPU_TEVOP_RGB_SRC_COLOR,
            GPU_TEVOP_RGB_SRC_COLOR
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_REPLACE);
        env = C3D_GetTexEnv(1);
        C3D_TexEnvInit(env);
        C3D_TexEnvColor(env, state->environment_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_MODULATE);
        C3D_TexEnvFunc(env, C3D_RGB, GPU_MODULATE);
        env = C3D_GetTexEnv(2);
        C3D_TexEnvInit(env);
        C3D_TexEnvColor(env, state->primitive_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_REPLACE);
        C3D_TexEnvFunc(env, C3D_RGB, GPU_ADD);
        env = C3D_GetTexEnv(3);
        C3D_TexEnvInit(env);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_REPLACE);
        C3D_TexEnvFunc(env, C3D_RGB, GPU_MODULATE);
        return;
    }
    if (
        combine->a0 == 2 &&
        combine->b0 == 1 &&
        combine->c0 == 13 &&
        combine->d0 == 1 &&
        combine->Aa0 == 1 &&
        combine->Ab0 == 7 &&
        combine->Ac0 == 4 &&
        combine->Ad0 == 7 &&
        combine->a1 == 0 &&
        combine->b1 == 15 &&
        combine->c1 == 4 &&
        combine->d1 == 7 &&
        combine->Aa1 == 0 &&
        combine->Ab1 == 7 &&
        combine->Ac1 == 5 &&
        combine->Ad1 == 7
    ) {
        /*
         * PICA mip filtering approximates the N64's explicit
         * TEXEL0/TEXEL1 LOD_FRACTION blend. Unlike the N64, it also
         * blends alpha between mip levels and uses conventional linear
         * filtering instead of the N64's three-point filter.
         */
        C3D_TexEnvSrc(
            env,
            C3D_Both,
            GPU_TEXTURE0,
            GPU_PRIMARY_COLOR,
            GPU_PRIMARY_COLOR
        );
        C3D_TexEnvFunc(env, C3D_Both, GPU_MODULATE);

        env = C3D_GetTexEnv(1);
        C3D_TexEnvInit(env);
        C3D_TexEnvColor(env, state->environment_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_REPLACE);
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_MODULATE);
        return;
    }
    if (
        combine->a0 == 15 &&
        combine->b0 == 15 &&
        combine->c0 == 31 &&
        combine->d0 == 1 &&
        combine->Aa0 == 1 &&
        combine->Ab0 == 7 &&
        combine->Ac0 == 4 &&
        combine->Ad0 == 7 &&
        combine->a1 == 15 &&
        combine->b1 == 15 &&
        combine->c1 == 31 &&
        combine->d1 == 0 &&
        combine->Aa1 == 0 &&
        combine->Ab1 == 7 &&
        combine->Ac1 == 5 &&
        combine->Ad1 == 7
    ) {
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_TEXTURE0,
            GPU_TEXTURE0,
            GPU_TEXTURE0
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_REPLACE);
        env = C3D_GetTexEnv(1);
        C3D_TexEnvInit(env);
        C3D_TexEnvColor(env, state->environment_color);
        C3D_TexEnvSrc(
            env,
            C3D_RGB,
            GPU_PREVIOUS,
            GPU_PREVIOUS,
            GPU_PREVIOUS
        );
        C3D_TexEnvSrc(
            env,
            C3D_Alpha,
            GPU_PREVIOUS,
            GPU_CONSTANT,
            GPU_CONSTANT
        );
        C3D_TexEnvFunc(env, C3D_RGB, GPU_REPLACE);
        C3D_TexEnvFunc(env, C3D_Alpha, GPU_MODULATE);
        return;
    }
}

static void sceneDrawRange(unsigned int first, unsigned int count,
    const Banjo3DSRenderState* render_state)
{
    for (unsigned int i = first; i < first + count; i++) {
        const Banjo3DSDraw *draw = &banjo_draws[i];
        // This left-handed viewer preserves N64 front faces as clockwise.
        switch (draw->cull_mode) {
            case BANJO_CULL_BOTH:
                continue;
            case BANJO_CULL_BACK:
                C3D_CullFace(GPU_CULL_FRONT_CCW);
                break;
            case BANJO_CULL_FRONT:
                C3D_CullFace(GPU_CULL_BACK_CCW);
                break;
            case BANJO_CULL_NONE:
                C3D_CullFace(GPU_CULL_NONE);
                break;
        }

#if BANJO_MATERIAL_COUNT > 0
        if (draw->material_index >= 0) {
            const Banjo3DSMaterial *material =
                &banjo_materials[draw->material_index];

            applyCombine(&draw->combine, render_state);
            C3D_TexBind(
                0,
                &textures[material->texture_slot]
            );
        }
#endif
#if BANJO_MATERIAL_COUNT > 0
        else
#endif
        {
            resetTexEnvs();
            C3D_TexEnvSrc(
                C3D_GetTexEnv(0),
                C3D_Both,
                GPU_PRIMARY_COLOR,
                GPU_PRIMARY_COLOR,
                GPU_PRIMARY_COLOR
            );
            C3D_TexEnvFunc(
                C3D_GetTexEnv(0),
                C3D_Both,
                GPU_REPLACE
            );
        }

        C3D_DrawArrays(
            GPU_TRIANGLES,
            draw->first_vertex,
            draw->vertex_count
        );
    }
}

#if BANJO_GEO_NODE_COUNT > 0
static C3D_FVec cameraSortProxyEye(void)
{
    return FVec4_New(
        camera.focusX - camera.eyeDistance * modelView.r[2].x,
        camera.focusY - camera.eyeDistance * modelView.r[2].y,
        camera.focusZ - camera.eyeDistance * modelView.r[2].z,
        1.0f);
}

// SORT-only tree: conditional visibility was deliberately flattened at export.
static void sceneDrawGeo(int index, C3D_FVec eye,
    const Banjo3DSRenderState* render_state)
{
    while (index >= 0) {
        const Banjo3DSGeoNode* node = &banjo_geo_nodes[index];
        if (node->kind == 0) {
            sceneDrawRange(node->first_draw, node->draw_count, render_state);
        } else {
            // Static map coordinates; equality belongs to child1 -> child2.
            float q = (node->point2[0] - node->point1[0]) * (eye.x - node->point1[0])
                    + (node->point2[1] - node->point1[1]) * (eye.y - node->point1[1])
                    + (node->point2[2] - node->point1[2]) * (eye.z - node->point1[2]);
            if (node->flags & 1) {
                // Original RUN_BOTH_BIT actually selects ONE child.
                sceneDrawGeo(q >= 0.0f ? node->child2 : node->child1, eye, render_state);
            } else {
                sceneDrawGeo(q >= 0.0f ? node->child1 : node->child2, eye, render_state);
                sceneDrawGeo(q >= 0.0f ? node->child2 : node->child1, eye, render_state);
            }
        }
        index = node->next;
    }
}
#endif

static void sceneRender(void)
{
    const Banjo3DSRenderState render_state = {
        .primitive_color = 0xFF000000u,
        .environment_color = 0xFFFFFFFFu,
    };

    C3D_FVUnifMtx4x4(
        GPU_VERTEX_SHADER,
        uLoc_projection,
        &projection
    );
    C3D_FVUnifMtx4x4(
        GPU_VERTEX_SHADER,
        uLoc_modelView,
        &modelView
    );

#if BANJO_GEO_NODE_COUNT > 0
    C3D_FVec eye = cameraSortProxyEye();
    if (BANJO_OPA_GEO_ROOT >= 0)
        sceneDrawGeo(BANJO_OPA_GEO_ROOT, eye, &render_state);
    else
#endif
        sceneDrawRange(0, BANJO_OPA_DRAW_COUNT, &render_state);

    unsigned int xlu_first_draw = BANJO_OPA_DRAW_COUNT;
#ifdef BANJO_ACTOR_DRAW_COUNT
    // Original world order: map OPA, character, map XLU. Canonical 034D's
    // FullDepthOpa modes 1 and 3 both use Z_CMP | Z_UPD; retain depth writes.
    float rows[4][4];
    C3D_Mtx world, actorModelView;
    movementActorMatrix(&actor, rows);
    for (int i = 0; i < 4; ++i)
        world.r[i] = FVec4_New(rows[i][0], rows[i][1], rows[i][2], rows[i][3]);
    // Citro3D out = a*b; shader uses matrix rows dotted with column positions.
    // Keep camera modelView intact, including the SORT proxy-eye calculation.
    Mtx_Multiply(&actorModelView, &modelView, &world);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &actorModelView);
    sceneDrawRange(BANJO_ACTOR_FIRST_DRAW, BANJO_ACTOR_DRAW_COUNT, &render_state);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &modelView);
    xlu_first_draw += BANJO_ACTOR_DRAW_COUNT;
#endif

    if (BANJO_XLU_DRAW_COUNT > 0) {
        C3D_DepthTest(true, GPU_GREATER, GPU_WRITE_COLOR);
        C3D_AlphaBlend(GPU_BLEND_ADD, GPU_BLEND_ADD,
            GPU_SRC_ALPHA, GPU_ONE_MINUS_SRC_ALPHA,
            GPU_SRC_ALPHA, GPU_ONE_MINUS_SRC_ALPHA);
#if BANJO_GEO_NODE_COUNT > 0
        if (BANJO_XLU_GEO_ROOT >= 0)
            sceneDrawGeo(BANJO_XLU_GEO_ROOT, eye, &render_state);
        else
#endif
            sceneDrawRange(xlu_first_draw, BANJO_XLU_DRAW_COUNT, &render_state);
        C3D_DepthTest(true, GPU_GREATER, GPU_WRITE_ALL);
    }
    // Alpha blend factors above match the existing Citro3D defaults.
}

static void sceneExit(void)
{
#if BANJO_TEXTURE_COUNT > 0
    for (unsigned int i = 0; i < BANJO_TEXTURE_COUNT; i++) {
        C3D_TexDelete(&textures[i]);
    }
#endif
    linearFree(vbo_data);
    shaderProgramFree(&program);
    DVLB_Free(vshader_dvlb);
}

int main(void)
{
    gfxInitDefault();
    C3D_Init(C3D_DEFAULT_CMDBUF_SIZE);

    C3D_RenderTarget *target =
        C3D_RenderTargetCreate(
            240,
            400,
            GPU_RB_RGBA8,
            GPU_RB_DEPTH24_STENCIL8
        );

    C3D_RenderTargetSetOutput(
        target,
        GFX_TOP,
        GFX_LEFT,
        DISPLAY_TRANSFER_FLAGS
    );

    sceneInit();

    u64 previousFrameMs = osGetTime();
    while (aptMainLoop()) {
        u64 now = osGetTime();
        float dt = movementDelta(now, previousFrameMs);
        previousFrameMs = now;
        hidScanInput();

        u32 down = hidKeysDown();
        if (down & KEY_START)
            break;

        circlePosition pad;
        hidCircleRead(&pad);
        u32 held = hidKeysHeld();
        cameraUpdate(down, held, &pad, dt);
        MovementActor previousActor = actor;
        bool accepted = movementUpdate(&actor, pad.dx, pad.dy, camera.yawDegrees, dt,
            (held & KEY_Y) != 0, banjo_floor_vertices, banjo_floor_triangles,
            BANJO_FLOOR_TRIANGLE_COUNT);

        if (!C3D_FrameBegin(C3D_FRAME_SYNCDRAW)) continue;
        /* FrameBegin waits for the previous GPU submission before VBO writes. */
        float dx = actor.x - previousActor.x, dz = actor.z - previousActor.z;
        float speed = accepted && dt > 0 ? sqrtf(dx*dx + dz*dz) / dt : 0;
        u64 poseStart = svcGetSystemTick();
        bool changed = walkAnimationUpdate(&walkAnimation,
            banjo_pose_packet, BANJO_POSE_PACKET_SIZE, accepted, speed, dt,
            vbo_data, banjo_vertices, BANJO_VERTEX_COUNT,
            BANJO_ACTOR_FIRST_VERTEX, BANJO_ACTOR_VERTEX_COUNT, sizeof(Banjo3DSVertex));
        if (accepted && speed > 0) {
            banjoPoseLastUs = (svcGetSystemTick() - poseStart) / CPU_TICKS_PER_USEC;
            if (banjoPoseLastUs > banjoPoseMaxUs) banjoPoseMaxUs = banjoPoseLastUs;
            ++banjoPoseUpdateCount;
        }
        if (changed)
            GSPGPU_FlushDataCache((Banjo3DSVertex *)vbo_data + BANJO_ACTOR_FIRST_VERTEX,
                BANJO_ACTOR_VERTEX_COUNT * sizeof(Banjo3DSVertex));
        C3D_RenderTargetClear(target, C3D_CLEAR_ALL, CLEAR_COLOR, 0);
        C3D_FrameDrawOn(target);
        sceneRender();
        C3D_FrameEnd(0);
    }

    sceneExit();

    C3D_Fini();
    gfxExit();

    return 0;
}
