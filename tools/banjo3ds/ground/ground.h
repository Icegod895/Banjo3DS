#ifndef BANJO_GROUND_PHASE_H
#define BANJO_GROUND_PHASE_H
#include "../world_query/floor_state.h"
/* Isolated ordinary static-map phase, NOT the complete player collision loop.
 * No body contacts, stuck-ground override, water state, slide or animation.
 * floor_height is the PREVIOUS resolved floor at state-update time. */
typedef struct {
    float position[3], vertical_velocity, floor_height;
    uint32_t grounded, falling;
} BgState;
typedef struct {
    float previous[3], candidate[3], requested[3], normal[3];
    uint32_t previous_grounded;
} BgFrame;
typedef int (*BgFloorQuery)(BqFloorState *,const BqModel *,const BqModel *,
                           const float[3],float,uint32_t,unsigned);
/* Call BEFORE choosing/evaluating the horizontal physics response. Returns
 * entry into BS_2F_FALL; no jump impulse, gravity reset or velocity reset.
 * falling is only an entry latch, not a landing/animation state machine. */
int bg_state_update(BgState *);
/* horizontal_velocity is the already evaluated physics velocity, NOT intent
 * or accepted displacement. dt is the original simulation delta, no new cap. */
void bg_candidate(BgState *,const float horizontal_velocity[2],float dt,BgFrame *);
/* Original func_8029350C post-query branch. No body correction is performed.
 * Keep unsuffixed 0.432/0.9 comparisons: those are original double literals. */
void bg_resolve(BgState *,BgFrame *,float floor_height,const float normal[3]);
/* Existing persistent query supplier (bq_floor_update/bridge_floor_update).
 * Upper=56, ordinary marker mask=0x400000; caller owns parity/lifecycle.
 * Error leaves state/frame unchanged (provider has its own atomic contract).
 * This is ONE floor phase. It cannot synthesize Rare's body-loop candidates. */
int bg_query_resolve(BgState *,BgFrame *,BqFloorState *,const BqModel *,
                     const BqModel *,unsigned parity,BgFloorQuery);
#endif
