#ifndef BANJO_ORIGINAL_RESPONSE_H
#define BANJO_ORIGINAL_RESPONSE_H
#include "../contact_history/history.h"

/* Inert SM normal-horizontal response, NOT a native horizontal mode.
 * history must be an unmodified successful ch_observe[_body] publication
 * from the PREVIOUS resolution. Reset-only history (serial 0) is unusable.
 * map and history_serial explicitly identify the caller's intended context;
 * this pure API cannot authenticate a forged snapshot or decide frame order.
 * coefficient and active already include the observer's explicit engine
 * overrides/immunities. No category/mode substitution or new history here. */
typedef struct {
    const ChHistory *history;
    uint32_t history_serial, map;
    float velocity[2];                 /* X,Z, current stored velocity */
    float target_heading, target_speed; /* degrees; signed speed is supported */
    float dt;                          /* seconds, (0,.05] */
} OriginalResponseInput;

typedef struct {
    float displacement_velocity[2]; /* X,Z BEFORE tiny-component snapping */
    float stored_velocity[2];       /* X,Z AFTER snapping; neither is position */
} OriginalResponseOutput;

/* 1 success, 0 invalid/unsupported, output unchanged on failure.
 * All input storage is immutable and borrowed for this call. Overlap with
 * output is rejected. No allocation, queries, state advancement or live calls.
 * Requires binary32/binary64, default nearest rounding, gradual underflow,
 * no fast-math/contraction. Finite intermediates are required (no clamp).
 * Headings use original mlNormalizeAngle within its defined int32 cast
 * domain: abs(heading)/360 < 2147483648. Observer exclusions still apply,
 * including SM-only, timer [0,1], nonnegative coefficient, unit support and
 * abs(support.Y)>0.0174519997. Repeated calls are intentionally deterministic. */
int original_horizontal_response(const OriginalResponseInput *,
                                 OriginalResponseOutput *);
#endif
