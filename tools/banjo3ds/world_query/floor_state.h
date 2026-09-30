#ifndef BANJO_WORLD_FLOOR_STATE_H
#define BANJO_WORLD_FLOOR_STATE_H
#include "segment.h"
/* Original 0x60 logical fields. model is normalized: 0 none, 1 OPA, 2 XLU.
 * Uninitialized original diagnostic records/padding are canonically zero until
 * first written; they never participate in the floor state-machine. */
typedef struct {int16_t vertex[3],surface;uint32_t flags;} BqFloorTriangle;
typedef struct {
    uint32_t model;
    BqFloorTriangle floor_triangle,special_triangle;
    float candidate[3],previous[3],normal[3];
    float height,special_height,upper;
    uint32_t flags;
    int16_t surface,pad52;
    uint32_t filter;
    uint8_t valid,special_valid,old_valid,old_special_valid;
    uint8_t grace,countdown,mode,pad5f;
    /* Diagnostic identities: role/occurrence/cell, -1 before first copy.
     * Ordinary identity is retained even when model resets on no-hit, exactly
     * like the original copied triangle. Special identity is not used in math. */
    int32_t floor_ref[3],special_ref[3];
} BqFloorState;
void bq_floor_init(BqFloorState *s);
/* Original func_8031BA7C: mode=1,countdown=5; other history is retained. */
void bq_floor_reinit(BqFloorState *s);
/* One ORIGINAL candidate call, not one frame/final actor position.
 * parity is gGlobalTimer&1, identical for all calls within the frame.
 * SM ordinary upper=56, filter=baMarker mask (normally 0x400000).
 * Returns 1 success, -1 invalid primitive/input; failure leaves state intact.
 * No grounding, actor position correction or physics side effects. */
int bq_floor_update(BqFloorState *s,const BqModel *opa,const BqModel *xlu,
                    const float candidate[3],float upper,uint32_t filter,unsigned parity);
#endif
