#ifndef BANJO_HOST_POSE_H
#define BANJO_HOST_POSE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* B3P3 v1 walk / v2 idle+walk / v3 four-clip evaluator. Compile without
 * fast-math or FP contraction. Phase is inclusive [0,1]; no controller. */
typedef struct {
    float bones[109][10]; /* quaternion XYZW, scale XYZ, translation XYZ */
    float matrices[60][4][4]; /* Rare row-vector matrices */
    float xyz[723][3];
} BanjoPose;
typedef enum { BANJO_CLIP_WALK, BANJO_CLIP_IDLE, BANJO_CLIP_CREEP, BANJO_CLIP_RUN } BanjoClip;
bool banjo_pose_sample(const uint8_t *packet, size_t size, BanjoClip clip, float phase, float out[109][10]);
bool banjo_pose_apply(const uint8_t *packet, size_t size, BanjoPose *out);
void banjo_pose_blend(float out[109][10], const float source[109][10],
                      const float destination[109][10], float factor);
bool banjo_pose_evaluate(const uint8_t *packet, size_t size, float phase, BanjoPose *out);
#endif
