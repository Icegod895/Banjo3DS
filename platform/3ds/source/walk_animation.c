#include "walk_animation.h"
#include <math.h>
#include <string.h>

float walkAnimationDuration(float speed)
{
    /* bs/walk.c slow init + ba/anim.c horizontal velocity mapping.
     * ml_mapRange_f extrapolates; only the final duration is clamped. */
    float duration = ((speed - 80.0f) / 70.0f) * (0.6f - 1.3f) + 1.3f;
    return fminf(fmaxf(duration, 0.3f), 1.5f);
}

bool walkAnimationUpdate(WalkAnimation *s, const uint8_t *packet, size_t packetSize,
                         bool accepted, float speed, float dt, void *vertices,
                         const void *idle, size_t total, size_t first, size_t count, size_t stride)
{
    if (!s || !vertices || !idle || stride < 12 || count != 2085 ||
        first > total || count > total-first) return false;
    bool moving = accepted && isfinite(speed) && speed > 0 && isfinite(dt) && dt >= 0;
    if (moving) {
        float phase = s->phase + fminf(dt, 0.05f) / walkAnimationDuration(speed);
        phase -= floorf(phase);
        if (banjo_pose_evaluate(packet, packetSize, phase, &s->pose)) {
            /* B3P3 v1: header/factor + skeleton + loads precede corners. */
            const uint8_t *corners = packet + 36 + 960 + 5784;
            for (size_t i = 0; i < count; ++i) {
                unsigned load = (unsigned)corners[2*i]*256 + corners[2*i+1];
                memcpy((uint8_t *)vertices+(first+i)*stride, s->pose.xyz[load], 12);
            }
            s->phase = phase;
            s->walking = true;
            return true;
        }
        /* Invalid pose data must never leave a partially updated actor. */
    }
    s->phase = 0;
    if (!s->walking) return false;
    for (size_t i = 0; i < count; ++i)
        memcpy((uint8_t *)vertices+(first+i)*stride,
               (const uint8_t *)idle+(first+i)*stride, 12);
    s->walking = false;
    return true;
}
