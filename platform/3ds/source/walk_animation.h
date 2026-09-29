#ifndef BANJO_WALK_ANIMATION_H
#define BANJO_WALK_ANIMATION_H
#include "pose.h"
typedef struct {
    BanjoPose pose;                 /* Last actually evaluated/mixed pose. */
    float source[109][10];          /* Frozen until the next state change. */
    float phase, factor;           /* Destination time and transition alpha. */
    bool walking, initialized;
} WalkAnimation;
float walkAnimationDuration(float speed);
/* Only XYZ (first 12 bytes of each vertex) is written. Caller must wait for
 * GPU completion first and flush the modified range before submission. */
bool walkAnimationUpdate(WalkAnimation *state, const uint8_t *packet, size_t packetSize,
                         bool accepted, float speed, float dt, void *vertices,
                         size_t total, size_t first, size_t count, size_t stride);
#endif
