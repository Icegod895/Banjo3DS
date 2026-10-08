#ifndef BANJO_CAMERA_ZONES_H
#define BANJO_CAMERA_ZONES_H
#include "../camera_contact/free_b.h"
/* Host-only normal dry Banjo: no water/manual/override/active viewport state.
 * Immutable data built from the canonical setup; indices are original order. */
typedef struct { int32_t first,count,node; } BzGroup;
typedef struct { int32_t type,profile; BanjoCameraZoom zoom; } BzNode;
typedef struct {
    const BanjoCameraTrigger *triggers;
    const BzGroup *groups;
    const BzNode *nodes;
    size_t group_count,node_count;
} BzData;
typedef struct {
    int32_t group,local,profile,last_zoom;
    uint8_t enabled[80];
} BzState;
/* Initialize a NEW selection instance (all nodes enabled). Not a camera-mode
 * reset: retain this state across B/zoom transitions. Does not clear camera
 * smoothing or B history/counter. Initialize those separately at world start. */
void bz_init(BzState *);
bool bz_enable(BzState *,int32_t node,bool enabled);
/* Pure normal-mask1 lookup; previous group/local win if still eligible. */
int32_t bz_select(BzState *,const BzData *,const float stable_position[3]);
/* Transactional, one update. Stable query XYZ belongs to BanjoCamera;
 * force_refresh models the original explicit refresh event. No heap allocation.
 * Last zoom parameters survive the final zoom update on zone exit. */
bool bz_update(BzState *,BanjoCamera *,BcFreeBState *,const BanjoCameraMath *,
    const BzData *,const BanjoCameraInput *,bool force_refresh,
    const BqModel *,const BqModel *,const float target[3],BcScratch *,BcFreeBTrace *);
#endif
