#ifndef BANJO_BOTTLES_B_INTERACTION_H
#define BANJO_BOTTLES_B_INTERACTION_H
#include <math.h>
#include "player_input.h"
#include "gait.h"
#include "../../../tools/banjo3ds/crouch/crouch.h"
/* Authorized B3-P1-FIX1 diagnostic policy, NOT Rare's full qualification.
 * Root XYZ replaces the cached model query. Scripted look-at/BF/interrupt
 * systems are outside this diagnostic. No gameplay or animation state here. */
#define BOTTLES_B_DIAGNOSTIC_RADIUS 250.0f
typedef struct { bool reserved, consumed; } BottlesBInput;
/* One already-qualified B press may wait for native recoil. The actor and
 * dialogue start remain owned by the existing B call site, not this latch. */
typedef struct { bool pending; } BottlesBPending;
static inline bool bottlesBPendingPoll(BottlesBPending *s, bool encounter_valid,
    bool recoil_complete, bool recoil_failed)
{
    if (!s->pending) return false;
    if (!encounter_valid || recoil_failed) { s->pending = false; return false; }
    if (!recoil_complete) return false;
    s->pending = false;
    return true;
}
typedef struct {
    float x, y, z, vertical_velocity;
    uint32_t abilities;
    unsigned gait;
    int action_request;
    bool waiting, grounded, jumping, first_person, crouching, conflict;
} BottlesBContext;
static bool bottlesBLocomotion(unsigned gait, int request)
{
    switch (gait) {
        case BANJO_GAIT_IDLE: case BANJO_GAIT_CREEP: case BANJO_GAIT_SLOW:
        case BANJO_GAIT_WALK: case BANJO_GAIT_FAST: break;
        default: return false;
    }
    /* Only no request or supported ordinary locomotion; attack requests are
     * meaningful even when their animation implementation is not present. */
    switch (request) {
        case 0: case BANJO_CROUCH_IDLE: case BANJO_CROUCH_CREEP:
        case BANJO_CROUCH_SLOW: case BANJO_CROUCH_WALK: case BANJO_CROUCH_FAST:
            return true;
        default: return false;
    }
}
static bool bottlesBEligible(const BottlesBContext *c, float hx, float hy, float hz)
{
    float dx = c->x - hx, dy = c->y - hy, dz = c->z - hz;
    return c->waiting && c->grounded && !c->jumping && !c->first_person &&
        !c->crouching && !c->conflict && !(c->abilities & (1u << 3)) &&
        bottlesBLocomotion(c->gait, c->action_request) &&
        isfinite(c->vertical_velocity) && c->vertical_velocity < 0 &&
        isfinite(dx) && isfinite(dy) && isfinite(dz) &&
        dx*dx + dy*dy + dz*dz < BOTTLES_B_DIAGNOSTIC_RADIUS * BOTTLES_B_DIAGNOSTIC_RADIUS;
}
static bool bottlesBConsume(BottlesBInput *s, PlayerInputFrame *f, bool eligible,
    bool physical_b, bool physical_b_pressed)
{
    bool suppress = s->consumed;
    if (!physical_b) s->consumed = false;
    bool start = eligible && s->reserved && !suppress && physical_b &&
        physical_b_pressed && (f->pressed & PI_N64_B) && (f->held & PI_N64_B);
    if (start) { s->consumed = true; suppress = true; }
    /* State changes/ineligible frames clear reservation. A consumed press
     * stays suppressed through release even after leaving the waiting state.
     * Mapping history is untouched: no artificial B edge or release leaks. */
    s->reserved = eligible && !suppress;
    if (suppress) {
        f->held &= ~(uint32_t)PI_N64_B;
        f->pressed &= ~(uint32_t)PI_N64_B;
        f->released &= ~(uint32_t)PI_N64_B;
    }
    return start;
}
#endif
