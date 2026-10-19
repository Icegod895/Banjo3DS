/* Selector-2 diagnostic completion bridge. Included after the existing actor
 * and dialogue enums; owns no animation, rendering, input or player state. */
#ifndef BANJO3DS_BOTTLES_DIALOGUE_AUTO_EXIT_H
#define BANJO3DS_BOTTLES_DIALOGUE_AUTO_EXIT_H

enum { DAE_WAITING, DAE_ARMED, DAE_PENDING, DAE_DONE };
typedef struct { unsigned state; } DaeBridge;

static inline bool daeContext(int actor, unsigned selector)
{
    return selector == 2 && (actor == BOTTLES_EMERGING || actor == BOTTLES_IDLE);
}

static inline void daeObserve(DaeBridge *bridge, DsStatus dialogue, int actor, unsigned selector)
{
    if (!bridge || bridge->state == DAE_DONE) return;
    if (bridge->state == DAE_WAITING && dialogue == DS_WAITING &&
        actor == BOTTLES_WAITING && selector == 2) return;
    if (bridge->state > DAE_DONE || !daeContext(actor, selector) ||
        dialogue == DS_CANCELED || dialogue == DS_FAILED ||
        (unsigned)dialogue > DS_FAILED) {
        if (bridge) bridge->state = DAE_DONE;
        return;
    }
    if (dialogue == DS_ACTIVE && bridge->state == DAE_WAITING)
        bridge->state = DAE_ARMED;
    else if (dialogue == DS_COMPLETED) {
        if (bridge->state == DAE_ARMED) bridge->state = DAE_PENDING;
        else if (bridge->state != DAE_PENDING) bridge->state = DAE_DONE;
    } else if (bridge->state != DAE_WAITING && dialogue != DS_ACTIVE)
        bridge->state = DAE_DONE;
}

static inline bool daeRequest(DaeBridge *bridge, int actor, unsigned selector)
{
    if (!bridge) return false;
    /* WAITING before activation is normal. A pending request may wait for idle. */
    if (bridge->state > DAE_DONE || selector != 2 || actor < BOTTLES_WAITING ||
        actor >= BOTTLES_EXITING ||
        (actor == BOTTLES_WAITING && bridge->state != DAE_WAITING))
        bridge->state = DAE_DONE;
    return bridge->state == DAE_PENDING && actor == BOTTLES_IDLE && selector == 2;
}
#endif
