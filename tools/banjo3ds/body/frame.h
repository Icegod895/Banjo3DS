#ifndef BANJO_BODY_FRAME_H
#define BANJO_BODY_FRAME_H
#include "body.h"
#include "../world_query/floor_bridge.h"
/* Future sequential player -> camera use. Never two simultaneous borrowers.
 * This union is NOT installed in CameraRuntime by the host-only proof. */
typedef union { BpScratch player; BcScratch camera; } BpSharedScratch;
/* Borrowed for one logical simulation update; no independent world/floor state.
 * Caller has already performed state selection and physics once, and begun the
 * floor clock. E.2 owns all genuine iterative floor queries until it returns. */
typedef struct {
    BqFloorBridge *clock;
    BpState *history;
    BgState *phase;
    const BridgeModel *opa, *xlu;
    const BanjoCameraMath *math;
    BpScratch *scratch;
} BpFrameContext;
/* Does not begin/end a frame, run physics, publish a mesh, replay a final floor
 * candidate, or allocate. Successful iterations are the query ordinals. Caller
 * ends the clock ONCE after collision/any explicit relocation lifecycle event.
 * Error commits no floor/body/phase/ordinal state. */
int bp_frame_resolve(const BpFrameContext *,BgFrame *,uint32_t frame_identity);
#endif
