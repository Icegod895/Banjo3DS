#ifndef BANJO_CAMERA_CONTACT_H
#define BANJO_CAMERA_CONTACT_H
#include "../world_query/segment.h"
/* Static map only, validated borrowed B3Q1; no allocation or viewer linkage.
 * Domain excludes original fixed-buffer overflows (>100 cells/active tris).
 * -1 error is atomic for outputs/state. Scratch may change on any call.
 * Open models with bq_open first; buffers/inputs/outputs must not alias.
 * Domain: finite XYZ within +/-1e6, .5 < radius <= 10000, 0..32 steps.
 * Camera callers use radius35/3 steps and radius40/4 steps. */
typedef struct {float ab[3],ac[3],normal[3],xyz[3][3];int32_t record,cell;} BcTriangle;
typedef struct {BcTriangle triangles[100];} BcScratch;
typedef struct {uint32_t counter;float position_step[3],angular_step[3];} BcState;
typedef struct {
    uint32_t sphere_calls,line_calls,moving_calls,gated_calls;
    uint32_t obstruction_calls,recovery_attempts,changed,recovered;
    float pushed_previous[3],extended_end[3],subtracted_end[3];
} BcTrace;
/* Sphere returns summed normal/last occurrence, center unchanged.
 * Moving returns last tested clear endpoint, not an analytic TOI. */
int bc_sphere(const BqModel *,const BqModel *,const float[3],float,uint32_t,BqHit *);
int bc_moving(const BqModel *,const BqModel *,const float[3],float[3],float,int,uint32_t,BcScratch *,BqHit *);
int bc_gated(const BqModel *,const BqModel *,const float[3],float[3],float,int,uint32_t,BcScratch *,BqHit *);
/* BE484: previous and camera BOTH in/out; return camera-changed. */
int bc_contact(const BqModel *,const BqModel *,float previous[3],float camera[3],BcScratch *,BcTrace *);
/* Contact + conditional BC84C(1), NOT a complete state-B camera update.
 * Caller invokes only when contact is enabled (never node32/file-select/snap).
 * Zero-initialize state once, then preserve it across calls including misses
 * and unchanged-position updates. Target = original collider-center target,
 * supplied explicitly; not focus/lead. Does not run state B's subsequent
 * C03BC rollback, C04B0 orbit or rotation smoothing (later integration). */
int bc_state_b(const BqModel *,const BqModel *,float previous[3],float camera[3],
    const float player_target[3],BcState *,BcScratch *,BcTrace *);
#endif
