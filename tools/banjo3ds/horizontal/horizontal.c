#include "horizontal.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static float clamp(float x, float lo, float hi) {
    return x < lo ? lo : x > hi ? hi : x;
}
static float angle(float x) {
    x = fmodf(x, 360.0f);
    return x < 0 ? x + 360.0f : x;
}
/* Finite [0,2pi] subset of libultra sinf/cosf, as in the proven pose evaluator.
 * Do not substitute host/newlib trig: cardinal residuals affect float goldens. */
static float trig(float a, bool cosine) {
    uint32_t bits; memcpy(&bits, &a, 4);
    unsigned exponent = (bits >> 22) & 511;
    if (!cosine && exponent < 0xe6) return a;
    double x = cosine ? fabs(a) : a;
    int n = 0;
    if (cosine || exponent >= 0xff) {
        double dn = x * 0x1.45f306dc9c883p-2 + (cosine ? 0.5 : 0.0);
        n = (int)(dn + (dn >= 0 ? 0.5 : -0.5));
        dn = n - (cosine ? 0.5 : 0.0);
        x = (x - dn * 0x1.921fb50000000p+1) - dn * 0x1.110b4611a6263p-25;
    }
    double square = x*x;
    double p = ((0x1.5dbdf0e314bfep-19*square - 0x1.9f6ffeea56814p-13)*square
                + 0x1.110ed3804c2a0p-7)*square - 0x1.55554bc83656dp-3;
    float r = (float)(x + (x*square)*p);
    return n & 1 ? -r : r;
}
static void target_vector(BanjoHorizontal *s) {
    /* ml.c:func_80256D0C with pitch/X/Y zero, including the original adds. */
    float radians = (float)(s->heading * (3.141592654 / 180.0));
    float sn = trig(radians, false), cs = trig(radians, true);
    s->target[0] = s->target_speed*sn + cs*0.0f;
    s->target[1] = s->target_speed*cs - sn*0.0f;
}
float banjo_horizontal_n64_axis(int raw, bool y_axis) {
    int maximum = y_axis ? 61 : 59;
    if (raw > 0) {
        raw = raw > maximum ? maximum : raw < 7 ? 7 : raw;
        raw = (raw - 7)*80/(maximum - 7);
    } else if (raw < 0) {
        raw = raw < -maximum ? -maximum : raw > -7 ? -7 : raw;
        raw = (raw + 7)*80/(maximum - 7);
    }
    return (1/80.f)*raw;
}
float banjo_horizontal_magnitude(float x, float y) {
    float m = sqrtf(x*x + y*y);
    /* bastick_update compares against double 1.0. */
    return m > 1.0 ? 1.0f : m;
}
float banjo_horizontal_target(float m) {
    /* bastick float zone markers + ml_interpolate_f; equality is lower band. */
    static const float bounds[] = {.12f, .2f, .5f, .75f, 1.f};
    static const float speeds[] = {30.f, 80.f, 150.f, 225.f, 500.f};
    if (m <= bounds[0]) return 0;
    m = fminf(m, 1.f);
    for (int i = 1; i < 5; ++i) {
        if (m <= bounds[i]) {
            float fraction = (m - bounds[i-1])/(bounds[i] - bounds[i-1]);
            return fraction*(speeds[i] - speeds[i-1]) + speeds[i-1];
        }
    }
    return 0;
}
float banjo_horizontal_yaw(float visible, float ideal, float dt) {
    float limit = 700.f*dt, delta = ideal - visible;
    if (fabsf(delta) > 180.0f) delta += delta < 0 ? 360.0 : -360.0;
    float step = delta*7.5f*dt;
    step = step < 0 ? clamp(step, -limit, -.1f) : clamp(step, .1f, limit);
    visible = fabsf(step) <= fabsf(delta) ? visible + step : ideal;
    if (visible < 360.0) {
        if (visible < 0.0) visible += 360.0;
    } else visible -= 360.0;
    return visible;
}
bool banjo_horizontal_should_skid(float ideal, float visible, float speed) {
    /* playerutils.c:func_8028B4C4 + walk.c gate. Caller must be WALK/FAST. */
    float delta = ideal - visible;
    while (delta > 180) delta -= 360;
    while (delta <= -180) delta += 360;
    return fabsf(delta) > 135.f && speed > 125.f;
}
float banjo_horizontal_skid_target(float phase, float starting_speed) {
    /* turn.c:bsturn_update -> ml_map_f, NOT an animation-derived guess. */
    float value = ((phase - .18f)/(1.f - .18f))*(0.f - starting_speed) + starting_speed;
    return clamp(value, 0, starting_speed);
}
void banjo_horizontal_init(BanjoHorizontal *s, float yaw) {
    memset(s, 0, sizeof(*s));
    s->ideal_yaw = s->visible_yaw = s->heading = angle(yaw);
}
bool banjo_horizontal_intent(BanjoHorizontal *s, float magnitude, float world_yaw) {
    if (!s || !isfinite(magnitude) || magnitude < 0 || magnitude > 1 || !isfinite(world_yaw)) return false;
    s->intent.magnitude = magnitude;
    s->intent.desired_yaw = angle(world_yaw);
    s->target_speed = banjo_horizontal_target(magnitude);
    return true;
}
void banjo_horizontal_takeoff(BanjoHorizontal *s) {
    /* bsjump_init: overwrite actual XZ, not additive/preserved ground momentum. */
    if (s->intent.magnitude != 0) s->ideal_yaw = s->intent.desired_yaw;
    s->heading = s->ideal_yaw;
    s->target_speed = banjo_horizontal_target(s->intent.magnitude);
    target_vector(s);
    memcpy(s->velocity, s->target, sizeof(s->velocity));
}
bool banjo_horizontal_step(BanjoHorizontal *s, BanjoHorizontalMode mode, float dt) {
    if (!s || !isfinite(dt) || dt < 0 || dt > .05f || (unsigned)mode > BANJO_HORIZONTAL_LOCKED) return false;
    if (mode == BANJO_HORIZONTAL_GROUND) s->heading = s->ideal_yaw;
    if (mode == BANJO_HORIZONTAL_AIR && s->intent.magnitude > 0) s->heading = s->intent.desired_yaw;
    target_vector(s);
    float coefficient = mode == BANJO_HORIZONTAL_AIR ? .07f : .29f;
    /* physics.c:38. Preserve EACH float assignment and the DOUBLE divisor.
     * In particular (target-current)*c is not bit-equivalent. No FMA/fast-math. */
    float ratio = (float)(dt / 0.0333333);
    for (int i = 0; i < 2; ++i) {
        float scaled_target = s->target[i]*coefficient;
        float scaled_current = s->velocity[i]*coefficient;
        float delta = scaled_target - scaled_current;
        delta *= ratio;
        s->velocity[i] += delta;
        float displacement_velocity = s->velocity[i];
        if (fabsf(s->velocity[i]) < 0.0001) s->velocity[i] = 0;
        s->candidate[i] = displacement_velocity*dt; /* BEFORE tiny-velocity snap */
        s->accepted[i] = 0;
    }
    /* bsmethods.c:282: physics precedes yaw. Air controller 3 keeps ideal. */
    if (mode == BANJO_HORIZONTAL_GROUND && s->intent.magnitude != 0)
        s->ideal_yaw = s->intent.desired_yaw;
    if (mode != BANJO_HORIZONTAL_LOCKED)
        s->visible_yaw = banjo_horizontal_yaw(s->visible_yaw, s->ideal_yaw, dt);
    return true;
}
void banjo_horizontal_accept(BanjoHorizontal *s, float dx, float dz) {
    s->accepted[0] = dx; s->accepted[1] = dz;
}
BanjoHorizontalMetrics banjo_horizontal_metrics(const BanjoHorizontal *s, float dt) {
    BanjoHorizontalMetrics m = {s->intent.magnitude, s->target_speed,
        sqrtf(s->velocity[0]*s->velocity[0] + s->velocity[1]*s->velocity[1]), 0,
        {s->accepted[0], s->accepted[1]}};
    if (dt > 0) m.accepted_speed = sqrtf(s->accepted[0]*s->accepted[0] + s->accepted[1]*s->accepted[1])/dt;
    return m;
}
