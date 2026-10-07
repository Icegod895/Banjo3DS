#ifndef BANJO_BRIDGE_MOVEMENT_OVERLAY_H
#define BANJO_BRIDGE_MOVEMENT_OVERLAY_H
#include "bridge.h"
#include "../../../platform/3ds/source/movement.h"
/* Borrows the SAME state as BridgeModel/rendering. Read applied, never pending
 * offsets: actor -> player/camera -> mesh publication remains unchanged. */
MovementOverlay bridge_movement_overlay(const BridgeState *state);
#endif
