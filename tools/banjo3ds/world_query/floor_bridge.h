#ifndef BANJO_FLOOR_BRIDGE_H
#define BANJO_FLOOR_BRIDGE_H
#include "floor_state.h"
/* Bounded static-SM scheduling adapter, NOT Rare's iterative collision solver.
 * No linkage to the viewer. Caller supplies genuine pre-collision candidates.
 * Default ordinary SM upper/filter only: 56 / 0x400000. */
typedef struct {
    BqFloorState floor;
    uint32_t frame, next_ordinal;
    uint8_t initial_parity, active, initialized, reserved;
} BqFloorBridge;
/* New player/session: full allocation-equivalent reset; no query. */
int bq_bridge_init(BqFloorBridge *s,unsigned initial_parity);
/* Exactly one begin/end pair per simulation frame, including zero-callback
 * frames. Pausing without a frame does not advance parity. No nested begin. */
int bq_bridge_begin(BqFloorBridge *s);
/* Explicit relocation/reinitialization event, no query and no clock reset.
 * Original floor mode=1,countdown=5, all other history retained. Can occur
 * between frames or before a relocation candidate in the current frame. */
int bq_bridge_reinit(BqFloorBridge *s);
/* Ordinals start at zero each frame and increase only on successful queries.
 * Normal current-runtime path submits ONE candidate; no accepted/final replay.
 * Diagnostic recovery: explicit reinit + genuine relocated destination is a
 * SECOND callback with the same parity. This is port lifecycle policy. */
int bq_bridge_candidate(BqFloorBridge *s,const BqModel *opa,const BqModel *xlu,
                        const float xyz[3],uint32_t ordinal);
int bq_bridge_end(BqFloorBridge *s);
unsigned bq_bridge_parity(const BqFloorBridge *s);
#endif
