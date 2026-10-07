#ifndef BANJO_BODY_PHASE_H
#define BANJO_BODY_PHASE_H
#include "../ground/ground.h"
#include "../bridge_state/queries.h"
/* Normal Banjo, static map only. Borrow the existing published BridgeModel views
 * and camera math lookup; no private geometry, publication or timing state. */
typedef struct {float normal[3];uint32_t stuck;} BpState;
typedef struct {
 float initial[3],after_line[3],after_floor[3],start_center[3],end_center[3],normal[3],final[3];
 int32_t role,record;uint32_t line_hit,grounded,paths;uint8_t floor[120];
} BpIteration;
typedef struct {
 float pushed_previous[3],fallback[3],final[3],normal[3];
 uint32_t iterations,hits,exhausted,forced;BpIteration iteration[5];
} BpTrace;
typedef struct {
 float position[3],previous[3],normal[3],end[3],start[3];BqHit hit;int contacted;
} BpStep;
typedef struct {BcScratch contact;BpStep steps[5];BpTrace trace;} BpScratch;
/* Caller already executed state update and physics/bg_candidate. Reuses E.1
 * floor resolution unchanged, postponing its velocity finalization to loop end.
 * 1 success (including no contacts), -1 unsupported/invalid/query overflow.
 * Error leaves phase/frame/floor/history/output untouched; scratch may change.
 * Water-controller state, forced-position freeze and dynamic providers excluded.
 * Repeated-body stuck counter is preserved; initialized to zero at map/player init.
 * No call to this layer is made by the live viewer. */
int bp_resolve(BpState *,BgState *,BgFrame *,BqFloorState *,const BridgeModel *,
               const BridgeModel *,const BanjoCameraMath *,unsigned,BpScratch *,BpTrace *);
#endif
