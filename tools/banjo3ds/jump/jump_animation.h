#ifndef BANJO_JUMP_ANIMATION_H
#define BANJO_JUMP_ANIMATION_H
#include "pose.h"
/* Portable host-tested layer shared with the viewer. Together
 * with BanjoJumpMotion this is the minimal jump state. */
typedef struct {
    BanjoPose pose;
    float source[109][10];
    float phase, factor, duration, transition;
    uint8_t clip; /* fixed-width storage: ARM uses short enums */
    uint8_t segment; /* jump: 0 takeoff, 1 airborne, 2 held; gait: ignored */
} BanjoJumpAnimation;
/* Freeze VALUES of the last evaluated mixed pose, including interruption.
 * source may alias s->pose.bones. Jump always begins at .3; gait at zero. */
bool banjo_jump_animation_begin(BanjoJumpAnimation *s, const float source[109][10],
                                BanjoClip clip, float duration);
bool banjo_jump_animation_step(BanjoJumpAnimation *s, const uint8_t *packet, size_t size, float dt);
/* Actual floor contact: nominal existing gait selection, no landing lock.
 * The caller supplies accepted ground movement, not pre-contact air speed. */
void banjo_jump_animation_land(BanjoJumpAnimation *s, bool accepted, float speed);
#endif
