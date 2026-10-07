#include "movement_overlay.h"
#include "generated_bridge_movement.h"
static int16_t applied(const void *state,unsigned slot) {
    return ((const BridgeState *)state)->mesh[slot].applied;
}
MovementOverlay bridge_movement_overlay(const BridgeState *state) {
    const MovementOverlay overlay={banjo_bridge_movement_binding,
        BANJO_BRIDGE_MOVEMENT_BINDING_COUNT,state,applied};
    return overlay;
}
