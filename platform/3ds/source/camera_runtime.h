#ifndef BANJO_CAMERA_RUNTIME_H
#define BANJO_CAMERA_RUNTIME_H
#include "player_runtime.h"
#include "player_ground.h"
#include "camera.h"
#include "floor_bridge.h"
#include "renderer_culling.h"
#include "../../../tools/banjo3ds/bridge_state/queries.h"

enum { CAMERA_RUNTIME_OK=1, CAMERA_RUNTIME_WAIT=0,
       CAMERA_RUNTIME_QUERY_FAILED=-1, CAMERA_RUNTIME_UNSUPPORTED=-2,
       CAMERA_RUNTIME_INVALID=-3 };
typedef struct {
    BanjoCameraMath math;
    BanjoCamera camera;
    BqFloorBridge bridge;
    BridgeModel opa, xlu; /* Borrowed constant packet blocks. */
    const BanjoCameraZoom *zoom;
    const BanjoCameraTrigger *triggers;
    size_t trigger_count;
    float view[4][4];
    float pre_candidate[3]; /* Last genuine proposal, never accepted-position replay. */
    unsigned candidate_calls;
    int status;
    RendererWindingParity parity;
    bool initialized, floor_ready, view_ready;
    BcFreeBState contact; /* Lifetime state, never reset on B entry/landing. */
    BridgeState world_bridge;
    uint32_t learned_abilities; /* Explicit viewer input, not a save system. */
    PlayerGroundState player_ground;
    BpState body; /* 16-byte player history, separate from camera contact state. */
    BpSharedScratch query_scratch; /* Sequential player -> camera lease.
                                   * No separate persistent observer/trace copy. */
} CameraRuntime;

/* Deterministic B.9 viewport seed; first real update selects the actual zone.
 * No manufactured floor candidate or simulation frame during initialization. */
bool cameraRuntimeInit(CameraRuntime *s,const PlayerRuntime *player,
    const uint8_t *opa,size_t opa_size,const uint8_t *xlu,size_t xlu_size,
    const BanjoCameraZoom *zoom,const BanjoCameraTrigger *triggers,size_t count);
/* Input changes do not resurrect a despawned actor. Full RuntimeInit is the
 * fresh map lifecycle; diagnostic player void recovery preserves bridge state. */
void cameraRuntimeSetLearnedAbilities(CameraRuntime *s,uint32_t bits);
int cameraRuntimeMove(CameraRuntime *s,PlayerRuntime *player,
    float pad_x,float pad_y,float movement_yaw,float dt,int vi_frames,
    bool jump_pressed,bool camera_mode,
    const FloorVertex *vertices,const FloorTriangle *triangles,size_t count);
/* Single camera update after the existing floor bridge. Explicit original
 * collider-center target. No player/physics mutation, inactive viewport path. */
int cameraRuntimeUpdateView(CameraRuntime *s,const BanjoCameraInput *input,
    const float collider_center[3]);
/* One explicit RH -> LH boundary. No projection or camera-state mutation. */
bool cameraRareView(const BanjoCamera *camera,float view[4][4],RendererWindingParity *parity);
float cameraMovementYaw(const BanjoCamera *camera);
/* Adapt the complete camera XZ basis to movementDirection; debug is identity. */
void cameraMovementInput(const BanjoCamera *camera,bool debug,float debug_yaw,
    float pad_x,float pad_y,float input[3]);
/* Citro3D's default-60Hz VBlank counter, separate from clamped seconds. */
int cameraViFrames(uint32_t current,uint32_t previous);
#endif
