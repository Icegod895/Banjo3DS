#ifndef BANJO_CAMERA_RAIL_H
#define BANJO_CAMERA_RAIL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* Category-4 volumes and func_803411B0 chains from the canonical setup.
 * BrRuntime is the D_8037DBE0 rail plus the lead amplitudes that predicate
 * writes. No authored doorway positions. */
typedef struct {
    int32_t center[3], radius, actor, marker_bit, spline_actor, cube[3], prop;
} BrVolume;
typedef struct {
    const float *knots;
    int32_t count, actor, scale;
    float origin[3];
} BrSpline;
typedef struct {
    const BrVolume *volumes;
    const BrSpline *splines;
    int32_t volume_count, spline_count, cube_min[3], cube_width[3], stride[2];
} BrData;
typedef struct {
    int32_t spline;
    float step, param, captured[3], blend, sample[3];
    int32_t actor;
    uint8_t phase, previous, allow_zero, allow_one;
    float lead_near, lead_far, distance;
    int32_t predicate;
    float engage_distance;
    int32_t engage_predicate;
} BrRuntime;
void br_bind(const BrData *data);
bool br_bound(void);
size_t br_volume_size(void);
size_t br_spline_size(void);
size_t br_data_size(void);
size_t br_runtime_size(void);
#endif
