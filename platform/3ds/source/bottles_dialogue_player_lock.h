/* Bounded selector-2 native rest policy, not Rare's balookat/state stack.
 * Included after the existing actor/dialogue enums. No HID or GPU ownership. */
#ifndef BANJO3DS_BOTTLES_DIALOGUE_PLAYER_LOCK_H
#define BANJO3DS_BOTTLES_DIALOGUE_PLAYER_LOCK_H
#include "player_input.h"
#include "horizontal.h"
enum { DPL_UNLOCKED, DPL_LOCKED, DPL_DONE };
typedef struct { unsigned state; uint32_t held_actions; } DplLock;

static inline bool dplBegin(DplLock *s, bool accepted, int actor, unsigned selector)
{
    if (!s || s->state != DPL_UNLOCKED || !accepted ||
        actor != BOTTLES_WAITING || selector != 2) return false;
    s->state = DPL_LOCKED;
    return true;
}
static inline void dplRelease(DplLock *s)
{
    if (s && s->state == DPL_LOCKED) s->state = DPL_DONE;
}
static inline void dplAbortStart(DplLock *s)
{
    /* Nothing was committed: a later genuinely new qualified B may retry. */
    if (s && s->state == DPL_LOCKED) s->state = DPL_UNLOCKED;
}
static inline void dplObserve(DplLock *s, DsStatus dialogue, int actor)
{
    if (!s || s->state != DPL_LOCKED) return;
    /* Completion waits for successful exit preparation. Failure recovers only
     * control, never forces an actor transition. SELECT can finish idle actors. */
    if (dialogue == DS_CANCELED || dialogue == DS_FAILED ||
        (unsigned)dialogue > DS_FAILED ||
        (dialogue == DS_WAITING && actor == BOTTLES_IDLE) ||
        actor < BOTTLES_EMERGING || actor >= BOTTLES_EXITING)
        dplRelease(s);
}
static inline void dplRest(BanjoHorizontal *h)
{
    /* Stop stored horizontal propulsion once. Preserve position, gravity,
     * ground/contact history, heading and all animation-controller state. */
    h->intent.magnitude = 0;
    h->target_speed = 0;
    h->target[0] = h->target[1] = 0;
    h->velocity[0] = h->velocity[1] = 0;
}
static inline void dplFilter(DplLock *s, PlayerInputFrame *f)
{
    uint32_t blocked = s->held_actions;
    s->held_actions &= f->held;
    if (s->state == DPL_LOCKED) {
        s->held_actions = f->held;
        *f = (PlayerInputFrame){0};
        f->suppress_movement = true;
        return;
    }
    /* Downstream crouch/fp consumers derive their own edges from held bits.
     * Quarantine held actions until release; never restore an old input frame. */
    blocked |= s->held_actions;
    f->held &= ~blocked;
    f->pressed &= ~blocked;
    f->released &= ~blocked;
    f->manual &= ~blocked;
    if (blocked & PI_N64_A) f->jump_pressed = false;
}
#endif
