#ifndef BANJO_PLAYER_GROUND_RUNTIME_H
#define BANJO_PLAYER_GROUND_RUNTIME_H
#include "player_runtime.h"
#include "../../../tools/banjo3ds/ground/ground.h"
#include "floor_bridge.h"
#include "../../../tools/banjo3ds/body/frame.h"
typedef struct {
    BgState phase;
    uint32_t fall_request;
    bool jump_flight;
    /* P27 isolated SELECT diagnostic; native ground/body remains the sole
     * movement and collision publisher. Never present in the original tree. */
    enum { PLAYER_RECOIL_NONE, PLAYER_RECOIL_REQUESTED,
           PLAYER_RECOIL_ACTIVE, PLAYER_RECOIL_COMPLETE } recoil;
    unsigned recoil_frames;
    float recoil_dx, recoil_dz, recoil_heading, recoil_face;
} PlayerGroundState;
/* Borrowed for one update; no ownership of geometry, provider or BridgeState. */
typedef struct {
    PlayerGroundState *state;
    BqFloorBridge *floor;
    BanjoCandidateObserver observe;
    void *context;
    const FloorVertex *vertices;
    const FloorTriangle *triangles;
    size_t count;
    const MovementOverlay *overlay;
    int *query_status;
    BpState *body;
    BpScratch *scratch;
    const BridgeModel *opa, *xlu;
    const BanjoCameraMath *math;
} PlayerGroundContext;
void playerGroundInit(PlayerGroundState *,const BanjoJumpMotion *);
bool playerGroundRequestRecoil(PlayerGroundState *,const BanjoJumpMotion *,
    float mole_x,float mole_y,float mole_z);
bool playerGroundRearmRecoil(PlayerGroundState *);
unsigned playerGroundStep(void *,BanjoJumpMotion *,BanjoHorizontal *,float,bool,bool);
/* Default hook is a no-op. The crouch runtime installs its own. Existing
 * traces never install one, so ground, jump and body results stay unchanged. */
typedef void (*PlayerGroundCrouchHook)(BanjoJumpMotion *motion,BanjoHorizontal *horizontal,
    float dt,bool *jump,int should_fall,int *lock_mode,float *facing,int *use_facing);
void playerGroundSetCrouchHook(PlayerGroundCrouchHook hook);
#endif
