#include <3ds.h>
#include <citro3d.h>
#include <string.h>
#include <math.h>

#include "vshader_shbin.h"
#include "movement.h"
#include "player_runtime.h"
#include "player_input.h"
#include "player_crouch.h"
#include "generated_model.h"
#include "generated_actors.h"
#include "actor_pose.h"
#include "generated_crouch.h"
#include "renderer_culling.h"
#include "camera_runtime.h"
#include "generated_camera.h"
#include "generated_bridge.h"
#include "sfx_probe_3ds.h"
#include "footstep_3ds.h"
#include "../../../tools/banjo3ds/bridge_state/render.h"

/* Temporary diagnostic build choice, not an N64 camera-button mapping. */
#ifndef BANJO_DEBUG_CAMERA
#define BANJO_DEBUG_CAMERA 0
#endif
#ifndef BANJO_CAMERA_ASPECT
#define BANJO_CAMERA_ASPECT C3D_AspectRatioTop /* Banjo3DS presentation policy. */
#endif

_Static_assert((int)BANJO_CULL_NONE == (int)RENDERER_CULL_NONE
    && (int)BANJO_CULL_FRONT == (int)RENDERER_CULL_FRONT
    && (int)BANJO_CULL_BACK == (int)RENDERER_CULL_BACK
    && (int)BANJO_CULL_BOTH == (int)RENDERER_CULL_BOTH, "Exported cull bits must match");

#define CLEAR_COLOR 0x68B0D8FF
/* Isolation 1 compiles out staged actors and all runtime poses.
 * Static Bottles 1 draws the exported 013B phase-zero pose (FIX6).
 * Hill draw 1 enables the static closed molehill (FIX5).
 * Texture upload 1 uploads actor textures during startup.
 * Vertex init 1 also allocates the actor vertex buffer and copies the
 * initial vertices once. Both draw switches 0 leave it unbound (FIX4).
 * With both draw switches 0, upload 0 and vertex init 0 reproduce FIX2.
 * With both draw switches 0, upload 1 and vertex init 0 reproduce FIX3. */
#ifndef BANJO3DS_ACTOR_ISOLATION
#define BANJO3DS_ACTOR_ISOLATION 1
#endif
#ifndef BANJO3DS_ACTOR_TEXTURE_UPLOAD
#define BANJO3DS_ACTOR_TEXTURE_UPLOAD 1
#endif
#ifndef BANJO3DS_ACTOR_VERTEX_INIT
#define BANJO3DS_ACTOR_VERTEX_INIT 1
#endif
#ifndef BANJO3DS_ACTOR_HILL_DRAW
#define BANJO3DS_ACTOR_HILL_DRAW 1
#endif
#ifndef BANJO3DS_ACTOR_STATIC_BOTTLES
#define BANJO3DS_ACTOR_STATIC_BOTTLES 1
#endif
#ifndef BANJO3DS_ACTOR_IDLE_ANIMATION
#define BANJO3DS_ACTOR_IDLE_ANIMATION 1
#endif
#ifndef BANJO3DS_ACTOR_HILL_OPEN_ANIMATION
#define BANJO3DS_ACTOR_HILL_OPEN_ANIMATION 0
#endif
#ifndef BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER
#define BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER 0
#endif
#ifndef BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
#define BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER 0
#endif
#if BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER && BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER
#error "Hill manual and automatic proximity diagnostics are mutually exclusive"
#endif
#if BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER && BANJO3DS_ACTOR_HILL_OPEN_ANIMATION != 1
#error "Hill manual diagnostic requires B2-P1 hill animation"
#endif
#if BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER && BANJO3DS_ACTOR_HILL_OPEN_ANIMATION != 1
#error "Hill proximity diagnostic requires B2-P1 hill animation"
#endif
#if BANJO3DS_ACTOR_HILL_OPEN_ANIMATION
#if BANJO3DS_ACTOR_ISOLATION != 1 || BANJO3DS_ACTOR_TEXTURE_UPLOAD != 1 || BANJO3DS_ACTOR_VERTEX_INIT != 1 || BANJO3DS_ACTOR_HILL_DRAW != 1 || BANJO3DS_ACTOR_STATIC_BOTTLES != 1 || BANJO3DS_ACTOR_IDLE_ANIMATION != 1
#error "B2-P1 requires all hardware-approved FIX7 switches"
#endif
#include "generated_hill_open.h"
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_EMERGENCE
#define BANJO3DS_ACTOR_BOTTLES_EMERGENCE 0
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_EXIT
#define BANJO3DS_ACTOR_BOTTLES_EXIT 0
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
#define BANJO3DS_ACTOR_BOTTLES_B_INTERACTION 0
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW 0
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE 0
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK 0
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK && (!BANJO3DS_ACTOR_BOTTLES_B_INTERACTION || !BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW || !BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE || !BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT)
#error "Dialogue player lock requires explicitly enabled B interaction, preview, sequence and auto exit"
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK && BANJO_DEBUG_CAMERA
#error "Dialogue player lock requires the normal gameplay camera"
#endif
#ifndef BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT
#define BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT 0
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT && (!BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW || !BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE || !BANJO3DS_ACTOR_BOTTLES_EXIT)
#error "Dialogue auto exit requires explicitly enabled preview, sequence and actor exit"
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE && !BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW
#error "Dialogue sequence requires explicitly enabled preview"
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW
#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION != 1
#error "Dialogue preview requires the explicitly enabled B interaction"
#endif
#include <stdio.h>
#include "bottles_dialogue_preview.h"
static PrintConsole dialoguePreviewConsole;
static DpPreview dialoguePreview;
static DpSpeech dialoguePreviewSpeech;
static bool dialoguePreviewValid;
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
static DsSequence dialogueSequence;
#endif
/* CPU-only bottom screen. No consoleClear (which flushes both screens), no swaps. */
static void dialoguePreviewPresent(void)
{
    consoleSelect(&dialoguePreviewConsole);
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
    dsClearTextArea(dialoguePreviewConsole.frameBuffer, 320u * 240u);
#else
    memset(dialoguePreviewConsole.frameBuffer, 0, 320u * 240u * sizeof(u16));
#endif
    dialoguePreviewConsole.cursorX = 1;
    dialoguePreviewConsole.cursorY = 1;
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
    if (dialogueSequence.status == DS_ACTIVE) {
        fputs("0xDF4 - DIAGNOSTIC SEQUENCE", stdout);
        dialoguePreviewConsole.cursorY = 3;
        dialoguePreviewConsole.cursorX = 1;
        fputs(dsSpeakerLabel(dialogueSequence.speech.speaker), stdout);
        for (unsigned line = 0; line < dialogueSequence.layout.count; ++line) {
            dialoguePreviewConsole.cursorX = 1;
            dialoguePreviewConsole.cursorY = 5 + line;
            fwrite(dialogueSequence.speech.bytes + dialogueSequence.layout.offset[line],
                1, dialogueSequence.layout.length[line], stdout);
        }
        fflush(stdout);
    }
#else
    if (dialoguePreview.active) {
        /* Console newline handling flushes both screens: position rows directly. */
        fputs("0xDF4 - DIAGNOSTIC PREVIEW", stdout);
        dialoguePreviewConsole.cursorX = 1;
        dialoguePreviewConsole.cursorY = 3;
        fputs("BANJO", stdout);
        dialoguePreviewConsole.cursorX = 1;
        dialoguePreviewConsole.cursorY = 5;
        fwrite(dialoguePreviewSpeech.bytes, 1, dialoguePreviewSpeech.length, stdout);
        fflush(stdout);
    }
#endif
    GSPGPU_FlushDataCache(dialoguePreviewConsole.frameBuffer, 320u * 240u * sizeof(u16));
}
#endif
#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
#if BANJO3DS_ACTOR_BOTTLES_EXIT != 1 || BANJO_DEBUG_CAMERA != 0
#error "B interaction requires the approved B2-P3 exit and gameplay camera"
#endif
#include "bottles_b_interaction.h"
static BottlesBInput bottlesBInput;
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK && BANJO3DS_ACTOR_BOTTLES_EXIT && BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
/* A close qualified B press waits for the existing native recoil to land. */
static BottlesBPending bottlesBPending;
#endif
#endif
#if BANJO3DS_ACTOR_BOTTLES_EXIT
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE != 1
#error "Bottles exit requires B2-P2 emergence"
#endif
#include "generated_actor_exit.h"
#endif
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
#if BANJO3DS_ACTOR_HILL_OPEN_ANIMATION != 1 || BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER != 1 || BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER != 0
#error "Bottles emergence requires the hardware-approved FIX2 SELECT configuration"
#endif
#include "generated_bottles_emerge.h"
#endif
#if BANJO3DS_ACTOR_IDLE_ANIMATION
#if BANJO3DS_ACTOR_STATIC_BOTTLES != 1
#error "FIX7 requires the FIX6 Bottles renderer"
#endif
#endif
#if BANJO3DS_ACTOR_STATIC_BOTTLES
#if BANJO3DS_ACTOR_HILL_DRAW != 1
#error "FIX6 requires the FIX5 closed molehill diagnostic"
#endif
#endif
#if BANJO3DS_ACTOR_HILL_DRAW
#if BANJO3DS_ACTOR_ISOLATION != 1 || BANJO3DS_ACTOR_TEXTURE_UPLOAD != 1 || BANJO3DS_ACTOR_VERTEX_INIT != 1
#error "FIX5 requires actor isolation, texture upload, and vertex initialization"
#endif
#endif
#ifndef BANJO3DS_ACTOR_DIAG
#define BANJO3DS_ACTOR_DIAG 4
#endif

#define DISPLAY_TRANSFER_FLAGS \
    (GX_TRANSFER_FLIP_VERT(0) | GX_TRANSFER_OUT_TILED(0) | \
     GX_TRANSFER_RAW_COPY(0) | GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGBA8) | \
     GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB8) | \
     GX_TRANSFER_SCALING(GX_TRANSFER_SCALE_NO))

