#ifndef BANJO_ACTOR_POSE_H
#define BANJO_ACTOR_POSE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* A3P1 v1 actor pose. Parallel to the frozen B3P3 Banjo packet.
 * Caller owns the bone, matrix and load buffers. No heap and no globals.
 * Compile without fast-math or FP contraction.
 * anim_bytes == 0 is the boneless identity path (closed molehill).
 * A nonzero clip is sampled at phase * anim_last, phase in [0,1]. */
typedef struct {
    uint32_t matrix_count;
    uint32_t load_count;
    uint32_t corner_count;
    uint32_t bone_slots;
    uint32_t anim_bytes;
    uint16_t anim_last;
    uint16_t anim_channels;
    float factor;
    uint32_t boneless;
} ActorPoseInfo;
bool actor_pose_info(const uint8_t *packet, size_t size, ActorPoseInfo *out);
/* bones: bone_slots*10, matrices: matrix_count*16 row-major, xyz: load_count*3. */
bool actor_pose_evaluate(const uint8_t *packet, size_t size, float phase,
    float *bones, float *matrices, float *xyz);
#if BANJO3DS_ACTOR_BOTTLES_EMERGENCE
/* Source is a frozen bone_slots*10 pose, nonaliasing with output scratch.
 * Original quaternion/scale/translation blend, then the same A3P1 skinning. */
bool actor_pose_evaluate_blend(const uint8_t *packet, size_t size, float phase,
    const float *source, size_t source_slots, float factor,
    float *bones, float *matrices, float *xyz);
#endif
/* Copy posed XYZ into expanded triangle corners. count is the corner count. */
bool actor_pose_scatter(const uint8_t *packet, size_t size, const float *xyz,
    void *vertices, size_t total, size_t first, size_t count, size_t stride);
/* anctrl loop: fract(phase + dt/duration). Exact 1 becomes 0. */
float actor_pose_advance(float phase, float dt, float duration);
/* Row-major T(position) * Ry(yaw) * scale. Yaw is degrees. Yaw 0 is +Z. */
void actor_pose_placement(float rows[4][4], float x, float y, float z,
    float yaw_degrees, float scale);
#endif
