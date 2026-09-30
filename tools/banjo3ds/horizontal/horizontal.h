#ifndef BANJO_HORIZONTAL_H
#define BANJO_HORIZONTAL_H
#include <stdbool.h>

/* World heading: 0 = +Z, 90 = +X. Magnitude is POST controller normalization.
 * No 3DS input, camera, collision, vertical physics or gait selection here. */
typedef struct { float magnitude, desired_yaw; } BanjoHorizontalIntent;
typedef struct {
    BanjoHorizontalIntent intent;
    float target_speed, target[2], velocity[2]; /* X,Z; target != actual */
    float candidate[2], accepted[2];           /* displacements, NOT velocities */
    float ideal_yaw, visible_yaw, heading;
} BanjoHorizontal;
typedef enum {
    BANJO_HORIZONTAL_GROUND, BANJO_HORIZONTAL_AIR, BANJO_HORIZONTAL_LOCKED
} BanjoHorizontalMode;
typedef struct {
    float magnitude, target_speed, physics_speed, accepted_speed;
    float accepted[2];
} BanjoHorizontalMetrics;

/* Original joy.c per-axis normalization; separate from the 3DS radial adapter.
 * raw is an N64 signed-byte sample. y_axis selects 61 rather than 59. */
float banjo_horizontal_n64_axis(int raw, bool y_axis);
float banjo_horizontal_magnitude(float x, float y);
float banjo_horizontal_target(float magnitude);
float banjo_horizontal_yaw(float visible, float ideal, float dt);
bool banjo_horizontal_should_skid(float ideal, float visible, float speed);
float banjo_horizontal_skid_target(float phase, float starting_speed);
void banjo_horizontal_init(BanjoHorizontal *s, float yaw);
bool banjo_horizontal_intent(BanjoHorizontal *s, float magnitude, float world_yaw);
void banjo_horizontal_takeoff(BanjoHorizontal *s);
/* Finite dt in [0,.05]; invalid input returns false without changing state.
 * Consumes stored target_speed. A future state controller may explicitly
 * override it for idle entry / skid; this module does not choose those states.
 * GROUND: previous ideal -> physics, then input -> ideal -> visible smoothing.
 * AIR: input -> heading, then physics; visible smooths toward existing ideal.
 * LOCKED: existing heading, ordinary-ground response, no yaw update (skid).
 * accepted is cleared: caller must report the collision result separately. */
bool banjo_horizontal_step(BanjoHorizontal *s, BanjoHorizontalMode mode, float dt);
void banjo_horizontal_accept(BanjoHorizontal *s, float dx, float dz);
BanjoHorizontalMetrics banjo_horizontal_metrics(const BanjoHorizontal *s, float dt);
#endif
