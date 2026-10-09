#ifndef BANJO_GAIT_H
#define BANJO_GAIT_H
#include "pose.h"
/* Portable gait controller shared by host tests and the viewer. */
typedef enum { BANJO_GAIT_IDLE, BANJO_GAIT_CREEP, BANJO_GAIT_SLOW,
               BANJO_GAIT_WALK, BANJO_GAIT_FAST } BanjoGait;
typedef struct {
    BanjoPose pose;
    float source[109][10];
    float phase, factor;
    uint8_t gait;
    bool initialized;
} BanjoGaitState;
BanjoGait banjo_gait_select(BanjoGait current, bool accepted, float actualSpeed);
float banjo_gait_duration(BanjoGait gait, float actualSpeed);
BanjoClip banjo_gait_clip(BanjoGait gait);
float banjo_gait_start_phase(BanjoGait oldGait, BanjoGait newGait, float phase);
/* Zero-initialize state. Only pose/controller state changes; no VBO access.
 * Packet must be the validated canonical B3P3 v3/v4 export, or v5 (36994),
 * which is that v4 payload plus the appended crouch clips. Clips 0-4 are unchanged. */
bool banjo_gait_update(BanjoGaitState *state, const uint8_t *packet, size_t size,
                       bool accepted, float actualSpeed, float dt);
/* Same proven pose/phase/blend path, driven by an explicit gameplay decision.
 * Legacy acceptedSpeed/150 entry point remains for M4.5/M4.6 golden fixtures. */
bool banjo_gait_update_selected(BanjoGaitState *state, const uint8_t *packet, size_t size,
                               BanjoGait next, float duration, float dt);
#endif
