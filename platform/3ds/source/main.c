#include <3ds.h>
#include <citro3d.h>
#include <string.h>

#include "vshader_shbin.h"
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

    Mtx_OrthoTilt(&projection, -60.0f, 100.0f, -130.0f, 210.0f, -250.0f, 250.0f, true);
    Mtx_Identity(&modelView);
    Mtx_RotateX(&modelView, C3D_Angle(M_TAU / 4.0f), true);

    vbo_data = linearAlloc(sizeof(banjo_vertices));
    memcpy(vbo_data, banjo_vertices, sizeof(banjo_vertices));

    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);
#if BANJO_TEXTURE_COUNT > 0
    for (unsigned int i = 0; i < BANJO_TEXTURE_COUNT; i++) {
        C3D_TexInit(
            &textures[i],
            banjo_textures[i].width,
            banjo_textures[i].height,
            GPU_RGBA8
        );
        C3D_TexUpload(&textures[i], banjo_textures[i].data);
        C3D_TexSetFilter(&textures[i], GPU_NEAREST, GPU_NEAREST);
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

static void applyCombine(
    const Banjo3DSCombine *combine,
    const Banjo3DSRenderState *state
)
{
    for (int i = 0; i < 6; i++) {
        C3D_TexEnvInit(C3D_GetTexEnv(i));
    }
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
        return;
    }
}

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

    for (unsigned int i = 0; i < BANJO_DRAW_COUNT; i++) {
        const Banjo3DSDraw *draw = &banjo_draws[i];

#if BANJO_MATERIAL_COUNT > 0
        if (draw->material_index >= 0) {
            const Banjo3DSMaterial *material =
                &banjo_materials[draw->material_index];

            applyCombine(&draw->combine, &render_state);
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

    while (aptMainLoop()) {
        hidScanInput();

        if (hidKeysDown() & KEY_START)
            break;

        C3D_FrameBegin(C3D_FRAME_SYNCDRAW);
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
