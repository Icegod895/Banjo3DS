#ifndef BANJO_JUMP_H
#define BANJO_JUMP_H
#include "movement.h"
#include "../horizontal/horizontal.h"
/* Banjo3DS policy, not the full Rare controller. Static point-foot collision.
 * Scene minimum collision Y (-504) minus 500 diagnostic safety margin. */
#define BANJO_JUMP_VOID_Y (-1004.0f)
#define BANJO_JUMP_CONTACT_EPSILON 0.01f
#define BANJO_JUMP_TAKEOFF 1u
#define BANJO_JUMP_LANDED 2u
#define BANJO_JUMP_RECOVERED 4u
#define BANJO_JUMP_MOVED 8u
typedef struct {
    MovementActor actor;
    float verticalVelocity;
    float lastSafeGroundPosition[3];
    bool grounded, hasSafeGround;
} BanjoJumpMotion;
/* Inclusive edges; equal-time hits retain the lowest exported triangle index.
 * Outputs untouched on failure. No wall/ceiling/volume response. */
bool banjo_jump_sweep(const FloorVertex *vertices, const FloorTriangle *triangles,
                     size_t count, const float start[3], const float end[3],
                     float contact[3], size_t *triangleIndex);
/* jumpPressed is an edge, never a held button. horizontalAllowed suppresses
 * ONLY horizontal displacement (e.g. a rejected proposal), never gravity.
 * cameraMode likewise suppresses input, not simulation. */
unsigned banjo_jump_step(BanjoJumpMotion *state, float padX, float padY, float cameraYaw,
                        float dt, bool jumpPressed, bool cameraMode, bool horizontalAllowed,
                        const FloorVertex *vertices, const FloorTriangle *triangles, size_t count);
/* Prepared intent; shared vertical/sweep/recovery path, accelerated XZ. */
unsigned banjo_jump_step_horizontal(BanjoJumpMotion *state, BanjoHorizontal *horizontal,
                        float dt, bool jumpPressed, bool cameraMode,
                        const FloorVertex *vertices, const FloorTriangle *triangles, size_t count);
#endif
