#ifndef BANJO_CAMERA_H
#define BANJO_CAMERA_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Normal, non-water Banjo only. No viewer, collision, manual camera or physics.
 * Angles are original BK viewport degrees, NOT Citro3D Euler angles. */
typedef struct { uint16_t angle_table[10001]; } BanjoCameraMath;
typedef struct {
    float anchor[3], offset[3], position_gains[2], rotation_gains[2];
    float close_distance, far_distance;
    uint32_t flags;
} BanjoCameraZoom;
typedef struct {
    int32_t position[3], radius, node, mask;
} BanjoCameraTrigger;
typedef struct {
    float position[3], rotation[3], focus[3], lead[3];
    float position_step[3], angular_step[3], stable_position[3];
    float orbit_yaw;
    int32_t mode, state, node, preset;
} BanjoCamera;
typedef struct {
    float player[3], floor_height, visible_yaw, floor_under_camera;
    float dt; /* time_getDelta(), finite [0,.05] */
    int32_t vi_frames; /* time_getDeltaReal_frames(), [1,15], separate from dt */
    bool stable; /* player_isStable(): refresh zone probe only when true */
} BanjoCameraInput;

/* Transactional internal phase boundary. prepare leaves the committed camera
 * untouched. next contains position smoothing, but NO look/rotation update.
 * previous is immutable rollback input; contact must push a separate copy.
 * Keep zoom/input/math unchanged between prepare and finish. */
typedef struct {
    BanjoCamera next;
    float previous[3], desired[3];
    float angular_gain, angular_response, anchor_distance;
} BanjoCameraPhase;
bool banjo_camera_prepare(BanjoCameraPhase *phase, const BanjoCamera *s,
    const BanjoCameraMath *, const BanjoCameraZoom *, const BanjoCameraTrigger *,
    size_t count, const BanjoCameraInput *);
/* Internal evaluator boundary for an independently resolved dry-Banjo zone.
 * Caller validates input, maintains stable_position, profile and last zoom.
 * Selection has completed BEFORE lead update/position smoothing. */
bool banjo_camera_prepare_selected(BanjoCameraPhase *, const BanjoCamera *,
    const BanjoCameraMath *, const BanjoCameraZoom *, const BanjoCameraInput *,
    int32_t node, bool zoom_selected, float radius, float height);
/* Postprocessing may change next.position and its smoothing accumulators.
 * Reheading only on effective contact change; recovery sets rotation BEFORE
 * ordinary angular smoothing. Optional look_output observes that target.
 * Successful recovery's accumulator reset belongs to the contact layer. */
bool banjo_camera_finish(BanjoCamera *s, const BanjoCameraPhase *phase,
    const BanjoCameraMath *, const BanjoCameraZoom *, const BanjoCameraInput *,
    bool contact_changed, bool recovered, float look_output[3]);

void banjo_camera_math_init(BanjoCameraMath *math);
/* Explicit initial viewport/probe. Lead/accumulators reset to zero as Rare init.
 * State B starts at its init hook; first zone selection occurs in update. */
void banjo_camera_init(BanjoCamera *s, const BanjoCameraMath *math,
                       const BanjoCameraInput *in, const float eye[3],
                       const float rotation[3]);
/* The setup parser supplies real 071D records. Supports node32/no zone only.
 * Unsupported zones/invalid inputs return false without mutating camera state.
 * Existing node32 membership has Rare's preference over a new zone.
 * floor_under_camera is an explicit external sample, NOT the player floor.
 * No collision correction is pretended: this is the unobstructed contract. */
bool banjo_camera_update(BanjoCamera *s, const BanjoCameraMath *math,
                         const BanjoCameraZoom *zoom,
                         const BanjoCameraTrigger *triggers, size_t count,
                         const BanjoCameraInput *in);
/* Original RH camera -> perspective NDC, fixed vertical FOV 40 degrees.
 * aspect must be explicit: BK=1.35185182f, no 3DS aspect choice here.
 * Positive fixed clips are caller/test data; no dynamic near-plane emulation.
 * Returns false for on/behind-eye points. No viewport tilt/pixel conversion. */
bool banjo_camera_project(const BanjoCamera *s, const float world[3],
                          float aspect, float near_plane, float far_plane,
                          float ndc[3]);
#endif
