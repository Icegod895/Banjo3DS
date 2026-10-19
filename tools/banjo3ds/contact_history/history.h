#ifndef BANJO_CONTACT_HISTORY_H
#define BANJO_CONTACT_HISTORY_H
#include "../body/body.h"
/* Host-only SM observer. Not linked/called by the 3DS runtime. All pointer
 * inputs borrowed, immutable and non-aliasing with output. No queries/writes
 * to physics. Caller resets with playerGroundInit, NOT interaction/landing.
 * Water/immunity/overrides must be supplied from known state, never inferred
 * from input lock. Unsupported maps and unknown predicates fail atomically. */
typedef struct {
    uint32_t map, water, immune3, immune4, special_request;
    uint32_t override_enabled[4];
    float override_value[4];
} ChEngine;
typedef struct {
    uint32_t serial, grounded, forced, special_valid, floor_flags, material_flags;
    float position[3], support[3], special_height, dt;
    int32_t primary_role, primary_record; /* both -1 when no primary this frame */
    uint32_t primary_flags;
    ChEngine engine;
} ChObservation;
typedef struct {
    uint32_t initialized, serial, below_special, category, grounded, forced;
    uint32_t floor_flags, material_flags, effective_flags, active;
    int32_t primary_role, primary_record;
    uint32_t primary_flags, special_valid, timer_refresh; /* 0, 5 or 6; no effect */
    float slope_timer, angle, coefficient, support[3], special_height;
} ChHistory;
void ch_reset(ChHistory *);
/* 1 committed, 0 resolution failed (no reads except result), -1 invalid.
 * serial starts at 1 and increments per successful observation; failed
 * attempts do not consume serial. Snapshot is the caller-owned ChHistory.
 * dt domain (0,.05] matches native candidate updates; zero-dt is no event.
 * Support is unit within 1e-4; abs(Y)>0.0174519997: original degree-table
 * endpoint is undefined in the decomp. No normalization/clamping repair. */
int ch_observe(ChHistory *, int resolution_result, const ChObservation *);
/* Read only SUCCESSFUL bp_resolve outputs before scratch reuse. Models must
 * be validated by bridge_model_open and remain alive. Last primary identity
 * comes from trace, never the correction-query scratch hit. No solver call. */
int ch_observe_body(ChHistory *, int result, uint32_t serial, float dt,
    const BgState *, const BqFloorState *, const BpTrace *,
    const BridgeModel *, const BridgeModel *, const ChEngine *);
#endif
