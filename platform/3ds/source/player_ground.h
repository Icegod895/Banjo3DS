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
unsigned playerGroundStep(void *,BanjoJumpMotion *,BanjoHorizontal *,float,bool,bool);
#endif
