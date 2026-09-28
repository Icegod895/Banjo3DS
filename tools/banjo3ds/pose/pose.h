#ifndef BANJO_HOST_POSE_H
#define BANJO_HOST_POSE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* Standalone B3P3 v1 evaluator; not linked into the viewer. Compile without
 * fast-math or FP contraction. Phase is inclusive [0,1]; no controller. */
typedef struct {
    float bones[109][10]; /* quaternion XYZW, scale XYZ, translation XYZ */
    float matrices[60][4][4]; /* Rare row-vector matrices */
    float xyz[723][3];
} BanjoPose;
bool banjo_pose_evaluate(const uint8_t *packet, size_t size, float phase, BanjoPose *out);
#endif
