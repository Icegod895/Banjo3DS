#ifndef BANJO_MOVEMENT_H
#define BANJO_MOVEMENT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { int16_t x, y, z; } FloorVertex;
typedef struct { uint16_t a, b, c; int16_t surface; uint32_t flags; } FloorTriangle;
typedef struct { float x, y, z, yaw; } MovementActor;

/* Diagnostic tuning, not guaranteed Circle Pad hardware limits. */
#define MOVEMENT_DEADZONE 20.0f
#define MOVEMENT_NOMINAL_MAXIMUM 156.0f
#define MOVEMENT_SPEED 150.0f
#define MOVEMENT_STEP 30.0f
#define MOVEMENT_MIN_NORMAL_Y 0.432f
#define MOVEMENT_FLOOR_FILTER 0x005E0000u

void movementNormalize(float x, float y, float out[2]);
void movementDirection(float x, float y, float cameraYaw, float out[2]);
float movementDelta(uint64_t now, uint64_t previous);
bool movementFloor(const FloorVertex *vertices, const FloorTriangle *triangles,
                   size_t count, float x, float z, float previousY, float *height);
bool movementUpdate(MovementActor *actor, float padX, float padY, float cameraYaw,
                    float dt, bool cameraMode, const FloorVertex *vertices,
                    const FloorTriangle *triangles, size_t count);
/* Row-major T(position) * Ry(yaw), yaw 0 faces +Z, +90 faces +X. */
void movementActorMatrix(const MovementActor *actor, float rows[4][4]);
#endif
