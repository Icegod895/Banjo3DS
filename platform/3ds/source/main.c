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
static int uLoc_projection;
static C3D_Mtx projection;
static void *vbo_data;
static C3D_Tex textures[BANJO_TEXTURE_COUNT];
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

static void sceneInit(void)
{
    vshader_dvlb = DVLB_ParseFile((u32 *)vshader_shbin, vshader_shbin_size);
    shaderProgramInit(&program);
    shaderProgramSetVsh(&program, &vshader_dvlb->DVLE[0]);
    C3D_BindProgram(&program);

    uLoc_projection =
        shaderInstanceGetUniformLocation(program.vertexShader, "projection");

    C3D_AttrInfo *attrInfo = C3D_GetAttrInfo();
    AttrInfo_Init(attrInfo);
    AttrInfo_AddLoader(attrInfo, 0, GPU_FLOAT, 3);
    AttrInfo_AddLoader(attrInfo, 1, GPU_FLOAT, 2);

    Mtx_OrthoTilt(&projection, -40.0f, 40.0f, -24.0f, 24.0f, -1.0f, 1.0f, true);

    vbo_data = linearAlloc(sizeof(banjo_vertices));
    memcpy(vbo_data, banjo_vertices, sizeof(banjo_vertices));

    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 2, 0x10);
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

    C3D_TexEnv *env = C3D_GetTexEnv(0);
    C3D_TexEnvInit(env);
    C3D_TexEnvSrc(env, C3D_Both, GPU_TEXTURE0, 0, 0);
    C3D_TexEnvFunc(env, C3D_Both, GPU_REPLACE);
}

static void sceneRender(void)
{
    C3D_FVUnifMtx4x4(
        GPU_VERTEX_SHADER,
        uLoc_projection,
        &projection
    );

    for (unsigned int i = 0; i < BANJO_DRAW_COUNT; i++) {
        const Banjo3DSDraw *draw = &banjo_draws[i];
        const Banjo3DSMaterial *material = &banjo_materials[draw->material_index];

        C3D_TexBind(0, &textures[material->texture_slot]);
        C3D_DrawArrays(GPU_TRIANGLES, draw->first_vertex, draw->vertex_count);
    }
}

static void sceneExit(void)
{
    for (unsigned int i = 0; i < BANJO_TEXTURE_COUNT; i++) {
        C3D_TexDelete(&textures[i]);
    }
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