static DVLB_s *vshader_dvlb;
static shaderProgram_s program;
static int uLoc_projection, uLoc_modelView;
static C3D_Mtx projection, modelView;
static RendererWindingParity viewWindingParity = RENDERER_WINDING_NORMAL;
static CameraRuntime rareCamera;
static PlayerInputState playerInput;
static BanjoFootState foot_state;
static BanjoFootPlay foot_plays[2];
static int foot_play_count;
/* Explicit debugger-visible failure, never a query-miss debug fallback. */
static volatile int cameraRuntimeStatus;
static void *vbo_data;
#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_VERTEX_INIT
__attribute__((used))
static void *actor_vbo;
#endif
#if BANJO3DS_ACTOR_ISOLATION == 0
static float actor_bottles_phase;
static int actor_diag_stage;
static u64 actor_diag_start_ms;
static float actor_bottles_bones[ACTOR_BOTTLES_BONE_SLOTS * 10];
static float actor_bottles_matrices[ACTOR_BOTTLES_MATRIX_COUNT * 16];
static float actor_bottles_xyz[ACTOR_BOTTLES_LOAD_COUNT * 3];
#endif
#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_TEXTURE_UPLOAD
static C3D_Tex actor_textures[ACTOR_TEXTURE_COUNT];
#endif
static PlayerRuntime player = {.motion = {.actor = {0.0f, 1800.0f, 0.0f, 0.0f}, .grounded = true}};
static uint8_t banjo_crouch_packet[36994];
static const uint8_t *banjo_runtime_pose = banjo_pose_packet;
static size_t banjo_runtime_pose_size = BANJO_POSE_PACKET_SIZE;
/* Debugger-visible CPU measurements: evaluator + corner XYZ propagation,
 * excluding GPU wait/cache flush. No console work in the measured interval. */
volatile float banjoPoseLastUs, banjoPoseMaxUs;
volatile u32 banjoPoseUpdateCount;

#if BANJO_TEXTURE_COUNT > 0
static C3D_Tex textures[BANJO_TEXTURE_COUNT];
#endif

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

_Static_assert(ACTOR_HILL_FIRST_DRAW == 0, "molehill is drawn before Bottles");
_Static_assert(ACTOR_BOTTLES_FIRST_DRAW == ACTOR_HILL_DRAW_COUNT, "Bottles follows the molehill");
_Static_assert(ACTOR_HILL_FIRST_VERTEX == 0, "molehill vertices precede Bottles");
_Static_assert(sizeof actor_molehill_packet == ACTOR_HILL_PACKET_SIZE, "molehill packet");
_Static_assert(sizeof actor_bottles_packet == ACTOR_BOTTLES_PACKET_SIZE, "Bottles packet");
_Static_assert(ACTOR_BOTTLES_ANIM_LAST == 267 && ACTOR_BOTTLES_ANIM_CHANNELS == 42,
    "Bottles idle is animation 013B");
_Static_assert(sizeof(Banjo3DSVertex) == 24, "vertex stride stays 24 bytes");
_Static_assert(sizeof(actor_vertices) == (size_t)ACTOR_VERTEX_COUNT * sizeof(Banjo3DSVertex),
    "actor vertex capacity is the exported array");
_Static_assert(sizeof(banjo_vertices) == (size_t)BANJO_VERTEX_COUNT * sizeof(Banjo3DSVertex),
    "world vertex capacity is the exported array");

#if BANJO3DS_ACTOR_ISOLATION
#if BANJO3DS_ACTOR_HILL_DRAW
#if BANJO3DS_ACTOR_IDLE_ANIMATION
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: FIX7 closed molehill and Bottles idle only";
#elif BANJO3DS_ACTOR_STATIC_BOTTLES
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: FIX6 closed molehill and static Bottles";
#else
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: FIX5 closed molehill only";
#endif
/* Last completed command list high-water mark, for hardware debugging. */
volatile float actorDiagCmdBufMax;
#elif BANJO3DS_ACTOR_VERTEX_INIT
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: vertex buffer init";
#elif BANJO3DS_ACTOR_TEXTURE_UPLOAD
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: texture upload only";
#else
/* FIX2 control. The bytes stay linked and no actor code runs. */
__attribute__((used)) static const char actor_isolation_banner[] =
    "actor-isolation: runtime disabled";
#endif
__attribute__((used)) static const void *const actor_isolation_retained[] = {
    actor_vertices,
    actor_texture_info,
    actor_draws,
    actor_bottles_packet,
    actor_molehill_packet,
};
#endif

static struct {
    float yawDegrees, pitchDegrees, zoom;
    float eyeDistance;
    float focusX, focusY, focusZ;
} camera;


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

static uint32_t firstPersonButtons(uint32_t logical)
{
    uint32_t out=0;
    if(logical&PI_N64_A)out|=FP_A;
    if(logical&PI_N64_B)out|=FP_B;
    if(logical&PI_N64_CUP)out|=FP_CUP;
    if(logical&PI_N64_Z)out|=FP_Z;
    return out;
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
    viewWindingParity = RENDERER_WINDING_NORMAL;
    Mtx_OrthoTilt(&projection,
        -1500.0f / camera.zoom, 1500.0f / camera.zoom,
        -900.0f / camera.zoom, 900.0f / camera.zoom,
        -11000.0f, 11000.0f, true);
    Mtx_Identity(&modelView);
    Mtx_RotateX(&modelView, C3D_AngleFromDegrees(camera.pitchDegrees), true);
    Mtx_RotateY(&modelView, C3D_AngleFromDegrees(camera.yawDegrees), true);
    Mtx_Translate(&modelView, -camera.focusX, -camera.focusY, -camera.focusZ, true);
}

