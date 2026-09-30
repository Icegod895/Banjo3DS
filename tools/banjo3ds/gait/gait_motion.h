#ifndef BANJO_GAIT_MOTION_H
#define BANJO_GAIT_MOTION_H
#include "gait.h"
#include "../horizontal/horizontal.h"
typedef struct { float downshift_remaining; uint8_t gait; } BanjoGaitMotion;
/* Input zones + pre-update physics speed, never accepted displacement.
 * Only ordinary walk.c selection; no skid/surface/player-state machine. */
BanjoGait banjo_gait_motion_select(BanjoGaitMotion *s, const BanjoHorizontalMetrics *m, float dt);
float banjo_gait_motion_duration(BanjoGait gait, float physicsSpeed);
#endif
