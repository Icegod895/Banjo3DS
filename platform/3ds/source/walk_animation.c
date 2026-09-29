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
                         size_t total, size_t first, size_t count, size_t stride)
{
    if (!s || !vertices || stride < 12 || count != 2085 ||
        first > total || count > total-first || !isfinite(dt) || dt < 0) return false;
    if (!s->initialized) {
        /* Seed the actual idle target at t=0; no startup transition. */
        if (!banjo_pose_sample(packet, packetSize, BANJO_CLIP_IDLE, 0, s->pose.bones)) return false;
        s->phase = 0;
        s->factor = 1;
        s->walking = false;
        s->initialized = true;
    }
    bool moving = accepted && isfinite(speed) && speed > 0;
    if (moving != s->walking) {
        /* Includes interrupted transitions: snapshot mixed VALUES, not a clip. */
        memcpy(s->source, s->pose.bones, sizeof(s->source));
        s->walking = moving;
        s->phase = 0;
        s->factor = 0;
    }
    dt = fminf(dt, 0.05f);
    float duration = moving ? walkAnimationDuration(speed) : 5.5f;
    float phase = s->phase + dt / duration;
    phase -= floorf(phase);
    float factor = fminf(1.0f, s->factor + dt / 0.2f);
    if (!banjo_pose_sample(packet, packetSize, moving ? BANJO_CLIP_WALK : BANJO_CLIP_IDLE,
                           phase, s->pose.bones)) return false;
    /* Exact endpoint copies; no general blend at factor 1. */
    banjo_pose_blend(s->pose.bones, s->source, s->pose.bones, factor);
    if (!banjo_pose_apply(packet, packetSize, &s->pose)) return false;
    const uint8_t *corners = packet + 36 + 960 + 5784;
    for (size_t i = 0; i < count; ++i) {
        unsigned load = (unsigned)corners[2*i]*256 + corners[2*i+1];
        memcpy((uint8_t *)vertices+(first+i)*stride, s->pose.xyz[load], 12);
    }
    s->phase = phase;
    s->factor = factor;
    return true;
}