static void cameraApplyRareView(void)
{
    /* Fixed positive clips are a bounded viewer policy, not Rare dynamic clips.
     * Perspective 40 degrees and XY-preserving RH->LH conversion were proven
     * separately; cameraRareView supplies the matching REVERSED parity. */
    Mtx_PerspTilt(&projection, C3D_AngleFromDegrees(40.0f),
        BANJO_CAMERA_ASPECT, 10.0f, 20000.0f, true);
    for (int i = 0; i < 4; ++i)
        modelView.r[i] = FVec4_New(rareCamera.view[i][0], rareCamera.view[i][1],
            rareCamera.view[i][2], rareCamera.view[i][3]);
    viewWindingParity = rareCamera.parity;
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

#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_VERTEX_INIT
/* Out of line so the link map can prove this experiment allocated the buffer.
 * The copy length is the allocation length. The GPU buffer stays vbo_data. */
__attribute__((noinline))
static void initActorVertexBuffer(void)
{
    actor_vbo = linearAlloc(sizeof(actor_vertices));
    memcpy(actor_vbo, actor_vertices, sizeof(actor_vertices));
}
#endif

#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_TEXTURE_UPLOAD
/* Out of line so the link map can prove this experiment uploaded textures. */
__attribute__((noinline))
static void uploadActorTextures(void)
{
    for (unsigned int i = 0; i < ACTOR_TEXTURE_COUNT; i++) {
        const Actor3DSTexture *info = &actor_texture_info[i];
        GPU_TEXTURE_FILTER_PARAM filter = info->linear_filter ? GPU_LINEAR : GPU_NEAREST;
        C3D_TexInitWithParams(
            &actor_textures[i],
            NULL,
            (C3D_TexInitParams){
                info->width,
                info->height,
                info->mipmap_count,
                GPU_RGBA8,
                GPU_TEX_2D,
                false
            }
        );
        C3D_TexLoadImage(&actor_textures[i], info->data, GPU_TEXFACE_2D, 0);
        for (unsigned int level = 1; level <= info->mipmap_count; level++)
            C3D_TexLoadImage(&actor_textures[i], info->mipmaps[level - 1], GPU_TEXFACE_2D, level);
        C3D_TexSetFilter(&actor_textures[i], filter, filter);
        C3D_TexSetFilterMipmap(&actor_textures[i], GPU_LINEAR);
        C3D_TexSetWrap(&actor_textures[i],
            textureWrapTo3DS(info->wrap_s), textureWrapTo3DS(info->wrap_t));
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

#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_VERTEX_INIT
    initActorVertexBuffer();
#endif
#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_TEXTURE_UPLOAD
    uploadActorTextures();
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
        int cull = rendererCullMode(draw->cull_mode, viewWindingParity);
        if (cull == RENDERER_CULL_SKIP)
            continue;
        C3D_CullFace((GPU_CULLMODE)cull);

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
    if (!BANJO_DEBUG_CAMERA)
        return FVec4_New(rareCamera.visible_position[0], rareCamera.visible_position[1],
            rareCamera.visible_position[2], 1.0f);
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

#if BANJO3DS_ACTOR_HILL_OPEN_ANIMATION
/* Diagnostic starts at boot unless the optional proximity gate is enabled,
 * samples the whole original 4.5-second clip once,
 * then holds phase 1 (CLOSED). No Rare state dispatch or visibility changes.
 * Seconds use double precision to avoid accumulated normalized-phase drift. */
static double hillOpenSeconds;
#if BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER || BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
/* Observation-only sphere in original world units, not Rare's B-button gate. */
#define ACTOR_HILL_PROXIMITY_RADIUS 400.0f
static bool hillOpenTriggered;
#if BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
/* Physical SELECT edge, observed without changing the gameplay input stream. */
static bool hillOpenManualPressed;
#endif

static bool hillOpenInRange(void)
{
    /* Read the actual player position after cameraRuntimeMove, not camera,
     * view-space coordinates, or the posed Banjo mesh. Selector 2 only. */
    float dx = player.motion.actor.x - ACTOR_PLACE_X;
    float dy = player.motion.actor.y - ACTOR_PLACE_Y;
    float dz = player.motion.actor.z - ACTOR_PLACE_Z;
    return isfinite(dx) && isfinite(dy) && isfinite(dz) &&
        dx * dx + dy * dy + dz * dz <= ACTOR_HILL_PROXIMITY_RADIUS * ACTOR_HILL_PROXIMITY_RADIUS;
}
#endif
static float hillOpenBones[ACTOR_HILL_OPEN_BONE_SLOTS * 10];
static float hillOpenMatrices[ACTOR_HILL_OPEN_MATRIX_COUNT * 16];
static float hillOpenXYZ[ACTOR_HILL_OPEN_LOAD_COUNT * 3];
volatile u32 hillOpenUpdateCount, hillOpenRejectCount;
_Static_assert(ACTOR_HILL_FIRST_VERTEX == 0 && ACTOR_HILL_VERTEX_COUNT == ACTOR_HILL_OPEN_VERTEX_COUNT,
    "Hill packet must match the existing hill region");
_Static_assert(ACTOR_HILL_FIRST_VERTEX + ACTOR_HILL_VERTEX_COUNT == ACTOR_BOTTLES_FIRST_VERTEX &&
    ACTOR_BOTTLES_FIRST_VERTEX <= ACTOR_VERTEX_COUNT, "Hill writes must exclude Bottles");

__attribute__((noinline))
static bool hillOpenPrepare(float dt)
{
    ActorPoseInfo info;
    if (!isfinite(dt) || dt < 0.0f || dt > 0.05f ||
        !isfinite(hillOpenSeconds) || hillOpenSeconds < 0.0 || hillOpenSeconds > ACTOR_HILL_OPEN_DURATION ||
        sizeof actor_hill_open_packet != ACTOR_HILL_OPEN_PACKET_SIZE ||
        !actor_pose_info(actor_hill_open_packet, sizeof actor_hill_open_packet, &info) ||
        info.matrix_count != ACTOR_HILL_OPEN_MATRIX_COUNT ||
        info.load_count != ACTOR_HILL_OPEN_LOAD_COUNT ||
        info.corner_count != ACTOR_HILL_OPEN_VERTEX_COUNT ||
        info.bone_slots != ACTOR_HILL_OPEN_BONE_SLOTS || info.boneless ||
        info.anim_bytes != ACTOR_HILL_OPEN_ANIM_BYTES ||
        info.anim_last != ACTOR_HILL_OPEN_ANIM_LAST || info.anim_channels != ACTOR_HILL_OPEN_ANIM_CHANNELS)
        return false;
#if BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER || BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
#if BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
    bool triggered = hillOpenTriggered ||
#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
        hillOpenManualPressed; /* Already qualified before gameplay movement. */
#else
        (hillOpenManualPressed && hillOpenInRange());
#endif
#else
    bool triggered = hillOpenTriggered || hillOpenInRange();
#endif
    /* The entry frame publishes phase zero. The following deltas cover the
     * full 4.5 seconds; remaining near or leaving cannot reset the latch. */
    double seconds = hillOpenTriggered ? hillOpenSeconds + (double)dt : 0.0;
#else
    double seconds = hillOpenSeconds + (double)dt;
#endif
    if (seconds > ACTOR_HILL_OPEN_DURATION) seconds = ACTOR_HILL_OPEN_DURATION;
    float phase = (float)(seconds / ACTOR_HILL_OPEN_DURATION);
    if (!actor_pose_evaluate(actor_hill_open_packet, sizeof actor_hill_open_packet, phase,
            hillOpenBones, hillOpenMatrices, hillOpenXYZ))
        return false;
    for (size_t i = 0; i < ACTOR_HILL_OPEN_LOAD_COUNT * 3; ++i)
        if (!isfinite(hillOpenXYZ[i]) || hillOpenXYZ[i] < -200.0f || hillOpenXYZ[i] > 200.0f)
            return false;
#if BANJO3DS_ACTOR_HILL_PROXIMITY_TRIGGER || BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
    hillOpenTriggered = triggered;
#endif
    hillOpenSeconds = seconds;
    return true;
}

/* Only called after successful SYNCDRAW and preparation; XYZ only, hill span only. */
__attribute__((noinline))
static bool hillOpenPublish(void)
{
    if (!actor_vbo || actor_vbo == vbo_data ||
        !actor_pose_scatter(actor_hill_open_packet, sizeof actor_hill_open_packet, hillOpenXYZ,
            actor_vbo, ACTOR_VERTEX_COUNT, ACTOR_HILL_FIRST_VERTEX,
            ACTOR_HILL_VERTEX_COUNT, sizeof(Banjo3DSVertex)))
        return false;
    GSPGPU_FlushDataCache((Banjo3DSVertex *)actor_vbo + ACTOR_HILL_FIRST_VERTEX,
        ACTOR_HILL_VERTEX_COUNT * sizeof(Banjo3DSVertex));
    return true;
}
#endif

#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
/* SM smbottles.c: states 1/2/3. The shared draw omits waiting (mole.c:132).
 * No world translation or head motion is synthesized. Separate from hill time. */
enum { BOTTLES_WAITING, BOTTLES_EMERGING, BOTTLES_IDLE
#if BANJO3DS_ACTOR_BOTTLES_EXIT
    , BOTTLES_EXITING, BOTTLES_HIDDEN_DONE
#endif
};
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT
#include "bottles_dialogue_auto_exit.h"
static DaeBridge dialogueAutoExit;
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
#include "bottles_dialogue_player_lock.h"
static DplLock dialoguePlayerLock;
#endif
static int bottlesEmergenceState;
static bool bottlesEmergenceVisible;
static float bottlesEmergencePhase, bottlesEmergenceIdlePhase, bottlesEmergenceBlend;
static bool bottlesEmergenceSfxPending;
static bool bottlesPullSfxPending, bottlesPopSfxPending;
static bool bottlesEmergenceLoopStarted;
static float bottlesEmergenceBones[ACTOR_BOTTLES_BONE_SLOTS * 10];
static float bottlesEmergenceLastBones[ACTOR_BOTTLES_BONE_SLOTS * 10];
static float bottlesEmergenceSource[ACTOR_BOTTLES_BONE_SLOTS * 10];
static float bottlesEmergenceMatrices[ACTOR_BOTTLES_MATRIX_COUNT * 16];
static float bottlesEmergenceXYZ[ACTOR_BOTTLES_LOAD_COUNT * 3];
/* Selector-2 Bottles faces the player when this encounter starts. His model
 * uses the same +Z/positive-Y yaw convention as movementActorMatrix. */
static float bottlesFacingYaw = ACTOR_PLACE_YAW;
static float bottlesFacingTarget(float x, float z, float previous)
{
    float dx = x - ACTOR_PLACE_X, dz = z - ACTOR_PLACE_Z;
    if (!isfinite(dx) || !isfinite(dz) || (dx == 0.0f && dz == 0.0f)) return previous;
    return atan2f(dx, dz) * (180.0f / 3.14159265358979323846f);
}
volatile u32 bottlesEmergenceUpdateCount, bottlesEmergenceRejectCount;
_Static_assert(ACTOR_BOTTLES_EMERGE_MATRIX_COUNT == ACTOR_BOTTLES_MATRIX_COUNT &&
    ACTOR_BOTTLES_EMERGE_BONE_SLOTS == ACTOR_BOTTLES_BONE_SLOTS &&
    ACTOR_BOTTLES_EMERGE_LOAD_COUNT == ACTOR_BOTTLES_LOAD_COUNT &&
    ACTOR_BOTTLES_EMERGE_VERTEX_COUNT == ACTOR_BOTTLES_VERTEX_COUNT,
    "Bottles clips must share exact scratch and vertex capacities");
_Static_assert(ACTOR_BOTTLES_FIRST_VERTEX == ACTOR_HILL_FIRST_VERTEX + ACTOR_HILL_VERTEX_COUNT &&
    ACTOR_BOTTLES_FIRST_VERTEX + ACTOR_BOTTLES_VERTEX_COUNT <= ACTOR_VERTEX_COUNT,
    "Bottles must exclude hill and fit actor VBO");

static bool bottlesEmergencePacketValid(const u8 *packet, size_t size,
    unsigned bytes, unsigned last, unsigned channels)
{
    ActorPoseInfo info;
    return actor_pose_info(packet, size, &info) && !info.boneless &&
        info.matrix_count == ACTOR_BOTTLES_MATRIX_COUNT &&
        info.bone_slots == ACTOR_BOTTLES_BONE_SLOTS &&
        info.load_count == ACTOR_BOTTLES_LOAD_COUNT &&
        info.corner_count == ACTOR_BOTTLES_VERTEX_COUNT &&
        info.anim_bytes == bytes && info.anim_last == last && info.anim_channels == channels &&
        info.factor == 9.0f;
}

__attribute__((noinline))
static bool bottlesEmergencePrepare(float dt, bool start)
{
    if (!isfinite(dt) || dt < 0 || dt > 0.05f ||
        bottlesEmergenceState < BOTTLES_WAITING || bottlesEmergenceState > BOTTLES_IDLE ||
        !isfinite(bottlesEmergencePhase) || bottlesEmergencePhase < 0 || bottlesEmergencePhase > 1 ||
        !isfinite(bottlesEmergenceIdlePhase) || bottlesEmergenceIdlePhase < 0 || bottlesEmergenceIdlePhase >= 1 ||
        !isfinite(bottlesEmergenceBlend) || bottlesEmergenceBlend < 0 || bottlesEmergenceBlend > 1)
        return false;
    if (bottlesEmergenceState == BOTTLES_WAITING && !start) return true;
    /* Exact capacities checked before either capacity-less A3P1 evaluator. */
    if (!bottlesEmergencePacketValid(actor_bottles_emerge_packet, sizeof actor_bottles_emerge_packet,
            ACTOR_BOTTLES_EMERGE_ANIM_BYTES, ACTOR_BOTTLES_EMERGE_ANIM_LAST, ACTOR_BOTTLES_EMERGE_ANIM_CHANNELS) ||
        !bottlesEmergencePacketValid(actor_bottles_packet, sizeof actor_bottles_packet,
            2196, ACTOR_BOTTLES_ANIM_LAST, ACTOR_BOTTLES_ANIM_CHANNELS))
        return false;
    int state = bottlesEmergenceState;
    float previousPhase = bottlesEmergencePhase;
    float phase = bottlesEmergencePhase, idle = bottlesEmergenceIdlePhase, blend = bottlesEmergenceBlend;
    bool transition = false;
    if (state == BOTTLES_WAITING) {
        state = BOTTLES_EMERGING;
        phase = 0.0001f; /* Original subaddie_set_state_with_direction start. */
    } else if (state == BOTTLES_EMERGING) {
        /* Rare checks the previous controller step before advancing this one.
         * Forward once playback crosses .9999 and clamps below 1. */
        if (phase > 0.9999f) {
            state = BOTTLES_IDLE;
            idle = 0.0001f;
            blend = 0.0f;
            transition = true;
        } else {
            phase += dt / ACTOR_BOTTLES_EMERGE_DURATION;
            if ((double)phase > 0.999999) phase = 0.9999989867210388f;
        }
    }
    bool evaluated;
    if (state == BOTTLES_EMERGING) {
        evaluated = actor_pose_evaluate(actor_bottles_emerge_packet, sizeof actor_bottles_emerge_packet,
            phase, bottlesEmergenceBones, bottlesEmergenceMatrices, bottlesEmergenceXYZ);
    } else {
        idle = actor_pose_advance(idle, dt, ACTOR_BOTTLES_IDLE_DURATION);
        blend = fminf(1.0f, blend + dt / ACTOR_BOTTLES_TRANSITION_DURATION);
        const float *source = transition ? bottlesEmergenceLastBones : bottlesEmergenceSource;
        evaluated = blend < 1.0f ?
            actor_pose_evaluate_blend(actor_bottles_packet, sizeof actor_bottles_packet, idle,
                source, ACTOR_BOTTLES_BONE_SLOTS, blend,
                bottlesEmergenceBones, bottlesEmergenceMatrices, bottlesEmergenceXYZ) :
            actor_pose_evaluate(actor_bottles_packet, sizeof actor_bottles_packet, idle,
                bottlesEmergenceBones, bottlesEmergenceMatrices, bottlesEmergenceXYZ);
    }
    if (!evaluated) return false;
    /* Same conservative envelope as FIX7; dense 013A/key-boundary tests verify it. */
    for (size_t i = 0; i < ACTOR_BOTTLES_LOAD_COUNT * 3; ++i)
        if (!isfinite(bottlesEmergenceXYZ[i]) || bottlesEmergenceXYZ[i] < -200 || bottlesEmergenceXYZ[i] > 400)
            return false;
    if (transition) memcpy(bottlesEmergenceSource, bottlesEmergenceLastBones, sizeof bottlesEmergenceSource);
    memcpy(bottlesEmergenceLastBones, bottlesEmergenceBones, sizeof bottlesEmergenceLastBones);
    if (bottlesEmergenceState == BOTTLES_WAITING && start)
        bottlesFacingYaw = bottlesFacingTarget(player.motion.actor.x, player.motion.actor.z, bottlesFacingYaw);
    if (bottlesEmergenceState == BOTTLES_WAITING && start)
        bottlesEmergenceSfxPending = false;
    else if (state == BOTTLES_EMERGING && previousPhase < 0.14f && phase >= 0.14f)
        bottlesEmergenceSfxPending = true; /* smbottles.c state 2 SFX_C6 at .14. */
    else if (state != BOTTLES_EMERGING)
        bottlesEmergenceSfxPending = false;
    if (bottlesEmergenceState == BOTTLES_WAITING && start) {
        bottlesPullSfxPending = false;
        bottlesPopSfxPending = false;
    } else if (state == BOTTLES_EMERGING) {
        if (previousPhase < 0.40f && phase >= 0.40f)
            bottlesPullSfxPending = true; /* smbottles.c:568-569 SFX_2C. */
        if (previousPhase < 0.75f && phase >= 0.75f)
            bottlesPopSfxPending = true; /* smbottles.c:571-572 SFX_C5. */
    } else {
        bottlesPullSfxPending = false;
        bottlesPopSfxPending = false;
    }
    bottlesEmergenceState = state;
    bottlesEmergencePhase = phase;
    bottlesEmergenceIdlePhase = idle;
    bottlesEmergenceBlend = blend;
    return true;
}

__attribute__((noinline))
static bool bottlesEmergencePublish(void)
{
    /* Both packets use the original idle packet's identical corner/load map.
     * Visibility is committed only after the initial pose reaches the VBO. */
    if (!actor_vbo || actor_vbo == vbo_data || bottlesEmergenceState == BOTTLES_WAITING ||
        !actor_pose_scatter(actor_bottles_packet, sizeof actor_bottles_packet, bottlesEmergenceXYZ,
            actor_vbo, ACTOR_VERTEX_COUNT, ACTOR_BOTTLES_FIRST_VERTEX,
            ACTOR_BOTTLES_VERTEX_COUNT, sizeof(Banjo3DSVertex)))
        return false;
    GSPGPU_FlushDataCache((Banjo3DSVertex *)actor_vbo + ACTOR_BOTTLES_FIRST_VERTEX,
        ACTOR_BOTTLES_VERTEX_COUNT * sizeof(Banjo3DSVertex));
    bottlesEmergenceVisible = true;
    /* Sound follows the accepted pose publication, never a rejected prepare. */
    /* Original state 2 renews SFX_3F9 only for animation phase (0,.16).
     * Channel 5 lets its brief overlap with C6 at .14-.16 survive. */
    if (bottlesEmergenceState == BOTTLES_EMERGING &&
        bottlesEmergencePhase > 0.0f && bottlesEmergencePhase < 0.16f) {
        if (!bottlesEmergenceLoopStarted)
            bottlesEmergenceLoopStarted = sfxProbe3dsBottlesEmergenceLoopStart();
    } else if (bottlesEmergenceLoopStarted) {
        sfxProbe3dsBottlesEmergenceLoopStop();
        bottlesEmergenceLoopStarted = false;
    }
    if (bottlesEmergenceSfxPending && bottlesEmergenceState == BOTTLES_EMERGING) {
        bottlesEmergenceSfxPending = false;
        sfxProbe3dsBottlesEmergence();
    }
    if (bottlesPullSfxPending && bottlesEmergenceState == BOTTLES_EMERGING) {
        bottlesPullSfxPending = false;
        sfxProbe3dsBottlesPull();
    }
    if (bottlesPopSfxPending && bottlesEmergenceState == BOTTLES_EMERGING) {
        bottlesPopSfxPending = false;
        sfxProbe3dsBottlesPop();
    }
    return true;
}
#endif

#if BANJO3DS_ACTOR_BOTTLES_EXIT
/* SM state 4 and linked hill state 3: shared event, independent 1.7 s clocks.
 * Both retain anctrl's .2 s smooth transition. Hidden state 1 is not drawn.
 * No dialogue, camera, particles, or gameplay input consumption. */
static float bottlesExitPhase, bottlesExitBlend;
static float hillClosePhase, hillCloseBlend;
static float hillCloseBones[ACTOR_HILL_OPEN_BONE_SLOTS * 10];
static float hillCloseSource[ACTOR_HILL_OPEN_BONE_SLOTS * 10];
static bool bottlesExitFinalPublished;
static bool bottlesRetreatSfxStarted;
_Static_assert(ACTOR_BOTTLES_EXIT_MATRIX_COUNT == ACTOR_BOTTLES_MATRIX_COUNT &&
    ACTOR_BOTTLES_EXIT_BONE_SLOTS == ACTOR_BOTTLES_BONE_SLOTS &&
    ACTOR_BOTTLES_EXIT_LOAD_COUNT == ACTOR_BOTTLES_LOAD_COUNT &&
    ACTOR_BOTTLES_EXIT_VERTEX_COUNT == ACTOR_BOTTLES_VERTEX_COUNT &&
    ACTOR_HILL_CLOSE_MATRIX_COUNT == ACTOR_HILL_OPEN_MATRIX_COUNT &&
    ACTOR_HILL_CLOSE_BONE_SLOTS == ACTOR_HILL_OPEN_BONE_SLOTS &&
    ACTOR_HILL_CLOSE_LOAD_COUNT == ACTOR_HILL_OPEN_LOAD_COUNT &&
    ACTOR_HILL_CLOSE_VERTEX_COUNT == ACTOR_HILL_VERTEX_COUNT,
    "Exit packets must fit the existing disjoint actor regions");

__attribute__((noinline))
static bool bottlesExitPrepare(float dt, bool start)
{
    if (!isfinite(dt) || dt < 0 || dt > 0.05f ||
        !isfinite(bottlesExitPhase) || bottlesExitPhase < 0 || bottlesExitPhase > 1 ||
        !isfinite(hillClosePhase) || hillClosePhase < 0 || hillClosePhase > 1 ||
        !isfinite(bottlesExitBlend) || bottlesExitBlend < 0 || bottlesExitBlend > 1 ||
        !isfinite(hillCloseBlend) || hillCloseBlend < 0 || hillCloseBlend > 1)
        return false;
    if (bottlesEmergenceState == BOTTLES_HIDDEN_DONE) return true; /* Retry final GPU publication only. */
    if (start ? bottlesEmergenceState != BOTTLES_IDLE : bottlesEmergenceState != BOTTLES_EXITING)
        return false;
    ActorPoseInfo info;
    if (!bottlesEmergencePacketValid(actor_bottles_exit_packet, sizeof actor_bottles_exit_packet,
            ACTOR_BOTTLES_EXIT_ANIM_BYTES, ACTOR_BOTTLES_EXIT_ANIM_LAST, ACTOR_BOTTLES_EXIT_ANIM_CHANNELS) ||
        !actor_pose_info(actor_hill_close_packet, sizeof actor_hill_close_packet, &info) ||
        info.boneless || info.matrix_count != ACTOR_HILL_OPEN_MATRIX_COUNT ||
        info.bone_slots != ACTOR_HILL_OPEN_BONE_SLOTS || info.load_count != ACTOR_HILL_OPEN_LOAD_COUNT ||
        info.corner_count != ACTOR_HILL_VERTEX_COUNT || info.factor != 9.0f ||
        info.anim_bytes != ACTOR_HILL_CLOSE_ANIM_BYTES || info.anim_last != ACTOR_HILL_CLOSE_ANIM_LAST ||
        info.anim_channels != ACTOR_HILL_CLOSE_ANIM_CHANNELS)
        return false;
    float phase = start ? 0.0001f : bottlesExitPhase;
    float hill = start ? 0.0001f : hillClosePhase;
    float blend = start ? 0.0f : bottlesExitBlend;
    float hillBlend = start ? 0.0f : hillCloseBlend;
    /* Rare checks the previous step's .9999 crossing before advancing.
     * Each controller completes independently; final hill geometry equals rest. */
    bool complete = !start && phase > 0.9999f;
    bool hillComplete = !start && hill > 0.9999f;
    if (!start) {
        if (!complete) phase += dt / ACTOR_BOTTLES_EXIT_DURATION;
        if ((double)phase > 0.999999) phase = 0.9999989867210388f;
        if (!hillComplete) hill += dt / ACTOR_HILL_CLOSE_DURATION;
        if ((double)hill > 0.999999) hill = 0.9999989867210388f;
        blend = fminf(1, blend + dt / ACTOR_BOTTLES_TRANSITION_DURATION);
        hillBlend = fminf(1, hillBlend + dt / ACTOR_BOTTLES_TRANSITION_DURATION);
    }
    const float *source = start ? bottlesEmergenceLastBones : bottlesEmergenceSource;
    const float *hillSource = start ? hillOpenBones : hillCloseSource;
    bool ok = actor_pose_evaluate_blend(actor_bottles_exit_packet, sizeof actor_bottles_exit_packet,
        phase, source, ACTOR_BOTTLES_BONE_SLOTS, blend,
        bottlesEmergenceBones, bottlesEmergenceMatrices, bottlesEmergenceXYZ);
    ok = ok && actor_pose_evaluate_blend(actor_hill_close_packet, sizeof actor_hill_close_packet,
        hill, hillSource, ACTOR_HILL_OPEN_BONE_SLOTS, hillBlend,
        hillCloseBones, hillOpenMatrices, hillOpenXYZ);
    if (!ok) return false;
    for (size_t i = 0; i < ACTOR_BOTTLES_LOAD_COUNT * 3; ++i)
        if (!isfinite(bottlesEmergenceXYZ[i]) || bottlesEmergenceXYZ[i] < -200 || bottlesEmergenceXYZ[i] > 400)
            return false;
    for (size_t i = 0; i < ACTOR_HILL_OPEN_LOAD_COUNT * 3; ++i)
        if (!isfinite(hillOpenXYZ[i]) || hillOpenXYZ[i] < -200 || hillOpenXYZ[i] > 200)
            return false;
    if (start) {
        memcpy(bottlesEmergenceSource, bottlesEmergenceLastBones, sizeof bottlesEmergenceSource);
        memcpy(hillCloseSource, hillOpenBones, sizeof hillCloseSource);
    }
    bottlesExitPhase = phase; hillClosePhase = hill;
    bottlesExitBlend = blend; hillCloseBlend = hillBlend;
    if (start) bottlesRetreatSfxStarted = false;
    bottlesEmergenceState = complete && hillComplete ? BOTTLES_HIDDEN_DONE : BOTTLES_EXITING;
    return true;
}

__attribute__((noinline))
static bool bottlesExitPublish(void)
{
    /* Called only after the existing synchronous GPU wait. Final publication
     * remains pending across failed waits; terminal frames do no pose work. */
    if (!hillOpenPublish()) return false;
    if (bottlesEmergenceState == BOTTLES_HIDDEN_DONE) {
        bottlesEmergenceVisible = false;
        bottlesExitFinalPublished = true;
        sfxProbe3dsBottlesRetreatStop();
        bottlesRetreatSfxStarted = false;
        return true;
    }
    if (!bottlesEmergencePublish()) return false;
    /* smbottles.c state 4 renews SFX_3F9 only during (.35, .9).
     * Dispatch only after the retreat/hill pair has been published. */
    if (bottlesExitPhase > 0.35f && bottlesExitPhase < 0.9f) {
        if (!bottlesRetreatSfxStarted)
            bottlesRetreatSfxStarted = sfxProbe3dsBottlesRetreatStart();
    } else if (bottlesRetreatSfxStarted) {
        sfxProbe3dsBottlesRetreatStop();
        bottlesRetreatSfxStarted = false;
    }
    return true;
}
#endif

#if !BANJO3DS_ACTOR_BOTTLES_EMERGENCE
#if BANJO3DS_ACTOR_IDLE_ANIMATION
/* FIX7 owns CPU scratch only; the startup actor allocation remains the sole VBO.
 * Original ch/mole.c idle duration: 7 seconds. No actor behaviour dispatch. */
static float bottlesIdlePhase;
static float bottlesIdleBones[ACTOR_BOTTLES_BONE_SLOTS * 10];
static float bottlesIdleMatrices[ACTOR_BOTTLES_MATRIX_COUNT * 16];
static float bottlesIdleXYZ[ACTOR_BOTTLES_LOAD_COUNT * 3];
volatile u32 bottlesIdleUpdateCount, bottlesIdleRejectCount;
_Static_assert(ACTOR_BOTTLES_FIRST_VERTEX >= ACTOR_HILL_FIRST_VERTEX + ACTOR_HILL_VERTEX_COUNT,
    "Bottles writes must exclude the closed molehill");
_Static_assert(ACTOR_BOTTLES_FIRST_VERTEX + ACTOR_BOTTLES_VERTEX_COUNT <= ACTOR_VERTEX_COUNT,
    "Bottles writes must fit the owned actor allocation");

__attribute__((noinline))
static bool bottlesIdlePrepare(float dt)
{
    ActorPoseInfo info;
    /* movementDelta supplies [0, .05]. Reject invalid time before the evaluator's
     * fract conversion, and validate exact scratch capacities before evaluation. */
    if (!isfinite(dt) || dt < 0.0f || dt > 0.05f ||
        !isfinite(bottlesIdlePhase) || bottlesIdlePhase < 0.0f || bottlesIdlePhase >= 1.0f ||
        !actor_pose_info(actor_bottles_packet, sizeof actor_bottles_packet, &info) ||
        info.matrix_count != ACTOR_BOTTLES_MATRIX_COUNT ||
        info.load_count != ACTOR_BOTTLES_LOAD_COUNT ||
        info.corner_count != ACTOR_BOTTLES_VERTEX_COUNT ||
        info.bone_slots != ACTOR_BOTTLES_BONE_SLOTS || info.boneless || !info.anim_bytes ||
        info.anim_last != ACTOR_BOTTLES_ANIM_LAST || info.anim_channels != ACTOR_BOTTLES_ANIM_CHANNELS)
        return false;
    float phase = actor_pose_advance(bottlesIdlePhase, dt, ACTOR_BOTTLES_IDLE_DURATION);
    if (!isfinite(phase) || phase < 0.0f || phase >= 1.0f ||
        !actor_pose_evaluate(actor_bottles_packet, sizeof actor_bottles_packet, phase,
            bottlesIdleBones, bottlesIdleMatrices, bottlesIdleXYZ))
        return false;
    /* Conservative local-space bounds verified across the original idle clip.
     * Reject a bad pose as a whole before touching GPU-visible memory. */
    for (size_t i = 0; i < ACTOR_BOTTLES_LOAD_COUNT * 3; ++i)
        if (!isfinite(bottlesIdleXYZ[i]) || bottlesIdleXYZ[i] < -200.0f || bottlesIdleXYZ[i] > 400.0f)
            return false;
    bottlesIdlePhase = phase;
    return true;
}

/* Caller must have successfully waited in C3D_FrameBegin(SYNCDRAW), and must
 * pass only a successful prepare result. Scratch is unchanged between calls. */
__attribute__((noinline))
static bool bottlesIdlePublish(void)
{
    if (!actor_vbo || actor_vbo == vbo_data ||
        !actor_pose_scatter(actor_bottles_packet, sizeof actor_bottles_packet, bottlesIdleXYZ,
            actor_vbo, ACTOR_VERTEX_COUNT, ACTOR_BOTTLES_FIRST_VERTEX,
            ACTOR_BOTTLES_VERTEX_COUNT, sizeof(Banjo3DSVertex)))
        return false;
    GSPGPU_FlushDataCache((Banjo3DSVertex *)actor_vbo + ACTOR_BOTTLES_FIRST_VERTEX,
        ACTOR_BOTTLES_VERTEX_COUNT * sizeof(Banjo3DSVertex));
    return true;
}
#endif

#endif

#if BANJO3DS_ACTOR_ISOLATION == 0
/* Staged diagnostic, compiled only when isolation is off.
 * 4 steps the clear every four seconds: magenta, green, yellow, red. */
static int actorDiagStage(float seconds)
{
#if BANJO3DS_ACTOR_DIAG == 0
    (void)seconds;
    return 3;
#elif BANJO3DS_ACTOR_DIAG == 1
    (void)seconds;
    return 0;
#elif BANJO3DS_ACTOR_DIAG == 2
    (void)seconds;
    return 1;
#elif BANJO3DS_ACTOR_DIAG == 3
    (void)seconds;
    return 2;
#else
    if (seconds < 4.0f)
        return 0;
    if (seconds < 8.0f)
        return 1;
    if (seconds < 12.0f)
        return 2;
    return 3;
#endif
}

static u32 actorDiagClear(int stage)
{
#if BANJO3DS_ACTOR_DIAG == 0
    (void)stage;
    return CLEAR_COLOR;
#else
    /* RRGGBBAA, same channel order as CLEAR_COLOR. */
    static const u32 colors[4] = {
        0xC020C0FFu,
        0x20B020FFu,
        0xD0C020FFu,
        0xD02020FFu,
    };
    if (stage < 0 || stage > 3)
        return CLEAR_COLOR;
    return colors[stage];
#endif
}

#endif

#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_HILL_DRAW
static void sceneDrawActorRange(unsigned int first, unsigned int count,
    const Banjo3DSRenderState *render_state)
{
    for (unsigned int i = first; i < first + count; i++) {
        const Banjo3DSDraw *draw = &actor_draws[i];
        int cull = rendererCullMode(draw->cull_mode, viewWindingParity);
        if (cull == RENDERER_CULL_SKIP)
            continue;
        C3D_CullFace((GPU_CULLMODE)cull);
        /* Shaded triangles can precede the first texture load. Their combiner
         * still runs; only a real material binds a texture. */
        applyCombine(&draw->combine, render_state);
        if (draw->material_index >= 0) {
            const Banjo3DSMaterial *material = &actor_materials[draw->material_index];
            C3D_TexBind(0, &actor_textures[material->texture_slot]);
        }
        C3D_DrawArrays(GPU_TRIANGLES, draw->first_vertex, draw->vertex_count);
    }
}

#endif

#if BANJO3DS_ACTOR_ISOLATION == 0
static void sceneDrawPlacedActors(const Banjo3DSRenderState *render_state)
{
    /* Closed molehill, then idle Bottles, at the selector-2 placement.
     * Restore Banjo's vertex buffer and the camera matrix before map XLU.
     * Stage 0 returns before any actor matrix or vertex-buffer change. */
    if (actor_diag_stage <= 0)
        return;
    float rows[4][4];
    C3D_Mtx world, placed;
    actor_pose_placement(rows, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z,
        ACTOR_PLACE_YAW, ACTOR_PLACE_SCALE);
    for (int i = 0; i < 4; ++i)
        world.r[i] = FVec4_New(rows[i][0], rows[i][1], rows[i][2], rows[i][3]);
    Mtx_Multiply(&placed, &modelView, &world);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &placed);
    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, actor_vbo, sizeof(Banjo3DSVertex), 3, 0x210);
    if (actor_diag_stage >= 1)
        sceneDrawActorRange(ACTOR_HILL_FIRST_DRAW, ACTOR_HILL_DRAW_COUNT, render_state);
    if (actor_diag_stage >= 2)
        sceneDrawActorRange(ACTOR_BOTTLES_FIRST_DRAW, ACTOR_BOTTLES_DRAW_COUNT, render_state);
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);
    /* DrawArrays consumed the dirty flag. A cached pointer alone cannot
     * publish the restored world VBO before the water/bridge draws. */
    C3D_SetBufInfo(bufInfo);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &modelView);
}
#endif

