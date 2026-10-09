#ifndef BANJO_CAMERA_RUNTIME_H
#define BANJO_CAMERA_RUNTIME_H
#include "player_runtime.h"
#include "player_ground.h"
#include "camera.h"
#include "../../../tools/banjo3ds/camera_manual/manual.h"
#include "floor_bridge.h"
#include "renderer_culling.h"
#include "../../../tools/banjo3ds/bridge_state/queries.h"
#include "../../../tools/banjo3ds/camera_first_person/first_person.h"

enum { CAMERA_RUNTIME_OK=1, CAMERA_RUNTIME_WAIT=0,
       CAMERA_RUNTIME_QUERY_FAILED=-1, CAMERA_RUNTIME_UNSUPPORTED=-2,
       CAMERA_RUNTIME_INVALID=-3 };
typedef struct {
    BanjoCameraMath math;
    BmState manual; /* Internal camera, zones/contact history and visible viewport. */
    uint32_t manual_buttons, manual_enabled; /* Logical N64 inputs, no physical mapping. */
    BqFloorBridge bridge;
    BridgeModel opa, xlu; /* Borrowed constant packet blocks. */
    const BzData *zone_data; /* Immutable canonical setup, borrowed. */
    float view[4][4];
    float pre_candidate[3]; /* Last genuine proposal, never accepted-position replay. */
    unsigned candidate_calls;
    int status;
    RendererWindingParity parity;
    bool initialized, floor_ready, view_ready;
    BridgeState world_bridge;
    uint32_t learned_abilities; /* Explicit viewer input, not a save system. */
    PlayerGroundState player_ground;
    BpState body; /* 16-byte player history, separate from camera contact state. */
    BpSharedScratch query_scratch; /* Sequential player -> camera lease.
                                   * No separate persistent observer/trace copy. */
    FpCamera first_person;
    float first_person_gains[4];
    int32_t model_visible;
    float visible_position[3], visible_rotation[3];
} CameraRuntime;

/* Deterministic B.9 viewport seed; first real update selects the actual zone.
 * No manufactured floor candidate or simulation frame during initialization. */
bool cameraRuntimeInit(CameraRuntime *s,const PlayerRuntime *player,
    const uint8_t *opa,size_t opa_size,const uint8_t *xlu,size_t xlu_size,
    const BzData *zones);
/* Input changes do not resurrect a despawned actor. Full RuntimeInit is the
 * fresh map lifecycle; diagnostic player void recovery preserves bridge state. */
void cameraRuntimeSetLearnedAbilities(CameraRuntime *s,uint32_t bits);
int cameraRuntimeMove(CameraRuntime *s,PlayerRuntime *player,
    float pad_x,float pad_y,float movement_yaw,float dt,int vi_frames,
    bool jump_pressed,bool camera_mode,
    const FloorVertex *vertices,const FloorTriangle *triangles,size_t count);
/* Held logical BM_* inputs; enabled is the original bainput mask (bits 0,1,5).
 * Viewer supplies zero buttons. Repeated updates derive edges in bm_update. */
void cameraRuntimeManualInput(CameraRuntime *s,uint32_t buttons,uint32_t enabled);
/* Update DroneLook before physics, using the previous internal camera. */
void cameraRuntimeFirstPersonInput(CameraRuntime *,PlayerRuntime *,uint32_t,
    float stick_x,float stick_y,float dt,int vi_frames);
bool cameraRuntimeFirstPersonActive(const CameraRuntime *);
bool cameraRuntimeModelVisible(const CameraRuntime *);
/* Read BEFORE the player/camera update: movement follows the previous visible
 * viewport yaw even while the internal R camera has already moved. */
void cameraRuntimeMovementInput(const CameraRuntime *s,bool debug,float debug_yaw,
    float pad_x,float pad_y,float input[3]);
/* Single camera/viewport update after the existing floor bridge. Explicit
 * original collider-center target. No player/physics mutation. */
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
