#ifndef BANJO_FREE_B_CONTACT_H
#define BANJO_FREE_B_CONTACT_H
#include "contact.h"
#include "../camera/camera.h"

/* Zero once at lifecycle creation, NOT at B entry/re-entry. The local static
 * original D_8037DB9C survives ncDynamicCamB_init and camera reset functions. */
typedef struct { uint32_t obstruction_counter; float previous_rollback_dot; } BcFreeBState;
typedef struct {
    float previous[3], desired[3], smoothed[3], corrected[3], final_position[3], look[3], dot;
    uint32_t rollback_executed, rolled_back, free_b;
    BcTrace contact;
} BcFreeBTrace;
/* Original C03BC. Preconditions: finite vectors, independent storage.
 * Invoke ONLY when contact changed position and recovery did not succeed. */
bool bc_free_b_rollback(float *history, const float previous[3], const float desired[3],
    float camera[3], float *dot_output);
/* Host-testable complete static B composition; NOT called by the viewer.
 * Explicit collider-center target; inactive viewport transition only.
 * On failure camera/state/trace remain unchanged; scratch may change. */
bool bc_free_b_update(BanjoCamera *, BcFreeBState *, const BanjoCameraMath *,
    const BanjoCameraZoom *, const BanjoCameraTrigger *, size_t, const BanjoCameraInput *,
    const BqModel *opa, const BqModel *xlu, const float player_target[3],
    BcScratch *, BcFreeBTrace *);
#endif
