#ifndef BANJO_PREPHYSICS_RESPONSE_H
#define BANJO_PREPHYSICS_RESPONSE_H
#include "original_response.h"
#include "../contact_history/response_selection.h"
/* Epoch B: immutable caller snapshot AFTER state updates, BEFORE physics.
 * No input/dialogue inference. epoch is a caller-chosen nonzero identity;
 * the API never creates/increments it, and matching cannot prove freshness,
 * actual engine provenance, reset generation, or correct scheduling.
 * Caller keeps history and engine snapshots alive and unchanged throughout
 * the synchronous call. map must match the previous SM context. */
typedef struct {
    uint64_t epoch;
    uint32_t map;
    ChResponseEngine response;
} PrephysicsEngine;
typedef struct {
    uint64_t engine_epoch;
    uint32_t history_serial, map;
    ChResponseSelection selection;
    OriginalResponseOutput velocity;
} PrephysicsResponse;
/* Epoch A is the same authentic, UNMODIFIED successful previous publication
 * required by G2C, including its frozen fields' validity. Only the response
 * arithmetic uses current selection; category/floor/support/timer are retained.
 * Previous map is a caller assertion (ChHistory does not store a map field).
 * 1 success, 0 invalid/unsupported, all output unchanged on failure.
 * Output overlap with either input/history is rejected. No queries, position
 * writes, history copies/patches, serial/timer advancement or mutable globals.
 * Original G2C float/domain requirements apply. Pure repeated calls allowed;
 * no transaction/commit or replay protection is claimed by the epoch token. */
int original_horizontal_response_prephysics(const OriginalResponseInput *,
    const PrephysicsEngine *, uint64_t expected_engine_epoch, PrephysicsResponse *);
#endif