#if BANJO3DS_ACTOR_HILL_DRAW
/* FIX5: original 0388 closed vertices, yaw 0, scale 1. No pose entry point.
 * Out of line so the ELF check proves this diagnostic contains the draw. */
__attribute__((noinline))
static void sceneDrawClosedMolehill(const Banjo3DSRenderState *render_state)
{
    C3D_Mtx world, placed;
    Mtx_Identity(&world);
    Mtx_Translate(&world, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z, true);
    Mtx_Multiply(&placed, &modelView, &world);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &placed);
    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, actor_vbo, sizeof(Banjo3DSVertex), 3, 0x210);
    sceneDrawActorRange(ACTOR_HILL_FIRST_DRAW, ACTOR_HILL_DRAW_COUNT, render_state);
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);
    /* Re-dirty the GPU buffer state after the actor draw consumed it. */
    C3D_SetBufInfo(bufInfo);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &modelView);
}
#endif

#if BANJO3DS_ACTOR_STATIC_BOTTLES
/* FIX6: original 0387, with 013B phase 0 baked by the existing exporter.
 * FIX7 updates only its XYZ region; this validated draw path is unchanged. */
__attribute__((noinline))
static void sceneDrawStaticBottles(const Banjo3DSRenderState *render_state)
{
    C3D_Mtx world, placed;
    Mtx_Identity(&world);
    Mtx_Translate(&world, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z, true);
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
    Mtx_RotateY(&world, C3D_AngleFromDegrees(bottlesFacingYaw), true);
#endif
    Mtx_Multiply(&placed, &modelView, &world);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &placed);
    C3D_BufInfo *bufInfo = C3D_GetBufInfo();
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, actor_vbo, sizeof(Banjo3DSVertex), 3, 0x210);
    sceneDrawActorRange(ACTOR_BOTTLES_FIRST_DRAW, ACTOR_BOTTLES_DRAW_COUNT, render_state);
    BufInfo_Init(bufInfo);
    BufInfo_Add(bufInfo, vbo_data, sizeof(Banjo3DSVertex), 3, 0x210);
    /* Re-dirty the GPU buffer state after the actor draw consumed it. */
    C3D_SetBufInfo(bufInfo);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &modelView);
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
    movementActorMatrix(&player.motion.actor, rows);
    for (int i = 0; i < 4; ++i)
        world.r[i] = FVec4_New(rows[i][0], rows[i][1], rows[i][2], rows[i][3]);
    // Citro3D out = a*b; shader uses matrix rows dotted with column positions.
    // Keep camera modelView intact, including the SORT proxy-eye calculation.
    Mtx_Multiply(&actorModelView, &modelView, &world);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &actorModelView);
    if (cameraRuntimeModelVisible(&rareCamera))
        sceneDrawRange(BANJO_ACTOR_FIRST_DRAW, BANJO_ACTOR_DRAW_COUNT, &render_state);
    C3D_FVUnifMtx4x4(GPU_VERTEX_SHADER, uLoc_modelView, &modelView);
    xlu_first_draw += BANJO_ACTOR_DRAW_COUNT;
