#ifndef BANJO_WORLD_SEGMENT_H
#define BANJO_WORLD_SEGMENT_H
#include <stdint.h>
#include <stddef.h>
/* Borrowed immutable B3Q1 blocks; caller keeps packet alive. No allocation. */
typedef struct {
    const uint8_t *vertices, *collision;
    int16_t grid[11];
    uint16_t vertex_count;
    int16_t global_norm;
    uint16_t role;
} BqModel;
typedef struct {
    float position[3], normal[3];
    int32_t role, occurrence, cell, surface;
    uint32_t flags;
    uint16_t indices[3];
} BqHit;
int bq_open(BqModel *out, const uint8_t *packet, size_t size);
/* 1 hit (end/out updated), 0 miss (both untouched), -1 outside defined domain
 * (both untouched). Original active-cell array permits at most 100 cells per
 * model query. Finite coordinates bounded to +/-1e6 avoid C integer overflow.
 * OPA required; XLU optional. No actor providers. No aliasing start/end/out. */
int bq_segment(const BqModel *opa, const BqModel *xlu,
               const float start[3], float end[3], uint32_t filter, BqHit *out);
/* 1 hit / 0 no hit -> height set; -1 invalid -> untouched. */
int bq_camera_terrain(const BqModel *opa, const BqModel *xlu,
                      const float camera[3], float *height);
#endif
