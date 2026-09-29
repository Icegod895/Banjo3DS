#include "walk_animation.h"
#include <string.h>

bool walkAnimationUpdate(WalkAnimation *s, const uint8_t *packet, size_t packetSize,
                         bool accepted, float speed, float dt, void *vertices,
                         size_t total, size_t first, size_t count, size_t stride)
{
    if (!s || !vertices || stride < 12 || count != 2085 ||
        first > total || count > total-first) return false;
    if (!banjo_gait_update(s, packet, packetSize, accepted, speed, dt)) return false;
    /* B3P3 v3 retains the original skeleton/load/corner binding offsets. */
    const uint8_t *corners = packet + 36 + 960 + 5784;
    for (size_t i = 0; i < count; ++i) {
        unsigned load = (unsigned)corners[2*i]*256 + corners[2*i+1];
        memcpy((uint8_t *)vertices+(first+i)*stride, s->pose.xyz[load], 12);
    }
    return true;
}