#endif

#if BANJO3DS_ACTOR_ISOLATION == 0
    sceneDrawPlacedActors(&render_state);
#endif
#if BANJO3DS_ACTOR_HILL_DRAW
    sceneDrawClosedMolehill(&render_state);
#endif
#if BANJO3DS_ACTOR_STATIC_BOTTLES
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
    if (bottlesEmergenceVisible)
#endif
    sceneDrawStaticBottles(&render_state);
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
#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_TEXTURE_UPLOAD
    for (unsigned int i = 0; i < ACTOR_TEXTURE_COUNT; i++)
        C3D_TexDelete(&actor_textures[i]);
#endif
#if BANJO3DS_ACTOR_ISOLATION == 0 || BANJO3DS_ACTOR_VERTEX_INIT
    linearFree(actor_vbo);
#endif
    linearFree(vbo_data);
    shaderProgramFree(&program);
    DVLB_Free(vshader_dvlb);
}

#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
/* Snapshot BEFORE this frame's gameplay consumers. This deliberately uses
 * native root position and supported locomotion, not Rare's model cache or
 * full movement-group classifier. No facing restriction. */
static bool bottlesBPrepareInput(PlayerInputFrame *controls, u32 held, u32 down)
{
    BottlesBContext context = {
        .x = player.motion.actor.x, .y = player.motion.actor.y, .z = player.motion.actor.z,
        .vertical_velocity = player.motion.verticalVelocity,
        .abilities = BANJO_LEARNED_ABILITIES, .gait = player.locomotion.gait,
        .action_request = playerCrouchRequested(),
        .waiting = bottlesEmergenceState == BOTTLES_WAITING,
        .grounded = player.motion.grounded, .jumping = player.jumpActive,
        .first_person = playerRuntimeFirstPersonActive(&player) ||
            playerRuntimeFirstPersonBlocks(&player) || cameraRuntimeFirstPersonActive(&rareCamera),
        .crouching = playerCrouchActive(),
        .conflict = controls->suppress_movement || (controls->held & ~(uint32_t)PI_N64_B) ||
            (held & (KEY_A | KEY_X | KEY_Y | KEY_L | KEY_R | KEY_SELECT | KEY_START))
    };
    return bottlesBConsume(&bottlesBInput, controls,
        bottlesBEligible(&context, ACTOR_PLACE_X, ACTOR_PLACE_Y, ACTOR_PLACE_Z),
        (held & KEY_B) != 0, (down & KEY_B) != 0);
}
static bool bottlesBRouteRecoil(bool bStart)
{
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK && BANJO3DS_ACTOR_BOTTLES_EXIT && BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
    /* Re-arm only after the entire actor/dialogue encounter has retired.
     * This does not reset movement, contact, or collision state. */
    if (bottlesEmergenceState == BOTTLES_HIDDEN_DONE &&
        dialoguePlayerLock.state != DPL_LOCKED && !bottlesBPending.pending)
        playerGroundRearmRecoil(&rareCamera.player_ground);
    bool encounterReady = bottlesEmergenceState == BOTTLES_WAITING &&
        !hillOpenTriggered && dialoguePlayerLock.state == DPL_UNLOCKED &&
        dialoguePreviewValid && actor_vbo && actor_vbo != vbo_data;
    bool hadPending = bottlesBPending.pending;
    bool resumed = bottlesBPendingPoll(&bottlesBPending, encounterReady,
        rareCamera.player_ground.recoil == PLAYER_RECOIL_COMPLETE &&
            player.motion.grounded && !player.jumpActive,
        rareCamera.player_ground.recoil == PLAYER_RECOIL_NONE);
    /* Even cancellation consumes this frame's new edge: an invalidated old
     * request must never fall through to an actor start. */
    if (hadPending) bStart = false;
    if (resumed) bStart = true;
    /* The existing B consumer accepted this edge. Defer its one actor
     * start only if the unchanged P27 native recoil accepts the request. */
    if (bStart && !resumed && encounterReady &&
        playerGroundRequestRecoil(&rareCamera.player_ground,&player.motion,
            ACTOR_PLACE_X,ACTOR_PLACE_Y,ACTOR_PLACE_Z)) {
        bottlesBPending.pending = true;
        bStart = false;
    }
#endif
    return bStart;
}
#endif

int main(void)
{
    gfxInitDefault();
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW
    /* libctru consoleInit swaps displays: run before creating any Citro3D resources. */
    consoleInit(GFX_BOTTOM, &dialoguePreviewConsole);
    dialoguePreviewValid = dpSelectGenerated(&dialoguePreviewSpeech);
#endif
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
    if (!cameraRuntimeInit(&rareCamera, &player,
            camera_opa_packet, sizeof(camera_opa_packet),
            camera_xlu_packet, sizeof(camera_xlu_packet),
            &camera_zone_data)) {
        cameraRuntimeStatus = CAMERA_RUNTIME_INVALID;
        sceneExit();
        C3D_Fini();
        gfxExit();
        return 1;
    }
    br_bind(&camera_rail_data);

    cameraRuntimeSetLearnedAbilities(&rareCamera, BANJO_LEARNED_ABILITIES);
    playerCrouchInstall();
    playerCrouchSetAbilities(BANJO_LEARNED_ABILITIES);
    _Static_assert(BANJO_POSE_PACKET_SIZE == 28022, "crouch prefix is the frozen v4 packet");
    _Static_assert(sizeof banjo_crouch_enter_clip == 2176
        && sizeof banjo_crouch_turn_clip == 2576
        && sizeof banjo_crouch_noinput_clip == 4220, "raw crouch clips");
    {
        size_t assembled = playerCrouchActivate(banjo_crouch_packet, sizeof banjo_crouch_packet,
            banjo_pose_packet, BANJO_POSE_PACKET_SIZE,
            banjo_crouch_enter_clip, sizeof banjo_crouch_enter_clip,
            banjo_crouch_turn_clip, sizeof banjo_crouch_turn_clip,
            banjo_crouch_noinput_clip, sizeof banjo_crouch_noinput_clip);
        if (assembled == 36994) {
            banjo_runtime_pose = banjo_crouch_packet;
            banjo_runtime_pose_size = assembled;
        }
    }

    /* The voice stays silent until a crouch coast raises the sustain latch. Sustained frames keep looped SFX_18 and step pitch with Rare's formula. The first unsustained frame stops that voice and plays SFX_19 once. No new button, and this call does not enter crouch, gait, input, physics, or camera. */
    sfxProbe3dsInit();
    banjo_foot_reset(&foot_state);
    footstep3dsInit();

#if BANJO3DS_ACTOR_ISOLATION == 0
    actor_diag_start_ms = osGetTime();
#endif
    u64 previousFrameMs = osGetTime();
    u32 previousVi = C3D_FrameCounter(0);
    while (aptMainLoop()) {
        u64 now = osGetTime();
        float dt = movementDelta(now, previousFrameMs);
        previousFrameMs = now;
        u32 currentVi = C3D_FrameCounter(0);
        int viFrames = cameraViFrames(currentVi, previousVi);
        previousVi = currentVi;
        hidScanInput();

        u32 down = hidKeysDown();
        if (down & KEY_START)
            break;

        circlePosition pad;
        hidCircleRead(&pad);
        u32 held = hidKeysHeld();
        if (BANJO_DEBUG_CAMERA)
            cameraUpdate(down, held, &pad, dt);
        float movementInput[3];
        /* hidScanInput already scans IRRST; no second scan/init or key-repeat.
         * Debug builds retain their original controls and neutral manual input. */
        circlePosition cstick = {0};
        hidCstickRead(&cstick);
        PlayerInputFrame controls = playerInputUpdate(&playerInput, held, cstick.dx, cstick.dy);
#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
        bool bottlesBStart = bottlesBRouteRecoil(bottlesBPrepareInput(&controls, held, down));
        if (rareCamera.player_ground.recoil == PLAYER_RECOIL_REQUESTED ||
            rareCamera.player_ground.recoil == PLAYER_RECOIL_ACTIVE) {
            /* Quarantine gameplay input; physical HID history stays intact. */
            controls=(PlayerInputFrame){0};
            controls.suppress_movement=true;
            pad.dx=pad.dy=0;
        }
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
        /* Physical histories and B reservation ran first. Only gameplay intent
         * is filtered; raw SELECT/START and the collision update remain intact. */
        dplObserve(&dialoguePlayerLock, dialogueSequence.status, bottlesEmergenceState);
        if (dplBegin(&dialoguePlayerLock, bottlesBStart, bottlesEmergenceState, 2))
            dplRest(&player.horizontal);
        if (!dialoguePreviewValid) dplRelease(&dialoguePlayerLock);
        dplFilter(&dialoguePlayerLock, &controls);
        if (dialoguePlayerLock.state == DPL_LOCKED) pad.dx = pad.dy = 0;
#endif
        cameraRuntimeManualInput(&rareCamera, BANJO_DEBUG_CAMERA ? 0 : controls.manual, 0x23);
        /* Previous-frame crouch hides C-up from fp_select. Idle Z+C-up still
         * reaches fp_select, because crouch is not active yet. The held bit is
         * recorded so the release frame's C-up is not a new press afterwards.
         * Debug builds keep L as camera zoom and do not feed crouch. */
        uint32_t fp_buttons = firstPersonButtons(controls.held);
        const int crouch_masks_look = !BANJO_DEBUG_CAMERA && playerCrouchActive();
        if (crouch_masks_look)
            fp_buttons &= ~(uint32_t)FP_CUP;
        if (!BANJO_DEBUG_CAMERA)
            cameraRuntimeFirstPersonInput(&rareCamera, &player,
                fp_buttons, cameraPadAxis(pad.dx), cameraPadAxis(pad.dy), dt, viFrames);
        else
            player.first_person_blocks=false;
        if (crouch_masks_look && (controls.held & PI_N64_CUP))
            player.first_person.buttons |= FP_CUP;
        const bool firstPersonBlocks=playerRuntimeFirstPersonBlocks(&player);
        if (!BANJO_DEBUG_CAMERA)
            playerCrouchFrame(&player, controls.held, firstPersonBlocks);
        cameraRuntimeMovementInput(&rareCamera, BANJO_DEBUG_CAMERA, camera.yawDegrees,
            pad.dx, pad.dy, movementInput);
        /* An invalid cameraRuntimeMove may leave the prior event bit intact. */
        player.events = 0;
        cameraRuntimeStatus = cameraRuntimeMove(&rareCamera, &player,
            movementInput[0], movementInput[1], movementInput[2], dt, viFrames,
            BANJO_DEBUG_CAMERA ? (down & KEY_A) != 0 : (controls.jump_pressed && !firstPersonBlocks),
            BANJO_DEBUG_CAMERA ? (held & KEY_Y) != 0 : (controls.suppress_movement || firstPersonBlocks),
            banjo_floor_vertices, banjo_floor_triangles, BANJO_FLOOR_TRIANGLE_COUNT);
        if ((player.events & BANJO_JUMP_LANDED) && !(player.events & BANJO_JUMP_RECOVERED))
            footstep3dsLanding();
        if (!BANJO_DEBUG_CAMERA && rareCamera.view_ready)
            cameraApplyRareView();

        u64 poseStart = svcGetSystemTick();
        BanjoFootFrame foot_frame = {0};
        foot_frame.gait_before = (int)player.gait.gait;
        foot_frame.phase_before = player.gait.phase;
        foot_frame.initialized_before = player.gait.initialized ? 1 : 0;
        bool evaluated = playerRuntimeAnimate(&player,
            banjo_runtime_pose, banjo_runtime_pose_size, dt);
        /* Flags are the body floor query already stored on the bridge.
         * No second collision query and no coordinate classification. */
        foot_frame.gait_after = (int)player.gait.gait;
        foot_frame.phase_after = player.gait.phase;
        foot_frame.initialized_after = player.gait.initialized ? 1 : 0;
        foot_frame.animated = evaluated ? 1 : 0;
        foot_frame.grounded = player.motion.grounded ? 1 : 0;
        foot_frame.crouch = playerCrouchActive() ? 1 : 0;
        foot_frame.jumping = player.jumpActive ? 1 : 0;
        foot_frame.map_id = BANJO_FOOT_MAP_SPIRAL_MOUNTAIN;
        foot_frame.flags = rareCamera.bridge.floor.flags;
        foot_frame.floor_y = rareCamera.bridge.floor.height;
        foot_frame.player_y = player.motion.actor.y;
        foot_frame.floor_valid = rareCamera.bridge.floor.valid ? 1 : 0;
        foot_play_count = banjo_foot_observe(&foot_state, &foot_frame, foot_plays, 2);
        u64 poseTicks = svcGetSystemTick() - poseStart;
#if BANJO3DS_ACTOR_ISOLATION == 0
        /* First submitted frame is phase 0. A failed frame begin retries it.
         * The difference is milliseconds. Stage 1 cannot start before 4.0s
         * unless osGetTime steps backward and the unsigned subtract wraps. */
        actor_diag_stage = actorDiagStage((float)(now - actor_diag_start_ms) / 1000.0f);
        bool actorBottlesReady = false;
        if (actor_diag_stage >= 3)
            actorBottlesReady = actor_pose_evaluate(
                actor_bottles_packet, sizeof actor_bottles_packet, actor_bottles_phase,
                actor_bottles_bones, actor_bottles_matrices, actor_bottles_xyz);
#endif
#if !BANJO3DS_ACTOR_BOTTLES_EMERGENCE
#if BANJO3DS_ACTOR_IDLE_ANIMATION
        /* CPU scratch can be prepared while the previous GPU list runs. */
        bool bottlesIdleReady = bottlesIdlePrepare(dt);
        if (!bottlesIdleReady) ++bottlesIdleRejectCount;
#endif
#endif
#if BANJO3DS_ACTOR_HILL_OPEN_ANIMATION
#if BANJO3DS_ACTOR_HILL_MANUAL_TRIGGER
        /* SELECT is unmapped by playerInputUpdate; do not intercept B or
         * modify down/held/controls. A press outside the radius is not queued. */
        hillOpenManualPressed = (down & KEY_SELECT) != 0;
#if BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
        /* Only the initial event is replaced. SELECT exit retains its 400-unit
         * diagnostic check. Approved pose/clock/publication functions unchanged. */
        if (bottlesEmergenceState == BOTTLES_WAITING) hillOpenManualPressed = bottlesBStart;
#endif
#endif
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
        /* Shared start event, separate clocks. Roll back only CPU clock/latch
         * commits if either pose rejects; never publish a partial pair. */
#if BANJO3DS_ACTOR_BOTTLES_EXIT
        bool exitStart = bottlesEmergenceState == BOTTLES_IDLE &&
            hillOpenManualPressed && hillOpenInRange();
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT
        /* The selector-2 singleton consumes completion only at this CPU boundary.
         * SELECT retains its qualification; both causes use ONE paired prepare. */
        exitStart = exitStart || daeRequest(&dialogueAutoExit, bottlesEmergenceState, 2);
#endif
        bool exitRoute = exitStart || bottlesEmergenceState >= BOTTLES_EXITING;
        bool exitReady = exitRoute && !bottlesExitFinalPublished && bottlesExitPrepare(dt, exitStart);
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT
        /* Retire only after preparation commits. Rejected poses retain the request. */
        if (exitReady) dialogueAutoExit.state = DAE_DONE;
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
        if (exitReady) dplRelease(&dialoguePlayerLock);
#endif
#endif
        if (exitRoute && !bottlesExitFinalPublished && !exitReady) ++bottlesEmergenceRejectCount;
#endif
        double previousHillSeconds = hillOpenSeconds;
        bool previousHillTriggered = hillOpenTriggered;
        bool pairStart = bottlesEmergenceState == BOTTLES_WAITING &&
            !hillOpenTriggered && hillOpenManualPressed
#if !BANJO3DS_ACTOR_BOTTLES_B_INTERACTION
            && hillOpenInRange()
#endif
            ;
#endif
        bool hillOpenReady =
#if BANJO3DS_ACTOR_BOTTLES_EXIT
            !exitRoute &&
#endif
            hillOpenPrepare(dt);
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
        bool bottlesEmergenceReady = hillOpenReady && bottlesEmergencePrepare(dt, pairStart);
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
        /* No committed emergence: release the provisional input lock. */
        if (bottlesBStart && !bottlesEmergenceReady)
            dplAbortStart(&dialoguePlayerLock);
#endif
        if (!bottlesEmergenceReady
#if BANJO3DS_ACTOR_BOTTLES_EXIT
            && !exitRoute
#endif
        ) {
            hillOpenSeconds = previousHillSeconds;
            hillOpenTriggered = previousHillTriggered;
            hillOpenReady = false;
            ++bottlesEmergenceRejectCount;
        }
#endif
        if (!hillOpenReady
#if BANJO3DS_ACTOR_BOTTLES_EXIT
            && !exitRoute
#endif
        ) ++hillOpenRejectCount;
#endif
        if (!C3D_FrameBegin(C3D_FRAME_SYNCDRAW)) continue;
#if BANJO3DS_ACTOR_BOTTLES_EXIT
        if (exitReady) {
            if (bottlesExitPublish()) ++bottlesEmergenceUpdateCount;
            else ++bottlesEmergenceRejectCount;
        }
#endif
#if BANJO3DS_ACTOR_HILL_OPEN_ANIMATION
        if (hillOpenReady) {
            if (hillOpenPublish()) ++hillOpenUpdateCount;
            else ++hillOpenRejectCount;
        }
#endif
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
        if (bottlesEmergenceReady && bottlesEmergenceState != BOTTLES_WAITING) {
            if (bottlesEmergencePublish()) ++bottlesEmergenceUpdateCount;
            else ++bottlesEmergenceRejectCount;
        }
#else
#if BANJO3DS_ACTOR_IDLE_ANIMATION
        /* Installed Citro3D waits gxCmdQueueWait before returning success.
         * Failed frame begins never publish. No per-frame GPU allocation. */
        if (bottlesIdleReady) {
            if (bottlesIdlePublish()) ++bottlesIdleUpdateCount;
            else ++bottlesIdleRejectCount;
        }
#endif
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PREVIEW
        /* Read-only observation after the existing GPU wait and actor publication. */
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
        if (dialoguePreviewValid) {
            bool activation = dpObserve(&dialoguePreview,
                bottlesEmergenceVisible && bottlesEmergenceState == BOTTLES_EMERGING,
                bottlesEmergenceVisible && bottlesEmergenceState == BOTTLES_IDLE,
                bottlesEmergenceState >= BOTTLES_EXITING, bottlesEmergencePhase);
            bool textChanged;
            if (bottlesEmergenceState >= BOTTLES_EXITING)
                textChanged = dsCancel(&dialogueSequence);
            else if (activation && dialoguePreview.active)
                textChanged = dsBeginGenerated(&dialogueSequence);
            else
                textChanged = dsTick(&dialogueSequence, dt);
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_AUTO_EXIT
            /* Queue only; never mutate actors in the post-publication observer.
             * Accepted SELECT was processed first, so cancellation wins that frame. */
            daeObserve(&dialogueAutoExit, dialogueSequence.status, bottlesEmergenceState, 2);
#endif
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_PLAYER_LOCK
            dplObserve(&dialoguePlayerLock, dialogueSequence.status, bottlesEmergenceState);
#endif
            if (textChanged) dialoguePreviewPresent();
        }
#else
        if (dialoguePreviewValid && dpObserve(&dialoguePreview,
                bottlesEmergenceVisible && bottlesEmergenceState == BOTTLES_EMERGING,
                bottlesEmergenceVisible && bottlesEmergenceState == BOTTLES_IDLE,
                bottlesEmergenceState >= BOTTLES_EXITING, bottlesEmergencePhase))
            dialoguePreviewPresent();
#endif
#endif
        /* CPU pose evaluation is independent of the GPU. VBO writes wait for
         * the previous submission; failed render frames cannot lose events. */
        u64 scatterStart = svcGetSystemTick();
        bool changed = evaluated && playerRuntimeWriteVertices(&player, banjo_runtime_pose,
            vbo_data, BANJO_VERTEX_COUNT,
            BANJO_ACTOR_FIRST_VERTEX, BANJO_ACTOR_VERTEX_COUNT, sizeof(Banjo3DSVertex));
        if (changed) {
            banjoPoseLastUs = (poseTicks + svcGetSystemTick() - scatterStart) / CPU_TICKS_PER_USEC;
            if (banjoPoseLastUs > banjoPoseMaxUs) banjoPoseMaxUs = banjoPoseLastUs;
            ++banjoPoseUpdateCount;
        }
        if (changed)
            GSPGPU_FlushDataCache((Banjo3DSVertex *)vbo_data + BANJO_ACTOR_FIRST_VERTEX,
                BANJO_ACTOR_VERTEX_COUNT * sizeof(Banjo3DSVertex));
#if BANJO3DS_ACTOR_ISOLATION == 0
        if (actorBottlesReady && actor_pose_scatter(
                actor_bottles_packet, sizeof actor_bottles_packet, actor_bottles_xyz,
                actor_vbo, ACTOR_VERTEX_COUNT,
                ACTOR_BOTTLES_FIRST_VERTEX, ACTOR_BOTTLES_VERTEX_COUNT,
                sizeof(Banjo3DSVertex)))
            GSPGPU_FlushDataCache((Banjo3DSVertex *)actor_vbo + ACTOR_BOTTLES_FIRST_VERTEX,
                ACTOR_BOTTLES_VERTEX_COUNT * sizeof(Banjo3DSVertex));
#endif
        /* Original mesh publication follows the camera queries. Commit the same
         * state to the 48 bridge corners only after the GPU wait, never a packet
         * copy. Failed draw frames catch up from the absolute source coordinates. */
        const size_t bridgeFirst = BANJO_VERTEX_COUNT - BANJO_BRIDGE_XLU_VERTEX_COUNT
                                 + BANJO_BRIDGE_XLU_FIRST_CORNER;
        int bridgeChanged = bridge_render_y(&rareCamera.xlu, vbo_data,
            BANJO_VERTEX_COUNT, sizeof(Banjo3DSVertex), bridgeFirst,
            banjo_bridge_source_ids, BANJO_BRIDGE_CORNER_COUNT);
        if (bridgeChanged < 0) {
            cameraRuntimeStatus = CAMERA_RUNTIME_INVALID;
            C3D_FrameEnd(0);
            break; /* Never render mismatched visible/query bridge geometry. */
        }
        if (bridgeChanged)
            GSPGPU_FlushDataCache((Banjo3DSVertex *)vbo_data + bridgeFirst,
                BANJO_BRIDGE_CORNER_COUNT * sizeof(Banjo3DSVertex));
#if BANJO3DS_ACTOR_ISOLATION
        C3D_RenderTargetClear(target, C3D_CLEAR_ALL, CLEAR_COLOR, 0);
#else
        C3D_RenderTargetClear(target, C3D_CLEAR_ALL, actorDiagClear(actor_diag_stage), 0);
#endif
        C3D_FrameDrawOn(target);
        /* Do not publish the bootstrap floor seed as a rendered camera frame. */
        if (BANJO_DEBUG_CAMERA || rareCamera.view_ready)
            sceneRender();
        C3D_FrameEnd(0);
        /* The crouch-coast latch sustains looped SFX_18. The first frame without it plays SFX_19 once. */
        sfxProbe3dsFrame(playerCrouchSlideSfx());
        footstep3dsSubmit(foot_plays, foot_play_count);
#if BANJO3DS_ACTOR_HILL_DRAW
        float cmdUsage = C3D_GetCmdBufUsage();
        if (cmdUsage > actorDiagCmdBufMax)
            actorDiagCmdBufMax = cmdUsage;
#endif
#if BANJO3DS_ACTOR_ISOLATION == 0
        if (actor_diag_stage >= 3)
            actor_bottles_phase = actor_pose_advance(
                actor_bottles_phase, dt, ACTOR_BOTTLES_IDLE_DURATION);
#endif
    }

    footstep3dsExit();
    sceneExit();
    sfxProbe3dsExit();

    C3D_Fini();
    gfxExit();

    return 0;
}
